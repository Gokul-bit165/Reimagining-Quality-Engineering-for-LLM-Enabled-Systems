# 13 — Competitor and Prior-Art Analysis

**Limits of this analysis:** based on vendor docs pages, comparison articles and aggregator listings surfaced by search. **No source code was read**, so "source-level" claims are not made. Competitor-authored comparisons (e.g., LangSmith vs Braintrust, DeepEval vs RAGAS/TruLens, Giskard vs Garak/PyRIT) are **marketing** and are tagged as such. Humanloop was not investigated.

## Capability matrix
Legend: **P** = Proven/documented feature (docs or multiple consistent sources) · **V** = vendor-claimed, unverified · **X** = not found / not offered per sources read · **?** = not investigated

| Capability | LangSmith | Braintrust | Langfuse | Phoenix | RAGAS | DeepEval(+DeepTeam) | Promptfoo | TruLens | Inspect(+Petri) | MLflow |
|---|---|---|---|---|---|---|---|---|---|---|
| Trace capture | P | P | P (OTel) | P (OTel/OpenInference) | X (metrics lib) | P (`@observe`) | partial | P (OTel) | transcripts/logs | P (MLflow Tracing) |
| LLM-as-judge | P | P | P (num/bool/categorical, online) | P | P | P (50+ metrics) | P | P (feedback fns) | P (scorers) | P (`make_judge`, trace-aware, alignment to human feedback) |
| Synthetic test generation | ? | V (Loop) | X (datasets from traces/annotation) | ? | P (KG-based single/multi-hop) | P (Synthesizer: filter + evolve) | P (red-team plugins) | X | partial (Petri seeds) | ? |
| Automatic risk modeling from the app | X | X | X | X | X | X | X | X | X | X |
| Grounding/claim verification | P (evaluators) | P (scorers) | P (judge prompts) | P (RAG evals) | P (faithfulness etc.) | P | P | P (RAG triad) | via scorers | P (RetrievalGroundedness judge) |
| Security/red-team | partial | partial | X | X | X | P (DeepTeam) | **P** (50+ vuln types; MCP, memory poisoning plugins) | X | Petri (alignment audit), sandbox | X |
| Agent/workflow testing | P (agent evals) | P | traces | P | P (tool-call acc., goal acc.) | P (task completion, tool/argument correctness, plan adherence, step efficiency) | partial | P (trajectory metrics) | P (sandboxed agent evals) | P (agent-as-judge over traces) |
| Failure→regression | V (Engine auto-creates offline evals) | V (one-click trace→dataset; CI gates) | P (promote traces to datasets) | P (traces→datasets) | X | partial | P (CI) | X | X | P (datasets from traces) |
| Monitoring/online eval | P | P | P | P | X | via Confident AI | X | partial | X | P (production monitoring) |
| Release management/gates | V (CI) | V (CI/CD thresholds) | partial (experiments, alerts) | X | X | partial (pytest thresholds) | P (CI) | X | X | X |
| Structural/trace-assertion testing | X (as far as read) | X | X | X | X | partial (span-level metrics) | X | partial | X | partial (trace scorers) |
| Independent-evidence/heterogeneous verification | X | X | X | X | X | X | X | X | X | X |
| Calibrated uncertainty/conformal | X | X | X | X | X | X | X | X | X | partial (judge alignment ≠ conformal) |

(The "X" in rows for risk modeling, heterogeneous verification and conformal means *not found in the sources read*, not "proven absent". It is the single most important caveat for novelty claims.)

## Per-product notes (all ◐2 unless stated)
- **Langfuse** — acquired by ClickHouse (announced 16 Jan 2026); MIT core, self-hostable; LLM-judge on live traces, code evaluators (GA 28 May 2026 per its own page), experiments rebuilt as first-class (13 Apr 2026). Reviewers note judge calibration is buyer-owned work.
- **LangSmith** — offline/online evals, annotation queues, "Align Evals" to calibrate judges vs human feedback, **Engine** clusters production traces into issues and proposes fixes/evals (**LangChain marketing**, unverified).
- **Braintrust** — evals + CI gates; **Loop** AI assistant generates scorers/datasets and analyzes logs (**Braintrust marketing**; the comparison page is competitor-authored).
- **Arize Phoenix** — open-source (own license; patent notice in repo), OTel + OpenInference tracing, datasets/experiments, `phoenix-evals`; Arize AX is the commercial sibling with monitors/drift for ML.
- **RAGAS** — Apache-2.0 per a third-party page; RAG metrics (faithfulness, context precision/recall, noise sensitivity), agent metrics (tool-call accuracy/F1, goal accuracy, topic adherence), KG-based testset generation.
- **DeepEval/DeepTeam/Confident AI** — pytest-style; 50+ metrics; Synthesizer with filtration & evolution; red-team split into DeepTeam; cloud platform optional. Comparison tables on its site are self-authored.
- **Promptfoo** — OpenAI acquisition announced 9 Mar 2026; OSS (MIT) retained per statements; integration into OpenAI "Frontier" planned (◐2). Future governance of the OSS project is a **dependency risk** for anything built on it.
- **TruLens** — MIT; Snowflake-stewarded (TruEra acquired 2024); OTel-based; RAG Triad; agent trajectory metrics.
- **Inspect (UK AISI)** — dataset→solver→scorer; Docker sandboxing; 200+ pre-built evals. *License reported inconsistently (MIT vs Apache-2.0 across sources) — verify.* **Inspect Petri** (Meridian Labs + UK AISI; MIT) — auditor agent.
- **MLflow** — GenAI evaluate with scorers (built-in judges, custom judges via `make_judge`, code scorers), multi-turn judges, "Agent-as-a-Judge" over traces, human-aligned judges.
- **HELM / OpenAI Evals** — not examined.

## What is genuinely already available (do not claim as novel)
Tracing; judges; datasets; experiments; online evals; CI-style gates; synthetic Q&A generation from documents; RAG and agent metrics; red-team probe libraries; sandboxed agent evals; trace→dataset promotion; judge alignment to human labels.

## What I did not find in the products read
(1) Application-model-driven risk register generation; (2) coverage accounting that reports uncovered risk areas; (3) measured independence of verifiers (n_eff) and heterogeneous portfolios; (4) conformal/probabilistic release gates as a product feature (exists in research: AGO; arXiv:2608.12970); (5) automatic validity checking of generated test oracles with reported invalid-test rate; (6) outcome-verified security tests auto-harnessed onto arbitrary apps. These are **candidates to challenge in Phase 9**, not claims.
