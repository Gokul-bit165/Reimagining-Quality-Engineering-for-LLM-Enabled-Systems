# 06 — Structural and Trace-Level Testing

## What exists (verified)
**Kohl et al., "Automated structural testing of LLM-based agents: methods, framework, and case studies," arXiv:2601.18827 (25 Jan 2026; BMW Group, AWS, LMU affiliations) ✔S** — captures agent trajectories as **OpenTelemetry** traces, uses **mocking** to make LLM behavior reproducible, and **assertions** over traces (tool inclusion/exclusion, order, content, custom checks). Argues it enables a test-automation pyramid, regression and TDD for agents, and faster root-cause analysis. Open-source reference implementation cited (awslabs/generative-ai-toolkit). Evidence is **case studies**, not a controlled benchmark. I read the abstract/intro excerpts only.

**RAG diagnosis:** RAG-X (arXiv:2603.03541, medical QA; separates retrieval from generation) ✔S; Doctor-RAG (arXiv:2604.00865; trajectory-level, coverage-gated error taxonomy; localizes earliest failure point in agentic RAG on HotpotQA) ✔S; RAGChecker (claim-level retrieval vs generation diagnosis; described via a vendor blog, ◐2).

**Controlled-substitution diagnosis (practitioner consensus, ◐2):** hold generation constant and swap in known-good context; if the answer becomes correct, retrieval/packing was at fault. This is the cleanest fault-localization experiment and needs an *intervention point* (ability to supply context), i.e., grey/white-box access.

## Observability ≠ deep testing
OTel GenAI conventions give a vocabulary for spans (`invoke_agent`, `execute_tool`, inference spans, MCP) but every `gen_ai.*` attribute is still **"Development"** status; GenAI/MCP conventions were moved to a separate repository on 12 Jun 2026 and that repo had no tagged release as of mid-July (◐2: Dash0, azena.ai dev.to, Greptime). Capturing traces gives *data*; testing requires (1) expected structure, (2) oracles over that structure, (3) the ability to drive the app to specific paths. Observability platforms provide (1)-(3) only to the extent the user writes them.

## Can application graphs be extracted automatically?
| Source | What can be extracted | Reliability |
|---|---|---|
| Framework metadata (e.g., LangGraph compiled graph) | Nodes/edges, conditional routes | High **when the framework exposes it** (engineering; not verified this session) |
| OTel/trace corpus from live or test traffic | Observed span-type DAGs, tool sequences, retrieval counts, latencies | High for *observed* paths; unobserved paths unknown |
| Repository analysis (AST + LLM summarization) | Entry points, prompts, tool definitions, model configs | Plausible; **no validated method found**; dynamic dispatch defeats static analysis |
| Black-box probing | Capabilities (what it answers/refuses/calls) | Low–medium; cannot see internals |

**Open problem:** a framework-agnostic *application model* (components, data stores, tools, permissions, trust boundaries) learned from the above, with an uncertainty annotation per element. I found no paper that delivers this end to end; treat as **requires original research**.

## Proposed structural coverage criteria (our hypotheses; not validated)
1. **Span-type/edge coverage** over the observed trace graph.
2. **Tool-sequence n-gram coverage** (and forbidden-sequence tests).
3. **Retrieval coverage**: fraction of corpus chunks (or strata) ever retrieved by tests (the "Chunk Coverage" idea — source is only a seminar abstract).
4. **Branch coverage of routing/fallback/retry logic** via fault injection.
5. **State-transition coverage** for agent memory/state.
Each is observable under grey-box. None is yet shown to correlate with finding real defects → **needs an experiment** (`17`).

## Failure-location taxonomy to attach to every failure record
`input_handling | retrieval | ranking/packing | context_assembly | prompt_template | generation | tool_selection | tool_arguments | tool_execution | state/memory | orchestration/routing | guardrail | output_validation | dependency/provider | unknown`.
Localization methods by access: **black-box** → only repeated-run and perturbation evidence ("unknown" dominates); **grey-box** → retrieval records + tool events + spans; **white-box** → substitution/replay/intervention.

## Minimum useful instrumentation (derived, to validate)
Request/response with IDs; model name+version string; per-LLM-call prompt hash (content optional); retrieved item IDs + scores + source version; tool name/args/result status; error/retry events; token/latency. Without retrieved-item IDs, retrieval vs generation cannot be separated; without tool events, tool misuse cannot be asserted.

## Not claimable
Hidden chain-of-thought access, or that trace capture alone constitutes structural testing.
