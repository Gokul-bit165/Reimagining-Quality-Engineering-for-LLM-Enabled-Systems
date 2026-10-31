# 08 — Multi-Agent Evaluation: Is It Justified?

## Evidence summary
- Debate-style multi-agent reasoning generally **does not beat** simple baselines (CoT, self-consistency) despite extra compute; **heterogeneous models help** (Zhang et al., arXiv:2502.08788 ✔S).
- LLM-judge panels: ~2 effective votes out of 9 (Kohli, arXiv:2605.29800 ✔S); shared confounders (CARE, ICML 2026 ✔S).
- Judges are attackable (JudgeDeceiver arXiv:2403.17710 ✔S; SoK arXiv:2603.29403 ◐2).
- Auditor-agent designs are effective for *exploration* (Petri; AJAR) ✔S — exploration is where autonomy has the strongest case.
- I did not run or read framework comparisons (LangGraph, AutoGen/Microsoft Agent Framework, Google ADK, OpenAI Agents SDK, CrewAI, DSPy, LlamaIndex Workflows, Temporal) beyond awareness; **no claims about them are made here** (○R only). Framework choice should follow requirements for durability, replay, and determinism (Temporal-style durable execution is an obvious fit for resumable runs — engineering judgment, not verified).

## Principle
Use an LLM **only where the task needs open-ended generation/judgment and no deterministic or learned-classifier substitute is available**; keep evidence ownership, scoring arithmetic and decisions deterministic and auditable.

## Role-by-role assessment (candidate roles from the mandate)
| Role | Recommended form | Reason |
|---|---|---|
| Application Understanding | **Hybrid:** deterministic collectors (repo/trace parsers, OpenAPI readers) + LLM summarizer with provenance | Facts should come from artifacts; LLM only interprets |
| Architecture Analysis | Deterministic graph builder; LLM for naming/annotation | Graph from traces/framework metadata (`06`) |
| Risk Intelligence | **LLM agent** proposing risks, constrained by taxonomy (OWASP etc.) + deterministic ranking from declared policy | Creative enumeration benefits from LLM; ranking must be policy-driven |
| Test Planning | Deterministic scheduler/optimizer (budget, coverage) | Optimization problem |
| Dynamic Test Generation | **LLM agent(s)** + deterministic validators | Generation needs LLM; validation must not |
| Test Execution | **Deterministic worker** | Idempotent, retriable, logged |
| Grounding Verification | **Portfolio of verifiers** (deterministic + NLI + LLM) | See `09` |
| Security Evaluation | **Attacker agents** (adaptive) + **deterministic outcome oracles** (canary/state diff) | Attack search needs adaptation; verdict must be side-effect based |
| Behavioral Consistency | Deterministic statistics over repeated runs | pass^k, similarity distributions |
| Independent Evidence Verification | Separate verifier set with **no access to the primary judge's conclusion** | Independence by information isolation |
| Failure Root-Cause | Rule-based attribution over traces + LLM only for residual "explain" | Localization needs interventions |
| Quality Assessment | **Deterministic** computation with declared estimators | No LLM in arithmetic |
| Release Decision Support | Deterministic policy engine + LLM-written *explanation* tied to evidence IDs | Decision ≠ prose |
| Human Review | Human-controlled queue | Required by mandate |

## Per-role specification template (to fill at design time)
Responsibilities · Inputs · Outputs (typed) · Permissions (least privilege; no production creds) · State/memory (run-scoped; evidence is append-only, ID'd, hashed) · Communication (typed events via an orchestrator, not free-form chat) · Failure handling (checkpoint/resume; partial results labeled) · Order (DAG with explicit dependencies) · Evidence ownership (each evidence record has exactly one producing component; verifiers cannot edit evidence) · Human boundary (approve release; adjudicate disputed/low-confidence/high-impact items).

## Critical questions — current answers
| Question | Answer / approach | Strength of support |
|---|---|---|
| Avoid shared blind spots | Different model families + non-LLM verifiers; **measure** error correlation / n_eff; don't count judges | Medium (Kohli) |
| One agent approving another's unsupported claim | Verifier receives claim + evidence pointer only, not the producer's rationale; claims without evidence pointer are auto-"unsupported" | Design principle |
| Independent verification | Information isolation + method diversity + periodic human audit | Hypothesis H-het |
| Quantify disagreement | n_eff, pairwise κ/α, entropy of verdict distribution; route to human by disagreement × impact | Medium |
| Circular debate | Avoid free-form debate; use one-shot independent verdicts + deterministic referee | Supported by MAD results |
| Reproducible orchestration | Seeds, pinned versions, recorded LLM I/O, durable workflow engine, replay mode | Engineering |
| Latency/tokens | Cascade + caching + deterministic-first funnel; report cost per confirmed defect | Medium (cascade evidence mixed) |
| When deterministic overrides LLM | Whenever an exact check exists: citation ID existence, numeric equality, schema, forbidden-tool-call, canary exfiltration | Strong principle |
| Agent fails midway | Checkpointed steps; mark affected evidence "incomplete"; decision engine treats missing evidence as an explicit state (cf. AGO four-state model, arXiv:2610.01218 ✔S) | Medium |

## Does heterogeneous verification beat more LLM judges?
**Unknown from evidence gathered.** Supporting hints: debate improves with heterogeneity; panels fail from correlation. No direct experiment found comparing {k LLM judges} vs {k methods of different classes} on error independence. Treated as hypothesis H-het; experiment in `17`.
