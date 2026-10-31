"""Local web UI backend: a thin read-only JSON API over ledgers + the static frontend.

Every number shown comes from `qe.report.viewer.build_view`, i.e. from the ledger only
(R10). The only write endpoint regenerates the offline demo ledgers (FakeLLM, loopback).
Run:  uv run --extra ui uvicorn qe.ui.server:app --port 8000
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy, Signoff
from qe.demo.pipeline import APP_METRICS, TAXONOMY, run_scenario_variant
from qe.demo.run_demo import run_demo
from qe.demo.scenario_report import build_report
from qe.report.evidence_pack import render_json, render_markdown
from qe.report.viewer import build_view
from qe.risk.taxonomy import load_taxonomy

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def runs_dir() -> Path:
    return Path(os.environ.get("QE_RUNS_DIR", ROOT / "runs"))


def _open(run_id: str) -> tuple[SQLiteLedger, Policy]:
    if not RUN_ID.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    base = runs_dir() / run_id
    ledger_path, policy_path = base.with_suffix(".sqlite"), base.with_suffix(".policy.json")
    if not ledger_path.exists() or not policy_path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    policy = Policy.model_validate_json(policy_path.read_text("utf-8"))
    return SQLiteLedger(ledger_path), policy


def _summary(run_id: str) -> dict[str, Any]:
    ledger, policy = _open(run_id)
    try:
        view = build_view(ledger, policy)
    finally:
        ledger.close()
    pack = view["pack"]
    app_name, _, variant = run_id.rpartition("-")
    return {
        "id": run_id, "app": app_name, "variant": variant,
        "decision": pack["decision"]["decision"],
        "entries": pack["ledger"]["entries"], "verified": pack["ledger"]["verified"],
        "example_policy": pack["policy"]["example_only"],
    }


app = FastAPI(title="qe evidence UI", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    base = runs_dir()
    if not base.exists():
        return []
    ids = sorted(p.stem for p in base.glob("*.sqlite")
                 if RUN_ID.match(p.stem) and p.with_suffix(".policy.json").exists())
    return [_summary(i) for i in ids]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    ledger, policy = _open(run_id)
    try:
        view = build_view(ledger, policy)
        view["appetite"] = dict(policy.risk_appetite)
        return {"id": run_id, **view}
    finally:
        ledger.close()


@app.post("/api/demo")
def regenerate_demo() -> list[dict[str, Any]]:
    """Rebuild the four offline demo ledgers (clean/seeded x rag/toolagent)."""
    run_demo(runs_dir())
    return list_runs()


class ScenarioRequest(BaseModel):
    app: str
    taxonomy_id: str = Field(pattern=r"^LLM\d{2}$")
    scenario: str = Field(min_length=3, max_length=500)
    budget: int = Field(default=12, ge=1, le=40)
    previous_failures: list[str] = Field(default_factory=list, max_length=10)


class SignoffRequest(BaseModel):
    approver: str = Field(min_length=1, max_length=80)
    approved: bool
    note: str = Field(default="", max_length=500)


@app.get("/api/taxonomy")
def taxonomy() -> dict[str, Any]:
    t = load_taxonomy(TAXONOMY)
    return {"name": t.title, "status": t.status, "apps": sorted(APP_METRICS),
            "entries": [{"id": e.id, "title": e.title} for e in t.entries]}


@app.post("/api/scenarios")
def run_scenario(req: ScenarioRequest) -> dict[str, Any]:
    """Generate tests from a risk scenario and run the full pipeline on clean + seeded."""
    if req.app not in APP_METRICS:
        raise HTTPException(status_code=400, detail="unknown app")
    if req.taxonomy_id not in load_taxonomy(TAXONOMY).ids():
        raise HTTPException(status_code=400, detail="unknown taxonomy id")
    sid = content_id([req.app, req.taxonomy_id, req.scenario, sorted(req.previous_failures),
                      req.budget])[:8]
    ids = [f"scn-{sid}-{req.app}-{v}" for v in ("clean", "seeded")]
    for run_id, variant in zip(ids, ("clean", "seeded"), strict=True):
        asyncio.run(run_scenario_variant(
            runs_dir(), run_id, req.app, variant, req.taxonomy_id, req.scenario,
            req.previous_failures, req.budget))
    return {"scenario_id": sid, "runs": ids}


@app.get("/api/runs/{run_id}/report")
def get_report(run_id: str) -> dict[str, Any]:
    ledger, policy = _open(run_id)
    try:
        report = build_report(ledger, policy)
        return {"id": run_id, **report}
    finally:
        ledger.close()


@app.get("/api/runs/{run_id}/pack")
def get_pack(run_id: str, fmt: str = "json") -> PlainTextResponse:
    if fmt not in ("json", "md"):
        raise HTTPException(status_code=400, detail="fmt must be json or md")
    ledger, policy = _open(run_id)
    try:
        pack = build_report(ledger, policy)["pack"]
    finally:
        ledger.close()
    body = render_json(pack) if fmt == "json" else render_markdown(pack)
    return PlainTextResponse(body, media_type="application/json" if fmt == "json"
                             else "text/markdown")


@app.post("/api/runs/{run_id}/signoff")
def signoff(run_id: str, req: SignoffRequest) -> dict[str, Any]:
    """Human approval, recorded in the ledger. Only a HUMAN producer may write this event."""
    ledger, policy = _open(run_id)
    try:
        decision = build_report(ledger, policy)["decision"]
        decision_id = content_id(decision)
        record = Signoff(decision_id=decision_id, approver=req.approver.strip(),
                         approved=req.approved, note=req.note)
        n = sum(1 for e in ledger.entries() if e.event.type is EventType.SIGNOFF_RECORDED)
        ledger.append(Event(key=f"signoff:{n}", type=EventType.SIGNOFF_RECORDED,
                            producer="human-reviewer", producer_kind=ProducerKind.HUMAN,
                            payload=record.model_dump(mode="json")))
        return {"recorded": record.model_dump(mode="json"), "decision": decision["decision"]}
    finally:
        ledger.close()


@app.get("/api/monitoring-plan")
def monitoring_plan() -> dict[str, str]:
    path = ROOT / "docs" / "MONITORING_PLAN.md"
    return {"markdown": path.read_text("utf-8") if path.exists() else "Monitoring plan missing."}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
