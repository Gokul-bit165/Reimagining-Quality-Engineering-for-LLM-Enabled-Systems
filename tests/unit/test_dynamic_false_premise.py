"""False-premise operator derives names from the user's own documents; never invents any."""

from qe.realeval.dataset import EvalItem
from qe.realeval.dynamic import apply_operator, document_entities

BASE = EvalItem(id="b1", question="How much does Widget cost?", reference_answer="5 dollars")
DOCS = [{"name": "kb.md", "text": "Prices are listed below. The Widget is sold by Acme Corp for 5 dollars."}]


def test_entities_come_from_the_documents_only() -> None:
    names = document_entities(DOCS)
    assert "Acme Corp" in names
    assert not {"Zorblax Dynamics", "Quintessa Holdings"} & set(names)


def test_false_premise_uses_a_document_entity_and_is_unanswerable() -> None:
    v = apply_operator("false_premise_unanswerable", BASE, 1, 0, DOCS)
    assert v is not None and v.answerable is False
    assert any(n in v.question for n in document_entities(DOCS))


def test_false_premise_is_dropped_without_documents() -> None:
    assert apply_operator("false_premise_unanswerable", BASE, 1, 0, []) is None
