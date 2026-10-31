"""Resolve a project id to its target + user inputs, via Agent A's `qe.ingest` (lazy import).

Expected adapter (to be provided by qe.ingest): `qe.ingest.eval_bridge.resolve_project(project_id)`
returning an object/dict with: name, status ("ready"), execution_mode ("sandboxed"|"static_only"
|...), authorized (bool), target (RagTarget), documents [{name,text}], qa_pairs [{question,
reference_answer?}], risk_flags [str], canaries [str] (optional). Tests inject a resolver with
`set_resolver`.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from qe.realeval.target import RagTarget


class ResolveError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class ResolvedProject:
    project_id: str
    name: str
    target: RagTarget
    documents: list[dict[str, str]] = field(default_factory=list)
    qa_pairs: list[dict[str, Any]] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    canaries: list[str] = field(default_factory=list)
    authorized: bool = False


Resolver = Callable[[str], ResolvedProject]
_override: Resolver | None = None


def set_resolver(fn: Resolver | None) -> None:
    global _override
    _override = fn


def _get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def resolve_target(project_id: str) -> ResolvedProject:
    if _override is not None:
        return _override(project_id)
    try:
        bridge = importlib.import_module("qe.ingest.eval_bridge")
    except ImportError:
        return _from_store(project_id)
    try:
        proj = bridge.resolve_project(project_id)
    except KeyError:
        raise ResolveError(404, "project not found") from None
    if proj is None:
        raise ResolveError(404, "project not found")
    if _get(proj, "status") != "ready":
        raise ResolveError(409, f"project is not ready (status={_get(proj, 'status')!r})")
    if _get(proj, "execution_mode") == "static_only":
        raise ResolveError(409, "project is static_only: it cannot be executed, so it cannot be "
                                "evaluated dynamically")
    return ResolvedProject(
        project_id=project_id, name=str(_get(proj, "name", project_id)),
        target=_get(proj, "target"),
        documents=list(_get(proj, "documents", [])), qa_pairs=list(_get(proj, "qa_pairs", [])),
        risk_flags=list(_get(proj, "risk_flags", [])), canaries=list(_get(proj, "canaries", [])),
        authorized=bool(_get(proj, "authorized", False)))


def _from_store(project_id: str) -> ResolvedProject:
    """Fallback straight from qe.ingest.store: only endpoint-mode projects can be built here."""
    from qe.ingest import store
    from qe.ingest.target import SandboxedRepoTarget

    proj = store.get(project_id)
    if proj is None:
        raise ResolveError(404, "project not found")
    if proj.state != "ready":
        raise ResolveError(409, f"project is not ready (state={proj.state!r})")
    mode = proj.analysis.execution_mode if proj.analysis else "static_only"
    if mode == "static_only":
        raise ResolveError(409, "project is static_only: it cannot be executed, so it cannot be "
                                "evaluated dynamically")
    from qe.ingest.vault import VAULT

    target: RagTarget
    if mode == "docker" and not proj.inputs.endpoint_url:
        target = _docker_target(project_id, proj)
    elif mode == "endpoint" and proj.inputs.endpoint_url:
        target = SandboxedRepoTarget("endpoint", endpoint_url=proj.inputs.endpoint_url,
                                     secrets=VAULT.get(project_id),
                                     target_config=proj.target_config)
    else:
        raise ResolveError(409, f"execution_mode {mode!r} has no runnable target (endpoint mode "
                                "needs an endpoint_url)")
    return ResolvedProject(
        project_id=project_id, name=project_id, target=target,
        documents=[d.model_dump() for d in proj.inputs.documents],
        qa_pairs=[q.model_dump() for q in proj.inputs.qa_pairs],
        risk_flags=[*proj.inputs.risk_focus,
                    *(f.id for f in (proj.analysis.risk_flags if proj.analysis else []))],
        authorized=proj.authorized)


def _docker_target(project_id: str, proj: Any) -> RagTarget:
    """Managed docker target: nothing is built here; the evaluation job calls prepare()/close()."""
    from qe.ingest import paths, store
    from qe.ingest.clone import IngestError, resolve_subdir
    from qe.ingest.docker_runner import ManagedDockerTarget
    from qe.ingest.models import RuntimeStatus
    from qe.ingest.runplan import NotRunnableError, detect_run_plan
    from qe.ingest.target import docker_status
    from qe.ingest.vault import VAULT

    ok, why = docker_status()
    if not ok:
        raise ResolveError(409, f"docker mode unavailable: {why}")
    try:
        root = resolve_subdir(paths.workspace_dir(project_id), proj.subdir)
        detect_run_plan(root, proj.inputs.app_port, proj.inputs.app_path)
    except (IngestError, NotRunnableError) as exc:
        raise ResolveError(409, f"docker mode unavailable: {exc}") from None

    def on_status(st: RuntimeStatus) -> None:
        cur = store.get(project_id)  # project may have been deleted mid-run
        if cur is not None:
            store.save(cur.model_copy(update={"runtime": st}))

    return ManagedDockerTarget(
        project_id, root, secrets=VAULT.get(project_id), egress_allow=proj.inputs.egress_allowlist,
        target_config=proj.target_config, app_port=proj.inputs.app_port,
        app_path=proj.inputs.app_path, on_status=on_status)


def prepare_target(target: RagTarget) -> None:
    """Build/start the target if it needs it. Raises on failure with the user-facing reason."""
    fn = getattr(target, "prepare", None)
    if callable(fn):
        fn()


def close_target(target: RagTarget) -> None:
    """Always release whatever the target holds (containers, networks, images). Never raises."""
    fn = getattr(target, "close", None)
    if callable(fn):
        try:
            fn()
        except Exception:  # noqa: BLE001, S110 - cleanup must not mask the job outcome
            pass
