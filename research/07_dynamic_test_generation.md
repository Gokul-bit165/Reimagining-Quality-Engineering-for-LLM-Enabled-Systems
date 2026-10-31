# 07 — Dynamic Test Generation

## What the market/literature already does (verified)
| System | Generation capability | Tag |
|---|---|---|
| **RAGAS** | Knowledge-graph (entities/themes/summaries) built from user documents → single-hop, multi-hop, abstract queries, persona/scenario generation; agent test-set generation page exists | ✔S (docs index) / ◐2 |
| **DeepEval Synthesizer** | goldens from docs / contexts / scratch / existing goldens; pipeline of input generation → **filtration** → **evolution** (increase complexity) | ◐2 (docs mirrored via blogs; deepeval.com docs seen in search) |
| **DeepTeam / Promptfoo / Garak / PyRIT / Giskard** | Attack-prompt generation; vulnerability taxonomies (Promptfoo: 50+ vuln types per a catalog page; Garak: 120+ categories per Giskard) | ◐2 |
| **Braintrust Loop; LangSmith Engine** | Vendor says: generate scorers/datasets from production data; cluster production failures and auto-create offline evals | ◐2 **vendor marketing — unverified** |
| **S-Eval** (arXiv:2405.14191) | Risk-taxonomy-driven generator + test selection; 220k prompts (safety only) | ✔S |
| **Petri / Inspect Petri** | Auditor agent runs multi-turn probes from seed instructions | ✔S |
| **AJAR** (arXiv:2601.10971) | Auditor agent orchestrates multi-turn jailbreak algorithms as MCP services with rollback/tool simulation | ✔S |
| **AutoDojo** (arXiv:2606.15057) | Adaptive IPI optimization against a given defense | ✔S |

**Conclusion:** "generate tests from documents" and "generate attacks from a taxonomy" are **solved at the engineering level**. Not found in this session: tests generated from an *inferred application model* (tools, permissions, workflows, data sensitivity) with **coverage accounting** and **oracle validity checking** as first-class parts.

## Adaptive lifecycle (mandate steps 1–12) → what supports each
| Step | Supported by | Gap |
|---|---|---|
| 1–2 understand / extract capabilities | probing + traces (`06`) | no validated automatic method |
| 3–4 failure modes, rank risks | OWASP LLM/Agentic Top 10 as taxonomy ◐2; S-Eval taxonomy ✔S | likelihood/impact estimation unvalidated |
| 5–6 scenarios + variations | RAGAS KG, DeepEval evolution, metamorphic relations | variation *diversity* not measured by these tools (as far as read) |
| 7–9 execute/collect/classify | all platforms | classification reliability = judge reliability |
| 10 uncovered risk areas | — | needs a coverage model |
| 11 tests from failures | LangSmith/Braintrust (claimed); AJAR/AutoDojo for attacks | minimization & flakiness control unknown |
| 12 preserve regression tests | Langfuse datasets from traces ✔(docs via ◐2) | admission criteria (is it a *real*, *stable* failure?) |

## Answers to the mandate's questions (evidence-bounded)
- **Risk coverage:** define against an explicit risk register: coverage = Σ over (risk × capability × access-path) cells with ≥1 *valid executed* test whose oracle was validated. It measures coverage of *our model*, so the model itself must be audited (compare to independently authored register in `17`). No standard found.
- **Redundancy:** cluster by embedding and by **trace signature** (spans/tools/chunks touched); retain one per cluster unless failure-revealing. Trace signature avoids rewarding paraphrases that exercise the same path.
- **What to test next:** bandit/Bayesian-optimization style allocation toward cells with high posterior failure probability × impact × cost⁻¹. Hypothesis; adaptive attack search (Nasr et al., ✔S) is the strongest evidence that feedback-driven search beats fixed sets.
- **Uncertainty-guided generation:** use disagreement among *heterogeneous* verifiers as a "this is a hard/informative case" signal (to be validated; see `03` H-het).
- **Expensive tests:** multi-turn adversarial and agentic runs cost more; use staged funnel — cheap deterministic/metamorphic first, adaptive search budgeted by remaining risk mass.
- **Mutations for diversity:** apply semantics-preserving and semantics-changing mutations; *validate relation correctness* before using as oracle.
- **Rejecting bad generated tests (critical):** (i) schema/executability check; (ii) expected behavior derived from **source-of-truth artifacts** (policy docs, corpus, tool schema), not from the generator's belief; (iii) independent re-derivation by a different method/model; (iv) human audit of a sampled stratum with measured invalid-test rate; (v) conformal risk control on oracle acceptance (as in arXiv:2608.12970 ✔S). Measure **test validity rate** as a reported metric.
- **Budget allocation:** treat as sequential experimental design; report cost per confirmed distinct defect.

## Autonomous vs conventional generation
| Dimension | Conventional (static set / template) | Autonomous (feedback-driven) |
|---|---|---|
| Coverage of unknown failures | Low | Potentially higher (attacks: demonstrated; quality: **unproven**) |
| Reproducibility | High | Needs seeds, logged lineage, replay |
| Cost | Low | Higher, variable |
| Invalid-test risk | Low (human-vetted) | Higher; needs oracle validation |
| Flakiness | Controlled | Must be measured (pass^k admission) |

Net: autonomy buys discovery but costs reproducibility and oracle risk. A defensible design keeps a **frozen** regression tier and a **discovery** tier whose findings are promoted only after validation.
