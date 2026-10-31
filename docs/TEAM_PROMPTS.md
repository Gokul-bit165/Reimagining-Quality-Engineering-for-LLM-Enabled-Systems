# Team prompts: 4 people, M1 to M6 in parallel

## Setup (everyone, once)
1. Lead commits current state to `main` (M0 + start of M1) and pushes. Each person then clones/pulls and works on a branch `p1-spine`, `p2-stats`, `p3-crew`, `p4-security`.
2. `python -m pip install --user uv` then `python -m uv sync`. Checks: `python -m uv run pytest -q`, `ruff check qe tests sandbox_apps`, `mypy --strict qe`.
3. Keys only in a gitignored `.env` (`GROQ_API_KEY`, `OPENROUTER_API_KEY`). No real LLM calls until the owner sets a spend budget. Everything must also run on the FakeLLM.

## Frozen contracts (change only via an ADR in docs/decisions/ + notice to all four)
`qe/core/{ids,events,ledger,schemas}.py`, `qe/ports/__init__.py`, `qe/exec/{egress,sandbox}.py`, `sandbox_apps/` contract. Add new event types or schema fields only by additive PR reviewed by the lead. Merge to `main` only with green tests, ruff, mypy. Rebase daily.

## Shared preamble (paste at top of every person's prompt)
```text
You are one of 4 engineers on a multi-agent pre-release verification platform for LLM apps (package `qe`). Read first: CLAUDE.md, docs/HANDOFF.md, docs/decisions/ADR-0001-foundations.md, docs/TEAM_PROMPTS.md, and research/CLAUDE_CODE_MASTER_PROMPT.md (rules R1-R12; milestones M1-M6). Only read other research files your tasks cite.
Rules: TDD (failing test first); honest claims only (no result claimed without a committed experiment output); no invented thresholds (use Policy files); LLMs propose, deterministic code decides and writes evidence; verifiers see (claim, evidence pointer) only; every rate has an interval; telemetry off; use `python -m uv run ...`; mypy --strict and ruff clean; files under 800 lines; do not edit frozen contracts or other people's directories without an ADR. Use the Write tool, not giant shell heredocs. Keep token use low. Stop at each milestone gate you own and report: what changed, test results, claims NOT made, next step.
```

## Person 1: Spine and Reporting (branch `p1-spine`)
Owns `qe/access/`, `qe/exec/executor.py`, `qe/report/`, `qe/cli/`, `qe/core/replay`.
- M1: T1.1 `qe connect` black-box HTTP adapter implementing `TargetPort`, capability negotiation A-E, `visibility_level` recorded in ledger (test against `sandbox_apps` HTTP wrapper on 127.0.0.1). T1.2 executor: repeated runs (pass^k), seeds, budgets, kill switch, resumable via idempotent ledger keys (use `LocalSandbox`). T1.4 Evidence Pack v0 generated ONLY from the ledger, deterministic Markdown+JSON, golden-file tests (syrupy). T1.5 offline replay: report from ledger is byte-identical.
- M2: `qe/access/otel_ingest.py`, SDK shim. M5: `qe/regress/` minimizer + pass^k admission + suite store.
- M6: T6.3 static HTML report viewer from ledger; T6.2 reproducibility bundle packaging.
Hands off: `ExecutorAPI` (run test cases -> RunRecord events) and `build_evidence_pack(ledger, policy)` for the others by end of M1 week.

## Person 2: Statistics, Verification, Adjudication (branch `p2-stats`)
Owns `qe/stats/`, `qe/verify/`, `qe/policy/`.
- Already done by lead (do not redo, harden): `qe/stats/{intervals,estimators}.py` (Clopper-Pearson, pass^k), `qe/verify/deterministic.py` (citation, quote, numbers, entities, schema, forbidden tool, canary), `qe/policy/engine.py`. Your M1 work: add cluster-robust and Bayesian intervals, judge-corrected estimators, mutation-test these modules and report the score, property tests (interval coverage, pass^k), cite metric definitions in `research/benchmarks/evaluation_metrics.md`.
- M3: T3.1 verifier portfolio (entailment adapter, DeepEval/RAGAS adapters behind `VerifierPort` as pinned optional extras, >=2 LLM judges of different families via Groq/OpenRouter, optional decision-model backend off by default). T3.2 aggregator: information isolation by types, Kish n_eff, pairwise error correlation, conformal abstention (NCM = nonconformity measure, still unconfirmed), `qe calibrate`. T3.3 judge-injection guard + canary tests. T3.4 experiment E-H1 per `research/17`; publish whichever way it comes out.
- M6: analysis scripts for all tables/figures; DeepEval/RAGAS default baseline arms.

## Person 3: Crew, App Model, Coverage, Localization (branch `p3-crew`)
Owns `qe/model/`, `qe/risk/`, `qe/crew/`, `qe/localize/`.
- M2: T2.1 app-model builder from traces/OpenAPI with per-edge uncertainty. T2.2 Risk Analyst (taxonomy-constrained; load OWASP LLM/Agentic from fetched primary files and cite; ranking by policy code), budgeted Planner, Scenario Authors (>=2 model families), RAGAS `GeneratorPort` adapter. T2.3 Skeptic (independent re-derivation from source docs, ambiguity/redundancy flags) + `qe audit` human sampling tool; measure invalid-test rate. T2.4 coverage report incl. UNCOVERED cells; log structural coverage (H3: log, do not claim).
- Crew LLM output is recorded only as draft/proposal event types (R3). Prompts versioned in files, hashed in the ledger.
- M5: T5.1 localizer (trace rules + controlled context substitution, "unknown" allowed, top-1 accuracy vs manifests).

## Person 4: Security, Drift, Benchmark (branch `p4-security`)
Owns `qe/exec/` additions (`sandbox_runner.py`), `qe/crew/attacker.py` (coordinate with P3), `bench/`, drift module.
- Immediately: harden sandbox app realism (natural-defect candidates, real-LLM mode behind opt-in), add a second drift defect to non-chatbot apps (coordinate; manifests stay independent of `qe/`).
- M4: T4.1 sandbox runner with canary sinks and state-diff oracles for `toolagent`; T4.2 attackers (direct/indirect injection, RAG poisoning, tool misuse, memory poisoning), budgets, AgentDojo-style task/attack pairs, ASR@budget with attacker class, static vs adaptive paired comparison with intervals; T4.3 optional Promptfoo/PyRIT/DeepTeam adapters as attack generators only (verdicts from our oracles).
- M5: T5.3 drift: pinned canaries + differential substitution, attribution (H7), no-change control for false-alarm rate.
- M6: T6.1 benchmark protocol (`research/17`: all arms, same base LLM, ablations, budget-matched, held-out families/app, natural-defect track); T6.2 `bench/preregistration.md` committed BEFORE any run.
- Optional F2: REA fidelity study (needs Node 22.23.4+/24.22.1+ and Docker running).

## Gates and integration
- Gate order is unchanged (M1 to M6); the lead integrates, runs the reviewer + skeptic subagents per gate, and the owner approves. Parallel work: M1 (P1+P2) -> M2 (P3, P1) and M4 (P4) can start once M1 interfaces land; M3 (P2) needs M2 outputs only for the E-H1 claim set (use sandbox manifests meanwhile); M5/M6 last.
- Weekly: each person updates the hypotheses table (confirmed / killed / pending) in `docs/HYPOTHESES.md` with links to committed experiment outputs only.
