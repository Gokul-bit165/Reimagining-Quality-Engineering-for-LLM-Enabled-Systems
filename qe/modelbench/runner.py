"""Run a benchmark: every model answers the same generated suite; evidence goes to a ledger.

Only deterministic code writes evidence. A call that fails (rate limit, outage) is recorded
as an errored run and produces NO verdict: it is missing evidence, never a failed test.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import Ledger, SQLiteLedger
from qe.llm.real import CallBudget, RealRuntime, _call
from qe.modelbench.models import is_simulated, make_client
from qe.modelbench.suite import (
    BenchTest,
    build_suite,
    consistency,
    messages_for,
    score,
    suite_summary,
)

PRODUCER = "modelbench"
DEFAULT_PACE_S = 3.0  # polite spacing between real calls (free tiers rate limit)


def _append(ledger: Ledger, key: str, etype: EventType, payload: dict[str, Any]) -> None:
    ledger.append(Event(key=key, type=etype, producer=PRODUCER,
                        producer_kind=ProducerKind.DETERMINISTIC, payload=payload))


def _verdict(ledger: Ledger, model: str, test: BenchTest, metric: str, v: Any,
             rep: int | None = None) -> None:
    suffix = "" if rep is None else f":{rep}"
    _append(ledger, f"bverdict:{model}:{test.test_id}:{metric}{suffix}", EventType.VERDICT_ISSUED,
            {"metric": metric, "model": model, "case_id": test.test_id, "repeat": rep,
             "run_key": f"brun:{model}:{test.test_id}:{rep}", "verdict": v.model_dump(mode="json")})


def run_benchmark(
    out_path: Path, models: list[str], focus: str, n_tests: int, repeats: int,
    real: RealRuntime | None = None, pace_s: float = DEFAULT_PACE_S, seed: int = 0,
    on_progress: Callable[[int, int, str], None] = lambda done, total, note: None,
) -> str:
    """Writes the ledger at `out_path`; returns its head hash."""
    for suffix in ("", "-wal", "-shm"):
        Path(str(out_path) + suffix).unlink(missing_ok=True)
    tests = build_suite(focus, n_tests, seed)
    ledger = SQLiteLedger(out_path)
    _append(ledger, "benchmark", EventType.EVIDENCE_RECORDED, {
        "kind": "benchmark", "models": models, "focus": focus, "n_tests": n_tests,
        "repeats": repeats, "seed": seed, "pace_s": pace_s,
        "simulated": {m: is_simulated(m) for m in models},
        "suite_generator": "deterministic stand-in (not a model)",
        "suite": suite_summary(tests)})
    _append(ledger, "suite", EventType.EVIDENCE_RECORDED, {
        "kind": "suite", "tests": [{k: v for k, v in t.model_dump().items() if k != "context"}
                                   for t in tests]})
    total, done = len(models) * len(tests) * repeats, 0
    factory = None if real is None else (lambda m: real.client(m, 90.0))
    for model in models:
        client = make_client(model, factory)
        budget = real.budget if real else CallBudget(10**9)
        for test in tests:
            outputs: list[str] = []
            for rep in range(repeats):
                done += 1
                on_progress(done, total, f"{model}: test {test.style} #{rep + 1}")
                error: str | None = None
                output = ""
                try:
                    if is_simulated(model):
                        output = client.complete(messages_for(test))
                    else:
                        output = _call(client, messages_for(test), budget)
                        time.sleep(pace_s)
                except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
                    error = f"{type(exc).__name__}: {exc}"
                _append(ledger, f"brun:{model}:{test.test_id}:{rep}", EventType.RUN_RECORDED,
                        {"model": model, "test_id": test.test_id, "repeat": rep,
                         "output": output, "error": error,
                         "run_id": content_id([model, test.test_id, rep])[:12]})
                if error is None:
                    outputs.append(output)
                    for metric, v in score(test, output).items():
                        _verdict(ledger, model, test, metric, v, rep)
            cons = consistency(test, outputs)
            if cons is not None:
                _verdict(ledger, model, test, "consistency", cons)
    head = ledger.head()
    ledger.close()
    return head
