import pytest

from qe.core.schemas import ConditionalRule, DecisionState, Policy
from qe.policy.engine import MetricEvidence, decide
from qe.policy.expected_loss import decide_expected_loss, p_unacceptable

LOSS = {
    "RELEASE": {"acceptable": 0.0, "unacceptable": 100.0},
    "REJECT": {"acceptable": 10.0, "unacceptable": 0.0},
    "INSUFFICIENT_EVIDENCE": {"acceptable": 4.0, "unacceptable": 4.0},
}


def pol(**kw: object) -> Policy:
    base: dict[str, object] = dict(
        policy_id="ex", version="1", loss_matrix=LOSS, required_evidence=("fab",),
        risk_appetite={"fab": 0.1}, example_only=True)
    return Policy(**{**base, **kw})  # type: ignore[arg-type]


def ev(k: int, n: int, lo: float, hi: float, name: str = "fab") -> MetricEvidence:
    return MetricEvidence(name=name, failures=k, trials=n, lower=lo, upper=hi, evidence_ids=("e1",))


RULE = ConditionalRule(metric="fab", max_failure_rate=0.2, condition="ship behind kill switch")


def test_conditional_only_from_declared_rule() -> None:
    straddle = ev(8, 100, 0.04, 0.15)
    assert decide(pol(), [straddle]).decision is DecisionState.INSUFFICIENT_EVIDENCE
    d = decide(pol(conditional_rules=(RULE,)), [straddle])
    assert d.decision is DecisionState.CONDITIONAL
    assert "CONDITION: ship behind kill switch" in d.conditions


def test_conditional_rule_ceiling_is_respected() -> None:
    assert decide(pol(conditional_rules=(RULE,)), [ev(8, 100, 0.04, 0.25)]).decision \
        is DecisionState.INSUFFICIENT_EVIDENCE
    assert decide(pol(conditional_rules=(RULE,)), [ev(30, 100, 0.25, 0.4)]).decision \
        is DecisionState.REJECT
    # a violated metric above appetite but under the ceiling is tolerated only via the rule
    assert decide(pol(conditional_rules=(RULE,)), [ev(14, 100, 0.12, 0.18)]).decision \
        is DecisionState.CONDITIONAL
    assert decide(pol(), [ev(14, 100, 0.12, 0.18)]).decision is DecisionState.REJECT


def test_conditional_does_not_mask_a_violation_or_missing_evidence() -> None:
    p = pol(required_evidence=("fab", "tool"), risk_appetite={"fab": 0.1, "tool": 0.1},
            conditional_rules=(RULE,))
    d = decide(p, [ev(8, 100, 0.04, 0.15)])
    assert d.decision is DecisionState.INSUFFICIENT_EVIDENCE
    d = decide(p, [ev(8, 100, 0.04, 0.15), ev(40, 100, 0.3, 0.5, "tool")])
    assert d.decision is DecisionState.REJECT


def test_no_rules_never_conditional() -> None:
    for hi in (0.05, 0.15, 0.5):
        assert decide(pol(), [ev(1, 10, 0.0, hi)]).decision is not DecisionState.CONDITIONAL


def test_expected_loss_clear_cases() -> None:
    d, r = decide_expected_loss(pol(), [ev(0, 500, 0.0, 0.01)])
    assert d.decision is DecisionState.RELEASE and r is not None and r.p_unacceptable < 1e-6
    d, r = decide_expected_loss(pol(), [ev(200, 500, 0.3, 0.5)])
    assert d.decision is DecisionState.REJECT and r is not None and r.p_unacceptable > 0.999


def test_expected_loss_matches_hand_calculation() -> None:
    d, r = decide_expected_loss(pol(), [ev(5, 50, 0.03, 0.2)])
    assert r is not None
    p = p_unacceptable(pol(), [ev(5, 50, 0.03, 0.2)])
    assert p is not None and r.p_unacceptable == pytest.approx(p)
    assert r.expected_loss["RELEASE"] == pytest.approx(100.0 * p)
    assert r.expected_loss["REJECT"] == pytest.approx(10.0 * (1 - p))
    assert r.expected_loss["INSUFFICIENT_EVIDENCE"] == pytest.approx(4.0)
    best = min(r.expected_loss, key=lambda k: r.expected_loss[k])
    assert d.decision.value == best


