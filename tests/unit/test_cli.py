from pathlib import Path

import yaml
from typer.testing import CliRunner

from qe.cli.main import app
from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger

runner = CliRunner()


def test_report_from_ledger_file_is_deterministic(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "l.sqlite")
    ledger.append(Event(key="m", type=EventType.MISSING_EVIDENCE, producer="executor",
                        producer_kind=ProducerKind.DETERMINISTIC, payload={"unrun": ["run:a:0"]}))
    ledger.close()
    pol = tmp_path / "p.yaml"
    pol.write_text(yaml.safe_dump({
        "policy_id": "ex", "version": "1", "loss_matrix": {}, "required_evidence": ["x"],
        "risk_appetite": {"x": 0.1}, "example_only": True}), encoding="utf-8")
    a = runner.invoke(app, ["report", str(tmp_path / "l.sqlite"), str(pol)])
    b = runner.invoke(app, ["report", str(tmp_path / "l.sqlite"), str(pol)])
    assert a.exit_code == 0 and a.output == b.output
    assert "INSUFFICIENT_EVIDENCE" in a.output and "EXAMPLE" in a.output


def test_report_missing_ledger_and_bad_connect_fail_cleanly(tmp_path: Path) -> None:
    assert runner.invoke(app, ["report", str(tmp_path / "nope"), str(tmp_path / "p")]).exit_code == 2
    assert runner.invoke(app, ["connect", "http://127.0.0.1:9"]).exit_code == 2
