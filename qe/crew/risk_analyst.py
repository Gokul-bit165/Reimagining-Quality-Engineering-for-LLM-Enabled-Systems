"""Risk Analyst (T2.2): LLM proposes, taxonomy + app model constrain, policy code ranks."""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import Ledger
from qe.crew.llm import CrewLLM
from qe.crew.parse import parse_json_list
from qe.crew.prompts import load_prompt
from qe.crew.recording import record_draft
from qe.model.app_model import AppModel
from qe.risk.register import RiskProposal
from qe.risk.taxonomy import Taxonomy


class RiskResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    accepted: tuple[RiskProposal, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()  # (taxonomy_id/component, reason)
    parse_error: str | None = None


async def propose_risks(
    llm: CrewLLM, model: AppModel, taxonomy: Taxonomy, ledger: Ledger
) -> RiskResult:
    prompt = load_prompt("risk_analyst")
    user = json.dumps(
        {"components": sorted(model.node_ids()), "taxonomy": sorted(taxonomy.ids())},
        sort_keys=True,
    )
    raw = await llm.complete(prompt.text, user)
    run_key = content_id([prompt.sha256, llm.model.model_dump(mode="json"), user])
    try:
        items = parse_json_list(raw)
    except ValueError as exc:
        record_draft(ledger, EventType.NARRATIVE_DRAFTED, f"risk-parse:{run_key}",
                     {"status": "unparseable", "error": str(exc)}, prompt, llm.model, raw)
        return RiskResult(parse_error=str(exc))
    accepted: list[RiskProposal] = []
    rejected: list[tuple[str, str]] = []
    for item in items:
        tid, comp = str(item.get("taxonomy_id", "")), str(item.get("component", ""))
        label = f"{tid}/{comp}"
        reason: str | None = None
        proposal: RiskProposal | None = None
        if tid not in taxonomy.ids():
            reason = f"taxonomy_id not in {taxonomy.taxonomy}"
        elif comp not in model.node_ids():
            reason = "component not in app model"
        else:
            try:
                proposal = RiskProposal(
                    risk_id="R-" + content_id([tid, comp])[:10], taxonomy_id=tid, component=comp,
                    rationale=str(item.get("rationale", "")),
                )
            except ValidationError:
                reason = "empty field"
        payload = {"status": "accepted" if proposal else "rejected", "item": item,
                   "taxonomy": taxonomy.taxonomy, "taxonomy_sha256": taxonomy.sha256}
        if reason:
            payload["reason"] = reason
        record_draft(ledger, EventType.RISK_PROPOSED, f"risk:{run_key}:{content_id(item)}",
                     payload, prompt, llm.model, raw)
        if proposal and proposal not in accepted:
            accepted.append(proposal)
        elif reason:
            rejected.append((label, reason))
    return RiskResult(accepted=tuple(accepted), rejected=tuple(rejected))
