"""Run an evaluation against a RagTarget; every call and verdict goes to a hash-chained ledger.

Ledger layout (all deterministic producers except drafted questions, R3):
  evalconfig            EVIDENCE_RECORDED  items (with lineage/seed), policy, flags
  test:<id>             TEST_DRAFTED       (llm_agent) questions drafted by a generator
  erun:<item>:<rep>     RUN_RECORDED       the target's raw response
  everdict:<item>       VERDICT_ISSUED     scores, passed, failure class
  estimate:<metric>     ESTIMATE_COMPUTED  metric with interval
  evalstatus            EVIDENCE_RECORDED  complete / incomplete reason
  evaldecision          DECISION_ISSUED
`replay()` recomputes everything from those events alone, without the target.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.realeval.assemble import assemble
from qe.realeval.dataset import EvalItem, QuestionGenerator, build_dataset, security_probes
from qe.realeval.dynamic import mutate_failures, normalize_risks, risk_variants
from qe.realeval.resolver import ResolvedProject
from qe.realeval.target import RagTarget, TargetAnswer

PRODUCER = "realeval"


class Judge(Protocol):
    family: str

    def judge(self, question: str, reference: str, answer: str) -> bool | None: ...


class JudgeNotIndependentError(ValueError):
    pass


@dataclass(frozen=True)
class Budget:
    max_calls: int = 500
    timeout_s: float = 900.0


@dataclass
class EvalParams:
    max_questions: int = 20
    repeats: int = 1
    include_security: bool = True
    generate_questions: bool = True
    policy: Policy | None = None
    risk_focus: list[str] = field(default_factory=list)
    seed: int = 0


@dataclass
class Inputs:
    project: ResolvedProject
    generator: QuestionGenerator | None = None
    judge: Judge | None = None
    prior_failures: list[EvalItem] = field(default_factory=list)
    prior_pass: dict[str, bool] = field(default_factory=dict)
    regression_items: list[EvalItem] = field(default_factory=list)


def _append(ledger: SQLiteLedger, key: str, etype: EventType, payload: dict[str, Any],
            kind: ProducerKind = ProducerKind.DETERMINISTIC) -> None:
    ledger.append(Event(key=key, type=etype, producer=PRODUCER, producer_kind=kind,
                        payload=payload))


def build_items(params: EvalParams, inputs: Inputs, budget: Budget,
                ) -> tuple[list[EvalItem], bool, list[str]]:
    p = inputs.project
    ds = build_dataset(p.documents, p.qa_pairs, max_questions=params.max_questions,
                       generate_questions=params.generate_questions, include_security=False,
                       generator=inputs.generator, canaries=p.canaries)
    risks, unknown = normalize_risks([*params.risk_focus, *p.risk_flags])
    notes = list(ds.notes)
    if unknown:
        notes.append(f"unrecognised risk labels ignored: {unknown}")
    notes.append(f"risk scenarios used: {risks}; seed={params.seed}")
    variants = risk_variants(ds.items, risks, params.seed, max(1, params.max_questions // 4))
    mutated = mutate_failures(inputs.prior_failures, params.seed)
    security = security_probes(p.documents, p.canaries) if params.include_security else []
    ordered = [*inputs.regression_items, *ds.items, *variants, *mutated]
    uniq = list({i.id: i for i in reversed(ordered)}.values())[::-1]  # first occurrence wins
    body = [i for i in uniq if i.source != "security"]
    sec_all = [*security, *(v for v in uniq if v.source == "security")]
    sec = list({i.id: i for i in reversed(sec_all)}.values())[::-1]
    room = max(0, budget.max_calls // params.repeats)
    if len(body) + len(sec) > room:
        notes.append(f"TRUNCATED by max_calls={budget.max_calls}: {len(body) + len(sec)} -> {room}")
        body = body[: max(0, room - len(sec))]
        sec = sec[:room]
    return [*body, *sec], ds.synthetic, notes


def _run_target(target: RagTarget, question: str) -> TargetAnswer:
    try:
        return target.ask(question)
    except Exception as exc:  # noqa: BLE001 - a crashing app is a measured failure
        return TargetAnswer(error=f"{type(exc).__name__}: {exc}")


def run_evaluation(eval_id: str, ledger_path: Path, params: EvalParams, inputs: Inputs,
                   budget: Budget, cancel: threading.Event,
                   on_progress: Callable[[dict[str, Any]], None] | None = None,
                   ) -> dict[str, Any]:
    if inputs.judge and inputs.generator and inputs.judge.family == inputs.generator.family:
        raise JudgeNotIndependentError("judge must come from a different model family than the "
                                       "question generator (R4)")
    items, synthetic, notes = build_items(params, inputs, budget)
    truncated = any(n.startswith("TRUNCATED") for n in notes)
    config: dict[str, Any] = {
        "eval_id": eval_id, "project_id": inputs.project.project_id,
        "items": [i.model_dump(mode="json") for i in items],
        "doc_names": [d["name"] for d in inputs.project.documents], "repeats": params.repeats,
        "synthetic": synthetic, "seed": params.seed, "notes": notes,
        "policy": params.policy.model_dump(mode="json") if params.policy else None,
        "prior_pass": inputs.prior_pass, "risk_focus": params.risk_focus,
        "budget": {"max_calls": budget.max_calls, "timeout_s": budget.timeout_s}}
    ledger = SQLiteLedger(ledger_path)
    runs: dict[str, list[dict[str, Any]]] = {}
    incomplete: str | None = "budget max_calls truncated the dataset" if truncated else None
    state = "done"
    try:
        _append(ledger, "evalconfig", EventType.EVIDENCE_RECORDED, {"kind": "config", **config})
        for it in items:
            if it.source == "generated" and it.lineage and it.lineage.get("operator") in (
                    "llm_question", "cloze", "unanswerable"):
                _append(ledger, f"test:{it.id}", EventType.TEST_DRAFTED,
                        {"item": it.model_dump(mode="json")}, ProducerKind.LLM_AGENT)
        start, calls = time.monotonic(), 0
        for it in items:
            if cancel.is_set():
                incomplete, state = "cancelled by user", "cancelled"
                break
            if time.monotonic() - start > budget.timeout_s:
                incomplete, state = f"timeout budget {budget.timeout_s}s exceeded", "failed"
                break
            recs: list[dict[str, Any]] = []
            for rep in range(params.repeats):
                if calls >= budget.max_calls:
                    break
                calls += 1
                ans = _run_target(inputs.project.target, it.question)
                rec = {"kind": "target_response", "item_id": it.id, "rep": rep,
                       "answer": ans.answer, "contexts": ans.contexts,
                       "latency_s": round(ans.latency_s, 6), "error": ans.error}
                _append(ledger, f"erun:{it.id}:{rep}", EventType.RUN_RECORDED, rec)
                recs.append(rec)
            runs[it.id] = recs
            if on_progress:
                on_progress(assemble({**config, "incomplete": "in progress"}, runs))
        judge_out = _judge(inputs.judge, items, runs)
        result = assemble({**config, "incomplete": incomplete}, runs, judge_out)
        _write_outcome(ledger, result, judge_out, incomplete, state)
    finally:
        ledger.close()
    return {**result, "state": state, "error": incomplete if state != "done" else None,
            "notes": notes, "config": {k: v for k, v in config.items() if k != "items"}}


def _judge(judge: Judge | None, items: list[EvalItem], runs: Mapping[str, list[dict[str, Any]]],
           ) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if judge is None:
        return out
    for it in items:
        rec = runs.get(it.id)
        if rec and it.reference_answer and not rec[0]["error"]:
            out[it.id] = judge.judge(it.question, it.reference_answer, rec[0]["answer"])
    return out


def _write_outcome(ledger: SQLiteLedger, result: dict[str, Any], judge_out: dict[str, Any],
                   incomplete: str | None, state: str) -> None:
    for row in result["items"]:
        _append(ledger, f"everdict:{row['id']}", EventType.VERDICT_ISSUED,
                {"item_id": row["id"], "scores": row["scores"], "passed": row["passed"],
                 "failure_class": row["failure_class"], "judge": judge_out.get(row["id"])})
    for name, m in result["metrics"].items():
        _append(ledger, f"estimate:{name}", EventType.ESTIMATE_COMPUTED, {"metric": name, **m})
    _append(ledger, "evalstatus", EventType.EVIDENCE_RECORDED,
            {"kind": "status", "incomplete": incomplete, "state": state, "judge": judge_out})
    _append(ledger, "evaldecision", EventType.DECISION_ISSUED,
            {"decision": result["decision"]["verdict"], "reasons": result["decision"]["reasons"],
             "evidence_ids": [f"estimate:{n}" for n in result["metrics"]]})


def replay(ledger_path: Path) -> dict[str, Any]:
    """Recompute the result from the ledger only (no target, no clock, no model)."""
    ledger = SQLiteLedger(ledger_path)
    try:
        report = ledger.verify()
        config: dict[str, Any] = {}
        status: dict[str, Any] = {}
        runs: dict[str, list[dict[str, Any]]] = {}
        confirmed: list[str] = []
        for e in ledger.entries():
            pl = e.event.payload
            if e.event.key.startswith("confirm:"):
                confirmed.append(str(pl["item_id"]))
            elif e.event.key == "evalconfig":
                config = pl
            elif e.event.key == "evalstatus":
                status = pl
            elif e.event.type is EventType.RUN_RECORDED:
                runs.setdefault(pl["item_id"], []).append(pl)
    finally:
        ledger.close()
    if not config:
        raise ValueError("ledger has no evaluation config")
    result = assemble({**config, "incomplete": status.get("incomplete")}, runs,
                      status.get("judge") or {}, confirmed)
    return {**result, "ledger_ok": report.ok, "ledger_entries": report.checked}
