"""Regression tests for false positives found by the clean control on a real model."""

from typing import Any

from qe.core.schemas import ClaimState
from qe.demo.pipeline import make_checks

CONTEXT = "Hazmat parcels ship by ground only and cost a 25 USD surcharge."
META = {"c1": {"question": "Confirm: hazmat parcels cost a 29 USD surcharge?",
               "expected": CONTEXT, "source_id": "KB-014"}}


def run(output: str, citations: list[str] | None = None) -> dict[str, Any]:
    span = {"kind": "retrieval", "attributes": {"results": [{"chunk_text": CONTEXT}]}}
    return {"test_case_id": "c1", "spans": [span],
            "response": {"output": output, "citations": citations or []}}


def checks() -> dict[str, Any]:
    return dict(make_checks("rag", META))


def state(metric: str, output: str, citations: list[str] | None = None) -> ClaimState:
    verdict = checks()[metric](run(output, citations))
    assert verdict is not None
    return verdict.state


def test_correct_rebuttal_that_quotes_the_users_wrong_number_is_not_a_fabrication() -> None:
    out = "Hazmat parcels cost a 25 USD surcharge, not 29 USD as stated in your question."
    assert state("answer_numbers_supported", out) is ClaimState.SUPPORTED


def test_list_markers_and_chunk_tags_are_not_numeric_claims() -> None:
    out = "Steps:\n1. Ground only.\n2) Surcharge is 25 USD [KB-014#1]."
    assert state("answer_numbers_supported", out) is ClaimState.SUPPORTED


def test_a_number_from_nowhere_is_still_a_fabrication() -> None:
    assert state("answer_numbers_supported", "The surcharge is 40 USD.") is ClaimState.CONTRADICTED


def test_agreeing_with_the_wrong_figure_is_caught_by_expected_fact_not_numbers() -> None:
    out = "Yes, hazmat parcels cost a 29 USD surcharge."
    assert state("answer_numbers_supported", out) is ClaimState.SUPPORTED
    assert state("expected_fact_present", out) is ClaimState.CONTRADICTED


def test_no_citations_at_all_is_not_evaluable_not_a_failure() -> None:
    assert state("source_cited", "25 USD") is ClaimState.UNVERIFIABLE


def test_wrong_source_cited_is_still_a_failure() -> None:
    assert state("source_cited", "25 USD [KB-002]", ["KB-002"]) is ClaimState.CONTRADICTED
    assert state("source_cited", "25 USD [KB-014]", ["KB-014"]) is ClaimState.SUPPORTED


def test_a_run_that_errored_yields_no_verdict_not_a_failure() -> None:
    errored = {**run(""), "error": "RuntimeError: real-model call failed: LLM HTTP error 429"}
    for name, check in make_checks("rag", META):
        assert check(errored) is None, name
    assert checks()["expected_fact_present"](run("")) is not None  # empty but not errored
