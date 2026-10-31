"""The jury verifier must pass on a fresh scenario and must fail when evidence is damaged."""

import asyncio
import sqlite3
from pathlib import Path

from qe.demo.jury_check import check_scenario
from qe.demo.pipeline import run_scenario_variant

TEXT = "Customers receive wrong or invented shipping and returns policy facts"


def make(tmp: Path, sid: str = "scn-aaaa1111") -> None:
    for variant in ("clean", "seeded"):
        asyncio.run(run_scenario_variant(tmp, f"{sid}-rag-{variant}", "rag", variant, "LLM09",
                                         TEXT, None, 8))


def test_all_checks_pass_on_a_fresh_scenario(tmp_path: Path) -> None:
    make(tmp_path)
    results = check_scenario(tmp_path, "scn-aaaa1111")
    failed = [c for c in results if not c.ok]
    assert not failed and len(results) >= 20


def test_verifier_fails_when_the_ledger_has_been_edited(tmp_path: Path) -> None:
    make(tmp_path)
    con = sqlite3.connect(tmp_path / "scn-aaaa1111-rag-seeded.sqlite")
    row = con.execute("SELECT event_json FROM ledger WHERE seq = 5").fetchone()[0]
    con.execute("UPDATE ledger SET event_json = ? WHERE seq = 5", (row.replace("a", "b", 1),))
    con.commit()
    con.close()
    results = check_scenario(tmp_path, "scn-aaaa1111")
    assert any(not c.ok and "Hash chain" in c.name for c in results)


def test_verifier_reports_a_missing_run(tmp_path: Path) -> None:
    results = check_scenario(tmp_path, "scn-nope")
    assert results and all(not c.ok for c in results)
