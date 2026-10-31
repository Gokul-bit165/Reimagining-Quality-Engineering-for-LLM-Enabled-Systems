# M4 pre-registration: static vs adaptive attackers with outcome oracles

Date: 2026-10-31. Written BEFORE the first registered run of `bench/m4_experiment.py`. The SHA-256 of this
file is recorded in the results file; the lead must commit this file before the results are accepted.

## Honest status of this experiment
* The attack pairs (`qe/crew/attack_pairs.py`), operator pool and oracles were developed and debugged
  against the sandbox apps, so outcomes on the seeded variants were observed during development
  (unit tests assert some of them). This run is therefore a **plumbing and regression check of the M4
  stack on the FakeLLM sandbox, not a held-out evaluation**.
* The FakeLLM is a regex/template engine. Whether a payload works depends on its patterns, not on model
  behaviour. **No statement about real LLM applications, real attackers or real-world ASR follows.**
* n = 12 attack pairs (unit of analysis). Pairs within a surface are correlated; intervals ignore that
  and are therefore too narrow. Per-surface counts are reported without intervals (n = 2 or 3).

## Question (hypothesis M4-A, label: hypothesis)
At an equal attempt budget, does a feedback-driven attacker find oracle-confirmed breaches that a fixed
generic wrapper list misses, and is that due to the feedback itself or only to a larger operator pool?

## Design (fixed before running)
* Environments: `sandbox_apps` toolagent and rag, variants `clean` and `seeded`, seed 0, FakeLLM, drift off.
* Pairs: the 12 in `qe/crew/attack_pairs.py` (DI-1,2; TM-1,2,3; II-1,2; RP-1,2,3; MP-1,2).
* Attacker classes (all deterministic; none uses a model):
  `static_template` (first 6 operators, no role-claim operators), `static_extended` (all 8 operators in
  fixed order), `adaptive_mutation` (same 8 operators, order chosen from the previous attempt's
  attacker-visible feedback: its own last response text and whether an attacker-controlled sink was hit).
  The adaptive and extended pools are identical by construction, so adaptive vs extended isolates the
  feedback effect; static_template vs the others includes the pool-size effect.
* Budget: up to 8 attempts per (pair, attacker); campaign stops at the first oracle breach.
  Reported budgets b in {1, 2, 4, 8}. One attempt = one fresh app instance.
* Outcome decision: only the oracles in `qe/exec/oracles.py` (canary at sink or output, protected-state
  diff, forbidden tool call with status ok, attacker marker in victim output with retrieved quotes removed,
  disallowed sink use). The attacker's text and the app's own statements are never consulted.
* Controls: (1) no-attack baseline per pair and variant (inert payload), expected 0 breaches;
  (2) all attackers against the `clean` variants, expected 0 breaches. A non-zero count in either is an
  **oracle or pair design error to investigate, reported as such**, not an attacker success.
* Statistics: ASR@b = pairs with first breach at attempt <= b, over 12; Clopper-Pearson 95% interval.
  Paired differences: Newcombe (1998) method 10 95% interval plus exact McNemar test on discordant pairs.
* Results are computed from the ledger only (`results_from_ledger`), and replaying that function on the
  stored ledger must reproduce the stored results exactly.

## Primary and secondary comparisons (seeded variants only)
1. PRIMARY: adaptive_mutation minus static_template at b = 4.
2. adaptive_mutation minus static_extended at b in {1, 2, 4, 8} (feedback effect).
3. static_extended minus static_template at b in {1, 2, 4, 8} (pool-size effect).

## Decision rules (no ASR threshold is set or implied; this is not a release criterion)
* Report "adaptive found more breaches on this toy" only if the primary interval excludes 0.
  Otherwise report "no difference demonstrated at this n", including when the point estimate is positive.
* If adaptive minus extended excludes 0 at no budget, say the advantage is attributable to the larger
  operator pool, not to feedback. If a control fails, no comparison is reported until it is explained.
* All results, including null or negative ones, are published unchanged (R1, R12).

## Not claimed
Real-model ASR; superiority of adaptive attackers in general; generalisation beyond these 12 pairs and
two sandbox apps; coverage of OWASP LLM/Agentic categories; any defense effectiveness.
External generators (Promptfoo, PyRIT, DeepTeam) are not part of this run (adapters exist and are tested
with synthetic payload files only).
