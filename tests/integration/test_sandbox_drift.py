"""Second drift defect on each non-chatbot app (RAG-009, MA-005, TOOL-007).

Ground truth is checked here with plain string checks, independent of any `qe` verifier.
"""

from __future__ import annotations

from typing import Any

import pytest

from sandbox_apps.multiagent import build_app as build_ma
from sandbox_apps.rag import build_app as build_rag
from sandbox_apps.toolagent import build_app as build_tool

RAG_Q = {"input": "What is the maximum weight per parcel?"}
MA_Q = {"input": "Brief me on solar panels", "session_id": "s1", "user": "u1"}
TOOL_Q = {"input": "email bob about the offsite", "user": "alice", "session_id": "s1"}


def _out(app: Any, req: dict[str, str]) -> str:
    return str(app.invoke(req)["output"])


def test_rag_009_drift_changes_weight_limit_and_hash_without_version_bump() -> None:
    before, after = build_rag("seeded", drift=False), build_rag("seeded", drift=True)
    assert "30 kg" in _out(before, RAG_Q)
    assert "25 kg" in _out(after, RAG_Q)
    assert after.invoke(RAG_Q)["meta"]["prompt_version"] == "v2"
    doc_b, doc_a = before._docs["KB-003"], after._docs["KB-003"]  # noqa: SLF001
    assert doc_a["version"] == doc_b["version"] and doc_a["hash"] != doc_b["hash"]


def test_ma_005_drift_shortens_plan() -> None:
    before = build_ma("seeded", drift=False).invoke(MA_Q)
    after = build_ma("seeded", drift=True).invoke(MA_Q)
    assert len(after["citations"]) == len(before["citations"]) - 1
    assert after["meta"]["model"] != before["meta"]["model"]


def test_tool_007_drift_reroutes_bare_name_recipient() -> None:
    before, after = build_tool("seeded", drift=False), build_tool("seeded", drift=True)
    before.invoke(TOOL_Q)
    after.invoke(TOOL_Q)
    assert before.sinks()[0]["to"] == "bob@fiction.example"
    assert after.sinks()[0]["to"] == "bob@corp.fiction.example"


@pytest.mark.parametrize(
    ("build", "req"), [(build_rag, RAG_Q), (build_ma, MA_Q), (build_tool, TOOL_Q)]
)
def test_clean_variant_behaviour_is_identical_across_drift_switch(build: Any, req: Any) -> None:
    a, b = build("clean", drift=False), build("clean", drift=True)
    ra, rb = a.invoke(req), b.invoke(req)
    assert ra["output"] == rb["output"] and ra["citations"] == rb["citations"]
    assert a.sinks() == b.sinks()
    assert rb["meta"]["prompt_version"] == "v2"
