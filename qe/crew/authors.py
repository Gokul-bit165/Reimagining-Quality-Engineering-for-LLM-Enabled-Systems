"""Scenario Authors: draft test cases from source-of-truth docs. Drafts are never evidence (R3).

At least two author slots with distinct model families are required (generator diversity, R5).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import Ledger
from qe.core.schemas import Frozen, TestCase
from qe.crew.llm import LLMClient
from qe.crew.prompt_store import Prompt, load_prompt
from qe.crew.record import record_crew_event

PROMPT_NAME = "scenario_author_v1"
ABSTAIN_ORACLE = "none:expects_abstain"


@dataclass(frozen=True)
class AuthorSlot:
    name: str
    llm: LLMClient


class Draft(Frozen):
    case: TestCase
    expected_span: str | None
    expects_abstain: bool
    author: str
    family: str
    prompt_sha256: str


def check_slots(slots: Sequence[AuthorSlot]) -> None:
    if len({s.name for s in slots}) != len(slots):
        raise ValueError("author slot names must be unique")
    if len({s.llm.family for s in slots}) < 2:
        raise ValueError("at least two author slots with distinct model families are required")


def _to_draft(raw: Any, slot: AuthorSlot, cell: str, prompt: Prompt) -> Draft | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("question"), str):
        return None
    question = raw["question"].strip()
    if not question:
        return None
    abstain = bool(raw.get("expects_abstain", False))
    source = raw.get("source_id")
    span = raw.get("expected_span")
    oracle = ABSTAIN_ORACLE if abstain or not source else f"source_of_truth:{source}"
    case_id = content_id({"q": question, "cell": cell, "oracle": oracle})
    case = TestCase(
        id=case_id, risk_cell=cell, input={"input": question}, oracle_source=oracle,
        lineage=(f"author:{slot.name}", f"family:{slot.llm.family}", f"prompt:{prompt.sha256[:12]}"),
    )
    return Draft(case=case, expected_span=span if isinstance(span, str) else None,
                 expects_abstain=abstain, author=slot.name, family=slot.llm.family,
                 prompt_sha256=prompt.sha256)


def author_scenarios(
    slots: Sequence[AuthorSlot],
    risk_cell: str,
    docs: Mapping[str, str],
    n_per_slot: int,
    ledger: Ledger | None = None,
    prompt: Prompt | None = None,
) -> tuple[Draft, ...]:
    """Each slot drafts `n_per_slot` scenarios; identical questions across slots are merged."""
    check_slots(slots)
    prompt = prompt or load_prompt(PROMPT_NAME)
    drafts: dict[str, Draft] = {}
    for slot in slots:
        user = json.dumps(
            {"risk_cell": risk_cell, "docs": dict(docs), "n": n_per_slot, "slot": slot.name},
            sort_keys=True,
        )
        raw = slot.llm.complete(
            [{"role": "system", "content": prompt.text}, {"role": "user", "content": user}]
        )
        try:
            items = json.loads(raw).get("scenarios", [])
        except (json.JSONDecodeError, AttributeError):
            items = []
        for item in items if isinstance(items, list) else []:
            draft = _to_draft(item, slot, risk_cell, prompt)
            if draft is not None:
                drafts.setdefault(draft.case.id, draft)
    ordered = tuple(drafts[k] for k in sorted(drafts))
    if ledger is not None:
        for d in ordered:
            body = {
                "test_case": d.case.model_dump(mode="json"),
                "expected_span": d.expected_span,
                "expects_abstain": d.expects_abstain,
                "author": d.author,
            }
            llm = next(s.llm for s in slots if s.name == d.author)
            record_crew_event(ledger, EventType.TEST_DRAFTED, f"author:{d.author}", body,
                              prompt=prompt, llm=llm)
    return ordered
