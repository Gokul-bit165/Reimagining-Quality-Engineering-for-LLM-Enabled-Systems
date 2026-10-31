"""Risk Analyst (LLM, taxonomy-constrained). Proposals only; ranking is the Planner's job."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from qe.core.events import EventType
from qe.core.ledger import Ledger
from qe.crew.llm import LLMClient
from qe.crew.prompt_store import Prompt, load_prompt
from qe.crew.record import record_crew_event
from qe.model.builder import AppModel
from qe.risk.register import RiskItem
from qe.risk.taxonomy import Taxonomy, allowed_ids

PROMPT_NAME = "risk_analyst_v1"
PRODUCER = "risk_analyst"
APP_COMPONENT = "app"


@dataclass(frozen=True)
class Rejection:
    proposal: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class RiskProposals:
    accepted: tuple[RiskItem, ...]
    rejected: tuple[Rejection, ...]


def _parse(raw: str) -> list[Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    risks = data.get("risks") if isinstance(data, dict) else None
    return risks if isinstance(risks, list) else []


def _check(
    p: Any, allowed: frozenset[str], components: frozenset[str]
) -> tuple[RiskItem | None, str]:
    if not isinstance(p, dict):
        return None, "proposal is not an object"
    category, component = p.get("category"), p.get("component", APP_COMPONENT)
    if not isinstance(category, str) or category not in allowed:
        return None, "category not in taxonomy"
    if not isinstance(component, str) or component not in components:
        return None, "component not in app model"
    item = RiskItem(category=category, component=component, rationale=str(p.get("rationale", "")))
    return item, ""


def propose_risks(
    llm: LLMClient,
    model: AppModel,
    taxonomies: tuple[Taxonomy, ...],
    ledger: Ledger | None = None,
    prompt: Prompt | None = None,
) -> RiskProposals:
    """Ask the LLM for risks; keep only proposals whose category is in the taxonomy."""
    prompt = prompt or load_prompt(PROMPT_NAME)
    allowed = allowed_ids(taxonomies)
    components = frozenset({APP_COMPONENT, *(n.id for n in model.nodes)})
    user = json.dumps(
        {
            "model": {
                "nodes": [n.id for n in model.nodes],
                "edges": [[e.src, e.dst, e.kind] for e in model.edges],
            },
            "taxonomy": sorted(allowed),
        },
        sort_keys=True,
    )
    raw = llm.complete(
        [{"role": "system", "content": prompt.text}, {"role": "user", "content": user}]
    )
    accepted: list[RiskItem] = []
    rejected: list[Rejection] = []
    for p in _parse(raw):
        item, reason = _check(p, allowed, components)
        if item is None:
            rejected.append(Rejection(p if isinstance(p, dict) else {"raw": str(p)}, reason))
        else:
            accepted.append(item)
    if ledger is not None:
        for item in accepted:
            body = {"status": "accepted", **item.model_dump(mode="json")}
            record_crew_event(ledger, EventType.RISK_PROPOSED, PRODUCER, body, prompt=prompt, llm=llm)
        for rej in rejected:
            body = {"status": "rejected", "reason": rej.reason, "proposal": rej.proposal}
            record_crew_event(ledger, EventType.RISK_PROPOSED, PRODUCER, body, prompt=prompt, llm=llm)
    return RiskProposals(tuple(accepted), tuple(rejected))
