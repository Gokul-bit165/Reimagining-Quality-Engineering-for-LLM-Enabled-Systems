"""Ledger event vocabulary and write-permission classes (rule R3)."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from qe.core.ids import canonical_json


class ProducerKind(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM_AGENT = "llm_agent"
    HUMAN = "human"


class EventType(StrEnum):
    # Evidence and decisions: deterministic services only.
    CAPABILITY_INVENTORY = "capability_inventory"
    RUN_RECORDED = "run_recorded"
    TRACE_RECORDED = "trace_recorded"
    EVIDENCE_RECORDED = "evidence_recorded"
    VERDICT_ISSUED = "verdict_issued"
    ADJUDICATED = "adjudicated"
    FAILURE_RECORDED = "failure_recorded"
    ESTIMATE_COMPUTED = "estimate_computed"
    MISSING_EVIDENCE = "missing_evidence"
    DECISION_ISSUED = "decision_issued"
    # Proposals and drafts: LLM agents may write these; they are never evidence.
    RISK_PROPOSED = "risk_proposed"
    TEST_DRAFTED = "test_drafted"
    ATTACK_ATTEMPTED = "attack_attempted"
    VALIDITY_VERDICT = "validity_verdict"
    NARRATIVE_DRAFTED = "narrative_drafted"
    # Human only.
    SIGNOFF_RECORDED = "signoff_recorded"


DETERMINISTIC_ONLY: frozenset[EventType] = frozenset(
    {
        EventType.CAPABILITY_INVENTORY,
        EventType.RUN_RECORDED,
        EventType.TRACE_RECORDED,
        EventType.EVIDENCE_RECORDED,
        EventType.VERDICT_ISSUED,
        EventType.ADJUDICATED,
        EventType.FAILURE_RECORDED,
        EventType.ESTIMATE_COMPUTED,
        EventType.MISSING_EVIDENCE,
        EventType.DECISION_ISSUED,
    }
)
HUMAN_ONLY: frozenset[EventType] = frozenset({EventType.SIGNOFF_RECORDED})


def check_write_permission(event_type: EventType, kind: ProducerKind) -> None:
    if event_type in DETERMINISTIC_ONLY and kind is not ProducerKind.DETERMINISTIC:
        raise PermissionError(f"{kind.value} may not write {event_type.value} (R3)")
    if event_type in HUMAN_ONLY and kind is not ProducerKind.HUMAN:
        raise PermissionError(f"{kind.value} may not write {event_type.value}")


class Event(BaseModel):
    """An immutable ledger event. `key` is the idempotency key (unique per ledger)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    type: EventType
    producer: str
    producer_kind: ProducerKind
    payload: dict[str, Any]

    @field_validator("key", "producer")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("payload")
    @classmethod
    def _json_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        normalised: dict[str, Any] = json.loads(canonical_json(v))
        return normalised

    def canonical(self) -> str:
        return canonical_json(self.model_dump(mode="json"))
