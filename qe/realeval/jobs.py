"""Background evaluation jobs persisted as JSON (+ a hash-chained ledger per run)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Signoff
from qe.realeval import audit
from qe.realeval.dataset import EvalItem
from qe.realeval.runner import Budget, EvalParams, Inputs, replay, run_evaluation

EVAL_ID = re.compile(r"^eval-[0-9a-f]{8}$")
ROOT = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()
_IO = threading.Lock()
_BY_PROJECT: dict[str, list[tuple[float, str]]] = {}
_INDEXED = False
_RUNNING: dict[str, threading.Event] = {}
_PRIVATE = ("config",)


def runs_dir() -> Path:
    return Path(os.environ.get("QE_RUNS_DIR", ROOT / "runs"))


def evals_dir() -> Path:
    return runs_dir() / "evals"


def _path(eid: str) -> Path:
    return evals_dir() / f"{eid}.json"


def _index(rec: dict[str, Any]) -> None:
    entry = (float(rec["created"]), rec["id"])
    ids = _BY_PROJECT.setdefault(rec["project_id"], [])
    if entry not in ids:
        ids.append(entry)


def _ensure_index() -> None:
    """One scan of the directory per process; afterwards _save keeps the index current."""
    global _INDEXED
    with _IO:
        if _INDEXED:
            return
        _INDEXED = True
        for p in sorted(evals_dir().glob("eval-*.json")) if evals_dir().is_dir() else []:
            _index(_read(p.stem))


def _save(rec: dict[str, Any]) -> None:
    evals_dir().mkdir(parents=True, exist_ok=True)
    _index(rec)
    with _IO:  # one writer at a time; readers retry (Windows refuses reads during replace)
        tmp = _path(rec["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        for attempt in range(50):
            try:
                tmp.replace(_path(rec["id"]))
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)


def _read(eid: str) -> dict[str, Any]:
    for attempt in range(50):
        try:
            data: dict[str, Any] = json.loads(_path(eid).read_text("utf-8"))
            return data
        except (PermissionError, json.JSONDecodeError):
            if attempt == 49:
                raise
            time.sleep(0.01)
    raise RuntimeError("unreachable")


def load(eid: str) -> dict[str, Any] | None:
    if not EVAL_ID.match(eid) or not _path(eid).is_file():
        return None
    rec = _read(eid)
    if rec["state"] in ("queued", "running") and eid not in _RUNNING:
        rec = {**rec, "state": "failed", "error": "interrupted (server restarted)"}
    return rec


def public(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if k not in _PRIVATE}


def list_all() -> list[dict[str, Any]]:
    if not evals_dir().is_dir():
        return []
    recs = [load(p.stem) for p in sorted(evals_dir().glob("eval-*.json"))]
    return [{"id": r["id"], "project_id": r["project_id"], "state": r["state"],
             "progress": r["progress"], "synthetic": r["synthetic"],
             "verdict": r["decision"]["verdict"] if r.get("decision") else None,
             "status": r["decision"].get("status") if r.get("decision") else None,
             "created": r["created"]} for r in recs if r]


def previous(project_id: str) -> dict[str, Any] | None:
    """Latest finished evaluation of this project (basis for failure mutation / regressions).
    Uses a project -> evaluations index, so cost is independent of other projects' history."""
    _ensure_index()
    for _, eid in sorted(_BY_PROJECT.get(project_id, []), reverse=True):
        rec = load(eid)
        if rec and rec["state"] in ("done", "cancelled", "failed") and rec.get("items"):
            return rec
    return None


def prior_context(project_id: str) -> tuple[list[EvalItem], dict[str, bool]]:
    prev = previous(project_id)
    if not prev:
        return [], {}
    failed = [EvalItem.model_validate({
        "id": r["id"], "question": r["question"], "reference_answer": r["reference_answer"],
        "source": r["source"], "answerable": r["answerable"], "risk": r["risk"],
        "lineage": r["lineage"], "probe": r.get("probe")})
        for r in prev["items"] if not r["passed"] and r["source"] != "security"]
    return failed, {r["id"]: bool(r["passed"]) for r in prev["items"]}


