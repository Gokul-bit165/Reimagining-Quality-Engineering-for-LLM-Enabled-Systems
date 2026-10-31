"""Apply deterministic checks to recorded runs; verdicts are ledger events (R3)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import Verdict

# A check maps a recorded run payload to a Verdict, or None when it does not apply.
RunCheck = Callable[[dict[str, Any]], Verdict | None]
PRODUCER = "verifier"


def verify_runs(ledger: Ledger, checks: Sequence[tuple[str, RunCheck]]) -> int:
    """For each RUN_RECORDED entry and (metric, check), append a VERDICT_ISSUED once."""
    added = 0
    for entry in list(ledger.entries()):
        if entry.event.type is not EventType.RUN_RECORDED:
            continue
        for metric, check in checks:
            key = f"verdict:{entry.event.key}:{metric}"
            if ledger.find_by_key(key) is not None:
                continue
            verdict = check(entry.event.payload)
            if verdict is None:
                continue
            payload = {
                "metric": metric,
                "run_key": entry.event.key,
                "case_id": entry.event.payload["test_case_id"],
                "verdict": verdict.model_dump(mode="json"),
            }
            ledger.append(Event(key=key, type=EventType.VERDICT_ISSUED, producer=PRODUCER,
                                producer_kind=ProducerKind.DETERMINISTIC, payload=payload))
            added += 1
    return added
