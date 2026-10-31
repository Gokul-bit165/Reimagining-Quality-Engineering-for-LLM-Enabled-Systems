"""Verify an evidence bundle offline: hashes, ledger chains, and full re-derivation."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qe.core.ledger import SQLiteLedger
from qe.qareport.build import build_report
from qe.qareport.bundle import (
    MANIFEST_SCHEMA,
    derived_files,
    sha256_bytes,
)
from qe.qareport.evidence import build_input
from qe.qareport.models import ReportContext
from qe.qareport.render_html import render_html
from qe.qareport.render_md import render_markdown

MAX_ENTRIES = 200
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_DIFF_LINES = 40


class VerifyResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    checks: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)


def flat(value: Any, prefix: str = "$") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out.update(flat(v, f"{prefix}.{k}"))
        return out or {prefix: {}}
    if isinstance(value, list):
        out = {}
        for i, v in enumerate(value):
            out.update(flat(v, f"{prefix}[{i}]"))
        return out or {prefix: []}
    return {prefix: value}


def diff_paths(expected: Any, actual: Any) -> list[str]:
    """Precise differences: path, recomputed value, value in the bundle."""
    a, b = flat(expected), flat(actual)
    lines = []
    for path in sorted(set(a) | set(b)):
        if path not in b:
            lines.append(f"{path}: recomputed {_short(a[path])}; missing in bundle")
        elif path not in a:
            lines.append(f"{path}: not in recomputation; bundle has {_short(b[path])}")
        elif a[path] != b[path]:
            lines.append(f"{path}: recomputed {_short(a[path])}; bundle has {_short(b[path])}")
    return lines


def _short(v: Any) -> str:
    text = json.dumps(v, ensure_ascii=False)
    return text if len(text) <= 120 else text[:117] + "..."


def _safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return not (p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name)


def _read_zip(path: Path) -> dict[str, bytes] | str:
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            if len(infos) > MAX_ENTRIES:
                return f"too many entries ({len(infos)} > {MAX_ENTRIES})"
            if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                return "uncompressed size exceeds the cap"
            names = [i.filename for i in infos]
            bad = [n for n in names if not _safe_name(n)]
            if bad:
                return f"unsafe path(s) in archive: {bad}"
            if len(set(names)) != len(names):
                return "duplicate entries in archive"
            return {i.filename: z.read(i) for i in infos if not i.is_dir()}
    except (zipfile.BadZipFile, OSError) as exc:
        return f"not a readable zip: {exc}"


def _check_manifest(files: dict[str, bytes], res: list[str], bad: list[str],
                    ) -> dict[str, Any] | None:
    raw = files.get("MANIFEST.json")
    if raw is None:
        bad.append("MANIFEST.json is missing")
        return None
    try:
        manifest: dict[str, Any] = json.loads(raw)
        listed: dict[str, Any] = manifest["files"]
    except (ValueError, KeyError, TypeError) as exc:
        bad.append(f"MANIFEST.json is unreadable: {exc}")
        return None
    if manifest.get("schema") != MANIFEST_SCHEMA:
        bad.append(f"unknown manifest schema {manifest.get('schema')!r}")
    for name, meta in sorted(listed.items()):
        if name not in files:
            bad.append(f"{name}: listed in MANIFEST.json but missing from the archive")
        elif sha256_bytes(files[name]) != meta["sha256"]:
            bad.append(f"{name}: sha256 mismatch (manifest {meta['sha256'][:16]}..., "
                       f"actual {sha256_bytes(files[name])[:16]}...)")
    for name in sorted(set(files) - set(listed) - {"MANIFEST.json"}):
        bad.append(f"{name}: present in the archive but not listed in MANIFEST.json")
    if not bad:
        res.append(f"file hashes: {len(listed)} file(s) match MANIFEST.json")
    return manifest


def _check_ledgers(files: dict[str, bytes], manifest: dict[str, Any], tmp: Path,
                   res: list[str], bad: list[str]) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for name, anchor in sorted(manifest.get("ledgers", {}).items()):
        if name not in files:
            continue  # already reported by the hash check
        target = tmp / PurePosixPath(name).name
        target.write_bytes(files[name])
        try:
            ledger = SQLiteLedger(target)
            try:
                rep = ledger.verify(expected_head=anchor["head"], expected_len=anchor["entries"])
            finally:
                ledger.close()
        except (sqlite3.DatabaseError, ValueError) as exc:
            bad.append(f"{name}: ledger is not a readable SQLite database ({exc})")
            continue
        if rep.ok:
            res.append(f"{name}: hash chain intact, {rep.checked} entries, head matches anchor")
            paths[name] = target
        else:
            where = "" if rep.first_bad_seq is None else f" at seq {rep.first_bad_seq}"
            bad.append(f"{name}: ledger verification FAILED{where}: {rep.reason}")
    return paths


def _compare_json(name: str, expected: Any, files: dict[str, bytes], bad: list[str]) -> None:
    try:
        actual = json.loads(files[name])
    except (KeyError, ValueError):
        bad.append(f"{name}: missing or not valid JSON")
        return
    diff = diff_paths(expected, actual)
    for line in diff[:MAX_DIFF_LINES]:
        bad.append(f"{name} {line}")
    if len(diff) > MAX_DIFF_LINES:
        bad.append(f"{name}: ... {len(diff) - MAX_DIFF_LINES} more difference(s)")


def _rederive(files: dict[str, bytes], paths: dict[str, Path], res: list[str],
              bad: list[str]) -> None:
    try:
        ctx = ReportContext.model_validate_json(files["context.json"])
        if ctx.kind == "campaign":
            from qe.qareport.campaign import CONTEXT_FILE, PLAN_FILE, inputs_from_context
            ledger = paths[ctx.targets[0].ledger_file]
            inp = inputs_from_context(ctx, ledger, json.loads(files[PLAN_FILE]),
                                      json.loads(files[CONTEXT_FILE]))
        else:
            inp = build_input(ctx, paths)
    except (KeyError, ValidationError, ValueError, sqlite3.DatabaseError) as exc:
        bad.append(f"cannot re-derive the report from the ledgers: {exc}")
        return
    report = build_report(inp)
    try:
        given: dict[str, Any] = json.loads(files["report.json"])
    except (KeyError, ValueError):
        bad.append("report.json: missing or not valid JSON")
        return
    before = len(bad)
    for t_new, t_old in zip(report["targets"], given.get("targets", []), strict=False):
        for sec in ("results", "recommendation"):
            for line in diff_paths(t_new.get(sec), t_old.get(sec))[:MAX_DIFF_LINES]:
                bad.append(f"scorecard/decision re-derivation, target {t_new['name']!r}, "
                           f"{sec} {line}")
    if len(bad) == before:
        res.append("scorecard and decision re-derived from the ledgers match report.json")
    before = len(bad)
    _compare_json("report.json", report, files, bad)
    if len(bad) == before:
        res.append("report.json is identical to the report rebuilt from the ledgers")
    expected = derived_files(inp, report)
    for name, data in sorted(expected.items()):
        if name != "report.json" and files.get(name) != data:
            bad.append(f"{name}: differs from the file re-derived from the ledgers")
    if given == report:
        if render_markdown(given).encode() != files.get("report.md"):
            bad.append("report.md: differs from the rendering of report.json")
        if render_html(given).encode() != files.get("report.html"):
            bad.append("report.html: differs from the rendering of report.json")
    if tool := ctx.tool.git_commit:
        res.append(f"report generated by tool commit {tool}")


def verify_bundle(path: Path) -> VerifyResult:
    loaded = _read_zip(path)
    if isinstance(loaded, str):
        return VerifyResult(ok=False, problems=[loaded])
    res: list[str] = []
    bad: list[str] = []
    manifest = _check_manifest(loaded, res, bad)
    if manifest is None:
        return VerifyResult(ok=False, checks=res, problems=bad)
    with tempfile.TemporaryDirectory() as tmp:
        paths = _check_ledgers(loaded, manifest, Path(tmp), res, bad)
        if "context.json" not in loaded:
            bad.append("context.json is missing")
        elif len(paths) == len(manifest.get("ledgers", {})):
            _rederive(loaded, paths, res, bad)
        else:
            bad.append("re-derivation skipped: a ledger failed verification")
    return VerifyResult(ok=not bad, checks=res, problems=bad)