def start(project_id: str, params: EvalParams, inputs: Inputs, budget: Budget,
          monitoring: dict[str, Any] | None = None) -> dict[str, Any]:
    eid = "eval-" + uuid.uuid4().hex[:8]
    cancel = threading.Event()
    rec: dict[str, Any] = {
        "id": eid, "project_id": project_id, "state": "queued",
        "progress": {"done": 0, "total": 0},
        "error": None, "synthetic": False, "metrics": {}, "scorecard": {}, "items": [],
        "decision": None, "monitoring": monitoring, "failure_taxonomy": {}, "regression": None,
        "created": time.time(),
        "params": {"max_questions": params.max_questions, "repeats": params.repeats,
                   "include_security": params.include_security, "seed": params.seed,
                   "risk_focus": params.risk_focus}}
    _save(rec)
    with _LOCK:
        _RUNNING[eid] = cancel

    def snap(part: dict[str, Any]) -> None:
        _save({**rec, "state": "running", "progress": {"done": part["done"], "total":
               part["total"]}, "items": part["items"], "metrics": part["metrics"],
               "synthetic": part["synthetic"], "scorecard": part["scorecard"]})

    def work() -> None:
        final = {**rec, "state": "running"}
        _save(final)
        try:
            res = run_evaluation(eid, evals_dir() / f"{eid}.sqlite", params, inputs, budget,
                                 cancel, snap)
            out = {**rec, **res, "progress": {"done": res["done"], "total": res["total"]}}
            out.pop("done", None)
            out.pop("total", None)
            _save(out)
            audit.log(evals_dir(), f"evaluation_{res['state']}", evaluation_id=eid,
                      project_id=project_id, verdict=res["decision"]["verdict"])
        except Exception as exc:  # noqa: BLE001 - reported through the record
            _save({**rec, "state": "failed", "error": f"{type(exc).__name__}: {exc}"})
            audit.log(evals_dir(), "evaluation_failed", evaluation_id=eid, project_id=project_id,
                      error=type(exc).__name__)
        finally:
            with _LOCK:
                _RUNNING.pop(eid, None)

    threading.Thread(target=work, daemon=True, name=eid).start()
    return {"id": eid, "state": "queued"}


def cancel(eid: str) -> dict[str, Any] | None:
    rec = load(eid)
    if rec is None:
        return None
    with _LOCK:
        ev = _RUNNING.get(eid)
    if ev is not None:
        ev.set()
        audit.log(evals_dir(), "evaluation_cancel_requested", evaluation_id=eid,
                  project_id=rec["project_id"])
    return {"id": eid, "state": rec["state"] if ev is None else "cancelling"}


def wait(eid: str, timeout: float = 30.0) -> dict[str, Any]:
    """Test helper: block until the job leaves queued/running."""
    end = time.time() + timeout
    while time.time() < end:
        rec = load(eid)
        if rec and rec["state"] not in ("queued", "running") and eid not in _RUNNING:
            return rec
        time.sleep(0.02)
    raise TimeoutError(eid)


class SignoffError(Exception):
    pass


def signoff(eid: str, reviewer: str, decision: str, rationale: str) -> dict[str, Any]:
    rec = load(eid)
    if rec is None or not rec.get("decision"):
        raise SignoffError("evaluation has no decision to review yet")
    if rec["decision"]["status"] != "pending_review":
        raise SignoffError("decision already reviewed")
    approved = decision.lower() in ("approve", "approved")
    ledger = SQLiteLedger(evals_dir() / f"{eid}.sqlite")
    try:
        so = Signoff(decision_id=rec["decision"]["decision_id"], approver=reviewer.strip(),
                     approved=approved, note=rationale)
        ledger.append(Event(key="signoff:0", type=EventType.SIGNOFF_RECORDED,
                            producer="human-reviewer", producer_kind=ProducerKind.HUMAN,
                            payload=so.model_dump(mode="json")))
    finally:
        ledger.close()
    rec["decision"] = {**rec["decision"], "status": "approved" if approved else "rejected",
                       "signoff": {"reviewer": reviewer.strip(), "decision": decision.lower(),
                                   "rationale": rationale,
                                   "signed_digest": content_id(rec["decision"]["decision_id"])}}
    _save(rec)
    audit.log(evals_dir(), "signoff", evaluation_id=eid, project_id=rec["project_id"],
              reviewer=reviewer.strip(), decision=decision.lower())
    return rec


def confirm_item(eid: str, item_id: str, reviewer: str) -> dict[str, Any]:
    """Human confirms an advisory (LLM-generated) item; decision is recomputed from the ledger."""
    rec = load(eid)
    if rec is None or not rec.get("decision"):
        raise SignoffError("evaluation has no decision yet")
    if rec["decision"]["status"] != "pending_review":
        raise SignoffError("decision already reviewed; start a new evaluation instead")
    row = next((r for r in rec["items"] if r["id"] == item_id), None)
    if row is None:
        raise KeyError(item_id)
    if not (row["lineage"] or {}).get("advisory"):
        raise SignoffError("item is not advisory")
    path = evals_dir() / f"{eid}.sqlite"
    ledger = SQLiteLedger(path)
    try:
        ledger.append(Event(
            key=f"confirm:{item_id}", type=EventType.SIGNOFF_RECORDED, producer="human-reviewer",
            producer_kind=ProducerKind.HUMAN,
            payload={"kind": "item_confirmation", "item_id": item_id,
                     "reviewer": reviewer.strip()}))
    finally:
        ledger.close()
    fresh = replay(path)
    for k in ("items", "metrics", "scorecard", "decision", "failure_taxonomy", "regression",
              "advisory"):
        rec[k] = fresh[k]
    _save(rec)
    audit.log(evals_dir(), "item_confirmed", evaluation_id=eid, project_id=rec["project_id"],
              item_id=item_id, reviewer=reviewer.strip(), verdict=rec["decision"]["verdict"])
    return rec
