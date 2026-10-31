"""Bayesian beta-binomial credible interval (research/benchmarks/evaluation_metrics.md,
"Interval methods": Bayesian beta for proportions).

Posterior for k successes in n trials under Beta(a0, b0) is Beta(a0 + k, b0 + n - k); the
interval is equal-tailed. The default prior is Jeffreys Beta(0.5, 0.5); it is a modelling choice
and is recorded by the caller, not a decision threshold.
"""

from __future__ import annotations

from qe.stats.special import beta_ppf

JEFFREYS: tuple[float, float] = (0.5, 0.5)


def beta_credible(
    k: int, n: int, confidence: float = 0.95, prior: tuple[float, float] = JEFFREYS
) -> tuple[float, float]:
    if n <= 0 or k < 0 or k > n:
        raise ValueError("need n >= 1 and 0 <= k <= n")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    a0, b0 = prior
    if a0 <= 0.0 or b0 <= 0.0:
        raise ValueError("prior parameters must be > 0")
    alpha = 1.0 - confidence
    a, b = a0 + k, b0 + n - k
    return beta_ppf(a, b, alpha / 2), beta_ppf(a, b, 1.0 - alpha / 2)
