# 03 — Advanced Evaluation Architectures

Format per mandate: **Problem → Hypothesis → Mechanism → Data flow → Evaluation → Results → Limitations → Feasibility.** Only architectures with evidence are expanded; others are marked as untested.

## 1. Confidence-gated cascade (cheap decision model → escalate to strong judge)
- **Problem:** judging at volume is slow/expensive.
- **Hypothesis:** a first-stage judge's confidence identifies where it is trustworthy; escalate the rest.
- **Mechanism:** stage 1 returns label probabilities; accept if max-prob ≥ τ else escalate (JEV paper, arXiv:2609.26550 ✔P; also arXiv:2608.12970 uses a conformal-risk-controlled cascade ✔S).
- **Evidence:** JEV paper — threshold chosen on 96 pilot pairs, tested on 510 held-out; cascade 92.5% vs strong judge 93.1% while accepting 53.7% of pairs (reported). Same paper: weakens on style-adversarial pairs and reference-free prose; one proprietary model version; comparisons not compute-matched.
- **Counter-evidence:** arXiv:2610.20634 ✔P (abstract): on 495 LLM-AggreFact claims, accuracy tie at ~187× cost gap, **but** the cheap model accepted more unsupported claims (23.2% vs 14.1%), and **random escalation at the same budget did as well as confidence-gated escalation** → savings came from the escalation *rate*, not the confidence signal.
- **Feasibility:** engineering integration; the *routing signal's value* is an open empirical question per-task.

## 2. Judge panels / ensembles
- **Hypothesis:** diverse judges → near-independent errors → majority/weighted vote beats single judge.
- **Evidence against (for LLM-only panels):** Kohli (arXiv:2605.29800 ✔S): 9 judges ≈ 2 independent votes; best single judge ≥ panel; smarter aggregation doesn't close the gap.
- **Partial remedy:** CARE (ICML 2026) models shared confounders; still operates on LLM judge scores.
- **Implication:** *Count judges by effective sample size, not by number.* Any ensemble claim must report n_eff on that task.

## 3. Heterogeneous verifier portfolio (hypothesis, untested here)
- **Hypothesis H-het:** combining *different method classes* — deterministic checks (string/number/citation-existence), retrieval-assisted NLI/entailment models, small fine-tuned detectors, decision-only models, and generative judges — yields lower error correlation (higher n_eff) than the same number of generative judges.
- **Why plausible:** different inductive biases; some checks are exact. **Why uncertain:** all neural verifiers share training-data and shortcut biases; I found no paper that measured n_eff across method classes. (Related: HALT-RAG "calibrated NLI ensembles" is mentioned in arXiv:2512.15068's related work ✔S — not read.)
- **Test:** compute pairwise error correlation / Kish n_eff on a human-adjudicated claim set across method classes vs within-class (see `17`).

## 4. Claim-level evidence pipelines (decompose → retrieve → verify)
FActScore/RAGAS/RAGChecker/MetaRAG family. MetaRAG (arXiv:2509.09360 ✔S) adds metamorphic variants (synonym → expect entailed; antonym → expect contradicted) checked against retrieved context. Limits: decomposition errors propagate; verification quality bounded by the verifier; reference-free variants only test *consistency with retrieved context*, not truth.

## 5. Critic–verifier / debate
Evidence is negative-to-mixed for plain debate (arXiv:2502.08788 ✔S); heterogeneity helps. Treat debate as unproven for judging; consider only with different base models and a deterministic referee.

## 6. Conformal / calibrated abstention
Conformal prediction gives distribution-free coverage under exchangeability (✔S: arXiv:2403.01216 API-only CP; arXiv:2407.00499 ConU; arXiv:2604.13991; arXiv:2512.15068). Applied to judge *scores* (arXiv:2604.15302) and to cascades (arXiv:2608.12970). Limits: exchangeability between calibration and deployment data is exactly what drift breaks; marginal (not conditional) guarantees; needs labelled calibration data per task/domain.

## 7. Formal / runtime verification
Not investigated in this session. Plausible role: deterministic *invariants over traces* (e.g., "tool X never called without prior approval event"). Structural-testing paper (arXiv:2601.18827) uses assertions over traces — the practical form of this idea. Temporal-logic specification mining for LLM apps: **no evidence gathered**.

## 8. Self-consistency / repeated-run measures
Cheap, black-box, strongly supported as a reliability signal (τ-bench pass^k ✔S; ReliabilityBench ✔S; arXiv:2602.21368 ✔S). Measures stability, not correctness.

## Summary table
| Architecture | Evidence level | Main risk |
|---|---|---|
| Cascade | Mixed; one favorable (partly vendor-adjacent), one skeptical | Gain may be budget, not signal |
| LLM judge panel | Negative on independence | False sense of redundancy |
| Heterogeneous portfolio | **Hypothesis** | Shared biases; unmeasured |
| Claim-level pipeline | Established, with known weaknesses | Error propagation |
| Debate | Negative/mixed | Compute without gain |
| Conformal abstention | Strong theory; applied results young | Exchangeability under drift |
| Runtime assertions | Practical (trace testing) | Needs instrumentation |
