"""ADR-0009 end to end: gated vs advisory judge through run_evaluation, ledger-recorded judge I/O
and offline replay equality; plus the /api/judge endpoints with an injected fake-server client."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.core.ledger import SQLiteLedger
from qe.realeval import calibration as cal
from qe.realeval.assemble import example_policy
from qe.realeval.judge import SemanticJudge, check_independence
from qe.realeval.resolver import ResolvedProject
from qe.realeval.runner import Budget, EvalParams, Inputs, replay, run_evaluation
from qe.realeval.target import TargetAnswer
from qe.ui import routes_judge
from qe.ui.server import app
from tests.realeval.judge_fakes import KEY_ENV, Scripted, client, fake_server

IND = check_independence("gpt-4o", "groq:llama-3.1-8b")
QA = [{"question": "Can I cancel?", "reference_answer": "Customers can cancel at any time"},
      {"question": "Is shipping free?", "reference_answer": "Shipping is free"}]
ANSWERS = {"Can I cancel?": "You are free to terminate whenever you like.",
           "Is shipping free?": "Shipping is free."}


class Target:
    def ask(self, question: str) -> TargetAnswer:
        return TargetAnswer(answer=ANSWERS[question], contexts=[], latency_s=0.01)


def project() -> ResolvedProject:
    return ResolvedProject("p1", "demo", Target(), [{"name": "d.md", "text": "x"}], QA,
                           authorized=True)


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "fake-not-a-secret")


def script() -> Scripted:
    return Scripted(rubric={"terminate": "correct", "Shipping is free": "correct",
                            "bad-answer": "incorrect", "good-answer": "correct"})


def calibration_items() -> list[cal.CalibrationItem]:
    items = [cal.CalibrationItem(question="q", reference="ref", answer=f"bad-answer-{k}",
                                 label="incorrect") for k in range(20)]
    return [*items, *(cal.CalibrationItem(question="q", reference="ref",
                                          answer=f"good-answer-{k}", label="correct")
                      for k in range(20))]


def evaluate(tmp: Path, judge: SemanticJudge, min_agreement: float | None) -> dict[str, Any]:
    policy = example_policy().model_copy(update={"judge_min_agreement": min_agreement})
    return run_evaluation(
        "eval-00000001", tmp / "e.sqlite",
        EvalParams(max_questions=10, repeats=1, include_security=False,
                   generate_questions=False, policy=policy),
        Inputs(project=project(), judge=judge), Budget(), threading.Event())


def row(res: dict[str, Any], question: str) -> dict[str, Any]:
    return next(r for r in res["items"] if r["question"] == question)


def test_gated_judge_fixes_false_fail_and_replays_offline(tmp_path: Path) -> None:
    with fake_server(script()) as url:
        j = SemanticJudge.from_clients([("gpt-4o", client(url, "gpt-4o"))], 100, IND)
        rec = cal.calibrate(calibration_items(), j)
        cal.save(rec, j.calls())
        live = SemanticJudge.from_clients([("gpt-4o", client(url, "gpt-4o"))], 100, IND)
        res = evaluate(tmp_path, live, min_agreement=0.8)
    assert res["judge"]["gating"] is True and res["judge"]["gate"]["calibration_id"] == rec.id
    assert row(res, "Can I cancel?")["scores"]["correct"] is True  # paraphrase now correct
    assert row(res, "Can I cancel?")["passed"] is True
    assert "correctness" in res["judge"]["corrected"]
    assert res["judge"]["usage"]["calls_used"] == 2  # two items; repeats and legacy call memoised
    # the ledger holds the judge's raw I/O: replay needs no server and no network
    ledger = SQLiteLedger(tmp_path / "e.sqlite")
    keys = [e.event.key for e in ledger.entries() if e.event.key.startswith("judgecall:")]
    ledger.close()
    assert len(keys) == 2
    again = replay(tmp_path / "e.sqlite")
    assert [r["scores"] for r in again["items"]] == [r["scores"] for r in res["items"]]
    assert [r["passed"] for r in again["items"]] == [r["passed"] for r in res["items"]]
    assert again["metrics"] == res["metrics"] and again["decision"] == res["decision"]
    assert again["judge"]["gating"] is True and again["judge"]["gate"] == res["judge"]["gate"]
    assert again["ledger_ok"] is True


def test_without_calibration_or_policy_minimum_the_judge_is_advisory(tmp_path: Path) -> None:
    with fake_server(script()) as url:
        j = SemanticJudge.from_clients([("gpt-4o", client(url, "gpt-4o"))], 100, IND)
        res = evaluate(tmp_path, j, min_agreement=0.8)  # no calibration record exists
        assert res["judge"]["gating"] is False and "no calibration" in res["judge"]["gate"]["reason"]
        j2 = SemanticJudge.from_clients([("gpt-4o", client(url, "gpt-4o"))], 100, IND)
        (tmp_path / "second").mkdir()
        res2 = evaluate(tmp_path / "second", j2, min_agreement=None)
    assert row(res, "Can I cancel?")["scores"]["correct"] is False  # lexical verdict decides
    assert row(res, "Can I cancel?")["scores"]["judge_correct_untrusted"] is True  # but shown
    assert "judge_min_agreement" in res2["judge"]["gate"]["reason"]


# ---------------------------------------------------------------- API
api = TestClient(app)
FULL = {"QE_ALLOW_REAL_LLM": "1", "GROQ_API_KEY": "k", "QE_LLM_SPEND_BUDGET_USD": "1",
        "QE_LLM_MAX_CALLS": "5", "QE_LLM_MODEL": "llama-3.1-8b-instant"}


def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server imports .env at load time: start every API test from a known-empty config."""
    for k in (*FULL, "QE_JUDGE_MODEL", "QE_JUDGE_MODEL_2", "QE_AGENT_MODEL", "QE_TARGET_MODEL",
              "OPENROUTER_API_KEY", "QE_JUDGE_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)


def test_status_without_configuration_lists_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)
    body = api.get("/api/judge/status").json()
    assert body["configured"] is False and body["independent"] is False
    assert body["calibration"] is None and "QE_JUDGE_MODEL" in body["missing"]
    assert "k" not in str(body["missing"]).replace("KEY", "")  # names only, never values
    assert api.get("/api/judge/calibration").json() == {"latest": None, "records": []}
    assert api.post("/api/judge/calibrate", json={"items": [
        {"answer": "a", "reference": "r", "label": "correct"}]}).status_code == 409


