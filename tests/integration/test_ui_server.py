"""UI backend: read-only JSON API over ledgers + demo regeneration. Offline, FakeLLM only."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe.demo.run_demo import run_demo
from qe.ui.server import app

DEMO_IDS = {"rag-clean", "rag-seeded", "toolagent-clean", "toolagent-seeded"}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    runs: Path = tmp_path_factory.mktemp("runs")
    run_demo(runs)
    mp = pytest.MonkeyPatch()
    mp.setenv("QE_RUNS_DIR", str(runs))
    yield TestClient(app)  # type: ignore[misc]
    mp.undo()


def test_lists_the_four_demo_runs_with_verified_ledgers(client: TestClient) -> None:
    rows = client.get("/api/runs").json()
    assert {r["id"] for r in rows} == DEMO_IDS
    assert all(r["verified"] and r["example_policy"] for r in rows)


def test_seeded_runs_show_failures_and_clean_runs_show_none(client: TestClient) -> None:
    def failed(run_id: str) -> int:
        pack = client.get(f"/api/runs/{run_id}").json()["pack"]
        return sum(m["failed_cases"] for m in pack["metrics"])

    assert failed("rag-clean") == 0 and failed("toolagent-clean") == 0
    assert failed("rag-seeded") > 0 and failed("toolagent-seeded") > 0


def test_small_samples_yield_insufficient_evidence_not_a_pass(client: TestClient) -> None:
    for row in client.get("/api/runs").json():
        assert row["decision"] == "INSUFFICIENT_EVIDENCE"


def test_run_detail_carries_intervals_and_appetite(client: TestClient) -> None:
    body = client.get("/api/runs/rag-seeded").json()
    rate = body["pack"]["metrics"][0]["failure_rate"]
    assert rate["lower"] < rate["point"] < rate["upper"]
    assert body["appetite"]["citation_validity"] > 0


@pytest.mark.parametrize("bad", ["../x", "..%2Fx", "A B", ".hidden", "x" * 80])
def test_invalid_ids_are_rejected_not_resolved_to_files(client: TestClient, bad: str) -> None:
    assert client.get(f"/api/runs/{bad}").status_code in (400, 404)


def test_unknown_run_is_404_and_index_is_served(client: TestClient) -> None:
    assert client.get("/api/runs/nope").status_code == 404
    assert "qe" in client.get("/").text


def test_static_assets_are_served(client: TestClient) -> None:
    for asset in ("tokens.css", "app.css", "app.js"):
        assert client.get(f"/static/{asset}").status_code == 200
