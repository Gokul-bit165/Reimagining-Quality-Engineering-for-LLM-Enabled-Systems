# Report viewer: design note (P1)

## Audience and job
A release engineer or risk reviewer opens one file, offline, minutes before a sign-off.
They must see the decision and the reason for it first, then how far to trust it (access
level, intervals, what was not run), then the full evidence. It is read like an audit
document, not monitored like a dashboard.

## Tone
Sober, precise, a little editorial. Nothing celebrates; "not run" and "INSUFFICIENT_EVIDENCE"
are shown as plainly as a pass. No marketing gloss, no gradients, glows, glass or icon grids.

## Memorable idea: the interval ruler
Every rate is drawn on a ruler: a hairline track, the confidence interval as a bar, the
point estimate as a dot, and the policy's risk appetite as a vertical tick. Whether the
interval is left of, straddles or is right of the tick IS the release logic, readable in
one glance. The numbers are always printed beside it (the ruler is never the only channel).

## Layout
Single reading column (max 46rem) with hairline rules and numbered sections; at >= 1100px a
sticky section index sits in a left gutter. Metrics are rows in a definition-style list, not
cards. Missing sections render as a dashed "not run" block with the reason, never silence.

## Tokens
- Type (system stacks only, no CDN): display `Georgia, "Iowan Old Style", serif`;
  text `system-ui, sans-serif`; data `ui-monospace, "Cascadia Mono", monospace`.
  Scale (rem): 0.8125, 0.9375 (base), 1.125, 1.5, 2.75 (decision word).
- Colour roles (all text pairs >= 4.5:1 on paper): paper `#f7f5ef`, ink `#1c1b18`,
  muted `#55524a`, rule `#cfc9ba`, release `#1d6a38`, reject `#a2281c`, insufficient
  `#7a5200`, conditional `#1f4f8f`, notrun-fill `#efece3`.
- Spacing (rem): 0.25, 0.5, 1, 1.5, 2.5, 4. Radii: 0 (hairline, square). Elevation: none.
- Motion: ruler bars grow once on load (240ms, ease-out); disabled under
  `prefers-reduced-motion`.

## Accessibility and responsiveness
Responsive from 360px (single column, rulers shrink via viewBox); visible focus ring on
interactive elements; landmarks (header/nav/main/section); every ruler has an aria-label
that repeats its numbers; colour is never the sole carrier of the decision (the word is).
