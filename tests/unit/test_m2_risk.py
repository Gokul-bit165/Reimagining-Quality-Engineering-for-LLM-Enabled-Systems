"""T2.2 risk taxonomy, register and policy-code ranking."""

import pytest
from pydantic import ValidationError

from qe.core.schemas import Policy
from qe.risk.register import RiskProposal, rank_risks, validate_proposals
from qe.risk.taxonomy import load_taxonomy


def pol(appetite: dict[str, float]) -> Policy:
    return Policy(
        policy_id="ex", version="1", loss_matrix={}, required_evidence=(),
        risk_appetite=appetite, example_only=True,
    )


def test_owasp_llm_taxonomy_loaded_with_citation() -> None:
    t = load_taxonomy("owasp_llm_2025")
    assert {e.id for e in t.entries} == {f"LLM{i:02d}" for i in range(1, 11)}
    assert t.source_url.startswith("https://genai.owasp.org/") and t.fetched
    assert len(t.sha256) == 64
    assert all(e.url.startswith("https://genai.owasp.org/") for e in t.entries)


def test_agentic_taxonomy_is_honestly_unverified() -> None:
    t = load_taxonomy("owasp_agentic_2026")
    assert t.entries == () and t.status == "primary_entries_not_fetched"


def test_unknown_taxonomy_rejected() -> None:
    with pytest.raises(KeyError):
        load_taxonomy("nope")


def test_proposal_outside_taxonomy_is_rejected() -> None:
    t = load_taxonomy("owasp_llm_2025")
    good = RiskProposal(risk_id="R1", taxonomy_id="LLM01", component="chat", rationale="x")
    bad = RiskProposal(risk_id="R2", taxonomy_id="LLM99", component="chat", rationale="x")
    ok, rejected = validate_proposals([good, bad], t)
    assert ok == (good,) and rejected == ((bad, "taxonomy_id not in owasp_llm_2025"),)


def test_proposal_requires_nonempty_fields() -> None:
    with pytest.raises(ValidationError):
        RiskProposal(risk_id="", taxonomy_id="LLM01", component="c", rationale="x")


def test_ranking_by_policy_lowest_appetite_first_unranked_last_and_stable() -> None:
    ps = [RiskProposal(risk_id=f"R{i}", taxonomy_id=t, component="c", rationale="r")
          for i, t in enumerate(["LLM01", "LLM02", "LLM09", "LLM06"])]
    ranked = rank_risks(ps, pol({"LLM09": 0.01, "LLM01": 0.05, "LLM02": 0.05}))
    assert [r.proposal.taxonomy_id for r in ranked] == ["LLM09", "LLM01", "LLM02", "LLM06"]
    assert ranked[-1].appetite is None and ranked[0].appetite == 0.01
    assert rank_risks(list(reversed(ps)), pol({"LLM09": 0.01}))[0].proposal.taxonomy_id == "LLM09"
