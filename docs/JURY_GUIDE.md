# Jury guide: how to demo, how to verify every requirement, and what is different

Read `docs/FINAL_DEMO_GUIDE.md` for setup. This guide is the script and the proof. Everything below is stated as it is: where a requirement is only partly met, it says so.

## 1. The 60-second pitch
"Most LLM test tools give you a score and a green tick from a few prompts. We built a framework that refuses to say *release* unless the evidence supports it. You describe a risk; the system generates tests from it, runs them against an app, attacks it, checks grounding, classifies failures with evidence, and recommends Release, Conditional or Reject, with every rate shown as an interval, every result traceable to a tamper-evident ledger, and a human signing off. It also runs the same tests on a *clean control* app, so you can see its false-alarm rate, and it tells you what it did not check."

## 2. The live demo (8 minutes). Say what you click, say what they should see.
Start: `python -m uv run --extra ui uvicorn qe.ui.server:app --port 8000` and open `http://127.0.0.1:8000`. Have one scenario already generated as a fallback.

| Min | You do | They see | Requirement it answers |
|---|---|---|---|
| 0:30 | Open **New scenario**; pick `rag`, `LLM09 Misinformation`; edit the risk sentence to something the jury gives you | A free-text risk becomes the input | Adapt to new jury scenarios |
| 1:00 | Press **Generate tests and run** | Progress text, then the report | Define risks, generate tests, execute |
| 1:30 | Point at the decision hero and the three labels | **Reject**, plus *SIMULATED* / *EXAMPLE policy* labels | Honesty; explain the recommendation |
| 2:30 | **Risk register**, then **Dynamic test generation** → "Generated tests" | The jury's risk sentence is a row; tests built from the knowledge base in several styles (direct, false-premise, pressure, injection-wrapped), each with a source quote | Dynamic generation from risks and context |
| 3:30 | **Grounding and hallucination** → open a failing case | Question, expected sentence, what the app said, the evidence key | Detect unsupported claims; verify grounding and citations |
| 4:30 | **Adversarial security** | 3 to 9 attack pairs, static vs adaptive attacker, oracle verdicts and an interval | Prompt injection and adversarial tests |
| 5:15 | **Failure taxonomy** then **Regression suite** | Failures classified by location with rule and evidence; each failing test minimized and admitted only if reproducible | Classify failures; convert failures to regression tests |
| 6:00 | Toggle **Clean control app** | 0 failures, decision *Insufficient evidence* | Low false-positive rate; no over-claiming |
| 6:30 | **Scorecard** | Per-metric intervals against the policy line; no composite number | Quality and safety scores |
| 7:00 | **Human approval**: enter a name, record a decision | Sign-off appears; the ledger records a human-only event | Human review for critical decisions |
| 7:30 | **Monitoring plan** | A plan, labelled "not a running system" | Continuous-monitoring plan |
| 8:00 | Run the verifier (below) | `23/23 checks passed` | Evidence and audit logs |

Then, to show it adapts: run the **same risk text** against `toolagent` (`LLM06`), or tick "also target previous failures" and run again, and show that the generated tests change.

## 3. Prove it (run these in front of the jury)
```bash
# 1. Every claim the demo makes, checked against the ledgers (integrity, replay, tamper, controls, provenance)
python -m uv run python -m qe.demo.jury_check runs scn-<scenario id>      # id is in the run list / URL

# 2. The whole test suite
python -m uv run pytest -q          # 567+ tests, offline
python -m uv run ruff check qe sandbox_apps tests bench && python -m uv run mypy --strict qe
```
`jury_check` shows, for both the seeded app and the clean control: the hash chain verifies; the report is byte-identical when regenerated from the ledger; **editing one stored event in a copy is detected**; model output is stored only as drafts; every rate has an interval; attack results come from deterministic oracles; the clean control has no false alarms; both apps ran the identical generated suite.

## 4. Requirement-by-requirement status (honest)
| Brief requirement | Status | Proof |
|---|---|---|
| Dynamically generate tests from risk scenarios | **Met (simulated generator by default; real tester model optional).** Verified that a different scenario, category or prior failure changes the tests | `tests/integration/test_scenario_pipeline.py::test_generation_is_dynamic…` |
| Test an LLM-enabled application | **Met** for two sandbox apps (RAG, tool agent), each clean and seeded. A third-party app is **not** supported yet | demo |
| Detect hallucinations and unsupported claims | **Partly.** Numeric claims vs the retrieved context, expected figures, citation ids. **Free-text claims are not judged** | grounding section |
| Verify grounding and citations | **Met for citation ids, expected-source citation, numeric support**; not semantic entailment | grounding section |
| Prompt-injection and adversarial tests | **Met** on the sandbox: 12 attack/task pairs, static and adaptive attackers, deterministic oracles | security section |
| Quality and safety scores | **Met as per-metric intervals by dimension.** Deliberately no composite score | scorecard |
| Explain the release recommendation | **Met** ("Why" list from the policy engine inputs) | recommendation |
| Convert failures to regression tests | **Met in simulated mode** (minimize, then admit if reproducible on the defect and clean on the control). **Skipped in real-model mode**, which needs a measured flake rate | regression section |
| Reusable dataset and test suite | **Met**: the generated suite and regression cases live in the ledger and evidence pack | pack download |
| Failure taxonomy with evidence | **Met** by location and rule; controlled-substitution localization is not run | taxonomy section |
| Release recommendation | **Met** (Release / Conditional / Reject / Insufficient evidence) | decision |
| Human review | **Met**: sign-off is a human-only ledger event | approval section |
| Continuous-monitoring plan | **A written plan only** | `docs/MONITORING_PLAN.md` |
| Guardrails (sandbox only, no real targets, synthetic data, audit log, human review) | **Met**: loopback sandbox apps, synthetic data, egress guard, hash-chained ledger, human sign-off. The egress guard is in-process only (see ADR-0001) | `jury_check`, tests |

