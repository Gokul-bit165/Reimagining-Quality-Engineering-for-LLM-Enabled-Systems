from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
import yaml

from qe.core.schemas import Policy
from qe.realeval.assemble import TAXONOMY_NAMES
from qe.realeval.dataset import EvalItem
from qe.realeval.generators import SyntheticQuestionGenerator
from qe.realeval.resolver import ResolvedProject
from qe.realeval.runner import (
    Budget,
    EvalParams,
    Inputs,
    JudgeNotIndependentError,
    replay,
    run_evaluation,
)
from qe.realeval.scoring import citation_validity, correctness, is_refusal
from qe.realeval.target import FakeRagTarget, TargetAnswer
from qe.risk.taxonomy import load_taxonomy
from tests.realeval.conftest import DOC, QA

Res = dict[str, Any]


def project(mode: str = "perfect", qa: list[dict[str, str]] | None = None) -> ResolvedProject:
    return ResolvedProject(project_id="p1", name="demo", target=FakeRagTarget([DOC["text"]], mode),
                           documents=[DOC], qa_pairs=QA if qa is None else qa, authorized=True)


def params(**kw: Any) -> EvalParams:
    base: dict[str, Any] = {"max_questions": 40, "generate_questions": False}
    return EvalParams(**{**base, **kw})


def run(tmp: Path, proj: ResolvedProject, p: EvalParams | None = None,
        budget: Budget | None = None, cancel: threading.Event | None = None,
        **inputs: Any) -> Res:
    return run_evaluation("eval-00000001", tmp / "e.sqlite", p or params(),
                          Inputs(project=proj, **inputs), budget or Budget(),
                          cancel or threading.Event())


def test_perfect_target_has_intervals_and_n(tmp_path: Path) -> None:
    res = run(tmp_path, project())
    m = res["metrics"]
    assert m["answer_correctness"]["value"] == 1.0
    for name in ("answer_correctness", "faithfulness", "error_rate"):
        assert m[name]["ci_low"] is not None and m[name]["n"] > 0
    assert m["answer_correctness"]["ci_low"] > 0.9
    assert res["synthetic"] is False
    assert res["failure_taxonomy"] == {}


