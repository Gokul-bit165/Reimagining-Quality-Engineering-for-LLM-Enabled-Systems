"""Opt-in construction of a real LLM client for sandbox apps (never used by default or in tests).

Refuses to build a client unless ALL of these hold (project rule: no real model calls before the
owner sets a spend budget):
  * ``QE_ALLOW_REAL_LLM=1``
  * ``QE_LLM_SPEND_BUDGET_USD`` parses to a number > 0 (owner-set budget)
  * ``QE_LLM_MAX_CALLS`` parses to a positive integer (hard per-process call cap)
  * ``QE_LLM_MODEL`` names the model
Keys are read from the environment at call time by ``OpenAICompatibleLLM``, never here.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from sandbox_apps._common.llm import LLMClient, OpenAICompatibleLLM

PROVIDERS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


class RealLLMNotAllowedError(RuntimeError):
    pass


class CappedLLM:
    """Wraps a client with a hard call cap; the cap is shared by every app built from it."""

    def __init__(self, inner: LLMClient, max_calls: int) -> None:
        self._inner = inner
        self.max_calls = max_calls
        self.calls = 0
        self.model_name = str(getattr(inner, "model_name", "llm"))

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        if self.calls >= self.max_calls:
            raise RealLLMNotAllowedError("QE_LLM_MAX_CALLS reached")
        self.calls += 1
        return self._inner.complete(messages, **kw)


def real_llm_from_env(provider: str, env: Mapping[str, str] | None = None) -> CappedLLM:
    e = os.environ if env is None else env
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(PROVIDERS)}")
    if e.get("QE_ALLOW_REAL_LLM") != "1":
        raise RealLLMNotAllowedError("set QE_ALLOW_REAL_LLM=1 to opt in")
    try:
        budget = float(e.get("QE_LLM_SPEND_BUDGET_USD", ""))
    except ValueError:
        budget = 0.0
    if not budget > 0:
        raise RealLLMNotAllowedError("owner spend budget (QE_LLM_SPEND_BUDGET_USD) is not set")
    cap_raw = e.get("QE_LLM_MAX_CALLS", "")
    if not cap_raw.isdigit() or int(cap_raw) < 1:
        raise RealLLMNotAllowedError("QE_LLM_MAX_CALLS must be a positive integer")
    model = e.get("QE_LLM_MODEL", "")
    if not model:
        raise RealLLMNotAllowedError("QE_LLM_MODEL is not set")
    base_url, key_env = PROVIDERS[provider]
    return CappedLLM(OpenAICompatibleLLM(base_url, model, api_key_env=key_env), int(cap_raw))
