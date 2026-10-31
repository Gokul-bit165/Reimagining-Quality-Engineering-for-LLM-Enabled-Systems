# 23 — Reverse-Engineering the Three Repos (+ what REA can and cannot do here)

Method: shallow clones (`--depth 1`) read statically — file trees, class/function signatures, module docstrings, LICENSE files, pyproject dependencies. **Nothing from these repos was executed.** All findings are ✔P (read from the files) unless marked. "Latest commit" = head commit date in the clone; shallow clones cannot show commit frequency, so **no activity trend is claimed** (an earlier remark in this session about "commit counts" was an artifact of shallow cloning and is retracted).

## 0. REA (morluto/rea) — what it is, and why I could not run it
- **What it is:** "Reverse Engineer Anything" — an MCP server + CLI (`rea-agents` on npm, MIT) giving agents evidence-backed analysis tools for native binaries (via Hopper/Ghidra/IDA), JS/Electron apps, .NET, APKs, websites (browser observation), HAR captures, process behavior, etc. Every result carries **Evidence and stated limitations**. Needs Node 22.x ≥ 22.23.4 / 24.x ≥ 24.22.1 / 26.12.1+.
- **Fit to these three targets:** poor for *source analysis* — all three are open-source Python; REA's strength is closed artifacts. Reading the source directly is the right tool, which is what this document does.
- **Where REA *does* fit our product (hypotheses to try on your machine):**
  1. **Black-box web-app → sandbox environment.** `rea environment-build session.har ./env` turns a recorded HAR into an AgentEnv-runnable MCP environment whose reads/writes answer from recorded evidence, supporting writes **only when the capture confirmed their effect** (statuses such as `unconfirmed`, `incomplete-entities`). This is a real, shipped answer to part of research gap O2 (environment synthesis for outcome oracles), with explicit fidelity limits. Needs AgentEnv + Docker. **Unverified by me: whether the environments are faithful enough to serve as security-test oracles.**
  2. **Inspecting target apps without source** (JS/Electron routes, IPC, tool inventories) to seed the app model (`06`).
  3. **Design pattern:** results = claim + evidence + limitations. Adopt for our evidence ledger.
- **Why it did not run here:** `npx rea-agents` failed with DNS `ENOTFOUND registry.npmjs.org`. The session's proxy status lists the npm registry in its no-proxy list and there is no direct route. I did not bypass the proxy. Run it locally (Claude Code on your machine) — the master prompt includes a check step.
- **Safety:** REA runs/observes targets with *your* permissions; point it only at sandboxes. Per its own docs, acquire the package from a trusted directory outside the target project.

## 1. openai/evals — MIT, © 2023 OpenAI. Head commit 2026-04-14.
**Size:** 353 Python files, ~46k LOC, 463 registry eval YAMLs. README now points users to the hosted OpenAI Dashboard Evals.

**Core abstractions (worth copying as *ideas*, not as a dependency):**
| Abstraction | Where | Pattern |
|---|---|---|
| `CompletionFn` (Protocol: `__call__(prompt, **kw) -> CompletionResult`) | `evals/api.py` | The *system under test* is any callable returning completions — a clean adapter seam (OpenAI, LangChain chain, retrieval, CoT wrappers in `completion_fns/`). |
| `Eval` / `SolverEval` (`eval_sample`, `run`, `eval_all_samples`) | `evals/eval.py` | Per-sample evaluation with seeded RNG and thread-pool execution. |
| `Recorder` event log | `evals/record.py` | Typed events — `match`, `sampling`, `function_call`, `cond_logp`, `pick_option`, `metrics`, `error` — to Local JSONL / HTTP / DB recorders. A primitive evidence log. |
| `Registry` (YAML for evals, completion_fns, solvers, eval_sets, modelgraded specs) | `evals/registry.py` | Declarative, extensible suites with registry paths. |
| Model-graded specs | `registry/modelgraded/*.yaml`, `elsuite/modelgraded/` | Judge = prompt template + **closed choice set** (e.g., fact.yaml uses choices A–E) → choice-constrained, parseable verdicts (same idea as decision-only judges). |
| `Solver` abstraction | `evals/solvers/` | Agent scaffolds (memory, nested, postprocessors) decoupled from tasks. |
| `elsuite/` | e.g., `bugged_tools`, `error_recovery`, `sandbagging`, `steganography`, `make_me_pay`, `multistep_web_tasks`, `self_prompting` | A library of agent/safety scenario ideas — **mine for seeded-defect and scenario inspiration** (not for scoring). |

