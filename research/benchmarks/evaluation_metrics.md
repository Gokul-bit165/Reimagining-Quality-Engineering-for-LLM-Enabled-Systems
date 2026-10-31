# Evaluation Metrics — Definitions and Estimation Notes

(See `11_statistical_reliability.md` for rationale.) All metrics are reported with an interval and the unit of analysis.

## Detection (defect level, deduplicated by root cause)
- Precision = TP/(TP+FP); Recall = TP/(TP+FN) vs **known** defects; FPR = FP/(FP+TN) (requires defect-free controls); FNR = 1−Recall.
- Unknown-defect recall is not estimable; capture-recapture style estimates across independent methods are possible but untested here (hypothesis).

## Grounding / hallucination
- Per-claim confusion matrix across six states (Supported, Contradicted, Partially supported, Unsupported, Unverifiable, Source unavailable); report macro and per-class precision/recall; treat "Unverifiable" as its own class.
- Report **context-faithfulness** (supported by retrieved context) and **world-factuality** separately.
- Citation correctness: existence (deterministic) × support (adjudicated).

## Security
- ASR@B: outcome-oracle-confirmed successes / attempts at attacker budget B and class (static, adaptive black-box, human).
- Prevention rate = 1 − ASR@B on the same task–attack pairs; paired across arms.
- Utility under attack (as in AgentDojo-style benchmarks).

## Coverage
- Risk coverage = |cells with ≥1 valid executed test| / |cells in risk register|; compare with an independently authored register.
- Structural coverage (hypotheses): span-edge, tool-sequence n-gram, retrieved-chunk coverage, branch/fallback coverage.
- Regression coverage = past validated failures with live tests / validated failures.

## Agreement and independence
- Cohen's κ (2 raters), Krippendorff's α (≥2, missing data), pairwise error-correlation matrix, Kish n_eff for panels.

## Calibration
- Brier score; reliability diagrams; ECE (state binning); conformal coverage on held-out calibration/test split; selective accuracy at coverage level.

## Reliability
- pass@1, pass^k (τ-bench definition); reliability surface R(k, ε, λ) (ReliabilityBench).

## Decision quality
- Release-decision accuracy = agreement with pre-registered policy applied to ground truth; report **unsafe-promotion rate** and **false-block rate** separately (both costs), plus abstain rate (cf. AGO's unsafe-promotion/false-alarm framing ✔S).

## Cost
- $/confirmed defect; tokens/test; p50/p95 latency/test; throughput; human minutes per adjudicated item.

## Interval methods
Wilson/exact (Clopper–Pearson) or Bayesian beta for proportions; cluster-robust SEs for grouped items; paired bootstrap or McNemar for paired binary outcomes; avoid CLT at small n (Bowyer ✔S). Rule of three for zero-failure bounds.

## Implemented estimators (code ↔ definition; `qe/stats/`)
- `intervals.clopper_pearson(k, n)` — exact two-sided binomial interval (beta quantiles of Binomial CDF inversion). Conservative; coverage ≥ nominal.
- `bayes.beta_credible(k, n, prior)` — equal-tailed posterior interval, posterior Beta(a₀+k, b₀+n−k); default prior Jeffreys Beta(½, ½). Prior is a modelling choice and must be recorded with the result. Guarantee: nominal coverage *averaged over the prior*, not conditional on p.
- `cluster.cluster_rate([(k_g, n_g)])` — ratio estimator p = Σk/Σn, CR1 cluster-robust variance G/(G−1)·Σ(k_g − p·n_g)²/n², Student-t(G−1) interval clipped to [0,1]; reports design effect = Var_cluster / Var_binomial. Zero-variance cases fall back to Clopper–Pearson (`cluster_boundary_cp` over G clusters; `cluster_zero_variance_cp` over n items). Approximate for small G.
- `judge.rogan_gladen` / `judge.judge_corrected_rate` — θ = (q + Sp − 1)/(Se + Sp − 1) with Se/Sp from a **human-labelled** calibration set; interval from Monte-Carlo over Jeffreys-Beta posteriors of q, Se, Sp (seeded, deterministic). Draws with Se + Sp − 1 ≤ 0 are dropped and reported as `unidentified_fraction`. Assumes calibration items are representative of the evaluated population (untested here).
- `estimators.pass_hat_k_at(outcomes, k)` — τ-bench pass^k, mean over items of C(c,k)/C(n,k) (c passes of n trials); k=n gives the all-trials-pass fraction (`pass_hat_k`). `pass_hat_k_estimate` wraps k=n as a rate over items with a Clopper–Pearson interval (items are the unit).
- Property tests: `tests/property/test_stats_properties.py`; simulated-coverage tests in `tests/unit/test_stats_ext.py` (seeds fixed; these are simulation checks of the implementation, not claims about any LLM system).

## Not to be used without declared policy
Composite quality scores with invented weights; pass/fail thresholds not tied to a loss matrix.
