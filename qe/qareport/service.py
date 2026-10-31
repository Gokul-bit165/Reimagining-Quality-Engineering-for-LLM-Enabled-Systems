"""Glue between the stores (evaluation jobs, campaigns) and the report generator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from qe.qareport.build import build_report
from qe.qareport.bundle import build_bundle, ledger_file_name, pretty
from qe.qareport.evidence import load_target, meta_for_project, tool_info
from qe.qareport.models import ReportContext, ReportInput, TargetContext, ToolInfo
from qe.qareport.render_html import render_html
from qe.qareport.render_md import render_markdown

FINISHED = ("done", "cancelled", "failed")


class ReportNotFoundError(Exception):
    pass


class ReportConflictError(Exception):
    pass


@dataclass
class Source:
    """Everything needed to render a report or build a bundle for one evaluation/campaign."""

    inp: ReportInput
    context: ReportContext
    ledgers: dict[str, Path]
    project_ids: list[str]
    extra_files: dict[str, bytes] = field(default_factory=dict)


@lru_cache(maxsize=1)
def _tool() -> ToolInfo:
    return tool_info()


def evaluation_source(eid: str) -> Source:
    from qe.realeval import jobs

    rec = jobs.load(eid)
    if rec is None:
        raise ReportNotFoundError("evaluation not found")
    if rec["state"] not in FINISHED:
        raise ReportConflictError(f"evaluation is {rec['state']}: a report needs a finished run")
    path = jobs.evals_dir() / f"{eid}.sqlite"
    if not path.is_file():
        raise ReportConflictError("evaluation has no ledger: nothing to report")
    name = ledger_file_name(rec["project_id"], 0)
    tctx = TargetContext(
        name=rec["project_id"], eval_id=eid, project_id=rec["project_id"],
        created=rec.get("created"), state=rec["state"], params=rec.get("params") or {},
        meta=meta_for_project(rec["project_id"]), monitoring=rec.get("monitoring"),
        ledger_file=name)
    try:
        ev = load_target(path, tctx)
    except ValueError as exc:
        raise ReportConflictError(str(exc)) from None
    ctx = ReportContext(kind="evaluation", id=eid,
                        title=f"Quality-tester report: evaluation {eid}",
                        created=rec.get("created"), tool=_tool(), targets=[tctx])
    inp = ReportInput(kind="evaluation", id=eid, title=ctx.title, created=ctx.created,
                      tool=ctx.tool, targets=[ev])
    return Source(inp, ctx, {name: path}, [rec["project_id"]])


def campaign_source(cid: str) -> Source:
    from qe.campaign import store
    from qe.qareport import campaign as adapter

    try:
        rec = store.load_raw(cid)
    except KeyError:
        rec = None
    if rec is None:
        raise ReportNotFoundError("campaign not found")
    if rec["state"] not in FINISHED:
        raise ReportConflictError(f"campaign is {rec['state']}: a report needs a finished run")
    plan = store.load_plan(cid)
    path = store.campaign_dir(cid) / "ledger.sqlite"
    if plan is None or not path.is_file():
        raise ReportConflictError("campaign has no plan or ledger yet: nothing to report")
    cctx = adapter.sanitize_context(rec)
    name = ledger_file_name("campaign", 0)
    try:
        inp, ctx = adapter.report_input(cctx, plan, path, name, _tool())
    except ValueError as exc:
        raise ReportConflictError(str(exc)) from None
    extra = {adapter.PLAN_FILE: pretty(plan).encode("utf-8"),
             adapter.CONTEXT_FILE: pretty(cctx).encode("utf-8")}
    return Source(inp, ctx, {name: path}, [rec["project_id"]], extra)


def render(source: Source, fmt: str) -> tuple[bytes, str]:
    """(body, media type) for html | md | json."""
    report = build_report(source.inp)
    if fmt == "html":
        return render_html(report).encode("utf-8"), "text/html; charset=utf-8"
    if fmt == "md":
        return render_markdown(report).encode("utf-8"), "text/markdown; charset=utf-8"
    return json.dumps(report, indent=2, sort_keys=True,
                      ensure_ascii=False).encode("utf-8"), "application/json"


def bundle(source: Source) -> bytes:
    from qe.ingest.vault import VAULT

    secrets = [v for pid in source.project_ids for v in VAULT.get(pid).values()]
    try:
        return build_bundle(source.inp, source.context, source.ledgers, secrets,
                            source.extra_files)
    except ValueError as exc:
        raise ReportConflictError(str(exc)) from None
