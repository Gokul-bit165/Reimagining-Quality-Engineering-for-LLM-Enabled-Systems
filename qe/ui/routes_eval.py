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
from qe.realeval.assemble import EXAMPLE_APPETITE, SECURITY_METRIC
from qe.realeval.dataset import EvalItem
from qe.realeval.exports import dataset_jsonl, monitoring_plan, report_markdown
from qe.realeval.generators import generator_from_env
from qe.realeval.judge import judge_from_env
from qe.realeval.resolver import ResolveError, resolve_target
from qe.realeval.runner import (
    DEFAULT_MAX_QUESTIONS,
    DEFAULT_REPEATS,
    Budget,
    EvalParams,
    Inputs,
)
from sandbox_apps._common.real_llm import missing_llm_config

router = APIRouter()
MAX_CALLS_CAP = 2000
DEFAULT_TIMEOUT_S = 900.0
ID_RE = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"


class EvalRequest(BaseModel):
    project_id: str = Field(pattern=ID_RE)
    max_questions: int = Field(default=DEFAULT_MAX_QUESTIONS, ge=1, le=200)
    repeats: int = Field(default=DEFAULT_REPEATS, ge=1, le=10)
    include_security: bool = True
    generate_questions: bool = True
    policy: dict[str, Any] | None = None
    use_example_policy: bool = False  # explicit opt-in to the NON-binding example policy
    # additions beyond the original contract
    risk_focus: list[str] = Field(default_factory=list, max_length=20)
    seed: int = Field(default=0, ge=0, le=2**31)
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


def _require_policy_choice(req: EvalRequest, policy: Policy | None) -> None:
    """A release decision needs a risk appetite the USER chose. No silent default."""
    if policy is None and not req.use_example_policy:
        raise HTTPException(
            status_code=422,
            detail="no policy chosen: supply `policy` (see GET /api/policy/template) or pass "
                   "`use_example_policy: true` to explicitly use the non-binding example policy")
    if (policy is not None and req.include_security
            and SECURITY_METRIC not in policy.required_evidence):
        raise HTTPException(
            status_code=422,
            detail=f"invalid policy: security probes are on, so {SECURITY_METRIC} must be in "
                   "required_evidence (with a risk_appetite), or set include_security=false "
                   "(the decision then cannot be RELEASE: 'security not tested')")


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
    _require_policy_choice(req, policy)
    generator = generator_from_env() if req.generate_questions else None
    if not project.qa_pairs and generator is None:
        raise HTTPException(
            status_code=422,
            detail="no Q&A pairs supplied and no real LLM question generator is configured: "
                   "supply Q&A pairs, or set QE_ALLOW_REAL_LLM=1, a provider key "
                   "(GROQ_API_KEY or OPENROUTER_API_KEY) and QE_LLM_MODEL in the backend "
                   "environment")
    prior_failures, prior_pass = jobs.prior_context(req.project_id)
    inputs = Inputs(project=project, generator=generator,
                    judge=judge_from_env(generator.family if generator else None),
                    prior_failures=prior_failures,
                    prior_pass=prior_pass,
                    regression_items=regression.suite_items(jobs.runs_dir(), req.project_id))
    params = EvalParams(max_questions=req.max_questions, repeats=req.repeats,
                        include_security=req.include_security,
                        generate_questions=req.generate_questions, policy=policy,
                        risk_focus=req.risk_focus, seed=req.seed)
    out = jobs.start(req.project_id, params, inputs, Budget(req.max_calls, req.timeout_s),
                     req.monitoring)
    audit.log(ed, "evaluation_started", evaluation_id=out["id"], project_id=req.project_id,
              max_calls=req.max_calls)
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
    failed = [r for r in rec["items"] if r["passed"] is False
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


METRIC_DOCS = (
    ("answer_correctness", "Share of root questions whose answer matches the reference "
                           "(deterministic lexical check)."),
    ("faithfulness", "Share of root questions whose answer is supported by the passage text the "
                     "app returned. Not measured when the app returns ids/filenames."),
    ("citation_validity", "Share of answers whose citations resolve."),
    ("retrieval_hit_rate", "Share of questions where retrieval surfaced the evidence."),
    ("refusal_correctness", "Share of unanswerable questions correctly refused."),
    ("completeness", "Share of answerable questions answered without refusal or error."),
    ("injection_resistance", "Share of attack probes resisted (outcome oracles). Required "
                             "whenever security probes run."),
    ("error_rate", "Share of root questions whose target call errored (here the metric IS a "
                   "failure rate)."),
    ("stability_pass_k", "Share of root questions passing on every repeat."),
    ("overall_pass_rate", "Share of root questions passing every applicable check."),
)


@router.get("/api/policy/template")
def policy_template() -> dict[str, Any]:
    """A documented policy skeleton. Every number is null on purpose: the risk appetite is the
    user's decision, so the UI must make them choose; nothing here is a recommended default."""
    return {
        "policy": {
            "policy_id": None, "version": None, "loss_matrix": {},
            "required_evidence": [],
            "risk_appetite": {name: None for name, _ in METRIC_DOCS},
            "conditional_rules": [], "min_improvement": {}},
        "fields": {
            "policy_id": "your name for this policy (string)",
            "version": "your version label (string)",
            "required_evidence": "metric names that must be measured and within appetite to "
                                 f"RELEASE; must include {SECURITY_METRIC} when security runs",
            "risk_appetite": "metric -> the MAXIMUM failure rate (0..1) you tolerate; every "
                             "required metric needs one; the 95% interval must lie within it",
            "conditional_rules": "optional [{metric, max_failure_rate, condition}] for CONDITIONAL",
            "loss_matrix": "optional; leave {} unless you use expected-loss decisions"},
        "metrics": [{"name": n, "description": d} for n, d in METRIC_DOCS],
        "notes": ["Fill risk_appetite for every metric you list in required_evidence.",
                  "null means 'you have not chosen'; POST /api/evaluations rejects it (422).",
                  "An example policy exists for demos only: pass use_example_policy=true "
                  f"(appetites {dict(EXAMPLE_APPETITE)}); decisions then say policy_is_example."],
    }


@router.get("/api/llm/status")
def llm_status() -> dict[str, Any]:
    """Whether a real LLM is configured, as setting NAMES only (never values)."""
    missing = missing_llm_config()
    return {"configured": not missing, "missing": missing}
