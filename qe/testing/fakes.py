"""Deterministic fake implementations of every port, for tests and offline runs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from qe.core.ids import content_id
from qe.core.schemas import (
    ClaimState,
    MethodClass,
    ModelRef,
    Span,
    TestCase,
    Verdict,
    VisibilityLevel,
)
from qe.ports import (
    BudgetExceededError,
    GenerationSpec,
    KillSwitchError,
    SandboxLimits,
    SandboxSession,
    TargetRequest,
    TargetResponse,
    VerifierInput,
)


class FakeTarget:
    visibility_level = VisibilityLevel.A_BLACKBOX

    async def invoke(self, request: TargetRequest) -> TargetResponse:
        spans = (Span(span_id="s0", kind="llm_call"),) if request.want_trace else ()
        return TargetResponse(output=f"echo:{request.input}", spans=spans)


class FakeTrace:
    async def spans_for(self, trace_id: str) -> tuple[Span, ...]:
        return (Span(span_id=f"{trace_id}:0", kind="llm_call"),)


class FakeGenerator:
    async def generate(self, spec: GenerationSpec) -> tuple[TestCase, ...]:
        return tuple(
            TestCase(
                id=content_id({"src": spec.source_ids, "i": i, "seed": spec.seed}),
                input={"q": f"question {i}"},
                oracle_source=(
                    f"source_of_truth:{spec.source_ids[0]}" if spec.source_ids else "none"
                ),
            )
            for i in range(spec.n)
        )


class FakeSubstringVerifier:
    """Deterministic verifier: claim supported iff claim text occurs in the evidence."""

    name = "fake-substring"
    version = "1"
    method_class = MethodClass.DETERMINISTIC
    model: ModelRef | None = None

    async def verify(self, item: VerifierInput) -> Verdict:
        if item.evidence_text is None:
            state = ClaimState.SOURCE_UNAVAILABLE
        elif item.claim.text in item.evidence_text:
            state = ClaimState.SUPPORTED
        else:
            state = ClaimState.UNSUPPORTED
        return Verdict(
            claim_id=item.claim.claim_id,
            method=self.name,
            method_class=self.method_class,
            method_version=self.version,
            state=state,
        )


class FakeJudge:
    name = "fake-judge"
    version = "1"
    method_class = MethodClass.LLM_JUDGE
    model = ModelRef(provider="fake", name="fake-judge", family="fake-family-b")

    async def verify(self, item: VerifierInput) -> Verdict:
        return Verdict(
            claim_id=item.claim.claim_id,
            method=self.name,
            method_class=self.method_class,
            method_version=self.version,
            model_family=self.model.family,
            state=ClaimState.ABSTAIN,
        )


class _Session:
    def __init__(self, limits: SandboxLimits) -> None:
        self._limits = limits
        self._calls = 0
        self._tokens = 0
        self._killed = False

    def charge(self, calls: int = 1, tokens: int = 0) -> None:
        if calls < 0 or tokens < 0:
            raise ValueError("charges must be non-negative")
        if self._killed:
            raise KillSwitchError("kill switch engaged")
        if self._calls + calls > self._limits.max_calls or (
            self._tokens + tokens > self._limits.max_tokens
        ):
            raise BudgetExceededError("budget would be exceeded")
        self._calls += calls
        self._tokens += tokens

    def kill(self) -> None:
        self._killed = True

    def egress_attempts(self) -> tuple[str, ...]:
        return ()


class FakeSandbox:
    @asynccontextmanager
    async def session(self, limits: SandboxLimits) -> AsyncIterator[SandboxSession]:
        yield _Session(limits)
