# Handoff (state at end of M0 build, 2026-10-31)

## Decisions already made by the user
- Codename: keep `qe` (working title). Sandbox apps: built from scratch.
- Providers: Groq + OpenRouter ("best models"); keys only via env `GROQ_API_KEY`, `OPENROUTER_API_KEY` or gitignored `.env`. **Spend budget NOT set yet**; no real model calls allowed until it is.
- uv installed user-level (`python -m uv ...`), Python 3.12.16 provisioned. NCM = nonconformity measure is assumed, not confirmed.
- Env: Node v23.11 is unsupported by REA; Docker daemon was off. REA is optional (task F2).

## Done (M0)
- Skeleton, `pyproject.toml`, CI workflow, `THIRD_PARTY_NOTICES.md`, `docs/decisions/ADR-0001-foundations.md` (with addendum of fixes + remaining limits).
- `qe/core` (ids, events, ledger, schemas, telemetry), `qe/ports`, `qe/exec/{egress,sandbox}.py`, `qe/testing/fakes.py`.
- `sandbox_apps/` chatbot, rag, multiagent, toolagent (clean + seeded, 25 defects, 10 classes, `defects.yaml` + `probes.yaml`), coverage table in `sandbox_apps/README.md`.
- Adversarial review: `docs/reviews/M0-core-review.md`; all CRITICAL/HIGH/MEDIUM fixed with regression tests in `tests/adversarial/test_review_fixes.py`.
- Verified: 220 tests pass (PYTHONHASHSEED 0 and 123), ruff clean, `mypy --strict qe` clean.

## Not done / caveats
- M0 skeptic review did NOT complete (agent died). Mutation re-run after fixes not done.
- Nothing committed to git yet (only the initial commit exists).
- Known limits: no ledger MAC (use external anchor), egress guard is in-process only, producer kind pinned only if a registry is passed, model-family independence enforcement deferred to M3, fake-LLM defects are easier than natural ones.
- All hypotheses H1-H5, H7 pending.

## Next
Awaiting user approval of the M0 gate, then M1 (deterministic spine): `qe connect` black-box adapter, executor (pass^k, seeds, budgets, kill switch, resume), deterministic verifiers, estimators + intervals + policy engine + Evidence Pack v0, offline replay. Stop at the M1 gate.
Rules: research/CLAUDE_CODE_MASTER_PROMPT.md (R1-R12), project CLAUDE.md.

## Update: M1 built (not yet gate-approved)
- Added: `qe/stats/{intervals,estimators}`, `qe/verify/{deterministic,runner}`, `qe/policy/engine`, `qe/access/blackbox_http` (negotiate A/B), `qe/exec/executor` (pass^k repeats, seeds, budget, kill, resume), `qe/report/evidence_pack` (ledger-only, deterministic), `qe/cli/main` (`qe connect`, `qe report`), `bench/m1_preregistration.md`, tests `tests/integration/test_m1_{spine,gate}.py`.
- Verified: 250 tests pass (PYTHONHASHSEED 0 and 99), ruff and mypy --strict clean.
- Team split for M1-M6: `docs/TEAM_PROMPTS.md`. OpenRouter key is in gitignored `.env`; agent model `nvidia/nemotron-3-ultra-550b-a55b:free` (one family only: judges need a different family before M3).
- Limits: M1 reviewer/skeptic and mutation testing not run; policy `loss_matrix` unused; CONDITIONAL never produced; B-level means "trace returned in response", not true SDK instrumentation.
