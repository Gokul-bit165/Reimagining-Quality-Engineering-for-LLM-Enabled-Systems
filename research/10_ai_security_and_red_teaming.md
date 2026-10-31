# 10 — AI Security and Red Teaming

**Scope rule:** all experiments only against authorized sandbox targets with synthetic data and test identities.

## Core finding: detection ≠ resistance, and static ≠ adaptive
1. **Static suites overstate robustness.** Nasr, Carlini, et al. (arXiv:2510.09023 ✔S) bypassed 12 published jailbreak/prompt-injection defenses with adaptive search (gradient, RL, search, human-guided), ASR >90% for most, where original papers reported near-zero. Caveat they note: the experiment shows a break *exists*, not how costly it is to find.
2. **Cheap adaptive attacks matter in agents.** AutoDojo (arXiv:2606.15057 ✔S): a black-box LLM-driven optimizer recovers attack success against defenses that look strong under static injections. Also AdapTools (arXiv:2602.20720), arXiv:2606.10525 (GCG/TAP in AgentDojo; TAP > GCG; model-dependent transfer) ✔S.
3. **A judge saying "blocked" is not a safe outcome.** The adversarial Jev study notes its ASR records whether a judge *passes a message*, not the harm that follows (arXiv:2610.17820 ✔S). Our requirement: security verdicts must be **environment-state assertions** (canary token left the boundary; forbidden tool executed; record modified), as in AgentDojo's state-based security checks (arXiv:2406.13352 ✔S).
4. **The evaluator is itself a target.** LLM judges are injectable (JudgeDeceiver ✔S; SoK ◐2). Judge inputs must be sanitized/isolated, and security tests must not rely solely on an LLM verdict.

## Standards (secondary sources only — read primaries before citing)
- **OWASP Top 10 for LLM Applications 2026 edition** (published ~3–4 Aug 2026 per several secondary sources; ◐2): prompt injection LLM01; Excessive Agency reportedly promoted to #3; System Prompt Leakage reportedly broadened to "Hidden Context Exposure." *Sources disagree on details (e.g., commentary that prompt injection falls out by incident counts vs. the formal ranking).* → fetch genai.owasp.org before citing.
- **OWASP Top 10 for Agentic Applications (ASI01–ASI10)**, announced 9 Dec 2025: goal hijack, tool misuse, identity/privilege, supply chain, code execution, memory, inter-agent comms, cascading failures, human–agent trust, rogue agents (◐2).
- MITRE ATLAS, NIST AI RMF: **not investigated** this session.

## Tooling landscape (◐2 unless noted)
| Tool | Role | Notes |
|---|---|---|
| Promptfoo | Eval + red-team CLI; vuln plugins incl. tool misuse, MCP, memory poisoning; MIT | **OpenAI announced acquisition 9 Mar 2026**, pledged to keep OSS; stars/figures vary by source |
| Garak (NVIDIA) | Probe-based scanner, model-level; "120+ categories" | Giskard (competitor) says agent tool-calls and multi-turn are outside its design — competitor claim |
| PyRIT (Microsoft) | Multi-turn orchestration (targets, converters, scorers, memory); MIT | Repo moved to microsoft/PyRIT; Azure/PyRIT archived 27 Mar 2026 (◐2); version numbers conflict across sources |
| DeepTeam | DeepEval's red-team package | ◐2 |
| Inspect + Petri | Sandboxed agent evals; auditor agent | ✔S for Petri blog |
| AgentDojo | State-based agent injection benchmark | ✔S |
| HarmBench, JailbreakBench, InjecAgent, Tensor Trust | Datasets | ○R |

## Dynamic attack generation from the application model
Inputs from `06`/`14`: tool list + schemas, permissions per tool/user role, data classification, retrieval sources (who can write to them → poisoning surface), memory stores, trust boundaries. Attack families to instantiate per surface:
| Surface | Attack | Outcome oracle |
|---|---|---|
| User input | direct injection, jailbreak, system-prompt extraction | canary in hidden context appears in output |
| Retrieved docs | indirect injection / RAG poisoning | injected instruction followed (tool call or output marker) |
| Tool outputs | injection via tool result (AgentDojo-style) | unauthorized tool call with attacker-chosen args |
| Memory | poisoning across sessions | later session behavior changed |
| Tools | excessive agency / misuse | call outside allowed-set; state diff |
| Data | exfiltration | synthetic secret observed at sink |
| Multi-agent | privilege escalation via handoff | action beyond originating role |
**Reporting:** ASR at a stated **attacker budget** (queries, tokens, wall-clock) and attacker class (static / adaptive black-box / human). Never a single unqualified ASR. Compare using paired design on identical task–attack pairs.

## Required safeguards (design constraints)
Isolated network egress with canary sinks; synthetic tenants and credentials; per-run spend and call limits; kill switch; logging of every attack for audit; no production data; no use against third-party systems.

## Not established
Whether automatic *environment synthesis* (building a sandbox harness for an arbitrary customer app so outcome oracles exist) is reliable — this is the central engineering risk for generalized outcome-based security testing (`18`, `21`).
