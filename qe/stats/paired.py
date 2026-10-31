"""Paired comparison of two systems on identical items (exact McNemar).

Definition: research/benchmarks/evaluation_metrics.md, "Interval methods" (McNemar for
paired binary outcomes); only discordant pairs carry information (research/11).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict


class McNemarResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    b: int  # A success, B failure
    c: int  # A failure, B success
    discordant: int
    p_value: float  # two-sided exact


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact p-value: 2 * P(X <= min(b, c)), X ~ Binomial(b + c, 1/2), capped at 1."""
    if b < 0 or c < 0:
        raise ValueError("counts must be non-negative")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return float(min(1.0, 2.0 * tail))


def mcnemar_exact(a_ok: Sequence[bool], b_ok: Sequence[bool]) -> McNemarResult:
    if len(a_ok) != len(b_ok):
        raise ValueError("paired outcomes must have equal length")
    b = sum(x and not y for x, y in zip(a_ok, b_ok, strict=True))
    c = sum(y and not x for x, y in zip(a_ok, b_ok, strict=True))
    return McNemarResult(b=b, c=c, discordant=b + c, p_value=mcnemar_exact_p(b, c))
