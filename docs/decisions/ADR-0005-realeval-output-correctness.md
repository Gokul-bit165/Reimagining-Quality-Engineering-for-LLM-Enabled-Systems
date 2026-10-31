# ADR-0005: realeval output correctness for real RAG apps

Status: accepted. Context: an audit showed the evaluation mechanics were sound but the output was
wrong for real apps (id-only contexts judged as passages, unchecked items counted as passes,
brittle lexical matching, security silently dropped from the decision, variants inflating n).

Decisions
1. Contexts that are ids/filenames/titles are not passage text. Faithfulness and retrieval are
   `None` (never gate); ids resolve against uploaded document names for `citation_valid` and, when
   the item has a `source_doc`, for `retrieval_hit`.
2. An item whose every gating score is `None` has `passed = None` (UNCHECKED): excluded from all
   rates, counted in `unchecked`, and named in notes and decision reasons. `answerable: bool|None`
   is user-declared; an LLM judge (QE_JUDGE_MODEL, different from the generator) is advisory only.
3. Lexical scoring canonicalises numbers, units, percentages and dates (`qe/realeval/normalize.py`),
   guards negation, and detects refusals from a documented phrase set; weak hedges count only with
   the structural cue (no contexts and no citation).
4. The injection oracle also detects non-contiguous marker echo (fragments adjacent, separated only
   by whitespace/punctuation) and probe-defined predicates (`output_predicate`: forbidden
   domains, phrases, regexes, canaries). Sentences that refuse or flag the instruction are not
   counted as obedience (limit: a hostile answer inside such a sentence is missed). Verdicts stay
   oracle-based (R5).
5. `injection_resistance` is always required when security runs or is requested.
   `include_security=false` is a stated evidence gap and caps the verdict below RELEASE. The API
   requires a user policy (`GET /api/policy/template`) or an explicit `use_example_policy: true`.
6. Rates are computed over distinct root questions (variants share their parent's root; all repeats
   and all checked items under a root must pass). Every rate reports `n_roots` and `n_items`.
   `max_questions` (default 50; repeats default 3) is a hard cap on total items; priority:
   regression, reserved security probes (at most half), variants and mutated failures (at most a
   quarter each), base questions.
7. LLM config: `QE_LLM_MODEL` (falls back to `QE_AGENT_MODEL`), `GET /api/llm/status` lists missing
   setting NAMES only.
8. Per-project `target_config` (request template, method, JSONPath-lite answer/context paths,
   vault-referenced headers, JSON/SSE/text responses) plus a test-connection endpoint. SSRF
   protections are unchanged.
9. Analyzer risk flags map to scenarios (`FLAG_SCENARIOS`); `no-citation-handling` makes citation
   validity mandatory.
10. The monitoring plan is derived from the evaluation; cadence is null unless the user sets it.

Not done: docker execution of repos without an endpoint is still not wired into the evaluation
engine (only endpoint mode evaluates).
