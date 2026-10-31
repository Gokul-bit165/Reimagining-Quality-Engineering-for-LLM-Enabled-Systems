"""Evidence bundle: contents, verification happy path, tamper cases, secrets."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qe.cli.main import app
from qe.qareport.bundle import build_bundle, sha256_bytes
from qe.qareport.verify import verify_bundle
from tests.qareport.conftest import TEST_SECRET, Fixture, make_fixture

runner = CliRunner()


def _files(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {i.filename: z.read(i) for i in z.infolist()}


def _write(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return path


def _refresh_manifest(files: dict[str, bytes], name: str) -> None:
    """Attacker who also edits MANIFEST.json so the file hash matches."""
    manifest = json.loads(files["MANIFEST.json"])
    manifest["files"][name] = {"sha256": sha256_bytes(files[name]), "bytes": len(files[name])}
    files["MANIFEST.json"] = json.dumps(manifest).encode()


def _flip(data: bytes, at: int) -> bytes:
    b = bytearray(data)
    b[at] ^= 0x01
    return bytes(b)


def test_bundle_has_all_expected_files(bundle_bytes: bytes) -> None:
    names = set(_files(bundle_bytes))
    assert {"report.html", "report.md", "report.json", "items.jsonl", "plan.json", "config.json",
            "context.json", "MANIFEST.json", "VERIFY.md"} <= names
    assert any(n.startswith("ledgers/") and n.endswith(".sqlite") for n in names)
    manifest = json.loads(_files(bundle_bytes)["MANIFEST.json"])
    assert set(manifest["files"]) == names - {"MANIFEST.json"}
    assert manifest["tool"]["git_commit"] and manifest["ledgers"]
    head = next(iter(manifest["ledgers"].values()))["head"]
    assert len(head) == 64
    for n, meta in manifest["files"].items():
        assert meta["sha256"] == sha256_bytes(_files(bundle_bytes)[n])


def test_items_jsonl_has_full_request_response_and_ledger_hash(bundle_bytes: bytes) -> None:
    lines = [json.loads(x) for x in _files(bundle_bytes)["items.jsonl"].decode().splitlines()]
    assert lines and all(x["repeats"] for x in lines)
    first = lines[0]
    assert first["question"] and first["repeats"][0]["ledger_hash"]
    assert {"answer", "contexts", "latency_s", "error"} <= set(first["repeats"][0])


def test_verify_happy_path(bundle_bytes: bytes, tmp_path: Path) -> None:
    res = verify_bundle(_write(tmp_path / "b.zip", _files(bundle_bytes)))
    assert res.ok, res.problems
    assert any("hash chain intact" in c for c in res.checks)
    assert any("identical to the report rebuilt" in c for c in res.checks)


def test_cli_verify_ok_and_exit_codes(bundle_bytes: bytes, tmp_path: Path) -> None:
    good = tmp_path / "good.zip"
    good.write_bytes(bundle_bytes)
    ok = runner.invoke(app, ["verify-bundle", str(good)])
    assert ok.exit_code == 0 and "VERIFIED" in ok.output
    missing = runner.invoke(app, ["verify-bundle", str(tmp_path / "nope.zip")])
    assert missing.exit_code == 2
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    assert runner.invoke(app, ["verify-bundle", str(junk)]).exit_code == 1


@pytest.mark.parametrize("name", ["items.jsonl", "report.json", "report.md", "report.html",
                                  "plan.json", "config.json", "context.json"])
def test_tamper_byte_in_file_is_detected_by_hash(bundle_bytes: bytes, tmp_path: Path,
                                                 name: str) -> None:
    files = _files(bundle_bytes)
    files[name] = _flip(files[name], len(files[name]) // 2)
    path = _write(tmp_path / "t.zip", files)
    res = verify_bundle(path)
    assert not res.ok and any(name in p and "sha256 mismatch" in p for p in res.problems)
    cli = runner.invoke(app, ["verify-bundle", str(path)])
    assert cli.exit_code == 1 and "sha256 mismatch" in cli.output


def test_tamper_byte_in_ledger_is_detected(bundle_bytes: bytes, tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    ledger = next(n for n in files if n.startswith("ledgers/"))
    files[ledger] = _flip(files[ledger], len(files[ledger]) // 2)
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok and any(ledger in p for p in res.problems)


def test_tamper_report_json_with_matching_manifest_is_caught_by_rederivation(
        bundle_bytes: bytes, tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    report = json.loads(files["report.json"])
    row = report["targets"][0]["results"]["scorecard"][0]
    row["value"] = 0.999  # a better-looking figure
    files["report.json"] = json.dumps(report, indent=2, sort_keys=True).encode()
    _refresh_manifest(files, "report.json")
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok
    joined = "\n".join(res.problems)
    assert "scorecard" in joined and "0.999" in joined and "recomputed" in joined


def test_tamper_items_with_matching_manifest_is_caught(bundle_bytes: bytes,
                                                       tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    files["items.jsonl"] = files["items.jsonl"].replace(b"Zavo", b"Zavx", 1)
    _refresh_manifest(files, "items.jsonl")
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok and any("items.jsonl" in p and "re-derived" in p for p in res.problems)


def test_tamper_ledger_content_with_matching_manifest_breaks_the_chain(
        bundle_bytes: bytes, tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    ledger = next(n for n in files if n.startswith("ledgers/"))
    db = tmp_path / "l.sqlite"
    db.write_bytes(files[ledger])
    con = sqlite3.connect(db)
    con.execute("UPDATE ledger SET event_json = replace(event_json, '987654', '100') "
                "WHERE event_json LIKE '%987654%' AND key LIKE 'erun:%'")
    con.commit()
    con.close()
    files[ledger] = db.read_bytes()
    _refresh_manifest(files, ledger)
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok and any("ledger verification FAILED" in p for p in res.problems)


def test_truncated_ledger_tail_is_caught_by_the_anchor(bundle_bytes: bytes,
                                                       tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    ledger = next(n for n in files if n.startswith("ledgers/"))
    db = tmp_path / "l.sqlite"
    db.write_bytes(files[ledger])
    con = sqlite3.connect(db)
    con.execute("DELETE FROM ledger WHERE seq = (SELECT MAX(seq) FROM ledger)")
    con.commit()
    con.close()
    files[ledger] = db.read_bytes()
    _refresh_manifest(files, ledger)
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok and any("anchored" in p for p in res.problems)


def test_missing_and_extra_files_are_reported(bundle_bytes: bytes, tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    del files["items.jsonl"]
    files["extra.txt"] = b"x"
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert any("items.jsonl" in p and "missing" in p for p in res.problems)
    assert any("extra.txt" in p and "not listed" in p for p in res.problems)


def test_zip_slip_member_is_rejected(bundle_bytes: bytes, tmp_path: Path) -> None:
    files = _files(bundle_bytes)
    files["../evil.txt"] = b"x"
    res = verify_bundle(_write(tmp_path / "t.zip", files))
    assert not res.ok and "unsafe path" in res.problems[0]


def test_bundle_contains_no_secrets(fx: Fixture, bundle_bytes: bytes) -> None:
    for name, data in _files(bundle_bytes).items():
        assert TEST_SECRET.encode() not in data, name


def test_bundle_is_withheld_when_a_secret_value_leaks_into_it(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path, echo=f"debug {TEST_SECRET}")
    with pytest.raises(ValueError, match="bundle withheld"):
        build_bundle(fixture.inp, fixture.ctx, fixture.ledgers, secrets=[TEST_SECRET])


def test_size_cap_raises(fx: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    import qe.qareport.bundle as b
    monkeypatch.setattr(b, "MAX_BUNDLE_BYTES", 10)
    with pytest.raises(OverflowError):
        b.build_bundle(fx.inp, fx.ctx, fx.ledgers)
