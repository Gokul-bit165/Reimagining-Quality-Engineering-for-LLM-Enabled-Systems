# API Requests & Observations

All required frontend views and journeys have been implemented using the existing FastAPI contract without modifying backend schemas or inventing new fields.

## Current Working Integrations
- `GET /api/config`
- `GET /api/taxonomy`
- `GET /api/runs`
- `POST /api/scenarios`
- `GET /api/runs/{run_id}/report`
- `GET /api/runs/{run_id}/pack?fmt=json|md`
- `POST /api/runs/{run_id}/signoff`
- `GET /api/monitoring-plan`
- `GET /api/benchmarks/models`
- `POST /api/benchmarks`
- `GET /api/benchmarks`
- `GET /api/benchmarks/{bench_id}`

## Future Enhancements
- Server-Sent Events (SSE) or WebSockets for live scenario generation progress instead of blocking POST requests.
- Endpoint for comparing two scenario runs side by side.

