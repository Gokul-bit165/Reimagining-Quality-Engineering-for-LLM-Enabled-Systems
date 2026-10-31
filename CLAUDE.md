# CLAUDE.md
Project: multi-agent pre-release verification platform for LLM apps. Read ./research/ first (README, 24, 23, 16, 17).
Rules (full list R1–R12 in research/CLAUDE_CODE_MASTER_PROMPT.md): honest claims only; no invented thresholds (policy file); agents propose, deterministic code decides; verifier independence by information isolation + different model families; security verdicts from outcome oracles in a sandbox; telemetry off (DEEPEVAL_TELEMETRY_OPT_OUT=1, RAGAS_DO_NOT_TRACK=true); deepeval/ragas only behind ports, pinned, optional; never vendor Apache-2.0 code; INSUFFICIENT_EVIDENCE is a valid decision; every rate has an interval; every run replayable from the ledger.
Commands: `python -m uv sync`, `uv run pytest`, `uv run ruff check`, `uv run mypy --strict qe`.
Gates: stop at each milestone gate and wait for approval. Log decisions in docs/decisions/.
Secrets: provider keys only via env vars (GROQ_API_KEY, OPENROUTER_API_KEY) or gitignored .env. Never print or commit.
