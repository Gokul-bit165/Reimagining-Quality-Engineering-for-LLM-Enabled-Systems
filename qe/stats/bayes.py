"""Bayesian beta-binomial inference for failure rates.

Definitions: research/benchmarks/evaluation_metrics.md, "Interval methods" (Bayesian beta for
proportions) and "Decision quality". The prior is an explicit argument (default Jeffreys
Beta(0.5, 0.5)); it is a modelling choice, not a policy threshold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

JEFFREYS = (0.5, 0.5)
_GRID = 4000  # midpoint-rule resolution for the P(p_new < p_old - delta) integral
_TINY = 1e-300


def _safe(x: float) -> float:
    return x if abs(x) > _TINY else _TINY


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 / _safe(1.0 - qab * x / qap)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 / _safe(1.0 + aa * d)
        c = _safe(1.0 + aa / c)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 / _safe(1.0 + aa * d)
        c = _safe(1.0 + aa / c)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta I_x(a, b) = P(Beta(a, b) <= x)."""
    if a <= 0 or b <= 0:
        raise ValueError("beta parameters must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def beta_ppf(q: float, a: float, b: float) -> float:
    """Quantile of Beta(a, b) by bisection."""
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class BetaPosterior:
    a: float
    b: float

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b)

    def cdf(self, x: float) -> float:
        return beta_cdf(x, self.a, self.b)

    def interval(self, confidence: float = 0.95) -> tuple[float, float]:
        """Equal-tailed credible interval."""
        if not 0.0 < confidence < 1.0:
            raise ValueError("confidence must be in (0, 1)")
        tail = (1.0 - confidence) / 2
        return beta_ppf(tail, self.a, self.b), beta_ppf(1.0 - tail, self.a, self.b)


def posterior(
    failures: int, trials: int, prior: tuple[float, float] = JEFFREYS
) -> BetaPosterior:
    if trials < 0 or failures < 0 or failures > trials:
        raise ValueError("need 0 <= failures <= trials")
    return BetaPosterior(prior[0] + failures, prior[1] + trials - failures)


def prob_improvement(old: BetaPosterior, new: BetaPosterior, delta: float) -> float:
    """P(p_new < p_old - delta) under independent posteriors.

    `delta` is the minimum improvement the POLICY cares about (never defaulted here).
    Computed as E_{p_old}[ F_new(p_old - delta) ] by a midpoint rule over p_old's density,
    so it is deterministic (no sampling).
    """
    if delta < 0.0:
        raise ValueError("delta must be >= 0")
    total = 0.0
    for i in range(_GRID):
        x = (i + 0.5) / _GRID
        dens = math.exp(
            math.lgamma(old.a + old.b) - math.lgamma(old.a) - math.lgamma(old.b)
            + (old.a - 1) * math.log(x) + (old.b - 1) * math.log1p(-x)
        )
        total += dens * new.cdf(x - delta)
    return min(1.0, max(0.0, total / _GRID))
