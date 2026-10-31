"""Regression tests for UI server hardening: scenario errors, caps, bench setup leak, secrets."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe.modelbench import jobs
from qe.ui import server
from qe.ui.server import app

BODY = {"app": "rag", "taxonomy_id": "LLM09", "scenario": "wrong shipping facts", "budget": 5}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    return TestClient(app)


def test_scenario_provider_429_maps_to_429_with_generic_detail(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*a: object, **k: object) -> None:
        raise RuntimeError("HTTP 429 secret-provider-body")

    monkeypatch.setattr(server, "run_scenario_variant", boom)
    r = client.post("/api/scenarios", json=BODY)
    assert r.status_code == 429
    assert "secret-provider-body" not in r.text


def test_scenario_non_rate_limit_failure_is_502_not_mislabelled(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*a: object, **k: object) -> None:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(server, "run_scenario_variant", boom)
    r = client.post("/api/scenarios", json=BODY)
    assert r.status_code == 502
    assert "OpenRouter" not in r.text


def test_scenario_concurrency_is_capped(client: TestClient) -> None:
    held = [server._SCENARIO_SLOTS.acquire(blocking=False) for _ in range(2)]
    try:
        assert client.post("/api/scenarios", json=BODY).status_code == 429
    finally:
        for ok in held:
            if ok:
                server._SCENARIO_SLOTS.release()


def test_scenario_rejects_oversized_previous_failure(client: TestClient) -> None:
    r = client.post("/api/scenarios", json={**BODY, "previous_failures": ["x" * 201]})
    assert r.status_code == 422


def test_bench_setup_failure_does_not_leave_id_running(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*a: object, **k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(jobs, "_write", fail)
    with pytest.raises(OSError):
        jobs.start(tmp_path, ["sim-strong"] if False else [next(iter(
            __import__("qe.modelbench.models", fromlist=["SIM_PROFILES"]).SIM_PROFILES))],
            "", 5, 1)
    assert jobs._RUNNING == set()


def test_config_never_returns_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SUPERSECRET")
    assert "SUPERSECRET" not in client.get("/api/config").text
