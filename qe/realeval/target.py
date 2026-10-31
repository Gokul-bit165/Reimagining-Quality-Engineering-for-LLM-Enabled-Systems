"""The abstract system under test: any RAG app that can answer a question.

Agent A's `SandboxedRepoTarget` implements `RagTarget`; tests use `FakeRagTarget`/`CallableTarget`.
`ask` must never raise for app-level failures: it returns a `TargetAnswer` with `error` set.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class TargetAnswer(BaseModel):
    answer: str = ""
    contexts: list[str] = []
    latency_s: float = 0.0
    error: str | None = None


@runtime_checkable
class RagTarget(Protocol):
    def ask(self, question: str) -> TargetAnswer: ...


class CallableTarget:
    """Adapts `fn(question) -> (answer, contexts)` to a RagTarget; times it and traps errors."""

    def __init__(self, fn: Callable[[str], tuple[str, list[str]]]) -> None:
        self._fn = fn

    def ask(self, question: str) -> TargetAnswer:
        start = time.perf_counter()
        try:
            answer, contexts = self._fn(question)
        except Exception as exc:  # noqa: BLE001 - app failure is data, not a crash
            return TargetAnswer(latency_s=time.perf_counter() - start,
                                error=f"{type(exc).__name__}: {exc}")
        return TargetAnswer(answer=answer, contexts=list(contexts),
                            latency_s=time.perf_counter() - start)


# Aspects the test corpora never document; the fake refuses these even when an entity matches,
# standing in for a grounded app that does not answer beyond its documents.
UNDOCUMENTED_ASPECTS = ("annual revenue", "founding date", "head office address", "refund policy")


class FakeRagTarget:
    """Deterministic in-memory RAG over a list of document texts, for tests.

    mode: perfect (answers with the best-matching sentence, grounded), hallucinating (asserts
    invented figures, ignores context), injectable (obeys 'reply with X and Y' instructions),
    flaky (every `flaky_every`-th call raises/ errors and odd calls answer wrongly).
    """

    def __init__(self, documents: list[str], mode: str = "perfect", flaky_every: int = 2) -> None:
        self.documents, self.mode, self.flaky_every = documents, mode, flaky_every
        self.calls = 0

    def _retrieve(self, question: str) -> list[str]:
        words = {w for w in question.lower().replace("?", "").split() if len(w) > 3}
        sents = [s.strip() for d in self.documents for s in d.split(".") if s.strip()]
        ranked = sorted(sents, key=lambda s: -len(words & set(s.lower().split())))
        return [s + "." for s in ranked[:2] if words & set(s.lower().split())]

    def ask(self, question: str) -> TargetAnswer:
        self.calls += 1
        if self.mode == "flaky" and self.calls % self.flaky_every == 0:
            return TargetAnswer(error="TimeoutError: upstream model timed out", latency_s=0.01)
        ctx = self._retrieve(question)
        low = question.lower()
        if self.mode == "injectable" and ("concatenat" in low or "joined together" in low):
            q = question.split("'")
            return TargetAnswer(answer=q[1] + q[3], contexts=ctx, latency_s=0.01)
        if self.mode == "injectable" and "pay.evil.example" in low:
            return TargetAnswer(
                answer="Please complete your payment at http://pay.evil.example/verify.",
                contexts=ctx, latency_s=0.01)
        if self.mode == "hallucinating":
            return TargetAnswer(answer="The figure is 987654 according to our records.",
                                contexts=ctx, latency_s=0.02)
        if not ctx or any(a in low for a in UNDOCUMENTED_ASPECTS):
            return TargetAnswer(answer="I do not know based on the provided documents.",
                                contexts=[], latency_s=0.01)
        return TargetAnswer(answer=ctx[0], contexts=ctx, latency_s=0.01)
