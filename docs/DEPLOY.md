# Deploying qe FlowOps with Docker

```bash
cp .env.example .env        # optional: add GROQ_API_KEY / OPENROUTER_API_KEY (never commit .env)
docker compose up --build -d
docker compose ps           # wait for "healthy"
open http://localhost:8000
```

The image builds the React UI, installs the locked Python dependencies, runs as a non-root user
(uid 10001) on a read-only root filesystem with all capabilities dropped, and keeps all state in the
`qe-runs` volume (ledgers, projects, clone workspaces, evaluations).

## Read this before exposing it

- **There is no authentication.** Compose publishes the port on `127.0.0.1` only. For a team, put an
  authenticating reverse proxy (OIDC proxy, or basic auth over TLS) in front and set
  `QE_ALLOWED_HOSTS=qe.example.com` so the Host and Origin checks accept your hostname.
- **Container execution of submitted repos is off.** The "docker" execution mode needs a Docker daemon
  and the image deliberately does not mount the Docker socket. Inside the container use **endpoint
  mode** (the user's deployed app URL) or static analysis only.
- **Endpoints on private networks are refused** by default (SSRF guard). To test an app on a private
  network set `QE_ALLOW_PRIVATE_ENDPOINTS=1` knowingly.
- Telemetry flags (`DEEPEVAL_TELEMETRY_OPT_OUT`, `RAGAS_DO_NOT_TRACK`) are set in the image.

## Operate

| Task | Command |
|---|---|
| Logs | `docker compose logs -f qe` |
| Back up state | `docker run --rm -v qe-runs:/d -v "$PWD":/b alpine tar czf /b/qe-runs.tgz -C /d .` |
| Upgrade | `git pull && docker compose up --build -d` |
| Stop, keep data | `docker compose down` |
| Stop, delete data | `docker compose down -v` |

Health: `GET /api/health` returns `{"status":"ok"}`.
