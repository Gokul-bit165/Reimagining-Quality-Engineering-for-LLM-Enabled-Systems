"""Write crew output to the ledger as proposal/draft/validity events ONLY (R3)."""

from __future__ import annotations

from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import Entry, Ledger
from qe.crew.llm import LLMClient
from qe.crew.prompt_store import Prompt

CREW_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.RISK_PROPOSED,
        EventType.TEST_DRAFTED,
        EventType.VALIDITY_VERDICT,
        EventType.NARRATIVE_DRAFTED,
    }
)


def record_crew_event(
    ledger: Ledger,
    etype: EventType,
    producer: str,
    payload: dict[str, Any],
    *,
    prompt: Prompt | None = None,
    llm: LLMClient | None = None,
    kind: ProducerKind = ProducerKind.LLM_AGENT,
) -> Entry:
    """Append a crew event. The key is content-derived so re-runs are idempotent."""
    if etype not in CREW_EVENT_TYPES:
        raise PermissionError(f"crew may not write {etype.value} (R3)")
    body = dict(payload)
    if prompt is not None:
        body["prompt_name"] = prompt.name
        body["prompt_sha256"] = prompt.sha256
    if llm is not None:
        body["model_family"] = llm.family
        body["model_name"] = llm.model_name
    key = f"{etype.value}:{producer}:{content_id(body)[:32]}"
    event = Event(key=key, type=etype, producer=producer, producer_kind=kind, payload=body)
    existing = ledger.find_by_key(key)
    return existing if existing is not None else ledger.append(event)
