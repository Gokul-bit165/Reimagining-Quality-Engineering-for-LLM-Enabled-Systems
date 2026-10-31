# 01 — Problem Decomposition

## The mandate in one line
Given an arbitrary LLM-enabled application, derive application-specific risks → generate tests (not from a hand-written prompt list) → execute → capture evidence → verify grounding → classify failures → score → recommend RELEASE / CONDITIONAL RELEASE / REJECT → human review → monitor → regress.

## Decomposition into independently researchable sub-problems

| # | Sub-problem | Why it is hard (not just "call an LLM") | Where evidence lives |
|---|---|---|---|
| P1 | **Application understanding** — infer capabilities, data sources, tools, permissions from whatever access exists | Access varies from "an HTTP endpoint" to "full repo"; inference from black-box probing is lossy | `14`, `06` |
| P2 | **Risk modeling** — turn P1 into a ranked risk register | Likelihood/impact estimation is a judgment call; no validated automatic method found | `07`, `10` |
| P3 | **Test generation without hand-made prompt sets** | Generated tests may be invalid (wrong expected behavior), redundant, or non-diagnostic | `07` |
| P4 | **Test oracles** — decide pass/fail for open-ended output | Oracle = judge; judges are biased, correlated, attackable | `03`, `08`, `09` |
| P5 | **Grounding & claim verification** | Atomic-claim pipelines and NLI have known failure modes; "unverifiable" ≠ "false" | `09` |
| P6 | **Adversarial/security testing** that proves outcomes, not detection | Static suites overstate robustness; need adaptive attackers + side-effect assertions | `10` |
| P7 | **Failure localization** (retrieval vs context vs generation vs tool vs orchestration) | Needs internal visibility or controlled interventions | `06`, `14` |
| P8 | **Measurement** — quality/safety scores with uncertainty | Small n, clustered items, noisy judges; no defensible fixed thresholds | `11` |
| P9 | **Release decision** with explanation and human gate | Decision under uncertainty; prior art exists | `18` |
| P10 | **Regression & drift** | Flaky tests (stochastic outputs), judge drift, silent provider updates | `07`, `11` |
| P11 | **Reusability** across app types and frameworks | Heterogeneous traces; unstable telemetry standards | `14` |
| P12 | **Proving it works** | Needs ground truth independent of the tool and the underlying LLM | `17` |

## Mandatory capability → sub-problem map
Dynamic test generation → P2,P3 · Evaluate an actual app → P1,P11 · Hallucination/unsupported claims → P5 · Grounding/citations → P5 · Prompt-injection/adversarial → P6 · Quality & safety measures → P8 · Explainable release recommendation → P9 · Failures→regression → P10 · Continuous monitoring → P10.

## Constraints that shape everything (from the mandate, restated as design rules)
- No arbitrary thresholds or invented scoring weights → decisions must come from calibrated, policy-declared, uncertainty-aware rules (see `11`).
- Never assume hidden reasoning is observable → use observable traces/tool events/evidence only (`14`).
- Multi-agent only where justified → default to deterministic components (`08`).
- Sandbox-only, synthetic data, authorized targets (`10`, `14`).

## What would count as success (to be refined at product-definition time)
Not "a dashboard." Success = a measured, reproducible improvement over named baselines on seeded-defect applications (detection precision/recall, localization accuracy, release-decision accuracy) **holding the underlying LLM constant**, plus generalization to at least one application not used during development. See `17`.
