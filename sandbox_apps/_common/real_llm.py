"""Opt-in construction of a real LLM client for sandbox apps (never used by default or in tests).

Refuses to build a client unless ALL of these hold (project rule: no real model calls before the
owner sets a spend budget):
  * ``QE_ALLOW_REAL_LLM=1``
  * ``QE_LLM_SPEND_BUDGET_USD`` parses to a number > 0 (owner-set budget)
  * ``QE_LLM_MAX_CALLS`` parses to a positive integer (hard per-process call cap)
  * ``QE_LLM_MODEL`` names the model
  * ``QE_AGENT_MODEL`` is accepted as the model when ``QE_LLM_MODEL`` is unset
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


KEY_NAMES = "GROQ_API_KEY or OPENROUTER_API_KEY"


def _model(e: Mapping[str, str]) -> str:
    """QE_LLM_MODEL, else QE_AGENT_MODEL (the generator model of the older env contract)."""
    return e.get("QE_LLM_MODEL") or e.get("QE_AGENT_MODEL") or ""


def _budget(e: Mapping[str, str]) -> float:
    try:
        return float(e.get("QE_LLM_SPEND_BUDGET_USD", ""))
    except ValueError:
        return 0.0


def missing_llm_config(env: Mapping[str, str] | None = None) -> list[str]:
    """Names (never values) of the settings still needed for a real LLM, in fix-it order."""
    e = os.environ if env is None else env
    missing: list[str] = []
    if e.get("QE_ALLOW_REAL_LLM") != "1":
        missing.append("QE_ALLOW_REAL_LLM")
    if not (e.get("GROQ_API_KEY") or e.get("OPENROUTER_API_KEY")):
        missing.append(KEY_NAMES)
    if not _model(e):
        missing.append("QE_LLM_MODEL")
    if not _budget(e) > 0:
        missing.append("QE_LLM_SPEND_BUDGET_USD")
    cap = e.get("QE_LLM_MAX_CALLS", "")
    if not cap.isdigit() or int(cap) < 1:
        missing.append("QE_LLM_MAX_CALLS")
    return missing


def real_llm_from_env(provider: str, env: Mapping[str, str] | None = None) -> CappedLLM:
    e = os.environ if env is None else env
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {sorted(PROVIDERS)}")
    # The key is read at call time, so it is not required to BUILD the client.
    gaps = [m for m in missing_llm_config(e) if m != KEY_NAMES]
    if gaps:
        hints = {"QE_ALLOW_REAL_LLM": "QE_ALLOW_REAL_LLM=1 (opt in to real model calls)",
                 "QE_LLM_MODEL": "QE_LLM_MODEL=<provider model id> (or QE_AGENT_MODEL)",
                 "QE_LLM_SPEND_BUDGET_USD": "QE_LLM_SPEND_BUDGET_USD=<number > 0> (owner budget)",
                 "QE_LLM_MAX_CALLS": "QE_LLM_MAX_CALLS=<positive integer> (hard call cap)"}
        raise RealLLMNotAllowedError(
            "real LLM is not configured; set in the backend environment or .env: "
            + "; ".join(hints[g] for g in gaps)
            + f"; plus a provider key ({KEY_NAMES})")
    base_url, key_env = PROVIDERS[provider]
    return CappedLLM(OpenAICompatibleLLM(base_url, _model(e), api_key_env=key_env),
                     int(e["QE_LLM_MAX_CALLS"]))
