"""Crew LLM interface. Output is untrusted text (R3); every call carries a ModelRef (family)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from qe.core.schemas import ModelRef


@runtime_checkable
class CrewLLM(Protocol):
    model: ModelRef

    async def complete(self, system: str, user: str) -> str: ...


class ScriptedLLM:
    """Deterministic test double: replies from a list (cycled) or a function of (system, user)."""

    def __init__(
        self, model: ModelRef, replies: Sequence[str] | Callable[[str, str], str]
    ) -> None:
        self.model = model
        self._replies = replies
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if callable(self._replies):
            return self._replies(system, user)
        return self._replies[(len(self.calls) - 1) % len(self._replies)]
