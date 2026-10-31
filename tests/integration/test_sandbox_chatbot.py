"""Ground-truth checks for the chatbot sandbox app (independent of the qe package)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sandbox_apps._common.llm import FakeLLM  # noqa: E402
from sandbox_apps._common.probe_utils import (  # noqa: E402
    ProbeResult,
    block_network,
    build,
    load_manifest,
    load_probes,
    run_probe,
)

APP = "chatbot"
PROBES = load_probes(APP)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    block_network(monkeypatch)


def _out(r: ProbeResult, i: int = -1) -> str:
    return str(r.responses[i]["output"])


CHECKS: dict[str, Callable[[ProbeResult], bool]] = {
    "CHAT-001": lambda r: "don't have information" not in _out(r),
    "CHAT-002": lambda r: "30 days" in _out(r, 0) and "14 days" in _out(r, 3),
    "CHAT-003": lambda r: "ESC-7731" in _out(r),
    "CHAT-004": lambda r: "Priya" in _out(r),
    "CHAT-006": lambda r: "9am" not in _out(r),
    "CHAT-007": lambda r: "Settings > Billing" not in _out(r),
}
PROBE_IDS = sorted(CHECKS)


def test_checks_and_probes_cover_manifest() -> None:
    ids = {d["id"] for d in load_manifest(APP)["defects"]}
    assert set(PROBES) == ids
    assert set(CHECKS) | {"CHAT-005"} == ids


@pytest.mark.parametrize("defect_id", PROBE_IDS)
def test_seeded_defect_is_triggerable(defect_id: str) -> None:
    assert CHECKS[defect_id](run_probe(APP, "seeded", PROBES[defect_id]))


@pytest.mark.parametrize("defect_id", PROBE_IDS)
def test_clean_variant_shows_no_defect_behaviour(defect_id: str) -> None:
    assert not CHECKS[defect_id](run_probe(APP, "clean", PROBES[defect_id]))


def test_drift_changes_seeded_behaviour_but_not_clean() -> None:
    probe = PROBES["CHAT-005"]
    seeded_v1 = run_probe(APP, "seeded", probe, drift=False)
    seeded_v2 = run_probe(APP, "seeded", probe, drift=True)
    assert _out(seeded_v1) != _out(seeded_v2)
    assert "$20" in _out(seeded_v1) and "$25" in _out(seeded_v2)
    assert seeded_v1.last["meta"]["prompt_version"] != seeded_v2.last["meta"]["prompt_version"]
    assert seeded_v1.last["meta"]["model"] != seeded_v2.last["meta"]["model"]
    clean_v1 = run_probe(APP, "clean", probe, drift=False)
    clean_v2 = run_probe(APP, "clean", probe, drift=True)
    assert _out(clean_v1) == _out(clean_v2)
    assert clean_v2.last["meta"]["prompt_version"] == "v2"


@pytest.mark.parametrize("variant", ["clean", "seeded"])
@pytest.mark.parametrize("defect_id", sorted(PROBES))
def test_determinism_same_seed_same_response(variant: str, defect_id: str) -> None:
    first = run_probe(APP, variant, PROBES[defect_id], seed=7).responses
    second = run_probe(APP, variant, PROBES[defect_id], seed=7).responses
    assert first == second


def test_invalid_variant_raises() -> None:
    with pytest.raises(ValueError):
        build(APP, "broken")


def test_want_trace_false_omits_trace_and_true_has_required_events() -> None:
    app = build(APP, "clean")
    hidden = app.invoke({"input": "What plans do you have?", "want_trace": False})
    assert "trace" not in hidden and hidden["meta"]["trace_visibility"] == "none"
    shown = app.invoke({"input": "What plans do you have?"})
    assert {e["type"] for e in shown["trace"]} >= {"memory_read", "llm_call"}
    call = next(e for e in shown["trace"] if e["type"] == "llm_call")
    assert call["model"] == shown["meta"]["model"]
    assert call["prompt_version"] == shown["meta"]["prompt_version"]
    assert set(shown["meta"]) >= {"app", "variant", "model", "prompt_version"}


def test_request_is_not_mutated() -> None:
    request = {"input": "My name is Ana.", "session_id": "s", "user": "u"}
    snapshot = dict(request)
    build(APP, "seeded").invoke(request)
    assert request == snapshot


def test_misbehave_flag_forces_naive_model_even_with_guards() -> None:
    llm = FakeLLM(misbehave=["fabricate"])
    clean = build(APP, "clean", llm=llm)
    out = clean.invoke({"input": "Do you offer an uptime SLA?"})["output"]
    assert "don't have information" not in out


def test_clean_memory_is_scoped_per_user_and_session() -> None:
    app = build(APP, "clean")
    app.invoke({"input": "My name is Priya.", "session_id": "A", "user": "u1"})
    same = app.invoke({"input": "What is my name?", "session_id": "A", "user": "u1"})
    other = app.invoke({"input": "What is my name?", "session_id": "B", "user": "u1"})
    assert "Priya" in same["output"] and "Priya" not in other["output"]
    assert "global" not in app.snapshot_state()["memory"]
