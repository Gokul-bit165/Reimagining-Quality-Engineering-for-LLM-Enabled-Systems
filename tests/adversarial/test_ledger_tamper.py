import sqlite3
from pathlib import Path

import pytest

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger, compute_entry_hash


def make(path: Path, n: int = 5) -> SQLiteLedger:
    ledger = SQLiteLedger(path)
    for i in range(n):
        ledger.append(
            Event(
                key=f"k{i}",
                type=EventType.EVIDENCE_RECORDED,
                producer="p",
                producer_kind=ProducerKind.DETERMINISTIC,
                payload={"i": i},
            )
        )
    return ledger


def raw(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path)


def test_payload_edit_detected_at_row(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    make(p).close()
    c = raw(p)
    row = c.execute("SELECT event_json FROM ledger WHERE seq=2").fetchone()[0]
    c.execute("UPDATE ledger SET event_json=? WHERE seq=2", (row.replace('"i":2', '"i":99'),))
    c.commit()
    c.close()
    report = SQLiteLedger(p).verify()
    assert not report.ok and report.first_bad_seq == 2


def test_deleted_middle_row_detected(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    make(p).close()
    c = raw(p)
    c.execute("DELETE FROM ledger WHERE seq=2")
    c.commit()
    c.close()
    assert not SQLiteLedger(p).verify().ok


def test_recomputed_row_hash_breaks_next_link(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    make(p).close()
    c = raw(p)
    seq, prev, ev = c.execute(
        "SELECT seq, prev_hash, event_json FROM ledger WHERE seq=1"
    ).fetchone()
    ev2 = ev.replace('"i":1', '"i":77')
    c.execute(
        "UPDATE ledger SET event_json=?, hash=? WHERE seq=1",
        (ev2, compute_entry_hash(seq, prev, ev2)),
    )
    c.commit()
    c.close()
    report = SQLiteLedger(p).verify()
    assert not report.ok and report.first_bad_seq == 2


def test_tail_truncation_needs_external_anchor(tmp_path: Path) -> None:
    p = tmp_path / "l.sqlite"
    ledger = make(p)
    anchor_head, anchor_len = ledger.head(), len(ledger)
    ledger.close()
    c = raw(p)
    c.execute("DELETE FROM ledger WHERE seq>=3")
    c.commit()
    c.close()
    reopened = SQLiteLedger(p)
    assert reopened.verify().ok  # the chain alone cannot see truncation (documented limit)
    assert not reopened.verify(expected_head=anchor_head, expected_len=anchor_len).ok


def test_llm_agent_cannot_write_evidence_or_decisions() -> None:
    ledger = SQLiteLedger(":memory:")
    for t in (EventType.EVIDENCE_RECORDED, EventType.VERDICT_ISSUED, EventType.DECISION_ISSUED):
        with pytest.raises(PermissionError):
            ledger.append(
                Event(
                    key=str(t),
                    type=t,
                    producer="authors",
                    producer_kind=ProducerKind.LLM_AGENT,
                    payload={},
                )
            )
    ledger.append(
        Event(
            key="d1",
            type=EventType.TEST_DRAFTED,
            producer="authors",
            producer_kind=ProducerKind.LLM_AGENT,
            payload={"q": "x"},
        )
    )
    assert len(ledger) == 1


def test_only_humans_sign_off() -> None:
    ledger = SQLiteLedger(":memory:")
    with pytest.raises(PermissionError):
        ledger.append(
            Event(
                key="s",
                type=EventType.SIGNOFF_RECORDED,
                producer="x",
                producer_kind=ProducerKind.DETERMINISTIC,
                payload={},
            )
        )


def test_non_json_payload_rejected() -> None:
    with pytest.raises((TypeError, ValueError)):
        Event(
            key="k",
            type=EventType.RUN_RECORDED,
            producer="p",
            producer_kind=ProducerKind.DETERMINISTIC,
            payload={"x": {1, 2}},  # type: ignore[dict-item]
        )
