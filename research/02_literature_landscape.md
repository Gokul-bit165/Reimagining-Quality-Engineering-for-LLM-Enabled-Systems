# 02 — Literature Landscape (verified items only; see tags in README)

Dates are arXiv submission dates unless noted. "Peer-reviewed" is stated only where a venue page was seen.

## A. Judges, ensembles, calibration
| Work | Status | Key point | Tag |
|---|---|---|---|
| *Nine Judges, Two Effective Votes* — G. Kohli, arXiv:2605.29800 (28 May 2026); listed on NeurIPS 2026 virtual site | preprint + NeurIPS 2026 listing | 9 frontier judges / 7 families / 3 NLI datasets ≈ 2 effective independent votes (Kish n_eff ≈ 1.9–2.5); panel never meaningfully beat best single judge; aggregation algorithms close ≤11% of gap | ✔S |
| *CARE: Confounder-Aware Aggregation* — Zhao, Shin, Huang, Namburi, Sala; ICML 2026 poster | peer-reviewed (ICML 2026 page seen) | Models shared confounders (verbosity, style) across judges; claims up to 26.8% error reduction on 12 benchmarks | ✔S |
| *Noisy but Valid: Robust Statistical Evaluation of LLMs with Imperfect Judges* — arXiv:2601.20913 | preprint | Uses a small human-labelled calibration set to estimate judge TPR/FPR and correct inference | ✔S |
| *How to Correctly Report LLM-as-a-Judge Evaluations* — arXiv:2511.21140 (code: UW-Madison-Lee-Lab/LLM-judge-reporting) | preprint | Corrects naive scores using judge sensitivity/specificity | ✔S |
| *Diagnosing LLM Judge Reliability: Conformal Prediction Sets and Transitivity Violations* — arXiv:2604.15302 | preprint, under review | Reliability varies more by criterion than by judge | ✔S |
| *Black-Box Reliability Certification for AI Agents via …* — arXiv:2602.21368 | preprint | Conformal + self-consistency, API-only, coverage guarantee claim | ✔S (title truncated in my capture) |
| *Stop Overvaluing Multi-Agent Debate* — Zhang et al., arXiv:2502.08788 (v3 Jun 2025) | preprint | 5 MAD methods × 9 benchmarks × 4 models: debate generally fails to beat CoT / self-consistency; model heterogeneity helps | ✔S |
| *Security in LLM-as-a-Judge: A Comprehensive SoK* — Masoud et al., arXiv:2603.29403 (31 Mar 2026) | preprint survey | 45 core studies of 863; judge manipulation ASR >75% in some settings | ◐2 (via aggregator) |
| *JudgeDeceiver* — Shi et al., arXiv:2403.17710 | preprint (2024) | Optimization-based injection against LLM judges | ✔S |

## B. JEV cluster (see `04`)
arXiv:2609.26550 (CMU authors) ✔P · 2610.20634 ✔P (abstract) · 2609.29769 ✔S · 2610.17820 ✔S · 2609.27678 ✔S · 2610.02076 (Microsoft authors) ✔S.

## C. Hallucination / grounding
| Work | Note | Tag |
|---|---|---|
| Vectara *Benchmarking LLM Faithfulness in RAG with Evolving Leaderboards* — arXiv:2505.04847 | Reports detectors (incl. LLM-judge) remain weak on AggreFact/RAGTruth/TofuEval/FaithBench; proposes FaithJudge | ✔S |
| RAGTruth (ACL Anthology) | ~18,000 naturally generated RAG responses with word-level hallucination labels | ✔S |
| Conformal hallucination work: arXiv:2604.13991 (adaptive conformal, factuality); arXiv:2512.15068 (conformal calibration of detectors; finds embedding-only detection inadequate) | preprints | ✔S |
| FActScore, SelfCheckGPT, ALCE, TRUE, HaluEval, RAGAS (paper) | Foundational | ○R |

