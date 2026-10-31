"""Endpoints: /api/evaluations/{id}/qa-report|evidence-bundle and the campaign twins."""

from __future__ import annotations

import io
import json
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.ingest.vault import VAULT
from qe.qareport.verify import verify_bundle
from qe.realeval import jobs
from qe.ui import routes_report
from qe.ui.server import app
from tests.qareport.conftest import (
    CREATED,
    TEST_SECRET,
    add_signoff,
    build_ledger,
)

client = TestClient(app)
EID = "eval-0000abcd"


def _install(state: str = "done", echo: str | None = None, ledger: bool = True) -> str:
    if ledger:
        jobs.evals_dir().mkdir(parents=True, exist_ok=True)
        build_ledger(jobs.evals_dir() / f"{EID}.sqlite", eval_id=EID, echo=echo)
        add_signoff(jobs.evals_dir() / f"{EID}.sqlite")
    jobs._save({"id": EID, "project_id": "proj-1", "state": state,
                "progress": {"done": 1, "total": 1}, "error": None, "metrics": {},
                "scorecard": {}, "items": [], "decision": None, "monitoring": None,
                "failure_taxonomy": {}, "regression": None, "created": CREATED,
                "params": {"seed": 1}})
    if state in ("queued", "running"):
        jobs._RUNNING[EID] = threading.Event()
    return EID


@pytest.fixture(autouse=True)
def _clean() -> Any:
    yield
    jobs._RUNNING.pop(EID, None)
    VAULT.clear("proj-1")


def test_json_report_endpoint_and_headers() -> None:
    _install()
    r = client.get(f"/api/evaluations/{EID}/qa-report?format=json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"] == f'inline; filename="qa-report-{EID}.json"'
    body = r.json()
    assert body["schema"] == "qe.qa-report/1" and body["targets"][0]["defects"]


def test_html_and_md_formats() -> None:
    _install()
    h = client.get(f"/api/evaluations/{EID}/qa-report?format=html")
    assert h.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in h.text and "DEF-" in h.text
    assert client.get(f"/api/evaluations/{EID}/qa-report").text == h.text  # html is the default
    m = client.get(f"/api/evaluations/{EID}/qa-report?format=md")
    assert m.headers["content-type"].startswith("text/markdown")
    assert m.headers["content-disposition"].endswith(f'qa-report-{EID}.md"')
    assert m.text.startswith("# Quality-tester report")


def test_bad_format_is_422_and_unknown_ids_are_404() -> None:
    _install()
    assert client.get(f"/api/evaluations/{EID}/qa-report?format=pdf").status_code == 422
    assert client.get("/api/evaluations/eval-ffffffff/qa-report").status_code == 404
    assert client.get("/api/evaluations/not-an-id/evidence-bundle").status_code == 404
    assert client.get("/api/campaigns/cmp-ffffffff/qa-report").status_code == 404
    assert client.get("/api/campaigns/nope/evidence-bundle").status_code == 404


def test_unfinished_evaluation_is_409() -> None:
    _install(state="running")
    r = client.get(f"/api/evaluations/{EID}/qa-report?format=json")
    assert r.status_code == 409 and "running" in r.json()["detail"]
    assert client.get(f"/api/evaluations/{EID}/evidence-bundle").status_code == 409


def test_evaluation_without_ledger_is_409() -> None:
    _install(ledger=False)
    assert client.get(f"/api/evaluations/{EID}/qa-report").status_code == 409


def test_bundle_download_streams_a_verifiable_zip(tmp_path: Path) -> None:
    _install()
    r = client.get(f"/api/evaluations/{EID}/evidence-bundle")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == f'attachment; filename="evidence-bundle-{EID}.zip"'
    assert int(r.headers["content-length"]) == len(r.content)
    path = tmp_path / "dl.zip"
    path.write_bytes(r.content)
    assert verify_bundle(path).ok
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.testzip() is None
        assert all(TEST_SECRET.encode() not in z.read(n) for n in z.namelist())


def test_bundle_withheld_with_409_when_a_vault_secret_leaked_into_evidence() -> None:
    VAULT.set("proj-1", {"OPENAI_API_KEY": TEST_SECRET})
    _install(echo=f"debug {TEST_SECRET}")
    r = client.get(f"/api/evaluations/{EID}/evidence-bundle")
    assert r.status_code == 409 and "withheld" in r.json()["detail"]
    assert TEST_SECRET not in r.text


def test_size_caps_return_413(monkeypatch: pytest.MonkeyPatch) -> None:
    _install()
    monkeypatch.setattr(routes_report, "MAX_REPORT_BYTES", 10)
    monkeypatch.setattr(routes_report, "MAX_BUNDLE_BYTES", 10)
    assert client.get(f"/api/evaluations/{EID}/qa-report?format=json").status_code == 413
    assert client.get(f"/api/evaluations/{EID}/evidence-bundle").status_code == 413


def test_report_endpoint_matches_json_in_bundle() -> None:
    _install()
    live = client.get(f"/api/evaluations/{EID}/qa-report?format=json").json()
    z = client.get(f"/api/evaluations/{EID}/evidence-bundle").content
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        assert json.loads(zf.read("report.json")) == live
