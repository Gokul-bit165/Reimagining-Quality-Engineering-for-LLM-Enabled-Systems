"""M1 stats extensions: special functions, Bayesian, cluster-robust, judge-corrected, pass^k@k."""

from __future__ import annotations

import math
import random

import pytest

from qe.stats.bayes import beta_credible
from qe.stats.cluster import cluster_rate
from qe.stats.estimators import pass_hat_k, pass_hat_k_at, pass_hat_k_estimate
from qe.stats.intervals import clopper_pearson
from qe.stats.judge import CalibrationCounts, judge_corrected_rate, rogan_gladen
from qe.stats.special import beta_ppf, betainc, t_ppf

# ---------- special functions ----------


def test_betainc_closed_form_and_symmetry() -> None:
    # I_x(2,3) = sum_{j=2..4} C(4,j) x^j (1-x)^(4-j) = 0.5248 at x=0.4
    assert betainc(2.0, 3.0, 0.4) == pytest.approx(0.5248, abs=1e-10)
    assert betainc(6.0, 6.0, 0.5) == pytest.approx(0.5, abs=1e-12)
    assert betainc(2.5, 4.0, 0.3) == pytest.approx(1.0 - betainc(4.0, 2.5, 0.7), abs=1e-12)
    assert betainc(1.0, 1.0, 0.37) == pytest.approx(0.37, abs=1e-12)
    assert betainc(3.0, 2.0, 0.0) == 0.0 and betainc(3.0, 2.0, 1.0) == 1.0


def test_beta_ppf_inverts_betainc() -> None:
    for a, b, q in [(0.5, 0.5, 0.025), (6.0, 6.0, 0.975), (1.0, 11.0, 0.5), (30.0, 2.0, 0.1)]:
        assert betainc(a, b, beta_ppf(a, b, q)) == pytest.approx(q, abs=1e-9)


def test_t_ppf_known_critical_values() -> None:
    assert t_ppf(0.975, 1) == pytest.approx(12.7062, abs=1e-3)
    assert t_ppf(0.975, 10) == pytest.approx(2.2281, abs=1e-3)
    assert t_ppf(0.975, 29) == pytest.approx(2.0452, abs=1e-3)
    assert t_ppf(0.025, 10) == pytest.approx(-2.2281, abs=1e-3)
    assert t_ppf(0.5, 7) == pytest.approx(0.0, abs=1e-9)


def test_special_validation() -> None:
    with pytest.raises(ValueError):
        betainc(0.0, 1.0, 0.5)
    with pytest.raises(ValueError):
        betainc(1.0, 1.0, 1.5)
    with pytest.raises(ValueError):
        t_ppf(0.975, 0)
    with pytest.raises(ValueError):
        beta_ppf(1.0, 1.0, 1.0)


# ---------- Bayesian ----------


def test_bayes_uniform_prior_is_equal_tailed_posterior() -> None:
    lo, hi = beta_credible(5, 10, confidence=0.95, prior=(1.0, 1.0))  # posterior Beta(6, 6)
    assert betainc(6.0, 6.0, lo) == pytest.approx(0.025, abs=1e-8)
    assert betainc(6.0, 6.0, hi) == pytest.approx(0.975, abs=1e-8)
    assert lo + hi == pytest.approx(1.0, abs=1e-9)  # symmetric posterior


def test_bayes_default_prior_is_jeffreys_and_boundary_is_informative() -> None:
    lo, hi = beta_credible(0, 20)
    assert lo == 0.0 or lo < 1e-3
    assert 0.0 < hi < 0.2
    # Jeffreys credible interval is narrower than exact CP at zero failures
    assert hi < clopper_pearson(0, 20)[1]


def test_bayes_validation() -> None:
    with pytest.raises(ValueError):
        beta_credible(3, 2)
    with pytest.raises(ValueError):
        beta_credible(1, 5, prior=(0.0, 1.0))
    with pytest.raises(ValueError):
        beta_credible(1, 5, confidence=1.0)


