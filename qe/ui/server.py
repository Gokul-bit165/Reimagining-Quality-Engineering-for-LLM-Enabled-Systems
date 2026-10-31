"""Local web UI backend: JSON API (projects, evaluations) plus the built React frontend.

Every number shown comes from real evaluation records; nothing here generates or displays
simulated data. If the frontend has not been built, `/` answers 503 with a build hint.
Run:  uv run --extra ui uvicorn qe.ui.server:app --port 8000
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from qe.core.dotenv import load_dotenv
from qe.ui.routes_campaign import router as campaign_router
from qe.ui.routes_eval import router as eval_router
from qe.ui.routes_judge import router as judge_router
from qe.ui.routes_projects import router as projects_router
from qe.ui.routes_report import router as report_router
from qe.ui.security import install as install_security

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # allow-listed names only; values are never printed

FRONTEND_DIST = Path(os.environ.get("QE_FRONTEND_DIST", ROOT / "frontend" / "dist"))



def _reap_orphan_containers() -> None:
    from qe.ingest.docker_runner import reap_orphans
    try:
        reap_orphans()
    except Exception:  # noqa: BLE001, S110 - docker may be absent; reaping is best effort
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Remove containers/networks left by a crashed run (label qe-run) without blocking start."""
    threading.Thread(target=_reap_orphan_containers, daemon=True, name="qe-reaper").start()
    yield


app = FastAPI(title="qe evidence UI", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)
app.include_router(projects_router)
install_security(app)
app.include_router(eval_router)
app.include_router(judge_router)
app.include_router(campaign_router)
app.include_router(report_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_model=None)
def index() -> Response:
    built = FRONTEND_DIST / "index.html"
    if built.is_file():
        return FileResponse(built)
    return JSONResponse(status_code=503,
                        content={"detail": "frontend not built; run npm run build in frontend/"})


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
