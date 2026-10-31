# ADR-0009: semantic judging for correctness and faithfulness

Status: accepted. Context: an independent audit found every verdict-bearing check was lexical, so a
paraphrase that flips meaning passed (false pass) and a correct paraphrase failed (false fail);
faithfulness was a token-recall proxy.

Decisions
1. Two judge tasks, both closed-choice and schema-validated.
   - Answer vs reference: `correct | incorrect | partial | refusal | unanswerable`.
   - Claim groundedness: the answer is split into atomic claims by a deterministic splitter
     (sentences, `;`, `, and/but`; optional LLM extraction was NOT built). For each claim the judge
     sees only (claim, one candidate evidence passage): never the producer's rationale, other
     claims or other verdicts (R4). It must return `supported | contradicted | not_enough_info`
     plus a verbatim quote.
2. Judge output is untrusted. Strict JSON (no extra keys, closed enums, bounded size, one optional
   code fence), prompts are versioned files (`qe/realeval/judge_prompts/*.md`) whose sha256 is
   recorded with every call, and untrusted fields are wrapped in tags that the text itself cannot
   close (tag-like text is neutralised). A `supported`/`contradicted` verdict counts only if the
   quote occurs literally in the passage the judge was shown AND is on topic (it shares
   `QUOTE_MIN_OVERLAP` of the claim's content tokens; a `supported` quote must also contain every
   number of the claim). Otherwise it is downgraded to `unverified` and the lexical verdict stands.
   `QUOTE_MIN_OVERLAP=0.25` is a sanity floor against injected-text quotes, not a validity
   threshold.
3. Independence (R4): the judge model family must differ from the generator's and, if
   `QE_TARGET_MODEL` is set, the target's. Families come from a model-id table
   (`model_family`: openai, anthropic, google, meta, mistral, qwen, deepseek, nvidia, xai, cohere,
   ...). An unknown family on a configured side is refused as unverified, never assumed
   independent. Limit: a fine-tune published under another vendor's name is classed by that vendor.
   A second judge (`QE_JUDGE_MODEL_2`) is added only if it also passes; the pair reports pairwise
   agreement (Cohen's kappa, `qe.stats.agreement.cohen_kappa`); a disagreement yields no opinion
   (claims stay unverified, rubric becomes a conflict). At calibration the pair also reports error
   correlation and `n_eff` (`correlated_errors` when errors co-occur more than independence
   implies).
4. Gating. A judge verdict gates ONLY when (a) the policy sets `judge_min_agreement` (new optional
   `Policy` field; nothing is defaulted in code), (b) a calibration record exists for the current
   `judge_key` (models + prompt hashes), and (c) the lower bound of the exact (Clopper-Pearson)
   interval of agreement with the user's labels, taken over every judge member, is at least that
   minimum. Otherwise the judge is advisory: scores stay lexical and the judge view is only shown
   (`judge_correct_untrusted`, `detail.judge`). Calibration (`qe/realeval/calibration.py`) runs the
   judge on user-labelled items, collapses to defect / no defect and stores accuracy, kappa and
   false-pass rate with intervals plus the confusion counts in `runs/calibration/<id>.json` (with
   the raw calls, so it replays offline). When gating, `qe.stats.judge_correction` corrects the
   judge-flagged defect rate for judge error with propagated intervals (`result.judge.corrected`).
5. Deterministic first line. Numbers, dates, durations, units and percentages (normalize.py) stay
   authoritative; verbatim claims and stated refusals never reach the judge. Where the judge and
   the lexical check disagree on an item that carries a verifiable fact, the result is a CONFLICT:
   the score is `None`, `detail.needs_review` names it, and the item is not a pass (when gating;
   when advisory the lexical value stays but the conflict is still flagged). Disagreement without
   a verifiable fact is resolved by the judge only when gating, and flagged `judge_disagrees`.
6. Replay (R10). Every judge call (model, prompt name and hash, input hash, raw response) is
   recorded in the ledger as `judgecall:<key>`; the gate decision, models and prompt hashes are in
   `evalconfig.judge`. `replay()` rebuilds the judge from those events with no client, so scores
   and metrics reproduce offline. Identical calls are memoised (no repeat cost). The raw response
   is recorded by deterministic code; interpretation is deterministic.
7. Budget. A hard per-service call cap (`QE_JUDGE_MAX_CALLS`, default 200) is shared by all
   members; after exhaustion the judge gives no opinion and `result.judge.usage.budget_exhausted`
   says so. Judge clients are only built through `real_llm_from_env`, which still requires the
   owner's `QE_LLM_SPEND_BUDGET_USD`.

Consequences / limits
- The legacy no-reference "plausibility" advisory (`judge_advisory`) is gone: with no reference the
  judge has nothing to grade against and gives no opinion.
- Claims starting with a pronoun lose their referent (no decontextualisation); only the two best
  lexical passages per claim are tried; at most 20 claims per answer are judged.
- The judge is only as good as its calibration set; the interval reports that, a threshold does not.
- Nothing here was exercised against a real model (fake local servers only).
