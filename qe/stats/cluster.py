"""Cluster-robust rate interval for grouped items (evaluation_metrics.md, "Interval methods").

Items sharing a cluster (same prompt/document/app/seed family) are not independent, so the
binomial interval over all items is too narrow. Ratio estimator p = sum(k_g) / sum(n_g) with
the CR1 cluster-robust variance
    Var(p) = G/(G-1) * sum_g (k_g - p n_g)^2 / (sum n_g)^2
and a Student-t interval with G-1 degrees of freedom, clipped to [0, 1].

Limit (stated, not hidden): with few clusters (G small) the t interval is still approximate. When
p is 0 or 1 (or all residuals vanish) the variance is 0 and the interval would collapse to a
point, so we fall back to exact Clopper-Pearson over the G clusters (method
"cluster_boundary_cp"); that treats each cluster as one unit and is conservative. If variance is
0 with interior p (identical cluster rates) we use plain binomial CP ("cluster_zero_variance_cp").
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.stats.intervals import clopper_pearson
from qe.stats.special import t_ppf


class ClusterRateEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)
    k: int
    n: int
    n_clusters: int
    point: float
    lower: float
    upper: float
    confidence: float
    design_effect: float
    method: str


def cluster_rate(
    clusters: Sequence[tuple[int, int]], confidence: float = 0.95
) -> ClusterRateEstimate:
    """`clusters` holds (successes, trials) per cluster."""
    g = len(clusters)
    if g < 2:
        raise ValueError("need at least 2 clusters")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    for k_g, n_g in clusters:
        if n_g <= 0 or k_g < 0 or k_g > n_g:
            raise ValueError("each cluster needs n >= 1 and 0 <= k <= n")
    k = sum(c[0] for c in clusters)
    n = sum(c[1] for c in clusters)
    p = k / n
    ss = sum((k_g - p * n_g) ** 2 for k_g, n_g in clusters)
    var = g / (g - 1) * ss / (n * n)
    if var <= 0.0:
        deff = float("nan")
        if p in (0.0, 1.0):  # every cluster all-success (g, g) or all-failure (0, g)
            lo, hi = clopper_pearson(g if p == 1.0 else 0, g, confidence)
            method = "cluster_boundary_cp"
        else:  # identical interior cluster rates: no between-cluster signal; plain binomial
            lo, hi = clopper_pearson(k, n, confidence)
            method = "cluster_zero_variance_cp"
    else:
        half = t_ppf(1.0 - (1.0 - confidence) / 2, g - 1) * math.sqrt(var)
        lo, hi = max(0.0, p - half), min(1.0, p + half)
        method = "cluster_robust_t"
        binom_var = p * (1.0 - p) / n
        deff = var / binom_var if binom_var > 0 else float("nan")
    return ClusterRateEstimate(
        k=k, n=n, n_clusters=g, point=p, lower=lo, upper=hi, confidence=confidence,
        design_effect=deff, method=method,
    )
