"""Real-LLM opt-in gating and the natural-defect track harness (offline; FakeLLM only)."""

from __future__ import annotations

import pytest

from sandbox_apps._common.llm import FakeLLM
from sandbox_apps._common.real_llm import CappedLLM, RealLLMNotAllowedError, real_llm_from_env
from sandbox_apps.natural_track import load_candidates, run_candidates

FULL = {
    "QE_ALLOW_REAL_LLM": "1",
    "QE_LLM_SPEND_BUDGET_USD": "5",
    "QE_LLM_MAX_CALLS": "3",
    "QE_LLM_MODEL": "some/model",
}


@pytest.mark.parametrize("missing", sorted(FULL))
def test_real_llm_refused_unless_every_gate_is_set(missing: str) -> None:
    env = {k: v for k, v in FULL.items() if k != missing}
    with pytest.raises(RealLLMNotAllowedError):
        real_llm_from_env("groq", env)


@pytest.mark.parametrize("bad", ["0", "-1", "abc"])
def test_budget_must_be_positive_number(bad: str) -> None:
    with pytest.raises(RealLLMNotAllowedError):
        real_llm_from_env("groq", {**FULL, "QE_LLM_SPEND_BUDGET_USD": bad})


def test_real_llm_built_without_network_or_key_read() -> None:
    llm = real_llm_from_env("openrouter", FULL)
    assert llm.max_calls == 3 and llm.model_name == "some/model"


def test_call_cap_is_hard() -> None:
    capped = CappedLLM(FakeLLM(), 2)
    capped.complete([{"role": "user", "content": "a"}])
    capped.complete([{"role": "user", "content": "b"}])
    with pytest.raises(RealLLMNotAllowedError):
        capped.complete([{"role": "user", "content": "c"}])


def test_natural_track_rows_are_unlabelled_and_cover_all_apps() -> None:
    rows = run_candidates(lambda: None)
    assert {r["app"] for r in rows} == {"chatbot", "rag", "multiagent", "toolagent"}
    assert len(rows) == len(load_candidates())
    assert all(r["human_label"] is None and r["meta"]["variant"] == "clean" for r in rows)
