"""Items 2, 5, 6, 9, 10: unchecked items, mandatory security evidence, user-chosen policy,
root-clustered statistics with a hard item cap, risk-flag mapping, derived monitoring plan."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.core.schemas import Policy
from qe.realeval import jobs, resolver
from qe.realeval.assemble import example_policy, root_ids
from qe.realeval.dataset import EvalItem
from qe.realeval.dynamic import FLAG_SCENARIOS, normalize_risks
from qe.realeval.exports import monitoring_plan
from qe.realeval.resolver import ResolvedProject
from qe.realeval.runner import Budget, EvalParams, Inputs, run_evaluation
from qe.realeval.target import CallableTarget, FakeRagTarget
from qe.ui.server import app
from tests.realeval.conftest import DOC, QA
from tests.realeval.test_engine import params, project, run

client = TestClient(app)


def policy(required: tuple[str, ...], appetite: float = 0.5) -> Policy:
    return Policy(policy_id="mine", version="1", loss_matrix={}, required_evidence=required,
                  risk_appetite={k: appetite for k in required})


# ---- item 2
def test_unchecked_items_are_excluded_and_counted(tmp_path: Path) -> None:
    proj = ResolvedProject("p1", "d", CallableTarget(lambda q: ("Whatever.", [])), [DOC],
                           [{"question": "Anything?"}, {"question": "More?"}], authorized=True)
    res = run(tmp_path, proj, params(max_questions=4, include_security=False))
    rows = [r for r in res["items"] if r["source"] == "user"]
    assert rows and all(r["passed"] is None for r in rows)
    assert res["unchecked"]["count"] >= len(rows)
    checked = [r for r in res["items"] if r["passed"] is not None]
    assert res["metrics"]["overall_pass_rate"]["n_items"] == len(checked)
    assert all(r["id"] not in res["unchecked"]["ids"] for r in checked)
    assert any("UNCHECKED" in n for n in res["notes"])
    assert res["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert any("unchecked" in r for r in res["decision"]["reasons"])


def test_unanswerable_flag_end_to_end(tmp_path: Path) -> None:
    qa = [{"question": f"Quuxlorp{k} frobnicate?", "answerable": False} for k in range(4)]
    res = run(tmp_path, project(qa=qa), params(max_questions=8, include_security=False))
    assert all(r["passed"] is True for r in res["items"] if r["source"] == "user")
    assert sum(r["source"] == "user" for r in res["items"]) == 4
    assert res["metrics"]["refusal_correctness"]["n_items"] >= 4


def test_judge_is_advisory_for_unreferenced_items(tmp_path: Path) -> None:
    class J:
        family = "other:judge"

        def judge(self, question: str, reference: str, answer: str) -> bool | None:
            assert reference == ""
            return True

    proj = ResolvedProject("p1", "d", CallableTarget(lambda q: ("Whatever.", [])), [DOC],
                           [{"question": "Anything?"}], authorized=True)
    res = run(tmp_path, proj, params(max_questions=3, include_security=False), judge=J())
    row = next(r for r in res["items"] if r["source"] == "user")
    assert row["scores"]["judge_advisory"] is True and row["passed"] is None


def test_inputs_endpoint_accepts_answerable_and_rejects_contradiction() -> None:  # tmp runs dir via conftest
    from qe.ingest import store
    from qe.ingest.models import Project

    pr = Project(id="prj-abcdef0123", repo_url="https://github.com/a/b", created_at=1.0,
                 state="ready", authorized=True)
    store.save(pr)
    try:
        ok = client.post("/api/projects/prj-abcdef0123/inputs", json={"qa_pairs": [
            {"question": "q1", "answerable": False}, {"question": "q2", "reference_answer": "a"}]})
        assert ok.status_code == 200 and ok.json()["qa_pairs"][0]["answerable"] is False
        bad = client.post("/api/projects/prj-abcdef0123/inputs", json={"qa_pairs": [
            {"question": "q", "reference_answer": "a", "answerable": False}]})
        assert bad.status_code == 422
    finally:
        store.delete("prj-abcdef0123")


# ---- item 5
def test_include_security_false_is_a_required_evidence_gap(tmp_path: Path) -> None:
    pol = policy(("answer_correctness", "faithfulness"), 0.9)
    res = run(tmp_path, project(), params(policy=pol, include_security=False))
    d = res["decision"]
    assert d["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert any("security not tested" in r for r in d["reasons"])


def test_security_ran_but_policy_has_no_appetite_is_a_gap(tmp_path: Path) -> None:
    pol = policy(("answer_correctness",), 0.9)
    res = run(tmp_path, project(), params(policy=pol))
    assert res["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert any("injection_resistance" in r for r in res["decision"]["reasons"])


def test_example_policy_always_requires_security() -> None:
    assert "injection_resistance" in example_policy().required_evidence


def test_injection_resistance_is_added_when_policy_has_the_appetite(tmp_path: Path) -> None:
    pol = Policy(policy_id="m", version="1", loss_matrix={},
                 required_evidence=("answer_correctness",),
                 risk_appetite={"answer_correctness": 0.9, "injection_resistance": 0.1})
    res = run(tmp_path, project("injectable"), params(policy=pol))
    assert res["decision"]["verdict"] == "REJECT"  # the security failure now decides


# ---- item 5: API
@pytest.fixture
def wired() -> Any:
    resolver.set_resolver(lambda pid: ResolvedProject(
        pid, "demo", FakeRagTarget([DOC["text"]], "perfect"), [DOC], QA[:12], authorized=True))
    yield
    resolver.set_resolver(None)


def test_policy_template_has_null_numbers() -> None:
    t = client.get("/api/policy/template").json()
    pol = t["policy"]
    assert pol["policy_id"] is None and pol["required_evidence"] == []
    assert pol["risk_appetite"] and all(v is None for v in pol["risk_appetite"].values())
    assert "injection_resistance" in pol["risk_appetite"]
    assert {m["name"] for m in t["metrics"]} >= {"answer_correctness", "injection_resistance"}


def test_evaluation_requires_a_chosen_policy(wired: Any) -> None:
    r = client.post("/api/evaluations", json={"project_id": "p1", "generate_questions": False})
    assert r.status_code == 422 and "no policy chosen" in r.text


def test_example_policy_is_explicit_and_flagged(wired: Any) -> None:
    r = client.post("/api/evaluations", json={
        "project_id": "p1", "generate_questions": False, "use_example_policy": True,
        "max_questions": 12, "repeats": 1})
    assert r.status_code == 202
    assert jobs.wait(r.json()["id"])["decision"]["policy_is_example"] is True


def test_user_policy_without_security_is_rejected_unless_security_off(wired: Any) -> None:
    raw = {"policy_id": "p", "version": "1", "loss_matrix": {},
           "required_evidence": ["answer_correctness"], "risk_appetite": {"answer_correctness": .2}}
    r = client.post("/api/evaluations", json={"project_id": "p1", "policy": raw,
                                              "generate_questions": False})
    assert r.status_code == 422 and "injection_resistance" in r.text
    ok = client.post("/api/evaluations", json={
        "project_id": "p1", "policy": raw, "generate_questions": False,
        "include_security": False, "max_questions": 12, "repeats": 1})
    assert ok.status_code == 202
    rec = jobs.wait(ok.json()["id"])
    assert rec["decision"]["policy_is_example"] is False
    assert rec["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_defaults_are_larger_samples() -> None:
    assert EvalParams().max_questions == 50 and EvalParams().repeats == 3
    from qe.ui.routes_eval import EvalRequest
    r = EvalRequest(project_id="p1")
    assert r.max_questions == 50 and r.repeats == 3


# ---- item 6
def test_root_ids_follow_lineage_chains() -> None:
    rows = [{"id": "a", "lineage": None}, {"id": "b", "lineage": {"parent": "a"}},
            {"id": "c", "lineage": {"parent": "b"}}, {"id": "d", "lineage": {"parent": "gone"}}]
    assert root_ids(rows) == {"a": "a", "b": "a", "c": "a", "d": "gone"}


def test_variants_do_not_inflate_n(tmp_path: Path) -> None:
    res = run(tmp_path, project(), params(max_questions=12, include_security=False, seed=3))
    m = res["metrics"]["answer_correctness"]
    assert m["n_items"] > m["n_roots"] == m["n"]
    assert res["sample"]["n_roots"] < res["sample"]["n_items"]
    assert "distinct root question" in m["note"]


def test_all_repeats_must_agree_for_a_root_to_pass(tmp_path: Path) -> None:
    calls = {"n": 0}

    def fn(q: str) -> tuple[str, list[str]]:
        calls["n"] += 1
        return ("It costs 100 dollars.", []) if calls["n"] % 2 else ("It costs 7 dollars.", [])

    proj = ResolvedProject("p1", "d", CallableTarget(fn), [DOC],
                           [{"question": "How much does Zavo0 cost?",
                             "reference_answer": "100 dollars"}], authorized=True)
    res = run(tmp_path, proj, params(max_questions=1, repeats=2, include_security=False))
    row = res["items"][0]
    assert row["scores"]["repeat_passes"] == [True, False] and row["passed"] is False
    assert res["metrics"]["answer_correctness"]["value"] == 0.0
    assert res["metrics"]["stability_pass_k"]["value"] == 0.0


def test_max_questions_is_a_hard_cap_with_regression_first(tmp_path: Path) -> None:
    reg = [EvalItem(id=f"r{k}", question=f"How much does Zavo{k} cost?",
                    reference_answer=f"{100 + k} dollars", regression=True) for k in range(3)]
    prior = [EvalItem(id="u-prev", question="How much does Zavo9 cost?",
                      reference_answer="109 dollars")]
    seen: list[dict[str, Any]] = []
    res = run_evaluation("eval-00000002", tmp_path / "c.sqlite",
                         params(max_questions=10, repeats=1), Inputs(
                             project=project(), prior_failures=prior, regression_items=reg),
                         Budget(), threading.Event(), seen.append)
    assert len(res["items"]) == 10 == res["total"] == res["progress"]["total"] if (
        "progress" in res) else len(res["items"]) == 10
    assert {"r0", "r1", "r2"} <= {r["id"] for r in res["items"]}
    assert any("max_questions=10" in n for n in res["notes"])
    assert seen and seen[-1]["total"] == 10 and seen[-1]["done"] <= 10
    assert res["done"] == res["total"] == 10


# ---- item 9
@pytest.mark.parametrize("flag,expected", [
    ("unsanitized-context-in-prompt", {"indirect_injection", "prompt_injection"}),
    ("no-top-k-bound", {"retrieval", "robustness"}),
    ("hardcoded-secret", {"data_leak"}),
    ("no-citation-handling", {"citation_check"}),
])
def test_analyzer_flags_map_to_scenarios(flag: str, expected: set[str]) -> None:
    risks, unmapped = normalize_risks([flag])
    assert expected <= set(risks) and unmapped == []


def test_every_analyzer_flag_id_is_mapped() -> None:
    import re
    src = Path("qe/ingest/analyzer.py").read_text("utf-8")
    ids = set(re.findall(r'RiskFlag\(\s*id="([a-z-]+)"', src))
    assert ids and {i.replace("-", "_") for i in ids} <= set(FLAG_SCENARIOS)


def test_unsanitized_flag_creates_indirect_injection_probes(tmp_path: Path) -> None:
    proj = project()
    proj.risk_flags = ["unsanitized-context-in-prompt"]
    res = run(tmp_path, proj, params(max_questions=20, seed=1))
    ops = {(r["lineage"] or {}).get("operator") for r in res["items"]}
    assert "indirect_injection_wrap" in ops
    assert not any("ignored" in n for n in res["notes"])


def test_no_citation_flag_makes_citations_mandatory(tmp_path: Path) -> None:
    proj = project()
    proj.risk_flags = ["no-citation-handling"]
    res = run(tmp_path, proj, params(max_questions=6, include_security=False))
    user = [r for r in res["items"] if r["source"] == "user"]
    assert user and all(r["scores"]["citation_valid"] is False for r in user)
    assert any("citation checks are mandatory" in n for n in res["notes"])


def test_unmapped_label_is_reported_not_ignored(tmp_path: Path) -> None:
    proj = project()
    proj.risk_flags = ["quantum-flux"]
    res = run(tmp_path, proj, params(max_questions=6, include_security=False))
    assert any("quantum-flux" in n and "no mapped test scenario" in n for n in res["notes"])


# ---- item 10
def test_monitoring_plan_is_derived_from_the_evaluation(tmp_path: Path) -> None:
    pol = policy(("answer_correctness", "injection_resistance"), 0.1)
    res = run(tmp_path, project("injectable"), params(policy=pol))
    rec = {**res, "id": "eval-00000009", "project_id": "p1"}
    plan = monitoring_plan(rec, pol.model_dump(mode="json"), None)
    assert plan["cadence_days"] is None and "NOT SET" in plan["cadence_note"]
    assert "injection_resistance" in plan["attention"]
    assert plan["derived_from"]["failure_classes"].get("QE-INJ")
    assert any("security probes failed" in t for t in plan["drift_triggers"])
    assert plan["rerun"]["failed_items"]
    assert monitoring_plan(rec, pol.model_dump(mode="json"), {"cadence_days": 7}
                           )["cadence_days"] == 7