def test_sensitivity_flags_unstable_decision() -> None:
    # borderline posterior: scaling the unacceptable-world loss flips RELEASE <-> something else
    _, r = decide_expected_loss(pol(), [ev(5, 50, 0.03, 0.2)])
    assert r is not None and not r.stable
    assert {row.scale for row in r.sensitivity} >= {0.1, 1.0, 10.0}
    d, r2 = decide_expected_loss(pol(), [ev(0, 2000, 0.0, 0.001)])
    assert r2 is not None and r2.stable and d.decision is DecisionState.RELEASE
    assert any("UNSTABLE" in c for c in decide_expected_loss(pol(), [ev(5, 50, 0.03, 0.2)])[0].conditions)


def test_expected_loss_missing_evidence_is_insufficient() -> None:
    d, r = decide_expected_loss(pol(), [])
    assert d.decision is DecisionState.INSUFFICIENT_EVIDENCE and r is None


def test_expected_loss_multi_metric_uses_product() -> None:
    p = pol(required_evidence=("a", "b"), risk_appetite={"a": 0.1, "b": 0.1})
    one = p_unacceptable(p, [ev(5, 50, 0, 1, "a"), ev(0, 5000, 0, 1, "b")])
    two = p_unacceptable(p, [ev(5, 50, 0, 1, "a"), ev(5, 50, 0, 1, "b")])
    assert one is not None and two is not None and two > one > 0


def test_expected_loss_conditional_candidate_needs_declared_rules() -> None:
    loss = {**LOSS, "CONDITIONAL": {"acceptable": 1.0, "unacceptable": 20.0}}
    e = [ev(7, 60, 0.05, 0.22)]
    d_none, r_none = decide_expected_loss(pol(loss_matrix=loss), e)
    assert r_none is not None and "CONDITIONAL" not in r_none.expected_loss
    d_rule, r_rule = decide_expected_loss(pol(loss_matrix=loss, conditional_rules=(RULE,)), e)
    assert r_rule is not None and "CONDITIONAL" in r_rule.expected_loss
    assert d_none.decision is not DecisionState.CONDITIONAL
    if d_rule.decision is DecisionState.CONDITIONAL:
        assert "CONDITION: ship behind kill switch" in d_rule.conditions


def test_conditional_chosen_by_loss_attaches_condition() -> None:
    loss = {
        "RELEASE": {"acceptable": 0.0, "unacceptable": 100.0},
        "REJECT": {"acceptable": 50.0, "unacceptable": 0.0},
        "CONDITIONAL": {"acceptable": 1.0, "unacceptable": 10.0},
    }
    d, _ = decide_expected_loss(pol(loss_matrix=loss, conditional_rules=(RULE,)),
                                [ev(5, 50, 0.03, 0.2)])
    assert d.decision is DecisionState.CONDITIONAL
    assert "CONDITION: ship behind kill switch" in d.conditions


def test_ties_resolve_conservatively() -> None:
    tie = {"RELEASE": {"acceptable": 5.0, "unacceptable": 5.0},
           "REJECT": {"acceptable": 5.0, "unacceptable": 5.0}}
    d, _ = decide_expected_loss(pol(loss_matrix=tie), [ev(0, 100, 0, 0.03)])
    assert d.decision is DecisionState.REJECT


def test_loss_matrix_validation() -> None:
    e = [ev(0, 100, 0, 0.03)]
    with pytest.raises(ValueError, match="unknown decision"):
        decide_expected_loss(pol(loss_matrix={"MAYBE": {"acceptable": 0, "unacceptable": 0}}), e)
    with pytest.raises(ValueError, match="needs"):
        decide_expected_loss(pol(loss_matrix={**LOSS, "REJECT": {"acceptable": 1.0}}), e)
    with pytest.raises(ValueError, match="non-negative"):
        decide_expected_loss(pol(loss_matrix={**LOSS, "REJECT": {"acceptable": -1.0,
                                                                  "unacceptable": 0.0}}), e)
    with pytest.raises(ValueError, match="must define"):
        decide_expected_loss(pol(loss_matrix={"RELEASE": LOSS["RELEASE"]}), e)
    with pytest.raises(ValueError, match="scales"):
        decide_expected_loss(pol(), e, scales=(0.5, 2.0))
    with pytest.raises(ValueError, match="scales"):
        decide_expected_loss(pol(), e, scales=(-1.0, 1.0))


def test_empty_loss_matrix_is_rejected_for_loss_path_only() -> None:
    with pytest.raises(ValueError):
        decide_expected_loss(pol(loss_matrix={}), [ev(0, 100, 0, 0.03)])
    assert decide(pol(loss_matrix={}), [ev(0, 100, 0, 0.03)]).decision is DecisionState.RELEASE
