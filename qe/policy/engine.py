"""Policy engine. All thresholds come from the user-supplied Policy (R2).

Per required metric m, with appetite a_m = max tolerated failure rate (from the policy):
  upper_m <= a_m   -> acceptable
  lower_m >  a_m   -> violated (any violated metric -> REJECT)
  otherwise/missing -> undetermined (-> INSUFFICIENT_EVIDENCE)
RELEASE only if every required metric is acceptable. CONDITIONAL is not produced in M1
(needs policy-defined conditions). `loss_matrix` is carried but not yet used (stated limit).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.core.schemas import DecisionRecord, DecisionState, Policy


class MetricEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    failures: int
    trials: int
    lower: float
    upper: float
    evidence_ids: tuple[str, ...] = ()


def decide(policy: Policy, metrics: Sequence[MetricEvidence]) -> DecisionRecord:
    no_appetite = [m for m in policy.required_evidence if m not in policy.risk_appetite]
    if no_appetite:
        raise ValueError(f"policy lacks risk_appetite for: {no_appetite}")
    by_name = {m.name: m for m in metrics}
    notes: list[str] = []
    if policy.example_only:
        notes.append("EXAMPLE policy: not a real risk appetite")
    violated: list[str] = []
    undetermined: list[str] = []
    for name in policy.required_evidence:
        m = by_name.get(name)
        appetite = policy.risk_appetite[name]
        if m is None:
            undetermined.append(name)
            notes.append(f"missing evidence: {name}")
        elif m.lower > appetite:
            violated.append(name)
            notes.append(f"{name}: lower bound {m.lower:.4f} > appetite {appetite}")
        elif m.upper > appetite:
            undetermined.append(name)
            notes.append(
                f"{name}: interval [{m.lower:.4f}, {m.upper:.4f}] straddles appetite {appetite}"
            )
    used = tuple(sorted({e for m in metrics for e in m.evidence_ids}))
    if violated:
        state = DecisionState.REJECT
    elif undetermined:
        state = DecisionState.INSUFFICIENT_EVIDENCE
    else:
        state = DecisionState.RELEASE
    return DecisionRecord(decision=state, policy_version=f"{policy.policy_id}@{policy.version}",
                          evidence_ids=used, conditions=tuple(notes))
