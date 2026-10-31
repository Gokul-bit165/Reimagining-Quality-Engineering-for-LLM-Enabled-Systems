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

## Not to be used without declared policy
Composite quality scores with invented weights; pass/fail thresholds not tied to a loss matrix.
