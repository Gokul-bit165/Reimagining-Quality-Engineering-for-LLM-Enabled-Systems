"""Background clone/extract + analyze jobs (thread pattern mirrors qe/modelbench/jobs.py)."""

from __future__ import annotations

import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from qe.ingest import clone as clone_mod
from qe.ingest import paths, store
from qe.ingest.analyzer import analyze_workspace
from qe.ingest.clone import IngestError, resolve_subdir
from qe.ingest.limits import MAX_CONCURRENT_JOBS, MAX_QUEUED_JOBS
from qe.ingest.models import Project, ProjectAnalysis
from qe.ingest.summary import choose_mode_detailed, decorate
from qe.ingest.target import docker_available, docker_status
from qe.ingest.upload import extract_zip
from qe.ingest.url import RepoRef

_POOL = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="ingest")
_LOCK = threading.Lock()
_FUTURES: dict[str, Future[None]] = {}


def finalize_analysis(raw: ProjectAnalysis, endpoint_url: str | None,
                      root: Path | None = None) -> ProjectAnalysis:
    ok = docker_available()
    why = "" if ok else docker_status()[1]
    mode, reason, plan = choose_mode_detailed(endpoint_url, raw, ok, root, why)
    return decorate(raw, mode, reason, plan)


def _set(project_id: str, **changes: object) -> Project:
    p = store.get(project_id)
    if p is None:
        raise IngestError("project was deleted")
    updated = p.model_copy(update=changes)
    store.save(updated)
    return updated


def _work(project_id: str, ref: RepoRef | None, zip_path: Path | None) -> None:
    try:
        ws = paths.workspace_dir(project_id)
        if ref is not None:
            token = os.environ.get("GITHUB_TOKEN") or None  # read here, never stored/logged
            clone_mod.clone_repo(ref, ws, token)
            subdir = ref.subdir
        elif zip_path is not None:
            extract_zip(zip_path, ws)
            subdir = ""
        else:
            raise IngestError("nothing to ingest")
        proj = _set(project_id, state="analyzing")
        root: Path = resolve_subdir(ws, subdir)
        raw = analyze_workspace(root)
        analysis = finalize_analysis(raw, proj.inputs.endpoint_url, root)
        _set(project_id, state="ready", analysis=analysis, error=None)
    except IngestError as exc:
        _fail(project_id, str(exc))
    except Exception as exc:  # noqa: BLE001 - reported to the user via the project record
        _fail(project_id, f"{type(exc).__name__}: {str(exc)[:200]}")


def _fail(project_id: str, message: str) -> None:
    try:
        _set(project_id, state="failed", error=message)
    except IngestError:
        pass  # project deleted while running


def has_capacity() -> bool:
    with _LOCK:
        return sum(1 for f in _FUTURES.values() if not f.done()) < MAX_QUEUED_JOBS


def start(project_id: str, ref: RepoRef | None = None, zip_path: Path | None = None) -> None:
    """Queue a job on the bounded pool (callers check has_capacity() first)."""
    def run() -> None:
        try:
            _work(project_id, ref, zip_path)
        finally:
            if zip_path is not None:
                zip_path.unlink(missing_ok=True)

    with _LOCK:
        for pid in [k for k, f in _FUTURES.items() if f.done()]:
            del _FUTURES[pid]
        _FUTURES[project_id] = _POOL.submit(run)


def wait(project_id: str, timeout: float = 30.0) -> None:
    with _LOCK:
        fut = _FUTURES.get(project_id)
    if fut is not None:
        try:
            fut.result(timeout)
        except Exception:  # noqa: BLE001, S110 - failures are recorded on the project
            pass
