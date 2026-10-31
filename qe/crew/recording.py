"""Record crew LLM output as DRAFT/PROPOSAL events only (R3, ADR-0001)."""

from __future__ import annotations

from typing import Any

from qe.core.events import Event, EventType, ProducerKind, check_write_permission
from qe.core.ledger import Entry, Ledger
from qe.core.schemas import ModelRef
from qe.crew.prompts import Prompt

DRAFT_TYPES = frozenset(
    {
        EventType.RISK_PROPOSED,
        EventType.TEST_DRAFTED,
        EventType.ATTACK_ATTEMPTED,
        EventType.VALIDITY_VERDICT,
        EventType.NARRATIVE_DRAFTED,
    }
)


def record_draft(
    ledger: Ledger,
    etype: EventType,
    key: str,
    payload: dict[str, Any],
    prompt: Prompt,
    model: ModelRef,
    raw_output: str,
) -> Entry:
    if etype not in DRAFT_TYPES:
        check_write_permission(etype, ProducerKind.LLM_AGENT)  # raises for evidence types
        raise PermissionError(f"{etype.value} is not a crew draft type")
    body = {
        **payload,
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "prompt_sha256": prompt.sha256,
        "model": model.model_dump(mode="json"),
        "raw_output": raw_output,
    }
    return ledger.append(
        Event(
            key=key,
            type=etype,
            producer=f"crew:{prompt.name}:{model.family}",
            producer_kind=ProducerKind.LLM_AGENT,
            payload=body,
        )
    )
