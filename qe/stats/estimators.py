"""Rate estimators with intervals and pass^k (tau-bench definition, research/11)."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.stats.intervals import clopper_pearson


class RateEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)
    k: int
    n: int
    point: float
    lower: float
    upper: float
    confidence: float
    method: str = "clopper_pearson"


def rate_estimate(k: int, n: int, confidence: float = 0.95) -> RateEstimate:
    lower, upper = clopper_pearson(k, n, confidence)
    return RateEstimate(k=k, n=n, point=k / n, lower=lower, upper=upper, confidence=confidence)


def pass_hat_k(outcomes: Sequence[Sequence[bool]]) -> float:
    """Fraction of items whose trials ALL passed (items x trials of booleans)."""
    if not outcomes or any(len(t) == 0 for t in outcomes):
        raise ValueError("need at least one item and one trial per item")
    return sum(all(t) for t in outcomes) / len(outcomes)
