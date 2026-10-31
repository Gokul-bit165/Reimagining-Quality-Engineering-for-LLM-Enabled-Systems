# UI design direction (v1)

**Audience:** AI-platform / QA / risk engineers deciding whether an LLM app version ships; reviewers who must be able to audit the call.

**Tone:** an audit ledger, not a dashboard. Calm, precise, paper-like. The interface should feel like a signed inspection report you can interrogate.

**Memorable idea:** *the decision never appears without its uncertainty.* Every rate is drawn as an interval bar against the policy's appetite line. Nothing is ever a bare number (rule R11), and "insufficient evidence" is a first-class, visually distinct outcome (R9).

**References:** printed lab reports, accounting ledgers, the Edward Tufte "small multiples" restraint. Not SaaS admin templates.

## Tokens (see `frontend/src/styles/tokens.css`)
- **Type:** headings and the decision word in a serif stack (Iowan Old Style / Palatino / Georgia) for gravity; UI text in the system sans; hashes and ids in the system mono. System fonts only: the product runs offline.
- **Color roles:** paper background, ink text, one rule colour; four *semantic* state colours (release, reject, conditional, insufficient) used only for decision state and interval bars, never decoration. All text pairs meet WCAG AA.
- **Spacing:** 4px base scale. **Radius:** 2px (documents are not pills). **Elevation:** none; separation by hairline rules and whitespace.
- **Motion:** 120ms ease-out on hover/focus only; disabled under `prefers-reduced-motion`.

## Layout
Left rail lists runs (app, variant, decision chip). Right pane is one reading column: Decision, Access level, Evidence (interval bars), Runs, Ledger integrity, Claims not made. At <=720px the rail becomes a top select.

## Not done in v1 (for the team)
Coverage / n_eff / invalid-test / ASR panels (the API already returns them when the ledger has those events; render them next), run comparison view, ledger event browser, dark theme.
