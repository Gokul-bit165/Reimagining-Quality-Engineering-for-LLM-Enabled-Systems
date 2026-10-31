import json
import math
import random
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from qe.cli.main import app
from qe.core.schemas import Claim, ClaimState, EvidenceRef, MethodClass, ModelRef, Verdict
from qe.ports import VerifierInput
from qe.testing.fakes import FakeSubstringVerifier
from qe.verify.aggregate import (
    Aggregator,
    PanelIndependenceError,
    check_panel,
    error_vectors,
    panel_report,
)
from qe.verify.conformal import LABELS, SplitConformal, nonconformity, vote_probs
from qe.verify.fake_judge import FakeJudge

S, C, U = ClaimState.SUPPORTED, ClaimState.CONTRADICTED, ClaimState.UNSUPPORTED


def vi(text: str = "c", ev: str | None = "e") -> VerifierInput:
    return VerifierInput(claim=Claim(claim_id="c1", text=text),
                         evidence_ref=EvidenceRef(source_id="s"), evidence_text=ev)


def fixed(name: str, family: str, state: ClaimState) -> FakeJudge:
    return FakeJudge(name=name, family=family, answer=lambda _i: state)


class Exact:
    """Deterministic verifier returning a fixed state."""

    version = "1"
    model: ModelRef | None = None

    def __init__(self, name: str, state: ClaimState,
                 klass: MethodClass = MethodClass.DETERMINISTIC) -> None:
        self.name, self._s, self.method_class = name, state, klass

    async def verify(self, item: VerifierInput) -> Verdict:
        return Verdict(claim_id=item.claim.claim_id, method=self.name,
                       method_class=self.method_class, method_version="1", state=self._s)


class Crashy(Exact):
    async def verify(self, item: VerifierInput) -> Verdict:
        raise RuntimeError("boom")


# ---- independence ------------------------------------------------------------------------
def test_panel_with_author_family_is_rejected() -> None:
    with pytest.raises(PanelIndependenceError, match="author family"):
        Aggregator([fixed("a", "nvidia", S), fixed("b", "meta", S)], author_families={"NVIDIA"})
    Aggregator([fixed("a", "meta", S)], author_families={"nvidia"})  # different family is fine


def test_panel_validation() -> None:
    with pytest.raises(PanelIndependenceError, match="empty"):
        check_panel([], {"x"})
    with pytest.raises(PanelIndependenceError, match="unique"):
        check_panel([fixed("a", "f1", S), fixed("a", "f2", S)], set())
    nofam = FakeJudge(name="n", family="")
    with pytest.raises(PanelIndependenceError, match="declare a family"):
        check_panel([nofam], set())

    class ModelLess(Exact):
        pass

    with pytest.raises(PanelIndependenceError, match="declare a family"):
        check_panel([ModelLess("m", S, MethodClass.LLM_JUDGE)], set())
    check_panel([FakeSubstringVerifier()], {"nvidia"})  # non-model verifiers have no family


# ---- isolation ---------------------------------------------------------------------------
async def test_only_verifier_input_is_accepted() -> None:
    agg = Aggregator([fixed("a", "f1", S)], author_families=set())

    class Sub(VerifierInput):
        pass

    with pytest.raises(TypeError, match="information isolation"):
        await agg.adjudicate({"claim": "x", "rationale": "producer says yes"})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        await agg.adjudicate(Sub(claim=Claim(claim_id="c", text="t"),  # subclass: covert channel
                                 evidence_ref=EvidenceRef(source_id="s"), evidence_text="e"))


async def test_every_verifier_receives_the_identical_input_object() -> None:
    seen: list[Any] = []

    class Spy(FakeJudge):
        async def verify(self, item: VerifierInput) -> Verdict:
            seen.append(item)
            return await super().verify(item)

    agg = Aggregator([Spy("a", "f1"), Spy("b", "f2")], author_families=set())
    item = vi("Customers", "Customers may")
    await agg.adjudicate(item)
    assert len(seen) == 2 and all(s is item for s in seen)


# ---- adjudication ------------------------------------------------------------------------
async def test_majority_vote_and_confidence() -> None:
    agg = Aggregator([fixed("a", "f1", S), fixed("b", "f2", S), fixed("c", "f3", C)],
                     author_families=set(), n_eff=2.1)
    r = await agg.adjudicate(vi())
    assert r.state is S and r.confidence == pytest.approx(2 / 3)
    assert r.n_eff == 2.1 and r.layers_fired == ("vote",) and len(r.verdict_ids) == 3


