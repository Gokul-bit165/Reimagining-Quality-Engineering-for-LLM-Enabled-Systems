# Continuous-monitoring plan

Status: **a plan, not a running system.** Only the statistics in `qe/drift/exact.py` exist as code; nothing here is scheduled or deployed.

## What is monitored, and how
| Signal | Method | Source in this repo |
|---|---|---|
| Behaviour drift after a model, prompt, corpus or tool change | Pinned canary suite re-run on every candidate change; exact paired test (McNemar) with Holm correction on the canary outcomes | `qe/drift/exact.py` |
| Drift attribution | Swap one component at a time (model / prompt / corpus snapshot / tool schema) against the pinned baseline; the component whose swap reproduces the change is blamed. Hypothesis H7, not yet validated | planned |
| False-alarm control | A no-change control period (same build, repeated) must show alarms no more often than the declared level before alarms are trusted | planned |
| Regression health | Every admitted regression case is re-run on each build; a case that stops reproducing on the defective build is flagged as flaky | `qe/regress/` |
| Security regression | The 12 attack/task pairs re-run with the adaptive attacker at a fixed budget; any oracle-confirmed breach blocks release | `qe/exec/sandbox_runner.py` |
| Evidence integrity | Ledger hash chain verified on every report; head hash anchored outside the database | `qe/core/ledger.py` |

## Triggers
Re-run the full pipeline on: any model or prompt version change, any knowledge-base update, any tool or permission change, and on a fixed schedule for providers that change silently. The schedule length is a policy choice and is **not** set here.

## Human review
A human signs off every RELEASE or CONDITIONAL decision. Disagreement between verifiers, abstentions and INSUFFICIENT_EVIDENCE outcomes go to a review queue (`qe audit`).

## What this plan does not claim
No detection rate, false-alarm rate or time-to-detect has been measured. Those numbers require the drift experiments (H7) which have not been run.
