"""LocalSandbox: SandboxPort with budgets, kill switch and in-process egress guard."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from qe.exec.egress import EgressGuard
from qe.ports import BudgetExceededError, KillSwitchError, SandboxLimits, SandboxSession


class _Session:
    def __init__(self, limits: SandboxLimits, guard: EgressGuard) -> None:
        self._limits = limits
        self._guard = guard
        self._calls = 0
        self._tokens = 0
        self._killed = False

    def charge(self, calls: int = 1, tokens: int = 0) -> None:
        if calls < 0 or tokens < 0:
            raise ValueError("charges must be non-negative")
        if self._killed:
            raise KillSwitchError("kill switch engaged")
        if self._calls + calls > self._limits.max_calls:
            raise BudgetExceededError("call budget would be exceeded")
        if self._tokens + tokens > self._limits.max_tokens:
            raise BudgetExceededError("token budget would be exceeded")
        self._calls += calls
        self._tokens += tokens

    def kill(self) -> None:
        self._killed = True

    def egress_attempts(self) -> tuple[str, ...]:
        return tuple(self._guard.attempts)


class LocalSandbox:
    @asynccontextmanager
    async def session(self, limits: SandboxLimits) -> AsyncIterator[SandboxSession]:
        with EgressGuard(limits.egress_allowlist) as guard:
            yield _Session(limits, guard)
