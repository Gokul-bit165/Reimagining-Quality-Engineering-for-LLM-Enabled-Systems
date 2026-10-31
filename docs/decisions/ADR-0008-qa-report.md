# ADR-0008: Quality-tester report and evidence bundle

Status: accepted (implementation under review)

## Context
A release board needs a deliverable whose every figure can be checked. The ledger (hash-chained,
R10) already holds every target response; scorecards and decisions are replayable from it.

## Decision
- `qe/qareport/` builds a deterministic report (dict, JSON round-tripped with sorted keys) from
  ledger-derived evidence only. No model text appears in findings; prose is static or templated.
- Renderers: Markdown, self-contained HTML (inline CSS + server-built SVG, no JS), JSON.
- Evidence bundle (zip): report.*, items.jsonl (all requests/responses with ledger hashes),
  plan.json, config.json, context.json, ledger copies, MANIFEST.json (sha256 of every file,
  ledger heads and lengths, tool commit), VERIFY.md. Campaigns add campaign_plan.json and
  campaign_context.json; the plan is checked against the plan id anchored in the ledger.
- `qe verify-bundle <zip>`: hashes, ledger chains against the manifest anchor, then the whole
  report is rebuilt from ledgers + context and compared (precise path diff); md/html re-rendered.
- Severity (`rubric.yaml`) and remediation (`remediation.yaml`) are static, versioned labels. Severity
  never feeds the verdict (tested). Remediation text is labelled guidance.
- Endpoints: GET /api/evaluations/{id}/qa-report?format=html|md|json, .../evidence-bundle, and the
  same under /api/campaigns/{id}. 404 unknown, 409 unfinished/no ledger/secret detected, 413 size cap.

## Consequences / limits
- MANIFEST.json is not signed: whoever rewrites the zip can rewrite the manifest. The ledger head
  is the anchor to compare out of band; tail truncation is only detectable against it.
- Re-derivation needs the same tool version (rubric, scoring) as named in the manifest.
- Items/ledger contain target responses verbatim; a bundle is withheld (409) if a project vault
  secret value appears in it. Echoed secrets not in the vault are not detected.
- Lexical scoring limits, small-n and example-policy caveats are surfaced in the report itself.
