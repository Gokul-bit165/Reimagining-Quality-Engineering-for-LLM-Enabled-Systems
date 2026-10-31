# 18 — Research Gaps (and a skeptical novelty review)

"Gap" here means: **not found in what I read**. Search coverage was partial; every gap is a claim to be attacked in a deeper prior-art pass.

## Gap matrix
| Research area | Existing approaches | Limitations | Unsolved technical problem | Potential contribution |
|---|---|---|---|---|
| Verifier independence | LLM panels; CARE; cascades | 9 judges ≈ 2 votes (Kohli); cascade gain may be budget (arXiv:2610.20634) | Does method-class diversity raise n_eff, and by how much? | Measured, independence-aware verification portfolio |
| Oracle validity of generated tests | Filter/evolve (DeepEval); conformal oracle cascade (arXiv:2608.12970) | Invalid-test rate rarely reported | Standardized test-validity estimation and rejection | Validity gate with reported invalid-test rate |
| Outcome-verified security on arbitrary apps | AgentDojo (fixed env); AutoDojo; PyRIT/Promptfoo | Need hand-built environments; judge-based verdicts | Automatic sandbox/environment synthesis from tool schemas | Generalized outcome oracles |
| Structural coverage & app model | OTel trace testing (arXiv:2601.18827); LeCov (white-box) | Coverage criteria not validated vs defects; app graph extraction manual | Framework-agnostic app model from traces/repo; coverage-guided generation | Coverage definitions + empirical validation |
| Failure localization | RAG diagnosis (RAG-X, Doctor-RAG); substitution practice | Mostly RAG; needs grey/white-box | Black/grey-box localization across RAG+tools+agents | Intervention-based localizer + accuracy benchmark |
| Release decisions under uncertainty | Quality-gate papers (2026) | Single-app case studies; thresholds are policy choices | Cross-app validation of decision rules; loss-aware policy elicitation | Decision-theoretic gate with abstention |
| Regression intelligence | Trace→dataset (platforms); vendor "auto-regression" claims | Flakiness, minimization, admission criteria unreported | Minimizing and admitting stochastic failures | Reproducible regression compiler |
| Drift attribution | Practitioner canaries; changepoint tools | Evidence is blog-level | Attribute drift to model/prompt/corpus/tool via differential tests | Attribution method + benchmark |
| System-level benchmark for app testing | Task benchmarks (τ-bench), RAG sets | No benchmark of *testing tools* on seeded-defect apps | Open seeded-defect benchmark with ground truth | Community benchmark |

## Skeptical review: "Try to disprove our innovations"
| Candidate claim | Closest existing work found | Verdict |
|---|---|---|
| "Release recommendation (R/CR/Reject) from automated evaluation" | Maiorano PROMOTE/HOLD/ROLLBACK gate (arXiv:2603.15676); readiness harness (arXiv:2603.27355); AGO four-state + beta-binomial gate (arXiv:2610.01218); governance gates (arXiv:2604.27789) | **Not novel.** Differentiator can only be breadth, validation across apps, or evidence quality — not the concept |
| "Dynamic test generation from documents" | RAGAS, DeepEval, S-Eval | **Not novel** |
| "Automated red teaming / adaptive attacks" | PyRIT, Promptfoo, AJAR, AutoDojo, Petri | **Not novel**; novelty only in outcome-harness synthesis for arbitrary apps |
| "Trace-based structural testing" | arXiv:2601.18827 + OSS | **Not novel**; automation of model extraction remains open |
| "Judge ensembles for reliability" | Many; but evidence shows limits | Claiming ensembles add reliability is **contradicted** by n_eff results |
| "Confidence-gated cascade saves cost" | JEV papers; arXiv:2608.12970 | Savings may not come from the confidence signal (arXiv:2610.20634) |
| "Convert failures to regression tests" | Langfuse/Braintrust/LangSmith (vendor-described) | **Not novel** at concept level; minimization/flakiness admission unproven |
| "Independent evidence verification via heterogeneous methods" | Hybrid claim pipelines; HALT-RAG (mentioned, unread) | **Possibly partially covered**; the *measurement of independence* looks open |
| "Coverage of risk register with accounting of uncovered risk" | S-Eval taxonomy; Chunk Coverage (seminar abstract) | Plausibly open for app-level; verify |

## Weak assumptions in this research
1. Search-engine recall: arXiv listings surfaced are those that ranked, not an exhaustive scan; many 2026 papers are single-author or under review.
2. Many sources are preprints; several are vendor-adjacent. Peer review is confirmed only for CARE (ICML 2026 page), Kohli (NeurIPS 2026 listing), and the ASE'26 paper.
3. Competitor capabilities rely on docs and secondary reports; absence of a feature in my notes ≠ absence in product.
4. Practitioner statistics about drift prevalence were excluded as unverifiable.
5. Foundational benchmarks/papers marked ○R may contain errors in my recollection.

## Separation of novelty types (for later positioning)
- **Engineering novelty:** capability negotiation across access levels; durable, replayable orchestration; evidence ledger with lineage.
- **Research novelty (hypotheses):** measured verifier independence across method classes; test-validity estimation; app-model→coverage→generation loop; regression minimization with stochastic admission; drift attribution.
- **Product differentiation:** integrated, access-aware, evidence-first workflow with explicit "insufficient evidence" outcomes — differentiation only if it is *measurably* better in `17`.