def test_status_same_family_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)
    for k, v in FULL.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("QE_JUDGE_MODEL", "meta-llama/llama-3.3-70b")
    body = api.get("/api/judge/status").json()
    assert body["configured"] is False and body["independent"] is False
    assert body["generator_family"] == "meta" and body["judge_family"] == "meta"


def test_calibrate_status_and_stale_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    clean_env(monkeypatch)
    for k, v in FULL.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("QE_JUDGE_MODEL", "gpt-4o")
    with fake_server(script()) as url:
        routes_judge.set_client_factory(lambda provider, model, env: client(url, model))
        try:
            status = api.get("/api/judge/status").json()
            assert status["configured"] and status["independent"] and status["calibration"] is None
            assert status["judge_family"] == "openai" and status["generator_family"] == "meta"
            bad = api.post("/api/judge/calibrate", json={"items": [{"answer": "a", "label": "x"}]})
            assert bad.status_code == 422
            items = [i.model_dump(mode="json") for i in calibration_items()]
            r = api.post("/api/judge/calibrate", json={"items": items})
            assert r.status_code == 200, r.text
            rec = r.json()
            assert rec["n"] == 40 and rec["agreement"] == 1.0 and rec["usage"]["calls_used"] == 40
            status = api.get("/api/judge/status").json()
            cal_block = status["calibration"]
            assert cal_block["n"] == 40 and cal_block["stale"] is False
            assert set(cal_block) >= {"n", "agreement", "ci", "prompt_hash", "stale"}
            latest = api.get("/api/judge/calibration").json()
            assert latest["latest"]["id"] == rec["id"] and len(latest["records"]) == 1
            monkeypatch.setenv("QE_JUDGE_MODEL", "claude-3-haiku")  # judge changed -> stale
            assert api.get("/api/judge/status").json()["calibration"]["stale"] is True
        finally:
            routes_judge.set_client_factory(None)
