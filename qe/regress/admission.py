"""Admission of a minimized case into the regression suite, with a KNOWN flake rate.

A genuine failure is observed as a failure with probability 1 - flake_rate per run (the
flake rate is measured by the caller on a known-bad control, never assumed here). A case is
admitted on the defective version iff its failure count over k runs is not improbably low:
failures >= s where s is the largest count with P(Binomial(k, 1 - flake) < s) <= alpha, so a
genuinely reproducing case is wrongly rejected with probability <= alpha. On the fixed version
failures must not exceed the same kind of bound for `clean_false_fail_rate` (default 0: no
tolerated spurious failures). alpha is an explicit argument, not a built-in constant.
"""

from __future__ import annotations

from math import ceil, comb, log

from pydantic import BaseModel, ConfigDict


class Admission(BaseModel):
    model_config = ConfigDict(frozen=True)
    admitted: bool
    successes: int  # failures reproduced on the defective version
    trials: int
    threshold: int
    reason: str


def _check_probability(name: str, value: float) -> None:
    if not 0.0 <= value < 1.0:
        raise ValueError(f"{name} must be in [0, 1)")


def repeats_needed(flake_rate: float, alpha: float) -> int:
    """Smallest r with flake_rate**r <= alpha (a real failure is masked r times w.p. <= alpha)."""
    _check_probability("flake_rate", flake_rate)
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if flake_rate == 0.0:
        return 1
    return max(1, ceil(log(alpha) / log(flake_rate) - 1e-12))


def _binom_lt(k: int, p: float, s: int) -> float:
    return sum(comb(k, i) * p**i * (1 - p) ** (k - i) for i in range(min(s, k + 1)))


def admission_threshold(k: int, flake_rate: float, alpha: float) -> int:
    _check_probability("flake_rate", flake_rate)
    if k < 1 or not 0.0 < alpha < 1.0:
        raise ValueError("need k >= 1 and alpha in (0, 1)")
    p = 1.0 - flake_rate
    return max(s for s in range(k + 2) if _binom_lt(k, p, s) <= alpha)


def decide_admission(
    *, k: int, buggy_failures: int, clean_failures: int, flake_rate: float, alpha: float,
    clean_false_fail_rate: float = 0.0,
) -> Admission:
    if not (0 <= buggy_failures <= k and 0 <= clean_failures <= k):
        raise ValueError("failure counts must lie in [0, k]")
    need = admission_threshold(k, flake_rate, alpha)
    if buggy_failures < need:
        return Admission(admitted=False, successes=buggy_failures, trials=k, threshold=need,
                         reason=f"does not reproduce reliably: {buggy_failures}/{k} < {need}")
    _check_probability("clean_false_fail_rate", clean_false_fail_rate)
    allowed = _clean_allowance(k, clean_false_fail_rate, alpha)
    if clean_failures > allowed:
        return Admission(admitted=False, successes=buggy_failures, trials=k, threshold=need,
                         reason=f"fails on the clean version: {clean_failures}/{k} > {allowed}")
    return Admission(admitted=True, successes=buggy_failures, trials=k, threshold=need,
                     reason="reproduces on defective version, passes on clean version")


def _clean_allowance(k: int, rate: float, alpha: float) -> int:
    """Smallest c with P(Binomial(k, rate) > c) <= alpha."""
    return min(c for c in range(k + 1) if 1.0 - _binom_lt(k, rate, c + 1) <= alpha)
