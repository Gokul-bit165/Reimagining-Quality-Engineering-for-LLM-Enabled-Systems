"""Rate estimators with intervals and pass^k (tau-bench definition, research/11)."""

from __future__ import annotations

from collections.abc import Sequence
from math import comb

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


def pass_hat_k_at(outcomes: Sequence[Sequence[bool]], k: int) -> float:
    """tau-bench pass^k for any k <= trials: mean over items of C(c, k) / C(n, k).

    c = passes among the item's n trials; equals the fraction of k-subsets of trials that all
    pass. At k == n it reduces to `pass_hat_k`; at k == 1 it is the mean per-item pass rate.
    Definition: evaluation_metrics.md, "Reliability".
    """
    if not outcomes or any(len(t) == 0 for t in outcomes):
        raise ValueError("need at least one item and one trial per item")
    n = len(outcomes[0])
    if any(len(t) != n for t in outcomes):
        raise ValueError("all items need the same number of trials")
    if not 1 <= k <= n:
        raise ValueError("need 1 <= k <= trials per item")
    return sum(comb(sum(t), k) / comb(n, k) for t in outcomes) / len(outcomes)


def pass_hat_k_estimate(
    outcomes: Sequence[Sequence[bool]], confidence: float = 0.95
) -> RateEstimate:
    """pass^k at k == trials as a rate over items (each item is one Bernoulli), with exact CP."""
    p = pass_hat_k(outcomes)
    return rate_estimate(round(p * len(outcomes)), len(outcomes), confidence)
