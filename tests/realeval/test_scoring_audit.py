"""Audit regressions for deterministic scoring (items 1-3): ids are not passages, nothing checked
is not a pass, lexical normalisation, negation guard, refusal detection."""

from __future__ import annotations

import pytest

from qe.realeval.dataset import EvalItem
from qe.realeval.scoring import (
    contexts_kind,
    correctness,
    faithfulness,
    is_refusal,
    retrieval_hit,
    score_item,
)

DOCS = ["leave_policy.md", "pricing.pdf"]


def item(**kw: object) -> EvalItem:
    base: dict[str, object] = {"id": "i1", "question": "q?", "source": "user"}
    return EvalItem.model_validate({**base, **kw})


# ---- item 1: contexts that are ids are not passage text
@pytest.mark.parametrize("ctxs", [["doc-12", "doc-7"], ["leave_policy.md"],
                                  ["3f2b8c1e-aaaa-4bbb-9ccc-123456789abc"], ["chunk_44#2"]])
def test_id_like_contexts_are_not_text(ctxs: list[str]) -> None:
    assert contexts_kind(ctxs) == "ids"
    assert faithfulness("Employees get 20 days of leave.", ctxs) is None


def test_real_passages_are_text_and_empty_is_none() -> None:
    assert contexts_kind(["Employees receive twenty days of paid leave each year."]) == "text"
    assert contexts_kind([]) == "none"


def test_id_contexts_never_gate_or_set_retrieval_hit() -> None:
    it = item(reference_answer="20 days")
    out = score_item(it, "Employees get 20 days.", ["doc-12"], None, DOCS)
    assert out["scores"]["faithful"] is None and out["scores"]["retrieval_hit"] is None
    assert out["passed"] is True  # correct=True is the only measured check
    assert retrieval_hit(it, ["doc-12"]) is None


def test_cited_ids_resolve_against_uploaded_documents() -> None:
    it = item(reference_answer="20 days")
    ok = score_item(it, "20 days", ["leave_policy.md"], None, DOCS)
    assert ok["scores"]["citation_valid"] is True
    nope = score_item(it, "20 days [leave_polcy.txt]", ["x"], None, DOCS)
    assert nope["scores"]["citation_valid"] is False
    unresolvable = score_item(it, "20 days", ["kb-991"], None, DOCS)
    assert unresolvable["scores"]["citation_valid"] is None


def test_retrieval_hit_from_resolved_source_doc() -> None:
    it = item(reference_answer="20 days", evidence="20 days", source_doc="leave_policy.md")
    assert retrieval_hit(it, ["leave_policy.md"], DOCS) is True
    assert retrieval_hit(it, ["pricing.pdf"], DOCS) is False


# ---- item 2: unchecked is not a pass
def test_no_reference_and_unset_answerable_is_unchecked_not_passed() -> None:
    it = item(answerable=None)
    out = score_item(it, "Anything at all.", [], None, DOCS)
    assert out["passed"] is None
    assert out["failure_reason"] is None


def test_unanswerable_flag_makes_refusal_the_check() -> None:
    it = item(answerable=False)
    assert score_item(it, "I don't know.", [], None, DOCS)["passed"] is True
    assert score_item(it, "It is 42.", [], None, DOCS)["passed"] is False


# ---- item 3: lexical normalisation
@pytest.mark.parametrize("ref,ans", [
    ("7 days", "The ticket remains valid for one week."),
    ("7 days", "It is valid for 168 hours."),
    ("7 days", "valid for seven days"),
    ("12 months", "warranty is twelve months"),
    ("5%", "The fee is 5.0% of the amount."),
    ("5%", "the fee is five percent"),
    ("2015-03", "It was founded in March 2015."),
    ("2015-03-01", "Effective March 1, 2015."),
    ("2 weeks", "within 14 days"),
])
def test_normalised_equivalents_are_correct(ref: str, ans: str) -> None:
    assert correctness(ref, ans), (ref, ans)


@pytest.mark.parametrize("ref,ans", [
    ("7 days", "Not 7 days, it is 30 days."),
    ("7 days", "It is 30 days, not 7 days."),
    ("7 days", "The window is 30 days."),
    ("12 months", "warranty is 24 months"),
    ("5%", "The fee is 15%."),
    ("Paris", "The capital is not Paris."),
    ("2015-03", "founded in March 2016"),
])
def test_negation_and_contradiction_are_wrong(ref: str, ans: str) -> None:
    assert not correctness(ref, ans), (ref, ans)


def test_negation_inside_the_reference_is_allowed() -> None:
    assert correctness("Refunds are not available after 30 days",
                       "Refunds are not available after 30 days.")


@pytest.mark.parametrize("text", [
    "Sorry, I can't help with that", "the document doesn't mention it",
    "I'm unable to answer that.", "I cannot assist with this request.",
    "That is not covered in the provided materials.", "There is no information about that.",
    "The context does not specify this.", "I don't have enough information.",
])
def test_refusals_detected(text: str) -> None:
    assert is_refusal(text), text


@pytest.mark.parametrize("text", ["The refund window is 30 days.", "Yes, it is covered.",
                                  "Employees get 20 days of leave."])
def test_non_refusals(text: str) -> None:
    assert not is_refusal(text)


def test_weak_hedges_refuse_only_with_no_contexts_and_no_citation() -> None:
    assert not is_refusal("I'm not sure.", contexts=["Some retrieved passage of real text here."])
    assert is_refusal("I'm not sure.", contexts=[])
    assert not is_refusal("I'm not sure. [1]", contexts=[])
