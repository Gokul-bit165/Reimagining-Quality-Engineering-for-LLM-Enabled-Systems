"""ASR@budget and paired attacker comparison, computed from campaign outcomes (R5, R11).

Unit of analysis = attack pair (n is small; pairs within a surface are correlated, so the
interval understates the true uncertainty; state this in every report that uses it).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from qe.stats.intervals import clopper_pearson


@dataclass(frozen=True)
class AsrEstimate:
    attacker_class: str
    budget: int
    successes: int
    n_pairs: int
    asr: float
    lower: float
    upper: float


def asr_at_budget(
    first_success: Mapping[str, int | None],
    budget: int,
    attacker_class: str,
    confidence: float = 0.95,
) -> AsrEstimate:
    """`first_success`: pair_id -> 1-based attempt of first oracle breach (None = never)."""
    if budget < 1 or not first_success:
        raise ValueError("need budget >= 1 and at least one pair")
    k = sum(1 for v in first_success.values() if v is not None and v <= budget)
    n = len(first_success)
    lo, hi = clopper_pearson(k, n, confidence)
    return AsrEstimate(attacker_class, budget, k, n, k / n, lo, hi)


def _wilson(k: int, n: int, z: float) -> tuple[float, float]:
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def _binom_two_sided(b: int, c: int) -> float:
    """Exact McNemar p-value: two-sided binomial test of b vs c discordant pairs at p=0.5."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return float(min(1.0, 2 * tail))


@dataclass(frozen=True)
class PairedComparison:
    a_label: str
    b_label: str
    budget: int
    n_pairs: int
    both: int
    a_only: int
    b_only: int
    neither: int
    diff: float  # P(a succeeds) - P(b succeeds)
    lower: float
    upper: float
    mcnemar_p: float


def paired_comparison(
    a: Mapping[str, int | None],
    b: Mapping[str, int | None],
    budget: int,
    a_label: str,
    b_label: str,
    confidence: float = 0.95,
) -> PairedComparison:
    """Newcombe (1998) method 10 interval for a paired difference of proportions + exact McNemar."""
    if set(a) != set(b) or not a:
        raise ValueError("both arms must cover the same non-empty set of pairs")
    n = len(a)
    sa = {p for p, v in a.items() if v is not None and v <= budget}
    sb = {p for p, v in b.items() if v is not None and v <= budget}
    both, a_only, b_only = len(sa & sb), len(sa - sb), len(sb - sa)
    neither = n - both - a_only - b_only
    z = _z(confidence)
    p1, p2 = len(sa) / n, len(sb) / n
    l1, u1 = _wilson(len(sa), n, z)
    l2, u2 = _wilson(len(sb), n, z)
    denom = (both + a_only) * (b_only + neither) * (both + b_only) * (a_only + neither)
    phi = 0.0 if denom == 0 else (both * neither - a_only * b_only) / math.sqrt(denom)
    d = p1 - p2
    lo = d - math.sqrt(max(0.0, (p1 - l1) ** 2 + (u2 - p2) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2)))
    hi = d + math.sqrt(max(0.0, (u1 - p1) ** 2 + (p2 - l2) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2)))
    return PairedComparison(
        a_label,
        b_label,
        budget,
        n,
        both,
        a_only,
        b_only,
        neither,
        d,
        max(-1.0, lo),
        min(1.0, hi),
        _binom_two_sided(a_only, b_only),
    )


def _z(confidence: float) -> float:
    """Normal quantile for a two-sided interval (bisection on erf; no scipy dependency)."""
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    lo, hi = 0.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if math.erf(mid / math.sqrt(2)) < confidence:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
