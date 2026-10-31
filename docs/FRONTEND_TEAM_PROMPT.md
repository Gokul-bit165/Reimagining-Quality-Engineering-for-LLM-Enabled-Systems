# Frontend team prompt: React app for `qe`

Paste everything inside the fenced block into your coding assistant, in a new folder `frontend/` at the repo root. Read `docs/UI_DESIGN.md`, `docs/FINAL_DEMO_GUIDE.md` and the working reference UI in `qe/ui/static/` (vanilla JS; it renders every section below against the real API) first.

````text
# ROLE
You are a frontend engineer building the React app for `qe`, a pre-release verification platform for LLM applications. A company's AI/QA team uses it to decide whether an LLM app version ships. The backend (FastAPI, `qe/ui/server.py`) already exists and is the single source of truth. Do NOT change the backend or invent API fields. If you need one, write it down in `frontend/API_REQUESTS.md` and keep going.

# WHO USES IT AND HOW (design for these journeys)
1. AI/QA engineer: describes a risk ("customers get invented policy facts"), picks the application and risk category, presses Run, reads the report, downloads the evidence pack.
2. QA lead: compares the seeded-defect run with the clean control, checks that the clean control stays clean, re-runs targeting previous failures.
3. Risk/compliance approver: reads the release recommendation and its reasons, records a human approval or rejection with a name and note. This is a mandatory step for critical decisions.
4. Executive viewer: opens a finished report link and reads only the decision, the uncertainty and the "claims not made".
A company reads the decision first, then asks "how sure are you" (intervals), then "what could you not check" (claims not made, uncovered risks), then "who signed it off".

# STACK
Vite + React 18 + TypeScript (strict), React Router (hash or browser routes), TanStack Query for server state, plain CSS with design tokens as CSS variables (copy `qe/ui/static/tokens.css`). No UI kit; no chart library (the interval bar is a small SVG, see `intervalBar` in `qe/ui/static/lib.js`). Dev: Vite proxy `/api` to `http://127.0.0.1:8000` (the backend has no CORS). Prod: build to `frontend/dist` and serve behind the same origin.

# API CONTRACT (all JSON; errors are `{"detail": string | [...]}` with 400/404/422)
- `GET  /api/config` -> `{ real_available: boolean, reason?: string, tester_model?: string, target_model?: string, max_calls?: number }`. Never contains a key.
- `GET  /api/taxonomy` -> `{ name, status, apps: string[], entries: {id, title}[] }` (OWASP LLM ids `LLM01`..`LLM10`).
- `GET  /api/runs` -> `{ id, app, variant: "clean"|"seeded", decision, entries, verified, example_policy }[]`. Scenario run ids look like `scn-<sid>-<app>-<variant>` (note `app` is `scn-<sid>-<app>` here; derive the app from the last hyphen part).
- `POST /api/scenarios` body `{ app, taxonomy_id, scenario (3..500 chars), budget (1..40, default 12), previous_failures: string[] (<=10), mode: "simulated"|"real" }` -> `{ scenario_id, runs: [cleanRunId, seededRunId] }`. Simulated takes about 10 s; real mode can take minutes (free-tier rate limits). It is a blocking request: show progress text, disable the button, handle timeouts and 4xx/5xx.
- `GET  /api/runs/{id}/report` -> Report (below).
- `GET  /api/runs/{id}/pack?fmt=json|md` -> the evidence pack as a download.
- `POST /api/runs/{id}/signoff` body `{ approver (1..80), approved: boolean, note (<=500) }` -> `{ recorded, decision }`. Human-only; re-fetch the report afterwards.
- `GET  /api/monitoring-plan` -> `{ markdown }`.

## Report shape (TypeScript, write these types first and validate responses with zod)
```ts
type Rate = { k:number; n:number; point:number; lower:number; upper:number; confidence:number; method:string };
type Metric = { metric:string; dimension:string; failed_cases:number; passed_cases:number; not_evaluable_cases:number;
  failure_rate?:Rate; appetite:number|null; status?:"within"|"above"|"straddles"|"no_appetite";
  failures:{case_id:string; question:string|null; expected:string|null; state:string; detail:string|null; evidence_key:string; output:string; citations:string[]}[] };
type Report = {
  id:string;
  scenario:{ app:string; variant:"clean"|"seeded"; taxonomy_id:string; text:string; previous_failures:string[]; budget:number;
    mode:"simulated"|"real"; tester_model:string|null; target_model:string|null; repeats:number; attack_budget:number; regression:string };
  labels:{ generation:string; target:string; policy:string; mode:"simulated"|"real" };
  risks:{ risk_id:string; taxonomy_id:string; title:string; component:string; rationale:string; source:string; status:string; planned_tests:number }[];
  plan:{ allocation:[string,number][]; unplanned:string[]; budget:number };
  generation:{ drafted:number; rejected_drafts:number; redundant:Record<string,string>; unplanned_risks:string[];
    tests:{case_id:string; question:string; expected:string; source_id:string; risk_id:string; family:string}[] };
  execution:{ runs:number; repeats:number; cases:number; errors:number; unrun:number; consistency:{cases:number; identical_across_repeats:number} };
  checks:{ ran:string[]; attack_oracles:string[]; not_run:string[] };
  metrics:Metric[];
  attacks:{ budget:number; verdict_attacker:string; rows:{pair_id:string; surface:string; goal:string; baseline_breached:boolean;
    static_template:{breached:boolean; first_success:number|null; attempts:number}; adaptive_mutation:{breached:boolean; first_success:number|null; attempts:number}}[];
    asr:Record<string,{successes:number; n_pairs:number; asr:number; lower:number; upper:number; budget:number}> };
  failures:{ case_id:string; metric:string; location:string; rule:string|null; evidence:string[]; substitution:string; source_id:string|null; question:string|null }[];
  failure_taxonomy:Record<string,number>;
  regression:{ admitted:{case_id:string; minimized_from:string; original_question:string|null; minimized_input:Record<string,unknown>; reproduced:[number,number]; metric:string|null; lineage:string[]}[];
    rejected:{case_id:string; metric:string; reason:string}[] };
  decision:{ decision:"RELEASE"|"CONDITIONAL"|"REJECT"|"INSUFFICIENT_EVIDENCE"; policy_version:string; evidence_ids:string[]; conditions:string[]; uncovered_risks:string[] };
  policy:{ id:string; version:string; example_only:boolean };
  access:{ visibility_levels:string[]; note:string };
  ledger:{ entries:number; head:string; verified:boolean };
  human_signoff:{ approver:string; approved:boolean; note:string; decision_id:string }[];
};
```

