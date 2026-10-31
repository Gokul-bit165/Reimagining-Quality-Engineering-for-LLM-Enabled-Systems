# Jury Q&A: how to answer

Use this as a prompt sheet. Each answer has **Say** (what to say, in your own words), **Show** (what to click or run) and sometimes **Avoid** (what not to claim). If a question is not here, use section 9.

## 0. Numbers and facts you can quote (and nothing else)
| Fact | Value | Where it comes from |
|---|---|---|
| Automated tests passing | 595 | `python -m uv run pytest -q` |
| Lint and strict type check | clean | `ruff`, `mypy --strict` |
| One-command verifier | 23 of 23 checks, on a simulated scenario | `python -m uv run python -m qe.demo.jury_check runs scn-<id>` |
| Attack pairs | 12, across 5 surfaces (direct injection, indirect injection, RAG poisoning, tool misuse, memory poisoning) | `qe/crew/attack_pairs.py` |
| Tool-agent seeded app, pairs breached in 8 attempts | static 5 of 9 (95% interval 21.2 to 86.3%); adaptive 8 of 9 (51.8 to 99.7%) | simulated sandbox run |
| Clean control app | 0 failing cases, 0 breaches | simulated runs |
| Decisions | Release, Conditional, Reject, Insufficient evidence | policy engine |
| Intervals | exact (Clopper-Pearson) 95% | `qe/stats/` |
| Policy tolerance in the demo | 10%, **an example, not a recommendation** | example policy |
| Apps tested | 2 in the pipeline (RAG, tool agent), each clean and seeded | `sandbox_apps/` |
| Benchmark metrics | faithfulness, answer accuracy, abstention, injection resistance, consistency | model benchmark |

**One-sentence honesty line (use it often):** "Everything you see runs on a labelled simulation by default; we have not measured detection accuracy against human labels, and our real-model validation is incomplete."

---

## 1. The project, in the jury's words

**Q1. What did you build?**
Say: "A reusable quality framework for LLM apps. You describe a risk in plain words; it generates tests from it, runs them against an app, attacks the app, checks grounding, classifies the failures, and recommends Release, Conditional or Reject with the evidence and the uncertainty. A human signs off, and every result is in a tamper-evident ledger."
Show: the demo, slide 3 (the pipeline).

**Q2. Does it cover the whole end-to-end chain in the brief?**
Say: "Define risks, generate tests, execute, capture, verify grounding, classify failures, score, recommend, human review and regress are built and demonstrable. Monitoring is a written plan with the statistics code, not a running service."
Show: `docs/MONITORING_PLAN.md`. Avoid: saying monitoring is live.

**Q3. Who is the user and how do they use it?**
Say: "An AI or QA engineer who must decide if an LLM app version ships. They enter a risk, read the decision then the intervals, check the failing evidence, compare with a clean control, rerun after a fix. An approver records sign-off."
Show: New scenario form.

**Q4. What is the output they get?**
Say: "A decision with reasons, a scorecard of per-metric intervals, a failure taxonomy with evidence, a regression suite, an evidence pack (JSON and Markdown) and a recorded human sign-off."
Show: Evidence pack section and the download links.

---

## 2. Test generation ("a manual prompt list is not enough")

**Q5. Is the test generation really dynamic, or just a fixed list?**
Say: "Tests are derived from three inputs: your risk text and category, the application's own source documents, and earlier failures. We tested that changing the scenario, the category or a prior failure changes the generated tests. Each test carries a verbatim quote from a source document."
Show: generate a scenario with the jury's own sentence; then rerun with "target previous failures".

**Q6. Is the generator an AI model?**
Say: "By default it is a deterministic stand-in, clearly labelled SIMULATED, so the demo is reproducible and free. A real tester model can draft the risks and tests; every draft goes through the same deterministic quote check. We do not call the simulation a model."
Avoid: "AI-generated tests" without the label.

**Q7. How varied are the tests? Aren't they templates?**
Say: "They are built from templates over real source sentences, in several styles: direct, false-premise, pressure and injection-wrapped. Variety is limited by the templates, not by the sources. A real model would add more variety, which is why that mode exists."

**Q8. How do you know a generated test is valid?**
Say: "Two deterministic gates before anything runs: the source must exist and the quoted evidence must be verbatim in it, and duplicates are removed. Rejected drafts are still recorded so the invalid-test rate has a denominator. We have not measured invalid-test rate against human audit."

**Q9. How do you handle a scenario we invent right now?**
Say: "Type it into the form and choose the closest OWASP category. Any text works; the apps are limited to the two bundled sandbox apps."
Show: do it live. If the result is odd, say what it is: it is evidence, not a bug in the demo.

