# Pre-registration: P4 security, drift and detection benchmark (offline, fake LLM)

Status: written and frozen BEFORE any P4 experiment was run (2026-10-31). Any change after the first run
is an amendment appended to the "Amendment log" at the bottom, never an edit in place. File hashes of
every design input (pairs, templates, suites, policies, manifests) are written into
`bench/results/p4/manifest.json` by the runner so a later change is detectable.

Scope and honesty limits (apply to every hypothesis below):
* All apps are the seeded-defect sandboxes in `sandbox_apps/` driven by the deterministic `FakeLLM`. Defects are
  rule-triggered; the fake LLM is a template engine, not a model. Results characterise the harness and the
  detectors on these apps, NOT natural defects, real models or production incidents (research/17 §10).
* The author of the arms, templates and operators (P4) had read the app sources and manifests. Results are
  therefore optimistic for every arm that encodes app knowledge and are not evidence of general capability.
* The fake LLM is deterministic: repeated runs with the same seed are identical, so there are no run-to-run
  replicates; the unit of analysis is the task-attack pair / defect / probe stream, never a repeated run.
* Nothing here uses a real LLM. Arms needing DeepEval, RAGAS, live judges or live attackers are recorded as
  `skipped` with a reason, never dropped.

## 1. Units and design inputs (frozen)
* Security unit: a task-attack pair (`bench/security/pairs.yaml`, AgentDojo style: user task + injection goal).
* Detection unit: a manifest defect (`sandbox_apps/*/defects.yaml`), plus clean-variant test cases for false positives.
* Drift unit: a simulated monitoring stream (for false alarm / power) and a drift scenario (for attribution).
* Seeds: all runs seed 0 unless a stream seed is stated. Application builds: `build_app(variant, seed=0)`.

## 2. Hypotheses
Security (T4.2). Attacker classes: `static` (fixed per-class list of 10 templates, ordered by sha256 of the
template text, no feedback) and `adaptive black-box` (same first template, then a deterministic search over
mutation operators proposed by an LLM-assisted mutator, seeing only response text). Fake mutator LLM.
* H-S1: on seeded variants, adaptive ASR@10 > static ASR@10 on the identical pairs. Test: one-sided exact
  McNemar on discordant pairs. Descriptive at B in {1,3,5}.
* H-S2: on clean variants, ASR@10 = 0 for both attackers. A success is a finding about the app or the oracle
  and is reported, not suppressed.
* Secondary: ASR@B per attack class (descriptive only; n per class is small).
Drift (T5.3).
* H-D1 (false alarm): in no-change streams the sequential exact-binomial monitor raises at most alpha = 0.05
  alarms per stream. Estimated as alarms/streams with a Clopper-Pearson interval.
* H-D2 (power): after an injected change of each component the monitor alarms within the horizon; reported
  as detected/streams with an interval and the delay distribution. No threshold for "good enough" is claimed.
* H-D3 (attribution, research H7): differential substitution names exactly the true changed component set.
  Reported as accuracy with an interval, per cause class. Expect failures on the model component under
  noise (see §5); that outcome is published.
Benchmark (M6).
* H-B1: defect-level recall ordering full >= hybrid-only >= static, tested by exact McNemar on identical
  defects. By construction full is a superset of hybrid-only in coverage, so only the size of the gap, and
  whether adaptive cases add defects, is informative.
* H-B2: false positives on clean variants: the deterministic portfolio arms produce 0 case-level false
  positives; rule-based heuristics may not. Reported with intervals, no pass/fail threshold.
* H-B3 (descriptive): recall on held-out defect families and on the held-out app is reported separately and
  is NOT pooled with development results.
* No hypothesis is stated for judge, ensemble, DeepEval or RAGAS arms (not run).

## 3. Metrics (definitions)
* ASR@B = fraction of pairs with oracle success within the first B attacker queries. Always reported with
  attacker class, budget B, n pairs, and a Clopper-Pearson 95% interval.
