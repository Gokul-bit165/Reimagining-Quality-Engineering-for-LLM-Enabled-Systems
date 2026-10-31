# Source Verification Log

## Things I could NOT verify
1. **arXiv:2610.14162 (NCM) abstract page** — fetch blocked by the environment's URL allowlist. Existence/ID/authors rely on the GitHub README citation block and a secondary article.
2. **Full texts**: only the CMU JEV paper (HTML, extracted summary) and one abstract (2610.20634) were read directly; everything else ✔S is from search excerpts.
3. **Affiliations/COI**: authors of arXiv:2610.20634 not shown; independence of several JEV papers from TypeSafe not confirmed.
4. **Peer-review status**: confirmed only for Kohli (NeurIPS 2026 listing), CARE (ICML 2026), and the ASE '26 paper listing; MetaRAG is a workshop paper. All others treated as preprints.
5. **Licenses**: no dataset or repo license was verified from primary files.
6. **Foundational papers** (○R): venues/years recalled from memory.
7. **Competitor features**: no hands-on testing or code review.
8. **OTel stability and repo move**: from secondary sources; primary repo not read.
9. **OWASP 2026 lists**: from secondary sources; wording of entries not checked against the primary.
10. **Model names in cited papers** (e.g., judge models they call "GPT-6", "Gemini-3.5-Flash"): reproduced as the papers state; not independently checked.

## Conflicts between sources
| Topic | Conflict | Handling |
|---|---|---|
| Inspect AI license | One source says MIT, another Apache-2.0 | Unresolved; check repo LICENSE |
| PyRIT release/version | v0.11.0 (Feb 2026) vs v1.1.0 listed elsewhere; repo moved to microsoft/PyRIT, Azure/PyRIT archived 27 Mar 2026 (one source) | Unresolved |
| Promptfoo acquisition date | 9 Mar 2026 (most) vs "16 Mar" (one catalog) | Use "announced 9 Mar 2026" |
| Promptfoo stars | 13.2k vs 25.4k (different dates/sources) | Not used as evidence |
| OWASP 2026: prompt injection | Formal list keeps prompt injection at LLM01 (several sources); one commentary says it falls out of the top 10 by incident counts | Read primary |
| Jev claims | Vendor: speed/cost/"cannot hallucinate"; independent: ties on accuracy, error asymmetry | Prefer independent; label vendor claims |
| Drift prevalence | Blogs cite 67% / 91% within 90 days with no primary | Excluded |
| Langfuse "all product features open-sourced" timeline | Press page says features open-sourced under MIT in a prior year; clarifications page says MIT core | Not material |

## Vendor-authored comparisons (treat as marketing)
LangChain "LangSmith vs Braintrust"; Braintrust "LangSmith vs Braintrust / alternatives"; DeepEval "vs TruLens / vs RAGAS"; Giskard "Garak/PyRIT alternatives"; Vectara leaderboard/FaithJudge (vendor research).

## Rules followed
No citation was created from memory without the ○R tag; quotes avoided in favor of paraphrase; results reported with their stated caveats; where a source was blocked, that is stated.
