# 11 — Statistical Reliability

## Principles (supported)
1. **Evals are samples from a super-population of prompts**; report standard errors/CIs (Miller, arXiv:2411.00640 ✔S). Use **clustered standard errors** when items are grouped (shared documents, templates, personas) — clustered SEs can exceed naive ones by >3× in his examples. Prefer **paired** comparisons between versions; resample answers per question and use next-token probabilities where available to reduce variance.
2. **Don't trust CLT intervals at small n** (Bowyer, Aitchison, Ivanova, arXiv:2503.01747, position paper ✔S): use exact/Bayesian intervals; CLT coverage fails below a few hundred points, and per-subtask sets are small. Release gating is often exactly this regime.
3. **Judge imperfection must be modelled**, not ignored: estimate judge TPR/FPR on a human-labelled calibration set and correct (arXiv:2601.20913; arXiv:2511.21140 ✔S).
4. **Beta-binomial / Bayesian gates** give probabilistic regression risk, e.g., P(p_new < p_old − δ), per stratum (AGO, arXiv:2610.01218 ✔S) — δ and risk appetite are **policy inputs**.
5. **Repeated-run reliability**: pass^k = probability all k trials succeed (τ-bench ✔S); report pass@1 and pass^k together; stochastic agents can look fine at k=1 and poor at k=8.

## Mathematical facts usable without inventing thresholds
- 0 failures in n independent trials → one-sided 95% upper bound on failure rate ≈ 3/n ("rule of three"; illustration: n=100 → ≈3%). This bounds *sampled-distribution* failure, not unseen inputs.
- For paired binary outcomes, power depends on the number of **discordant pairs**; plan sample size from expected discordance, not overall accuracy.
- Kish effective sample size n_eff = (Σw)²/Σw² (used by Kohli to quantify judge-panel redundancy, arXiv:2605.29800 ✔S).

## Metric definitions (defensible, require ground truth)
| Metric | Definition | Objectively measurable? |
|---|---|---|
| Failure-detection precision | TP/(TP+FP) at the **defect** level (deduplicated by root cause) | Yes, with seeded/adjudicated ground truth |
| Recall | TP/(TP+FN) over known defects | Only over *known* defects; unknown-defect recall is unmeasurable |
| FPR / FNR | FP/(FP+TN), FN/(FN+TP) | As above |
| Hallucination-detection accuracy | agreement with human-adjudicated claim labels | Needs expert adjudication |
| Grounding verification accuracy | per-state confusion matrix over the six states | Expert adjudication |
| Citation correctness | deterministic: ID resolves + span supports claim (support part needs adjudication) | Partly |
| Attack success rate | outcome oracle fired / attempts, **at stated budget & attacker class** | Yes (sandbox) |
| Risk coverage | fraction of risk-register cells with ≥1 valid executed test | Measures our model, not reality |
| Regression coverage | fraction of past validated failures with a live regression test | Yes |
| Evaluator agreement | Cohen's κ (2 raters) / Krippendorff's α (many, missing data); n_eff for panels | Yes |
| Calibration error | ECE (binning-sensitive), Brier, reliability diagram | Yes |
| Release decision accuracy | agreement with a **pre-registered policy applied to ground truth** | Only vs. that policy |
| Cost / latency / throughput | $ per confirmed defect; p50/p95 per test; tests/hour | Yes |

## What needs expert adjudication
Whether a claim is supported/unverifiable; severity and business impact; whether a refusal was appropriate; whether a generated test's expected behavior is valid. Plan: ≥2 blinded annotators + adjudicator who has **not** seen system outputs' aggregate results (note the CMU JEV paper's limitation: single annotator, adjudicator saw aggregates — arXiv:2609.26550 ✔P). Report κ/α and the adjudication protocol.

## Do-not list
No fixed accuracy cut-offs (e.g., "≥95% = release") without a stated loss function and calibration; no composite score with invented weights — if aggregation is required, derive weights from a **declared policy/stakeholder loss matrix** and show sensitivity analysis; no point estimates without intervals; no benchmark score presented as release confidence.

## Drift statistics
Silent provider updates are widely reported by practitioners, but figures such as "67–91% of deployments drift within 90 days" appear only in blogs (◐2) with unclear provenance — **excluded as evidence**. Use changepoint/sequential tests on pinned canary probes and behavior fingerprints; validate false-alarm rate on a no-change control period (hypothesis; method to be tested).
