"""Skeptic (T2.3): independent re-derivation from the source document, never from the author.

The Skeptic sees `SkepticInput` only (question + source text): no expected answer, no author
rationale (R4). Its status is a PROPOSAL; truth about validity comes from the human audit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import Ledger
from qe.core.schemas import TestCase
from qe.crew.llm import CrewLLM
from qe.crew.parse import parse_json_object
from qe.crew.prompts import load_prompt
from qe.crew.recording import record_draft

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_WORD = re.compile(r"[a-z0-9]+")


class SkepticInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question: str
    source_text: str


class Assessment(BaseModel):
    model_config = ConfigDict(frozen=True)
    test_id: str
    status: str  # valid | invalid | ambiguous
    reason: str


def _norm(s: str) -> str:
    return " ".join(_WORD.findall(s.lower()))


def answers_agree(expected: str, derived: str) -> bool:
    """Numbers decide when present (sets must match); otherwise normalised containment."""
    en, dn = set(_NUM.findall(expected)), set(_NUM.findall(derived))
    if en or dn:
        return en == dn
    e, d = _norm(expected), _norm(derived)
    return bool(e) and bool(d) and (e in d or d in e)


def flag_redundant(tests: Sequence[TestCase]) -> dict[str, str]:
    """duplicate id -> id of the first test with the same normalised question and evidence."""
    first: dict[tuple[str, str, str], str] = {}
    out: dict[str, str] = {}
    for t in tests:
        k = (_norm(str(t.input.get("question", ""))), str(t.input.get("source_id", "")),
             str(t.input.get("evidence_quote", "")))
        if k in first:
            out[t.id] = first[k]
        else:
            first[k] = t.id
    return out


class Skeptic:
    def __init__(self, llm: CrewLLM) -> None:
        self.llm = llm

    async def assess(
        self, test: TestCase, source_text: str, author_family: str, ledger: Ledger
    ) -> Assessment:
        if self.llm.model.family == author_family:
            raise ValueError("skeptic must be a different model family than the author (R4)")
        prompt = load_prompt("skeptic")
        inp = SkepticInput(question=str(test.input["question"]), source_text=source_text)
        user = json.dumps(inp.model_dump(), sort_keys=True)
        raw = await self.llm.complete(prompt.text, user)
        try:
            d = parse_json_object(raw)
            answerable, ambiguous = d.get("answerable") is True, d.get("ambiguous") is True
            answer = str(d.get("answer", ""))
        except ValueError:
            status, reason = "invalid", "skeptic output unparseable"
        else:
            if ambiguous:
                status, reason = "ambiguous", "skeptic flagged ambiguity"
            elif not answerable:
                status, reason = "invalid", "source does not answer the question"
            elif not answers_agree(str(test.input["expected"]), answer):
                status, reason = "invalid", "re-derived answer disagrees with expected"
            else:
                status, reason = "valid", "re-derived answer agrees"
        a = Assessment(test_id=test.id, status=status, reason=reason)
        record_draft(ledger, EventType.VALIDITY_VERDICT,
                     f"validity:{content_id([test.id, self.llm.model.family, raw])}",
                     {"test_id": test.id, "status": status, "reason": reason,
                      "author_family": author_family}, prompt, self.llm.model, raw)
        return a
