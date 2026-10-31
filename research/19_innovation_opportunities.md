# 19 — Innovation Opportunities (hypotheses, not features)

Each is a **testable hypothesis** with its closest prior art. Difficulty and resources are my estimates (engineering judgment), not measured.

## O1 — Independence-aware evidence adjudication
- **Supporting research:** Kohli (arXiv:2605.29800), CARE (ICML 2026), MAD critique (arXiv:2502.08788), cascade evidence (arXiv:2609.26550, 2610.20634).
- **Closest existing:** LLM-judge panels; FaithJudge; calibrated-NLI ensembles (HALT-RAG, unread).
- **Technical difference:** method-class diversity + information isolation + reported n_eff and error-correlation, with abstention routed to humans.
- **Why existing is insufficient:** panels of same-class judges have heavily correlated errors.
- **Hypothesis H1:** a portfolio spanning ≥3 verifier classes has strictly higher n_eff than an equally sized LLM-only panel on claim-support tasks, and yields better selective accuracy at matched cost.
- **Validation:** `17` §4 independence experiment. **Difficulty:** medium. **Resources:** adjudicated claim set (~hundreds of items, size set by pilot variance), several verifier backends.
- **Global relevance:** high — every eval pipeline uses LLM judges. **OSS contribution:** diagnostic toolkit + dataset of adjudicated claims (licensing permitting).

## O2 — Outcome-verified security tests via environment synthesis
- **Supporting:** arXiv:2510.09023, AgentDojo, AutoDojo.
- **Closest:** AgentDojo (hand-built envs); PyRIT/Promptfoo (often judge-scored).
- **Difference:** derive a sandbox + canary/state-diff oracles automatically from tool schemas and permissions.
- **H2:** for a held-out set of tool-using apps, an auto-synthesized harness yields outcome verdicts that agree with hand-built oracles at high rate (target rate to be pre-registered, not assumed).
- **Validation:** compare to manually authored harnesses on ≥N apps. **Difficulty:** high (stateful tools, auth, side-effects). **Relevance:** high. **OSS:** harness generator + conformance suite.

## O3 — App-model → structural coverage → coverage-guided generation
- **Supporting:** arXiv:2601.18827, RAG-X, Doctor-RAG, LeCov (white-box).
- **Closest:** OTel trace tests; Chunk Coverage (seminar abstract only).
- **Difference:** automatically built, uncertainty-annotated app model driving coverage criteria across retrieval/tool/state.
- **H3:** coverage under the proposed criteria correlates with seeded-defect detection better than input-diversity or random generation at equal budget.
- **Validation:** correlation + ablation on seeded apps. **Difficulty:** medium-high. **OSS:** open coverage-criteria spec.

## O4 — Test-oracle validity estimation
- **Supporting:** arXiv:2608.12970 (conformal oracle cascade), `07` rejection steps.
- **Closest:** DeepEval filtration; REAG oracles.
- **Difference:** report an *invalid-test rate with CI* per suite and gate release evidence on it.
- **H4:** source-of-truth-derived oracles + independent re-derivation reduce invalid-test rate vs generator-only oracles.
- **Validation:** human audit of sampled tests across arms. **Difficulty:** medium. **Relevance:** high.

## O5 — Stochastic regression compilation
- **Supporting:** τ-bench pass^k; ReliabilityBench.
- **Closest:** trace→dataset promotion (Langfuse, Braintrust per vendor).
- **Difference:** minimize a failing case (prompt/context/tool-state) and admit it only if reproducible under pass^k with known flake rate.
- **H5:** minimized, admitted cases have lower flake rate and higher re-detection after a fix than raw promoted traces.
- **Validation:** fix-and-replay experiments on seeded apps. **Difficulty:** medium.

## O6 — Decision-theoretic release gate with abstention
- **Supporting:** arXiv:2610.01218, 2603.15676, 2608.12970, Miller, Bowyer.
- **Closest:** same (prior art!).
- **Difference (only if shown):** cross-app validation, explicit loss matrix elicitation, sensitivity analysis, and "insufficient evidence" as a first-class outcome.
- **H6:** policy-declared Bayesian gates yield lower unsafe-promotion at matched false-alarm cost across ≥3 app types (AGO reports one setting of this).
- **Difficulty:** medium. **Novelty:** low–medium — be candid.

## O7 — Drift attribution by differential controlled substitution
- **Supporting:** practitioner reports (◐2) only; Kohl mocking; `05` differential testing.
- **Closest:** none found at research level.
- **H7:** swapping one component at a time (model, prompt, corpus snapshot, tool schema) against a pinned baseline attributes behavioral change to the correct component more reliably than aggregate quality-metric diffs.
- **Validation:** inject known changes into seeded apps. **Difficulty:** medium. **Relevance:** high (silent provider updates).

## O8 — Open evidence-record protocol and benchmark
- **Supporting:** OTel GenAI conventions (unstable), Inspect log formats (not reviewed).
- **Closest:** OTel/OpenInference; Inspect.
- **Difference:** a framework-agnostic schema for claim-level evidence, verdict provenance, and decision lineage; plus a seeded-defect benchmark of *testing tools* (none found).
- **Risk:** standards churn; adoption. **OSS:** high value if neutral.

## Priority view (no selection)
Highest scientific value/uncertainty: O1, O2, O3. Best near-term de-risking experiments: O1 (cheap), O4. Lowest novelty: O6, parts of O5.
