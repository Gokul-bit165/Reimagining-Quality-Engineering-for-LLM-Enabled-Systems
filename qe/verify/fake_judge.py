"""Deterministic judge fakes (default for every test; no network, no model)."""

from __future__ import annotations

from collections.abc import Callable

from qe.core.schemas import ClaimState, MethodClass, ModelRef, Verdict
from qe.ports import VerifierInput
from qe.verify.entailment import LexicalOverlapNli


def _lexical_answer(item: VerifierInput) -> ClaimState:
    ent, con, _ = LexicalOverlapNli().probabilities(item.evidence_text or "", item.claim.text)
    return ClaimState.SUPPORTED if ent else (
        ClaimState.CONTRADICTED if con else ClaimState.UNSUPPORTED)


class FakeJudge:
    """A judge of a declared model family whose answer is a pure function of the input."""

    method_class = MethodClass.LLM_JUDGE
    version = "fake-1"

    def __init__(
        self, name: str = "fake-judge", family: str = "fake-family-b",
        answer: Callable[[VerifierInput], ClaimState] = _lexical_answer,
    ) -> None:
        self.name = name
        self.model = ModelRef(provider="fake", name=name, family=family)
        self._answer = answer

    async def verify(self, item: VerifierInput) -> Verdict:
        state = (ClaimState.SOURCE_UNAVAILABLE if item.evidence_text is None
                 else self._answer(item))
        return Verdict(claim_id=item.claim.claim_id, method=self.name,
                       method_class=self.method_class, method_version=self.version,
                       model_family=self.model.family, state=state)
