import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from qe.cli.main import app
from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.report.bundle import verify_bundle, write_bundle
from qe.report.evidence_pack import build_pack, render_json, render_markdown

runner = CliRunner()
POLICY = Policy(policy_id="ex", version="1", loss_matrix={}, required_evidence=("m",),
                risk_appetite={"m": 0.1}, example_only=True)


def make(tmp_path: Path) -> tuple[Path, Path]:
    led = SQLiteLedger(tmp_path / "l.sqlite")
    for i in range(3):
        led.append(Event(key=f"run:c{i}:0", type=EventType.RUN_RECORDED, producer="executor",
                         producer_kind=ProducerKind.DETERMINISTIC, payload={
                             "test_case_id": f"c{i}", "repeat_index": 0, "seed": i,
                             "visibility_level": "A", "request": {}, "response": {}, "spans": [],
                             "versions": {"prompt_version": "p1"}, "error": None,
                             "prompt_hash": "ab" * 32}))
    led.close()
    pol = tmp_path / "policy.yaml"
    pol.write_text(yaml.safe_dump(POLICY.model_dump(mode="json")), encoding="utf-8")
    return tmp_path / "l.sqlite", pol


def test_bundle_has_expected_files_and_manifest(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    out = tmp_path / "b"
    write_bundle(led, pol, out)
    names = {p.name for p in out.iterdir()}
    assert {"ledger.sqlite", "policy.yaml", "versions.txt", "prompt_hashes.json", "README.md",
            "pack.json", "pack.md", "MANIFEST.json"} <= names
    assert json.loads((out / "prompt_hashes.json").read_text())["ledger"] == ["ab" * 32]
    assert "pydantic==" in (out / "versions.txt").read_text()
    readme = (out / "README.md").read_text()
    assert "qe report ledger.sqlite policy.yaml" in readme and "verify" in readme.lower()
    assert "claims" in readme.lower()


def test_replay_from_bundle_is_byte_identical(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    original = build_pack(SQLiteLedger(led), POLICY)
    out = tmp_path / "b"
    write_bundle(led, pol, out)
    copy = tmp_path / "moved"
    shutil.copytree(out, copy)  # relocatable
    policy = Policy.model_validate(yaml.safe_load((copy / "policy.yaml").read_text()))
    replay = build_pack(SQLiteLedger(copy / "ledger.sqlite"), policy)
    assert render_json(replay) == render_json(original)
    assert render_json(replay) == (copy / "pack.json").read_text(encoding="utf-8")
    assert render_markdown(replay) == (copy / "pack.md").read_text(encoding="utf-8")
    assert verify_bundle(copy).ok


def test_replay_via_cli_matches_bundled_pack(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    out = tmp_path / "b"
    res = runner.invoke(app, ["bundle", str(led), "--policy", str(pol), "--out", str(out)])
    assert res.exit_code == 0
    r = runner.invoke(app, ["report", str(out / "ledger.sqlite"), str(out / "policy.yaml"),
                            "--format", "json"])
    assert r.output == (out / "pack.json").read_text(encoding="utf-8")


def test_verify_bundle_detects_tampering(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    out = tmp_path / "b"
    write_bundle(led, pol, out)
    (out / "policy.yaml").write_text((out / "policy.yaml").read_text() + "\n# edited\n")
    res = verify_bundle(out)
    assert not res.ok and "policy.yaml" in res.problems[0]


def test_verify_bundle_detects_pack_that_no_longer_replays(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    out = tmp_path / "b"
    write_bundle(led, pol, out)
    (out / "pack.json").write_text("{}", encoding="utf-8")
    # manifest still lists the old hash, so tamper is caught either way
    assert not verify_bundle(out).ok


def test_bundle_refuses_nonempty_output_and_corrupt_ledger(tmp_path: Path) -> None:
    led, pol = make(tmp_path)
    out = tmp_path / "b"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(FileExistsError):
        write_bundle(led, pol, out)
    bad = tmp_path / "bad.sqlite"
    shutil.copy(led, bad)
    import sqlite3
    con = sqlite3.connect(bad)
    con.execute("UPDATE ledger SET event_json = replace(event_json, 'run:c1:0', 'run:zz:0') WHERE seq=1")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="ledger"):
        write_bundle(bad, pol, tmp_path / "b2")
    assert runner.invoke(app, ["bundle", str(bad), "--policy", str(pol),
                               "--out", str(tmp_path / "b3")]).exit_code == 2


def test_bundle_leaves_no_sqlite_sidecar_files_and_manifest_matches_dir(tmp_path: Path) -> None:
    import json

    led, pol = make(tmp_path)
    out = tmp_path / "b"
    write_bundle(led, pol, out)
    names = sorted(p.name for p in out.iterdir())
    assert not [n for n in names if n.endswith(("-shm", "-wal"))]
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    assert sorted([*manifest, "MANIFEST.json"]) == names