**Weaknesses for our purposes:** evaluates *models/solvers* on datasets, not *applications* with traces/retrieval records/tool state; no coverage model; heavy dependency set (langchain, datasets, docker, flask, gymnasium, chess, …); registry data in Git-LFS; python ≥3.9. **Verdict:** borrow `CompletionFn`-style adapter, JSONL event vocabulary, closed-choice judge specs and scenario ideas; **do not depend on it.**

## 2. confident-ai/deepeval — Apache-2.0. Head commit 2026-10-29.
**Size:** 1,155 Python files, ~213k LOC; also a TypeScript package, a setup wizard, Claude-oriented `skills/`, and a `sqlite` store. Version/layout seen: `deepeval/{metrics, synthesizer, tracing, test_case, dataset, models, evaluate, simulator, integrations, openai_agents, sqlite_store, telemetry, plugins, optimizer, voice, ...}`.

| Area | Findings |
|---|---|
| **Metrics** (`metrics/`, ~198 files, ~31k LOC) | RAG: faithfulness, answer relevancy, contextual precision/recall/relevancy, hallucination, summarization. Agent: task completion, tool correctness, argument correctness, step efficiency, plan quality/adherence, goal accuracy, **`tool_permission`** (deterministic allowlist/denylist policy check on called tools — denial wins; independent of task success), **`agent_loop_detection`**, MCP metrics. Safety: bias, toxicity, PII leakage, misuse, non-advice, role violation. Custom: G-Eval, DAG, conversational variants. Base classes: `BaseMetric.measure/a_measure/is_successful`, `BaseConversationalMetric`, `BaseArenaMetric`. |
| **Jev integration** | `metrics/jev_eval/` (**`JevEval`**, `ConversationalJevEval`): decision points defined as Noul/Score/Choice questions sent to TypeSafe's Jev via `TypeSafeModel(DeepEvalBaseSystemOneModel)`; weighted mean of mapped answers; reasons are deterministic text built from answers + confidence; can evaluate an agent trace. **Implication:** DeepEval already offers Jev as an optional backend through a provider interface (`DeepEvalBaseSystemOneModel`) — we can consume Jev through that seam without coupling to it. Requires TypeSafe access (proprietary). |
| **Synthesizer** | `synthesizer/synthesizer.py`: `generate_goldens_from_docs / contexts / scratch / goldens` (+ async); chunking; filtration/evolution templates. |
| **Tracing** | `tracing/`: `@observe` decorator, `Observer`, `TraceManager`, OTel exporter (`tracing/otel/`), integrations/patchers (e.g., `openai_agents`). Span-level metrics attach to components. |
| **Red teaming** | `red_teaming/` is a README stub: moved to **DeepTeam** (separate repo; **not ingested**). |
| **Simulator** | `simulator/` conversation/user simulation (multi-turn). |
| **Telemetry** | `telemetry/` (events, identity, runtime); **on by default**; opt out `DEEPEVAL_TELEMETRY_OPT_OUT=1`. Anonymous identity stored once per machine. |
| **Platform coupling** | `confident/` client → Confident AI cloud (optional). |

**Risks:** very large surface and fast churn (breaking changes likely); metrics are LLM-judge-heavy (inherit correlation/injection issues, `03`); telemetry default-on; repo root contains stray scratch files (`a.py`, `b.py`, `c.py`) — a hygiene signal, not a blocker.
**Verdict:** best **verifier/metric supplier and trace vocabulary**. Use behind a port (`VerifierPort`) with pinned versions, telemetry disabled, never as our core data model.

