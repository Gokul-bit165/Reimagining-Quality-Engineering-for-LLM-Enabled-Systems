"""`qe audit`: sample drafted tests for human labelling; score labelled CSVs."""

from __future__ import annotations

from pathlib import Path

import typer

from qe.core.ledger import SQLiteLedger
from qe.crew.audit import items_from_ledger, sample, score, to_csv
from qe.risk.coverage import record_estimate

audit_app = typer.Typer(no_args_is_help=True, add_completion=False, help="Human audit of tests.")


@audit_app.command("sample")
def sample_cmd(
    ledger: Path, out: Path, n: int = typer.Option(..., "--n"), seed: int = typer.Option(0)
) -> None:
    """Write a blind, stratified, seeded CSV of drafted tests for labelling."""
    if not ledger.exists():
        typer.echo(f"error: no such ledger: {ledger}", err=True)
        raise typer.Exit(code=2)
    items = items_from_ledger(SQLiteLedger(ledger))
    try:
        picked = sample(items, n, seed)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    out.write_text(to_csv(picked), encoding="utf-8", newline="")
    typer.echo(f"wrote {len(picked)} rows to {out}")


@audit_app.command("score")
def score_cmd(
    labelled: Path,
    ledger: Path | None = typer.Option(None, help="Record the estimate in this ledger"),
) -> None:
    """Compute the invalid-test rate with an exact interval from labelled rows."""
    try:
        est = score(labelled.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if ledger is not None:
        record_estimate(SQLiteLedger(ledger), est)
    typer.echo(est.model_dump_json(indent=2))
    if est.synthetic:
        typer.echo("WARNING: labels are SYNTHETIC (pipeline test only); not a human audit", err=True)
