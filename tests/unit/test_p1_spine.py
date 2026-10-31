"""Person 1 (spine & reporting) tests: access recording, replay, hand-off API, goldens."""

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from qe.access.blackbox_http import record_access_profile
from qe.cli.main import app
from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.replay import ReplayMismatchError, replay, verify_replay
from qe.core.schemas import AccessProfile, ClaimState, MethodClass, Policy, Verdict, VisibilityLevel
from qe.report.evidence_pack import build_evidence_pack, build_pack, render_json, render_markdown

POLICY = Policy(policy_id="ex", version="1", loss_matrix={}, required_evidence=("m",),
                risk_appetite={"m": 0.1}, example_only=True)
runner = CliRunner()


def _det(key: str, etype: EventType, payload: dict[str, Any]) -> Event:
    return Event(key=key, type=etype, producer="t", producer_kind=ProducerKind.DETERMINISTIC,
                 payload=payload)


def _fixture_ledger(path: str | Path = ":memory:") -> SQLiteLedger:
    ledger = SQLiteLedger(path)
    record_access_profile(ledger, AccessProfile(
        target="demo", visibility_level=VisibilityLevel.A_BLACKBOX, capabilities=("health",)))
    for i in range(6):
        ledger.append(_det(f"run:c{i}:0", EventType.RUN_RECORDED, {
            "visibility_level": "A", "test_case_id": f"c{i}", "error": None}))
        state = ClaimState.CONTRADICTED if i < 2 else ClaimState.SUPPORTED
        ledger.append(_det(f"verdict:c{i}", EventType.VERDICT_ISSUED, {
            "metric": "m", "case_id": f"c{i}",
            "verdict": Verdict(claim_id=f"c{i}", method="x", method_class=MethodClass.DETERMINISTIC,
                               method_version="1", state=state).model_dump(mode="json")}))
    return ledger


def test_access_profile_recorded_in_ledger_and_idempotent() -> None:
    ledger = SQLiteLedger(":memory:")
    prof = AccessProfile(target="t", visibility_level=VisibilityLevel.B_SDK,
                         capabilities=("health", "trace_in_response"))
    record_access_profile(ledger, prof)
    record_access_profile(ledger, prof)  # idempotent
    inv = [e for e in ledger.entries() if e.event.type is EventType.CAPABILITY_INVENTORY]
    assert len(inv) == 1 and inv[0].event.payload["visibility_level"] == "B"
    assert build_pack(ledger, POLICY)["access"]["profiles"][0]["visibility_level"] == "B"


def test_replay_is_byte_identical_across_copies(tmp_path: Path) -> None:
    src = tmp_path / "l.sqlite"
    _fixture_ledger(src).close()
    copy = tmp_path / "c.sqlite"
    shutil.copy(src, copy)
    a = replay(SQLiteLedger(src), POLICY)
    b = replay(SQLiteLedger(copy), POLICY)
    assert a.json == b.json and a.markdown == b.markdown and a.digest == b.digest
    verify_replay(SQLiteLedger(copy), POLICY, a.digest)  # no raise


def test_replay_detects_changed_ledger_or_policy() -> None:
    ledger = _fixture_ledger()
    first = replay(ledger, POLICY)
    ledger.append(_det("run:extra:0", EventType.RUN_RECORDED,
                       {"visibility_level": "A", "test_case_id": "x", "error": None}))
    with pytest.raises(ReplayMismatchError):
        verify_replay(ledger, POLICY, first.digest)
    other = POLICY.model_copy(update={"version": "2"})
    with pytest.raises(ReplayMismatchError):
        verify_replay(_fixture_ledger(), other, first.digest)


def test_replay_refuses_broken_chain(tmp_path: Path) -> None:
    import sqlite3
    path = tmp_path / "l.sqlite"
    _fixture_ledger(path).close()
    con = sqlite3.connect(path)
    con.execute("update ledger set event_json = replace(event_json, 'c0', 'zz') where seq = 2")
    con.commit()
    con.close()
    assert replay(SQLiteLedger(path), POLICY).chain_ok is False


def test_handoff_build_evidence_pack_matches_build_pack() -> None:
    ledger = _fixture_ledger()
    assert render_json(build_evidence_pack(ledger, POLICY)) == render_json(
        build_pack(ledger, POLICY))


def test_golden_evidence_pack(snapshot: SnapshotAssertion) -> None:
    pack = build_pack(_fixture_ledger(), POLICY)
    assert render_markdown(pack) == snapshot(name="markdown")
    assert render_json(pack) == snapshot(name="json")


def test_cli_replay_matches_and_detects_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "l.sqlite"
    _fixture_ledger(path).close()
    pol = tmp_path / "p.yaml"
    pol.write_text(yaml.safe_dump(POLICY.model_dump(mode="json")), encoding="utf-8")
    digest = replay(SQLiteLedger(path), POLICY).digest
    ok = runner.invoke(app, ["replay", str(path), str(pol), "--expect-digest", digest])
    assert ok.exit_code == 0 and digest in ok.output
    bad = runner.invoke(app, ["replay", str(path), str(pol), "--expect-digest", "0" * 64])
    assert bad.exit_code == 1
