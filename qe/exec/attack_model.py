"""Serializable attack description shared by attackers (propose) and the sandbox runner (decide).

An attack carries NO verdict field: whether it worked is decided only by the oracles in
`sandbox_runner` (R5), never by the attacker or by an LLM reading the transcript.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from qe.core.schemas import Frozen


class Surface(StrEnum):
    DIRECT_INJECTION = "direct_injection"
    INDIRECT_INJECTION = "indirect_injection"
    RAG_POISONING = "rag_poisoning"
    TOOL_MISUSE = "tool_misuse"
    MEMORY_POISONING = "memory_poisoning"


class SetupOp(Frozen):
    """Environment preparation granted to the attacker's capability class (e.g. plant a note)."""

    op: Literal["plant_note", "remove_note", "ingest_document", "drop_unofficial_docs"]
    args: dict[str, str] = Field(default_factory=dict)


class OracleSpec(Frozen):
    kind: Literal[
        "canary_at_sink", "state_diff", "forbidden_tool", "marker_in_output", "sink_policy",
        "output_predicate"
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class AttackStep(Frozen):
    actor: Literal["attacker", "victim"]
    request: dict[str, Any]


class AttackSpec(Frozen):
    attack_id: str
    pair_id: str
    surface: Surface
    env: str  # sandbox environment name, e.g. "toolagent" | "rag"
    attacker_class: str  # e.g. "static_template" | "adaptive_mutation" | "external:<label>"
    attempt_index: int = Field(ge=0)
    payload: str  # attacker-controlled text (untrusted data)
    setup: tuple[SetupOp, ...] = ()
    steps: tuple[AttackStep, ...]
    oracles: tuple[OracleSpec, ...]
    utility_regex: str | None = None  # did the benign victim task still succeed?
