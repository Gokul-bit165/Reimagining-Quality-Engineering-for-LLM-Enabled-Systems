# 04 — JEV and NCM Investigation

Method: exact-acronym searches (JEV, NCM, "JEV NCM"), then fetched primary pages. I did not assume expansions.

## Result in one paragraph
**JEV and NCM are not a related pair.** JEV is a *named proprietary model* ("Jev") used as a low-cost judge/verifier. NCM, in the LLM literature of 2026, is a *text-generation architecture*. A third, older and established expansion of NCM — *nonconformity measure* — fits the "calibrated release decision" theme but I cannot tell from the brief whether that is what was meant.

---
## JEV

### What it is (✔P / ◐2)
- **Jev** is TypeSafe AI's first "System One" model: a **non-generative decision model** that takes structured state plus typed questions (Choice / Noul(yes-probability) / Score) and returns **label probabilities, no text**. Publicly released in early access **15 Sep 2026**; production version cited as **jev-1.13.0** (◐2: DigitalOcean, nexos.ai, DataCamp, VKTR, vendor-announcement coverage). TypeSafe announced a $40M seed (DCVC) (◐2). It is **hosted and proprietary**; the CMU paper states its implementation is proprietary (✔P).
- Training is described by the vendor as "Reinforcement Learning for Calibrated Decisions" (◐2, LinkedIn/vendor summaries) — **not independently verifiable**; architecture details are not published in anything I read.
- Marketing claims such as "cannot hallucinate" refer to *schema validity* (cannot emit an out-of-schema value); one commentator correctly notes it can still decide wrongly (◐2). Do not treat it as correctness.

### The research literature (all 2026 preprints)
| Paper | Authors/affil. | Finding | Tag |
|---|---|---|---|
| **JEV-as-a-Judge: Accept When Confident, Escalate When Unsure** arXiv:2609.26550 | Yubo Li, Yidi Miao, Ramayya Krishnan, Rema Padman (CMU); NIST award + CMU AIMSEC funding; OpenAI researcher-access API credits | Within ~3 pts of the strongest generative judge where the verdict can be "read off" text; behind where it must be *derived* (math/code/logic). Cascade at frozen τ: 92.5% vs 93.1% for the strong judge on 510 extension pairs, 53.7% accepted. Reports no COI statement regarding TypeSafe; one annotator per item; adjudicator saw aggregate results; RewardBench human–LLM κ = 0.29; one model version; contamination unknown; repro package not confirmed | ✔P |
| **Jev-as-a-Judge for RAG Claim Verification** arXiv:2610.20634 | A. Do Rosario, K. Atef (affiliation not shown on page) | 495 LLM-AggreFact claims: accuracy statistically tied at ~187× cost gap; 15.2% disagreement; Jev accepts more unsupported claims (23.2% vs 14.1%); **random escalation matched confidence-gated cascade**; says predictions/prompts/pricing/code released | ✔P (abstract) |
| **Jev vs. LLMs as Rubric Judges: Cheaper, Faster, and Wrong in the Same Places** arXiv:2609.29769 | not captured | 9 panels / 7 benchmarks; differs significantly from an LLM judge in only 8 of 27 paired comparisons; leads on binary criteria, trails on graded | ✔S |
| **Same Attack, Different Judge** arXiv:2610.17820 | Xiang Li et al. | Adaptive attack succeeded on 5/50 vs Jev and 11/50 vs a GPT judge ("could be chance"); more exposed on judgment-heavy tasks; ASR measures *passing a message*, not downstream harm | ✔S |
| **Same Scores, Different Decisions** arXiv:2609.27678 | not captured | ContractNLI: Jev gives the most unanimous answers yet the lowest correct fraction among them → confidence ≠ correctness under request variation | ✔S |
| **LLM-as-Jev** arXiv:2610.02076 | Microsoft authors | Argues LLMs can be fine-tuned into Jev-style decision models; reports ECE/Brier | ✔S |

### Assessment
- **Established?** No. It is a ~6-week-old commercial model with an emerging independent literature. Several papers are independent of the vendor (CMU, adversarial, legal, Microsoft); I could not confirm each author's independence.
- **Relevance to the mandate:** a *component* candidate for high-volume binary checks (claim support, injection triage, routing) inside a verifier portfolio — **not** a framework. Its main plausible value is cost/latency and a confidence signal.
- **Hazards:** vendor lock-in/proprietary opacity (hard for a reproducible benchmark); probability calibration reported mostly by the vendor ecosystem; ties/disagreements hide error-type asymmetry (more false "supported"); susceptibility to adversarial inputs on judgment tasks.
- **What would make it usable:** replace by an open equivalent (e.g., fine-tuned NLI/small LM with the same typed-output interface) and treat Jev as one optional backend; always measure the false-"supported" rate separately.

---
## NCM

### Primary reading (✔P: GitHub README HazyResearch/ncm; arXiv ID from its citation block)
- **Next-Concept Modeling (NCM)**: two-stage parallel text generation — a multiscale residual-VQ tokenizer turns a sequence into a hierarchy of discrete codes; a transformer predicts the hierarchy coarse→fine, generating all positions of a level in parallel (one forward pass per level). MIT license. Self-reported "9–31× faster than strong diffusion baselines." Released checkpoints: XSum, WMT14 De–En, Sudoku, LM1B, TinyStories, OpenWebText. arXiv:**2610.14162** (Kumbong, Khare et al., Hazy Research; Oct 2026) — the arXiv abstract page itself was **blocked in this environment**, so the ID/authors rest on the README and a secondary article (◐2).
- **Metrics used:** ROUGE, sacreBLEU/chrF, Sudoku solve rates, generative perplexity under GPT-2 large. None measure factuality. A secondary write-up states "no demonstrated superiority" on safety/hallucination (◐2).
- **Relevance:** none to evaluating LLM applications, except as a possible *target model type* whose different failure modes (no left-to-right token logits) could affect logit-based uncertainty methods.

### Other expansion (not assumed): **nonconformity measure** (conformal prediction)
- Established (Vovk et al., 2005; ○R). A nonconformity measure scores how atypical a prediction is relative to calibration data; thresholding at a calibrated quantile gives finite-sample coverage under exchangeability. Applied to LLMs: arXiv:2403.01216 (API-only), arXiv:2407.00499 (ConU), arXiv:2604.13991, arXiv:2604.15302, arXiv:2602.21368, arXiv:2608.12970 (all ✔S).
- **Relevance:** high for "release readiness with quantified uncertainty" and for deciding when a judge verdict may be trusted vs sent to a human.

### Unmatched
No paper found that treats "JEV" and "NCM" together, as methods in one architecture. Other candidate meanings (e.g., Neural Cognitive Model, etc.) returned nothing relevant to LLM evaluation in my searches; absence in my searches is not proof of absence.

## Decision requested from you
Confirm which NCM you intended: (a) Next-Concept Modeling (not an evaluator), (b) nonconformity measure (recommended interpretation), or (c) something from your own materials not surfaced by searches.
