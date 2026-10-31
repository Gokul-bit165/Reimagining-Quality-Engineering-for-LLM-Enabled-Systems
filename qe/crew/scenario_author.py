"""Scenario Authors (T2.2). Drafts only: expected answers must be anchored in a source document.

Deterministic gates before a draft is kept: source exists, evidence quote is verbatim in it.
Failing drafts are still recorded (status=rejected) so the invalid-test rate has a denominator.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import Ledger
from qe.core.schemas import TestCase
from qe.crew.llm import CrewLLM
from qe.crew.parse import parse_json_list
from qe.crew.planner import Plan
from qe.crew.prompts import load_prompt
from qe.crew.recording import record_draft
from qe.risk.register import RankedRisk, RiskProposal


class AuthorResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    tests: tuple[TestCase, ...] = ()
    rejected: tuple[tuple[dict[str, Any], str], ...] = ()


def _check(item: dict[str, Any], sources: dict[str, str]) -> str | None:
    for f in ("question", "expected", "source_id", "evidence_quote"):
        if not isinstance(item.get(f), str) or not item[f].strip():
            return f"missing field: {f}"
    if item["source_id"] not in sources:
        return "unknown source_id"
    if item["evidence_quote"] not in sources[item["source_id"]]:
        return "evidence_quote not verbatim in source"
    return None


class ScenarioAuthor:
    def __init__(self, llm: CrewLLM) -> None:
        self.llm = llm

    @property
    def family(self) -> str:
        return self.llm.model.family

    async def author(
        self, risk: RiskProposal, n: int, sources: dict[str, str], ledger: Ledger
    ) -> AuthorResult:
        prompt = load_prompt("scenario_author")
        user = json.dumps({"risk": risk.model_dump(), "n": n, "sources": sources}, sort_keys=True)
        raw = await self.llm.complete(prompt.text, user)
        try:
            items = parse_json_list(raw)[:n]
        except ValueError as exc:
            record_draft(ledger, EventType.NARRATIVE_DRAFTED,
                         f"author-parse:{content_id([risk.risk_id, self.family, user])}",
                         {"status": "unparseable", "error": str(exc)}, prompt,
                         self.llm.model, raw)
            return AuthorResult()
        tests: list[TestCase] = []
        rejected: list[tuple[dict[str, Any], str]] = []
        for item in items:
            reason = _check(item, sources)
            tid = content_id([risk.risk_id, self.family, item])
            payload: dict[str, Any] = {"status": "rejected" if reason else "drafted", "item": item}
            if reason:
                payload["reason"] = reason
                rejected.append((item, reason))
            else:
                tc = TestCase(
                    id=tid,
                    risk_cell=risk.risk_id,
                    input={k: item[k] for k in ("question", "expected", "source_id",
                                                "evidence_quote")},
                    oracle_source=f"source_of_truth:{item['source_id']}",
                    lineage=(f"risk:{risk.risk_id}", f"prompt:{prompt.sha256[:12]}",
                             f"family:{self.family}"),
                )
                tests.append(tc)
                payload["test"] = tc.model_dump(mode="json")
                payload["source_text"] = sources[item["source_id"]]
            record_draft(ledger, EventType.TEST_DRAFTED, f"draft:{tid}", payload, prompt,
                         self.llm.model, raw)
        return AuthorResult(tests=tuple(tests), rejected=tuple(rejected))


async def author_suite(
    authors: Sequence[ScenarioAuthor],
    pl: Plan,
    ranked: Sequence[RankedRisk],
    sources: dict[str, str],
    ledger: Ledger,
) -> AuthorResult:
    if len({a.family for a in authors}) < 2:
        raise ValueError("need authors from at least 2 distinct model families")
    by_id = {r.proposal.risk_id: r.proposal for r in ranked}
    tests: list[TestCase] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    m = len(authors)
    for idx, (risk_id, n) in enumerate(pl.allocation):
        for k in range(m):  # rotate the odd remainder so families share work across risks
            a = authors[(k + idx) % m]
            share = n // m + (1 if k < n % m else 0)
            if share:
                res = await a.author(by_id[risk_id], share, sources, ledger)
                tests.extend(res.tests)
                rejected.extend(res.rejected)
    return AuthorResult(tests=tuple(tests), rejected=tuple(rejected))
