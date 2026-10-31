"""Simulation-based property tests for the P2 statistics (fixed seeds, deterministic)."""

import random
from statistics import NormalDist

from hypothesis import given, settings
from hypothesis import strategies as st

from qe.stats.agreement import correlation_matrix, panel_n_eff
from qe.stats.bayes import posterior
from qe.stats.cluster import cluster_bootstrap_rate
from qe.stats.estimators import pass_hat_k
from qe.stats.judge_correction import judge_corrected_rate

_N = NormalDist()


def correlated_errors(
    rng: random.Random, k: int, n: int, rate: float, rho: float
) -> list[list[bool]]:
    """k error vectors with marginal P(error)=rate and latent-Gaussian correlation rho."""
    cut = _N.inv_cdf(rate)
    rows: list[list[bool]] = [[] for _ in range(k)]
    for _ in range(n):
        z = rng.gauss(0, 1)
        for j in range(k):
            x = rho**0.5 * z + (1 - rho) ** 0.5 * rng.gauss(0, 1)
            rows[j].append(x < cut)
    return rows


def test_credible_interval_coverage_is_near_nominal() -> None:
    rng = random.Random(11)
    p, n, hits, reps = 0.2, 40, 0, 300
    for _ in range(reps):
        k = sum(rng.random() < p for _ in range(n))
        lo, hi = posterior(k, n).interval(0.95)
        hits += lo <= p <= hi
    assert 0.90 <= hits / reps <= 0.99


def test_cluster_bootstrap_coverage_on_clustered_data() -> None:
    rng = random.Random(5)
    m, size, hits, reps, true_p = 30, 5, 0, 60, 0.3
    for r in range(reps):
        outs: list[bool] = []
        cls: list[int] = []
        for c in range(m):
            pc = min(1.0, max(0.0, rng.gauss(true_p, 0.2)))  # cluster-level heterogeneity
            outs += [rng.random() < pc for _ in range(size)]
            cls += [c] * size
        ci = cluster_bootstrap_rate(outs, cls, resamples=300, seed=r)
        hits += ci.lower <= true_p <= ci.upper
    assert hits / reps >= 0.85  # nominal 0.95; percentile bootstrap + MC slack


def test_n_eff_tracks_known_correlation() -> None:
    rng = random.Random(21)
    k, n = 4, 6000
    for rho in (0.0, 0.5, 0.9):
        expected = k / (1 + (k - 1) * rho)  # design-effect formula for equicorrelation
        # latent correlation rho -> phi differs slightly from rho; check within tolerance
        n_eff = panel_n_eff(correlation_matrix(correlated_errors(rng, k, n, 0.3, rho)))
        assert abs(n_eff - expected) < 0.45, (rho, n_eff, expected)


def test_n_eff_is_monotone_in_correlation() -> None:
    rng = random.Random(33)
    vals = [
        panel_n_eff(correlation_matrix(correlated_errors(rng, 3, 4000, 0.3, rho)))
        for rho in (0.0, 0.4, 0.8)
    ]
    assert vals[0] > vals[1] > vals[2]


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.lists(st.booleans(), min_size=3, max_size=3), min_size=1, max_size=12
    )
)
def test_pass_hat_k_properties(outcomes: list[list[bool]]) -> None:
    full = pass_hat_k(outcomes)
    first_only = pass_hat_k([t[:1] for t in outcomes])
    two = pass_hat_k([t[:2] for t in outcomes])
    assert 0.0 <= full <= two <= first_only <= 1.0  # pass^k non-increasing in k


def test_pass_hat_k_matches_p_to_the_k_for_iid_trials() -> None:
    rng = random.Random(8)
    p, k, items = 0.8, 4, 4000
    outcomes = [[rng.random() < p for _ in range(k)] for _ in range(items)]
    assert abs(pass_hat_k(outcomes) - p**k) < 0.03


def test_judge_correction_recovers_true_rate_with_interval_coverage() -> None:
    rng = random.Random(2)
    tpr, fpr, true_p, n, hits, reps = 0.85, 0.1, 0.25, 800, 0, 40
    for r in range(reps):
        flagged = sum(
            rng.random() < (tpr if rng.random() < true_p else fpr) for _ in range(n)
        )
        tp = sum(rng.random() < tpr for _ in range(150))
        fp = sum(rng.random() < fpr for _ in range(150))
        res = judge_corrected_rate(
            flagged, n, tp=tp, positives=150, fp=fp, negatives=150, draws=800, seed=r
        )
        hits += res.lower <= true_p <= res.upper
    assert hits / reps >= 0.85