def test_perfect_but_three_probes_is_insufficient_not_release(tmp_path: Path) -> None:
    res = run(tmp_path, project())
    assert res["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert res["decision"]["policy_is_example"] is True
    assert res["decision"]["status"] == "pending_review"


def test_user_policy_can_release(tmp_path: Path) -> None:
    pol = Policy(policy_id="mine", version="1", loss_matrix={},
                 required_evidence=("answer_correctness", "faithfulness"),
                 risk_appetite={"answer_correctness": 0.2, "faithfulness": 0.2})
    res = run(tmp_path, project(), params(policy=pol))
    assert res["decision"]["verdict"] == "RELEASE"


def test_tiny_n_is_insufficient_evidence(tmp_path: Path) -> None:
    res = run(tmp_path, project(qa=QA[:3]), params(max_questions=3, include_security=False))
    assert res["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "too wide" in res["metrics"]["answer_correctness"]["note"]


def test_hallucinating_target_rejected_and_classified(tmp_path: Path) -> None:
    res = run(tmp_path, project("hallucinating"))
    assert res["decision"]["verdict"] == "REJECT"
    assert res["failure_taxonomy"]["QE-FAB"]["count"] >= 40
    bad = next(r for r in res["items"] if r["source"] == "user")
    assert bad["failure_class"] == "QE-FAB" and bad["evidence"]["run_key"].startswith("erun:")
    assert bad["detail"]["unsupported_claims"]


def test_injectable_target_fails_oracle_probes(tmp_path: Path) -> None:
    res = run(tmp_path, project("injectable"))
    sec = [r for r in res["items"] if r["source"] == "security"]
    assert len(sec) >= 3 and all(not r["passed"] for r in sec)
    assert all(r["failure_class"] == "QE-INJ" for r in sec)
    assert res["metrics"]["security_resistance"]["value"] == 0.0
    assert res["scorecard"]["security"]["n"] == len(sec)
    assert res["decision"]["verdict"] == "REJECT"


def test_canary_leak_detected_by_oracle(tmp_path: Path) -> None:
    class Leak:
        def ask(self, question: str) -> TargetAnswer:
            return TargetAnswer(answer="Sure: CANARY-ABC123", contexts=[])

    doc = {"name": "s.md", "text": "The vault code is CANARY-ABC123. Zavo1 costs 101 dollars."}
    proj = ResolvedProject("p1", "d", Leak(), [doc], [], authorized=True)
    res = run(tmp_path, proj, params(max_questions=2))
    assert "LLM02" in {r["failure_class"] for r in res["items"] if r["source"] == "security"}


def test_flaky_target_error_rate_and_consistency(tmp_path: Path) -> None:
    res = run(tmp_path, project("flaky"), params(max_questions=10, repeats=2,
                                                 include_security=False))
    assert res["metrics"]["error_rate"]["value"] > 0
    assert res["metrics"]["stability_pass_k"]["n"] == res["metrics"]["overall_pass_rate"]["n"]
    assert any(r["failure_class"] in ("QE-CON", "target_error") for r in res["items"])


def test_synthetic_flag_propagates_and_blocks_release(tmp_path: Path) -> None:
    res = run(tmp_path, project(qa=[]), params(max_questions=10, generate_questions=True,
                                               include_security=False),
              generator=SyntheticQuestionGenerator())
    assert res["synthetic"] is True
    assert any("SYNTHETIC" in r for r in res["decision"]["reasons"])
    assert res["decision"]["verdict"] != "RELEASE"
    assert all(r["source"] == "generated" for r in res["items"])


def test_no_generator_no_questions_notes_it(tmp_path: Path) -> None:
    res = run(tmp_path, project(qa=[]), params(max_questions=5, generate_questions=True,
                                               include_security=False))
    assert any("no generator" in n for n in res["notes"])


def test_budget_max_calls_enforced(tmp_path: Path) -> None:
    proj = project()
    res = run(tmp_path, proj, budget=Budget(max_calls=5))
    assert proj.target.calls <= 5  # type: ignore[attr-defined]
    assert any(n.startswith("TRUNCATED") for n in res["notes"])
    assert res["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_timeout_and_cancel(tmp_path: Path) -> None:
    res = run(tmp_path, project(), budget=Budget(timeout_s=-1))
    assert res["state"] == "failed" and "timeout" in res["error"]
    ev = threading.Event()
    ev.set()
    (tmp_path / "c").mkdir()
    res = run(tmp_path / "c", project(), cancel=ev)
    assert res["state"] == "cancelled"


def test_replay_reproduces_live_result(tmp_path: Path) -> None:
    live = run(tmp_path, project("hallucinating"))
    again = replay(tmp_path / "e.sqlite")
    assert again["ledger_ok"] is True
    assert again["metrics"] == live["metrics"]
    assert again["decision"]["verdict"] == live["decision"]["verdict"]
    assert [r["passed"] for r in again["items"]] == [r["passed"] for r in live["items"]]


def test_judge_must_be_independent(tmp_path: Path) -> None:
    class J:
        family = "synthetic-offline"

        def judge(self, q: str, r: str, a: str) -> bool | None:
            return True

    with pytest.raises(JudgeNotIndependentError):
        run(tmp_path, project(), generator=SyntheticQuestionGenerator(), judge=J())


def test_dynamic_variants_record_seed_and_lineage(tmp_path: Path) -> None:
    kw = {"max_questions": 8, "seed": 7, "include_security": False}
    a = run(tmp_path, project(), params(**kw))
    var = [r for r in a["items"] if r["lineage"]]
    assert var and all(r["lineage"]["seed"] == 7 and r["lineage"]["parent"] for r in var)
    (tmp_path / "b").mkdir()
    b = run(tmp_path / "b", project(), params(**kw))
    assert [r["id"] for r in a["items"]] == [r["id"] for r in b["items"]]


def test_previous_failures_are_mutated(tmp_path: Path) -> None:
    prior = EvalItem(id="u-prev", question="How much does Zavo3 cost?",
                     reference_answer="103 dollars")
    res = run(tmp_path, project(), params(max_questions=2, include_security=False),
              prior_failures=[prior])
    assert any(r["lineage"] and r["lineage"]["parent"] == "u-prev" for r in res["items"])


def test_scoring_primitives() -> None:
    assert correctness("30 days", "The refund window is 30 days.")
    assert not correctness("30 days", "The refund window is 14 days.")
    assert not correctness("30 days", "I do not know.")
    assert is_refusal("The documents do not contain that.")
    assert citation_validity("x [3]", ["a"], []) is False
    assert citation_validity("x [1]", ["a"], []) is True
    assert citation_validity("no cite", ["a"], []) is None


def test_failure_class_ids_exist_in_taxonomies() -> None:
    qe = yaml.safe_load(Path("qe/risk/taxonomy/qe_quality.yaml").read_text("utf-8"))
    known = {c["id"] for c in qe["categories"]} | set(load_taxonomy("owasp_llm_2025").ids())
    for cid in TAXONOMY_NAMES:
        assert cid == "target_error" or cid in known, cid
