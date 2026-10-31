"""Property tests for intervals and pass^k (hypothesis)."""

from __future__ import annotations

import random
from math import comb

from hypothesis import given, settings
from hypothesis import strategies as st

from qe.stats.bayes import beta_credible
from qe.stats.cluster import cluster_rate
from qe.stats.estimators import pass_hat_k, pass_hat_k_at
from qe.stats.intervals import clopper_pearson

kn = st.integers(1, 80).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n)))
conf = st.sampled_from([0.8, 0.9, 0.95, 0.99])
items = st.integers(1, 6).flatmap(
    lambda t: st.lists(st.lists(st.booleans(), min_size=t, max_size=t), min_size=1, max_size=8)
)


@settings(max_examples=60, deadline=None)
@given(kn, conf)
def test_intervals_ordered_bounded_and_nested_by_confidence(x: tuple[int, int], c: float) -> None:
    k, n = x
    for f in (clopper_pearson, beta_credible):
        lo, hi = f(k, n, c)
        assert 0.0 <= lo <= hi <= 1.0
        lo99, hi99 = f(k, n, 0.995)
        assert lo99 <= lo + 1e-9 and hi99 >= hi - 1e-9  # higher confidence never narrower


@settings(max_examples=60, deadline=None)
@given(kn)
def test_interval_endpoints_monotone_in_successes(x: tuple[int, int]) -> None:
    k, n = x
    if k == n:
        return
    for f in (clopper_pearson, beta_credible):
        lo0, hi0 = f(k, n)
        lo1, hi1 = f(k + 1, n)
        assert lo1 >= lo0 - 1e-9 and hi1 >= hi0 - 1e-9


@settings(max_examples=40, deadline=None)
@given(kn)
def test_reflection_symmetry(x: tuple[int, int]) -> None:
    k, n = x
    for f in (clopper_pearson, beta_credible):
        lo, hi = f(k, n)
        lo2, hi2 = f(n - k, n)
        assert abs((1 - hi) - lo2) < 1e-7 and abs((1 - lo) - hi2) < 1e-7


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 10), st.just(10)), min_size=2, max_size=12))
def test_cluster_rate_bounded_and_contains_point(cl: list[tuple[int, int]]) -> None:
    est = cluster_rate(cl)
    assert 0.0 <= est.lower <= est.point <= est.upper <= 1.0


@settings(max_examples=80, deadline=None)
@given(items)
def test_pass_hat_k_bounded_and_nonincreasing_in_k(data: list[list[bool]]) -> None:
    t = len(data[0])
    vals = [pass_hat_k_at(data, k) for k in range(1, t + 1)]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert all(a >= b - 1e-12 for a, b in zip(vals, vals[1:], strict=False))
    assert abs(vals[0] - sum(sum(r) / t for r in data) / len(data)) < 1e-12  # k=1: mean pass rate
    assert vals[-1] == pass_hat_k(data)


@settings(max_examples=60, deadline=None)
@given(items, st.integers(0, 10_000))
def test_pass_hat_k_permutation_invariant(data: list[list[bool]], seed: int) -> None:
    rng = random.Random(seed)
    shuffled = [rng.sample(r, len(r)) for r in data]
    rng.shuffle(shuffled)
    for k in range(1, len(data[0]) + 1):
        assert abs(pass_hat_k_at(data, k) - pass_hat_k_at(shuffled, k)) < 1e-12


@settings(max_examples=60, deadline=None)
@given(st.integers(1, 12).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n), st.integers(1, n))))
def test_pass_hat_k_unbiased_for_iid_item(x: tuple[int, int, int]) -> None:
    """C(c,k)/C(n,k) is the exact fraction of k-subsets of the n trials that all pass."""
    c, n, k = x
    outcomes = [[True] * c + [False] * (n - c)]
    assert abs(pass_hat_k_at(outcomes, k) - comb(c, k) / comb(n, k)) < 1e-12
