# Paper Catalog

Fields: ID · Title · Authors (as seen) · Date · Venue/status · Problem · Method · Key result · Limitations · Code · Tag. Only what I actually saw is recorded; blank = not seen.

| ID | Title | Authors | Date | Status | Problem → Method → Result (as seen) | Limitations | Code | Tag |
|---|---|---|---|---|---|---|---|---|
| arXiv:2609.26550 | JEV-as-a-Judge: Accept When Confident, Escalate When Unsure | Y. Li, Y. Miao, R. Krishnan, R. Padman (CMU) | Sep 2026 | preprint | Cheap judge cost → decision-only judge + confidence-gated cascade → within ~3 pts of strong judge on text-readable verdicts; 92.5% vs 93.1% cascade on 510 pairs | One proprietary version; single annotator; not compute-matched | not confirmed | ✔P |
| arXiv:2610.20634 | Jev-as-a-Judge for RAG Claim Verification | A. Do Rosario, K. Atef | 30 Sep 2026 (v1) | preprint | RAG claim support, 495 LLM-AggreFact claims → paired comparison → tie in accuracy, 187× cost gap; more unsupported accepted; random escalation = gated | Affiliation/COI not shown | says released | ✔P |
| arXiv:2609.29769 | Jev vs. LLMs as Rubric Judges | — | 2026 | preprint | Rubric judging, 9 panels → parity in most comparisons | Behind on graded criteria | — | ✔S |
| arXiv:2610.17820 | Same Attack, Different Judge | X. Li, A. Huang, M. Zhang, Z. Liu | 2026 | preprint | Adversarial robustness of Jev vs LLM judges/classifiers | Small samples; "could be chance" | — | ✔S |
| arXiv:2609.27678 | Same Scores, Different Decisions (ContractNLI) | — | 2026 | preprint | Request-variation robustness | — | — | ✔S |
| arXiv:2610.02076 | LLM-as-Jev | Y. Li, J. Wagle (Microsoft) et al. | 2026 | preprint | Fine-tune LLMs as decision models | — | — | ✔S |
| HazyResearch/ncm (+ arXiv:2610.14162) | Next-Concept Modeling | H. Kumbong, I. Khare et al. | Oct 2026 | preprint + MIT repo | Parallel coarse-to-fine text generation | Self-reported speedups; not an evaluator | MIT | ✔P(README)/◐2 |
| arXiv:2605.29800 | Nine Judges, Two Effective Votes | G. Kohli | 28 May 2026 | preprint; NeurIPS 2026 listing | Judge-panel independence → Kish n_eff, Condorcet null → ~2 effective votes | NLI + RewardBench tasks only | — | ✔S |
| ICML 2026 poster | CARE: Confounder-Aware Aggregation | J. Zhao, C. Shin, T. Huang, S. Namburi, F. Sala | 2026 | peer-reviewed (ICML 2026) | Shared confounders in judge ensembles → latent-variable aggregation → up to 26.8% error reduction | — | — | ✔S |
| arXiv:2601.20913 | Noisy but Valid | — | Jan 2026 | preprint | Inference with imperfect judges using calibration TPR/FPR | — | — | ✔S |
| arXiv:2511.21140 | How to Correctly Report LLM-as-a-Judge Evaluations | — | Nov 2025 | preprint | Sensitivity/specificity correction | — | UW-Madison-Lee-Lab/LLM-judge-reporting | ✔S |
| arXiv:2604.15302 | Diagnosing LLM Judge Reliability | M. Gupta, D. Kumar (BITS Pilani) | Apr 2026 | preprint (under review) | Conformal set width + transitivity violations | — | — | ✔S |
| arXiv:2602.21368 | Black-Box Reliability Certification for AI Agents via … | — | Feb 2026 | preprint | Conformal + self-consistency | Title truncated in capture | — | ✔S |
| arXiv:2502.08788 | Stop Overvaluing Multi-Agent Debate | H. Zhang, Z. Cui, J. Chen, … S. Hu | Feb 2025 (v3 Jun 2025) | preprint/position | MAD vs CoT/SC baselines → debate rarely wins; heterogeneity helps | — | — | ✔S |
| arXiv:2601.18827 | Automated structural testing of LLM-based agents | J. Kohl, O. Kruse, Y. Mostafa, A. Luckow, K. Schroer, T. Riedl et al. | 25 Jan 2026 | preprint | OTel traces + mocks + assertions | Case studies | awslabs/generative-ai-toolkit (per paper) | ✔S |
| arXiv:2605.13898 | Bidirectional Empowerment of Metamorphic Testing and LLMs | Z. Zheng, Z. Zhou, Y. Xu, D. Ren, T.Y. Chen | 12 May 2026 | preprint survey | MT↔LLM | — | — | ✔S |
| arXiv:2509.09360 | MetaRAG | C. Sok, D. Luz, Y. Haddam | Sep 2025 (v2 Nov 2025) | workshop (IAAI @ ECAI 2025) | Metamorphic hallucination detection for RAG | Proprietary enterprise dataset | — | ✔S |
| arXiv:2408.10474 | LeCov | — | 2024 | preprint | LLM coverage criteria | Needs internals | — | ✔S |
| arXiv:2405.14191 | S-Eval | X. Yuan, J. Li, et al. | 2024 | preprint | Risk-taxonomy test generation, 220k prompts | Safety scope | released (per paper) | ✔S |
| arXiv:2601.06112 | ReliabilityBench | — | Jan 2026 | preprint | Reliability surface R(k, ε, λ) | — | — | ✔S |
| arXiv:2406.12045 | τ-bench | S. Yao, N. Shinn, P. Razavi, K. Narasimhan | Jun 2024 | preprint | pass^k reliability | — | sierra-research/tau-bench | ✔S |
| arXiv:2603.03541 | RAG-X | — | Mar 2026 | preprint | Decoupled retrieval/generation diagnosis (medical) | Domain-specific | — | ✔S |
| arXiv:2604.00865 | Doctor-RAG | S. Jiao, C. Huang, S. Qi, X. Wang, Y. Li, L. Yao | 1 Apr 2026 | preprint | Trajectory-level diagnosis + repair for agentic RAG | HotpotQA-centric | — | ✔S |
| arXiv:2510.09023 | The Attacker Moves Second | M. Nasr, N. Carlini, C. Sitawarin, S. Schulhoff, … F. Tramèr | 10 Oct 2025 | preprint | Adaptive attacks vs 12 defenses → ASR >90% mostly | Existence not cost | — | ✔S |
| arXiv:2406.13352 | AgentDojo | E. Debenedetti et al. | Jun 2024 | benchmark (venue ○R) | 97 tasks/629 security cases | Static v1 | ethz-spylab/agentdojo (○R) | ✔S |
| arXiv:2606.15057 | AutoDojo | X. Ma, T. Li, C. Xiao, Z. Yu, N. Zhang, Y. Vorobeychik | 13 Jun 2026 | preprint | Adaptive IPI vs defenses | — | — | ✔S |
| arXiv:2602.20720 | AdapTools | — | Feb 2026 | preprint | Adaptive tool-based IPI; IPI-3K | — | — | ✔S |
| arXiv:2601.10971 | AJAR | Y. Dou, W. Yang et al. | Jan 2026 (v2 Mar) | preprint | Adaptive multi-turn jailbreak orchestration (MCP) | — | douyipu/ajar | ✔S |
| arXiv:2606.10525 | Assessing Automated Prompt Injection Attacks in Agentic Environments | — | 9 Jun 2026 | preprint | GCG/TAP in AgentDojo | — | — | ✔S |
| arXiv:2403.17710 | JudgeDeceiver | J. Shi et al. | 2024 | preprint | Injection vs LLM judges | — | — | ✔S |
| arXiv:2603.29403 | Security in LLM-as-a-Judge: SoK | Masoud et al. | 31 Mar 2026 | preprint | Survey | via aggregator | — | ◐2 |
| arXiv:2603.15676 | Automated Self-Testing as a Quality Gate | A.C. Maiorano | Mar 2026 | preprint | PROMOTE/HOLD/ROLLBACK | one internal app | — | ✔S |
| arXiv:2603.27355 | LLM Readiness Harness | A.C. Maiorano | Mar 2026 | preprint | Eval+OTel+CI gates | — | — | ✔S |
| arXiv:2610.01218 | AGO AI Quality Gate | G. Zeloni et al. | 2026 | preprint (pre-review) | Four-state, beta-binomial gate, judge meta-eval | industrial engagements | self-hosted platform | ✔S |
| arXiv:2608.12970 | Requirements-Augmented Generation for Trustworthy Acceptance Testing | — | 2026 | ASE '26 (Munich, 12–16 Oct 2026) | Oracles + conformal cascade | — | — | ✔S |
| arXiv:2604.27789 | Test Before You Deploy | — | Apr 2026 | preprint | Deployer contracts + gates | — | — | ✔S |
| arXiv:2411.00640 | Adding Error Bars to Evals | E. Miller (Anthropic) | Nov 2024 | preprint | CLT/clustered SE, power | — | — | ✔S |
| arXiv:2503.01747 | Don't use the CLT in LLM evals with fewer than a few hundred datapoints | S. Bowyer, L. Aitchison, D.R. Ivanova | Mar 2025 | position paper | CI methods at small n | venue not verified | — | ✔S |
| arXiv:2505.04847 | Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards | Vectara | May 2025 | preprint | HHEM, FaithJudge | vendor | — | ✔S |
| arXiv:2403.01216; 2407.00499; 2604.13991; 2512.15068 | Conformal-for-LLM works (API-only CP; ConU; adaptive CP factuality; conformal hallucination) | various | 2024–2026 | preprints | Coverage guarantees for LLM outputs | exchangeability | — | ✔S |