## 3. ragas (github.com/vibrantlabsai/ragas) — Apache-2.0. Head commit 2026-02-23.
(The repo appears under the `vibrantlabsai` org; earlier references in `13` named RAGAS generally. Org/ownership change not investigated.)
**Size:** 387 Python files, ~73k LOC under `src/ragas/` (uv workspace; a `CLAUDE.md` exists for Claude Code).

| Area | Findings |
|---|---|
| **Test generation** | `testset/`: **`KnowledgeGraph`** of `Node`/`Relationship` (`graph.py`; save/load JSON; `find_indirect_clusters` for multi-hop), **transforms** (extractors: LLM-, regex-, embedding-based; relationship builders; splitters; filters; default pipelines + engine), **personas**, **synthesizers** (single-hop, multi-hop specific/abstract). A genuinely reusable *corpus → graph → scenario* pipeline. |
| **Metrics** | `metrics/` (114 files) + newer `metrics/collections/` (faithfulness, answer correctness/relevancy/accuracy, context precision/recall/relevance/entity recall, noise sensitivity, response groundedness, factual correctness, tool-call accuracy/F1, agent goal accuracy, topic adherence, SQL equivalence, rubric-based, string/BLEU/ROUGE/chrF). |
| **Experiments** | `experiment.py` (`@experiment` wrapper, `version_experiment`, `Experiment(DataTable)`), pluggable **backends** (in-memory, local CSV/JSONL, Google Drive). |
| **Plumbing** | `executor.py`, `cache.py`, `cost.py`, `run_config.py`, LLM/embedding wrappers, `integrations/` (15 files). |
| **Telemetry** | `_analytics.py`; opt out `RAGAS_DO_NOT_TRACK=true`. |

**Risks:** head commit ~8 months old at clone time (may be slower-moving than DeepEval; do not infer more); LangChain/LlamaIndex coupling noted by competitor sources (◐2) — verify in `pyproject`; judge-based metrics again.
**Verdict:** reuse the **knowledge-graph test-generation pipeline** and RAG metrics via adapters; its graph is also a template for *our* app-model graph (nodes = components/docs, edges = relations).

## 4. What none of the three provide (matches `13`/`18`)
Application-model-driven risk register; coverage accounting with uncovered-risk reporting; verifier independence measurement (n_eff); conformal/Bayesian release gating; outcome-verified (sandbox state) security tests; test-validity estimation; localization via controlled substitution; drift attribution. The repos are **component suppliers**, not competitors for those capabilities — but see `13` for platforms (Langfuse, Phoenix, Braintrust, LangSmith) that overlap on workflow.

## 5. License and compliance notes (read from LICENSE files)
openai/evals MIT; deepeval Apache-2.0; ragas Apache-2.0; rea MIT. Apache-2.0 requires retaining notices and stating changes if modified; do not copy code wholesale — depend on published packages or re-implement ideas. Maintain a `THIRD_PARTY_NOTICES`. Dataset licenses inside `evals/registry/data` and DeepEval `benchmarks/` were **not audited**.

## 6. Reuse decision table
| Capability needed | Source | How | Coupling |
|---|---|---|---|
| System-under-test adapter | evals `CompletionFn` idea | Re-implement as `TargetPort` | none |
| Event/evidence vocabulary | evals `Recorder` | Inspiration only | none |
| Closed-choice judge specs | evals modelgraded | Re-implement | none |
| Scenario ideas | evals `elsuite/` | Read & adapt | none |
| RAG scenario generation | ragas `testset` | pip dependency behind `GeneratorPort` | pinned, optional |
| RAG metrics | ragas / deepeval | Behind `VerifierPort` | pinned, optional |
| Agent metrics (`tool_permission`, loop detection, tool correctness) | deepeval | Reuse deterministic ones; re-implement policy checks natively where trivial | pinned, optional |
| Trace capture | OTel + deepeval/openinference | Ingest OTel; don't require deepeval SDK | none |
| Decision-model judge | DeepEval `JevEval` / TypeSafe API | Optional backend | optional, proprietary |
| Red-team probes | DeepTeam / PyRIT / Promptfoo (not ingested) | Adapters later | optional |
| Black-box env synthesis | REA `environment-build` | Run locally; evaluate fidelity | optional |
