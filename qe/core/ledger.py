"""Append-only, hash-chained evidence ledger (SQLite WAL backend).

Chain: hash_n = SHA-256(f"{seq}|{prev_hash}|{event_json}"). The chain detects edits,
deletions and reordering. It cannot by itself detect truncation of the tail; callers
that need that must pin an external anchor (head hash + length) and pass it to verify().
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from qe.core.events import Event, ProducerKind, check_write_permission
from qe.core.ids import sha256_hex

GENESIS_HASH = "0" * 64


class ConflictError(Exception):
    """Same idempotency key re-used with different content."""


class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    prev_hash: str
    hash: str
    event: Event


class VerifyReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    checked: int
    first_bad_seq: int | None = None
    reason: str | None = None


def compute_entry_hash(seq: int, prev_hash: str, event_json: str) -> str:
    return sha256_hex(f"{seq}|{prev_hash}|{event_json}")


class Ledger(Protocol):
    """Storage interface; SQLite now, Postgres later."""

    def append(self, event: Event) -> Entry: ...
    def get(self, seq: int) -> Entry: ...
    def find_by_key(self, key: str) -> Entry | None: ...
    def entries(self, start: int = 0) -> Iterator[Entry]: ...
    def head(self) -> str: ...
    def __len__(self) -> int: ...
    def verify(
        self, expected_head: str | None = None, expected_len: int | None = None
    ) -> VerifyReport: ...
    def close(self) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    seq        INTEGER PRIMARY KEY,
    key        TEXT NOT NULL UNIQUE,
    prev_hash  TEXT NOT NULL,
    hash       TEXT NOT NULL,
    event_json TEXT NOT NULL
)
"""


class SQLiteLedger:
    def __init__(
        self, path: str | Path, producer_kinds: Mapping[str, ProducerKind] | None = None
    ) -> None:
        """`producer_kinds`, if given, pins each producer name to one kind (H2): unknown
        producers or a kind mismatch are rejected, so a caller cannot self-declare a kind."""
        self._producer_kinds = None if producer_kinds is None else dict(producer_kinds)
        self._conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._lock = threading.RLock()
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)

    # --- reads -------------------------------------------------------------
    @staticmethod
    def _row_to_entry(row: tuple[int, str, str, str]) -> Entry:
        seq, prev, hash_, event_json = row
        event = Event.model_validate_json(event_json)
        return Entry(seq=seq, prev_hash=prev, hash=hash_, event=event)

    def get(self, seq: int) -> Entry:
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, prev_hash, hash, event_json FROM ledger WHERE seq=?", (seq,)
            ).fetchone()
        if row is None:
            raise KeyError(seq)
        return self._row_to_entry(row)

    def find_by_key(self, key: str) -> Entry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT seq, prev_hash, hash, event_json FROM ledger WHERE key=?", (key,)
            ).fetchone()
        return None if row is None else self._row_to_entry(row)

    def entries(self, start: int = 0) -> Iterator[Entry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, prev_hash, hash, event_json FROM ledger WHERE seq>=? ORDER BY seq",
                (start,),
            ).fetchall()
        for row in rows:
            yield self._row_to_entry(row)

    def head(self) -> str:
        with self._lock:
            row = self._conn.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
        return GENESIS_HASH if row is None else str(row[0])

    def __len__(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0])

    # --- writes ------------------------------------------------------------
    def append(self, event: Event) -> Entry:
        event = Event.model_validate(event.model_dump())  # defeats model_construct (H3)
        check_write_permission(event.type, event.producer_kind)
        if self._producer_kinds is not None:
            pinned = self._producer_kinds.get(event.producer)
            if pinned is None or pinned is not event.producer_kind:
                raise PermissionError(
                    f"producer {event.producer!r} is not registered as {event.producer_kind.value}"
                )
        event_json = event.canonical()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existing = self._conn.execute(
                    "SELECT seq, prev_hash, hash, event_json FROM ledger WHERE key=?",
                    (event.key,),
                ).fetchone()
                if existing is not None:
                    if existing[3] != event_json:
                        raise ConflictError(f"key {event.key!r} already used with other content")
                    self._conn.execute("COMMIT")
                    return self._row_to_entry(existing)
                last = self._conn.execute(
                    "SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                seq, prev = (0, GENESIS_HASH) if last is None else (last[0] + 1, last[1])
                digest = compute_entry_hash(seq, prev, event_json)
                self._conn.execute(
                    "INSERT INTO ledger (seq, key, prev_hash, hash, event_json) VALUES (?,?,?,?,?)",
                    (seq, event.key, prev, digest, event_json),
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return Entry(seq=seq, prev_hash=prev, hash=digest, event=event)

    # --- integrity ---------------------------------------------------------
    def verify(
        self, expected_head: str | None = None, expected_len: int | None = None
    ) -> VerifyReport:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, prev_hash, hash, event_json, key FROM ledger ORDER BY seq"
            ).fetchall()
        prev = GENESIS_HASH
        for index, (seq, row_prev, row_hash, event_json, row_key) in enumerate(rows):
            if seq != index:
                return VerifyReport(ok=False, checked=index, first_bad_seq=index,
                                    reason=f"sequence gap: expected {index}, found {seq}")
            if row_prev != prev:
                return VerifyReport(ok=False, checked=index, first_bad_seq=seq,
                                    reason="prev_hash does not match previous entry")
            if compute_entry_hash(seq, row_prev, event_json) != row_hash:
                return VerifyReport(ok=False, checked=index, first_bad_seq=seq,
                                    reason="entry hash mismatch (content altered)")
            problem = self._row_problem(row_key, event_json)
            if problem is not None:
                return VerifyReport(ok=False, checked=index, first_bad_seq=seq, reason=problem)
            prev = row_hash
        if expected_len is not None and len(rows) != expected_len:
            return VerifyReport(ok=False, checked=len(rows),
                                reason=f"length {len(rows)} != anchored {expected_len}")
        if expected_head is not None and prev != expected_head:
            return VerifyReport(ok=False, checked=len(rows), reason="head != anchored head")
        return VerifyReport(ok=True, checked=len(rows))

    def _row_problem(self, row_key: str, event_json: str) -> str | None:
        try:
            event = Event.model_validate_json(event_json)
        except ValueError:
            return "stored event does not validate against the schema"
        if event.key != row_key:
            return "key column differs from the key inside the hashed event"
        try:
            check_write_permission(event.type, event.producer_kind)
        except PermissionError as exc:
            return f"stored event violates write permissions: {exc}"
        if self._producer_kinds is not None and (
            self._producer_kinds.get(event.producer) is not event.producer_kind
        ):
            return "stored event violates the producer registry"
        return None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
