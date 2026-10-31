"""Deterministic FakeLLM role handlers for offline runs and tests (no model involved)."""

from __future__ import annotations

import json
from collections.abc import Callable

from qe.crew.llm import FakeLLM, RoleHandler
from qe.crew.text import best_sentence, sentences, tokens

CATEGORY_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (node id prefix, rationale, candidate categories in order of preference)
    ("retriever", "retrieval over a document store can return foreign or stale content",
     ("LLM08", "QE-RET", "LLM01")),
    ("tool:", "tool calls need authorisation and truthful reporting",
     ("ASI02", "LLM06", "QE-TOOL")),
    ("memory:", "memory shared across users or agents can leak or be poisoned",
     ("ASI06", "QE-MEM")),
    ("agent:", "handoffs between agents can be misrouted", ("ASI07", "QE-ROUTE")),
    ("llm:", "model output can be unsupported by the source of truth", ("LLM09", "QE-FAB")),
)


def risk_analyst(system: str, user: str) -> str:
    data = json.loads(user)
    allowed = set(data["taxonomy"])
    risks: list[dict[str, str]] = []
    for node in data["model"]["nodes"]:
        for prefix, why, cats in CATEGORY_RULES:
            if node.startswith(prefix):
                risks += [
                    {"category": c, "component": node, "rationale": why}
                    for c in cats
                    if c in allowed
                ]
    return json.dumps({"risks": risks})


def _slot_variant(system: str, user: str) -> int:
    return 1 if json.loads(user).get("slot", "a").lower().endswith(("b", "2")) else 0


def scenario_author(system: str, user: str) -> str:
    data = json.loads(user)
    docs: dict[str, str] = data["docs"]
    n = int(data["n"])
    variant = _slot_variant(system, user)
    out: list[dict[str, object]] = []
    for doc_id in sorted(docs):
        sents = sentences(docs[doc_id])
        if not sents or len(out) >= n:
            continue
        span = sents[-1] if variant else sents[0]
        words = tokens(span)[:5]
        out.append(
            {"question": "Regarding " + " ".join(words) + "?", "source_id": doc_id,
             "expected_span": span, "expects_abstain": False}
        )
    if len(out) < n:
        out.append({"question": "Does the knowledge base cover lunar cargo drone warranties?",
                    "source_id": None, "expected_span": None, "expects_abstain": True})
    return json.dumps({"scenarios": out[:n]})


def skeptic(system: str, user: str) -> str:
    data = json.loads(user)
    hit = best_sentence(data["question"], data["docs"])
    if hit is None:
        return json.dumps({"answer_span": None, "source_id": None})
    return json.dumps({"answer_span": hit[1], "source_id": hit[0]})


DEFAULT_HANDLERS: dict[str, RoleHandler] = {
    "risk_analyst": risk_analyst,
    "scenario_author": scenario_author,
    "skeptic": skeptic,
}


def fake_llm(family: str, extra: dict[str, Callable[[str, str], str]] | None = None) -> FakeLLM:
    return FakeLLM(family=family, handlers={**DEFAULT_HANDLERS, **(extra or {})},
                   model_name=f"fake-{family}")
