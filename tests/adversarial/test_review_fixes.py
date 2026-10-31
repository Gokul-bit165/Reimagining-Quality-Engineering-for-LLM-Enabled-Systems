"""Regression tests for findings in docs/reviews/M0-core-review.md."""

import asyncio
import socket
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from qe.core.events import DETERMINISTIC_ONLY, Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger, compute_entry_hash
from qe.core.schemas import (
    AdjudicatedVerdict,
    Claim,
    ClaimState,
    DecisionRecord,
    DecisionState,
    EvidenceRef,
    MethodClass,
    RegressionCase,
    Verdict,
)
from qe.exec.egress import EgressBlockedError, EgressGuard
from qe.exec.sandbox import LocalSandbox
from qe.ports import SandboxLimits, VerifierInput
from qe.testing.fakes import FakeSandbox


def ev(key: str, t: EventType = EventType.RUN_RECORDED, **kw: object) -> Event:
    base = {"key": key, "type": t, "producer": "p", "producer_kind": ProducerKind.DETERMINISTIC,
            "payload": {"i": 1}}
    return Event(**{**base, **kw})  # type: ignore[arg-type]


# C2: key column must be covered by verification
def test_key_column_tampering_detected(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    ledger = SQLiteLedger(p)
    for k in ("k0", "k1", "k2"):
        ledger.append(ev(k))
    ledger.close()
    c = sqlite3.connect(p)
    c.execute("UPDATE ledger SET key='zzz' WHERE seq=1")
    c.commit()
    c.close()
    report = SQLiteLedger(p).verify()
    assert not report.ok and report.first_bad_seq == 1


# H1: stored rows are re-checked against write permissions
def test_forged_llm_evidence_row_with_valid_chain_is_flagged(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    ledger = SQLiteLedger(p)
    ledger.append(ev("k0"))
    head = ledger.head()
    ledger.close()
    forged = ev("k1", EventType.EVIDENCE_RECORDED, producer_kind=ProducerKind.LLM_AGENT)
    js = forged.canonical()
    c = sqlite3.connect(p)
    digest = compute_entry_hash(1, head, js)
    c.execute("INSERT INTO ledger VALUES (1,'k1',?,?,?)", (head, digest, js))
    c.commit()
    c.close()
    report = SQLiteLedger(p).verify()
    assert not report.ok and report.first_bad_seq == 1


# H2: producer kinds can be pinned by a registry
def test_producer_registry_pins_kinds() -> None:
    ledger = SQLiteLedger(":memory:", producer_kinds={"exec": ProducerKind.DETERMINISTIC,
                                                      "authors": ProducerKind.LLM_AGENT})
    ledger.append(ev("a", producer="exec"))
    with pytest.raises(PermissionError):
        ledger.append(ev("b", EventType.DECISION_ISSUED, producer="authors"))  # kind mismatch
    with pytest.raises(PermissionError):
        ledger.append(ev("c", producer="unknown-service"))
    with pytest.raises(PermissionError):
        # LLM_AGENT may not write RUN_RECORDED even when registered
        ledger.append(ev("d", producer="authors", producer_kind=ProducerKind.LLM_AGENT))


# H3: unvalidated events are rejected
def test_model_construct_bogus_event_rejected() -> None:
    ledger = SQLiteLedger(":memory:")
    bogus = Event.model_construct(key="x", type="bogus_type", producer="p",
                                  producer_kind=ProducerKind.DETERMINISTIC, payload={})
    with pytest.raises((ValidationError, PermissionError, ValueError)):
        ledger.append(bogus)
    assert len(ledger) == 0


# surviving mutants: every deterministic-only type is protected
@pytest.mark.parametrize("t", sorted(DETERMINISTIC_ONLY))
def test_every_deterministic_only_type_rejects_llm(t: EventType) -> None:
    with pytest.raises(PermissionError):
        SQLiteLedger(":memory:").append(ev("k", t, producer_kind=ProducerKind.LLM_AGENT))


def test_verify_anchor_and_gap_checks() -> None:
    ledger = SQLiteLedger(":memory:")
    ledger.append(ev("a"))
    assert ledger.verify(expected_len=1).ok and not ledger.verify(expected_len=2).ok
    assert ledger.verify(expected_head=ledger.head()).ok
    assert not ledger.verify(expected_head="f" * 64).ok


# H4: subclassed Claim cannot smuggle fields
def test_verifier_input_rejects_subclass_covert_channel() -> None:
    class Sneaky(Claim):
        rationale: str = "producer says trust me"

    with pytest.raises(ValidationError):
        VerifierInput(claim=Sneaky(claim_id="c", text="t"),
                      evidence_ref=EvidenceRef(source_id="d"), evidence_text="e")


# C1 / H5: egress guard
def test_asyncio_connect_is_blocked() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    async def go() -> None:
        loop = asyncio.get_running_loop()
        with pytest.raises(EgressBlockedError):
            await loop.create_connection(asyncio.Protocol, "127.0.0.1", port)
        s = socket.socket()
        s.setblocking(False)
        with pytest.raises(EgressBlockedError):
            await loop.sock_connect(s, ("127.0.0.1", port))
        s.close()

    try:
        with EgressGuard(allowlist=()) as g:
            asyncio.run(go())
        assert any("127.0.0.1" in a for a in g.attempts)
    finally:
        srv.close()


def test_other_resolvers_and_udp_blocked() -> None:
    with EgressGuard(allowlist=()):
        with pytest.raises(EgressBlockedError):
            socket.gethostbyname("example.com")
        with pytest.raises(EgressBlockedError):
            socket.getnameinfo(("8.8.8.8", 53), 0)
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with pytest.raises(EgressBlockedError):
            u.sendto(b"x", ("127.0.0.1", 9))
        u.close()


def test_overlapping_guards_stay_blocking_and_restore_cleanly() -> None:
    original = (socket.socket.connect, socket.getaddrinfo)
    a = EgressGuard(allowlist=())
    b = EgressGuard(allowlist=())
    a.__enter__()
    b.__enter__()
    a.__exit__(None, None, None)  # non-LIFO exit
    with pytest.raises(EgressBlockedError):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
    b.__exit__(None, None, None)
    assert (socket.socket.connect, socket.getaddrinfo) == original


def test_exit_restores_connect_ex_and_sendto() -> None:
    before = (socket.socket.connect_ex, socket.socket.sendto)
    with EgressGuard(allowlist=()):
        pass
    assert (socket.socket.connect_ex, socket.socket.sendto) == before


# budget hardening
@pytest.mark.parametrize("make", [LocalSandbox, FakeSandbox])
async def test_budget_rejects_negative_charges_and_limits(make: type) -> None:
    with pytest.raises(ValidationError):
        SandboxLimits(max_calls=-1, max_tokens=1)
    async with make().session(SandboxLimits(max_calls=1, max_tokens=10)) as s:
        with pytest.raises(ValueError):
            s.charge(calls=-1000)
        with pytest.raises(ValueError):
            s.charge(tokens=-5)
        s.charge(tokens=10)
        from qe.ports import BudgetExceededError
        with pytest.raises(BudgetExceededError):
            s.charge(calls=0, tokens=1)  # token budget enforced


# schema holes
def test_schema_constraints() -> None:
    with pytest.raises(ValidationError):
        Verdict(claim_id="c", method="m", method_class=MethodClass.DETERMINISTIC,
                method_version="1", state=ClaimState.SUPPORTED, score=float("nan"))
    with pytest.raises(ValidationError):
        AdjudicatedVerdict(claim_id="c", state=ClaimState.SUPPORTED, confidence=7.5)
    with pytest.raises(ValidationError):
        AdjudicatedVerdict(claim_id="c", state=ClaimState.SUPPORTED, n_eff=-1.0)
    with pytest.raises(ValidationError):
        RegressionCase(case_id="r", minimized_from="t", pass_k_admission=(5, 2))
    with pytest.raises(ValidationError):
        DecisionRecord(decision=DecisionState.RELEASE, policy_version="p", evidence_ids=("",))
    with pytest.raises(ValidationError):
        DecisionRecord(decision=DecisionState.CONDITIONAL, policy_version="p",
                       evidence_ids=("e1",))
    with pytest.raises(ValidationError):
        DecisionRecord(decision=DecisionState.REJECT, policy_version="p", evidence_ids=())


# surviving mutants: telemetry values, immutability, seed sensitivity
@pytest.mark.parametrize(
    ("flag", "value"),
    [("DEEPEVAL_TELEMETRY_OPT_OUT", "1"), ("RAGAS_DO_NOT_TRACK", "true"), ("DO_NOT_TRACK", "1"),
     ("HF_HUB_DISABLE_TELEMETRY", "1"), ("ANONYMIZED_TELEMETRY", "False")],
)
def test_each_telemetry_flag_has_exact_value_in_process(flag: str, value: str) -> None:
    import os
    assert os.environ[flag] == value


def test_event_and_models_are_immutable_and_forbid_extras() -> None:
    e = ev("k")
    with pytest.raises(ValidationError):
        e.key = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Event(key="k", type=EventType.RUN_RECORDED, producer="p",
              producer_kind=ProducerKind.DETERMINISTIC, payload={}, extra="x")  # type: ignore[call-arg]
    c = Claim(claim_id="c", text="t")
    with pytest.raises(ValidationError):
        c.text = "u"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Claim(claim_id="c", text="t", rationale="x")  # type: ignore[call-arg]
    vi = VerifierInput(claim=c, evidence_ref=EvidenceRef(source_id="d"), evidence_text="e")
    with pytest.raises(ValidationError):
        vi.evidence_text = "z"  # type: ignore[misc]


async def test_fake_generator_depends_on_seed() -> None:
    from qe.ports import GenerationSpec
    from qe.testing.fakes import FakeGenerator
    a = await FakeGenerator().generate(GenerationSpec(source_ids=("d",), n=2, seed=1))
    b = await FakeGenerator().generate(GenerationSpec(source_ids=("d",), n=2, seed=2))
    assert {c.id for c in a}.isdisjoint({c.id for c in b})
