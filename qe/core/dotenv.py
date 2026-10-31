"""Minimal .env loader. Only an explicit allow-list of names is read; values are never printed."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

ALLOWED = frozenset({
    "OPENROUTER_API_KEY", "GROQ_API_KEY", "QE_AGENT_MODEL", "QE_TARGET_MODEL",
    "QE_ALLOW_REAL_LLM", "QE_LLM_MAX_CALLS", "QE_LLM_SPEND_BUDGET_USD", "QE_LLM_MODEL",
    "QE_JUDGE_MODEL", "QE_JUDGE_MODEL_2", "QE_JUDGE_MAX_CALLS",
})


def load_dotenv(path: Path, env: MutableMapping[str, str] | None = None) -> list[str]:
    """Set allow-listed variables that are not already in the environment; returns names set."""
    target = os.environ if env is None else env
    if not path.is_file():
        return []
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        name, _, value = text.partition("=")
        name = name.strip().removeprefix("export ").strip()
        value = value.strip().strip("'\"")
        if name in ALLOWED and value and name not in target:
            target[name] = value
            loaded.append(name)
    return loaded
