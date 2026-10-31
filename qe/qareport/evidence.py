"""Load a target's evidence from a ledger file (the only source of figures), plus tool info."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from qe.core.events import EventType
from qe.core.ledger import SQLiteLedger
from qe.qareport.models import (
    EntryRef,
    EvidenceInput,
    ReportContext,
    ReportInput,
    TargetContext,
    TargetMeta,
    ToolInfo,
)
from qe.realeval.runner import replay

ROOT = Path(__file__).resolve().parents[2]


def host_only(url: str | None) -> str | None:
    """host[:port] of an endpoint URL; userinfo, path and query (may carry tokens) are dropped."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if not host:
            return None
        return f"{host}:{parts.port}" if parts.port else host
    except ValueError:
        return None


def tool_info() -> ToolInfo:
    try:
        version = metadata.version("qe")
    except metadata.PackageNotFoundError:
        version = "unknown"
    commit: str | None = None
    dirty: bool | None = None
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, timeout=10, check=True).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "qe"], cwd=ROOT,
                                    capture_output=True, text=True, timeout=20,
                                    check=True).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return ToolInfo(version=version, git_commit=commit, git_dirty=dirty)


def _scan(path: Path) -> dict[str, Any]:
    ledger = SQLiteLedger(path)
    try:
        report = ledger.verify()
        entries: dict[str, EntryRef] = {}
        runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        signoffs: list[dict[str, Any]] = []
        confirmations: list[dict[str, Any]] = []
        config: dict[str, Any] = {}
        for e in ledger.entries():
            entries[e.event.key] = EntryRef(seq=e.seq, hash=e.hash)
            pl = e.event.payload
            if e.event.key == "evalconfig":
                config = dict(pl)
            elif e.event.type is EventType.RUN_RECORDED:
                runs[str(pl["item_id"])].append(dict(pl))
            elif e.event.key.startswith("confirm:"):
                confirmations.append({**pl, "seq": e.seq, "hash": e.hash})
            elif e.event.type is EventType.SIGNOFF_RECORDED:
                signoffs.append({**pl, "seq": e.seq, "hash": e.hash})
        return {"entries": entries, "runs": {k: sorted(v, key=lambda r: r["rep"])
                                             for k, v in runs.items()},
                "signoffs": signoffs, "confirmations": confirmations, "config": config,
                "head": ledger.head(), "length": len(ledger), "chain_ok": report.ok,
                "chain_reason": report.reason}
    finally:
        ledger.close()


def load_target(path: Path, ctx: TargetContext) -> EvidenceInput:
    """Evidence for one target. Raises ValueError when the ledger has no evaluation config."""
    scan = _scan(path)
    config = scan["config"]
    if not config:
        raise ValueError("ledger has no evaluation config")
    result = replay(path)
    plan = list(config.get("items", []))
    return EvidenceInput(
        name=ctx.name, eval_id=ctx.eval_id, project_id=ctx.project_id, created=ctx.created,
        state=ctx.state, params=ctx.params,
        config={k: v for k, v in config.items() if k != "items"}, items_planned=plan,
        result=result, runs=scan["runs"], entries=scan["entries"], head=scan["head"],
        length=scan["length"], chain_ok=scan["chain_ok"], chain_reason=scan["chain_reason"],
        signoffs=scan["signoffs"], confirmations=scan["confirmations"], meta=ctx.meta,
        monitoring=ctx.monitoring)


def build_input(ctx: ReportContext, ledgers: dict[str, Path]) -> ReportInput:
    """ReportInput from a context and a ledger path per `ledger_file`."""
    targets = [load_target(ledgers[t.ledger_file], t) for t in ctx.targets]
    return ReportInput(kind=ctx.kind, id=ctx.id, title=ctx.title, created=ctx.created,
                       tool=ctx.tool, targets=targets, notes=ctx.notes)


def meta_for_project(project_id: str) -> TargetMeta:
    """Best-effort target facts from the ingest store (lazy; absent store = unknown)."""
    try:
        from qe.ingest import store
        proj = store.get(project_id)
    except Exception:  # noqa: BLE001 - metadata is optional; unknown stays unknown
        return TargetMeta(notes=["project metadata unavailable"])
    if proj is None:
        return TargetMeta(notes=["project record not found"])
    mode = proj.analysis.execution_mode if proj.analysis else None
    versions: dict[str, str] = {}
    if proj.branch:
        versions["branch"] = proj.branch
    if proj.analysis and proj.analysis.framework != "unknown":
        versions["framework"] = proj.analysis.framework
    return TargetMeta(endpoint_host=host_only(proj.inputs.endpoint_url), execution_mode=mode,
                      authorized=proj.authorized, authorized_at=proj.authorized_at,
                      versions=versions)
