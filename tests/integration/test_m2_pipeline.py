"""M2 pipeline on the real sandbox apps with scripted (fake) crew LLMs.

Checks plumbing and the R3/R4 guarantees only. Scripted LLMs say nothing about real-model
invalid-test rates, so no rate is asserted or claimed here.
"""

import json

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import ModelRef, Policy, Span
from qe.crew.audit import drafted_tests
from qe.crew.llm import ScriptedLLM
from qe.crew.planner import plan
from qe.crew.risk_analyst import propose_risks
from qe.crew.scenario_author import ScenarioAuthor, author_suite
from qe.crew.skeptic import Skeptic
from qe.model.app_model import build_from_traces
from qe.risk.coverage import build_coverage, record_coverage
from qe.risk.register import rank_risks
from qe.risk.taxonomy import load_taxonomy
from sandbox_apps.rag import build_app

QS = ["How long to pay import duties?", "Is there a deadline for insurance claims?",
      "Can you ship lithium batteries?"]


async def test_m2_pipeline_on_rag_sandbox(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = build_app(variant="clean", llm=None, seed=0)
    traces = []
    for q in QS:
        r = app.invoke({"input": q, "want_trace": True})
        traces.append(tuple(Span(span_id=f"s{i}", kind=str(ev["type"]), attributes=ev)
                            for i, ev in enumerate(r["trace"])))
    model = build_from_traces(traces)
    assert model.n_traces == 3 and model.nodes
    docs = {k: v["text"] for k, v in app.corpus_manifest()["docs"].items()}
    node = sorted(model.node_ids())[0]
    A = ModelRef(provider="fake", name="a", family="fam-a")
    B = ModelRef(provider="fake", name="b", family="fam-b")
    led = SQLiteLedger(tmp_path / "ledger.db")

    risks = await propose_risks(
        ScriptedLLM(A, [json.dumps([
            {"taxonomy_id": "LLM09", "component": node, "rationale": "fabricated answers"},
            {"taxonomy_id": "LLM01", "component": node, "rationale": "injected doc"}])]),
        model, load_taxonomy("owasp_llm_2025"), led)
    assert len(risks.accepted) == 2
    pol = Policy(policy_id="ex", version="1", loss_matrix={}, required_evidence=(),
                 risk_appetite={"LLM09": 0.02}, example_only=True)
    ranked = rank_risks(risks.accepted, pol)
    assert ranked[0].proposal.taxonomy_id == "LLM09"
    pl = plan(ranked, budget=2)  # one test each

    quote = docs["KB-005"].split(". ")[2]  # a sentence copied verbatim
    reply = json.dumps([{"question": "Is there a deadline for insurance claims?",
                         "expected": "14 days", "source_id": "KB-005", "evidence_quote": quote}])
    suite = await author_suite(
        [ScenarioAuthor(ScriptedLLM(A, [reply])), ScenarioAuthor(ScriptedLLM(B, [reply]))],
        pl, ranked, docs, led)
    assert len(suite.tests) == 2 and not suite.rejected

    sk = Skeptic(ScriptedLLM(ModelRef(provider="fake", name="c", family="fam-c"),
                             [json.dumps({"answerable": True, "answer": "14 days",
                                          "ambiguous": False})]))
    statuses = {}
    for t in suite.tests:
        a = await sk.assess(t, docs["KB-005"], t.lineage[-1].removeprefix("family:"), led)
        statuses[t.id] = a.status
    rep = build_coverage(load_taxonomy("owasp_llm_2025"), risks.accepted, suite.tests, statuses,
                         model, traces)
    assert {c.status for c in rep.cells} == {"COVERED"}
    assert rep.structural.edges_exercised <= rep.structural.edges_total
    record_coverage(led, rep)

    assert led.verify().ok
    for e in led.entries():
        if e.event.type in (EventType.RISK_PROPOSED, EventType.TEST_DRAFTED,
                            EventType.VALIDITY_VERDICT):
            assert e.event.producer_kind is ProducerKind.LLM_AGENT
            assert len(e.event.payload["prompt_sha256"]) == 64
    assert len(drafted_tests(led)) == 2
