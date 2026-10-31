"""Exact binomial helpers shared by drift monitoring and paired comparisons (no SciPy)."""

from __future__ import annotations

import math


def _log_pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(k + 1)))


def binom_sf_ge(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), summed from the upper tail for accuracy."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(k, n + 1)))


def mcnemar_exact(b: int, c: int, alternative: str = "two-sided") -> float:
    """Exact McNemar on discordant counts: b = A-only successes, c = B-only successes.

    alternative: "two-sided", or "greater" (H1: B succeeds more, i.e. c > b).
    With no discordant pairs the p-value is 1.0 (no evidence either way).
    """
    n = b + c
    if n == 0:
        return 1.0
    if alternative == "greater":
        return binom_sf_ge(c, n, 0.5)
    if alternative != "two-sided":
        raise ValueError("alternative must be 'two-sided' or 'greater'")
    return min(1.0, 2.0 * binom_cdf(min(b, c), n, 0.5))


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in the input order."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    adjusted = [0.0] * len(pvalues)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (len(pvalues) - rank) * pvalues[idx]))
        adjusted[idx] = running
    return adjusted
