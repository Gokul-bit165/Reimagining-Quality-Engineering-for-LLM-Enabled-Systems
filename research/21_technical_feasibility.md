# 21 — Technical Feasibility Assessment

Classification legend: **EP** existing proven technology · **OS** open-source implementation available · **EI** requires engineering integration · **OR** requires original research · **SP** speculative / currently impractical.

| Component | Class | Basis | Main risk |
|---|---|---|---|
| OTel trace ingestion, span storage | EP/OS | OTel, Phoenix/Langfuse/TruLens use it (✔S/◐2) | `gen_ai.*` instability |
| Evidence store (append-only, hashed) | EI | standard engineering | Schema design |
| Deterministic claim/citation/schema checks | EP | exact checks | Coverage of claim types |
| Claim decomposition + verification pipeline | OS/EI | RAGAS, FActScore-style (○R), MetaRAG ✔S | Error propagation |
| NLI/fine-tuned detectors | OS | Vectara HHEM etc. ✔S | Domain shift; contamination |
| Decision-only judges (e.g., Jev) | EP (proprietary) | arXiv:2609.26550 ✔P | Opacity, lock-in; accepts more unsupported claims in one study |
| LLM-judge layer | EP | widespread | Correlation, bias, attackability |
| Method-diverse portfolio with measured independence | **OR** | Hypothesis H1 | May not beat best single verifier |
| Conformal abstention / gated cascades | OS technique, EI | arXiv:2403.01216, 2608.12970 ✔S | Exchangeability under drift |
| Bayesian release gate | EI | AGO ✔S, Miller, Bowyer | Policy elicitation |
| Test generation from documents | OS | RAGAS, DeepEval | Oracle validity |
| Risk-taxonomy-driven generation | OS/EI | S-Eval ✔S, OWASP | Likelihood/impact estimates |
| App-model extraction (traces) | EI | arXiv:2601.18827 (assertions on traces) | Unobserved paths |
| App-model extraction (repo + black-box) | **OR** | no validated method | Static analysis limits |
| Coverage-guided generation for LLM apps | **OR** | H3 | Coverage–defect correlation unknown |
| Adaptive attacker agents | OS/EI | AJAR, PyRIT, Petri, AutoDojo ✔S | Cost, safety controls |
| Outcome-oracle harness for known env | EI | AgentDojo ✔S | Hand-built per app |
| **Environment synthesis for arbitrary apps** | **OR / SP** | None found | Stateful tools, auth, side-effects |
| Failure localization (grey-box) | EI | RAG-X, Doctor-RAG ✔S; substitution | Needs hooks |
| Failure localization (black-box) | **OR / SP** | None validated | Fundamental information limit |
| Regression minimization for stochastic failures | **OR** | H5 | Flakiness |
| Drift attribution | **OR** | H7 | Confounded changes |
| Durable orchestration/replay | EP | workflow engines (○R/judgment) | Replay of non-deterministic LLM calls requires recording |
| Gateway capture/fault injection | EP/EI | standard proxy tech | Streaming/provider quirks |
| Human review workflow | EP | — | Reviewer fatigue |
| Sandbox isolation & canary sinks | EP/EI | containers, network policy | Operational care |

## Where feasibility is weakest
1. Black-box root-cause localization (information-theoretically limited).
2. Arbitrary-app environment synthesis for outcome-based security testing.
3. Automatic app-model construction without instrumentation.
4. Proving method-diverse verification adds independence.

## Where feasibility is strong
Trace capture; deterministic checks; claim-level verification pipelines; statistical estimators with intervals; CI-style gating; adaptive red-team orchestration against *provided* sandboxes.

## Honest limits of any system
Cannot see hidden model reasoning; cannot prove absence of failures (testing shows presence); verifier recall for subtle hallucination is imperfect; production behavior can diverge from pre-release tests.
