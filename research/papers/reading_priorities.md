# Reading Priorities (what to read in full next, and why)

## Tier 1 — decisions depend on these
| Paper | Question to answer by reading |
|---|---|
| arXiv:2605.29800 (Kohli) | Exact definition of n_eff, datasets, what "independent" baseline means; do conclusions hold for non-NLI tasks? |
| arXiv:2610.20634 | Task definition, escalation-control design, whether Jev vendor affiliation exists |
| arXiv:2609.26550 §threshold validation | Is the frozen-threshold protocol sound; pre-registration claims |
| arXiv:2610.01218 (AGO) | Decision model details; what is *not* covered vs our gaps |
| arXiv:2603.15676, 2603.27355 | Exact gate formulation; validation depth (one app?) |
| arXiv:2608.12970 | Oracle generation + conformal risk control; guarantees and assumptions |
| arXiv:2601.18827 | Methods for trace assertions; what can/can't be automated; repo capabilities |
| arXiv:2510.09023 | Attack budgets; which defense classes failed; implications for our attacker design |

## Tier 2 — design details
arXiv:2606.15057 (AutoDojo), arXiv:2604.00865 (Doctor-RAG), arXiv:2603.03541 (RAG-X), arXiv:2605.13898 (MT survey), arXiv:2601.06112 (ReliabilityBench), arXiv:2411.00640 and 2503.01747 (statistics), arXiv:2601.20913 & 2511.21140 (judge correction), arXiv:2512.15068 (conformal hallucination; HALT-RAG reference), arXiv:2602.21368.

## Tier 3 — context
S-Eval, LeCov, MetaRAG, τ-bench/τ²-bench, AgentDojo, AJAR, SoK on judges, Vectara leaderboard paper.

## Primary standards to fetch
OWASP LLM Top 10 2026 and Agentic Top 10 pages; MITRE ATLAS; NIST AI RMF; OTel GenAI semantic conventions (repo `semantic-conventions-genai`).

## Implementations to inspect
awslabs/generative-ai-toolkit (structural testing reference), Langfuse, Phoenix/OpenInference, DeepEval/DeepTeam, RAGAS, Promptfoo, Inspect/Inspect Petri, PyRIT (microsoft/PyRIT), Garak, AgentDojo, AJAR, UW-Madison-Lee-Lab/LLM-judge-reporting, HazyResearch/ncm (only if NCM interpretation (a) is confirmed).
