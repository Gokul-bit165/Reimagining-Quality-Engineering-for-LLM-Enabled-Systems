"""Crew infrastructure: prompts hashed, drafts recorded with R3 permissions, planner."""

import pytest

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import ModelRef, Policy
from qe.crew.llm import ScriptedLLM
from qe.crew.planner import plan
from qe.crew.prompts import load_prompt
from qe.crew.recording import record_draft
from qe.risk.register import RiskProposal, rank_risks


def test_prompt_is_versioned_file_with_stable_hash() -> None:
    p = load_prompt("risk_analyst")
    assert p.version and len(p.sha256) == 64 and p.sha256 == load_prompt("risk_analyst").sha256
    with pytest.raises(KeyError):
        load_prompt("../../pyproject")


def test_record_draft_hashes_prompt_and_pins_llm_kind(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = SQLiteLedger(tmp_path / "l.db")
    llm = ScriptedLLM(ModelRef(provider="fake", name="a", family="fam-a"), ["x"])
    pr = load_prompt("risk_analyst")
    e = record_draft(led, EventType.RISK_PROPOSED, "k1", {"v": 1}, pr, llm.model, raw_output="x")
    assert e.event.producer_kind is ProducerKind.LLM_AGENT
    assert e.event.payload["prompt_sha256"] == pr.sha256
    assert e.event.payload["model"]["family"] == "fam-a" and e.event.payload["raw_output"] == "x"
    assert record_draft(led, EventType.RISK_PROPOSED, "k1", {"v": 1}, pr, llm.model, "x").seq == e.seq


def test_record_draft_refuses_evidence_types(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = SQLiteLedger(tmp_path / "l.db")
    m = ModelRef(provider="fake", name="a", family="f")
    with pytest.raises(PermissionError):
        record_draft(led, EventType.EVIDENCE_RECORDED, "k", {}, load_prompt("risk_analyst"), m, "")


def test_llm_agent_cannot_write_decision_directly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    led = SQLiteLedger(tmp_path / "l.db")
    with pytest.raises(PermissionError):
        led.append(Event(key="d", type=EventType.DECISION_ISSUED, producer="x",
                         producer_kind=ProducerKind.LLM_AGENT, payload={}))


def test_planner_round_robin_by_rank_and_reports_unplanned() -> None:
    pol = Policy(policy_id="p", version="1", loss_matrix={}, required_evidence=(),
                 risk_appetite={"LLM09": 0.01, "LLM01": 0.05}, example_only=True)
    ps = [RiskProposal(risk_id=f"R{i}", taxonomy_id=t, component="c", rationale="r")
          for i, t in enumerate(["LLM01", "LLM09", "LLM06"])]
    pl = plan(rank_risks(ps, pol), budget=4)
    assert dict(pl.allocation) == {"R1": 2, "R0": 1, "R2": 1}
    assert sum(n for _, n in pl.allocation) == 4 and pl.unplanned == ()
    small = plan(rank_risks(ps, pol), budget=2)
    assert dict(small.allocation) == {"R1": 1, "R0": 1} and small.unplanned == ("R2",)
    assert plan(rank_risks(ps, pol), budget=0).unplanned == ("R1", "R0", "R2")
    with pytest.raises(ValueError):
        plan(rank_risks(ps, pol), budget=-1)