---

## 3. Grounding, hallucination, accuracy

**Q10. How do you detect hallucinations?**
Say: "We detect specific, checkable kinds: a number in the answer that appears in neither the retrieved context nor the question, a citation id that does not exist, the wrong source cited, and a missing correct figure. We do not detect free-text unsupported claims."
Avoid: "We detect hallucinations" without the scope.

**Q11. What is your hallucination detection accuracy?**
Say: "We have not measured it against human labels, so we will not quote a percentage. What we can show is failures found on the seeded-defect apps and zero false alarms on the clean control."
Show: the clean control toggle.

**Q12. How do you verify citations?**
Say: "Deterministically. The citation id must exist in the corpus, and the expected source must be among those cited. If an answer carries no citations at all we mark it not evaluable, not failed."

**Q13. Why not use an LLM judge for grounding?**
Say: "Verdicts must not depend on a model that can itself be fooled by injected text. We use deterministic checks first. Entailment and judge adapters exist in the code but are not part of this demo."
Avoid: claiming a judge ensemble or inter-judge independence was tested; that experiment was not run.

**Q14. What about consistency?**
Say: "Each test is repeated and we check that the figures are stable. On the deterministic sandbox this is trivially consistent; it becomes informative with a real model, where we saw answers vary between repeats."

**Q15. What about bias and toxicity?**
Say: "Not covered. We would add them as further checks in the same framework."

---

## 4. Security and adversarial testing

**Q16. How do you test prompt injection?**
Say: "Twelve attack and task pairs on five surfaces, run with a static attacker and an adaptive one. The outcome is decided by an oracle in the sandbox: a canary reaching a sink, a protected state changing, or a forbidden tool call. Never by a model saying 'blocked'."
Show: Adversarial security section.

**Q17. Is the adaptive attacker better than the static one?**
Say: "On the tool-agent seeded app it breached 8 of 9 pairs against 5 of 9, but the intervals are wide and overlap, and we built the pairs knowing how the seeded apps behave. It is a plumbing check, not a held-out result."
Avoid: "adaptive attacks are better".

**Q18. Do you attack real systems?**
Say: "No. Apps run in-process or on loopback with synthetic data, and an egress guard blocks other network traffic. Real-model calls are limited to one approved host and only while a call is in flight."
Be ready for: the egress guard is in-process only; it does not contain subprocesses or native code.

**Q19. How do you measure prompt-injection detection?**
Say: "We measure attack success at a stated budget, not a detector accuracy. For injection tests in the benchmark, a model fails if it outputs the hidden canary token."

**Q20. Where are the secrets? Is the API key safe?**
Say: "Keys live only in a gitignored `.env`; we scanned every commit for key patterns and found none. The key was pasted into a chat during development, so we treat it as exposed and rotate it after the event."
Avoid: opening `.env` on screen.

---

## 5. Scoring, release decisions, uncertainty

**Q21. Where is the quality score?**
Say: "There is deliberately no single score. A weighted total would need invented weights. We show per-metric failure rates with exact 95% intervals against the policy tolerance."
Show: Scorecard.

**Q22. Why did the clean app say 'Insufficient evidence'?**
Say: "With 5 to 9 evaluable cases the interval is wider than the tolerance. For example 0 failures in 7 cases still allows a true failure rate up to about 41% at 95% confidence. More tests tighten it; we did not move the threshold to get a nicer answer."

**Q23. Where does the 10% tolerance come from?**
Say: "It is an example in an example policy, labelled so. In real use the owner supplies the policy. We did not invent a recommended threshold."

**Q24. Can it ever say Release?**
Say: "Yes, when every required metric's interval is inside the tolerance. Release also requires a human sign-off. In the demo the sample sizes are too small to get there."

**Q25. How do you explain a recommendation?**
Say: "The 'Why' list states, per metric, the failures, the interval and where it sits against the tolerance. Every failure links to an evidence key in the ledger."

**Q26. Why are intervals so wide?**
Say: "Small samples. That is honest. Raising the test budget (up to 40 here) and the suite size tightens them."

---

## 6. Evidence, audit, guardrails

**Q27. How do you prove the results are real?**
Say: "Each result is an event in a hash-chained ledger. We regenerate the report from it byte-for-byte, and editing one stored event in a copy is detected. The verifier checks this live."
Show: `python -m uv run python -m qe.demo.jury_check runs scn-<id>`.

**Q28. Can someone forge the ledger?**
Say: "With write access to the file they could rebuild a consistent chain. The ledger is not signed and there is no automatic external anchor; we list that as a known limit."

**Q29. Can a model write fake evidence?**
Say: "No. The ledger rejects evidence, verdicts and decisions written by a model; models can only write drafts. Sign-off is a human-only event. This is enforced in code and tested."

