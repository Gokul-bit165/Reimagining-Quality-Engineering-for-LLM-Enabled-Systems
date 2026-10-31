"""HTTP API for campaigns: multi-target benchmark programmes (see qe.campaign, ADR-0006)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from qe.campaign import manager, store
from qe.campaign.models import (
    DEFAULT_ALPHA,
    DEFAULT_MAX_CALLS,
    DEFAULT_TIMEOUT_S,
    ID_RE,
    MAX_CALLS_CAP,
    MAX_TARGETS,
    CampaignParams,
    TargetSpec,
)
from qe.campaign.plan import PlanError, validate_import
from qe.campaign.targets import validate_spec_urls
from qe.core.schemas import Policy
from qe.ingest.netguard import EndpointError
from qe.ingest.target_config import TargetConfig
from qe.ingest.vault import VAULT
from qe.policy.engine import decide
from qe.realeval import audit, regression
from qe.realeval.assemble import SECURITY_METRIC
from qe.realeval.jobs import runs_dir
from qe.realeval.resolver import ResolvedProject, ResolveError, resolve_target
from qe.realeval.runner import DEFAULT_MAX_QUESTIONS, DEFAULT_REPEATS

router = APIRouter()


class CampaignRequest(BaseModel):
    project_id: str = Field(pattern=ID_RE)
    name: str = Field(min_length=1, max_length=120)
    risk_focus: list[str] = Field(default_factory=list, max_length=20)
    targets: list[TargetSpec] = Field(min_length=1, max_length=MAX_TARGETS)
    plan: dict[str, Any] | None = None
    repeats: int = Field(default=DEFAULT_REPEATS, ge=1, le=10)
    max_cases: int = Field(default=DEFAULT_MAX_QUESTIONS, ge=1, le=200)
    max_calls: int = Field(default=DEFAULT_MAX_CALLS, ge=1, le=MAX_CALLS_CAP)
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0, le=7200)
    policy: dict[str, Any] | None = None
    use_example_policy: bool = False
    include_security: bool = True
    generate_with_llm: bool = True
    seed: int = Field(default=0, ge=0, le=2**31)
    alpha: float = Field(default=DEFAULT_ALPHA, gt=0, lt=0.5)


class SignoffRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    decision: Literal["approve", "reject", "approved", "rejected"]
    rationale: str = Field(default="", max_length=2000)
    target_label: str = Field(min_length=1, max_length=40)


class ConfirmRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)


def _policy(raw: dict[str, Any] | None, include_security: bool, use_example: bool,
            ) -> Policy | None:
    pol: Policy | None = None
    if raw is not None:
        try:
            pol = Policy.model_validate(raw)
            decide(pol, [])
        except (ValidationError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid policy: {exc}") from None
    if pol is None and not use_example:
        raise HTTPException(
            status_code=422,
            detail="no policy chosen: supply `policy` (see GET /api/policy/template) or pass "
                   "`use_example_policy: true` to explicitly use the non-binding example policy")
    if pol is not None and include_security and SECURITY_METRIC not in pol.required_evidence:
        raise HTTPException(
            status_code=422,
            detail=f"invalid policy: security probes are on, so {SECURITY_METRIC} must be in "
                   "required_evidence (with a risk_appetite), or set include_security=false")
    return pol


def _check_targets(req: CampaignRequest) -> None:
    labels = [t.label.lower() for t in req.targets]
    if len(set(labels)) != len(labels):
        raise HTTPException(status_code=422, detail="target labels must be unique")
    for t in req.targets:
        try:
            validate_spec_urls(t)
        except EndpointError as exc:
            raise HTTPException(status_code=422,
                                detail=f"target {t.label!r}: {exc}") from None
        if t.api_key_secret and t.api_key_secret not in VAULT.get(req.project_id):
            raise HTTPException(
                status_code=422,
                detail=f"target {t.label!r}: secret {t.api_key_secret} is not in this project's "
                       "vault (PUT the project secrets first)")
    needed = req.repeats * len(req.targets)
    if req.max_calls < needed:
        raise HTTPException(
            status_code=422,
            detail=f"max_calls={req.max_calls} cannot cover even one case: repeats x targets = "
                   f"{needed}")


def _project_config(project_id: str) -> TargetConfig | None:
    try:
        from qe.ingest import store as project_store

        proj = project_store.get(project_id)
    except Exception:  # noqa: BLE001 - no stored project (e.g. injected resolver): no config
        return None
    return proj.target_config if proj is not None else None


def _resolve(project_id: str) -> ResolvedProject:
    try:
        project = resolve_target(project_id)
    except ResolveError as exc:
        audit.log(store.campaigns_dir(), "campaign_refused", project_id=project_id,
                  reason=exc.detail)
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None
    if not project.authorized:
        audit.log(store.campaigns_dir(), "campaign_refused", project_id=project_id,
                  reason="not authorized")
        raise HTTPException(
            status_code=403,
            detail="project is not marked authorized: confirm you own or are permitted to test "
                   "this application before running a campaign")
    return project


def _get(cid: str) -> dict[str, Any]:
    rec = manager.load(cid)
    if rec is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return rec


@router.post("/api/campaigns", status_code=202)
def create_campaign(req: CampaignRequest) -> dict[str, Any]:
    project = _resolve(req.project_id)
    _check_targets(req)
    policy = _policy(req.policy, req.include_security, req.use_example_policy)
    if req.plan is not None:
        try:
            validate_import(req.plan)
        except PlanError as exc:
            raise HTTPException(status_code=422, detail=f"invalid plan: {exc}") from None
    elif not project.qa_pairs and not project.documents:
        raise HTTPException(status_code=422,
                            detail="the project has no documents or Q&A pairs and no plan was "
                                   "supplied: there is nothing real to test")
    params = CampaignParams(
        name=req.name, project_id=req.project_id, risk_focus=req.risk_focus,
        repeats=req.repeats, max_cases=req.max_cases, max_calls=req.max_calls,
        timeout_s=req.timeout_s, include_security=req.include_security,
        generate_with_llm=req.generate_with_llm, seed=req.seed, alpha=req.alpha,
        policy=policy, use_example_policy=req.use_example_policy, imported_plan=req.plan)
    return manager.start(project, params, req.targets, _project_config(req.project_id),
                         regression.suite_items(runs_dir(), req.project_id))


@router.get("/api/campaigns")
def list_campaigns() -> list[dict[str, Any]]:
    return manager.list_all()


@router.get("/api/campaigns/{cid}")
def get_campaign(cid: str) -> dict[str, Any]:
    return manager.public(_get(cid))


@router.get("/api/campaigns/{cid}/plan")
def get_plan(cid: str) -> dict[str, Any]:
    _get(cid)
    built = store.load_plan(cid)
    if built is None:
        raise HTTPException(status_code=409, detail="the plan has not been generated yet")
    return built


@router.post("/api/campaigns/{cid}/cancel", status_code=202)
def cancel_campaign(cid: str) -> dict[str, Any]:
    out = manager.cancel(cid)
    if out is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return out


@router.post("/api/campaigns/{cid}/resume", status_code=202)
def resume_campaign(cid: str) -> dict[str, Any]:
    rec = _get(cid)
    project = _resolve(rec["project_id"])
    try:
        return manager.resume(cid, project, _project_config(rec["project_id"]))
    except manager.CampaignError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None


@router.post("/api/campaigns/{cid}/signoff")
def signoff_campaign(cid: str, req: SignoffRequest) -> dict[str, Any]:
    _get(cid)
    try:
        dec = manager.signoff(cid, req.target_label, req.reviewer, req.decision, req.rationale)
    except KeyError:
        raise HTTPException(status_code=422,
                            detail=f"unknown target_label {req.target_label!r}") from None
    except manager.SignoffError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"id": cid, "target_label": req.target_label, "decision": dec}


@router.post("/api/campaigns/{cid}/items/{item_id}/confirm")
def confirm_case(cid: str, item_id: str, req: ConfirmRequest) -> dict[str, Any]:
    _get(cid)
    try:
        return manager.confirm_item(cid, item_id, req.reviewer)
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found") from None
    except manager.SignoffError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.get("/api/campaigns/{cid}/events")
def campaign_events(cid: str, include_runs: bool = False, limit: int = 1000,
                    ) -> dict[str, Any]:
    _get(cid)
    limit = max(1, min(limit, 5000))
    with store.ledger(cid) as lg:
        report = lg.verify()
        entries = [e for e in lg.entries()
                   if include_runs or not e.event.key.startswith("crun:")]
        total_runs = sum(1 for e in lg.entries() if e.event.key.startswith("crun:"))
    shown = entries[:limit]
    return {
        "campaign_id": cid, "ledger_ok": report.ok, "ledger_entries": report.checked,
        "recorded_target_calls": total_runs, "total": len(entries),
        "entries": [{"seq": e.seq, "hash": e.hash, "key": e.event.key,
                     "type": e.event.type.value, "producer": e.event.producer,
                     "producer_kind": e.event.producer_kind.value,
                     "action": e.event.payload.get("action"),
                     "at": e.event.payload.get("at"),
                     "payload": _event_payload(e.event.payload)} for e in shown]}


def _event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Audit payloads minus bulky/internal fields (never raw target answers)."""
    return {k: v for k, v in payload.items()
            if k not in ("answer", "contexts", "action", "at", "kind")}
