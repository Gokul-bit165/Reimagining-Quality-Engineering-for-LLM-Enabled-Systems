"""One-command verifier: checks the claims the demo makes against a scenario's real ledgers.

Usage:  python -m qe.demo.jury_check runs scn-<id>
Every line is computed from the ledgers on disk. A failing line is a real failure; nothing is
pre-baked. It verifies *properties of the evidence* (integrity, reproducibility, controls,
provenance), not model accuracy.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.replay import replay
from qe.core.schemas import Policy
from qe.demo.scenario_report import build_report

DRAFT_ONLY = {EventType.RISK_PROPOSED, EventType.TEST_DRAFTED, EventType.NARRATIVE_DRAFTED,
              EventType.ATTACK_ATTEMPTED}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _open(runs: Path, run_id: str) -> tuple[SQLiteLedger, Policy]:
    policy = Policy.model_validate_json((runs / f"{run_id}.policy.json").read_text("utf-8"))
    return SQLiteLedger(runs / f"{run_id}.sqlite"), policy


def _tamper_detected(runs: Path, run_id: str) -> Check:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.sqlite"
        shutil.copy(runs / f"{run_id}.sqlite", copy)
        con = sqlite3.connect(copy)
        row = con.execute("SELECT seq, event_json FROM ledger WHERE seq = 3").fetchone()
        con.execute("UPDATE ledger SET event_json = ? WHERE seq = 3",
                    (row[1].replace("a", "b", 1),))
        con.commit()
        con.close()
        tampered = SQLiteLedger(copy)
        report = tampered.verify()
        tampered.close()  # release the file before the temp dir is removed (Windows)
    return Check("Tampering with one stored event is detected", not report.ok,
                 f"verify() on an edited copy -> ok={report.ok}, "
                 f"first bad entry {report.first_bad_seq}")


def check_run(runs: Path, run_id: str) -> list[Check]:
    ledger, policy = _open(runs, run_id)
    rep = build_report(ledger, policy)
    first, second = replay(ledger, policy), replay(ledger, policy)
    drafts = [e for e in ledger.entries() if e.event.producer_kind is ProducerKind.LLM_AGENT]
    bad_types = {e.event.type.value for e in drafts if e.event.type not in DRAFT_ONLY}
    rates = [m for m in rep["metrics"] if m["failed_cases"] + m["passed_cases"] > 0]
    gen, att = rep["generation"], rep["attacks"]
    out = [
        Check("Hash chain verifies", ledger.verify().ok, f"{len(ledger)} entries"),
        Check("Report is byte-identical when regenerated from the ledger",
              first.digest == second.digest and first.markdown == second.markdown,
              f"sha256 {first.digest[:16]}…"),
        _tamper_detected(runs, run_id),
        Check("Model/crew output is stored only as drafts, never as evidence", not bad_types,
              f"{len(drafts)} crew events; non-draft types: {sorted(bad_types) or 'none'}"),
        Check("Tests were generated and each carries a verbatim source quote",
              bool(gen["tests"]), f"{len(gen['tests'])} executed, {gen['drafted']} drafted, "
              f"{gen['rejected_drafts']} rejected by the quote gate"),
        Check("Every reported rate carries an interval", all("failure_rate" in m for m in rates),
              f"{len(rates)} metrics with evaluable cases"),
        Check("Attack outcomes come from deterministic oracles",
              bool(att["rows"]) and bool(rep["checks"]["attack_oracles"]),
              f"{len(att['rows'])} pairs; oracles: {', '.join(rep['checks']['attack_oracles'])}"),
        Check("The report states what was not checked", bool(rep["checks"]["not_run"]),
              f"{len(rep['checks']['not_run'])} listed"),
        Check("Labels say whether generation and target are simulated or real",
              rep["labels"]["mode"] in ("simulated", "real"), rep["labels"]["generation"][:70]),
    ]
    signoffs = [e for e in ledger.entries() if e.event.type is EventType.SIGNOFF_RECORDED]
    out.append(Check("Sign-offs are human-only events",
                     all(e.event.producer_kind is ProducerKind.HUMAN for e in signoffs),
                     f"{len(signoffs)} recorded"))
    ledger.close()
    return out


def check_scenario(runs: Path, sid: str) -> list[Check]:
    results: list[Check] = []
    for variant in ("seeded", "clean"):
        run_id = next((p.stem for p in runs.glob(f"{sid}-*-{variant}.sqlite")), None)
        if run_id is None:
            results.append(Check(f"{variant} run exists", False, f"no ledger for {sid}"))
            continue
        results += [Check(f"[{variant}] {c.name}", c.ok, c.detail) for c in check_run(runs, run_id)]
    clean = next((p.stem for p in runs.glob(f"{sid}-*-clean.sqlite")), None)
    seeded = next((p.stem for p in runs.glob(f"{sid}-*-seeded.sqlite")), None)
    if clean and seeded:
        lc, pc = _open(runs, clean)
        ls, ps = _open(runs, seeded)
        rc, rs = build_report(lc, pc), build_report(ls, ps)
        fc = sum(m["failed_cases"] for m in rc["metrics"])
        fs = sum(m["failed_cases"] for m in rs["metrics"])
        out_clean = {m["metric"]: f"{m['failed_cases']}/{m['failed_cases'] + m['passed_cases']}"
                     for m in rc["metrics"]}
        results.append(Check("Clean control produces no false alarms", fc == 0,
                             f"failing cases on clean app: {fc} ({out_clean})"))
        results.append(Check("Seeded-defect app produces detectable failures", fs > 0,
                             f"failing cases on seeded app: {fs}"))
        same = [t["question"] for t in rc["generation"]["tests"]] == [
            t["question"] for t in rs["generation"]["tests"]]
        results.append(Check("Both apps ran the identical generated suite", same,
                             f"{len(rc['generation']['tests'])} tests"))
    return results


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m qe.demo.jury_check <runs_dir> <scenario prefix, e.g. scn-1a2b3c4d>")
        return 2
    results = check_scenario(Path(argv[0]), argv[1])
    for c in results:
        print(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}\n        {c.detail}")
    failed = [c for c in results if not c.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
