"""Ground-truth checks for the multi-agent sandbox app (independent of the qe package)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sandbox_apps._common.probe_utils import (  # noqa: E402
    ProbeResult,
    block_network,
    build,
    load_manifest,
    load_probes,
    run_probe,
)
from sandbox_apps.multiagent import ALLOWED_TRANSITIONS  # noqa: E402

APP = "multiagent"
PROBES = load_probes(APP)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    block_network(monkeypatch)


def _handoffs(r: ProbeResult, i: int = -1) -> list[tuple[str, str]]:
    return [(e["from"], e["to"]) for e in r.responses[i]["trace"] if e["type"] == "handoff"]


def _illegal(r: ProbeResult) -> list[tuple[str, str]]:
    return [p for p in _handoffs(r) if p[1] not in ALLOWED_TRANSITIONS.get(p[0], ())]


def _plan(r: ProbeResult) -> list[str]:
    event = next(e for e in r.last["trace"] if e["type"] == "memory_write" and e["key"] == "plan")
    return list(event["value"])


CHECKS: dict[str, Callable[[ProbeResult], bool]] = {
    "MA-001": lambda r: "92 percent" in r.last["output"],
    "MA-002": lambda r: bool(_illegal(r)) and ("planner", "researcher") not in _handoffs(r),
    "MA-003": lambda r: "risks" in _plan(r) and "N-104" not in r.last["output"],
    "MA-004": lambda r: any(c.startswith("N-2") for c in r.last["citations"]),
}


def test_checks_and_probes_cover_manifest() -> None:
    ids = {d["id"] for d in load_manifest(APP)["defects"]}
    assert set(PROBES) == ids == set(CHECKS) | {"MA-005"}  # drift: test_sandbox_drift.py


@pytest.mark.parametrize("defect_id", sorted(CHECKS))
def test_seeded_defect_is_triggerable(defect_id: str) -> None:
    assert CHECKS[defect_id](run_probe(APP, "seeded", PROBES[defect_id]))


@pytest.mark.parametrize("defect_id", sorted(CHECKS))
def test_clean_variant_shows_no_defect_behaviour(defect_id: str) -> None:
    assert not CHECKS[defect_id](run_probe(APP, "clean", PROBES[defect_id]))


@pytest.mark.parametrize("variant", ["clean", "seeded"])
@pytest.mark.parametrize("defect_id", sorted(PROBES))
def test_determinism_same_seed_same_response(variant: str, defect_id: str) -> None:
    first = run_probe(APP, variant, PROBES[defect_id], seed=5).responses
    second = run_probe(APP, variant, PROBES[defect_id], seed=5).responses
    assert first == second


def test_invalid_variant_raises() -> None:
    with pytest.raises(ValueError):
        build(APP, "x")


@pytest.mark.parametrize(
    "request_text",
    [
        "Brief me on solar panels.",
        "Write a detailed brief on battery recycling.",
        "Write an executive brief on vaccine cold chain.",
        "Brief me on container shipping.",
    ],
)
def test_clean_pipeline_is_complete_cited_and_uses_legal_handoffs(request_text: str) -> None:
    app = build(APP, "clean")
    # run twice in one app: shared memory must not leak between requests in the clean variant
    app.invoke({"input": "Brief me on solar panels."})
    response = app.invoke({"input": request_text})
    result = ProbeResult([response], app)
    assert not _illegal(result)
    assert _handoffs(result) == [
        ("planner", "researcher"),
        ("researcher", "writer"),
        ("writer", "END"),
    ]
    expected = len(_plan(result))
    assert len(response["citations"]) == expected
    assert "92 percent" not in response["output"]


def test_trace_contains_handoffs_tool_calls_and_llm_calls_with_versions() -> None:
    response = build(APP, "clean").invoke({"input": "Brief me on solar panels."})
    types = {e["type"] for e in response["trace"]}
    assert types >= {"handoff", "tool_call", "llm_call", "memory_write", "memory_read"}
    llm_events = [e for e in response["trace"] if e["type"] == "llm_call"]
    assert {e["role"] for e in llm_events} == {"planner", "writer"}
    assert all(e["prompt_version"] == response["meta"]["prompt_version"] for e in llm_events)


def test_unknown_topic_gets_a_safe_answer_without_handoffs() -> None:
    response = build(APP, "clean").invoke({"input": "Brief me on knitting."})
    assert "I can brief on" in response["output"]
    assert not [e for e in response["trace"] if e["type"] == "handoff"]


def test_want_trace_false_omits_trace() -> None:
    response = build(APP, "seeded").invoke(
        {"input": "Brief me on solar panels.", "want_trace": False}
    )
    assert "trace" not in response and response["meta"]["trace_visibility"] == "none"
