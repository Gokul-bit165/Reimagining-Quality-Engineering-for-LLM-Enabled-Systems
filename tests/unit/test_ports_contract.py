"""Contract tests every port implementation must satisfy. Fakes run them today; real
adapters (black-box HTTP, DeepEval, ...) will be parametrised into the same tests."""

import pytest
from pydantic import ValidationError

from qe.core.schemas import (
    Claim,
    ClaimState,
    DecisionRecord,
    DecisionState,
    EvidenceRef,
    VisibilityLevel,
)
from qe.ports import (
    BudgetExceededError,
    GenerationSpec,
    GeneratorPort,
    JudgePort,
    KillSwitchError,
    SandboxLimits,
    SandboxPort,
    TargetPort,
    TargetRequest,
    TracePort,
    VerifierInput,
    VerifierPort,
)
from qe.testing.fakes import (
    FakeGenerator,
    FakeJudge,
    FakeSandbox,
    FakeSubstringVerifier,
    FakeTarget,
    FakeTrace,
)


def item(text: str, evidence: str | None) -> VerifierInput:
    return VerifierInput(
        claim=Claim(claim_id="c1", text=text),
        evidence_ref=EvidenceRef(source_id="doc-1"),
        evidence_text=evidence,
    )


def test_fakes_satisfy_port_protocols() -> None:
    assert isinstance(FakeTarget(), TargetPort)
    assert isinstance(FakeTrace(), TracePort)
    assert isinstance(FakeGenerator(), GeneratorPort)
    assert isinstance(FakeSubstringVerifier(), VerifierPort)
    assert isinstance(FakeJudge(), JudgePort)
    assert isinstance(FakeSandbox(), SandboxPort)


async def test_target_is_deterministic_and_respects_want_trace() -> None:
    t = FakeTarget()
    assert t.visibility_level is VisibilityLevel.A_BLACKBOX
    a = await t.invoke(TargetRequest(input="hi"))
    b = await t.invoke(TargetRequest(input="hi"))
    assert a == b and a.spans == ()
    assert (await t.invoke(TargetRequest(input="hi", want_trace=True))).spans


async def test_generator_returns_drafts_with_oracle_source_and_stable_ids() -> None:
    spec = GenerationSpec(source_ids=("doc-1",), n=3, seed=7)
    a = await FakeGenerator().generate(spec)
    b = await FakeGenerator().generate(spec)
    assert a == b and len({c.id for c in a}) == 3
    assert all(c.validity == "unreviewed" for c in a)


async def test_missing_source_is_source_unavailable_not_pass_or_fail() -> None:
    v = await FakeSubstringVerifier().verify(item("x", None))
    assert v.state is ClaimState.SOURCE_UNAVAILABLE


async def test_deterministic_verifier_states() -> None:
    ver = FakeSubstringVerifier()
    assert (await ver.verify(item("cat", "the cat sat"))).state is ClaimState.SUPPORTED
    assert (await ver.verify(item("dog", "the cat sat"))).state is ClaimState.UNSUPPORTED


def test_verifier_input_cannot_carry_producer_rationale_or_other_verdicts() -> None:
    base = {
        "claim": Claim(claim_id="c", text="t"),
        "evidence_ref": EvidenceRef(source_id="d"),
        "evidence_text": "e",
    }
    for leak in ("rationale", "producer_reasoning", "other_verdicts", "verdicts"):
        with pytest.raises(ValidationError):
            VerifierInput(**base, **{leak: "leaked"})  # type: ignore[arg-type]


def test_judge_declares_a_model_family() -> None:
    assert FakeJudge().model.family


async def test_sandbox_enforces_budget_and_kill_switch() -> None:
    async with FakeSandbox().session(SandboxLimits(max_calls=2, max_tokens=100)) as s:
        s.charge(calls=1, tokens=40)
        s.charge(calls=1, tokens=40)
        with pytest.raises(BudgetExceededError):
            s.charge(calls=1)
    async with FakeSandbox().session(SandboxLimits(max_calls=10, max_tokens=100)) as s:
        with pytest.raises(BudgetExceededError):
            s.charge(tokens=101)
        s.kill()
        with pytest.raises(KillSwitchError):
            s.charge()


def test_release_decision_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        DecisionRecord(decision=DecisionState.RELEASE, policy_version="p1", evidence_ids=())
    DecisionRecord(decision=DecisionState.INSUFFICIENT_EVIDENCE, policy_version="p1",
                   evidence_ids=())


def test_content_ids_are_stable() -> None:
    c = Claim(claim_id="c", text="t")
    assert c.cid() == Claim(claim_id="c", text="t").cid()
    assert c.cid() != Claim(claim_id="c", text="u").cid()