## D. Testing LLM apps / agents
| Work | Note | Tag |
|---|---|---|
| *Automated structural testing of LLM-based agents* — Kohl et al. (BMW Group, AWS), arXiv:2601.18827 (25 Jan 2026) | OTel traces + LLM mocking + assertions; test pyramid; open-source reference implementation (awslabs/generative-ai-toolkit, as cited in paper) | ✔S |
| *Bidirectional Empowerment of Metamorphic Testing and LLMs: A Systematic Survey* — Zheng et al., arXiv:2605.13898 (12 May 2026) | Covers MT for LLMs, RAG, dialogue, agents | ✔S |
| *MetaRAG* — Sok, Luz, Haddam, arXiv:2509.09360 (Sep 2025); workshop paper (IAAI @ ECAI 2025, CEUR) | Metamorphic hallucination detection for RAG, black-box, reference-free | ✔S |
| *LeCov: Multi-level Testing Criteria for LLMs* — arXiv:2408.10474 | Coverage criteria + coverage-guided testing; relies on internals (white-box) | ✔S |
| *S-Eval* — Yuan et al., arXiv:2405.14191 | Risk-taxonomy-driven LLM test generation + selection; 220,000 prompts (safety domain) | ✔S |
| *ReliabilityBench* — arXiv:2601.06112 | Reliability surface R(k, ε, λ): repeated runs × perturbations × injected faults | ✔S |
| τ-bench — Yao et al., arXiv:2406.12045 (2024) | Introduces pass^k; GPT-4o pass^8 <25% in retail (as reported) | ✔S |
| RAG-X (arXiv:2603.03541), Doctor-RAG (arXiv:2604.00865) | Retrieval/generation attribution; trajectory-level failure diagnosis for agentic RAG | ✔S |

## E. Security
| Work | Note | Tag |
|---|---|---|
| *The Attacker Moves Second* — Nasr, Carlini, Sitawarin, Schulhoff, … Tramèr, arXiv:2510.09023 (10 Oct 2025) | 12 defenses bypassed, ASR >90% for most; originals reported near-zero | ✔S |
| AgentDojo — Debenedetti et al., arXiv:2406.13352 | 97 tasks / 629 security cases (v1); extensible; state-based utility & security | ✔S |
| AutoDojo — Ma et al., arXiv:2606.15057 (Jun 2026) | Cheap black-box adaptive attack raises ASR against defenses that look strong under static injections | ✔S |
| AdapTools (arXiv:2602.20720); AJAR (arXiv:2601.10971, code: douyipu/ajar); arXiv:2606.10525 (GCG/TAP in AgentDojo) | Adaptive/automated injection & jailbreak orchestration | ✔S |
| PyRIT paper arXiv:2410.02828 | Microsoft red-team framework | ◐2 (cited by a catalog page) |
| Petri (Anthropic, Oct 2025; now Meridian Labs/UK AISI "Inspect Petri") | Auditor-agent behavioral auditing built on Inspect | ✔S |

## F. Release gating / readiness (prior art — important for novelty)
| Work | Note | Tag |
|---|---|---|
| *Automated Self-Testing as a Quality Gate* — Maiorano, arXiv:2603.15676 | PROMOTE/HOLD/ROLLBACK from 5 dimensions; one internal multi-agent app | ✔S |
| *LLM Readiness Harness* — Maiorano, arXiv:2603.27355 | Eval + OTel + CI gates; readiness scores & Pareto frontiers | ✔S |
| *AGO AI Quality Gate* — Zeloni et al., arXiv:2610.01218 (pre-review) | Four-state decision (missing data / judge errors explicit); stratified beta-binomial gate; mandatory judge meta-evaluation | ✔S |
| *Requirements-Augmented Generation for Trustworthy Acceptance Testing of LLM-Based Software* — arXiv:2608.12970; ASE '26 (Munich, Oct 12–16 2026) | Context-aware oracles + conformal-risk-controlled cascade judging | ✔S |
| *Test Before You Deploy: Governing Updates in the LLM Supply Chain* — arXiv:2604.27789 | Deployer-side contracts, risk-category regression suites, compatibility gates | ✔S |

## G. Statistics
Miller, *Adding Error Bars to Evals*, arXiv:2411.00640 (Nov 2024) ✔S · Bowyer, Aitchison, Ivanova, *Don't use the CLT in LLM evals with fewer than a few hundred datapoints*, arXiv:2503.01747 (position paper) ✔S.

## H. Standards
OTel GenAI semantic conventions (all `gen_ai.*` still "Development"; moved to a dedicated repo 12 Jun 2026 per secondary sources) ◐2. OWASP LLM Top 10 **2026 edition (Aug 2026)** and OWASP Agentic Top 10 (ASI01–ASI10, announced 9 Dec 2025) ◐2 — primary pages not fetched.
