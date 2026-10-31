"""ADR-0009: judge calibration math, storage, gating policy and judge-error correction."""

from __future__ import annotations

from pathlib import Path

import pytest

from qe.realeval import calibration as cal
from qe.realeval.judge import SemanticJudge, check_independence, judge_key
from qe.stats.intervals import clopper_pearson
from tests.realeval.judge_fakes import KEY_ENV, Scripted, client, fake_server

IND = check_independence("gpt-4o", "groq:llama-3.1-8b")


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "fake-not-a-secret")


def labelled() -> tuple[list[cal.CalibrationItem], Scripted]:
    """Known confusion matrix: 4 human defects (judge catches 3, passes 1 = false pass) and
    6 human-fine answers (judge accepts 5, flags 1). tp=3 fn=1 tn=5 fp=1."""
    items, rubric = [], {}
    for k in range(4):
        items.append(cal.CalibrationItem(question="q", reference="the ref", label="incorrect",
                                         answer=f"bad-answer-{k}"))
        rubric[f"bad-answer-{k}"] = "incorrect" if k < 3 else "correct"
    for k in range(6):
        items.append(cal.CalibrationItem(question="q", reference="the ref", label="correct",
                                         answer=f"good-answer-{k}"))
        rubric[f"good-answer-{k}"] = "correct" if k < 5 else "partial"
    return items, Scripted(rubric=rubric)


def judge_at(url: str, model: str = "gpt-4o") -> SemanticJudge:
    return SemanticJudge.from_clients([(model, client(url, model))], 200, IND)


def test_calibration_math_on_known_confusion_matrix() -> None:
    items, script = labelled()
    with fake_server(script) as url:
        rec = cal.calibrate(items, judge_at(url))
    c = rec.members[0].confusion
    assert (c.tp, c.fn, c.tn, c.fp) == (3, 1, 5, 1)
    assert rec.n == 10 and rec.members[0].n_decided == 10 and rec.members[0].n_abstain == 0
    assert rec.agreement == pytest.approx(0.8)
    assert rec.agreement_ci == pytest.approx(clopper_pearson(8, 10))
    assert rec.false_pass_rate == pytest.approx(0.25)
    assert rec.false_pass_ci == pytest.approx(clopper_pearson(1, 4))
    # kappa: po=0.8; judge flags 4/10 and humans flag 4/10 -> pe=0.4*0.4+0.6*0.6=0.52
    assert rec.kappa == pytest.approx((0.8 - 0.52) / 0.48)
    assert rec.members[0].label_accuracy == pytest.approx(0.8)  # exact five-way label matches
    assert rec.judge_key == judge_key(["gpt-4o"]) and len(rec.prompt_hashes) == 2


def test_faithfulness_items_use_claim_audit() -> None:
    passage = "Customers may cancel their subscription at any time before the renewal date."
    quote = "may cancel their subscription at any time before the renewal date"
    items = [
        cal.CalibrationItem(context=passage, answer="Customers cannot cancel their subscription "
                            "before renewal.", label="incorrect"),
        cal.CalibrationItem(context=passage, answer="You may cancel your subscription any time "
                            "before renewal.", label="correct"),
    ]
    script = Scripted(claims={"cannot cancel": ("contradicted", quote),
                              "may cancel": ("supported", quote)})
    with fake_server(script) as url:
        rec = cal.calibrate(items, judge_at(url))
    assert rec.members[0].by_kind["faithfulness"].model_dump() == {
        "tp": 1, "fn": 0, "tn": 1, "fp": 0}
    assert rec.agreement == 1.0


def test_abstentions_are_excluded_not_counted_as_agreement() -> None:
    items, _ = labelled()
    with fake_server(Scripted(raw="not json")) as url:
        rec = cal.calibrate(items, judge_at(url))
    m = rec.members[0]
    assert m.n_decided == 0 and m.n_abstain == 10 and rec.agreement is None


def test_item_validation_and_bounds() -> None:
    with pytest.raises(ValueError):
        cal.CalibrationItem(answer="a", label="correct")  # no reference or context
    with pytest.raises(ValueError):
        cal.CalibrationItem(answer="a", reference="r", label="great")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        cal.calibrate([], judge_at("http://x"))


def test_calibration_replays_offline_with_identical_result(tmp_path: Path) -> None:
    items, script = labelled()
    with fake_server(script) as url:
        live = judge_at(url)
        rec = cal.calibrate(items, live)
    path = cal.save(rec, live.calls(), tmp_path)  # server is down from here on
    assert path.is_file()
    replayed = SemanticJudge.for_replay({"models": ["gpt-4o"]}, cal.load_calls(rec.id, tmp_path))
    again = cal.calibrate(items, replayed)
    assert again.id == rec.id and again.members == rec.members
    assert cal.load_for(rec.judge_key, tmp_path) is not None
    assert cal.load_for("other-key", tmp_path) is None


