# qe Frontend (React + Vite + TypeScript)

This is the React frontend for `qe`, a pre-release verification platform for LLM applications.

## Requirements
- Node.js >= 18 (developed with Node.js v26)
- Python 3.12+ (for the backend API)

## Running the Application

### 1. Start the Backend API (FastAPI)
In a separate terminal, from the repository root:
```bash
python -m uv sync
python -m uv run --extra ui uvicorn qe.ui.server:app --port 8001
```

### 2. Start the Frontend Development Server
In another terminal, from the `frontend/` directory:
```bash
npm install
npm run dev
```

Open **[http://localhost:8080](http://localhost:8080)** in your browser.

The Vite dev server runs on port `8080` and proxies `/api/*` requests to the FastAPI backend running on port `8001`.

## Features Preserved & Implemented
- **New Risk Scenario**: Form with dynamic taxonomy, simulated/real modes, test budget, prior failure feeds.
- **Scenario Report View**:
  - Decision hero with exact color coding (`RELEASE`, `REJECT`, `CONDITIONAL`, `INSUFFICIENT_EVIDENCE`).
  - Sibling toggle between seeded-defect app and clean control.
  - Sticky jump navigation for quick section access.
  - Risk register table with planned tests and uncovered risks alerts.
  - Verbatim test generation details with expandable sample tests.
  - Test execution metrics, errors, and consistency breakdown.
  - Grounding and citation checks with failure evidence records.
  - Adversarial security matrix with static & adaptive attack results and ASR intervals.
  - Failure taxonomy classification by location and rule.
  - Quality and safety scorecard with exact confidence intervals plotted against appetite lines.
  - Regression test suite with admitted minimized tests and lineage.
  - Release recommendation with audit-backed policy explanations.
  - Evidence pack verification status and direct JSON/Markdown downloads.
  - Human sign-off workflow recording reviewer name and decisions directly to the ledger.
  - Continuous monitoring plan viewer.
- **Model Benchmark Dashboard**:
  - Comparison across simulated reference models and OpenRouter real models.
  - Side-by-side metric comparison table with inline mini interval bars.
  - Statistically separable conclusions without invalid composite ranking.
  - Per-model evidence and raw execution logs.

