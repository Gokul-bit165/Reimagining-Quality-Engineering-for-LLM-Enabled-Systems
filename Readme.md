# qe: release evidence for LLM apps (working title)

Multi-agent pre-release verification platform. Agents propose; deterministic code executes, measures and decides. Every number comes from a hash-chained ledger. Read `CLAUDE.md` and `research/` for the rules (R1-R12), `docs/decisions/` for ADRs.

## Quick start
```bash
python -m pip install --user uv
python -m uv sync                      # dev tools + UI deps
python -m uv run pytest -q             # ~540 tests, offline
python -m uv run ruff check qe sandbox_apps tests bench
python -m uv run mypy --strict qe
```

## Demo UI (offline, FakeLLM, no keys needed)
```bash
python -m uv run python -m qe.demo.run_demo        # writes runs/*.sqlite + policies
python -m uv run uvicorn qe.ui.server:app --port 8000
# open http://127.0.0.1:8000  (or press "Regenerate demo runs" in the page)
```
What you see: four ledgers (RAG and tool-agent, each `clean` and `seeded`). The seeded apps show failing cases; the clean ones show none. All four decisions are **INSUFFICIENT_EVIDENCE**: with 6-9 evaluable cases the intervals are wider than the (example) policy appetite. That is the honest result at this sample size, not a bug. Do not tune appetites to get a prettier decision (R2).

## Where things live
| Area | Path | Notes |
|---|---|---|
| Core ledger, schemas, ports | `qe/core`, `qe/ports` | frozen contracts; change via ADR |
| Spine (connect, executor, report) | `qe/access`, `qe/exec`, `qe/report`, `qe/cli` | Person 1 |
| Stats, verifiers, policy | `qe/stats`, `qe/verify`, `qe/policy` | Person 2 |
| Crew, risk, app model | `qe/crew`, `qe/risk`, `qe/model` | Person 3 |
| Attackers, oracles, bench | `qe/exec/sandbox_runner.py`, `qe/crew/attacker.py`, `bench/` | Person 4 |
| Sandbox apps (system under test) | `sandbox_apps/` | independent of `qe` |
| **UI backend / frontend** | `qe/ui/server.py`, `qe/ui/static/` | see `docs/UI_DESIGN.md` |
| Demo pipeline | `qe/demo/run_demo.py` | sandbox apps -> ledger |

## UI: how to extend it
Vanilla HTML/CSS/ES modules, no build step. Tokens in `qe/ui/static/tokens.css`; components use tokens only. All ledger text is rendered with `textContent` (it is untrusted). The API already returns `coverage`, `n_eff`, `invalid_test_rate` and `asr_at_budget` when a ledger has those events; the page does not draw them yet. See "Not done in v1" in `docs/UI_DESIGN.md`.
