"""Cluster-robust rate intervals (grouped items share document/template/app).

Definition: research/benchmarks/evaluation_metrics.md, "Interval methods" (cluster-robust SEs
for grouped items) and research/17 section 5 (clustered by app/document/template).
Cluster bootstrap resamples whole clusters with a fixed seed, so output is deterministic.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Hashable, Sequence

from pydantic import BaseModel, ConfigDict

DEFAULT_RESAMPLES = 2000


class ClusterRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    point: float
    lower: float
    upper: float
    n_items: int
    n_clusters: int
    confidence: float
    method: str = "cluster_bootstrap_percentile"


def percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an ascending list."""
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def cluster_bootstrap_rate(
    outcomes: Sequence[bool],
    clusters: Sequence[Hashable],
    *,
    confidence: float = 0.95,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> ClusterRate:
    """Rate of True outcomes with a percentile interval from resampling whole clusters."""
    if len(outcomes) != len(clusters) or not outcomes:
        raise ValueError("outcomes and clusters must be equal-length and non-empty")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if resamples < 1:
        raise ValueError("resamples must be >= 1")
    groups: dict[Hashable, list[int]] = defaultdict(list)
    for o, c in zip(outcomes, clusters, strict=True):
        groups[c].append(int(o))
    sums = [sum(v) for v in groups.values()]
    sizes = [len(v) for v in groups.values()]
    m = len(sums)
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(resamples):
        idx = [rng.randrange(m) for _ in range(m)]
        stats.append(sum(sums[i] for i in idx) / sum(sizes[i] for i in idx))
    stats.sort()
    tail = (1.0 - confidence) / 2
    return ClusterRate(
        point=sum(sums) / sum(sizes),
        lower=percentile(stats, tail),
        upper=percentile(stats, 1.0 - tail),
        n_items=len(outcomes),
        n_clusters=m,
        confidence=confidence,
    )
