"""Panel redundancy: pairwise error correlation and Kish effective sample size.

Definitions: research/benchmarks/evaluation_metrics.md, "Agreement and independence"
(pairwise error-correlation matrix, Kish n_eff for panels) and research/11
(n_eff = (sum w)^2 / sum w^2). Errors are boolean indicators (verifier wrong on item).
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence


def kish_n_eff(weights: Sequence[float]) -> float:
    """Kish effective sample size (sum w)^2 / sum w^2."""
    if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
        raise ValueError("need non-negative weights with a positive sum")
    return sum(weights) ** 2 / sum(w * w for w in weights)


def overlap_count(a: Sequence[bool | None], b: Sequence[bool | None]) -> int:
    """Items on which both verifiers were decisive."""
    return sum(x is not None and y is not None for x, y in zip(a, b, strict=True))


def error_correlation(a: Sequence[bool | None], b: Sequence[bool | None]) -> float:
    """Phi coefficient of two error-indicator vectors on items where both are decisive.

    None marks an abstention and is dropped pairwise. If either vector has no variance on
    the overlap, correlation is undefined and 0.0 is returned (no evidence of shared
    errors); callers needing the distinction should check `overlap_count`.
    """
    if len(a) != len(b):
        raise ValueError("vectors must have equal length")
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return 0.0
    n11 = sum(x and y for x, y in pairs)
    n1_ = sum(x for x, _ in pairs)
    n_1 = sum(y for _, y in pairs)
    denom = math.sqrt(n1_ * (n - n1_) * n_1 * (n - n_1))
    if denom == 0.0:
        return 0.0
    return (n * n11 - n1_ * n_1) / denom


def correlation_matrix(errors: Sequence[Sequence[bool | None]]) -> list[list[float]]:
    k = len(errors)
    m = [[1.0] * k for _ in range(k)]
    for i in range(k):
        for j in range(i + 1, k):
            m[i][j] = m[j][i] = error_correlation(errors[i], errors[j])
    return m


def panel_n_eff(corr: Sequence[Sequence[float]]) -> float:
    """Effective number of independent verifiers: k^2 / sum_ij R_ij, bounded to [1, k].

    For equicorrelated errors with correlation r this equals k / (1 + (k-1) r)
    (the design effect), so independent panels give k and identical panels give 1.
    """
    k = len(corr)
    if k == 0 or any(len(r) != k for r in corr):
        raise ValueError("need a non-empty square correlation matrix")
    total = sum(sum(r) for r in corr)
    if total <= 0:
        return float(k)
    return min(float(k), max(1.0, k * k / total))


def cohen_kappa(a: Sequence[Hashable | None], b: Sequence[Hashable | None]) -> float | None:
    """Cohen's kappa of two label vectors on items where both are decisive (None = abstain).

    None when undefined: no overlap, or chance agreement is 1 (both raters constant and equal).
    """
    if len(a) != len(b):
        raise ValueError("vectors must have equal length")
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(x == y for x, y in pairs) / n
    labels = {x for x, _ in pairs} | {y for _, y in pairs}
    chance = sum((sum(x == c for x, _ in pairs) / n) * (sum(y == c for _, y in pairs) / n)
                 for c in labels)
    if chance >= 1.0:
        return None
    return (observed - chance) / (1.0 - chance)