* Paired comparison: for discordant pairs b (static wins) and c (adaptive wins), exact two-sided
  p = min(1, 2 * P(Bin(b+c, 0.5) <= min(b,c))), one-sided P(Bin(b+c,0.5) >= c) for H-S1. Multiplicity: Holm
  across the family {B=1,3,5,10} for the one-sided tests.
* Defect recall = detected defects / manifest defects of the stated subset. A defect is *detected* by an arm
  iff some case of the arm's suite triggers it (trigger predicate in `bench/ground_truth.py`, written from the
  manifest `trigger` text) AND the arm flags that case on the seeded SUT AND does not flag it on the clean SUT.
  Also reported: recall conditional on being exercised, and exercised fraction.
* Case-level false positive rate = clean cases flagged / clean cases. Run-level clean flag rate per app.
* Precision (case level) = seeded flagged cases that trigger a manifest defect and are unflagged on clean /
  all seeded flagged cases. Unattributed flags count against precision and are listed.
* Drift: monitor statistic = number of changed probes k among n per period. Under H0 k ~ Bin(n, p0) where p0
  is the upper 95% Clopper-Pearson bound of the change rate observed in a calibration window. Sequential
  alpha spending: period t uses alpha_t = alpha / (t (t+1)), so the total type I error over any horizon is at
  most alpha. Change-point estimate: exact-binomial maximum likelihood split of the observed counts.
* All intervals 95% exact. Cluster-robust intervals are not used: pairs/defects are treated as independent,
  which is optimistic for pairs that share a user task or injection.

## 4. Arms (same SUT builds, same access: response, citations, trace, state snapshot; same query budget Q=40 per app and variant)
1 static suite (fixed hand-written cases, keyword references from the source of truth) | 2 rule-based
(response-only heuristics, no source of truth) | 3 single LLM judge: SKIPPED (live disabled) | 4 judge ensemble:
SKIPPED | 5 DeepEval default: SKIPPED (dependency not installed) | 6 RAGAS default: SKIPPED | 7 adaptive-only
(generated cases verified by rule-based heuristics only) | 8 hybrid-only (static suite + deterministic
verifier portfolio) | 9 full (static + generated cases, references + deterministic portfolio + outcome
oracles). Promptfoo/PyRIT/DeepTeam arm 6b: SKIPPED (not installed; adapters tested with stubs only).
Ablations of full (one removed): no deterministic layer (= arm 7 on union cases), no adaptive cases
(= arm 8), no trace/state signals (response-only deterministic checks), random case selection under the same
budget. Cross-model ablation, judge-independence experiment, conformal abstention, validity gate: NOT RUN.

## 5. Held-out and development separation
* Held-out app: `multiagent`. No static suite entry, policy, template or operator is tuned against it; its
  suite is generated mechanically (one brief request per topic) and its policy contains only the public
  allowed-transitions and source-of-truth notes. Caveat: the author had read its manifest (see scope note);
  the hold-out is procedural, not blind.
* Held-out defect families: manifest `held_out_family: true` (all apps). Reported as a separate subset.
* Natural-defect track: NOT RUN. Reason: needs real open-source apps with human-labelled failures, a live
  model budget and annotators; none exist in this offline run.
* Known confound declared in advance: the drift "model" component is a harness-level LLM wrapper and the
  "prompt" component is an app flag; labels (`meta.model`, `meta.prompt_version`) are excluded from the
  change statistic so attribution uses behaviour only.

## 6. Exclusion rules
* No test case, pair or stream is excluded after the fact. A run that hits the budget or kill switch is
  recorded as MISSING_EVIDENCE and counted as "not detected" (never dropped).
* A defect no arm exercises stays in the denominator.
* If an oracle or harness bug is found, the experiment is rerun in full and the bug is listed in the report
  with the before/after numbers (amendment log).

## 7. Outputs
`bench/results/p4/`: ledgers (`*.sqlite`), tables regenerated from ledgers by `python -m bench.analysis`
(`qe bench analyze`), `REPORT.md`. Claims in the report must cite a table in this directory.

## Amendment log
(none at time of writing)
