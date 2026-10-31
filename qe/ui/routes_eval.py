"""HTTP API for evaluating a user's real RAG app. See qe.realeval for the engine."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from qe.core.schemas import Policy
from qe.policy.engine import decide
from qe.realeval import audit, jobs, regression
from qe.realeval.dataset import EvalItem
from qe.realeval.exports import dataset_jsonl, monitoring_plan, report_markdown
from qe.realeval.generators import generator_from_env
from qe.realeval.resolver import ResolveError, resolve_target
from qe.realeval.runner import Budget, EvalParams, Inputs

router = APIRouter()
MAX_CALLS_CAP = 2000
DEFAULT_TIMEOUT_S = 900.0
ID_RE = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"


class EvalRequest(BaseModel):
    project_id: str = Field(pattern=ID_RE)
    max_questions: int = Field(default=20, ge=1, le=200)
    repeats: int = Field(default=1, ge=1, le=10)
    include_security: bool = True
    generate_questions: bool = True
    policy: dict[str, Any] | None = None
    # additions beyond the original contract
    risk_focus: list[str] = Field(default_factory=list, max_length=20)
    seed: int = Field(default=0, ge=0, le=2**31)
    allow_synthetic: bool = False
    max_calls: int = Field(default=500, ge=1, le=MAX_CALLS_CAP)
    timeout_s: float = Field(default=DEFAULT_TIMEOUT_S, gt=0, le=3600)
    monitoring: dict[str, Any] | None = None


class SignoffRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)
    decision: Literal["approve", "reject", "approved", "rejected"]
    rationale: str = Field(default="", max_length=2000)


class ConfirmRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=100)


class RegressionRequest(BaseModel):
    item_ids: list[str] | None = None


def _policy(raw: dict[str, Any] | None) -> Policy | None:
    if raw is None:
        return None
    try:
        pol = Policy.model_validate(raw)
        decide(pol, [])  # rejects a policy whose required_evidence lacks a risk_appetite
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid policy: {exc}") from None
    return pol


def _get(eid: str) -> dict[str, Any]:
    rec = jobs.load(eid)
    if rec is None:
        raise HTTPException(status_code=404, detail="evaluation not found")
    return rec


@router.post("/api/evaluations", status_code=202)
def create_evaluation(req: EvalRequest) -> dict[str, Any]:
    ed = jobs.evals_dir()
    try:
        project = resolve_target(req.project_id)
    except ResolveError as exc:
        audit.log(ed, "evaluation_refused", project_id=req.project_id, reason=exc.detail)
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None
    if not project.authorized:
        audit.log(ed, "evaluation_refused", project_id=req.project_id, reason="not authorized")
        raise HTTPException(
            status_code=403,
            detail="project is not marked authorized: confirm you own or are permitted to test "
                   "this application before evaluating it")
    policy = _policy(req.policy)
    generator = generator_from_env(req.allow_synthetic) if req.generate_questions else None
    if not project.qa_pairs and generator is None:
        raise HTTPException(
            status_code=422,
            detail="no Q&A pairs supplied and no question generator available: provide "
                   "questions, configure a real LLM key, or set allow_synthetic=true "
                   "(results will be labelled SYNTHETIC)")
    prior_failures, prior_pass = jobs.prior_context(req.project_id)
    inputs = Inputs(project=project, generator=generator, prior_failures=prior_failures,
                    prior_pass=prior_pass,
                    regression_items=regression.suite_items(jobs.runs_dir(), req.project_id))
    params = EvalParams(max_questions=req.max_questions, repeats=req.repeats,
                        include_security=req.include_security,
                        generate_questions=req.generate_questions, policy=policy,
                        risk_focus=req.risk_focus, seed=req.seed)
    out = jobs.start(req.project_id, params, inputs, Budget(req.max_calls, req.timeout_s),
                     req.monitoring)
    audit.log(ed, "evaluation_started", evaluation_id=out["id"], project_id=req.project_id,
              max_calls=req.max_calls, synthetic_allowed=req.allow_synthetic)
    return out


@router.get("/api/evaluations")
def list_evaluations() -> list[dict[str, Any]]:
    return jobs.list_all()


@router.get("/api/evaluations/{eval_id}")
def get_evaluation(eval_id: str) -> dict[str, Any]:
    return jobs.public(_get(eval_id))


@router.post("/api/evaluations/{eval_id}/cancel", status_code=202)
def cancel_evaluation(eval_id: str) -> dict[str, Any]:
    out = jobs.cancel(eval_id)
    if out is None:
        raise HTTPException(status_code=404, detail="evaluation not found")
    return out


@router.post("/api/evaluations/{eval_id}/signoff")
def signoff_evaluation(eval_id: str, req: SignoffRequest) -> dict[str, Any]:
    _get(eval_id)
    try:
        rec = jobs.signoff(eval_id, req.reviewer, req.decision, req.rationale)
    except jobs.SignoffError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"id": eval_id, "decision": rec["decision"]}


@router.post("/api/evaluations/{eval_id}/items/{item_id}/confirm")
def confirm_item(eval_id: str, item_id: str, req: ConfirmRequest) -> dict[str, Any]:
    _get(eval_id)
    try:
        rec = jobs.confirm_item(eval_id, item_id, req.reviewer)
    except KeyError:
        raise HTTPException(status_code=404, detail="item not found") from None
    except jobs.SignoffError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"id": eval_id, "item_id": item_id, "decision": rec["decision"],
            "advisory": rec["advisory"]}


@router.post("/api/evaluations/{eval_id}/regression")
def admit_regression(eval_id: str, req: RegressionRequest | None = None) -> dict[str, Any]:
    rec = _get(eval_id)
    wanted = set(req.item_ids) if req and req.item_ids else None
    failed = [r for r in rec["items"] if not r["passed"]
              and (wanted is None or r["id"] in wanted)]
    items = {r["id"]: EvalItem.model_validate({
        "id": r["id"], "question": r["question"], "reference_answer": r["reference_answer"],
        "source": r["source"], "answerable": r["answerable"], "risk": r["risk"],
        "lineage": r["lineage"], "probe": r.get("probe")}) for r in failed}
    admitted = regression.admit(jobs.runs_dir(), rec["project_id"], eval_id, failed, items)
    audit.log(jobs.evals_dir(), "regression_admitted", evaluation_id=eval_id,
              project_id=rec["project_id"], admitted=admitted)
    return {"admitted": admitted,
            "suite_size": len(regression.suite(jobs.runs_dir(), rec["project_id"]))}


@router.get("/api/projects/{project_id}/regression")
def list_regression(project_id: str) -> dict[str, Any]:
    try:
        cases = regression.suite(jobs.runs_dir(), project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid project id") from None
    return {"project_id": project_id, "size": len(cases), "cases": cases}


@router.get("/api/evaluations/{eval_id}/monitoring-plan")
def get_monitoring_plan(eval_id: str) -> dict[str, Any]:
    rec = _get(eval_id)
    return monitoring_plan(rec, rec.get("config", {}).get("policy"), rec.get("monitoring"))


@router.get("/api/evaluations/{eval_id}/dataset", response_class=PlainTextResponse)
def get_dataset(eval_id: str) -> PlainTextResponse:
    rec = _get(eval_id)
    audit.log(jobs.evals_dir(), "dataset_exported", evaluation_id=eval_id)
    return PlainTextResponse(dataset_jsonl(rec), media_type="application/x-ndjson")


@router.get("/api/evaluations/{eval_id}/report")
def get_report(eval_id: str, format: Literal["md", "json"] = "md") -> PlainTextResponse:
    rec = _get(eval_id)
    audit.log(jobs.evals_dir(), "report_exported", evaluation_id=eval_id, format=format)
    if format == "json":
        return PlainTextResponse(json.dumps(jobs.public(rec), indent=2),
                                 media_type="application/json")
    return PlainTextResponse(report_markdown(rec), media_type="text/markdown")
