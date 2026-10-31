# 17 — Scientifically Defensible Benchmarking Plan

Goal: show improvements come from the **method**, not from using a stronger LLM; make the protocol reproducible by another team. Plan only — nothing run.

## 1. Experimental units: seeded-defect sandbox applications
Build ≥4 app families (chatbot, RAG assistant, multi-agent, tool assistant) × ≥2 implementation stacks × ≥2 base LLM families. Defects are injected via a **defect manifest** (ID, type, location, trigger conditions, severity) written by a team **separate** from the tool team; the manifest is the ground truth.

Seeded classes (from mandate): fabricated claims; invalid citations; contradictory answers; retrieval failures (stale/missing/poisoned docs, bad chunking); prompt injection susceptibility; unauthorized tool attempts; memory contamination; wrong agent transitions; incomplete task execution; model-behavior drift (swap model/prompt version).
Design for **validity**: (a) defects of varying subtlety and trigger rate (incl. low-trigger-rate), (b) *defect-free controls* (to estimate false positives and release-accuracy), (c) **held-out defect families** never seen during development, (d) a **natural-defect track**: real open-source RAG/agent apps with human-labelled failures, since seeded defects can be unrealistically detectable.

## 2. Arms (baselines vs proposed)
1. Static prompt evaluation (fixed hand-written set). 2. Rule-based evaluation. 3. Single LLM judge. 4. Judge ensemble (k judges). 5. Existing RAG-eval frameworks (e.g., RAGAS, DeepEval) with default settings. 6. Existing agent-eval/red-team systems (e.g., Promptfoo, PyRIT, Inspect+Petri) with default settings. 7. Adaptive test generation (no hybrid verification). 8. Hybrid evidence verification (static tests). 9. Full candidate (each of A/B/C).
Fairness: give every arm the **same access level**, **same test-execution budget** (queries, tokens, wall-clock, $) and report cost; tune each baseline's reasonable defaults with the same effort.

## 3. Measures (definitions in `11`)
Detection precision/recall/FPR/FNR at **defect level** (dedupe by root cause); grounding-verification confusion matrices over the six states; security: ASR at stated attacker budget + prevention (outcome oracle) rate; **test-generation novelty** (fraction of confirmed defects found by generated tests that no baseline static test found; plus trace-signature diversity); **risk coverage** vs an *independently authored* risk register; **localization accuracy** (top-1 component vs manifest); regression detection (injected regressions caught across versions); release-decision accuracy (agreement with pre-registered policy applied to the manifest); latency/cost per confirmed defect.

## 4. Separating architecture from model strength
- **Fix the underlying LLM per comparison** (same judge model in all judge-using arms) and repeat over ≥2 independent model families; report architecture effect *within* model.
- **Cross-model ablation:** run the full system with a weaker and a stronger judge; claim architecture value only if the advantage persists when baselines get the stronger model (i.e., baselines also upgraded).
- **Component ablations:** remove, one at a time: deterministic layer, entailment layer, heterogeneity (replace with same-class judges), conformal abstention, validity gate, adaptive feedback, grey-box signals.
- **Budget-matched controls:** random-escalation vs confidence-gated (cf. arXiv:2610.20634 ✔P), random vs guided test selection.
- **Judge-independence experiment (H-het):** on a human-adjudicated claim set, compare n_eff and pairwise error correlation for {k LLM judges} vs {k method-diverse verifiers}.

## 5. Statistics
Pre-register hypotheses, metrics, analysis plan, exclusion rules. Unit of analysis = defect/test item with **clustered SEs** by app/document/template (Miller ✔S). Small-n intervals: exact or Bayesian (Bowyer ✔S). Paired comparisons across arms on identical items; McNemar-style for discordant pairs; multiple-comparison control across metrics. **Repeated runs** (≥ several seeds; number set by pilot variance, not guess) to separate system variance from method effect. Judge-correction using human-labelled calibration subset (arXiv:2601.20913; arXiv:2511.21140 ✔S).

## 6. Human adjudication
≥2 blinded annotators per item + independent adjudicator unaware of arm identity and aggregate scores; report κ/α; sample stratified by verdict state, severity and disagreement; measure annotator time for cost accounting.

## 7. Generalization
Cross-model (train/develop on families X, test on Y); cross-application (develop on two app types, test on a third held-out type); cross-stack (LangGraph-like vs custom) — to show the integration layer does not overfit.

## 8. Threats to validity (listed up front)
Seeded-defect realism; contamination of verifiers by public datasets (e.g., HHEM trained on RAGTruth train ✔S); manifest author bias; judge drift between runs (pin versions, store outputs); proprietary dependencies (e.g., hosted Jev) harming reproducibility → require an open backend for the reproducible protocol; self-evaluation bias if the same LLM family generates and judges.

## 9. Reproducibility package (target)
Defect manifests + app code, container images, seeds, recorded LLM I/O (replay mode), prompts, analysis scripts, adjudication guidelines and labels, pre-registration, cost ledger. Licensing of included datasets must be cleared (`12`).

## 10. What a "win" would and would not show
Would show: higher defect-level recall at equal precision/cost on held-out families, better localization, calibrated abstention. Would **not** show: that the tool predicts production incidents (needs longitudinal field study), or that release recommendations lower real-world harm.
