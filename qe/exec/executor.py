"""Deterministic executor: repeated runs, seeds, budgets, kill switch, resumable.

Resume = idempotent ledger keys: a (case, repeat) already recorded is skipped, so a
crashed run continues where it stopped and never double-counts.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import RunRecord, TestCase
from qe.ports import (
    BudgetExceededError,
    KillSwitchError,
    SandboxSession,
    TargetPort,
    TargetRequest,
)

PRODUCER = "executor"


def run_key(case_id: str, repeat: int) -> str:
    return f"run:{case_id}:{repeat}"


async def execute(
    ledger: Ledger,
    target: TargetPort,
    cases: Sequence[TestCase],
    *,
    repeats: int,
    seed: int,
    session: SandboxSession,
    want_trace: bool = True,
    should_stop: Callable[[], bool] = lambda: False,
) -> list[str]:
    """Run every (case, repeat); returns keys of runs recorded in THIS call.

    On budget exhaustion or kill, remaining cells are logged as MISSING_EVIDENCE (never
    silently skipped) and the function returns normally.
    """
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    recorded: list[str] = []
    cells = [(c, r) for c in cases for r in range(repeats)]
    for index, (case, repeat) in enumerate(cells):
        key = run_key(case.id, repeat)
        if ledger.find_by_key(key) is not None:
            continue
        try:
            if should_stop():
                session.kill()
            session.charge(calls=1)
        except (BudgetExceededError, KillSwitchError) as exc:
            _log_missing(ledger, cells[index:], type(exc).__name__)
            return recorded
        request = TargetRequest(**{**case.input, "seed": seed + repeat, "want_trace": want_trace})
        response = await target.invoke(request)
        record = RunRecord(
            test_case_id=case.id, repeat_index=repeat, seed=seed + repeat,
            visibility_level=target.visibility_level,
            request=request.model_dump(mode="json"),
            response={"output": response.output, "citations": list(response.citations),
                      "meta": response.meta},
            spans=response.spans, versions={k: str(v) for k, v in response.meta.items()
                                            if k in ("model", "prompt_version", "variant")},
            error=response.error,
        )
        ledger.append(Event(key=key, type=EventType.RUN_RECORDED, producer=PRODUCER,
                            producer_kind=ProducerKind.DETERMINISTIC,
                            payload=record.model_dump(mode="json")))
        recorded.append(key)
    return recorded


def _log_missing(ledger: Ledger, remaining: Sequence[tuple[TestCase, int]], reason: str) -> None:
    keys = [run_key(c.id, r) for c, r in remaining]
    ledger.append(Event(key=f"missing:{keys[0]}", type=EventType.MISSING_EVIDENCE,
                        producer=PRODUCER, producer_kind=ProducerKind.DETERMINISTIC,
                        payload={"reason": reason, "unrun": keys}))
