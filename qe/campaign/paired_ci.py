"""Paired two-proportion statistics for the same items scored on two targets.

Newcombe (1998) method 10 interval for the difference of paired proportions (Wilson score
intervals combined through the phi correlation of the 2x2 table) and Cohen's h. The significance
test is exact McNemar from qe.stats.paired. Deterministic; no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z95 = 1.959963984540054  # standard normal 97.5% quantile (95% two-sided)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class PairedDiff:
    n: int
    p_a: float
    p_b: float
    diff: float
    ci_low: float
    ci_high: float
    cohens_h: float


def newcombe_paired(both: int, a_only: int, b_only: int, neither: int) -> PairedDiff:
    """A and B success on the same n items; difference = P(A ok) - P(B ok)."""
    n = both + a_only + b_only + neither
    if n <= 0:
        raise ValueError("need at least one pair")
    p1, p2 = (both + a_only) / n, (both + b_only) / n
    l1, u1 = wilson(both + a_only, n)
    l2, u2 = wilson(both + b_only, n)
    margins = (both + a_only) * (b_only + neither) * (both + b_only) * (a_only + neither)
    phi = 0.0 if margins == 0 else (both * neither - a_only * b_only) / math.sqrt(margins)
    d_lo, d_hi = p1 - l1, u2 - p2
    e_lo, e_hi = u1 - p1, p2 - l2
    lower = (p1 - p2) - math.sqrt(max(0.0, d_lo**2 + d_hi**2 - 2 * phi * d_lo * d_hi))
    upper = (p1 - p2) + math.sqrt(max(0.0, e_lo**2 + e_hi**2 - 2 * phi * e_lo * e_hi))
    h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))
    return PairedDiff(n=n, p_a=p1, p_b=p2, diff=p1 - p2, ci_low=max(-1.0, lower),
                      ci_high=min(1.0, upper), cohens_h=h)
