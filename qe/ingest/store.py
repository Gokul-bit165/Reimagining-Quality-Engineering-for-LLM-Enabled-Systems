"""JSON project store under runs/projects/ plus an audit ledger for authorization attestations."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.ingest import paths
from qe.ingest.clone import rmtree
from qe.ingest.models import Project

_LOCK = threading.RLock()
_CACHE: dict[str, tuple[int, int, Project]] = {}  # path -> (mtime_ns, size, project)
AUDIT_PRODUCER = "ingest-user-attestation"


def new_project_id() -> str:
    return "prj-" + uuid.uuid4().hex[:10]


def _file(project_id: str) -> Path:
    if not paths.PROJECT_ID.match(project_id):
        raise KeyError(project_id)
    return paths.projects_dir() / f"{project_id}.json"


def _read(f: Path) -> Project:
    st = f.stat()
    hit = _CACHE.get(str(f))
    if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    proj = Project.model_validate(json.loads(f.read_text("utf-8")))
    _CACHE[str(f)] = (st.st_mtime_ns, st.st_size, proj)
    return proj


def save(project: Project) -> None:
    with _LOCK:
        f = _file(project.id)
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(project.model_dump_json(), encoding="utf-8")
        tmp.replace(f)
        _CACHE.pop(str(f), None)


def get(project_id: str) -> Project | None:
    try:
        f = _file(project_id)
    except KeyError:
        return None
    with _LOCK:
        if not f.is_file():
            return None
        return _read(f)


def list_all() -> list[Project]:
    d = paths.projects_dir()
    if not d.is_dir():
        return []
    with _LOCK:
        out = [_read(p) for p in d.glob("prj-*.json")]
    return sorted(out, key=lambda p: p.created_at, reverse=True)


def delete(project_id: str) -> bool:
    with _LOCK:
        f = _file(project_id)
        existed = f.is_file()
        if existed:
            f.unlink()
            _CACHE.pop(str(f), None)
        ws = paths.workspace_dir(project_id)
        if ws.exists():
            rmtree(ws)
    return existed


def record_attestation(project: Project) -> None:
    """Append the user's authorization attestation to the hash-chained audit ledger."""
    paths.projects_dir().mkdir(parents=True, exist_ok=True)
    ledger = SQLiteLedger(paths.projects_dir() / "audit.sqlite")
    try:
        ledger.append(Event(
            key=f"authorization:{project.id}", type=EventType.SIGNOFF_RECORDED,
            producer=AUDIT_PRODUCER, producer_kind=ProducerKind.HUMAN,
            payload={"project_id": project.id, "source": project.source,
                     "repo_url": project.repo_url, "authorized": True,
                     "authorized_at": project.authorized_at,
                     "statement": "user attests ownership or authorization to test this app"}))
    finally:
        ledger.close()