async def test_tie_and_no_votes_abstain() -> None:
    tie = Aggregator([fixed("a", "f1", S), fixed("b", "f2", C)], author_families=set())
    assert (await tie.adjudicate(vi())).state is ClaimState.ABSTAIN
    none = Aggregator([Crashy("x", S)], author_families=set())
    r = await none.adjudicate(vi())  # a crashed verifier is an abstention
    assert r.state is ClaimState.ABSTAIN and r.layers_fired == ("no_votes",)


async def test_deterministic_overrides_neural_for_exact_check_only() -> None:
    panel = [Exact("det", C), fixed("a", "f1", S), fixed("b", "f2", S)]
    agg = Aggregator(panel, author_families=set())
    exact = await agg.adjudicate(vi(), exact_check=True)
    assert exact.state is C and exact.layers_fired == ("deterministic",) and exact.confidence == 1.0
    assert (await agg.adjudicate(vi(), exact_check=False)).state is S


async def test_exact_check_falls_back_when_deterministic_cannot_decide() -> None:
    panel = [Exact("det", ClaimState.UNVERIFIABLE), fixed("a", "f1", S)]
    r = await Aggregator(panel, author_families=set()).adjudicate(vi(), exact_check=True)
    assert r.state is S and r.layers_fired == ("vote",)


async def test_conflicting_deterministic_verdicts_abstain() -> None:
    panel = [Exact("d1", S), Exact("d2", C, MethodClass.OUTCOME_ORACLE), fixed("a", "f1", S)]
    r = await Aggregator(panel, author_families=set()).adjudicate(vi(), exact_check=True)
    assert r.state is ClaimState.ABSTAIN and "conflict" in r.layers_fired


async def test_conformal_abstention_layer() -> None:
    cal = [({S: 1.0}, S)] * 15 + [({S: 1 / 3, C: 2 / 3}, S)] * 10  # qhat = 1 - 1/3
    cp = SplitConformal.fit(cal, alpha=0.1)
    agg = Aggregator([fixed("a", "f1", S), fixed("b", "f2", C)], author_families=set(),
                     conformal=cp)
    # tie -> abstain before conformal; use 3 judges for a 2-1 split (p=0.667)
    agg3 = Aggregator([fixed("a", "f1", S), fixed("b", "f2", S), fixed("c", "f3", C)],
                      author_families=set(), conformal=cp)
    assert (await agg.adjudicate(vi())).state is ClaimState.ABSTAIN
    r = await agg3.adjudicate(vi())
    assert r.state is ClaimState.ABSTAIN and "conformal_abstain" in r.layers_fired
    unanimous = Aggregator([fixed("a", "f1", S), fixed("b", "f2", S)], author_families=set(),
                           conformal=cp)
    r = await unanimous.adjudicate(vi())
    assert r.state is S and r.layers_fired == ("vote", "conformal")


# ---- conformal ---------------------------------------------------------------------------
def test_vote_probs_ignores_abstentions_and_weights() -> None:
    def v(m: str, s: ClaimState) -> Verdict:
        return Verdict(claim_id="c", method=m, method_class=MethodClass.LLM_JUDGE,
                       method_version="1", state=s)

    vs = [v("a", S), v("b", C), v("c", ClaimState.ABSTAIN)]
    assert vote_probs(vs) == {S: 0.5, C: 0.5}
    assert vote_probs(vs, {"a": 3.0}) == {S: 0.75, C: 0.25}
    assert vote_probs([v("a", ClaimState.ABSTAIN)]) == {}
    assert nonconformity({S: 0.7}, S) == pytest.approx(0.3) and nonconformity({S: 0.7}, C) == 1.0


def test_split_conformal_quantile_rank() -> None:
    # scores 0.0 x 9 and 1.0 x 1; n=10, alpha=0.2 -> rank ceil(11*0.8)=9 -> qhat 0.0
    cal = [({S: 1.0}, S)] * 9 + [({C: 1.0}, S)]
    assert SplitConformal.fit(cal, 0.2).qhat == 0.0
    # alpha=0.05 -> rank ceil(11*0.95)=11 > n -> infinite (set = everything)
    cp = SplitConformal.fit(cal, 0.05)
    assert math.isinf(cp.qhat) and cp.prediction_set({S: 1.0}) == frozenset(LABELS)
    with pytest.raises(ValueError):
        SplitConformal.fit([], 0.1)
    with pytest.raises(ValueError):
        SplitConformal.fit(cal, 1.0)
    with pytest.raises(ValueError):
        cp.coverage([])


