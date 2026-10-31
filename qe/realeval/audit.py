"""Append-only audit log of every evaluation action, in a hash-chained ledger (R10)."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger


def log(evals_dir: Path, action: str, **fields: Any) -> None:
    evals_dir.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteLedger(evals_dir / "audit.sqlite")
    try:
        ledger.append(Event(
            key=f"audit:{time.time_ns()}:{uuid.uuid4().hex[:6]}", type=EventType.EVIDENCE_RECORDED,
            producer="realeval_audit", producer_kind=ProducerKind.DETERMINISTIC,
            payload={"kind": "audit", "action": action, "at": time.time(), **fields}))
    finally:
        ledger.close()


def read(evals_dir: Path) -> list[dict[str, Any]]:
    path = evals_dir / "audit.sqlite"
    if not path.is_file():
        return []
    ledger = SQLiteLedger(path)
    try:
        return [dict(e.event.payload) for e in ledger.entries()]
    finally:
        ledger.close()
