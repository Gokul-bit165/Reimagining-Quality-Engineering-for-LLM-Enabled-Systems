from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import GENESIS_HASH, ConflictError, SQLiteLedger

json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-(10**9), 10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)
payloads = st.dictionaries(st.text(min_size=1, max_size=8), json_leaf, max_size=5)


@st.composite
def events(draw: st.DrawFn) -> Event:
    return Event(
        key=draw(st.text(alphabet="abcdefgh0123456789", min_size=1, max_size=6)),
        type=draw(st.sampled_from([EventType.EVIDENCE_RECORDED, EventType.RUN_RECORDED])),
        producer="exec",
        producer_kind=ProducerKind.DETERMINISTIC,
        payload=draw(payloads),
    )


def unique_by_key(evs: list[Event]) -> list[Event]:
    seen: dict[str, Event] = {}
    for e in evs:
        seen.setdefault(e.key, e)
    return list(seen.values())


@settings(max_examples=60, deadline=None)
@given(st.lists(events(), max_size=15).map(unique_by_key))
def test_append_keeps_chain_valid_ordered_and_contiguous(evs: list[Event]) -> None:
    ledger = SQLiteLedger(":memory:")
    entries = [ledger.append(e) for e in evs]
    assert [x.seq for x in entries] == list(range(len(evs)))
    assert [x.event.key for x in ledger.entries()] == [e.key for e in evs]
    prev = GENESIS_HASH
    for x in ledger.entries():
        assert x.prev_hash == prev
        prev = x.hash
    assert ledger.verify().ok
    assert ledger.head() == prev


@settings(max_examples=40, deadline=None)
@given(st.lists(events(), min_size=1, max_size=10).map(unique_by_key))
def test_append_is_idempotent_for_identical_events(evs: list[Event]) -> None:
    ledger = SQLiteLedger(":memory:")
    first = [ledger.append(e) for e in evs]
    head = ledger.head()
    again = [ledger.append(e) for e in evs]
    assert again == first and len(ledger) == len(evs) and ledger.head() == head


@settings(max_examples=40, deadline=None)
@given(events(), payloads)
def test_same_key_different_content_conflicts(e: Event, other: dict[str, object]) -> None:
    ledger = SQLiteLedger(":memory:")
    ledger.append(e)
    changed = e.model_copy(update={"payload": {**other, "__x": 1}})
    with pytest.raises(ConflictError):
        ledger.append(changed)
    assert len(ledger) == 1 and ledger.verify().ok


@settings(max_examples=30, deadline=None)
@given(st.lists(events(), max_size=8).map(unique_by_key))
def test_identical_histories_have_identical_heads(evs: list[Event]) -> None:
    a, b = SQLiteLedger(":memory:"), SQLiteLedger(":memory:")
    for e in evs:
        a.append(e)
        b.append(e)
    assert a.head() == b.head()


def test_reopen_preserves_state(tmp_path: Path) -> None:
    path = tmp_path / "l.sqlite"
    ledger = SQLiteLedger(path)
    e = Event(
        key="k",
        type=EventType.RUN_RECORDED,
        producer="x",
        producer_kind=ProducerKind.DETERMINISTIC,
        payload={"a": 1},
    )
    ledger.append(e)
    head = ledger.head()
    ledger.close()
    again = SQLiteLedger(path)
    assert again.head() == head and len(again) == 1 and again.verify().ok
    again.append(e.model_copy(update={"key": "k2"}))
    assert again.verify().ok
