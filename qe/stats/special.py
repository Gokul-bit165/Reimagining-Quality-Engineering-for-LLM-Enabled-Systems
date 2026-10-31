"""Stdlib special functions: regularized incomplete beta, beta and Student-t quantiles.

No scipy dependency (keeps the core install small). Accuracy is checked against closed forms
and published critical values in tests/unit/test_stats_ext.py.
"""

from __future__ import annotations

import math

_EPS = 1e-15
_TINY = 1e-300


def _beta_cf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _TINY else _TINY)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > _TINY else _TINY)
        c = 1.0 + aa / c
        c = c if abs(c) > _TINY else _TINY
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b) = P(Beta(a, b) <= x)."""
    if a <= 0.0 or b <= 0.0:
        raise ValueError("a and b must be > 0")
    if not 0.0 <= x <= 1.0:
        raise ValueError("x must be in [0, 1]")
    if x == 0.0 or x == 1.0:
        return x
    log_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return min(1.0, bt * _beta_cf(a, b, x) / a)
    return max(0.0, 1.0 - bt * _beta_cf(b, a, 1.0 - x) / b)


def beta_ppf(a: float, b: float, q: float) -> float:
    """Quantile of Beta(a, b) by bisection (monotone CDF)."""
    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if betainc(a, b, mid) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _t_cdf(t: float, df: float) -> float:
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))  # P(T > |t|)
    return 1.0 - tail if t > 0 else tail


def t_ppf(q: float, df: int) -> float:
    """Quantile of Student's t with `df` degrees of freedom."""
    if df < 1:
        raise ValueError("df must be >= 1")
    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    if q == 0.5:
        return 0.0
    if q < 0.5:
        return -t_ppf(1.0 - q, df)
    lo, hi = 0.0, 1.0
    while _t_cdf(hi, df) < q:  # bracket (heavy tails at small df/q near 1)
        hi *= 2.0
        if hi > 1e12:
            raise ValueError("quantile out of range")
    for _ in range(200):
        mid = (lo + hi) / 2
        if _t_cdf(mid, df) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
