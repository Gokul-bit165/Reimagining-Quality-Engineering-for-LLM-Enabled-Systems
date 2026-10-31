# syntax=docker/dockerfile:1.7
# qe FlowOps: one image serving the API and the built React UI on port 8000.

# ---- 1. frontend build -----------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. python dependencies (locked) ---------------------------------------
FROM python:3.12-slim AS deps
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir "uv>=0.5"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra ui --no-install-project

# ---- 3. runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime
# git: shallow, read-only clones of the repositories users submit.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 qe \
 && useradd --system --uid 10001 --gid qe --home-dir /home/qe --create-home --shell /usr/sbin/nologin qe \
 && mkdir -p /app/runs && chown qe:qe /app/runs

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/qe \
    QE_RUNS_DIR=/app/runs \
    QE_FRONTEND_DIST=/app/frontend/dist \
    DEEPEVAL_TELEMETRY_OPT_OUT=1 \
    RAGAS_DO_NOT_TRACK=true

WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY qe ./qe
COPY sandbox_apps ./sandbox_apps
COPY bench/__init__.py bench/asr.py ./bench/
COPY bench/security ./bench/security
COPY docs/MONITORING_PLAN.md ./docs/MONITORING_PLAN.md
COPY --from=web /web/dist ./frontend/dist

USER qe
EXPOSE 8000
VOLUME ["/app/runs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "qe.ui.server:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
