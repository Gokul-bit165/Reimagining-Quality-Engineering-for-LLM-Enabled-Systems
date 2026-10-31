import asyncio
import json
from pathlib import Path

import pytest

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.crew.authors import AuthorSlot, author_scenarios
from qe.crew.fakes import fake_llm
from qe.crew.generator import RagScenarioGenerator
from qe.crew.llm import FakeLLM, live_client
from qe.crew.prompt_store import load_prompt
from qe.crew.ragas_adapter import OptionalDependencyError, RagasGenerator
from qe.crew.record import record_crew_event
from qe.crew.risk_analyst import propose_risks
from qe.model.builder import build_model
from qe.ports import GenerationSpec, GeneratorPort
from qe.risk.planner import Weights, load_weights, plan
from qe.risk.register import RiskItem, build_register
from qe.risk.taxonomy import load_all, load_taxonomy
from sandbox_apps.rag.corpus import official_docs

ROOT = Path(__file__).resolve().parents[2]
DOCS = {k: v["text"] for k, v in list(official_docs().items())[:6]}


def ledger(tmp_path: Path) -> SQLiteLedger:
    return SQLiteLedger(tmp_path / "l.sqlite")


def slots() -> list[AuthorSlot]:
    return [AuthorSlot("author_a", fake_llm("fam-a")), AuthorSlot("author_b", fake_llm("fam-b"))]


# --- taxonomy -----------------------------------------------------------------------------
def test_taxonomies_are_labelled_unverified_and_complete() -> None:
    llm, agentic = load_taxonomy("owasp_llm_top10"), load_taxonomy("owasp_agentic")
    assert len(llm.categories) == 10 and len(agentic.categories) == 10
    for t in (llm, agentic):
        assert "UNVERIFIED transcription; verify against genai.owasp.org before citing" in t.label
        assert t.verified is False
    assert {t.name for t in load_all()} == {"owasp_llm_top10", "owasp_agentic", "qe_quality"}


# --- risk analyst -------------------------------------------------------------------------
def _model():  # type: ignore[no-untyped-def]
    from qe.core.schemas import RunRecord, VisibilityLevel
    from qe.model.builder import spans_from_trace
    from sandbox_apps.rag import build_app

    resp = build_app("clean").invoke({"input": "How many days to return?", "want_trace": True})
    rr = RunRecord(test_case_id="t", repeat_index=0, seed=0, visibility_level=VisibilityLevel.B_SDK,
                   request={}, response={}, spans=spans_from_trace(resp["trace"]))
    return build_model([rr])


def test_risk_analyst_rejects_out_of_taxonomy_and_unknown_components(tmp_path: Path) -> None:
    bad = json.dumps({"risks": [
        {"category": "LLM99", "component": "retriever", "rationale": "x"},
        {"category": "LLM08", "component": "no-such-node", "rationale": "x"},
        {"category": "LLM08", "component": "retriever", "rationale": "ok"},
        "garbage",
    ]})
    llm = FakeLLM("fam-x", {"risk_analyst": lambda s, u: bad})
    led = ledger(tmp_path)
    out = propose_risks(llm, _model(), load_all(), led)
    assert [r.category for r in out.accepted] == ["LLM08"]
    assert {r.reason for r in out.rejected} == {
        "category not in taxonomy", "component not in app model", "proposal is not an object"}
    events = [e.event for e in led.entries()]
    assert all(e.type is EventType.RISK_PROPOSED and e.producer_kind is ProducerKind.LLM_AGENT
               for e in events)
    prompt = load_prompt("risk_analyst_v1")
    assert all(e.payload["prompt_sha256"] == prompt.sha256 for e in events)
    assert len(events) == 4


def test_risk_analyst_fake_is_deterministic_and_in_taxonomy() -> None:
    a = propose_risks(fake_llm("fam-x"), _model(), load_all())
    b = propose_risks(fake_llm("fam-x"), _model(), load_all())
    assert a == b and a.accepted and not a.rejected


def test_unparseable_llm_output_yields_no_proposals() -> None:
    llm = FakeLLM("f", {"risk_analyst": lambda s, u: "not json"})
    out = propose_risks(llm, _model(), load_all())
    assert out.accepted == () and out.rejected == ()


