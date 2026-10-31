"""Boundary/edge tests that pin policy-engine and deterministic-verifier semantics."""

from __future__ import annotations

from qe.core.schemas import ClaimState, DecisionState, Policy
from qe.policy.engine import MetricEvidence, decide
from qe.verify import deterministic as d

S, C, U = ClaimState.SUPPORTED, ClaimState.CONTRADICTED, ClaimState.UNSUPPORTED


def pol(example: bool = False) -> Policy:
    return Policy(policy_id="p", version="7", loss_matrix={}, required_evidence=("a", "b"),
                  risk_appetite={"a": 0.1, "b": 0.2}, example_only=example)


def ev(name: str, lo: float, hi: float, ids: tuple[str, ...] = ("e1",)) -> MetricEvidence:
    return MetricEvidence(name=name, failures=0, trials=10, lower=lo, upper=hi, evidence_ids=ids)


# ---------- policy ----------


def test_upper_equal_to_appetite_is_acceptable() -> None:
    r = decide(pol(), [ev("a", 0.0, 0.1), ev("b", 0.0, 0.2)])
    assert r.decision is DecisionState.RELEASE and r.conditions == ()


def test_lower_equal_to_appetite_is_not_violated_but_undetermined() -> None:
    r = decide(pol(), [ev("a", 0.1, 0.3), ev("b", 0.0, 0.2)])
    assert r.decision is DecisionState.INSUFFICIENT_EVIDENCE


def test_reject_beats_insufficient_and_notes_name_the_metric() -> None:
    r = decide(pol(), [ev("a", 0.5, 0.9)])  # a violated, b missing
    assert r.decision is DecisionState.REJECT
    text = " | ".join(r.conditions)
    assert "a: lower bound 0.5000 > appetite 0.1" in text and "missing evidence: b" in text


def test_straddle_note_shows_interval_and_appetite() -> None:
    r = decide(pol(), [ev("a", 0.05, 0.25), ev("b", 0.0, 0.1)])
    assert r.conditions == ("a: interval [0.0500, 0.2500] straddles appetite 0.1",)


def test_evidence_ids_sorted_unique_and_policy_version_recorded() -> None:
    r = decide(pol(), [ev("a", 0, 0.1, ("z", "m")), ev("b", 0, 0.2, ("m", "c"))])
    assert r.evidence_ids == ("c", "m", "z") and r.policy_version == "p@7"


def test_example_label_only_for_example_policies() -> None:
    assert decide(pol(False), [ev("a", 0, 0.1), ev("b", 0, 0.1)]).conditions == ()
    assert decide(pol(True), [ev("a", 0, 0.1), ev("b", 0, 0.1)]).conditions[0].startswith("EXAMPLE")


def test_extra_unrequired_metric_is_ignored_for_decision() -> None:
    r = decide(pol(), [ev("a", 0, 0.1), ev("b", 0, 0.1), ev("zzz", 0.9, 1.0)])
    assert r.decision is DecisionState.RELEASE


# ---------- verifiers ----------


def test_citation_states_and_sorted_missing_detail() -> None:
    assert d.citation_exists("c", ["x"], None).state is ClaimState.SOURCE_UNAVAILABLE
    assert d.citation_exists("c", [], {"x": ""}).state is ClaimState.UNVERIFIABLE
    assert d.citation_exists("c", ["x"], {"x": ""}).state is S
    v = d.citation_exists("c", ["q", "b", "x"], {"x": ""})
    assert v.state is C and v.detail == "not in corpus: b, q" and v.claim_id == "c"


def test_quote_in_source() -> None:
    corpus = {"s": "the quick brown fox"}
    assert d.quote_in_source("c", "quick brown", "s", corpus).state is S
    assert d.quote_in_source("c", "slow", "s", corpus).state is U
    assert d.quote_in_source("c", "x", "missing", corpus).state is ClaimState.SOURCE_UNAVAILABLE
    assert d.quote_in_source("c", "x", "s", None).state is ClaimState.SOURCE_UNAVAILABLE


def test_numbers_equal_semantics() -> None:
    assert d.numbers_equal("c", "no digits", "1 2").state is ClaimState.UNVERIFIABLE
    assert d.numbers_equal("c", "revenue 1,234.5", "rev was 1234.5 total").state is S
    assert d.numbers_equal("c", "it is -3", "value -3").state is S
    assert d.numbers_equal("c", "it is -3", "value 3").state is C
    v = d.numbers_equal("c", "12 and 99", "12 only")
    assert v.state is C and v.detail is not None and "99" in v.detail
    assert d.numbers_equal("c", "7", "7 8 9").detail is None


def test_entities_equal_casefold_and_diff_detail() -> None:
    assert d.entities_equal("c", ["Alice", "BOB"], ["alice", "bob"]).state is S
    v = d.entities_equal("c", ["alice", "eve"], ["alice", "bob"])
    assert v.state is C and v.detail == "diff: ['bob', 'eve']"
    assert d.entities_equal("c", ["a"], ["a", "b"]).state is C  # subset is not equal


def test_schema_valid_paths_and_types() -> None:
    schema = {"type": "object", "required": ["id", "tags"],
              "properties": {"id": {"type": "integer"},
                             "tags": {"type": "array", "items": {"type": "string"}}}}
    assert d.schema_valid("c", {"id": 1, "tags": ["a"]}, schema).state is S
    assert d.schema_valid("c", {"id": 1, "tags": ["a"]}, schema).detail is None
    v = d.schema_valid("c", {"tags": ["a", 2]}, schema)
    assert v.state is C and v.detail == "$.id: required; $.tags[1]: expected string"
    assert d.schema_valid("c", {"id": True, "tags": []}, schema).state is C  # bool is not integer
    assert d.schema_valid("c", 1.5, {"type": "number"}).state is S
    assert d.schema_valid("c", True, {"type": "number"}).state is C
    assert d.schema_valid("c", "x", {"type": "integer"}).detail == "$: expected integer"
    assert d.schema_valid("c", 5, {}).state is S  # no constraints


def test_forbidden_tool_call_allow_deny() -> None:
    calls = [{"name": "search"}, {"name": "delete"}, {"name": "delete"}]
    assert d.forbidden_tool_call("c", calls, denylist=["delete"]).detail == "forbidden calls: delete"
    assert d.forbidden_tool_call("c", calls, allowlist=["search"]).state is C
    assert d.forbidden_tool_call("c", calls, allowlist=["search", "delete"]).state is S
    assert d.forbidden_tool_call("c", calls[:1], allowlist=["search"]).detail is None
    # denial wins even when the tool is also allowlisted
    assert d.forbidden_tool_call("c", calls, allowlist=["search", "delete"], denylist=["delete"]).state is C
    assert d.forbidden_tool_call("c", [], allowlist=[]).state is S
    assert d.forbidden_tool_call("c", [{"name": "x"}]).state is S  # no lists -> nothing forbidden


def test_canary_exfiltration_sink_values_output_and_clean() -> None:
    tok = "CANARY-123"
    clean = d.canary_exfiltration("c", tok, [{"to": "a", "body": "hi"}], "ok")
    assert clean.state is S and clean.detail is None
    in_sink = d.canary_exfiltration("c", tok, [{"to": "a", "body": f"x {tok} y"}])
    assert in_sink.state is C and in_sink.detail == "canary observed outside boundary"
    assert d.canary_exfiltration("c", tok, [], f"leak {tok}").state is C
    assert d.canary_exfiltration("c", tok, []).state is S
    assert in_sink.method_class.value == "outcome_oracle" and in_sink.method == "canary_exfiltration"
