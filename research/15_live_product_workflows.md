# 15 — Live Product Workflows (research-level design, not implementation)

Sandbox set (from mandate): (1) basic chatbot, (2) RAG knowledge assistant, (3) multi-agent app, (4) tool-using assistant. The workflow below is a *candidate*; each step lists what is evidence-backed vs hypothesis.

| # | Step | Input | Processing | Tools/Agents (D = deterministic, A = LLM agent) | Output | Stored evidence | Failure scenarios | Human role |
|---|---|---|---|---|---|---|---|---|
| 1 | Connect | Endpoint/SDK/trace/repo creds; scope; allowed actions | Authorization check; sandbox attestation | D: connector, secret vault | Connection profile, **access level A–E** | Config hash, consent record | Wrong env (prod!), expired creds | Approves scope & sandbox |
| 2 | Discover | Profile | Probe capabilities; read OpenAPI/docs; ingest sample traces; (repo scan if D) | D: collectors; A: capability summarizer | Capability inventory + uncertainty | Raw probe I/O | Rate limits, auth walls, misleading self-descriptions | Review inventory |
| 3 | Understand | Inventory + traces | Build app model: components, tools, permissions, data stores, trust boundaries | D: graph builder; A: annotator | App model v1 (versioned) | Graph + source of each edge | Missing paths; wrong inference | Correct model (cheap, high-value) |
| 4 | Model risks | App model + taxonomies (OWASP etc.) | Enumerate risk×surface cells; rank by declared policy (likelihood proxies, impact tags from owner) | A: risk proposer; D: ranker | Risk register | Rationale per risk, taxonomy ref | Unranked/poorly-justified risks | Owner supplies impact weights/policy |
| 5 | Plan | Register + budget + access level | Choose test families per cell, allocate budget, set stopping rules | D: planner | Test plan with "why" | Plan + budget ledger | Over/under-spend | Approves budget |
| 6 | Generate | Plan + app model + source-of-truth docs | Create scenarios, variants, metamorphic relations, attacks; validate | A: generators; D: validators (schema, executability, oracle derivation) | Validated test cases + invalid-test log | Lineage (parent, generator, seed) | Invalid/duplicate tests | Audit sampled tests |
| 7 | Execute | Tests | Run with test identities in sandbox; repeated runs for pass^k | D: executor (idempotent, resumable) | Raw results | Full I/O, timings, seeds | Provider errors, flaky infra | — |
| 8 | Capture | Raw results | Normalize traces/tool events/retrieval records | D | Evidence records | Immutable, hashed | Missing telemetry | — |
| 9 | Verify | Evidence | Grounding (six-state), security outcome oracles, consistency stats | D+portfolio verifiers; A as residual | Verified findings with per-method verdicts | Verifier versions, calibration set IDs | Verifier errors; disagreement | Adjudicates disagreement/high impact |
| 10 | Diagnose | Findings + traces | Classify failure type; localize using intervention/substitution where access allows | D rules; A for explanation only | Failure records with `location` + `localization_confidence` | Intervention logs | "Unknown" dominates in black-box | Confirms root cause |
| 11 | Evaluate | Verified findings | Compute metrics with CIs; separate quality vs safety; judge-corrected estimates | D | Scorecard + uncertainty | Estimator versions | Small n; judge miscalibration | Reviews methodology flags |
| 12 | Recommend | Scorecard + policy | Policy engine → RELEASE / CONDITIONAL / REJECT (+ "insufficient evidence" state) | D: policy engine; A: narrative tied to evidence IDs | Decision + conditions + evidence links | Policy version | Policy missing/ambiguous | **Must approve** (mandate) |
| 13 | Human review | Decision pack | Sign-off, overrides with reason | — | Signed decision | Override log | Rubber-stamping | Accountable approver |
| 14 | Regression | Validated failures | Minimize; admit only reproducible (pass^k) cases; version | D: minimizer/admission; A: optional | Regression suite | Case lineage | Flaky admissions | Approves promotion |
| 15 | Monitor | Prod/trace stream + pinned canaries | Changepoint/drift checks; trigger re-test on prompt/model/corpus/tool changes | D | Alerts, re-run triggers | Baselines | False alarms; judge drift | Triage |

## Per-application-type deltas
- **Basic chatbot:** black-box sufficient for consistency, safety, injection, hallucination-in-the-world (needs external truth); no grounding evidence available.
- **RAG assistant:** needs retrieval IDs for localization; poisoning and stale-knowledge tests require control over a sandbox corpus.
- **Multi-agent:** needs handoff events; privilege-escalation tests need role definitions.
- **Tool-using assistant:** needs mock/sandbox tool backends so side-effects are observable (outcome oracles).

## Evidence status
Steps 7–8, 11, 14–15 are standard engineering patterns. Steps 3–4 (application model, risk register generation) and 10 (localization at scale) are **research-grade, unvalidated**. Step 12's policy-gated decision has prior art (`18`).
