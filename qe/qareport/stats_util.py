"""Small statistics helpers; every interval comes from qe.stats (exact methods)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qe.stats.estimators import rate_estimate


def percentile(values: Sequence[float], q: float) -> float:
    """Same nearest-rank rule as qe.realeval.assemble._pct, so figures agree with the scorecard."""
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def rate(k: int, n: int) -> dict[str, Any]:
    """k of n with an exact 95% Clopper-Pearson interval; n=0 is 'not measurable'."""
    if n == 0:
        return {"k": 0, "n": 0, "value": None, "ci_low": None, "ci_high": None}
    e = rate_estimate(k, n)
    return {"k": k, "n": n, "value": e.point, "ci_low": e.lower, "ci_high": e.upper}


def latency_summary(latencies: Sequence[float]) -> dict[str, Any]:
    if not latencies:
        return {"n": 0, "p50": None, "p90": None, "p95": None, "p99": None, "min": None,
                "max": None, "mean": None}
    return {"n": len(latencies), "p50": percentile(latencies, 0.5),
            "p90": percentile(latencies, 0.9), "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99), "min": min(latencies), "max": max(latencies),
            "mean": sum(latencies) / len(latencies)}
