"""Expected-loss decision path (ADDITIONAL to the appetite path in qe.policy.engine).

Model (every number comes from the Policy, R2):
  * World states per release: "acceptable" (every required metric's true failure rate is
    within its risk_appetite) or "unacceptable" (at least one exceeds it).
  * Posterior of each metric's failure rate: Beta(prior + failures, prior + successes)
    (Jeffreys prior unless a prior is passed; see qe.stats.bayes).
  * Metrics are treated as independent: P(acceptable) = prod_m P(p_m <= appetite_m).
    This is an assumption, stated in the decision notes.
  * loss_matrix[decision][world] gives the loss; the chosen decision minimises expected loss.
    Ties resolve conservatively (INSUFFICIENT_EVIDENCE > REJECT > CONDITIONAL > RELEASE).
  * Sensitivity: the "unacceptable" column is multiplied by each scale s in `scales`; the
    decision is `stable` if it does not change over the grid.
CONDITIONAL is a candidate only if the policy declares conditional_rules; its conditions are
those rule texts. This path never replaces the appetite path; callers report both.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.core.schemas import DecisionRecord, DecisionState, Policy
from qe.policy.engine import MetricEvidence
from qe.stats.bayes import JEFFREYS, posterior

WORLD_OK = "acceptable"
WORLD_BAD = "unacceptable"
DEFAULT_SCALES = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0)
_TIE_ORDER = (
    DecisionState.INSUFFICIENT_EVIDENCE,
    DecisionState.REJECT,
    DecisionState.CONDITIONAL,
    DecisionState.RELEASE,
)


class SensitivityRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    scale: float
    decision: DecisionState
    expected_loss: dict[str, float]


class ExpectedLossResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    p_unacceptable: float
    expected_loss: dict[str, float]
    sensitivity: tuple[SensitivityRow, ...]
    stable: bool


def _candidates(policy: Policy) -> dict[DecisionState, dict[str, float]]:
    out: dict[DecisionState, dict[str, float]] = {}
    for name, row in policy.loss_matrix.items():
        try:
            state = DecisionState(name)
        except ValueError as exc:
            raise ValueError(f"loss_matrix has unknown decision {name!r}") from exc
        if WORLD_OK not in row or WORLD_BAD not in row:
            raise ValueError(f"loss_matrix[{name}] needs '{WORLD_OK}' and '{WORLD_BAD}'")
        if any(v < 0 for v in row.values()):
            raise ValueError("losses must be non-negative")
        out[state] = row
    for needed in (DecisionState.RELEASE, DecisionState.REJECT):
        if needed not in out:
            raise ValueError(f"loss_matrix must define {needed.value}")
    if not policy.conditional_rules:
        out.pop(DecisionState.CONDITIONAL, None)
    return out


def _losses(
    cands: dict[DecisionState, dict[str, float]], p_bad: float, scale: float
) -> dict[DecisionState, float]:
    return {
        d: row[WORLD_OK] * (1.0 - p_bad) + row[WORLD_BAD] * scale * p_bad
        for d, row in cands.items()
    }


def _argmin(losses: dict[DecisionState, float]) -> DecisionState:
    best = min(losses.values())
    return next(d for d in _TIE_ORDER if d in losses and losses[d] == best)


def p_unacceptable(
    policy: Policy, metrics: Sequence[MetricEvidence], prior: tuple[float, float] = JEFFREYS
) -> float | None:
    """P(at least one required metric exceeds appetite); None if evidence is missing."""
    by_name = {m.name: m for m in metrics}
    p_ok = 1.0
    for name in policy.required_evidence:
        m = by_name.get(name)
        if m is None:
            return None
        p_ok *= posterior(m.failures, m.trials, prior).cdf(policy.risk_appetite[name])
    return 1.0 - p_ok


def decide_expected_loss(
    policy: Policy,
    metrics: Sequence[MetricEvidence],
    *,
    scales: Sequence[float] = DEFAULT_SCALES,
    prior: tuple[float, float] = JEFFREYS,
) -> tuple[DecisionRecord, ExpectedLossResult | None]:
    cands = _candidates(policy)
    version = f"{policy.policy_id}@{policy.version}"
    p_bad = p_unacceptable(policy, metrics, prior)
    used = tuple(sorted({e for m in metrics for e in m.evidence_ids}))
    if p_bad is None:
        missing = [n for n in policy.required_evidence if n not in {m.name for m in metrics}]
        note = f"missing evidence: {', '.join(missing)}"
        return DecisionRecord(decision=DecisionState.INSUFFICIENT_EVIDENCE, policy_version=version,
                              evidence_ids=used, conditions=(note,)), None
    if any(s <= 0 for s in scales) or 1.0 not in scales:
        raise ValueError("scales must be positive and include 1.0")
    base = _losses(cands, p_bad, 1.0)
    rows = tuple(
        SensitivityRow(scale=s, decision=_argmin(_losses(cands, p_bad, s)),
                       expected_loss={d.value: v for d, v in _losses(cands, p_bad, s).items()})
        for s in scales
    )
    decision = _argmin(base)
    if not used and decision is not DecisionState.INSUFFICIENT_EVIDENCE:
        decision = DecisionState.INSUFFICIENT_EVIDENCE  # a decision must cite evidence
    result = ExpectedLossResult(
        p_unacceptable=p_bad, expected_loss={d.value: v for d, v in base.items()},
        sensitivity=rows, stable=len({r.decision for r in rows}) == 1)
    notes = [
        "expected-loss path (metrics assumed independent)",
        f"P(unacceptable)={p_bad:.4f}",
        *(f"E[loss|{d}]={v:.4f}" for d, v in result.expected_loss.items()),
        f"sensitivity over loss scale: {'stable' if result.stable else 'UNSTABLE'} "
        + ", ".join(f"x{r.scale:g}->{r.decision.value}" for r in rows),
    ]
    if policy.example_only:
        notes.insert(0, "EXAMPLE policy: not a real loss matrix")
    if decision is DecisionState.CONDITIONAL:
        notes.extend(f"CONDITION: {r.condition}" for r in policy.conditional_rules)
    return DecisionRecord(decision=decision, policy_version=version, evidence_ids=used,
                          conditions=tuple(notes)), result
