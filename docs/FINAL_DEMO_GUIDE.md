# Final demo guide

Everything below runs offline on this machine. **Generation and the target applications are simulated** (a deterministic stand-in and the FakeLLM sandbox apps). No real model is called, no API key is read, and nothing leaves the machine.

## Launch
```bash
python -m pip install --user uv
python -m uv sync
python -m uv run --extra ui uvicorn qe.ui.server:app --port 8000
# open http://127.0.0.1:8000
```
If port 8000 is busy, use another (`--port 8791`).

## Live demonstration sequence (about 8 minutes)
1. **New scenario** (opens by default). Pick `rag`, category `LLM09 Misinformation`; the example risk text is pre-filled. Click **Generate tests and run** (about 10 seconds; it runs a clean control and a seeded-defect app).
2. **Decision hero:** the seeded app is **Reject**. Point at the three labels: *SIMULATED generation*, *FakeLLM sandbox target*, *EXAMPLE policy*. Say plainly that these are simulated.
3. **Risk register:** the risk you typed is validated against the OWASP LLM taxonomy and ranked with the simulated analyst's risks. Show the uncovered-risk note if present.
4. **Dynamic test generation:** open "Generated tests". Each question comes from a sentence in the application's own knowledge base, varied as a direct question, a false-premise question, a pressure question or an injection-wrapped question. Every test has a verbatim source quote.
5. **Grounding and hallucination:** open "failing case with evidence": the question, the expected source sentence, what the app said, and the evidence key. Note what is *not* checked: only citation ids and numeric claims.
6. **Adversarial security:** the attack table (3 RAG-poisoning pairs for `rag`, 9 for `toolagent`), static versus adaptive attackers, and the interval. Outcomes come from oracles, not from a model's opinion.
7. **Failure taxonomy → Regression suite:** failures are classified by location; each failing test is minimized and admitted only if it reproduces on the seeded app and passes on the clean one.
8. **Toggle "Clean control app":** zero failures, zero breaches, decision **Insufficient evidence**. This is the false-positive check, and it shows the system does not say "release" from a small sample.
9. **Scorecard and Release recommendation:** per-metric intervals against the policy appetite, no composite number. Read the "Why" list.
10. **Evidence pack:** download JSON/Markdown; the hash chain is verified.
11. **Human approval:** enter a name, record approval or rejection; it is written to the ledger as a human-only event.
12. **Monitoring plan:** a plan, labelled as such.
13. **Adaptive step (optional):** back on **New scenario**, tick "Also target previous failures" after opening a run with failures, and run again; the generated tests change.

Second scenario to show adaptability: `toolagent`, `LLM06 Excessive Agency`.

## Screenshots (real, taken from the running app)
- `docs/ui_report_1440.png` decision and labels at 1440px
- `docs/ui_security_1440.png` adversarial results at 1440px
- `docs/ui_report_390.png` report at 390px
- `docs/ui_form_390.png` scenario form at 390px

## Challenge coverage (what is real and what is not)
| Brief item | Status | Where |
|---|---|---|
| Generate tests dynamically from risk scenarios | **Yes, simulated generator.** Tests derive from your scenario text, the taxonomy id, the app's sources and prior failures; verified by tests that different inputs give different tests. Not a real LLM | `qe/demo/sim_llm.py`, `qe/crew/` |
| Test an LLM-enabled application | Yes, two sandbox apps (RAG, tool agent), each clean and seeded; FakeLLM | `sandbox_apps/` |
| Detect hallucinations / unsupported claims | **Partly.** Numeric claims not in the cited source, wrong or missing expected figures, citations not in the corpus, wrong source cited. No free-text hallucination detection in this demo | `qe/demo/pipeline.py` |
| Verify grounding and citations | Yes for citation ids, expected-source citation and numeric support | same |
| Prompt-injection and adversarial tests | Yes, 12 attack/task pairs across 5 surfaces, static and adaptive attackers, deterministic oracles | `qe/crew/attack_pairs.py`, `qe/exec/` |
| Quality and safety scores | Per-metric rates with exact intervals by dimension; **no composite score by design** | scorecard |
| Explain the release recommendation | Yes, the "Why" list comes from the policy engine's inputs | recommendation |
| Convert failures into regression tests | Yes: minimize, then admit only if reproducible on the defect and clean on the control | `qe/regress/` |
| Failure taxonomy with evidence | Yes, by location with rule and evidence; context substitution is not run | `qe/localize/` |
| Human review | Sign-off recorded in the ledger (human-only event). A reviewer queue (`qe audit`) exists in the CLI | UI, `qe/crew/audit_cli.py` |
| Continuous-monitoring plan | A written plan only | `docs/MONITORING_PLAN.md` |
| Reusable dataset and suite | The generated suite and regression cases live in each ledger and the evidence pack | ledger |
| Adapt to new jury-provided scenarios | Yes for new risk text, category and application among the two apps. A new application needs a sandbox adapter | form |

## Limitations (stated plainly)
- Generation and targets are simulated; results say nothing about real LLM applications.
- Small samples: 5 to 9 evaluable cases per metric, 3 to 9 attack pairs. Intervals are wide and the clean control always ends **Insufficient evidence**. This is the honest result, and no threshold was changed to improve it.
- The example policy's appetite (10%) is illustrative, not a recommendation.
- Hallucination detection is numeric and citation-based only. Bias, toxicity and free-text judging are not run.
- Attack intervals ignore correlation between pairs; attackers and pairs were developed knowing how the seeded apps behave, so this is a plumbing check and not a held-out evaluation.
- Regression admission uses demo parameters (flake rate 0, alpha 0.05) because the sandbox is deterministic.
- The ledger has no signature; an attacker with write access to the file could forge a consistent chain (see ADR-0001).
- The pre-existing M0 skeptic/mutation pass, reviewer and skeptic passes on the merged code, and a CI run on GitHub have not been done.

## Known bugs
- The report page shows a double horizontal rule where the section jump bar meets the first section.
- Running a scenario blocks the request for roughly 10 seconds with only a text status.
- Old demo ledgers from `qe.demo.run_demo` are not listed in the new UI (it lists scenario runs only).

## Verification run for this version
See the final summary in the pull request / chat for the exact test, `ruff` and `mypy --strict` output.
