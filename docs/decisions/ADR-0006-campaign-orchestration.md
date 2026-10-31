# ADR-0006: campaign orchestration (multi-target test + benchmark programme)

Status: accepted. Context: ADR-0005 evaluates one endpoint. A company needs to compare its
current RAG against a variant (chunk size, retriever, model, prompt), a vendor, or a bare LLM,
on the same tests, with a plan it can inspect, import and audit. No simulated data anywhere.

Decisions
1. A campaign is a persisted state machine under `runs/campaigns/<id>/` (`campaign.json`, `plan.json`,
   `ledger.sqlite`). Stages: risk_definition, test_plan, execution, verification, classification,
   scoring, comparison, recommendation, review. Each records start/end, an inputs hash, status
   and error; every transition and human action is an audit event in the hash-chained ledger.
2. The execution ledger is the source of truth: each target response is appended as
   `crun:<target>:<case>:<rep>` before the next call. Resume re-reads the ledger and skips
   recorded calls; verification..review are recomputed from it (pure functions in
   `qe/campaign/analysis.py`). A process death leaves state `running`, reported as `interrupted`
   (resumable). Resume refuses if the project's documents/Q&A changed (digest) to avoid mixing
   evidence. Cancel is a kill switch (stops between calls, calls `kill()` on targets); the
   wall-clock and call budgets stop the run the same way. Stopped runs are scored on the cases
   every target completed and carry `incomplete`, which forces INSUFFICIENT_EVIDENCE.
3. The test plan is an artifact (`GET /api/campaigns/{id}/plan`): risks (register) -> cases with
   ids, lineage, oracle types (reference_match, refusal, citation, canary, output_predicate,
   unchecked), expected evidence, and a coverage matrix (risk x tests x taxonomy ids) with
   explicit GAP / CHECK_ONLY rows, unmapped labels, and unassessed OWASP LLM ids. Risks come only
   from the user's focus, analyzer flags (`FLAG_SCENARIOS`), documents/Q&A, always-on security
   probes and an imported plan. Cases come from `qe.realeval` (`build_items`); the plan states
   "rule-based only; no LLM-authored tests" unless a real LLM drafted grounded questions (still
   advisory until confirmed). A plan can be imported (validated: ids, probes, size) and the
   engine recomputes risks, oracles and coverage from it.
4. Benchmark: one plan, N targets (endpoint or bare `model`), identical cases and seeds, repeats
   k, and a rotating per-(case,repeat) target order so no target systematically goes first.
   The plan is truncated once, before execution, so all targets see the same cases. Only cases
   answered by every target on every repeat are compared.
5. Statistics: per-target rates via `qe.realeval.assemble` (distinct root questions, 95%
   Clopper-Pearson, pass^k), latency p50/p95/p99, call error rate, response size, token usage when
   the response carries it. Pairwise: exact McNemar on discordant roots (`qe.stats.paired`),
   Newcombe paired difference interval and Cohen's h (`qe/campaign/paired_ci.py`), Bonferroni
   over all metric x pair tests (stated; conservative). Outcomes: A_BETTER / B_BETTER /
   NO_SIGNIFICANT_DIFFERENCE / INSUFFICIENT_EVIDENCE (< `MIN_N_NOTE` paired roots). `alpha` is a
   conventional parameter the user may change. A recommended target exists only if it wins
   overall_pass_rate significantly against every other and is significantly worse on no metric.
6. Decisions per target use `qe.policy` through `assemble` with the user policy (or explicit
   `use_example_policy`); advisory generated items stay excluded until confirmed.
7. Model targets: OpenAI-compatible `/chat/completions`, documents stuffed into the system
   prompt (capped, truncation noted), key from the project vault by name (`api_key_secret`),
   SSRF-guarded and DNS-pinned on every call. No retrieval, so contexts are empty: retrieval and
   grounding metrics are not measured for them.

Not done / limits: crew roles (risk_analyst, scenario_author, attacker, skeptic) are not wired:
LLM assistance is the existing grounded question generator only. Cost is not computed (no price
table); tokens only for model targets. Endpoint targets do not report token usage. Docker-mode
projects are not campaign targets. A static-only project cannot back a model-only campaign
(the resolver refuses it). Monitoring/regression admission is not exposed per campaign.
