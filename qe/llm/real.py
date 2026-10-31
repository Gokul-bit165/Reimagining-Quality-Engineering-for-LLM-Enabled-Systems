"""Opt-in real models via OpenRouter: a tester (crew) LLM and a target-app LLM.

Rules kept: keys come from the environment only and are never logged or stored; every call
counts against one shared cap; only the OpenRouter host is exempted from the egress guard,
and only while a call is in flight; crew output is untrusted text and is recorded only as
drafts by the crew modules. Free (":free") models cost nothing, so no spend budget is needed;
any other model requires an owner-set QE_LLM_SPEND_BUDGET_USD > 0.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qe.core.schemas import ModelRef
from qe.exec.egress import exempt_hosts
from sandbox_apps._common.llm import LLMClient, OpenAICompatibleLLM

BASE_URL = "https://openrouter.ai/api/v1"
HOST = "openrouter.ai"
KEY_ENV = "OPENROUTER_API_KEY"
DEFAULT_MAX_CALLS = 120
RETRY_DELAYS = (3.0, 8.0)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


class RealLLMNotAllowedError(RuntimeError):
    pass


class CallBudget:
    """Hard cap on real-model calls for one scenario run (thread-safe)."""

    def __init__(self, max_calls: int) -> None:
        self.max_calls, self.used = max_calls, 0
        self._lock = threading.Lock()

    def use(self) -> None:
        with self._lock:
            if self.used >= self.max_calls:
                raise RealLLMNotAllowedError(f"real-model call cap reached ({self.max_calls})")
            self.used += 1


@dataclass(frozen=True)
class RealSettings:
    agent_model: str
    target_model: str
    max_calls: int


def real_settings_from_env(env: Mapping[str, str] | None = None) -> RealSettings:
    e = os.environ if env is None else env
    if e.get("QE_ALLOW_REAL_LLM") != "1":
        raise RealLLMNotAllowedError("set QE_ALLOW_REAL_LLM=1 to opt in to real models")
    if not e.get(KEY_ENV):
        raise RealLLMNotAllowedError(f"{KEY_ENV} is not set")
    agent, target = e.get("QE_AGENT_MODEL", ""), e.get("QE_TARGET_MODEL", "")
    if not agent or not target:
        raise RealLLMNotAllowedError("QE_AGENT_MODEL and QE_TARGET_MODEL must both be set")
    if not (agent.endswith(":free") and target.endswith(":free")):
        try:
            budget = float(e.get("QE_LLM_SPEND_BUDGET_USD", ""))
        except ValueError:
            budget = 0.0
        if not budget > 0:
            raise RealLLMNotAllowedError("non-free models need QE_LLM_SPEND_BUDGET_USD > 0")
    cap = e.get("QE_LLM_MAX_CALLS", "")
    max_calls = int(cap) if cap.isdigit() and int(cap) > 0 else DEFAULT_MAX_CALLS
    return RealSettings(agent, target, max_calls)


def _call(client: LLMClient, messages: list[dict[str, str]], budget: CallBudget) -> str:
    """One budgeted call with polite retries on rate limits / transient errors."""
    last: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        budget.use()
        try:
            with exempt_hosts(HOST):
                return client.complete(messages)
        except RuntimeError as exc:
            last = exc
            transient = any(
                c in str(exc) for c in ("429", "500", "502", "503", "504", "connection"))
            if not transient or attempt == len(RETRY_DELAYS):
                break
            time.sleep(RETRY_DELAYS[attempt])
    raise RuntimeError(f"real-model call failed: {last}") from None


class BudgetedTargetLLM:
    """LLMClient for the target sandbox app (qwen): every call is budgeted and egress-scoped."""

    def __init__(self, inner: LLMClient, budget: CallBudget) -> None:
        self._inner, self._budget = inner, budget
        self.model_name = str(getattr(inner, "model_name", "llm"))

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        return _call(self._inner, messages, self._budget)


def clean_json_text(raw: str) -> str:
    """Strip reasoning blocks and surrounding prose; keep the first balanced JSON array."""
    text = _THINK.sub("", raw)
    start = text.find("[")
    if start < 0:
        return text.strip()
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            in_str, esc = (ch != '"' or esc), (ch == "\\" and not esc)
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:].strip()


class RealCrewLLM:
    """CrewLLM backed by a real model, with a disk cache so generation can be replayed offline."""

    def __init__(self, client: LLMClient, model: str, family: str, budget: CallBudget,
                 cache_path: Path | None = None) -> None:
        self._client, self._budget, self._cache = client, budget, cache_path
        self._lock = threading.Lock()
        self.model = ModelRef(provider="openrouter", name=model, version="unpinned", family=family)

    def _key(self, system: str, user: str) -> str:
        return hashlib.sha256(json.dumps([self.model.name, system, user]).encode()).hexdigest()

    def _lookup(self, key: str) -> str | None:
        if self._cache is None or not self._cache.is_file():
            return None
        with self._lock:
            for line in self._cache.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec["key"] == key:
                    return str(rec["output"])
        return None

    async def complete(self, system: str, user: str) -> str:
        key = self._key(system, user)
        cached = self._lookup(key)
        if cached is not None:
            return cached
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        raw = await asyncio.to_thread(_call, self._client, messages, self._budget)
        out = clean_json_text(raw)
        if self._cache is not None:
            with self._lock, self._cache.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "model": self.model.name, "output": out}) + "\n")
        return out


@dataclass(frozen=True)
class RealRuntime:
    """Everything the pipeline needs to run against real models."""

    settings: RealSettings
    budget: CallBudget
    cache_path: Path

    def client(self, model: str, timeout: float = 90.0) -> LLMClient:
        return OpenAICompatibleLLM(BASE_URL, model, api_key_env=KEY_ENV, timeout=timeout)

    def crew(self, family: str) -> RealCrewLLM:
        return RealCrewLLM(self.client(self.settings.agent_model), self.settings.agent_model,
                           family, self.budget, self.cache_path)

    def target_llm(self) -> BudgetedTargetLLM:
        return BudgetedTargetLLM(self.client(self.settings.target_model), self.budget)


def runtime_from_env(runs_dir: Path, env: Mapping[str, str] | None = None) -> RealRuntime:
    settings = real_settings_from_env(env)
    return RealRuntime(settings, CallBudget(settings.max_calls), runs_dir / "llm_cache.jsonl")