def test_bayes_prior_calibration_coverage() -> None:
    """If p ~ prior, credible intervals cover p at the nominal rate (exact in expectation)."""
    rng = random.Random(7)
    a, b, n, trials, hits = 2.0, 3.0, 20, 600, 0
    for _ in range(trials):
        p = rng.betavariate(a, b)
        k = sum(rng.random() < p for _ in range(n))
        lo, hi = beta_credible(k, n, 0.9, prior=(a, b))
        hits += lo <= p <= hi
    assert hits / trials >= 0.86  # nominal 0.90, MC s.e. ~0.012 -> 3 s.e. slack


# ---------- cluster-robust ----------


def test_cluster_rate_matches_hand_computation() -> None:
    clusters = [(2, 10), (5, 10), (8, 10), (3, 10)]  # p = 18/40 = 0.45
    est = cluster_rate(clusters, confidence=0.95)
    resid = [k - 0.45 * n for k, n in clusters]
    g = len(clusters)
    se = math.sqrt(g / (g - 1) * sum(e * e for e in resid)) / 40
    half = t_ppf(0.975, g - 1) * se
    assert est.point == pytest.approx(0.45)
    assert est.lower == pytest.approx(max(0.0, 0.45 - half), abs=1e-9)
    assert est.upper == pytest.approx(min(1.0, 0.45 + half), abs=1e-9)
    assert est.n_clusters == 4 and est.n == 40 and est.method == "cluster_robust_t"


def test_cluster_wider_than_naive_when_clusters_are_heterogeneous() -> None:
    clusters = [(0, 10), (10, 10)] * 5  # perfectly clustered outcomes
    est = cluster_rate(clusters)
    naive = clopper_pearson(50, 100)
    assert est.design_effect > 1.0
    assert (est.upper - est.lower) > (naive[1] - naive[0])


def test_cluster_boundary_falls_back_to_cluster_level_cp() -> None:
    est = cluster_rate([(10, 10)] * 6)  # zero variance, p=1: se=0 must not give [1,1]
    assert est.method == "cluster_boundary_cp"
    assert est.upper == 1.0 and est.lower == pytest.approx(clopper_pearson(6, 6)[0])
    est0 = cluster_rate([(0, 10)] * 6)
    assert est0.lower == 0.0 and est0.upper == pytest.approx(clopper_pearson(0, 6)[1])


def test_cluster_validation() -> None:
    with pytest.raises(ValueError):
        cluster_rate([(1, 2)])  # need >= 2 clusters
    with pytest.raises(ValueError):
        cluster_rate([(3, 2), (1, 2)])
    with pytest.raises(ValueError):
        cluster_rate([(0, 0), (1, 2)])


def test_cluster_coverage_beats_naive_on_clustered_data() -> None:
    rng = random.Random(11)
    g, m, trials = 30, 10, 400
    mu, conc = 0.3, 2.0  # cluster p ~ Beta(mu*conc, (1-mu)*conc): strong intra-cluster correlation
    cluster_hits = naive_hits = 0
    for _ in range(trials):
        cl = []
        for _ in range(g):
            pg = rng.betavariate(mu * conc, (1 - mu) * conc)
            cl.append((sum(rng.random() < pg for _ in range(m)), m))
        est = cluster_rate(cl)
        cluster_hits += est.lower <= mu <= est.upper
        lo, hi = clopper_pearson(sum(k for k, _ in cl), g * m)
        naive_hits += lo <= mu <= hi
    assert cluster_hits / trials >= 0.90
    assert cluster_hits > naive_hits  # the reason this module exists (measured, seed 11)


# ---------- judge-corrected ----------


def test_rogan_gladen_exact_algebra() -> None:
    # theta=0.2, sens=0.8, spec=0.9 -> q = 0.2*0.8 + 0.8*0.1 = 0.24
    assert rogan_gladen(0.24, 0.8, 0.9) == pytest.approx(0.2)
    assert rogan_gladen(0.0, 0.8, 0.9) == 0.0  # clipped (raw value would be negative)
    assert rogan_gladen(1.0, 0.8, 0.9) == 1.0  # clipped
    with pytest.raises(ValueError):
        rogan_gladen(0.3, 0.5, 0.5)  # Youden J = 0: judge carries no information


