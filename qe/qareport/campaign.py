"""Adapter from a campaign (qe.campaign: one ledger, plan.json, campaign.json) to EvidenceInput.

The functions here take plain files/dicts (ledger path, plan dict, campaign-context dict) so the
same code builds the report live and re-derives it offline from an evidence bundle. The plan is
not stored in the ledger, but its id is anchored there (`plan_created` audit event): the adapter
recomputes the id from the plan cases and refuses a plan that does not match.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import SQLiteLedger
from qe.qareport.evidence import host_only, meta_for_project
from qe.qareport.models import (
    EntryRef,
    EvidenceInput,
    ReportContext,
    ReportInput,
    TargetContext,
    TargetMeta,
    ToolInfo,
)
from qe.realeval.dataset import EvalItem

RUN_PREFIX = "crun:"
PLAN_FILE = "campaign_plan.json"
CONTEXT_FILE = "campaign_context.json"
NOTE = ("campaign ledgers record each target call (crun:*) and stage events; per-item verdicts "
        "are recomputed deterministically from the recorded responses (qe.realeval.assemble), "
        "not stored as separate ledger events")


def sanitize_context(rec: dict[str, Any]) -> dict[str, Any]:
    """The campaign.json fields the report needs, with endpoints reduced to host[:port] and no
    secrets (only the NAME of an api-key secret is ever stored by the campaign)."""
    targets = []
    for t in rec["targets"]:
        targets.append({
            "label": t["label"], "kind": t["kind"],
            "endpoint_host": host_only(t.get("endpoint_url") or t.get("base_url")),
            "model": t.get("model"), "api_key_secret_name": t.get("api_key_secret"),
            "metadata": {k: str(v) for k, v in (t.get("metadata") or {}).items()}})
    return {"id": rec["id"], "name": rec.get("name") or rec["id"],
            "project_id": rec["project_id"], "created": rec.get("created"),
            "state": rec.get("state"), "incomplete": rec.get("incomplete"),
            "params": rec["params"], "notes": list(rec.get("notes", [])), "targets": targets}


def _anchored_plan_id(ledger: SQLiteLedger) -> str | None:
    for e in ledger.entries():
        if e.event.payload.get("action") == "plan_created":
            return str(e.event.payload.get("plan_id"))
    return None


def check_plan(plan: dict[str, Any], anchored: str | None) -> None:
    items = [EvalItem.model_validate(c).model_dump(mode="json") for c in plan["cases"]]
    computed = "plan-" + content_id(items)[:12]
    if anchored is None:
        raise ValueError("the campaign ledger has no plan_created event: plan is not anchored")
    if computed != anchored or plan.get("plan_id") != anchored:
        raise ValueError(f"plan does not match the plan id anchored in the ledger "
                         f"(ledger {anchored}, recomputed {computed})")


def _scan(path: Path, labels: list[str]) -> dict[str, Any]:
    lg = SQLiteLedger(path)
    try:
        rep = lg.verify()
        runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
        entries: dict[str, dict[str, EntryRef]] = {lbl: {} for lbl in labels}
        signoffs: dict[str, list[dict[str, Any]]] = {lbl: [] for lbl in labels}
        confirmations: list[dict[str, Any]] = []
        confirmed: list[str] = []
        for e in lg.entries():
            key, pl = e.event.key, e.event.payload
            if key.startswith(RUN_PREFIX):
                runs.setdefault(pl["target"], {}).setdefault(pl["item_id"], []).append(pl)
                if pl["target"] in entries:
                    entries[pl["target"]][key] = EntryRef(seq=e.seq, hash=e.hash)
            elif key.startswith("confirm:"):
                confirmed.append(str(pl["item_id"]))
                confirmations.append({**pl, "seq": e.seq, "hash": e.hash})
            elif e.event.type is EventType.SIGNOFF_RECORDED and pl.get("target") in signoffs:
                signoffs[pl["target"]].append({**pl, "seq": e.seq, "hash": e.hash})
        for per_item in runs.values():
            for recs in per_item.values():
                recs.sort(key=lambda r: r["rep"])
        return {"runs": runs, "entries": entries, "signoffs": signoffs,
                "confirmations": confirmations, "confirmed": confirmed, "head": lg.head(),
                "length": len(lg), "chain_ok": rep.ok, "chain_reason": rep.reason,
                "plan_id": _anchored_plan_id(lg)}
    finally:
        lg.close()


def evidence_from_campaign(path: Path, plan: dict[str, Any], cctx: dict[str, Any],
                           targets: list[TargetContext]) -> list[EvidenceInput]:
    from qe.campaign import analysis  # lazy: evaluations must work without the campaign package
    from qe.core.schemas import Policy

    labels = [t.name for t in targets]
    scan = _scan(path, labels)
    check_plan(plan, scan["plan_id"])
    params = cctx["params"]
    policy = Policy.model_validate(params["policy"]) if params.get("policy") else None
    repeats = int(plan["repeats"])
    cases = analysis.common_items(plan["cases"], labels, scan["runs"], repeats)
    config_base: dict[str, Any] = {
        "doc_names": plan["doc_names"], "repeats": repeats,
        "include_security": plan["include_security"],
        "require_citations": plan["require_citations"],
        "policy": params.get("policy"), "seed": params.get("seed"),
        "risk_focus": list(params.get("risk_focus", [])), "notes": list(cctx.get("notes", [])),
        "max_questions": params.get("max_cases"),
        "budget": {"max_calls": params.get("max_calls"), "timeout_s": params.get("timeout_s")},
        "prior_pass": {}, "campaign_id": cctx["id"], "plan_id": plan["plan_id"]}
    scen = {str(c["id"]): str(c.get("scenario", "")) for c in plan["cases"] if c.get("scenario")}
    out: list[EvidenceInput] = []
    for tctx in targets:
        label = tctx.name
        mine = scan["runs"].get(label, {})
        result = analysis.verify(plan, cases, label, scan["runs"], policy,
                                 cctx.get("incomplete"), scan["confirmed"])
        runs = {str(c["id"]): mine[str(c["id"])][:repeats] for c in cases}
        out.append(EvidenceInput(
            name=label, eval_id=cctx["id"], project_id=cctx["project_id"], created=tctx.created,
            state=str(cctx.get("state") or "done"), params=params,
            config={**config_base, "incomplete": cctx.get("incomplete")},
            items_planned=[dict(c) for c in plan["cases"]], result=result, runs=runs,
            entries=scan["entries"][label], head=scan["head"], length=scan["length"],
            chain_ok=scan["chain_ok"], chain_reason=scan["chain_reason"],
            signoffs=scan["signoffs"][label], confirmations=scan["confirmations"],
            meta=tctx.meta, monitoring=tctx.monitoring,
            run_key_template=RUN_PREFIX + "{target}:{item}:{rep}", verdict_key_template=None,
            scenarios=scen, source_notes=[NOTE]))
    return out


def target_contexts(cctx: dict[str, Any], ledger_file: str, created: float | None,
                    ) -> list[TargetContext]:
    project_meta = meta_for_project(cctx["project_id"])
    out = []
    for t in cctx["targets"]:
        meta = TargetMeta(
            endpoint_host=t["endpoint_host"], execution_mode=t["kind"],
            authorized=project_meta.authorized, authorized_at=project_meta.authorized_at,
            versions={**({"model": t["model"]} if t.get("model") else {}), **t["metadata"]},
            notes=["authorization is the project-level attestation"])
        out.append(TargetContext(
            name=t["label"], eval_id=cctx["id"], project_id=cctx["project_id"], created=created,
            state=str(cctx.get("state") or "done"), params=cctx["params"], meta=meta,
            ledger_file=ledger_file))
    return out


def report_input(cctx: dict[str, Any], plan: dict[str, Any], ledger_path: Path,
                 ledger_file: str, tool: ToolInfo) -> tuple[ReportInput, ReportContext]:
    tctxs = target_contexts(cctx, ledger_file, cctx.get("created"))
    ctx = ReportContext(kind="campaign", id=cctx["id"],
                        title=f"Quality-tester report: campaign {cctx['name']} ({cctx['id']})",
                        created=cctx.get("created"), tool=tool, notes=[],
                        extra_files=[PLAN_FILE, CONTEXT_FILE], targets=tctxs)
    return inputs_from_context(ctx, ledger_path, plan, cctx), ctx


def inputs_from_context(ctx: ReportContext, ledger_path: Path, plan: dict[str, Any],
                        cctx: dict[str, Any]) -> ReportInput:
    targets = evidence_from_campaign(ledger_path, plan, cctx, ctx.targets)
    return ReportInput(kind="campaign", id=ctx.id, title=ctx.title, created=ctx.created,
                       tool=ctx.tool, targets=targets, notes=ctx.notes)
