# 09 — Grounding, Fact Verification and Hallucination

## State of detection (verified)
- Detectors, including LLM-judge approaches, remain **modest**; FaithBench reported near-chance for many methods (as summarized in Vectara's paper arXiv:2505.04847 ✔S). Small fine-tuned detectors can match or beat zero-shot LLM judges on RAGTruth/TofuEval (same source). Vectara's own FaithJudge (few-shot human-annotated hallucinations) is an improvement claim by a vendor.
- Embedding-similarity-only detection judged insufficient for production RAG in a conformal-calibration study (arXiv:2512.15068 ✔S, preprint, not read in full).
- Cascade/decision-model verifiers: cheap but may accept more unsupported claims (arXiv:2610.20634 ✔P).
- FActScore, SelfCheckGPT, ALCE, TRUE, HaluEval, RAGAS, ARES: foundational ○R — not re-verified.

## Required structure: one evidence record per claim
| Field | Meaning |
|---|---|
| claim_id, claim_text | atomic claim extracted from the response (extraction method + version logged) |
| source_ref | document/chunk ID + version/hash (None if absent) |
| evidence_span | character offsets in the source |
| method(s) | deterministic / NLI / LLM / decision-model, each with version |
| per-method verdict + score | recorded separately, never overwritten |
| aggregate verdict | one of the six states below |
| confidence | calibrated value + calibration set ID |
| provenance | trace span IDs; whether source was in retrieved context |

## Six states — operational definitions
| State | Definition (proposed) | How established |
|---|---|---|
| **Supported** | Evidence span entails the claim | verifier agreement + span located |
| **Contradicted** | Evidence span contradicts the claim | NLI/LLM + deterministic where numeric |
| **Partially supported** | Some atomic sub-claims supported, others not | re-decompose |
| **Unsupported** | Relevant source reviewed; no entailing/contradicting span | exhaustive check within retrieved context |
| **Unverifiable** | Claim is not checkable against available sources (opinion, future, out-of-scope) | classifier + human sample |
| **Source unavailable** | Cited/needed source cannot be fetched or is missing from the corpus snapshot | deterministic |

Key distinction: **unsupported by retrieved context** (RAG faithfulness failure) vs **false in the world** (factuality failure) — a claim can be unsupported-by-context but true. Report both axes; never merge them.

## Where deterministic checks should override
Citation existence (does the ID/URL resolve to a chunk in the corpus snapshot), quote-in-source substring match, numeric/date/entity equality, schema validity, forbidden-content patterns. These are exact and cheap; neural verifiers should not be allowed to overrule them.

## Hybrid verification architecture (proposal, H-het)
1. **Deterministic layer** (exact checks) →
2. **Entailment layer** (NLI / fine-tuned detector with span output) →
3. **Generative judge layer** only for residual / disagreement cases →
4. **Abstain/human** when verifiers disagree on a high-impact claim or calibrated confidence is low.
Aggregation must record **which layers fired**, and the portfolio must be audited for n_eff (`03`).

## Limitations to carry into every report
- Claim decomposition is itself an LLM-mediated step with errors (missed/merged/invented claims).
- NLI models degrade out of domain; long-context entailment is weak (○R; not verified here).
- LLM judges: verbosity/self-preference biases; ~positional biases (○R); attackable (`10`).
- Source credibility assessment, multi-hop and knowledge-graph verification, and conflicting-evidence resolution were **not investigated** this session.
- **No perfect hallucination detection is promised**; targets are measured precision/recall with CIs against human adjudication, per domain.

## Calibration and release effect
- Calibrate with a labelled set per domain/app; report ECE with caution (binning-sensitive) and Brier; conformal sets/abstention for the decision layer (arXiv:2604.15302, 2608.12970 ✔S).
- Ambiguous evidence (unverifiable / disagreement / source unavailable) should **not silently count as pass or fail**; AGO (arXiv:2610.01218 ✔S) models missing data and judge error as explicit decision outcomes — a design worth adopting; thresholds remain policy inputs, not constants we pick.
