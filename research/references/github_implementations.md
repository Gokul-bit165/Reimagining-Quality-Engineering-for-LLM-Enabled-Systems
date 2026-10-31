# GitHub / Implementation Notes

**No source trees were inspected.** The list below records repositories *named in sources I read*, what the source says they do, and what to verify. "Implementation exists" ≠ "feature is production-grade."

| Repo / project | Source of mention | Claimed function | Verify next |
|---|---|---|---|
| HazyResearch/ncm | README fetched (✔P) | NCM generation models + eval scripts; MIT | Not needed unless NCM interpretation (a) |
| awslabs/generative-ai-toolkit | Cited in arXiv:2601.18827 (✔S) | Reference implementation for structural testing | Trace assertion API, mocking approach, license |
| UKGovernmentBEIS/inspect_ai | Secondary sources | Eval framework: dataset→solver→scorer, sandboxes | LICENSE (MIT vs Apache-2.0 conflict) |
| safety-research/petri → Meridian Labs inspect_petri | Anthropic post (✔S), docs (✔S) | Auditor agent for behavioral probing; MIT | Seed format, judge rubric, extensibility |
| douyipu/ajar | arXiv:2601.10971 (✔S) | Adaptive multi-turn jailbreak orchestration via MCP services | Attack services, tool simulation |
| ethz-spylab/agentdojo (○R path) | AgentDojo paper (✔S) | Environments, tasks, attacks, defenses | How to add a custom environment (key to O2) |
| uiuc-kang-lab/AdaptiveAttackAgent | AutoDojo page (✔S) | Adaptive attacks vs IPI defenses | |
| microsoft/PyRIT | secondary | Orchestrators, targets, converters, scorers, memory | Current API; scorers' reliance on LLM judges |
| NVIDIA/garak | secondary | Probes/detectors/harnesses | Agent/tool coverage |
| promptfoo/promptfoo | secondary | Eval + red-team; plugins incl. MCP & memory poisoning | Post-acquisition governance; plugin outcome oracles |
| confident-ai/deepeval, deepteam | docs (✔S) | Metrics, Synthesizer, red-team | Synthesizer filter/evolve code; agent metrics' judge dependence |
| explodinggradients/ragas | docs (✔S) | Metrics, KG-based testset generation | Test-set diversity controls |
| langfuse/langfuse | press/clarifications page (✔S) | Tracing, evals, datasets, experiments; MIT | Evaluator execution model; OTel ingestion |
| Arize-ai/phoenix, Arize-ai/openinference | docs (✔S) | Tracing, evals, experiments | License terms (repo has IP notice) |
| truera/trulens | blog (✔S) | OTel tracing, feedback functions | Agent trajectory metrics code |
| mlflow/mlflow | docs (✔S) | Scorers/judges, `make_judge`, alignment | Judge alignment optimizers |
| UW-Madison-Lee-Lab/LLM-judge-reporting | arXiv:2511.21140 (✔S) | Judge-corrected reporting | Estimators for our metrics |
| open-telemetry/semantic-conventions-genai | secondary (◐2) | GenAI/MCP conventions (Development) | Current attribute set; release tags |

## Feasibility readings (from sources, not code)
Established: tracing/OTel, judge scoring, dataset-from-trace workflows, red-team probe libraries, sandboxed agent evals. Prototype-level (research code): adaptive attackers (AJAR/AutoDojo), structural testing reference implementation. Not found as software: method-diverse verifier independence measurement; environment synthesis for arbitrary apps; coverage-guided generation for LLM apps.
