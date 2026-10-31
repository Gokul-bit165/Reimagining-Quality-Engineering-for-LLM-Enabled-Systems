"""Local web UI backend: a thin read-only JSON API over ledgers + the static frontend.

Every number shown comes from `qe.report.viewer.build_view`, i.e. from the ledger only
(R10). The only write endpoint regenerates the offline demo ledgers (FakeLLM, loopback).
Run:  uv run --extra ui uvicorn qe.ui.server:app --port 8000
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.demo.run_demo import run_demo
from qe.report.viewer import build_view

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
