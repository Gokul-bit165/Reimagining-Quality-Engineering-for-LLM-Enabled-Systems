# 14 — Application Integration Models

Premise: do not assume a target exposes internals. Observable artifacts only; **no access to hidden chain-of-thought is assumed or claimed**.

## Comparison
| Integration | Access required | Visibility | Testing capabilities | Limitations | Ideal scenario |
|---|---|---|---|---|---|
| **A. Black-box** (API/UI + test account + docs) | Endpoint, auth, schema, test identities | Request/response, latency, error codes, streamed tokens | Functional tests, consistency (pass^k), metamorphic, perturbation, adversarial prompts, output-based grounding checks *if sources known* | Can't localize failures; can't verify tool side-effects unless sandbox exposes state; retrieval invisible | Third-party/closed apps; first-contact assessment |
| **B. SDK instrumentation** | Code change in target; dependency approval | Events authored by developer: retrieval IDs, tool calls, model/version, tokens, errors, workflow IDs | Structural assertions, localization, substitution tests (if hooks), coverage on retrieval/tool paths | Adoption friction; target can mis-instrument; version coupling | In-house apps with willing dev teams |
| **C. Observability/trace (OTel & vendor)** | Export/read access to traces (or ability to add exporter) | Span trees: LLM calls, tools, retrieval, agent steps — if instrumented | Same as B with less coupling; replay analysis; production regression | `gen_ai.*` conventions still **Development** (churn); span attribute completeness varies; content capture is opt-in/PII-sensitive | Teams already using LangSmith/Langfuse/Phoenix/OTel |
| **D. Repository inspection** | Read access to authorized repo | Entry points, prompts, tool defs, model config, retrieval components, deps, existing tests | Targeted test/risk generation; static checks (hard-coded secrets, over-broad tool permissions); app-graph seeding | Source exposure/IP risk; static analysis misses dynamic dispatch; LLM code summaries can be wrong | Pre-release audit by trusted internal team |
| **E. Gateway/proxy** | Route LLM/tool traffic through intermediary | Every model call (prompts/completions, tokens, latency) at the network edge | Capture without code change; fault injection (delay/error/rewrite) at provider boundary; response substitution | Adds latency/failure point; privacy exposure; streaming & provider-specific APIs; sees LLM calls but not app-internal logic (retrieval inside DB) | Many apps, uniform provider usage, strong need for no-code capture |

## Is one mode enough?
No evidence suggests a single mode suffices. Black-box is the universal fallback; the *quality of diagnosis scales with visibility* (A < E < C ≈ B < D+B/C). A practical platform needs a **capability negotiation** step: discover what is available, then declare which test families are enabled and which findings will be reported as "location unknown." That is an engineering design consequence, not a validated result.

## Minimum instrumentation for useful structural testing
(See `06`.) Request/trace ID; component spans with type; model name/version; retrieved item IDs+scores+corpus version; tool name/args/result status; retries/fallbacks; token & latency; policy/guardrail decision events.

## Framework notes (not verified this session)
LangChain/LangGraph, LlamaIndex, OpenAI-compatible, custom Python/Node, FastAPI, RAG and multi-agent stacks: the practical route is OTel export (OpenInference/GenAI instrumentations) where available, otherwise an SDK shim or gateway. **Which libraries emit which attributes today was not checked.** OTel status: all `gen_ai.*` attributes at "Development"; the project was split into `semantic-conventions-genai` on 12 Jun 2026 (◐2).

## Partial-information operation
Every finding carries `visibility_level` and `localization_confidence`. Unknown stays "unknown"; do not infer retrieval failure from a wrong answer alone. Release recommendations must state which risk areas were testable at the available access level.

## Source-inspection risks (D)
Secret/IP exposure; prompt-injection *into the inspector* via malicious repo content (treat repo text as untrusted input to LLM tools); license compliance; need for read-only, ephemeral, access-logged workspaces and secret scrubbing.

## Gateway trade-offs (E)
| Aspect | Advantage | Disadvantage |
|---|---|---|
| Latency | negligible if streaming passthrough | added hop; tail latency |
| Privacy | central redaction possible | proxy sees all content |
| Security | policy enforcement point | becomes high-value target |
| Provider compat | OpenAI-compatible surface common | non-uniform tool/streaming semantics |
| Reliability | can add retries | single point of failure |
| Coupling | no code change | tied to network path/config |
