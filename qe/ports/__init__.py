"""Ports (hexagonal boundaries). Third-party libraries and LLMs sit behind these."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from qe.core.schemas import (
    Claim,
    EvidenceRef,
    MethodClass,
    ModelRef,
    Span,
    TestCase,
    Verdict,
    VisibilityLevel,
)


class TargetRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    input: str
    session_id: str | None = None
    user: str | None = None
    want_trace: bool = False
    seed: int = 0


class TargetResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    output: str
    citations: tuple[str, ...] = ()
    spans: tuple[Span, ...] = ()
    meta: dict[str, Any] = {}
    error: str | None = None


@runtime_checkable
class TargetPort(Protocol):
    """System under test (inspired by openai/evals CompletionFn; re-implemented)."""

    visibility_level: VisibilityLevel

    async def invoke(self, request: TargetRequest) -> TargetResponse: ...


@runtime_checkable
class TracePort(Protocol):
    async def spans_for(self, trace_id: str) -> tuple[Span, ...]: ...


class GenerationSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_ids: tuple[str, ...]
    n: int
    seed: int = 0


@runtime_checkable
class GeneratorPort(Protocol):
    """Produces DRAFT test cases only; validity is decided elsewhere."""

    async def generate(self, spec: GenerationSpec) -> tuple[TestCase, ...]: ...


class VerifierInput(BaseModel):
    """The ONLY thing a verifier may see (R4): a claim and an evidence pointer + content.

    `extra="forbid"` means producer rationale or another verifier's verdict cannot be
    smuggled in as a field. Text fields are untrusted data (R3).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    claim: Claim
    evidence_ref: EvidenceRef
    evidence_text: str | None  # None = source unavailable

    @field_validator("claim", "evidence_ref")
    @classmethod
    def _exact_types_only(cls, v: Claim | EvidenceRef) -> Claim | EvidenceRef:
        # Subclasses could carry extra fields (covert channel for producer rationale).
        if type(v) not in (Claim, EvidenceRef):
            raise ValueError(f"{type(v).__name__} is not allowed; pass the exact base type")
        return v


@runtime_checkable
class VerifierPort(Protocol):
    name: str
    version: str
    method_class: MethodClass
    model: ModelRef | None  # None for non-model verifiers

    async def verify(self, item: VerifierInput) -> Verdict: ...


@runtime_checkable
class JudgePort(VerifierPort, Protocol):
    """A model-based verifier; must declare its model family (for independence audits)."""

    model: ModelRef


class SandboxLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_calls: int = Field(ge=0)
    max_tokens: int = Field(ge=0)
    egress_allowlist: tuple[str, ...] = ()


class BudgetExceededError(Exception):
    pass


class KillSwitchError(Exception):
    pass


@runtime_checkable
class SandboxSession(Protocol):
    def charge(self, calls: int = 1, tokens: int = 0) -> None:
        """Raise BudgetExceededError / KillSwitchError instead of overrunning."""

    def kill(self) -> None: ...

    def egress_attempts(self) -> tuple[str, ...]: ...


@runtime_checkable
class SandboxPort(Protocol):
    def session(self, limits: SandboxLimits) -> AbstractAsyncContextManager[SandboxSession]: ...


__all__ = [
    "BudgetExceededError",
    "GenerationSpec",
    "GeneratorPort",
    "JudgePort",
    "KillSwitchError",
    "SandboxLimits",
    "SandboxPort",
    "SandboxSession",
    "TargetPort",
    "TargetRequest",
    "TargetResponse",
    "TracePort",
    "VerifierInput",
    "VerifierPort",
]
