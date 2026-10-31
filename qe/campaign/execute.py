"""Execution stage: the IDENTICAL cases against every target, interleaved, resumable.

Order: for each case, for each repeat, every target is asked once, starting from a rotating
target so no target systematically goes first (drift / warm-up / rate-limit effects spread
evenly). Each response is written to the ledger under `crun:<target>:<case>:<rep>` BEFORE the
next call, so a killed process resumes exactly where it stopped and replay needs no target.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qe.campaign import store
from qe.core.events import EventType
from qe.core.ledger import SQLiteLedger
from qe.realeval.target import RagTarget, TargetAnswer

RUN_PREFIX = "crun:"


@dataclass(frozen=True)
class ExecOutcome:
    state: str  # complete | cancelled | timeout | budget
    reason: str | None
    calls_total: int
    calls_new: int


def run_key(label: str, item_id: str, rep: int) -> str:
    return f"{RUN_PREFIX}{label}:{item_id}:{rep}"


def recorded_keys(lg: SQLiteLedger) -> set[str]:
    return {e.event.key for e in lg.entries() if e.event.key.startswith(RUN_PREFIX)}


def call_order(labels: Sequence[str], item_index: int, rep: int) -> list[str]:
    """Rotate the target order per (case, repeat): deterministic and balanced."""
    k = (item_index + rep) % len(labels)
    return [*labels[k:], *labels[:k]]


def _ask(target: RagTarget, question: str) -> tuple[TargetAnswer, dict[str, Any] | None]:
    try:
        ans = target.ask(question)
    except Exception as exc:  # noqa: BLE001 - a crashing app is a measured failure
        ans = TargetAnswer(error=f"{type(exc).__name__}: {exc}")
    usage = getattr(target, "last_usage", None)
    return ans, usage if isinstance(usage, dict) else None


def _payload(label: str, item_id: str, rep: int, ans: TargetAnswer,
             usage: dict[str, Any] | None) -> dict[str, Any]:
    return {"kind": "target_response", "target": label, "item_id": item_id, "rep": rep,
            "answer": ans.answer, "contexts": ans.contexts,
            "latency_s": round(ans.latency_s, 6), "error": ans.error,
            "size_chars": len(ans.answer) + sum(len(c) for c in ans.contexts),
            "usage": usage}


def run_execution(*, items: Sequence[Mapping[str, Any]], repeats: int,
                  targets: Mapping[str, RagTarget], lg: SQLiteLedger, cancel: threading.Event,
                  max_calls: int, timeout_s: float,
                  on_progress: Callable[[int, int], None] | None = None) -> ExecOutcome:
    labels = list(targets)
    done = recorded_keys(lg)
    total = len(items) * repeats * len(labels)
    calls = len(done)
    new = 0
    start = time.monotonic()
    reason: str | None = None
    state = "complete"
    for idx, it in enumerate(items):
        for rep in range(repeats):
            for label in call_order(labels, idx, rep):
                key = run_key(label, str(it["id"]), rep)
                if key in done:
                    continue
                if cancel.is_set():
                    state, reason = "cancelled", "cancelled by user (kill switch)"
                elif time.monotonic() - start > timeout_s:
                    state, reason = "timeout", f"wall-clock budget {timeout_s}s exceeded"
                elif calls >= max_calls:
                    state, reason = "budget", f"call budget max_calls={max_calls} reached"
                if state != "complete":
                    _kill_all(targets)
                    return ExecOutcome(state, reason, calls, new)
                ans, usage = _ask(targets[label], str(it["question"]))
                store.append(lg, key, EventType.RUN_RECORDED,
                             _payload(label, str(it["id"]), rep, ans, usage))
                done.add(key)
                calls += 1
                new += 1
        if on_progress:
            on_progress(calls, total)
    if on_progress:
        on_progress(calls, total)
    return ExecOutcome("complete", None, calls, new)


def _kill_all(targets: Mapping[str, RagTarget]) -> None:
    for t in targets.values():
        kill = getattr(t, "kill", None)
        if callable(kill):
            try:
                kill()
            except Exception:  # noqa: BLE001, S110 - best effort; the run is already stopping
                pass


def read_runs(lg: SQLiteLedger) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], list[str]]:
    """runs[label][item_id] = recorded responses ordered by rep, and confirmed advisory ids."""
    runs: dict[str, dict[str, list[dict[str, Any]]]] = {}
    confirmed: list[str] = []
    for e in lg.entries():
        pl = e.event.payload
        if e.event.key.startswith(RUN_PREFIX):
            runs.setdefault(pl["target"], {}).setdefault(pl["item_id"], []).append(pl)
        elif e.event.key.startswith("confirm:"):
            confirmed.append(str(pl["item_id"]))
    for per_item in runs.values():
        for recs in per_item.values():
            recs.sort(key=lambda r: r["rep"])
    return runs, confirmed
