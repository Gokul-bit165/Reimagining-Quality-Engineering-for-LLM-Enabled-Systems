# Benchmark Inventory

"U" = unverified this session. Licensing fields intentionally left U where not seen. Do not assume commercial permissibility.

| Benchmark | Category | Source (tag) | Year | Size (as seen) | Metrics | Labels | License | Notes/limits |
|---|---|---|---|---|---|---|---|---|
| RAGTruth | Grounding/halluc. (RAG) | ACL Anthology listing (✔S) | 2024 (venue year U) | ~18,000 responses | Word-level halluc. spans; detector P/R/F1 | Human word-level | U | Summarization/QA/data-to-text |
| LLM-AggreFact | Grounding (claim support) | used in arXiv:2610.20634 (✔P) | — | 495-claim subset used | Balanced accuracy-type; paired diffs | Human | U | Aggregated from multiple sources |
| AggreFact / TofuEval / FaithBench | Faithfulness | Vectara paper (✔S) | 2022–2024 | U | Acc/F1 | Human | U | FaithBench: near-chance for many detectors (as reported) |
| HaluEval | Halluc. | ○R; used in arXiv:2609.26550 ✔P (240 evidence-grounded judgments sampled) | 2023 | U | Acc | Synthetic+human | U | Partly LLM-generated |
| FACTS Grounding | Grounding | Vectara paper (✔S) | 2025 | U | 3-judge ensemble | LLM-judged | U | LLM-judged |
| Vectara Hallucination Leaderboard | Halluc. (summarization) | arXiv:2505.04847 (✔S) | 2023– | 160+ LLMs ranked | HHEM-based rate | Model-judged | U | Summarization only |
| AgentDojo | Security (agent IPI) | arXiv:2406.13352 (✔S) | 2024 | 97 tasks / 629 sec. cases (v1) | Utility, ASR (state-based) | Programmatic | U | Four suites in later use: workspace, slack, travel, banking (✔S) |
| InjecAgent | Security | IPI-3K comparison (✔S) | 2024 | 510 cases | ASR | Programmatic | U | |
| IPI-3K | Security | AdapTools (✔S) | 2026 | 3,691 cases / 277 attack tools | ASR | — | U | |
| S-Eval | Safety | arXiv:2405.14191 (✔S) | 2024 | 220,000 prompts (20,000 base) | Risk score | Critic-LLM | U | Auto-generated |
| HarmBench / JailbreakBench / Tensor Trust | Security | ○R | 2023–24 | U | ASR | U | U | |
| τ-bench / τ²-bench | Agents/reliability | arXiv:2406.12045 (✔S) | 2024/2025 | retail, airline (+ telecom in τ²) | pass^1, pass^k | DB end-state | U | Simulated users are LLMs |
| ReliabilityBench | Reliability | arXiv:2601.06112 (✔S) | 2026 | 1,280 episodes | R(k, ε, λ) | outcome | U | |
| WebArena / OSWorld / AgentBench / BrowserGym | Agents | ○R | — | U | success rate | U | U | |
| TestBench | Test generation (code) | arXiv:2409.17561 (✔S) | 2024 | 108 Java programs | 5 aspects | executable | U | Code unit tests, not LLM-app tests |
| GBCV | Test generation (code) | arXiv:2502.02866 (✔S) | 2025 | generated | — | — | U | |
| BugsInPy-based LLM-vs-human tests | Test generation | arXiv:2606.08588 (✔S) | 2026 | 29 bugs | fault detection | — | U | |
| RewardBench / JudgeBench / RM-Bench | Judge quality | used in arXiv:2609.26550 (✔P) | 2024–25 | 400 / 350 / 80 samples used | acc | human prefs | U | RewardBench human–LLM κ=0.29 in that study |
| ContractNLI | NLI (legal) | arXiv:2609.27678 (✔S) | 2021 | U | acc | human | U | |

## Gaps (no benchmark found)
Drift across model/application versions; system-level LLM-application testing (tool vs seeded defects); generated-test quality for LLM apps; end-to-end release-decision accuracy.
