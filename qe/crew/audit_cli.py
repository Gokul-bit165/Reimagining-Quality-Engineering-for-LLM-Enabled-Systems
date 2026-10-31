# ruff: noqa: B008  (typer idiom)
"""`qe audit` sub-app (mount in qe/cli/main.py with `app.add_typer(audit_app, name="audit")`).

Until P1 mounts it: `python -m qe.crew.audit_cli sample|score ...`.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from qe.core.ledger import ConflictError, SQLiteLedger
from qe.crew.audit import (
    AuditLabel,
    assessments,
    drafted_tests,
    invalid_rate,
    machine_rejected,
    not_valid_rate,
    record_labels,
    sample,
    skeptic_precision,
)

audit_app = typer.Typer(no_args_is_help=True, add_completion=False, help="Human audit of tests.")


def _fmt(name: str, k: int, n: int, lo: float, hi: float) -> str:
    return f"{name}: {k}/{n} = {k / n:.3f}  95% CI (Clopper-Pearson) [{lo:.3f}, {hi:.3f}]"


@audit_app.command("sample")
def sample_cmd(
    ledger: Path,
    out: Path = typer.Option(..., "--out"),
    n: int = typer.Option(30, "--n"),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    """Write a blind labelling sheet (simple random sample of drafted tests)."""
    if not ledger.exists():
        typer.echo(f"error: no such ledger: {ledger}", err=True)
        raise typer.Exit(code=2)
    items = {i.test.id: i for i in drafted_tests(SQLiteLedger(ledger))}
    picked = sample([i.test for i in items.values()], n, seed)
    rows = [{"test_id": t.id, "question": t.input.get("question"),
             "expected": t.input.get("expected"), "source_text": items[t.id].source_text,
             "label": ""} for t in picked]
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"wrote {len(rows)} of {len(items)} drafted tests to {out}; "
               f"fill 'label' with one of: valid, invalid, ambiguous")


@audit_app.command("score")
def score_cmd(
    ledger: Path, sheet: Path, auditor: str = typer.Option(..., "--auditor")
) -> None:
    """Record human labels in the ledger and print the invalid-test rate with its interval."""
    try:
        rows = json.loads(sheet.read_text(encoding="utf-8"))
        labels = [AuditLabel(test_id=r["test_id"], label=r["label"]) for r in rows]
        if not labels:
            raise ValueError("empty sheet")
    except (OSError, ValueError, KeyError) as exc:
        typer.echo(f"error: bad sheet (every row needs a valid label): {exc}", err=True)
        raise typer.Exit(code=2) from exc
    led = SQLiteLedger(ledger)
    try:
        record_labels(led, labels, auditor)
    except ConflictError as exc:
        typer.echo(f"error: conflicting earlier label by this auditor: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    r, nv = invalid_rate(labels), not_valid_rate(labels)
    typer.echo(_fmt("invalid-test rate", r.k, r.n, r.lower, r.upper))
    typer.echo(_fmt("invalid-or-ambiguous rate", nv.k, nv.n, nv.lower, nv.upper))
    typer.echo(f"machine-rejected drafts (excluded from population): {machine_rejected(led)}")
    try:
        sp = skeptic_precision(labels, assessments(led))
        typer.echo(_fmt("skeptic precision on 'valid'", sp.k, sp.n, sp.lower, sp.upper))
    except ValueError:
        typer.echo("skeptic precision: no audited test was judged valid by the skeptic")


if __name__ == "__main__":
    audit_app()
