import math

import pytest

from qe.stats.agreement import (
    correlation_matrix,
    error_correlation,
    kish_n_eff,
    overlap_count,
    panel_n_eff,
)
from qe.stats.bayes import BetaPosterior, beta_cdf, beta_ppf, posterior, prob_improvement
from qe.stats.cluster import cluster_bootstrap_rate, percentile
from qe.stats.judge_correction import judge_corrected_rate, rogan_gladen
from qe.stats.paired import mcnemar_exact, mcnemar_exact_p


def test_beta_cdf_known_values() -> None:
    assert beta_cdf(0.3, 1, 1) == pytest.approx(0.3, abs=1e-9)
    assert beta_cdf(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    assert beta_cdf(0.2, 1, 5) == pytest.approx(1 - 0.8**5, abs=1e-9)
    assert beta_cdf(0.9, 6, 1) == pytest.approx(0.9**6, abs=1e-9)  # exercises the x > mean branch
    assert beta_cdf(0.0, 2, 3) == 0.0 and beta_cdf(1.0, 2, 3) == 1.0
    with pytest.raises(ValueError):
        beta_cdf(0.5, 0, 1)


def test_beta_ppf_inverts_cdf() -> None:
    for q in (0.025, 0.5, 0.975):
        assert beta_cdf(beta_ppf(q, 3.5, 7.2), 3.5, 7.2) == pytest.approx(q, abs=1e-9)
    with pytest.raises(ValueError):
        beta_ppf(1.5, 1, 1)


def test_credible_interval_matches_closed_form() -> None:
    post = posterior(0, 10, prior=(1.0, 1.0))  # Beta(1, 11): CDF = 1 - (1-x)^11
    lo, hi = post.interval(0.95)
    assert lo == pytest.approx(1 - 0.975 ** (1 / 11), abs=1e-9)
    assert hi == pytest.approx(1 - 0.025 ** (1 / 11), abs=1e-9)
    assert post.mean == pytest.approx(1 / 12)
    assert post.cdf(0.5) == pytest.approx(1 - 0.5**11)


def test_posterior_validation() -> None:
    with pytest.raises(ValueError):
        posterior(3, 2)
    with pytest.raises(ValueError):
        posterior(-1, 2)
    with pytest.raises(ValueError):
        posterior(1, 2).interval(1.0)


def test_prob_improvement_closed_form_and_validation() -> None:
    u = BetaPosterior(1, 1)
    assert prob_improvement(u, u, 0.0) == pytest.approx(0.5, abs=1e-3)
    assert prob_improvement(u, u, 0.2) == pytest.approx(0.5 * 0.8**2, abs=1e-3)
    assert prob_improvement(u, u, 1.0) == pytest.approx(0.0, abs=1e-6)
    better = prob_improvement(posterior(40, 100), posterior(5, 100), 0.1)
    assert better > 0.99
    with pytest.raises(ValueError):
        prob_improvement(u, u, -0.1)


def test_percentile_interpolates() -> None:
    assert percentile([0.0, 1.0, 2.0, 3.0], 0.5) == 1.5
    assert percentile([5.0], 0.9) == 5.0


def test_cluster_bootstrap_is_deterministic_and_wider_than_iid_when_clustered() -> None:
    # 10 clusters of 10: each cluster is all-fail or all-pass (ICC = 1)
    outcomes = [c < 3 for c in range(10) for _ in range(10)]
    clusters = [c for c in range(10) for _ in range(10)]
    a = cluster_bootstrap_rate(outcomes, clusters, seed=7)
    b = cluster_bootstrap_rate(outcomes, clusters, seed=7)
    assert a == b
    assert a.point == pytest.approx(0.3) and a.n_clusters == 10 and a.n_items == 100
    from qe.stats.intervals import clopper_pearson

    iid_lo, iid_hi = clopper_pearson(30, 100)
    assert (a.upper - a.lower) > (iid_hi - iid_lo)  # clustering must widen the interval
    assert a.lower <= a.point <= a.upper


def test_cluster_bootstrap_validation() -> None:
    with pytest.raises(ValueError):
        cluster_bootstrap_rate([True], [1, 2])
    with pytest.raises(ValueError):
        cluster_bootstrap_rate([], [])
    with pytest.raises(ValueError):
        cluster_bootstrap_rate([True], [1], confidence=1.5)
    with pytest.raises(ValueError):
        cluster_bootstrap_rate([True], [1], resamples=0)
    single = cluster_bootstrap_rate([True, False], ["a", "a"], resamples=5)
    assert single.lower == single.upper == 0.5  # one cluster: no resampling variability


def test_mcnemar_exact_known_values() -> None:
    assert mcnemar_exact_p(0, 5) == pytest.approx(2 / 32)
    assert mcnemar_exact_p(3, 3) == 1.0
    assert mcnemar_exact_p(0, 0) == 1.0
    assert mcnemar_exact_p(2, 8) == pytest.approx(2 * (1 + 10 + 45) / 1024)
    with pytest.raises(ValueError):
        mcnemar_exact_p(-1, 2)


def test_mcnemar_from_pairs() -> None:
    a = [True, True, True, False, False, True]
    b = [False, True, True, True, True, True]
    r = mcnemar_exact(a, b)
    assert (r.b, r.c, r.discordant) == (1, 2, 3)
    assert r.p_value == 1.0
    with pytest.raises(ValueError):
        mcnemar_exact([True], [True, False])


def test_rogan_gladen() -> None:
    assert rogan_gladen(0.3, 0.9, 0.1) == pytest.approx(0.25)
    assert rogan_gladen(0.0, 0.9, 0.1) == 0.0  # clipped
    assert rogan_gladen(1.0, 0.9, 0.1) == 1.0  # clipped
    with pytest.raises(ValueError):
        rogan_gladen(0.3, 0.5, 0.5)
    with pytest.raises(ValueError):
        rogan_gladen(1.2, 0.9, 0.1)


def test_judge_corrected_rate_interval_contains_truth_and_is_deterministic() -> None:
    kw = dict(tp=90, positives=100, fp=10, negatives=100)
    r1 = judge_corrected_rate(300, 1000, **kw, seed=3)
    r2 = judge_corrected_rate(300, 1000, **kw, seed=3)
    assert r1 == r2
    assert r1.corrected == pytest.approx(0.25) and r1.lower < 0.25 < r1.upper
    assert r1.lower > 0.1 and r1.upper < 0.4  # sanity: propagation, not a degenerate interval
    assert r1.observed == 0.3 and r1.tpr == 0.9 and r1.fpr == 0.1


def test_judge_correction_rejects_uninformative_judge_and_bad_counts() -> None:
    with pytest.raises(ValueError):
        judge_corrected_rate(30, 100, tp=50, positives=100, fp=50, negatives=100)
    with pytest.raises(ValueError):
        judge_corrected_rate(30, 100, tp=101, positives=100, fp=1, negatives=100)
    with pytest.raises(ValueError):
        judge_corrected_rate(30, 0, tp=1, positives=10, fp=1, negatives=10)
    with pytest.raises(ValueError):
        judge_corrected_rate(30, 100, tp=9, positives=10, fp=1, negatives=10, confidence=0.0)


def test_kish_n_eff() -> None:
    assert kish_n_eff([1, 1, 1, 1]) == pytest.approx(4.0)
    assert kish_n_eff([1, 0, 0]) == pytest.approx(1.0)
    assert kish_n_eff([2, 1, 1]) == pytest.approx(16 / 6)
    for bad in ([], [0, 0], [-1, 2]):
        with pytest.raises(ValueError):
            kish_n_eff(bad)


def test_error_correlation_basics() -> None:
    a = [True, True, False, False, True, False]
    assert error_correlation(a, a) == pytest.approx(1.0)
    assert error_correlation(a, [not x for x in a]) == pytest.approx(-1.0)
    assert error_correlation(a, [False] * 6) == 0.0  # no variance -> defined as 0
    assert error_correlation([True], [True]) == 0.0
    with pytest.raises(ValueError):
        error_correlation([True], [True, False])


def test_error_correlation_drops_abstentions_pairwise() -> None:
    a = [True, False, None, True, False, True]
    b = [True, False, True, None, False, True]
    assert overlap_count(a, b) == 4
    assert error_correlation(a, b) == pytest.approx(1.0)


def test_panel_n_eff() -> None:
    ident = [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]
    indep = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    half = [[1.0, 0.5], [0.5, 1.0]]
    assert panel_n_eff(ident) == pytest.approx(1.0)
    assert panel_n_eff(indep) == pytest.approx(3.0)
    assert panel_n_eff(half) == pytest.approx(2 / (1 + 0.5))
    assert panel_n_eff([[1.0, -1.0], [-1.0, 1.0]]) == 2.0  # sum <= 0 -> capped at k
    with pytest.raises(ValueError):
        panel_n_eff([])
    with pytest.raises(ValueError):
        panel_n_eff([[1.0, 0.0]])
    assert not math.isnan(correlation_matrix([[True, False, True]])[0][0])