def test_conformal_marginal_coverage_on_simulated_data() -> None:
    rng = random.Random(4)

    def draw() -> tuple[dict[ClaimState, float], ClaimState]:
        truth = S if rng.random() < 0.6 else C
        noisy = rng.random() < 0.25  # panel vote split on 25% of items
        p = rng.uniform(0.5, 0.9) if noisy else 1.0
        other = C if truth is S else S
        return ({truth: p, other: 1.0 - p} if noisy else {truth: 1.0}), truth

    cal = [draw() for _ in range(400)]
    cp = SplitConformal.fit(cal, alpha=0.1)
    test = [draw() for _ in range(2000)]
    assert cp.coverage(test) >= 0.87  # nominal 0.90; sampling slack
    assert cp.answers({}) is None  # empty votes -> full set -> abstain


# ---- panel report ------------------------------------------------------------------------
def test_panel_report_known_values() -> None:
    truth = [S, S, C, C, S, C]
    wrong = {"a": [C, C, S, S, S, C], "b": [C, C, S, S, S, C], "c": [S, S, C, C, S, C]}
    r = panel_report(wrong, truth)
    assert r.error_rates == (4 / 6, 4 / 6, 0.0)
    assert r.error_correlation[0][1] == pytest.approx(1.0) and r.error_correlation[0][2] == 0.0
    assert 1.0 <= r.n_eff < 3.0 and r.n_items == 6
    with pytest.raises(ValueError):
        panel_report({"a": [S]}, truth)
    with pytest.raises(ValueError):
        panel_report({}, [])


def test_error_vectors_mark_abstentions() -> None:
    v = error_vectors({"a": [S, ClaimState.ABSTAIN, C]}, [S, S, S])
    assert v["a"] == [False, None, True]
    r = panel_report({"a": [ClaimState.ABSTAIN, ClaimState.ABSTAIN], "b": [S, S]}, [S, S])
    assert r.error_rates[0] is None and r.abstain_rates[0] == 1.0


# ---- CLI ---------------------------------------------------------------------------------
def _rows(n: int) -> str:
    rng = random.Random(0)
    lines = []
    for _ in range(n):
        truth = S if rng.random() < 0.5 else C
        flip = lambda s: C if s is S else S  # noqa: E731
        a = truth if rng.random() < 0.85 else flip(truth)
        b = truth if rng.random() < 0.85 else flip(truth)
        lines.append(json.dumps({"truth": truth.value, "verdicts": {"a": a.value, "b": b.value}}))
    return "\n".join(lines) + "\n"


def test_calibrate_cli_outputs_report(tmp_path: Path) -> None:
    data = tmp_path / "cal.jsonl"
    data.write_text(_rows(200), encoding="utf-8")
    out = tmp_path / "out.json"
    res = CliRunner().invoke(app, ["calibrate", str(data), "--alpha", "0.1", "--holdout", "0.25",
                                   "--out", str(out)])
    assert res.exit_code == 0, res.output
    j = json.loads(out.read_text(encoding="utf-8"))
    assert j["n_calibration"] == 150 and j["n_heldout"] == 50
    assert j["panel"]["verifiers"] == ["a", "b"] and 1.0 <= j["panel"]["n_eff"] <= 2.0
    assert 0.0 <= j["heldout_coverage"] <= 1.0 and "NCM" in j["ncm"]
    res = CliRunner().invoke(app, ["calibrate", str(data)])
    assert res.exit_code == 0 and json.loads(res.output)["alpha"] == 0.1


def test_calibrate_cli_error_paths(tmp_path: Path) -> None:
    r = CliRunner()
    assert r.invoke(app, ["calibrate", str(tmp_path / "nope.jsonl")]).exit_code == 2
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"truth": "nonsense", "verdicts": {}}\n', encoding="utf-8")
    res = r.invoke(app, ["calibrate", str(bad)])
    assert res.exit_code == 2 and "invalid row" in res.output
    bad.write_text("", encoding="utf-8")
    assert r.invoke(app, ["calibrate", str(bad)]).exit_code == 2
    bad.write_text('{"truth":"supported","verdicts":{"a":"supported"}}\n'
                   '{"truth":"supported","verdicts":{"b":"supported"}}\n', encoding="utf-8")
    assert "same set" in r.invoke(app, ["calibrate", str(bad)]).output
    good = tmp_path / "g.jsonl"
    good.write_text(_rows(5), encoding="utf-8")
    assert r.invoke(app, ["calibrate", str(good), "--holdout", "1.0"]).exit_code == 2