def test_calibration_counts_validation_and_rates() -> None:
    cal = CalibrationCounts(tp=40, fn=10, tn=45, fp=5)
    assert cal.sensitivity == pytest.approx(0.8) and cal.specificity == pytest.approx(0.9)
    with pytest.raises(ValueError):
        CalibrationCounts(tp=0, fn=0, tn=5, fp=5)  # no positives labelled
    with pytest.raises(ValueError):
        CalibrationCounts(tp=-1, fn=1, tn=1, fp=1)


def test_judge_corrected_removes_judge_bias_and_reports_uncertainty() -> None:
    cal = CalibrationCounts(tp=160, fn=40, tn=360, fp=40)  # sens 0.8, spec 0.9
    est = judge_corrected_rate(flagged=240, n=1000, cal=cal, draws=4000, seed=3)
    assert est.apparent_rate == pytest.approx(0.24)
    assert est.point == pytest.approx(0.2, abs=1e-9)
    assert est.lower < 0.2 < est.upper
    assert est.upper - est.lower > beta_width(240, 1000)  # calibration noise widens the interval
    assert est.method == "rogan_gladen_bayes_mc" and est.draws == 4000 and est.seed == 3


def beta_width(k: int, n: int) -> float:
    lo, hi = beta_credible(k, n)
    return hi - lo


def test_judge_corrected_is_deterministic_given_seed() -> None:
    cal = CalibrationCounts(tp=40, fn=10, tn=45, fp=5)
    a = judge_corrected_rate(30, 100, cal, draws=2000, seed=5)
    b = judge_corrected_rate(30, 100, cal, draws=2000, seed=5)
    assert a == b


def test_judge_corrected_flags_weak_judge_instead_of_hiding_it() -> None:
    weak = CalibrationCounts(tp=11, fn=9, tn=10, fp=10)  # barely better than chance, tiny cal set
    est = judge_corrected_rate(10, 40, weak, draws=3000, seed=1)
    assert est.unidentified_fraction > 0.0  # some posterior draws have Youden J <= 0
    assert est.lower == 0.0 or est.upper == 1.0 or est.upper - est.lower > 0.5


def test_judge_corrected_coverage_simulation() -> None:
    rng = random.Random(21)
    theta, sens, spec, trials, hits = 0.2, 0.8, 0.9, 120, 0
    for i in range(trials):
        tp = sum(rng.random() < sens for _ in range(100))
        tn = sum(rng.random() < spec for _ in range(100))
        cal = CalibrationCounts(tp=tp, fn=100 - tp, tn=tn, fp=100 - tn)
        n = 400
        flagged = sum(rng.random() < (theta * sens + (1 - theta) * (1 - spec)) for _ in range(n))
        est = judge_corrected_rate(flagged, n, cal, draws=1500, seed=i)
        hits += est.lower <= theta <= est.upper
    assert hits / trials >= 0.88  # nominal 0.95; MC s.e. ~0.02 plus finite-draw slack


# ---------- pass^k at arbitrary k ----------


def test_pass_hat_k_at_matches_taubench_combinatorial_estimator() -> None:
    items = [[True, True, True, False], [True, False, False, False], [True, True, True, True]]
    # per-item C(c,k)/C(n,k): c = 3, 1, 4 with n = 4
    assert pass_hat_k_at(items, 1) == pytest.approx((3 / 4 + 1 / 4 + 1) / 3)
    assert pass_hat_k_at(items, 2) == pytest.approx((3 / 6 + 0 + 1) / 3)
    assert pass_hat_k_at(items, 4) == pytest.approx((0 + 0 + 1) / 3)
    assert pass_hat_k_at(items, 4) == pass_hat_k(items)


def test_pass_hat_k_at_validation() -> None:
    with pytest.raises(ValueError):
        pass_hat_k_at([[True, False]], 3)  # k > trials
    with pytest.raises(ValueError):
        pass_hat_k_at([[True, False]], 0)
    with pytest.raises(ValueError):
        pass_hat_k_at([[True], [True, False]], 1)  # ragged trials
    with pytest.raises(ValueError):
        pass_hat_k_at([], 1)


def test_pass_hat_k_estimate_has_interval_on_items() -> None:
    items = [[True, True]] * 7 + [[True, False]] * 3
    est = pass_hat_k_estimate(items)
    assert (est.k, est.n, est.point) == (7, 10, 0.7)
    assert (est.lower, est.upper) == clopper_pearson(7, 10)
