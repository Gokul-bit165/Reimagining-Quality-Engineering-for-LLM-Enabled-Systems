"""T2.2/T2.3: Risk Analyst, Scenario Authors (>=2 families), Skeptic, RAGAS adapter."""

import json

import pytest

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import ModelRef
from qe.crew.llm import ScriptedLLM
from qe.crew.ragas_adapter import RagasGenerator
from qe.crew.risk_analyst import propose_risks
from qe.crew.scenario_author import ScenarioAuthor, author_suite
from qe.crew.skeptic import Skeptic, SkepticInput, answers_agree, flag_redundant
from qe.model.app_model import AppModel, Node
from qe.ports import GenerationSpec, GeneratorPort
from qe.risk.register import RankedRisk, RiskProposal
from qe.risk.taxonomy import load_taxonomy

A = ModelRef(provider="fake", name="a", family="fam-a")
B = ModelRef(provider="fake", name="b", family="fam-b")
SRC = {"KB-1": "Returns are accepted within 30 days of delivery. Labels are free for defects."}
MODEL = AppModel(nodes=(Node(id="llm:planner", kind="llm"),), edges=())


def ledger(tmp_path):  # type: ignore[no-untyped-def]
    return SQLiteLedger(tmp_path / "l.db")


async def test_risk_analyst_filters_to_taxonomy_and_model_and_records_drafts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    reply = json.dumps([
        {"taxonomy_id": "LLM09", "component": "llm:planner", "rationale": "fabrication"},
        {"taxonomy_id": "LLM99", "component": "llm:planner", "rationale": "invented"},
        {"taxonomy_id": "LLM01", "component": "tool:ghost", "rationale": "no such node"},
    ])
    led = ledger(tmp_path)
    res = await propose_risks(ScriptedLLM(A, [reply]), MODEL, load_taxonomy("owasp_llm_2025"), led)
    assert [p.taxonomy_id for p in res.accepted] == ["LLM09"] and len(res.rejected) == 2
    evs = [e.event for e in led.entries() if e.event.type is EventType.RISK_PROPOSED]
    assert len(evs) == 3 and {e.producer_kind for e in evs} == {ProducerKind.LLM_AGENT}
    assert sorted(e.payload["status"] for e in evs) == ["accepted", "rejected", "rejected"]


async def test_risk_analyst_survives_garbage_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    res = await propose_risks(ScriptedLLM(A, ["not json {"]), MODEL,
                              load_taxonomy("owasp_llm_2025"), ledger(tmp_path))
    assert res.accepted == () and res.parse_error


def author_reply(n: int, quote: str = "within 30 days of delivery") -> str:
    return json.dumps([
        {"question": f"How long to return item {i}?", "expected": "30 days",
         "source_id": "KB-1", "evidence_quote": quote} for i in range(n)
    ])


RISK = RiskProposal(risk_id="R1", taxonomy_id="LLM09", component="llm:planner", rationale="r")


