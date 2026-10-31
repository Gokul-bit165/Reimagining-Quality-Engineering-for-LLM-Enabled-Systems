# Challenge 04 — Research Repository: AI Quality Engineering for LLM-Enabled Systems

Research cut-off: **31 October 2026**. Status: **research phase only** (no code, no frontend, no product name, no final architecture — per the stop condition). Awaiting approval before product definition.

## How to read this repository honestly

This was a single research session using web search and page fetches. It is **not** a completed literature review of the breadth the mandate describes. Every source carries a verification tag:

| Tag | Meaning |
|---|---|
| **✔P** | Primary page (arXiv abstract/HTML, GitHub README) fetched and read this session |
| **✔S** | Primary source seen only through a search-result excerpt (title/abstract/listing); full text **not** read |
| **◐2** | Described only by a secondary source (blog, trade press, aggregator, vendor marketing) |
| **○R** | Recalled from background knowledge; **not re-verified this session** — verify before citing |

No paper's full methodology was read end to end except where marked ✔P, and even then only the extracted portions. Benchmarks, product comparisons and source-code claims are mostly ◐2. See `references/source_verification.md` for the list of things that could not be verified and conflicts between sources.

## Headline findings (details in the numbered documents)

1. **JEV and NCM are unrelated to each other and neither is an established LLM-app QA method.**
   - **JEV** = *Jev*, a proprietary, hosted "decision-only" model from TypeSafe AI (launched 15 Sep 2026, early access). A small cluster of 2026 preprints evaluates it as a cheap first-pass judge. Evidence is promising but young, mixed, and partly vendor-reported. → `04_jev_ncm_investigation.md`
   - **NCM** = *Next-Concept Modeling*, a parallel coarse-to-fine **text-generation** architecture (Stanford Hazy Research). It is not an evaluator. A different, established expansion — **nonconformity measure** (conformal prediction) — is the one plausibly relevant to calibrated release decisions. **Please confirm which NCM you meant.**
2. **"Release recommendation from automated evaluation" is already published prior art** (2026 preprints propose PROMOTE/HOLD/ROLLBACK gates, readiness harnesses, four-state decision models, beta-binomial gates). It cannot be claimed as novel. → `18_research_gaps.md`
3. **More LLM judges ≠ independent evidence.** A 2026 study measured nine frontier judges as worth ~2 independent votes. Whether *heterogeneous method types* (NLI + retrieval + deterministic checks + LLM) break this correlation is plausible but **untested in anything I found**. → `03`, `08`, `09`
4. **Static security suites do not demonstrate resistance.** Adaptive attackers broke 12 published defenses that reported near-zero ASR. Tests must assert on *harmful outcomes in a sandbox*, not on judge opinions. → `10`
5. **Trace-based structural testing of agents exists** (OpenTelemetry + mocks + assertions; open-source reference). The open gap is *automatic* extraction of an application model and coverage-guided generation across arbitrary apps. → `06`
6. **Black-box alone cannot localize failures.** Retrieval-vs-generation attribution needs controlled context substitution or retrieval records, i.e., grey-box access. → `14`

## Depth map (what was actually investigated)

| Area | Depth |
|---|---|
| JEV / NCM | **Deep** (primary pages read) |
| Judge ensembles, correlated errors, conformal | Medium |
| Structural/trace testing, RAG fault localization | Medium |
| Adaptive security, OWASP, red-team tooling | Medium |
| Release-gate prior art | Medium (abstracts/snippets) |
| Competitors | **Shallow–medium**: docs/vendor/secondary pages, **no source-code reading** |
| Benchmarks/datasets licensing | **Shallow** — licensing fields mostly unverified |
| Mutation/grammar-fuzz/combinatorial for LLM apps | **Not searched**; hypotheses only |
| Humanloop, Braintrust/LangSmith internals | Not investigated beyond marketing/docs |

## Update 2 — repo reverse-engineering, solution plan, Claude Code prompt
- `23_repo_reverse_engineering.md` — static read of openai/evals, DeepEval, RAGAS and REA (licenses verified from LICENSE files; REA could **not** be executed in this sandbox because the npm registry was unreachable; no repo code was executed).
- `24_solution_plan.md` — chosen architecture (staged Candidate C), multi-agent crew design, hypotheses with kill tests, roadmap, positioning. **This is the first document that selects an architecture**, at your request.
- `CLAUDE_CODE_MASTER_PROMPT.md` — paste-ready prompt + `CLAUDE.md` for building it with Claude Code.
- Notable: DeepEval already ships `JevEval` (a Jev-backed metric) behind a provider interface, so Jev can be consumed optionally without coupling.
- Correction: the licenses for DeepEval and RAGAS are Apache-2.0, openai/evals and REA are MIT (verified).

## Index
`01_problem_decomposition` · `02_literature_landscape` · `03_advanced_architectures` · `04_jev_ncm_investigation` · `05_deep_testing_methods` · `06_structural_and_trace_testing` · `07_dynamic_test_generation` · `08_multi_agent_evaluation` · `09_grounding_and_verification` · `10_ai_security_and_red_teaming` · `11_statistical_reliability` · `12_benchmarks_and_datasets` · `13_competitor_source_analysis` · `14_application_integration` · `15_live_product_workflows` · `16_architecture_candidates` · `17_benchmarking_experiments` · `18_research_gaps` · `19_innovation_opportunities` · `20_global_impact` · `21_technical_feasibility` · `22_open_research_questions` · `papers/` · `benchmarks/` · `references/`
