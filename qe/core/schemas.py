"""Core domain schemas (Pydantic v2, frozen). Reference: research/24 §7, research/09.

IDs are content-addressed (see qe.core.ids). Schemas are provisional until the M0 gate.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qe.core.ids import content_id


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    def cid(self) -> str:
        return content_id(self.model_dump(mode="json"))


class VisibilityLevel(StrEnum):
    """Access level, research/14: A black-box, B SDK, C OTel traces, D repo, E gateway."""

    A_BLACKBOX = "A"
    B_SDK = "B"
    C_OTEL = "C"
    D_REPO = "D"
    E_GATEWAY = "E"


class ClaimState(StrEnum):
    """Six grounding states (research/09), plus an explicit no-verdict state."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    UNVERIFIABLE = "unverifiable"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ABSTAIN = "abstain"


class DecisionState(StrEnum):
    RELEASE = "RELEASE"
    CONDITIONAL = "CONDITIONAL"
    REJECT = "REJECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MethodClass(StrEnum):
    DETERMINISTIC = "deterministic"
    ENTAILMENT = "entailment"
    METRIC_LIBRARY = "metric_library"
    LLM_JUDGE = "llm_judge"
    DECISION_MODEL = "decision_model"
    OUTCOME_ORACLE = "outcome_oracle"


class Target(Frozen):
    name: str
    base_url: str | None = None
    description: str = ""


class AccessProfile(Frozen):
    target: str
    visibility_level: VisibilityLevel
    capabilities: tuple[str, ...] = ()


class ModelRef(Frozen):
    provider: str
    name: str
    version: str = "unpinned"
    family: str


class TestCase(Frozen):
    __test__ = False  # not a pytest class

    id: str
    risk_cell: str | None = None
    input: dict[str, Any]
    oracle_source: str  # e.g. "source_of_truth:doc-12" | "deterministic:schema" | "none"
    lineage: tuple[str, ...] = ()  # parent ids / generator ids
    validity: str = "unreviewed"  # unreviewed | valid | invalid | ambiguous


class Span(Frozen):
    span_id: str
    kind: str  # retrieval | tool_call | llm_call | handoff | memory_read | memory_write | other
    attributes: dict[str, Any] = Field(default_factory=dict)


class RunRecord(Frozen):
    test_case_id: str
    repeat_index: int
    seed: int
    visibility_level: VisibilityLevel
    request: dict[str, Any]
    response: dict[str, Any]
    spans: tuple[Span, ...] = ()
    versions: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class EvidenceRef(Frozen):
    """Pointer to evidence; verifiers resolve it, they never receive a producer rationale."""

    source_id: str
    source_version: str | None = None
    start: int | None = None
    end: int | None = None


class Claim(Frozen):
    claim_id: str
    text: str
    run_id: str | None = None


class Verdict(Frozen):
    claim_id: str
    method: str
    method_class: MethodClass
    method_version: str
    model_family: str | None = None
    state: ClaimState
    score: float | None = Field(default=None, allow_inf_nan=False)
    calibration_id: str | None = None
    detail: str | None = None


class AdjudicatedVerdict(Frozen):
    claim_id: str
    state: ClaimState
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    n_eff: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    layers_fired: tuple[str, ...] = ()
    verdict_ids: tuple[str, ...] = ()


class FailureRecord(Frozen):
    failure_id: str
    failure_type: str
    location: str  # "unknown" is a valid location
    localization_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    visibility_level: VisibilityLevel
    evidence_ids: tuple[str, ...] = ()


class RegressionCase(Frozen):
    case_id: str
    minimized_from: str
    pass_k_admission: tuple[int, int]  # (successes, trials)

    @model_validator(mode="after")
    def _successes_within_trials(self) -> Self:
        successes, trials = self.pass_k_admission
        if not 0 <= successes <= trials or trials < 1:
            raise ValueError("pass_k_admission must satisfy 0 <= successes <= trials, trials >= 1")
        return self


class Policy(Frozen):
    """User-supplied decision policy (R2). Nothing here has built-in defaults that decide."""

    policy_id: str
    version: str
    loss_matrix: dict[str, dict[str, float]]  # decision -> world-state -> loss
    required_evidence: tuple[str, ...]
    risk_appetite: dict[str, float]
    example_only: bool = False  # EXAMPLE policies must say so


class DecisionRecord(Frozen):
    decision: DecisionState
    policy_version: str
    evidence_ids: tuple[str, ...]
    conditions: tuple[str, ...] = ()
    uncovered_risks: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _decision_consistency(self) -> Self:
        if any(not e for e in self.evidence_ids):
            raise ValueError("evidence ids must be non-empty strings")
        needs_evidence = self.decision is not DecisionState.INSUFFICIENT_EVIDENCE
        if needs_evidence and not self.evidence_ids:
            raise ValueError(f"{self.decision.value} requires at least one evidence id")
        if self.decision is DecisionState.CONDITIONAL and not self.conditions:
            raise ValueError("CONDITIONAL requires at least one condition")
        return self


class Signoff(Frozen):
    decision_id: str
    approver: str
    approved: bool
    note: str = ""
