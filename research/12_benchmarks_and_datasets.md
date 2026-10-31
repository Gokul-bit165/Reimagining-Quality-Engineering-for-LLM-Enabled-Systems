# 12 — Benchmarks and Datasets (inventory; licensing largely UNVERIFIED)

**Warning:** "License/commercial" cells below are mostly **unknown (U)** — I did not open dataset cards. Do not assume commercial usability. Details in `benchmarks/benchmark_inventory.md` and `benchmarks/datasets.md`.

## Coverage by category
| Category | Items (with tag) | Notes |
|---|---|---|
| Accuracy/reasoning | not surveyed in depth | General capability benchmarks are weak proxies for app quality |
| Grounding / faithfulness | RAGTruth (~18k responses, word-level labels) ✔S; LLM-AggreFact (495 claims subset used in arXiv:2610.20634) ✔P; AggreFact, TofuEval, FaithBench (as used in arXiv:2505.04847) ✔S; HaluEval ○R; FACTS Grounding (Google; ensemble of 3 judges, per Vectara paper) ✔S | Mostly summarization/QA; limited for tool/agent grounding |
| Hallucination | Vectara leaderboard (HHEM) ✔S | Leaderboard ≠ your app |
| Security | AgentDojo (97 tasks/629 cases v1) ✔S; InjecAgent ○R (IPI-3K paper compares: AgentDojo 629, InjecAgent 510 cases ✔S); HarmBench/JailbreakBench/Tensor Trust ○R; S-Eval 220k ✔S | Static; adaptive extension needed (AutoDojo ✔S) |
| Agents | τ-bench / τ²-bench ✔S; WebArena, OSWorld, AgentBench, BrowserGym ○R | Task-success oriented |
| RAG | RAGAS-generated sets (synthetic) ✔S(docs); CRAG etc. not reviewed | |
| Consistency/reliability | pass^k (τ-bench) ✔S; ReliabilityBench ✔S | |
| Safety | S-Eval ✔S; HarmBench ○R | |
| Drift | none standard found | Gap |
| Test generation quality | TestBench (class-level Java test generation, 108 programs) ✔S; GBCV (arXiv:2502.02866) ✔S; LLM-vs-human unit tests (arXiv:2606.08588) ✔S | Code-test benchmarks; **no benchmark found for generating tests for LLM applications** → gap |
| System-level app testing | none found | Gap |

## Meta-lesson
Benchmark performance ≠ release confidence. Public datasets are useful for **calibrating verifiers** (e.g., claim-support detectors) but should not be the evidence for a specific app's readiness. Contamination/overfitting risk (models and verifiers may have seen them) applies, especially to verifiers trained on RAGTruth-like data (Vectara's HHEM-2.1 reportedly trained on RAGTruth train among others ✔S).

## Frameworks (see `13` for capabilities)
OpenAI Evals, HELM, Inspect, RAGAS, DeepEval, Promptfoo, TruLens, LangSmith, Langfuse, Phoenix, Braintrust, MLflow: capability summaries in `13`; **no source-code review** done.
