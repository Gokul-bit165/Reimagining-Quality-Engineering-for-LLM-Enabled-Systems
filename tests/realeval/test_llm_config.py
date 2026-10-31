"""Item 7: LLM configuration is discoverable (names only), env mapping and actionable errors."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe.core.dotenv import ALLOWED, load_dotenv
from qe.ui.server import app
from sandbox_apps._common.real_llm import (
    RealLLMNotAllowedError,
    missing_llm_config,
    real_llm_from_env,
)

client = TestClient(app)
FULL = {"QE_ALLOW_REAL_LLM": "1", "QE_LLM_SPEND_BUDGET_USD": "5", "QE_LLM_MAX_CALLS": "9",
        "QE_LLM_MODEL": "some/model", "GROQ_API_KEY": "sekret-value-123"}


def test_dotenv_allows_model_and_budget_names(tmp_path: Path) -> None:
    assert {"QE_LLM_MODEL", "QE_LLM_SPEND_BUDGET_USD", "QE_LLM_MAX_CALLS"} <= ALLOWED
    f = tmp_path / ".env"
    f.write_text("QE_LLM_MODEL=m/x\nEVIL=1\n", encoding="utf-8")
    env: dict[str, str] = {}
    assert load_dotenv(f, env) == ["QE_LLM_MODEL"] and env == {"QE_LLM_MODEL": "m/x"}


def test_agent_model_maps_to_generator_model_when_llm_model_unset() -> None:
    env = {k: v for k, v in FULL.items() if k != "QE_LLM_MODEL"} | {"QE_AGENT_MODEL": "agent/m"}
    assert real_llm_from_env("groq", env).model_name == "agent/m"
    assert real_llm_from_env("groq", {**env, "QE_LLM_MODEL": "own/m"}).model_name == "own/m"


def test_errors_list_everything_missing_actionably() -> None:
    with pytest.raises(RealLLMNotAllowedError) as exc:
        real_llm_from_env("groq", {})
    msg = str(exc.value)
    for name in ("QE_ALLOW_REAL_LLM", "QE_LLM_SPEND_BUDGET_USD", "QE_LLM_MAX_CALLS",
                 "QE_LLM_MODEL"):
        assert name in msg


def test_missing_config_names_only() -> None:
    assert missing_llm_config(FULL) == []
    gone = missing_llm_config({"QE_ALLOW_REAL_LLM": "1"})
    assert "QE_LLM_MODEL" in gone and "GROQ_API_KEY or OPENROUTER_API_KEY" in gone
    assert "QE_ALLOW_REAL_LLM" not in gone


def test_llm_status_endpoint_never_returns_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in FULL.items():
        monkeypatch.setenv(k, v)
    ok = client.get("/api/llm/status")
    assert ok.status_code == 200 and ok.json() == {"configured": True, "missing": []}
    monkeypatch.delenv("QE_LLM_MODEL")
    monkeypatch.delenv("QE_AGENT_MODEL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    bad = client.get("/api/llm/status").json()
    assert bad["configured"] is False
    assert "QE_LLM_MODEL" in bad["missing"]
    assert "sekret-value-123" not in str(bad) and "some/model" not in str(bad)
