"""Risk register: LLM proposals are validated against a taxonomy; ranking is policy code (R2/R3)."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from qe.core.schemas import Policy
from qe.risk.taxonomy import Taxonomy


class RiskProposal(BaseModel):
    """A DRAFT risk (LLM output). Never evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    risk_id: str
    taxonomy_id: str
    component: str  # app-model node the risk attaches to
    rationale: str

    @field_validator("risk_id", "taxonomy_id", "component", "rationale")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must be non-empty")
        return v


class RankedRisk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    proposal: RiskProposal
    appetite: float | None  # None = policy has no appetite for this taxonomy id
    rank: int


def validate_proposals(
    proposals: Sequence[RiskProposal], taxonomy: Taxonomy
) -> tuple[tuple[RiskProposal, ...], tuple[tuple[RiskProposal, str], ...]]:
    ids = taxonomy.ids()
    ok: list[RiskProposal] = []
    bad: list[tuple[RiskProposal, str]] = []
    for p in proposals:
        if p.taxonomy_id in ids:
            ok.append(p)
        else:
            bad.append((p, f"taxonomy_id not in {taxonomy.taxonomy}"))
    return tuple(ok), tuple(bad)


def rank_risks(proposals: Sequence[RiskProposal], policy: Policy) -> tuple[RankedRisk, ...]:
    """Lower tolerated failure rate (policy risk_appetite[taxonomy_id]) = higher priority.

    Risks the policy is silent on rank last (never dropped). Order is independent of input order.
    """
    def key(p: RiskProposal) -> tuple[int, float, str, str]:
        a = policy.risk_appetite.get(p.taxonomy_id)
        if a is None:
            return (1, 0.0, p.taxonomy_id, p.risk_id)
        return (0, a, p.taxonomy_id, p.risk_id)

    ordered = sorted(proposals, key=key)
    return tuple(
        RankedRisk(proposal=p, appetite=policy.risk_appetite.get(p.taxonomy_id), rank=i)
        for i, p in enumerate(ordered)
    )
