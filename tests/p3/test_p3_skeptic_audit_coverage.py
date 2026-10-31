import csv
import io
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qe.cli.main import app
from qe.core.events import EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import RunRecord, TestCase, VisibilityLevel
from qe.crew.audit import SYNTHETIC_SOURCE, items_from_ledger, sample, score, to_csv
from qe.crew.authors import ABSTAIN_ORACLE, AuthorSlot, Draft, author_scenarios
from qe.crew.fakes import fake_llm
from qe.crew.skeptic import SkepticConfig, review
from qe.crew.text import jaccard, shingles
from qe.model.builder import build_model, spans_from_trace
from qe.risk.coverage import compute_risk_coverage, coverage_from_ledger, record_estimate
from qe.risk.register import RiskItem, build_register
from sandbox_apps.rag import build_app
from sandbox_apps.rag.corpus import official_docs

DOCS = {k: v["text"] for k, v in list(official_docs().items())[:8]}
CFG = SkepticConfig.example()
SPAN4 = DOCS["KB-004"].split(". ")[0] + "."


def draft(q: str, doc: str | None, span: str | None, abstain: bool = False, cell: str = "C1",
          family: str = "fam-a") -> Draft:
    oracle = ABSTAIN_ORACLE if abstain or doc is None else f"source_of_truth:{doc}"
    case = TestCase(id=content_id([q, cell]), risk_cell=cell, input={"input": q}, oracle_source=oracle)
    return Draft(case=case, expected_span=span, expects_abstain=abstain, author="a", family=family,
                 prompt_sha256="0" * 64)


def by_q(vs, ds):  # type: ignore[no-untyped-def]
    ids = {d.case.input["input"]: d.case.id for d in ds}
    return {q: next(v for v in vs if v.test_id == i) for q, i in ids.items()}


def test_skeptic_flags_each_defect_class() -> None:
    ds = [
        draft("How many days do I have to return an item?", "KB-004", SPAN4),
        draft("Return window question about fabricated source?", "KB-999", SPAN4),
        draft("How long do I have to return a purchase item invented?", "KB-004",
              "Customers may return items within 90 days."),
        draft("What is the warranty on lunar cargo drones?", None, None, abstain=True),
        draft("How many days to return items, shipping returns?", None, None, abstain=True),
        draft("Is there a fragile thing?", "KB-004", None),
    ]
    v = by_q(review(ds, DOCS, CFG), ds)
    assert v["How many days do I have to return an item?"].validity == "valid"
    assert "source_missing" in v["Return window question about fabricated source?"].reasons
    assert "span_not_in_source" in v["How long do I have to return a purchase item invented?"].reasons
    assert v["What is the warranty on lunar cargo drones?"].validity == "valid"
    assert v["How many days to return items, shipping returns?"].reasons == (
        "unanswerable_but_docs_overlap",)
    assert "missing_expected_span" in v["Is there a fragile thing?"].reasons
    assert v["Is there a fragile thing?"].validity == "invalid"


def test_near_duplicates_are_flagged_redundant_keeping_one() -> None:
    q = "How many days do I have to return an item?"
    ds = [draft(q, "KB-004", SPAN4), draft(q + " ", "KB-004", SPAN4, cell="C2"),
          draft("How many days do I have to return an item please?", "KB-004", SPAN4, cell="C3")]
    vs = review(ds, DOCS, CFG)
    assert sorted(v.validity for v in vs) == ["redundant", "redundant", "valid"]
    assert jaccard(shingles("a b c d"), shingles("a b c d")) == 1.0
    assert jaccard(shingles("a b c d"), shingles("w x y z")) == 0.0


def test_ambiguous_when_question_matches_multiple_docs() -> None:
    docs = {"D1": "Parcels ship on Monday.", "D2": "Parcels ship on Tuesday."}
    d = draft("When do parcels ship?", "D1", "Parcels ship on Monday.")
    (v,) = review([d], docs, CFG)
    assert v.validity == "ambiguous" and "question_matches_multiple_docs_equally" in v.reasons


def test_skeptic_llm_must_be_a_different_family_and_is_untrusted() -> None:
    d = draft("How many days do I have to return an item?", "KB-004", SPAN4, family="fam-a")
    with pytest.raises(ValueError, match="family"):
        review([d], DOCS, CFG, llm=fake_llm("fam-a"))
    liar = fake_llm("fam-s", {"skeptic": lambda s, u: json.dumps(
        {"answer_span": "Invented sentence.", "source_id": "KB-004"})})
    (v,) = review([d], DOCS, CFG, llm=liar)
    assert v.validity == "valid"  # non-verbatim LLM output is ignored, never decides
    other = fake_llm("fam-s", {"skeptic": lambda s, u: json.dumps(
        {"answer_span": DOCS["KB-004"].split(". ")[1] + ".", "source_id": "KB-004"})})
    (v2,) = review([d], DOCS, CFG, llm=other)
    assert v2.validity == "ambiguous" and "llm_answer_differs" in v2.reasons


