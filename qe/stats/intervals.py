"""Exact binomial intervals (rates: research/benchmarks/evaluation_metrics.md)."""

from __future__ import annotations

import math
from collections.abc import Callable


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (
        math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
        + k * math.log(p) + (n - k) * math.log1p(-p)
    )


def _cdf(k: int, n: int, p: float) -> float:
    """P(X <= k), X ~ Binomial(n, p)."""
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(k + 1)))


def _bisect(f: Callable[[float], float], target: float, increasing: bool) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if (f(mid) > target) == increasing:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided exact (Clopper-Pearson) interval for k successes in n trials."""
    if n <= 0 or k < 0 or k > n:
        raise ValueError("need n >= 1 and 0 <= k <= n")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else _bisect(lambda p: 1.0 - _cdf(k - 1, n, p), alpha / 2, True)
    upper = 1.0 if k == n else _bisect(lambda p: _cdf(k, n, p), alpha / 2, False)
    return lower, upper