def test_crew_cannot_write_evidence_types(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        record_crew_event(ledger(tmp_path), EventType.VERDICT_ISSUED, "x", {})


# --- planner ------------------------------------------------------------------------------
def test_planner_is_deterministic_budgeted_and_reports_unweighted() -> None:
    reg = build_register([RiskItem(category="LLM01", component="app"),
                          RiskItem(category="LLM09", component="app"),
                          RiskItem(category="LLM08", component="retriever"),
                          RiskItem(category="QE-FAB", component="app")])
    w = Weights(label="EXAMPLE", example_only=True, budget_tests=10, min_per_cell=1,
                weights={"LLM01": 5, "LLM09": 3, "LLM08": 2})
    p = plan(reg, w)
    assert [c.category for c in p.cells][:3] == ["LLM01", "LLM09", "LLM08"]
    assert sum(c.allocated_tests for c in p.cells) == 10
    assert p.unweighted == ("QE-FAB@app",) and p.cells[-1].allocated_tests == 0
    assert p.example_only and plan(reg, w) == p


def test_planner_reports_floor_over_budget_and_zero_weights() -> None:
    reg = build_register([RiskItem(category="A", component="app"),
                          RiskItem(category="B", component="app")])
    p = plan(reg, Weights(label="x", budget_tests=1, min_per_cell=2, weights={"A": 0, "B": 0}))
    assert p.over_budget_by_floor == 3 and [c.allocated_tests for c in p.cells] == [2, 2]
    with pytest.raises(ValueError):
        Weights(label="x", budget_tests=1, weights={"A": -1})


def test_example_weights_file_is_labelled_example() -> None:
    w = load_weights(ROOT / "qe" / "risk" / "examples" / "weights.example.yaml")
    assert w.example_only and w.label.startswith("EXAMPLE")


# --- scenario authors / generator ---------------------------------------------------------
def test_authors_require_two_distinct_families() -> None:
    same = [AuthorSlot("a", fake_llm("fam")), AuthorSlot("b", fake_llm("fam"))]
    with pytest.raises(ValueError, match="distinct model families"):
        author_scenarios(same, "cell", DOCS, 2)
    with pytest.raises(ValueError):
        author_scenarios(same[:1], "cell", DOCS, 2)


def test_authors_deterministic_drafts_recorded_with_prompt_hash(tmp_path: Path) -> None:
    led = ledger(tmp_path)
    d1 = author_scenarios(slots(), "LLM09@app", DOCS, 3, led)
    d2 = author_scenarios(slots(), "LLM09@app", DOCS, 3)
    assert d1 == d2 and len(d1) >= 4
    assert {d.family for d in d1} == {"fam-a", "fam-b"}
    ev = [e.event for e in led.entries()]
    assert {e.type for e in ev} == {EventType.TEST_DRAFTED}
    assert all(e.payload["prompt_sha256"] == load_prompt("scenario_author_v1").sha256 for e in ev)
    assert all(d.case.risk_cell == "LLM09@app" for d in d1)


def test_generator_port_without_ragas() -> None:
    gen = RagScenarioGenerator(slots(), DOCS, "LLM09@app")
    assert isinstance(gen, GeneratorPort)
    cases = asyncio.run(gen.generate(GenerationSpec(source_ids=("KB-001", "KB-002"), n=3)))
    assert len(cases) == 3
    with pytest.raises(KeyError):
        asyncio.run(gen.generate(GenerationSpec(source_ids=("NOPE",), n=1)))


def test_ragas_adapter_is_lazy_and_optional() -> None:
    try:
        import ragas  # noqa: F401
    except ImportError:
        with pytest.raises(OptionalDependencyError):
            RagasGenerator()


# --- live client gating -------------------------------------------------------------------
def test_live_client_refused_without_qe_live_and_never_leaks_key() -> None:
    with pytest.raises(PermissionError):
        live_client("https://x.example", "m", "f", "KEY", env={"KEY": "secret-value"})
    c = live_client("https://x.example", "m", "f", "KEY", env={"QE_LIVE": "1", "KEY": "secret-value"})
    assert "secret-value" not in repr(c)
    with pytest.raises(RuntimeError) as err:
        live_client("https://x.example", "m", "f", "MISSING", env={"QE_LIVE": "1"},
                    dotenv=Path("nonexistent.env"))
    assert "secret" not in str(err.value)


def test_prompt_hash_changes_with_content(tmp_path: Path) -> None:
    (tmp_path / "p_v1.md").write_text("ROLE: x\nA", encoding="utf-8")
    a = load_prompt("p_v1", tmp_path)
    (tmp_path / "p_v1.md").write_text("ROLE: x\nB", encoding="utf-8")
    assert a.sha256 != load_prompt("p_v1", tmp_path).sha256
    with pytest.raises(FileNotFoundError):
        load_prompt("missing", tmp_path)
