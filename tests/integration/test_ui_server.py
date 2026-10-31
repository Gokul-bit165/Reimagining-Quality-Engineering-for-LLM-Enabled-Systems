"""UI backend: health, frontend serving, and absence of the removed simulated-data endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe.ui import server


def test_health() -> None:
    assert TestClient(server.app).get("/api/health").json() == {"status": "ok"}


def test_index_is_503_json_when_frontend_not_built(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "FRONTEND_DIST", tmp_path)
    r = TestClient(server.app).get("/")
    assert r.status_code == 503
    assert r.json() == {"detail": "frontend not built; run npm run build in frontend/"}


def test_index_serves_built_frontend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "index.html").write_text("<html>app</html>", "utf-8")
    monkeypatch.setattr(server, "FRONTEND_DIST", tmp_path)
    assert "app" in TestClient(server.app).get("/").text


@pytest.mark.parametrize("path", ["/api/runs", "/api/demo", "/api/scenarios", "/api/benchmarks",
                                  "/api/taxonomy", "/api/config", "/api/monitoring-plan",
                                  "/static/index.html"])
def test_removed_simulated_endpoints_are_gone(path: str) -> None:
    assert TestClient(server.app).get(path).status_code in (404, 405)
