"""Evidence bundle: a zip with the report in every format, ledger copies, full items, the plan,
configuration, MANIFEST.json (sha256 of every file) and VERIFY.md. `verify_bundle` (verify.py)
recomputes everything from the ledger copies alone."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from qe.core.ids import canonical_json
from qe.qareport.build import build_report
from qe.qareport.models import ReportContext, ReportInput, TargetContext
from qe.qareport.render_html import render_html
from qe.qareport.render_md import render_markdown

MAX_BUNDLE_BYTES = 256 * 1024 * 1024  # uncompressed total; larger evidence is refused (413)
MANIFEST_SCHEMA = "qe.evidence-bundle/1"

VERIFY_MD = """# Verifying this evidence bundle

This bundle holds a quality-tester report and the evidence it was derived from.

Run (from a checkout of the `qe` tool, ideally the commit named in MANIFEST.json):

    qe verify-bundle <this-file>.zip

The command exits 0 only when all of these hold; otherwise it exits 1 and prints a diff:

1. Every file listed in MANIFEST.json exists with the recorded sha256, and no extra file exists.
2. Every ledger copy in `ledgers/` has an intact hash chain, and its head hash and entry count
   match MANIFEST.json.
3. The scorecard, decision, items, plan and configuration recomputed from the ledgers match
   report.json, items.jsonl, plan.json and config.json.
4. The whole of report.json is rebuilt from the ledgers plus context.json and must be identical.
5. report.md and report.html re-rendered from report.json must be byte-identical.

What this does NOT prove: MANIFEST.json is not signed, so someone who can rewrite the whole zip
can also rewrite the manifest. The ledger head hash is the anchor: compare it with a value you
recorded earlier or received over a separate channel. The ledger chain cannot detect truncation
of its tail unless the anchored head/length are compared. Recorded target responses are as
reported by the evaluation harness; this check does not re-run the target.
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copy_ledger(src: Path) -> bytes:
    """Consistent single-file copy of a (possibly WAL-mode) SQLite ledger."""
    with tempfile.TemporaryDirectory() as tmp:
        dst_path = Path(tmp) / "copy.sqlite"
        source = sqlite3.connect(str(src))
        dest = sqlite3.connect(str(dst_path))
        try:
            source.backup(dest)
            dest.execute("PRAGMA journal_mode=DELETE")
        finally:
            dest.close()
            source.close()
        return dst_path.read_bytes()


def items_jsonl(inp: ReportInput) -> str:
    """Every item with every recorded request/response, plus the ledger key and hash of each."""
    lines = []
    for t in inp.targets:
        for row in t.result["items"]:
            reps = []
            for r in t.runs.get(row["id"], []):
                ref = t.entries.get(t.run_key(row["id"], r["rep"]))
                reps.append({"rep": r["rep"], "answer": r["answer"], "contexts": r["contexts"],
                             "latency_s": r["latency_s"], "error": r["error"],
                             "ledger_key": t.run_key(row["id"], r["rep"]),
                             "ledger_hash": ref.hash if ref else None})
            vkey = t.verdict_key(row["id"])
            verdict = t.entries.get(vkey) if vkey else None
            lines.append(canonical_json({
                "target": t.name, "item_id": row["id"], "source": row["source"],
                "risk": row.get("risk"), "lineage": row.get("lineage"), "probe": row.get("probe"),
                "question": row["question"], "reference_answer": row["reference_answer"],
                "answerable": row["answerable"], "repeats": reps, "scores": row["scores"],
                "passed": row["passed"], "failure_class": row["failure_class"],
                "failure_reason": row["failure_reason"],
                "verdict_ledger_hash": verdict.hash if verdict else None}))
    return "\n".join(lines) + ("\n" if lines else "")


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def derived_files(inp: ReportInput, report: dict[str, Any]) -> dict[str, bytes]:
    """Every file that is a pure function of (ledgers, context)."""
    return {
        "report.json": pretty(report).encode("utf-8"),
        "report.md": render_markdown(report).encode("utf-8"),
        "report.html": render_html(report).encode("utf-8"),
        "items.jsonl": items_jsonl(inp).encode("utf-8"),
        "plan.json": pretty({t.name: t.items_planned for t in inp.targets}).encode("utf-8"),
        "config.json": pretty({t.name: t.config for t in inp.targets}).encode("utf-8"),
    }


def ledger_file_name(name: str, index: int) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40] or "target"
    return f"ledgers/{index:02d}-{safe}.sqlite"


def secret_leaks(files: dict[str, bytes], secrets: Iterable[str]) -> list[str]:
    """Names of files that contain any secret value (values of 6+ characters only)."""
    needles = [s.encode("utf-8") for s in secrets if len(s) >= 6]
    return sorted(n for n, data in files.items() if any(x in data for x in needles))


def build_bundle(inp: ReportInput, context: ReportContext, ledgers: dict[str, Path],
                 secrets: Iterable[str] = (), extra_files: dict[str, bytes] | None = None,
                 ) -> bytes:
    """Zip bytes. Raises ValueError (secret detected) or OverflowError (size cap)."""
    report = build_report(inp)
    files = derived_files(inp, report)
    files["context.json"] = pretty(context.model_dump(mode="json")).encode("utf-8")
    for name, path in ledgers.items():
        files[name] = copy_ledger(path)
    files.update(extra_files or {})
    files["VERIFY.md"] = VERIFY_MD.encode("utf-8")
    leaks = secret_leaks(files, secrets)
    if leaks:
        raise ValueError(f"a secret value was found in {', '.join(leaks)}: bundle withheld")
    if sum(len(d) for d in files.values()) > MAX_BUNDLE_BYTES:
        raise OverflowError("evidence bundle exceeds the size cap")
    manifest = {
        "schema": MANIFEST_SCHEMA, "report_id": inp.id, "kind": inp.kind,
        "generated_epoch": int(time.time()), "tool": inp.tool.model_dump(),
        "ledgers": {tc.ledger_file: {"head": t.head, "entries": t.length}
                    for tc, t in zip(context.targets, inp.targets, strict=True)},
        "files": {n: {"sha256": sha256_bytes(d), "bytes": len(d)}
                  for n, d in sorted(files.items())},
    }
    files["MANIFEST.json"] = pretty(manifest).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(files):
            info = zipfile.ZipInfo(n, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[n])
    return buf.getvalue()


def context_for(inp: ReportInput, ledger_names: list[str]) -> ReportContext:
    targets = [TargetContext(
        name=t.name, eval_id=t.eval_id, project_id=t.project_id, created=t.created,
        state=t.state, params=t.params, meta=t.meta, monitoring=t.monitoring, ledger_file=n)
        for t, n in zip(inp.targets, ledger_names, strict=True)]
    return ReportContext(kind=inp.kind, id=inp.id, title=inp.title, created=inp.created,
                         tool=inp.tool, notes=inp.notes, targets=targets)
