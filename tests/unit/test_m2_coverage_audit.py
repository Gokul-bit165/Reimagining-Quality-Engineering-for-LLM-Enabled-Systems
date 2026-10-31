"""T2.3 audit tool + T2.4 coverage report."""

import json

import pytest
from typer.testing import CliRunner

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import ModelRef, Span, TestCase
from qe.crew.audit import (
    AuditLabel,
    drafted_tests,
    invalid_rate,
    record_labels,
    sample,
    skeptic_precision,
)
from qe.crew.audit_cli import audit_app
from qe.crew.llm import ScriptedLLM
from qe.crew.scenario_author import ScenarioAuthor
from qe.crew.skeptic import Assessment
from qe.model.app_model import build_from_traces
from qe.risk.coverage import build_coverage, record_coverage, render_markdown
from qe.risk.register import RiskProposal
from qe.risk.taxonomy import load_taxonomy

SRC = {"KB-1": "Returns are accepted within 30 days of delivery."}
RISK = RiskProposal(risk_id="R1", taxonomy_id="LLM09", component="llm:planner", rationale="r")
RISK2 = RiskProposal(risk_id="R2", taxonomy_id="LLM01", component="tool:search", rationale="r")


def tc(i: int, risk: str = "R1") -> TestCase:
    return TestCase(id=f"t{i}", risk_cell=risk, input={"question": f"q{i}"}, oracle_source="x")


def sp(kind: str, **a: object) -> Span:
    return Span(span_id="s", kind=kind, attributes=dict(a))


def test_coverage_reports_uncovered_unvalidated_and_unassessed() -> None:
    model = build_from_traces([(sp("llm_call", role="planner"), sp("tool_call", tool="search"))])
    tax = load_taxonomy("owasp_llm_2025")
    rep = build_coverage(tax, [RISK, RISK2], [tc(1), tc(2)], {"t1": "valid", "t2": "invalid"},
                         model, run_traces=[(sp("llm_call", role="planner"),)])
    st = {c.risk_id: c.status for c in rep.cells}
    assert st == {"R1": "COVERED", "R2": "UNCOVERED"}
    c1 = next(c for c in rep.cells if c.risk_id == "R1")
    assert (c1.n_drafted, c1.n_valid) == (2, 1)
    assert "LLM02" in rep.unassessed_taxonomy_ids and "LLM09" not in rep.unassessed_taxonomy_ids
    assert rep.structural.nodes_total == 2 and rep.structural.nodes_exercised == 1
    assert rep.structural.label == "logged_not_validated_H3"
    md = render_markdown(rep)
    assert "UNCOVERED" in md and "R2" in md and "not a claim" in md
    assert md == render_markdown(rep)


def test_drafted_not_validated_status() -> None:
    model = build_from_traces([])
    rep = build_coverage(load_taxonomy("owasp_llm_2025"), [RISK], [tc(1)], {}, model, [])
    assert rep.cells[0].status == "DRAFTED_NOT_VALIDATED"


def test_coverage_recorded_by_deterministic_producer(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = SQLiteLedger(tmp_path / "l.db")
    rep = build_coverage(load_taxonomy("owasp_llm_2025"), [RISK], [], {}, build_from_traces([]), [])
    e = record_coverage(led, rep)
    assert e.event.type is EventType.EVIDENCE_RECORDED
    assert e.event.producer_kind is ProducerKind.DETERMINISTIC
    assert e.event.payload["kind"] == "coverage_report"
    assert record_coverage(led, rep).seq == e.seq


def test_sample_is_seeded_without_replacement_and_blind() -> None:
    items = [tc(i) for i in range(20)]
    a, b = sample(items, 5, seed=1), sample(items, 5, seed=1)
    assert [t.id for t in a] == [t.id for t in b] and len({t.id for t in a}) == 5
    assert [t.id for t in sample(items, 5, seed=2)] != [t.id for t in a]
    assert len(sample(items, 99, seed=1)) == 20


def test_invalid_rate_has_exact_interval() -> None:
    labels = [AuditLabel(test_id=f"t{i}", label="invalid" if i < 3 else "valid") for i in range(20)]
    r = invalid_rate(labels)
    assert (r.k, r.n) == (3, 20) and 0.03 < r.lower < 0.15 < r.upper < 0.40
    with pytest.raises(ValueError):
        invalid_rate([])


def test_invalid_label_values_rejected() -> None:
    with pytest.raises(ValueError):
        AuditLabel(test_id="t", label="maybe")


def test_skeptic_precision_counts_only_labeled_skeptic_valid() -> None:
    labels = [AuditLabel(test_id="a", label="valid"), AuditLabel(test_id="b", label="invalid"),
              AuditLabel(test_id="c", label="valid")]
    ass = {"a": Assessment(test_id="a", status="valid", reason=""),
           "b": Assessment(test_id="b", status="valid", reason=""),
           "c": Assessment(test_id="c", status="invalid", reason="")}
    r = skeptic_precision(labels, ass)
    assert (r.k, r.n) == (1, 2)


async def test_labels_recorded_as_human_signoff_and_tests_read_back(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = SQLiteLedger(tmp_path / "l.db")
    reply = json.dumps([{"question": "q", "expected": "30 days", "source_id": "KB-1",
                         "evidence_quote": "within 30 days"}])
    m = ModelRef(provider="fake", name="a", family="fa")
    await ScenarioAuthor(ScriptedLLM(m, [reply])).author(RISK, 1, SRC, led)
    items = drafted_tests(led)
    assert len(items) == 1 and items[0].source_text == SRC["KB-1"]
    record_labels(led, [AuditLabel(test_id=items[0].test.id, label="valid")], auditor="alice")
    last = list(led.entries())[-1].event
    assert last.type is EventType.SIGNOFF_RECORDED and last.producer_kind is ProducerKind.HUMAN


async def test_cli_sample_then_score(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "l.db"
    led = SQLiteLedger(db)
    reply = json.dumps([{"question": f"q{i}", "expected": "30 days", "source_id": "KB-1",
                         "evidence_quote": "within 30 days"} for i in range(4)])
    m = ModelRef(provider="fake", name="a", family="fa")
    await ScenarioAuthor(ScriptedLLM(m, [reply])).author(RISK, 4, SRC, led)
    led.close()
    runner, sheet = CliRunner(), tmp_path / "sheet.json"
    r = runner.invoke(audit_app, ["sample", str(db), "--n", "3", "--seed", "7", "--out", str(sheet)])
    assert r.exit_code == 0, r.output
    rows = json.loads(sheet.read_text(encoding="utf-8"))
    assert len(rows) == 3 and all(row["label"] == "" for row in rows)
    assert not ({"status", "skeptic"} & set(rows[0]))  # blind to the skeptic verdict
    rows[0]["label"], rows[1]["label"], rows[2]["label"] = "valid", "invalid", "valid"
    sheet.write_text(json.dumps(rows), encoding="utf-8")
    r2 = runner.invoke(audit_app, ["score", str(db), str(sheet), "--auditor", "alice"])
    assert r2.exit_code == 0 and "1/3" in r2.output and "95%" in r2.output
    bad = rows
    bad[0]["label"] = ""
    sheet.write_text(json.dumps(bad), encoding="utf-8")
    assert runner.invoke(audit_app, ["score", str(db), str(sheet), "--auditor", "a"]).exit_code == 2
