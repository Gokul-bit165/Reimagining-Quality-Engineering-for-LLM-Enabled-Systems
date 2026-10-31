import pytest
from pydantic import ValidationError

from qe.core.schemas import DecisionState, Policy
from qe.policy.engine import MetricEvidence, decide


def pol(**kw: object) -> Policy:
    base = dict(policy_id="ex", version="1", loss_matrix={}, required_evidence=("fabrication", "tool_misuse"),
                risk_appetite={"fabrication": 0.1, "tool_misuse": 0.05}, example_only=True)
    return Policy(**{**base, **kw})  # type: ignore[arg-type]


def ev(name: str, k: int, n: int, lo: float, hi: float) -> MetricEvidence:
    return MetricEvidence(name=name, failures=k, trials=n, lower=lo, upper=hi, evidence_ids=("e1",))


def test_missing_required_evidence_is_insufficient() -> None:
    d = decide(pol(), [ev("fabrication", 0, 100, 0, 0.03)])
    assert d.decision is DecisionState.INSUFFICIENT_EVIDENCE and "tool_misuse" in " ".join(d.conditions)


def test_all_upper_bounds_within_appetite_releases() -> None:
    d = decide(pol(), [ev("fabrication", 0, 100, 0, 0.03), ev("tool_misuse", 0, 100, 0, 0.03)])
    assert d.decision is DecisionState.RELEASE and d.evidence_ids


def test_lower_bound_above_appetite_rejects() -> None:
    d = decide(pol(), [ev("fabrication", 40, 100, 0.3, 0.5), ev("tool_misuse", 0, 100, 0, 0.03)])
    assert d.decision is DecisionState.REJECT


def test_interval_straddling_appetite_is_not_release() -> None:
    d = decide(pol(), [ev("fabrication", 5, 50, 0.03, 0.22), ev("tool_misuse", 0, 100, 0, 0.03)])
    assert d.decision is DecisionState.INSUFFICIENT_EVIDENCE


def test_example_policy_is_labelled() -> None:
    d = decide(pol(), [])
    assert any("EXAMPLE" in c for c in d.conditions)


def test_policy_without_appetite_for_required_metric_is_invalid() -> None:
    with pytest.raises((ValidationError, ValueError)):
        decide(pol(risk_appetite={}), [])