## 5. Success measures: what we measured and what we did not
| Measure | Where we are |
|---|---|
| Failure / hallucination detection **accuracy** | **Not measured as an accuracy.** We show failures detected on seeded-defect apps and zero on the clean control, but we have not scored detections against the seeded-defect manifests or against human labels. Do not claim a percentage |
| Grounding verification accuracy | **Not measured** against human labels |
| Prompt-injection detection | Attack success measured with oracles at 3 to 9 pairs; intervals are wide. No detector accuracy claimed |
| False-positive rate | **Measured on the clean control** (failing cases / evaluable cases, as an interval). With few cases the upper bound stays high; that is why the control says *Insufficient evidence* |
| Test and risk coverage | Risk coverage and **uncovered risks** are reported; structural coverage is only logged, not claimed |
| Regression coverage | Count of failures admitted as regression cases (simulated mode) |
| Consistency | Measured by repeating each test (identical output across repeats); trivial for the deterministic sandbox, informative with a real model |
| Explainability | Evidence key and rule on every failure; reasons list for the decision |
| Quality of recommendations | Not independently evaluated; the decision follows the policy mechanically and the example policy's appetite is illustrative |
| Adapt to new jury scenarios | New risk text and category: yes. New application or policy file: **not yet** |

## 6. What is different, and what is not
Be modest about novelty. Test generation, red teaming and "recommend a release" already exist in tools such as DeepEval, RAGAS and Promptfoo, and in recent papers (see `research/18_research_gaps.md`). We did not benchmark against them here. What we built differently, and can show live:

1. **Evidence you can audit.** Every result is an event in a hash-chained ledger. The report is regenerated from it byte-for-byte, and a one-byte edit is caught on screen. Most tools store results in a database you must trust.
2. **It refuses to over-claim.** Every rate is an exact interval drawn against the policy line; `INSUFFICIENT_EVIDENCE` is a first-class decision; a "claims not made" block is always shown. Small samples cannot produce a green tick.
3. **A built-in control.** Each scenario also runs on a clean app, so the false-alarm rate is visible. This is how we caught our own checks producing false positives on a real model (see section 7).
4. **Models propose; deterministic code decides.** The ledger itself rejects any evidence, verdict or decision written by a model. Security outcomes come from oracles (canary at a sink, state change, forbidden tool call), never from a model's opinion of "blocked".
5. **No invented numbers.** No composite quality score, no hard-coded pass thresholds; decisions follow a declared policy, and the demo policy is labelled as an example.
6. **Honest labelling.** Simulated vs real generation and target, access level, and what was not checked are on every report.

## 7. Real-model run (what actually happened; say this plainly)
We wired in real models through OpenRouter: Nemotron as the tester that drafts risks and tests, and a free Laguna model as the application under test. (The requested Qwen id does not exist on OpenRouter, and both free Gemma models were rate limited.)

- The first real run **failed the clean control**. The real model answered correctly, but not in the app's citation format, and two of our checks treated that as a hallucination. The control caught our own bug.
- We fixed the checks and added regression tests built from the real answers: numbers are verified against the retrieved context **and the question** (a correct rebuttal quotes the user's wrong figure; agreeing with it is caught by the expected-fact check); list numbering is ignored; "no citations at all" is *not evaluable*. These changes were made after seeing the control fail, so they are not pre-registered.
- A later run found a third bug: when the free tier returned HTTP 429, the empty answers were scored as failures. Runs that error now produce **no verdict** and are listed in the report as missing evidence.
- **Not yet validated:** after those fixes we could not re-run the real target, because its free quota was exhausted (429). So the clean control has **not** been shown clean on live real-model answers. Run it again when the quota resets; `jury_check` will tell you in one line whether the control passes.
- The fully verified path is the **simulated** one (clean control clean, seeded app caught). Real mode is a working integration, not a validated result.

## 8. Questions the jury will ask
- *"Is the generation real AI?"* Default mode is a labelled simulation so the demo is reproducible and offline. Real mode uses a real tester model for part of the generation, with every draft passing the same verbatim-quote gate. We do not claim the simulation is a model.
- *"What is the detection accuracy?"* We have not measured it, and we would rather say so. We can show detections on seeded defects and the false-alarm control.
- *"Can I point it at my app?"* Not yet; it tests the two bundled sandbox apps. That is the next feature.
- *"Why no overall score?"* Any weighting would be an invented number; we show per-metric intervals instead.
- *"Why Insufficient evidence for the clean app?"* With 5 to 9 evaluable cases the interval is wider than the policy's tolerance. More generated tests tighten it; we did not move the threshold.

## 9. Before you walk in
- Run the demo once end to end on the machine you will use; keep one finished scenario as a fallback.
- Decide mode: **simulated** is deterministic and fast; **real** may take minutes and can hit free-tier rate limits. Do not run real mode live unless you have a pre-generated fallback.
- `.env` holds the OpenRouter key; never open it on screen. Rotate the key after the event.
