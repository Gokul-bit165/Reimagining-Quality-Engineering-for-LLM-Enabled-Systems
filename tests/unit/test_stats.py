import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qe.stats.estimators import pass_hat_k, rate_estimate
from qe.stats.intervals import clopper_pearson


def test_zero_failures_upper_bound_near_rule_of_three() -> None:
    lo, hi = clopper_pearson(0, 100, confidence=0.95)
    assert lo == 0.0 and hi == pytest.approx(0.03622, abs=2e-4)  # 1-0.025**(1/100); two-sided exact


def test_known_value() -> None:
    lo, hi = clopper_pearson(5, 20, confidence=0.95)
    assert lo == pytest.approx(0.0866, abs=1e-3) and hi == pytest.approx(0.4910, abs=1e-3)


def test_edges_and_validation() -> None:
    assert clopper_pearson(10, 10)[1] == 1.0
    with pytest.raises(ValueError):
        clopper_pearson(3, 2)
    with pytest.raises(ValueError):
        clopper_pearson(0, 0)


@settings(max_examples=30, deadline=None)
@given(st.integers(1, 60).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_interval_contains_point_and_is_ordered(kn: tuple[int, int]) -> None:
    k, n = kn
    lo, hi = clopper_pearson(k, n)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


def test_coverage_on_simulated_data_is_at_least_nominal() -> None:
    import random

    rng = random.Random(1)
    p, n, hits, trials = 0.3, 25, 0, 400
    for _ in range(trials):
        k = sum(rng.random() < p for _ in range(n))
        lo, hi = clopper_pearson(k, n, confidence=0.95)
        hits += lo <= p <= hi
    assert hits / trials >= 0.93  # CP is conservative; allow Monte-Carlo slack


def test_rate_estimate_carries_interval() -> None:
    est = rate_estimate(2, 10)
    assert est.k == 2 and est.n == 10 and est.lower < 0.2 < est.upper


def test_pass_hat_k() -> None:
    # 3 items, k=2 trials each: item outcomes (2/2, 1/2, 0/2) -> pass^2 = (1+0+0)/3
    assert pass_hat_k([[True, True], [True, False], [False, False]]) == pytest.approx(1 / 3)
    assert not math.isnan(pass_hat_k([[True]]))
    with pytest.raises(ValueError):
        pass_hat_k([])
