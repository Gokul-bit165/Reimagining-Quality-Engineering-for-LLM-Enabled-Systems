# qe: release evidence for LLM apps (working title)

Multi-agent pre-release verification platform. Agents propose; deterministic code executes, measures and decides. Every number comes from a hash-chained ledger. Read `CLAUDE.md` and `research/` for the rules (R1-R12), `docs/decisions/` for ADRs.

## Quick start
```bash
python -m pip install --user uv
python -m uv sync                      # dev tools + UI deps
python -m uv run pytest -q             # offline tests
python -m uv run ruff check qe sandbox_apps tests bench
python -m uv run mypy --strict qe
```

## UI
```bash
cd frontend && npm install && npm run build && cd ..
python -m uv run --extra ui uvicorn qe.ui.server:app --port 8000
# open http://127.0.0.1:8000
```
The React app (`frontend/`) is served by the backend from `frontend/dist`; if it is not built, `GET /` returns a JSON 503 telling you to build it. Evaluations run against your own project and documents. Question generation needs a real LLM (`QE_ALLOW_REAL_LLM=1`, a provider key and `QE_LLM_MODEL`); without it, supply your own Q&A pairs. There is no simulated or demo data in the product.

## Where things live
| Area | Path | Notes |
|---|---|---|
| Core ledger, schemas, ports | `qe/core`, `qe/ports` | frozen contracts; change via ADR |
| Spine (connect, executor, report) | `qe/access`, `qe/exec`, `qe/report`, `qe/cli` | Person 1 |
| Stats, verifiers, policy | `qe/stats`, `qe/verify`, `qe/policy` | Person 2 |
| Crew, risk, app model | `qe/crew`, `qe/risk`, `qe/model` | Person 3 |
| Attackers, oracles, bench | `qe/exec/sandbox_runner.py`, `qe/crew/attacker.py`, `bench/` | Person 4 |
| Sandbox apps (system under test) | `sandbox_apps/` | independent of `qe` |
| **UI backend / frontend** | `qe/ui/` (API), `frontend/` (React) | see `docs/UI_DESIGN.md` |
| Real evaluation engine | `qe/realeval/` | documents + Q&A -> target -> scored, ledgered evaluation |