**Q30. How do you satisfy the guardrails in the brief?**
Say: "Sandbox apps only, synthetic data, an egress guard, a call cap for real models, a hash-chained audit log, telemetry of our dependencies switched off, and human sign-off for the decision."

---

## 7. Real models and the benchmark

**Q31. Does it work with real LLMs?**
Say: "It is integrated through OpenRouter: a real tester model drafts risks and tests, and a real model can run as the target. A first real run failed our clean control because of bugs in our own checks; we fixed them and added regression tests, but could not re-run live because the free quota ran out. So it is a working integration, not a validated result."
Show: the guide section on this run. Avoid: any claim about real-model accuracy.

**Q32. Why a different target model than requested?**
Say: "The requested Qwen model id does not exist on OpenRouter and the Gemma free models were rate limited, so we used a free Laguna model. It is a free, different-family stand-in."

**Q33. What does the model benchmark do?**
Say: "You choose any models, simulated references or real OpenRouter ids. They all answer the same generated suite: grounded questions, false premises, unanswerable questions and hidden injections. The dashboard shows five metrics per model with intervals side by side, and claims a difference only when the intervals do not overlap."

**Q34. Which model is best?**
Say: "We make no ranking claim; with small suites the intervals overlap, and the dashboard says so. The simulated reference models behave as designed: the faithful one passes, the hallucinator fails abstention, the injectable one fails injection."

**Q35. What happens on rate limits?**
Say: "Calls are paced and retried. A call that still fails is recorded as missing evidence and never counted as a failed test; we fixed a bug where it was."

---

## 8. Scope, honesty, comparison

**Q36. What is unique compared with DeepEval, RAGAS or Promptfoo?**
Say: "Test generation, red teaming and release recommendations exist elsewhere, and we did not benchmark against those tools. What we add and can demonstrate: an auditable ledger with replay and tamper detection, intervals everywhere with insufficient evidence as a valid answer, a built-in clean control, models that can only propose, and no invented composite score. We designed adapters so those tools could sit behind our ports; they are not installed in this build."

**Q37. What did you borrow?**
Say: "No third-party code is vendored. Ideas from open-source evaluation frameworks were re-implemented; a notices file lists the integrations."

**Q38. Is the seeded-defect approach biased?**
Say: "Yes. Seeded defects are easier to detect than natural ones, and we wrote the attacks knowing the seeded apps. A natural-defect track and held-out families are planned but not evaluated."

**Q39. Is the sandbox app realistic?**
Say: "No. It is a small fictional carrier with a keyword retriever and a deterministic stand-in model. It exists to give ground truth for defects."

**Q40. Can I test my own app?**
Say: "Not yet. Today it tests the two bundled apps. Connecting your own endpoint and policy file is the first next feature."

**Q41. What would you do with another week?**
Say: "Own-app endpoint and policy upload, free-text grounding with entailment, a measured detection accuracy against human labels, re-validating the real-model run, and running monitoring."

**Q42. What was the hardest problem?**
Say: "Telling a model failure from a checker failure. Our own clean control exposed three bugs in our checks on real-model output, which is exactly why the control exists."

**Q43. How does it scale?**
Say: "We make no scaling claim. Each run is a local ledger; storage is built behind an interface so a database could replace it."

**Q44. What is the business or social impact?**
Say: "We did no market research and make no sizing claim. The value we can point to is evidence a team can audit before shipping an LLM feature."

---

## 9. When you do not know

1. Say what you know, then what you do not: "We have not measured that."
2. Say how you would measure it: "We would label a sample and compare with the detections."
3. Point to the limit that is already written down: slide 11, `docs/JURY_GUIDE.md` section 5.
Never invent a number, a benchmark, or a comparison.

## 10. If the demo breaks
| Problem | Do this |
|---|---|
| Server will not start / port busy | Use another port: `--port 8791`. Open the pre-generated scenario |
| Scenario run is slow | Use simulated mode (about 10 seconds). Do not use real mode live |
| Real model returns 429 | Say it is the free tier's rate limit; switch to simulated; point to "missing evidence, not failures" |
| Page looks wrong | Show the saved screenshots in `docs/`, or the slide deck `docs/presentation/index.html` |
| A check fails in the verifier | Say it is a real finding and read the failing line; do not hide it |

## 11. Before you walk in
- Generate one scenario in advance and note its id for `jury_check`.
- Open the slide deck and the dashboard in separate tabs.
- Close anything showing `.env` or a terminal with keys.
- Rehearse questions 5, 11, 17, 22, 31 and 36 out loud; they are the ones that probe the honest limits.
