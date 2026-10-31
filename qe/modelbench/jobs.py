"""Background benchmark jobs with a persisted status file (real models can take minutes)."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qe.core.ids import content_id
from qe.llm.real import RealLLMNotAllowedError, RealRuntime, runtime_from_env
from qe.modelbench.models import is_simulated, valid_model_id
from qe.modelbench.runner import DEFAULT_PACE_S, run_benchmark

BENCH_ID = re.compile(r"^bench-[a-z0-9]{8}$")
MAX_MODELS = 4
MAX_CONCURRENT = 2
_LOCK = threading.Lock()
IO_RETRIES = 20
IO_RETRY_DELAY_S = 0.01
_RUNNING: set[str] = set()


class BenchRequestError(ValueError):
    pass


def validate(models: list[str], env: os._Environ[str] | dict[str, str] | None = None) -> None:
    e = os.environ if env is None else env
    if not 1 <= len(models) <= MAX_MODELS or len(set(models)) != len(models):
        raise BenchRequestError(f"choose 1 to {MAX_MODELS} distinct models")
    for m in models:
        if not valid_model_id(m):
            raise BenchRequestError(f"invalid model id: {m!r}")
    real = [m for m in models if not is_simulated(m)]
    if not real:
        return
    try:
        runtime_from_env(Path("."), e)
    except RealLLMNotAllowedError as exc:
        raise BenchRequestError(str(exc)) from None
    paid = [m for m in real if not m.endswith(":free")]
    try:
        budget = float(e.get("QE_LLM_SPEND_BUDGET_USD", ""))
    except ValueError:
        budget = 0.0
    if paid and not budget > 0:
        raise BenchRequestError(
            f"{paid[0]} is not a free model: set QE_LLM_SPEND_BUDGET_USD to allow paid models")


def bench_id(models: list[str], focus: str, n_tests: int, repeats: int) -> str:
    return "bench-" + content_id([sorted(models), focus, n_tests, repeats])[:8]


def _status_path(runs: Path, bid: str) -> Path:
    return runs / f"{bid}.status.json"


def _retry_io[T](op: Callable[[], T]) -> T:
    """Windows refuses to rename over / read a file another thread has open; retry briefly."""
    for attempt in range(IO_RETRIES):
        try:
            return op()
        except PermissionError:
            if attempt == IO_RETRIES - 1:
                raise
            time.sleep(IO_RETRY_DELAY_S)
    raise AssertionError("unreachable")


def read_status(runs: Path, bid: str) -> dict[str, Any] | None:
    path = _status_path(runs, bid)
    if not path.is_file():
        return None
    data: dict[str, Any] = _retry_io(lambda: json.loads(path.read_text("utf-8")))
    if data["state"] == "running" and bid not in _RUNNING:
        data = {**data, "state": "error", "error": "interrupted (server restarted)"}
    return data


def _write(runs: Path, bid: str, data: dict[str, Any]) -> None:
    tmp = _status_path(runs, bid).with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    _retry_io(lambda: tmp.replace(_status_path(runs, bid)))


def start(runs: Path, models: list[str], focus: str, n_tests: int, repeats: int) -> dict[str, Any]:
    validate(models)
    bid = bench_id(models, focus, n_tests, repeats)
    with _LOCK:
        if bid in _RUNNING:
            return read_status(runs, bid) or {}
        if len(_RUNNING) >= MAX_CONCURRENT:
            raise BenchRequestError(
                f"too many benchmarks running (max {MAX_CONCURRENT}); wait for one to finish")
        _RUNNING.add(bid)
    try:
        runs.mkdir(parents=True, exist_ok=True)
        real: RealRuntime | None = (
            runtime_from_env(runs) if any(not is_simulated(m) for m in models) else None)
        status = {"id": bid, "state": "running", "done": 0,
                  "total": len(models) * n_tests * repeats, "note": "starting", "error": None,
                  "models": models, "started": time.time()}
        _write(runs, bid, status)
    except BaseException:
        with _LOCK:  # setup failed: do not leave the id marked running forever
            _RUNNING.discard(bid)
        raise

    def progress(done: int, total: int, note: str) -> None:
        _write(runs, bid, {**status, "done": done, "total": total, "note": note})

    def work() -> None:
        try:
            run_benchmark(runs / f"{bid}.sqlite", models, focus, n_tests, repeats, real,
                          DEFAULT_PACE_S, 0, progress)
            _write(runs, bid, {**status, "state": "done", "done": status["total"],
                               "note": "finished"})
        except Exception as exc:  # noqa: BLE001 - reported to the user via the status file
            _write(runs, bid, {**status, "state": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            with _LOCK:
                _RUNNING.discard(bid)

    threading.Thread(target=work, daemon=True, name=bid).start()
    return status
