from qe.core.schemas import ClaimState
from qe.verify.deterministic import (
    canary_exfiltration,
    citation_exists,
    entities_equal,
    forbidden_tool_call,
    numbers_equal,
    quote_in_source,
    schema_valid,
)

CORPUS = {"D-1": "Refunds are issued within 14 days.", "D-2": "Offices open at 9am."}


def test_citation_exists() -> None:
    assert citation_exists("c", ["D-1"], CORPUS).state is ClaimState.SUPPORTED
    v = citation_exists("c", ["D-1", "D-99"], CORPUS)
    assert v.state is ClaimState.CONTRADICTED and "D-99" in (v.detail or "")
    assert citation_exists("c", [], CORPUS).state is ClaimState.UNVERIFIABLE
    assert citation_exists("c", ["D-1"], None).state is ClaimState.SOURCE_UNAVAILABLE


def test_quote_in_source() -> None:
    assert quote_in_source("c", "within 14 days", "D-1", CORPUS).state is ClaimState.SUPPORTED
    assert quote_in_source("c", "within 30 days", "D-1", CORPUS).state is ClaimState.UNSUPPORTED
    assert quote_in_source("c", "x", "D-9", CORPUS).state is ClaimState.SOURCE_UNAVAILABLE


def test_numbers_equal() -> None:
    assert numbers_equal("c", "Refund in 14 days", "issued within 14 days").state is ClaimState.SUPPORTED
    assert numbers_equal("c", "Refund in 30 days", "issued within 14 days").state is ClaimState.CONTRADICTED
    assert numbers_equal("c", "no digits", "none either").state is ClaimState.UNVERIFIABLE
    assert numbers_equal("c", "1,000 units", "1000 units").state is ClaimState.SUPPORTED


def test_entities_equal() -> None:
    assert entities_equal("c", {"Dana", "Paris"}, {"dana", "paris"}).state is ClaimState.SUPPORTED
    assert entities_equal("c", {"Dana"}, {"Dana", "Bob"}).state is ClaimState.CONTRADICTED


def test_schema_valid() -> None:
    schema = {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}}
    assert schema_valid("c", {"id": 3}, schema).state is ClaimState.SUPPORTED
    assert schema_valid("c", {"id": "x"}, schema).state is ClaimState.CONTRADICTED
    assert schema_valid("c", {}, schema).state is ClaimState.CONTRADICTED


def test_forbidden_tool_call_denial_wins() -> None:
    calls = [{"name": "read_note", "args": {}}, {"name": "delete_record", "args": {}}]
    assert forbidden_tool_call("c", calls, denylist={"delete_record"}).state is ClaimState.CONTRADICTED
    assert forbidden_tool_call("c", calls, allowlist={"read_note"}).state is ClaimState.CONTRADICTED
    assert forbidden_tool_call("c", calls[:1], allowlist={"read_note"}).state is ClaimState.SUPPORTED
    assert forbidden_tool_call("c", calls, allowlist={"read_note", "delete_record"},
                               denylist={"delete_record"}).state is ClaimState.CONTRADICTED


def test_canary_exfiltration() -> None:
    sinks = [{"sink": "email", "body": "hi CANARY-abc123 bye"}]
    assert canary_exfiltration("c", "CANARY-abc123", sinks, output="ok").state is ClaimState.CONTRADICTED
    assert canary_exfiltration("c", "CANARY-abc123", [], output="leak CANARY-abc123").state is ClaimState.CONTRADICTED
    assert canary_exfiltration("c", "CANARY-abc123", [{"body": "clean"}], output="ok").state is ClaimState.SUPPORTED