async def test_author_rejects_unverbatim_quote_and_unknown_source(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = ledger(tmp_path)
    bad = json.dumps([
        {"question": "q1", "expected": "x", "source_id": "KB-1", "evidence_quote": "made up"},
        {"question": "q2", "expected": "x", "source_id": "KB-9", "evidence_quote": "x"},
        {"question": "q3", "expected": "30 days", "source_id": "KB-1",
         "evidence_quote": "within 30 days of delivery"},
    ])
    res = await ScenarioAuthor(ScriptedLLM(A, [bad])).author(RISK, 3, SRC, led)
    assert len(res.tests) == 1 and len(res.rejected) == 2
    t = res.tests[0]
    assert t.risk_cell == "R1" and t.oracle_source == "source_of_truth:KB-1"
    assert t.validity == "unreviewed" and "fam-a" in " ".join(t.lineage)
    types = [e.event.type for e in led.entries()]
    assert types.count(EventType.TEST_DRAFTED) == 3


async def test_author_suite_requires_two_families_and_splits_work(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ranked = (RankedRisk(proposal=RISK, appetite=0.1, rank=0),)
    from qe.crew.planner import plan
    pl = plan(ranked, 4)
    la, lb = ScriptedLLM(A, [author_reply(4)]), ScriptedLLM(B, [author_reply(4)])
    with pytest.raises(ValueError, match="families"):
        await author_suite([ScenarioAuthor(la), ScenarioAuthor(ScriptedLLM(A, [""]))],
                           pl, ranked, SRC, ledger(tmp_path))
    res = await author_suite([ScenarioAuthor(la), ScenarioAuthor(lb)], pl, ranked, SRC,
                             ledger(tmp_path))
    fams = {t.lineage[-1] for t in res.tests}
    assert len(res.tests) == 4 and fams == {"family:fam-a", "family:fam-b"}
    assert len({t.id for t in res.tests}) == 4


def test_answers_agree_uses_numbers_then_containment() -> None:
    assert answers_agree("30 days", "Within 30 days of delivery")
    assert not answers_agree("30 days", "14 days")
    assert not answers_agree("30 days", "no limit")
    assert answers_agree("free labels", "Labels are free for defects") is False  # no containment
    assert answers_agree("Labels are free", "labels are free for defects")


async def test_skeptic_never_sees_expected_answer_and_flags(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = ledger(tmp_path)
    tests = (await ScenarioAuthor(ScriptedLLM(A, [author_reply(1)])).author(RISK, 1, SRC, led)).tests
    sk_llm = ScriptedLLM(B, [json.dumps({"answerable": True, "answer": "30 days", "ambiguous": False})])
    a = await Skeptic(sk_llm).assess(tests[0], SRC["KB-1"], "fam-a", led)
    assert a.status == "valid"
    assert set(json.loads(sk_llm.calls[0][1])) == {"question", "source_text"}
    wrong = ScriptedLLM(B, [json.dumps({"answerable": True, "answer": "14 days", "ambiguous": False})])
    assert (await Skeptic(wrong).assess(tests[0], SRC["KB-1"], "fam-a", led)).status == "invalid"
    amb = ScriptedLLM(B, [json.dumps({"answerable": True, "answer": "30 days", "ambiguous": True})])
    assert (await Skeptic(amb).assess(tests[0], SRC["KB-1"], "fam-a", led)).status == "ambiguous"
    garbage = ScriptedLLM(B, ["???"])
    assert (await Skeptic(garbage).assess(tests[0], SRC["KB-1"], "fam-a", led)).status == "invalid"
    vtypes = [e.event for e in led.entries() if e.event.type is EventType.VALIDITY_VERDICT]
    assert len(vtypes) == 4 and all(e.producer_kind is ProducerKind.LLM_AGENT for e in vtypes)


async def test_skeptic_same_family_as_author_is_refused(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = ledger(tmp_path)
    t = (await ScenarioAuthor(ScriptedLLM(A, [author_reply(1)])).author(RISK, 1, SRC, led)).tests[0]
    with pytest.raises(ValueError, match="family"):
        await Skeptic(ScriptedLLM(A, ["{}"])).assess(t, SRC["KB-1"], "fam-a", led)


def test_skeptic_input_forbids_extra_fields() -> None:
    with pytest.raises(Exception):  # noqa: B017
        SkepticInput(question="q", source_text="s", expected="leak")  # type: ignore[call-arg]


async def test_redundancy_flags_duplicates(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = ledger(tmp_path)
    ts = (await ScenarioAuthor(ScriptedLLM(A, [author_reply(1) .replace("item 0", "ITEM 0")]))
          .author(RISK, 1, SRC, led)).tests
    dup = ts[0].model_copy(update={"id": "other"})
    assert flag_redundant([ts[0], dup]) == {"other": ts[0].id}
    assert flag_redundant([ts[0]]) == {}


async def test_ragas_adapter_satisfies_generator_port_and_never_marks_valid() -> None:
    class Backend:
        def generate(self, docs: dict[str, str], n: int, seed: int) -> list[dict[str, str]]:
            return [{"question": f"q{i}", "reference": "r", "source_id": next(iter(docs))}
                    for i in range(n)]

    g = RagasGenerator(Backend(), SRC)
    assert isinstance(g, GeneratorPort)
    out = await g.generate(GenerationSpec(source_ids=("KB-1",), n=2, seed=1))
    assert len(out) == 2 and all(t.validity == "unreviewed" for t in out)
    assert out[0].oracle_source == "source_of_truth:KB-1" and out[0].lineage[0] == "ragas"
    with pytest.raises(KeyError):
        await g.generate(GenerationSpec(source_ids=("nope",), n=1))
