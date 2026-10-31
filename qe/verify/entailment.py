"""Entailment verifier adapter (method class ENTAILMENT), no heavy dependencies.

The NLI model sits behind `NliBackend`. Shipped here: a deterministic lexical-overlap FAKE
(for tests and pipeline validation, NOT a real entailment method) and a stub that reports
"backend unavailable" until a real model backend is plugged in. The verdict is the argmax
over the backend's three probabilities, so no decision threshold is introduced here (R2).
Reference: research/09 (grounding states), research/benchmarks/evaluation_metrics.md.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from qe.core.schemas import ClaimState, MethodClass, ModelRef, Verdict
from qe.ports import VerifierInput

VERSION = "1"
_WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_NUM = re.compile(r"\d+(?:\.\d+)?")


class BackendUnavailableError(RuntimeError):
    """The NLI backend is not installed/configured."""


@runtime_checkable
class NliBackend(Protocol):
    def probabilities(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        """Return (P(entailment), P(contradiction), P(neutral))."""


class LexicalOverlapNli:
    """Deterministic FAKE backend. `min_coverage` is a test fixture, not a policy threshold.

    Contradiction if the hypothesis states a number absent from the premise; entailment if
    at least `min_coverage` of hypothesis words occur in the premise; otherwise neutral.
    """

    def __init__(self, min_coverage: float = 0.8) -> None:
        if not 0.0 < min_coverage <= 1.0:
            raise ValueError("min_coverage must be in (0, 1]")
        self.min_coverage = min_coverage

    def probabilities(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        p, h = premise.lower(), hypothesis.lower()
        if set(_NUM.findall(h)) - set(_NUM.findall(p)):
            return (0.0, 1.0, 0.0)
        words = _WORD.findall(h)
        if not words:
            return (0.0, 0.0, 1.0)
        prem = set(_WORD.findall(p))
        coverage = sum(w in prem for w in words) / len(words)
        return (1.0, 0.0, 0.0) if coverage >= self.min_coverage else (0.0, 0.0, 1.0)


class NliModelStub:
    """Placeholder for a real NLI model (e.g. a DeBERTa-MNLI class model); not implemented."""

    def probabilities(self, premise: str, hypothesis: str) -> tuple[float, float, float]:
        raise BackendUnavailableError("no NLI model backend is installed")


class EntailmentVerifier:
    method_class = MethodClass.ENTAILMENT
    model: ModelRef | None = None

    def __init__(self, backend: NliBackend, name: str = "entailment") -> None:
        self.backend = backend
        self.name = name
        self.version = VERSION

    def _verdict(self, item: VerifierInput, state: ClaimState, **kw: object) -> Verdict:
        return Verdict(claim_id=item.claim.claim_id, method=self.name,
                       method_class=self.method_class, method_version=self.version,
                       state=state, **kw)  # type: ignore[arg-type]

    async def verify(self, item: VerifierInput) -> Verdict:
        if item.evidence_text is None:
            return self._verdict(item, ClaimState.SOURCE_UNAVAILABLE)
        try:
            ent, con, neu = self.backend.probabilities(item.evidence_text, item.claim.text)
        except BackendUnavailableError as exc:
            return self._verdict(item, ClaimState.ABSTAIN, detail=str(exc))
        best = max(ent, con, neu)
        if best == ent:
            state = ClaimState.SUPPORTED
        elif best == con:
            state = ClaimState.CONTRADICTED
        else:
            state = ClaimState.UNSUPPORTED
        return self._verdict(item, state, score=best)
