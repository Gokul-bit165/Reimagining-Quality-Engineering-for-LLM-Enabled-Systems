# ADR-0003: Integration of four branches

Date: 2026-10-31. Merged `member-3` (M2), `member-4` (M4), `member-2` (stats), `person1` (spine) onto `integration`.

- Where the lead's earlier local files duplicated an owner's module, the owner's pushed version won (crew/risk -> P3, security/runner -> P4, stats -> P2).
- Removed superseded local duplicates: `qe/crew/{record,fakes,authors,generator,prompt_store,text}.py`, `qe/risk/planner.py`, `qe/cli/audit.py`, `qe/policy/expected_loss.py` and their tests. All recoverable from commit e809494. `expected_loss` (optional loss-matrix path) needs a Beta `posterior` API; Person 2 should re-add it on top of `qe/stats/bayes.py` if wanted.
- `.gitattributes` pins LF for `bench/**` and `*.md` so the M4 pre-registration hash is stable on Windows.
- Gate status after merge: pytest 531 passed, ruff clean, mypy --strict clean. Not yet done: M0/M1 reviewer+skeptic pass on the merged tree, mutation scores, CI run on GitHub.