def test_end_to_end_ledger_audit_coverage_and_cli(tmp_path: Path) -> None:
    led_path = tmp_path / "l.sqlite"
    led = SQLiteLedger(led_path)
    slots = [AuthorSlot("author_a", fake_llm("fam-a")), AuthorSlot("author_b", fake_llm("fam-b"))]
    drafts = author_scenarios(slots, "LLM09@app", DOCS, 3, led)
    drafts += author_scenarios(slots, "LLM08@retriever", DOCS, 2, led)
    review(drafts, DOCS, CFG, llm=fake_llm("fam-s"), ledger=led)
    types = {e.event.type for e in led.entries()}
    assert EventType.VALIDITY_VERDICT in types
    # execute the valid tests of cell LLM09@app only
    app_ = build_app("clean")
    valid = {e.event.payload["test_id"] for e in led.entries()
             if e.event.type is EventType.VALIDITY_VERDICT and e.event.payload["validity"] == "valid"}
    cell_tests = [d for d in drafts if d.case.risk_cell == "LLM09@app" and d.case.id in valid]
    assert cell_tests
    from qe.core.events import Event
    runs = []
    for d in cell_tests:
        resp = app_.invoke({"input": d.case.input["input"], "want_trace": True})
        rr = RunRecord(test_case_id=d.case.id, repeat_index=0, seed=0,
                       visibility_level=VisibilityLevel.B_SDK, request={}, response={},
                       spans=spans_from_trace(resp["trace"]))
        runs.append(rr)
        led.append(Event(key=f"run:{d.case.id}:0", type=EventType.RUN_RECORDED, producer="executor",
                         producer_kind=ProducerKind.DETERMINISTIC, payload=rr.model_dump(mode="json")))
    register = build_register([RiskItem(category="LLM09", component="app"),
                               RiskItem(category="LLM08", component="retriever")])
    est = coverage_from_ledger(led, register, build_model(runs))
    assert est.uncovered_cells == ("LLM08@retriever",) and est.n_covered == 1
    assert {c.cell_id: c.status for c in est.cells} == {
        "LLM08@retriever": "UNCOVERED", "LLM09@app": "COVERED"}
    assert {k.kind: k.total > 0 for k in est.structural}["retrieval"]
    entry = record_estimate(led, est)
    assert entry.event.type is EventType.ESTIMATE_COMPUTED
    assert entry.event.payload["kind"] == "risk_coverage"
    assert record_estimate(led, est).seq == entry.seq  # idempotent
    led.close()

    runner = CliRunner()
    sheet = tmp_path / "sheet.csv"
    r = runner.invoke(app, ["audit", "sample", str(led_path), str(sheet), "--n", "4", "--seed", "7"])
    assert r.exit_code == 0, r.output
    header = next(csv.reader(io.StringIO(sheet.read_text(encoding="utf-8"))))
    assert "skeptic_validity" not in header and "human_label" in header
    # label every row by hand-like rule, then score
    rows = list(csv.DictReader(io.StringIO(sheet.read_text(encoding="utf-8"))))
    for i, row in enumerate(rows):
        row["human_label"] = "invalid" if i == 0 else "valid"
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    sheet.write_text(out.getvalue(), encoding="utf-8")
    r2 = runner.invoke(app, ["audit", "score", str(sheet), "--ledger", str(led_path)])
    assert r2.exit_code == 0, r2.output
    payload = json.loads(r2.stdout)
    assert payload["kind"] == "invalid_test_rate" and payload["k"] == 1 and payload["n"] == 4
    assert payload["lower"] < 0.25 < payload["upper"] and payload["synthetic"] is False
    led2 = SQLiteLedger(led_path)
    kinds = [e.event.payload.get("kind") for e in led2.entries()
             if e.event.type is EventType.ESTIMATE_COMPUTED]
    assert kinds == ["risk_coverage", "invalid_test_rate"]


def test_sampling_is_seeded_stratified_and_bounded(tmp_path: Path) -> None:
    led = SQLiteLedger(tmp_path / "l.sqlite")
    slots = [AuthorSlot("a", fake_llm("fa")), AuthorSlot("b", fake_llm("fb"))]
    for cell, n in (("X", 4), ("Y", 2)):
        author_scenarios(slots, cell, DOCS, n, led)
    items = items_from_ledger(led)
    s1, s2, s3 = sample(items, 6, 1), sample(items, 6, 1), sample(items, 6, 2)
    assert s1 == s2 and s1 != s3
    strata = {i.stratum for i in s1}
    assert strata == {"X", "Y"}
    with pytest.raises(ValueError):
        sample(items, 0, 1)
    with pytest.raises(ValueError):
        sample(items, len(items) + 1, 1)
    assert "human_label" in to_csv(s1).splitlines()[0]


def test_score_exact_interval_and_edge_cases() -> None:
    def sheet(labels: list[str], source: str = "") -> str:
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["test_id", "stratum", "human_label", "label_source"])
        for i, lab in enumerate(labels):
            w.writerow([i, "s", lab, source])
        return out.getvalue()

    est = score(sheet(["valid"] * 9 + ["invalid"]))
    assert (est.k, est.n) == (1, 10) and est.lower == pytest.approx(0.0025, abs=1e-3)
    assert est.upper == pytest.approx(0.4450, abs=1e-3)  # exact Clopper-Pearson 1/10
    zero = score(sheet(["valid"] * 5 + [""]))
    assert zero.n == 5 and zero.k == 0 and zero.lower == 0.0 and zero.upper > 0.4
    assert score(sheet(["ambiguous", "valid"])).n_ambiguous == 1
    assert score(sheet(["valid"], SYNTHETIC_SOURCE)).synthetic is True
    with pytest.raises(ValueError):
        score(sheet([""]))
    with pytest.raises(ValueError):
        score(sheet(["maybe"]))


def test_uncovered_when_only_invalid_or_unexecuted_tests() -> None:
    reg = build_register([RiskItem(category="A", component="app"),
                          RiskItem(category="B", component="app")])
    est = compute_risk_coverage(
        reg, {"t1": "A@app", "t2": "A@app", "t3": "B@app"},
        {"t1": "invalid", "t2": "valid", "t3": "valid"}, executed={"t1", "t3"})
    assert est.uncovered_cells == ("A@app",)
    assert {c.cell_id: c.n_tests for c in est.cells} == {"A@app": 0, "B@app": 1}
    assert est.structural == () and "H3" in est.structural_note
