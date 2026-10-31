"""Persistence for campaigns: runs/campaigns/<id>/{campaign.json, plan.json, ledger.sqlite}.

campaign.json holds the mutable state machine; ledger.sqlite is the hash-chained evidence and audit
trail (every call to a target, every stage transition and human action). State is derived
again from the ledger on replay, so the JSON is a cache, not the source of truth for results.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from qe.campaign.models import CAMPAIGN_ID
from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.realeval.jobs import runs_dir

PRODUCER = "campaign"
_IO = threading.RLock()


def campaigns_dir() -> Path:
    return runs_dir() / "campaigns"


def campaign_dir(cid: str) -> Path:
    if not CAMPAIGN_ID.match(cid):
        raise KeyError(cid)
    return campaigns_dir() / cid


def new_id() -> str:
    return "cmp-" + uuid.uuid4().hex[:8]


def exists(cid: str) -> bool:
    if CAMPAIGN_ID.match(cid) is None:
        return False
    return (campaigns_dir() / cid / "campaign.json").is_file()


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _IO:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        for attempt in range(50):  # Windows refuses a replace while a reader has the file open
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)


def _read(path: Path) -> dict[str, Any]:
    for attempt in range(50):
        try:
            data: dict[str, Any] = json.loads(path.read_text("utf-8"))
            return data
        except (PermissionError, json.JSONDecodeError):
            if attempt == 49:
                raise
            time.sleep(0.01)
    raise RuntimeError("unreachable")


def save(rec: dict[str, Any]) -> None:
    _write(campaign_dir(rec["id"]) / "campaign.json", rec)


def load_raw(cid: str) -> dict[str, Any] | None:
    if not exists(cid):
        return None
    return _read(campaign_dir(cid) / "campaign.json")


def save_plan(cid: str, plan: dict[str, Any]) -> None:
    _write(campaign_dir(cid) / "plan.json", plan)


def load_plan(cid: str) -> dict[str, Any] | None:
    path = campaign_dir(cid) / "plan.json"
    return _read(path) if path.is_file() else None


def save_imported(cid: str, plan: dict[str, Any]) -> None:
    _write(campaign_dir(cid) / "imported_plan.json", plan)


def load_imported(cid: str) -> dict[str, Any] | None:
    path = campaign_dir(cid) / "imported_plan.json"
    return _read(path) if path.is_file() else None


def list_ids() -> list[str]:
    base = campaigns_dir()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir()
                  if CAMPAIGN_ID.match(p.name) and (p / "campaign.json").is_file())


def open_ledger(cid: str) -> SQLiteLedger:
    d = campaign_dir(cid)
    d.mkdir(parents=True, exist_ok=True)
    return SQLiteLedger(d / "ledger.sqlite")


@contextmanager
def ledger(cid: str) -> Iterator[SQLiteLedger]:
    lg = open_ledger(cid)
    try:
        yield lg
    finally:
        lg.close()


def append(lg: SQLiteLedger, key: str, etype: EventType, payload: dict[str, Any],
           kind: ProducerKind = ProducerKind.DETERMINISTIC, producer: str = PRODUCER) -> None:
    lg.append(Event(key=key, type=etype, producer=producer, producer_kind=kind,
                    payload=payload))


def audit(cid: str, action: str, lg: SQLiteLedger | None = None, **fields: Any) -> None:
    """Append one audit event (action + fields) to the campaign ledger."""
    payload = {"kind": "audit", "action": action, "at": time.time(), **fields}
    key = f"evt:{time.time_ns()}:{uuid.uuid4().hex[:6]}"
    if lg is not None:
        append(lg, key, EventType.EVIDENCE_RECORDED, payload)
        return
    with ledger(cid) as own:
        append(own, key, EventType.EVIDENCE_RECORDED, payload)
