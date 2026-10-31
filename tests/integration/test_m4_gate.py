"""M4 gate: controls hold, ledger verifies, results replay from the ledger, committed results match."""

from __future__ import annotations

import json
from pathlib import Path

from bench.m4_experiment import PREREG, main, results_from_ledger
from qe.core.events import EventType
from qe.core.ledger import SQLiteLedger

COMMITTED = Path(__file__).resolve().parents[2] / "bench" / "results" / "m4"


def test_rerun_is_deterministic_and_replays_from_ledger(tmp_path: Path) -> None:
    assert main(["--out", str(tmp_path)]) == 0
    stored = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite")
    assert ledger.verify().ok
    replay = results_from_ledger(ledger)
    assert {k: v for k, v in stored.items() if k != "preregistration_sha256"} == json.loads(
        json.dumps(replay)
    )
    assert stored["preregistration_sha256"]
    ledger.close()


def test_controls_are_zero_and_every_verdict_is_deterministic(tmp_path: Path) -> None:
    main(["--out", str(tmp_path)])
    res = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert all(c["breaches"] == 0 for c in res["controls"].values())
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite")
    kinds = {
        e.event.producer_kind.value
        for e in ledger.entries()
        if e.event.type in (EventType.VERDICT_ISSUED, EventType.EVIDENCE_RECORDED)
    }
    assert kinds == {"deterministic"}
    ledger.close()


def test_committed_results_match_a_fresh_run_and_prereg_hash(tmp_path: Path) -> None:
    main(["--out", str(tmp_path)])
    fresh = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    committed = json.loads((COMMITTED / "results.json").read_text(encoding="utf-8"))
    assert fresh == committed, "bench/results/m4 is stale: re-run python -m bench.m4_experiment"
    assert PREREG.exists()