def test_two_judge_calibration_reports_error_correlation() -> None:
    items, script = labelled()
    with fake_server(script) as ua, fake_server(script) as ub:  # same errors: fully correlated
        j = SemanticJudge.from_clients([("gpt-4o", client(ua, "gpt-4o")),
                                        ("claude-3-haiku", client(ub, "claude-3-haiku"))],
                                       200, IND)
        rec = cal.calibrate(items, j)
    assert rec.panel is not None and rec.panel["both_wrong"] == 2
    assert rec.panel["correlated_errors"] is True
    assert rec.panel["error_correlation"] == pytest.approx(1.0)
    assert rec.panel["n_eff"] == pytest.approx(1.0)  # identical errors: one effective judge
    assert len(rec.members) == 2 and rec.panel["kappa"] == pytest.approx(1.0)


# ---------------------------------------------------------------- gating policy
def _record(url: str, model: str = "gpt-4o") -> tuple[SemanticJudge, cal.CalibrationRecord]:
    items, _ = labelled()
    judge = judge_at(url, model)
    return judge, cal.calibrate(items, judge)


def test_gate_requires_policy_minimum_calibration_and_freshness() -> None:
    items, script = labelled()
    with fake_server(script) as url:
        judge, rec = _record(url)
    lower = rec.agreement_ci[0] if rec.agreement_ci else 0.0
    off = cal.decide_gate
    assert not off(None, 0.5, rec)["enabled"]
    assert not off(judge, None, rec)["enabled"] and "judge_min_agreement" in off(
        judge, None, rec)["reason"]
    assert not off(judge, 0.5, None)["enabled"] and "no calibration" in off(
        judge, 0.5, None)["reason"]
    assert not off(judge, lower + 0.01, rec)["enabled"] and "below" in off(
        judge, lower + 0.01, rec)["reason"]
    stale_judge = SemanticJudge.from_clients([("claude-3-haiku", client("http://x", "c"))], 5, IND)
    assert "stale" in off(stale_judge, 0.1, rec)["reason"]
    unverified = SemanticJudge.from_clients([("gpt-4o", client("http://x", "c"))], 5, None)
    assert not off(unverified, 0.1, rec)["enabled"]
    on = off(judge, lower - 0.01, rec)
    assert on["enabled"] and on["calibration_id"] == rec.id and "counts" in on


def test_gate_uses_the_weakest_member() -> None:
    items, script = labelled()
    bad = Scripted(rubric={})  # says 'incorrect' to everything: agreement 4/10
    with fake_server(script) as ua, fake_server(bad) as ub:
        j = SemanticJudge.from_clients([("gpt-4o", client(ua, "gpt-4o")),
                                        ("claude-3-haiku", client(ub, "claude-3-haiku"))],
                                       200, IND)
        rec = cal.calibrate(items, j)
    assert cal.gate_agreement(rec) == min(m.agreement_ci[0] for m in rec.members  # type: ignore[index]
                                          if m.agreement_ci)
    assert not cal.decide_gate(j, 0.5, rec)["enabled"]


# ---------------------------------------------------------------- judge-error correction
def test_judge_report_corrects_rates_only_when_gating() -> None:
    items, script = labelled()
    with fake_server(script) as url:
        judge, rec = _record(url)
    rows = [{"id": f"r{k}", "detail": {"judge": {"correctness": "incorrect" if k < 4 else
                                                 "correct"}}} for k in range(10)]
    advisory = cal.judge_report(rows, judge)
    assert advisory["gating"] is False and "corrected" not in advisory
    judge.set_gate(cal.decide_gate(judge, 0.1, rec))
    out = cal.judge_report(rows, judge)
    corr = out["corrected"]["correctness"]
    # observed 0.4; tpr = 3/4, fpr = 1/6: (0.4 - 1/6) / (0.75 - 1/6) = 0.4
    assert corr["observed_defect_rate"] == pytest.approx(0.4)
    assert corr["corrected_defect_rate"] == pytest.approx(0.4)
    assert corr["ci_low"] < 0.4 < corr["ci_high"] and corr["n_judged"] == 10
    assert "faithfulness" not in out["corrected"]  # no faithfulness verdicts in these rows


def test_status_block_marks_stale() -> None:
    items, script = labelled()
    with fake_server(script) as url:
        _, rec = _record(url)
    assert cal.status_block(None, "k") is None
    assert cal.status_block(rec, rec.judge_key)["stale"] is False  # type: ignore[index]
    block = cal.status_block(rec, "another-key")
    assert block is not None and block["stale"] is True and block["n"] == 10
