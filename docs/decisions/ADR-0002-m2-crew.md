# ADR-0002: M2 crew, app model, coverage (P3)

Status: proposed (P3, no frozen contract changed). Date: 2026-10-31.

- **No new event types.** Crew output uses `RISK_PROPOSED`, `TEST_DRAFTED`, `VALIDITY_VERDICT`, `NARRATIVE_DRAFTED` (LLM_AGENT). Coverage reports are deterministic code and use `EVIDENCE_RECORDED` with `payload.kind="coverage_report"`. Human audit labels use `SIGNOFF_RECORDED` with `payload.kind="audit_label"`. Lead: if you prefer dedicated types, that is an additive change in `qe/core/events.py`.
- **Every crew draft** carries `prompt_name/version/sha256`, full `model` ref and `raw_output` (R10). Rejected drafts are recorded too (`status=rejected`) so invalid-test-rate has a denominator.
- **OWASP taxonomies:** `qe/risk/data/*.json`. LLM Top 10 2025: IDs/titles/URLs copied from https://genai.owasp.org/llm-top-10/ on 2026-10-31; descriptions NOT fetched. Agentic 2026: landing page fetched, entries NOT visible, file has zero entries (`status=primary_entries_not_fetched`). Nothing invented; fetch the PDF before using it.
- **Ranking** = policy code: lower `risk_appetite[taxonomy_id]` ranks first; ids the policy is silent on rank last and are flagged, never dropped. **Planner** = round-robin over that rank; risks given zero tests are reported UNCOVERED.
- **Skeptic independence (R4):** input type `SkepticInput` (question + source text, `extra=forbid`); family must differ from the author's. Agreement rule is numbers-equal, else normalised containment; no tuned threshold.
- **Audit:** simple random sample (not stratified, so the rate is unbiased), blind to Skeptic verdicts; exact CP interval.
- **CLI:** `qe.crew.audit_cli.audit_app` must be mounted in `qe/cli/main.py` (P1's file): `app.add_typer(audit_app, name="audit")`.
- **ragas:** adapter + `TestsetBackend` port only; the pinned extra and real backend are NOT wired (not in `pyproject.toml`).
