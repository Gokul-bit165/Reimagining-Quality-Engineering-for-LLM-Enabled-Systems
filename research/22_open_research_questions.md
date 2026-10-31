# 22 — Open Research Questions, Risks, and Decisions Needed

## Decisions needed from you (block product definition)
1. **Which NCM?** Next-Concept Modeling (not an evaluator) vs nonconformity measure (relevant) vs something else. (`04`)
2. **JEV scope:** treat Jev as an optional proprietary backend or require an open-weights equivalent for reproducibility? (`04`, `17`)
3. **Access assumption for the demo:** will target sandbox apps be instrumented (grey-box) or must black-box be the headline? This changes which claims are possible (`14`).
4. **Time/resources:** a deeper pass (full-text reading, competitor source review, licensing checks, dataset cards) is required before relying on any ○R/◐2 item.

## Open scientific questions
Q1 Does method-class diversity raise independent evidence (n_eff) beyond LLM-only panels? (H1)
Q2 Is cascade benefit attributable to the confidence signal or just escalation rate, across tasks? (arXiv:2610.20634 vs 2609.26550)
Q3 Do structural coverage criteria predict defect detection? (H3)
Q4 Can environment synthesis produce valid outcome oracles automatically? (H2)
Q5 What invalid-test rates do generated oracles have, and can they be bounded? (H4)
Q6 Can failures be localized from black-box evidence beyond chance?
Q7 How do conformal guarantees hold under drift (exchangeability violated)?
Q8 What is a defensible, stakeholder-elicited loss function for RELEASE/CONDITIONAL/REJECT?
Q9 How should "unverifiable" and "source unavailable" claims influence release?
Q10 How to attribute drift to model vs prompt vs corpus vs tool?
Q11 How do next-generation non-autoregressive models (e.g., NCM-style) change logit-based uncertainty methods? (speculative)

## Risks
| Risk | Why it matters | Mitigation |
|---|---|---|
| Over-claiming novelty | Release gating, generation, red-teaming all have prior art | Position on measured outcomes, not concepts |
| Evaluator integrity | Judges injectable & correlated | Isolation, deterministic overrides, independence audits |
| Benchmark gaming / seeded-defect bias | Inflated detection | Held-out families, natural-defect track |
| Proprietary dependency | Reproducibility, lock-in (Jev; OpenAI-owned Promptfoo) | Open backends; pin versions |
| Unstable standards | OTel GenAI in Development | Adapter layer, schema versioning |
| Safety of the red-team tooling | Dual use | Sandbox-only, rate limits, audit |
| False reassurance from "RELEASE" | Human over-trust | Always show access level, uncovered risk, uncertainty |
| Scope explosion | Candidate C is large | Stage by evidence; start from de-risking experiments (O1, O4) |

## Suggested next research steps (still research, not building)
1. Fetch and read primaries for items tagged ✔S that will carry weight (Kohli, Nasr et al., Kohl et al., AGO, Maiorano ×2, arXiv:2608.12970, Miller, Bowyer, AutoDojo).
2. Read OWASP LLM/Agentic Top 10 primaries; MITRE ATLAS; NIST AI RMF (not done).
3. Source-level review of Langfuse, Phoenix, DeepEval/DeepTeam, RAGAS, Promptfoo, Inspect/Petri, MLflow GenAI, TruLens (not done).
4. Dataset cards and license audit for RAGTruth, LLM-AggreFact, AgentDojo, S-Eval, τ-bench etc.
5. Targeted prior-art search for H1 (method-diverse verifier independence) and H3 (coverage criteria for LLM apps).
6. Pilot study design for O1 using an existing adjudicated claim set.

**Stop condition respected:** no code, no frontend, no agents, no final architecture, no product name. Awaiting your approval and answers above.
