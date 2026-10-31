# 20 — Global Impact and Contribution Potential

Qualitative assessment; no impact numbers are claimed.

## Why the problem matters (evidence-backed)
- LLM apps now carry tool access and memory; OWASP separated an Agentic Top 10 from the LLM Top 10 because risk shifts from "what a model says" to "what a system does" (◐2).
- Benchmark scores overstate field reliability: τ-bench reports large drops from pass@1 to pass^8 (✔S); adaptive attacks defeat defenses that look robust under static tests (✔S).
- Teams increasingly rely on LLM judges whose independence is overstated (✔S).
- Providers can change model behavior under a fixed name (practitioner reports, ◐2) → continuous verification is a real operational need.

## Possible open-source / research contributions (all conditional on validation)
| Contribution | Value | Prerequisite |
|---|---|---|
| Seeded-defect benchmark for *testing tools* | Comparability across vendors; none found | Funding for adjudication; licensing hygiene |
| Judge-independence diagnostics (n_eff, error correlation, abstention) | Immediate use by any eval team | Adjudicated datasets |
| Framework-agnostic evidence/decision-record schema | Auditability, reproducible release evidence | Neutral governance; OTel alignment |
| Outcome-oracle harness conformance suite | Raises bar for security claims | Environment synthesis research |
| Reproducible protocol (`17`) | Lets others replicate claims | Complete package, replay mode |

## Standardization angle
A "trustworthy release certification" would be premature: certification claims require validated decision accuracy (`17`), not demonstrated. A *reporting standard* (what must accompany any release claim: n, CIs, judge validity, attacker budget, coverage of risk register, access level) is a safer, more useful target and is consistent with the error-bar literature.

## Societal risks of the work itself
Over-trust: a "RELEASE" label may be treated as safety assurance. Mitigation: always report access level, uncovered risks, uncertainty, and an "insufficient evidence" outcome. Dual use: adaptive attack generators help attackers; keep sandbox-only, rate-limited, access-controlled.

## Realism check
Value depends on measured superiority over existing tooling on held-out apps; today's evidence supports the *problem*, not yet the *solution*.