# INPUTS THE COMPANY GIVES TODAY (build these forms exactly)
Application (select from `/api/taxonomy.apps`), risk category (select from taxonomy entries), risk scenario (textarea), test budget (number), "also target previous failures" (checkbox, enabled only when the last opened report had failures; send their `source_id`s), mode (simulated, or real if `/api/config.real_available`), and at the end the human sign-off form (name, note, approve/reject).
# INPUTS THE COMPANY WILL WANT NEXT (design the form so these slot in, but do NOT call endpoints that do not exist; render them disabled with "coming soon")
Target application endpoint URL and auth, their own policy file (appetites, loss matrix), their own source documents, their own seed tests.

# SCREENS (route per screen; one reading column, left rail of scenarios)
1. New scenario: the form above, an honest "what will happen" paragraph, a visible SIMULATED / REAL label.
2. Report with a sticky section nav and these sections in order: Decision hero; Application and scenario; Risk register; Dynamic test generation; Test execution; Grounding and hallucination; Adversarial security; Failure taxonomy; Scorecard; Regression suite; Release recommendation; Evidence pack (downloads + hash chain status); Human approval; Monitoring plan.
3. Seeded/clean toggle at the top of a report (sibling run id = same prefix + variant).
Empty, loading and error states for every screen. Responsive from 360px; tables scroll inside their own container, never the page.

# NON-NEGOTIABLE PRODUCT RULES (these are the product, not polish)
- Never show a rate without its interval; draw it against the policy appetite line (`status` tells you within/above/straddles). Never compute or show a composite quality score.
- `INSUFFICIENT_EVIDENCE` is a valid first-class outcome with its own colour and plain-language explanation, not an error.
- Always show the labels: simulated vs real, example policy, access level, and a "Claims not made / not checked" block (`checks.not_run`).
- Render all ledger-derived text as text (React escapes by default; never use `dangerouslySetInnerHTML`). Model outputs and test questions are untrusted.
- Show actual counts (failed / passed / not evaluable). Do not round up, hide small samples or add reassurance copy.
- RELEASE and CONDITIONAL must visibly say a human sign-off is required; show recorded sign-offs.
- No secrets in the browser; there are none to handle. No telemetry or third-party scripts; system fonts only (the product runs offline).

# QUALITY BAR
WCAG AA (contrast, focus rings, keyboard, labels, `role=status` for async messages), `prefers-reduced-motion`, no layout shift. Use the design tokens and the direction in `docs/UI_DESIGN.md` (audit-ledger feel, serif for the decision, no gradients/glass/card grids). Tests: Vitest + React Testing Library for the interval bar, the decision states, form validation and the sign-off flow; one Playwright test that runs a simulated scenario end to end against a local backend. Typecheck, lint and build must pass. Take real screenshots at 390px and 1440px of: new-scenario form, report top, security section, human approval.

# DELIVERABLES
`frontend/` app, `frontend/README.md` (how to run against the backend), `frontend/API_REQUESTS.md`, screenshots in `frontend/screenshots/`. Stop and report: what is built, test and build output, what is not done.

# HOW TO RUN THE BACKEND
python -m uv sync
python -m uv run --extra ui uvicorn qe.ui.server:app --port 8000
````

## How a company uses it (for your demo narration)
1. Engineer opens **New scenario**, selects the application and risk category, writes the risk in plain words, runs it.
2. Reads the **decision**, then the **scorecard intervals** and the **failure evidence** for each failing test.
3. Toggles to the **clean control** to confirm no false alarms; reruns with "target previous failures" after a fix.
4. Downloads the **evidence pack**; the approver records **sign-off**; the **monitoring plan** says what is re-run on each model, prompt or knowledge-base change.
