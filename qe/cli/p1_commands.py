"""P1 CLI commands (`view`, `bundle`), kept apart from main.py to stay merge-friendly."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml

from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.report.bundle import write_bundle
from qe.report.viewer import render_viewer

OutOpt = Annotated[Path, typer.Option("--out", help="Output file or directory")]
PolicyOpt = Annotated[Path, typer.Option("--policy", help="Policy YAML")]


def _load(ledger: Path, policy: Path) -> tuple[SQLiteLedger, Policy]:
    for label, path in (("ledger", ledger), ("policy", policy)):
        if not path.exists():
            typer.echo(f"error: no such {label}: {path}", err=True)
            raise typer.Exit(code=2)
    return (SQLiteLedger(ledger),
            Policy.model_validate(yaml.safe_load(policy.read_text(encoding="utf-8"))))


def register(app: typer.Typer) -> None:
    @app.command()
    def view(ledger: Path, policy: Path, out: OutOpt) -> None:
        """Write a self-contained HTML report generated from the ledger only."""
        led, pol = _load(ledger, policy)
        out.write_text(render_viewer(led, pol), encoding="utf-8", newline="\n")
        typer.echo(f"wrote {out}")

    @app.command()
    def bundle(ledger: Path, out: OutOpt, policy: PolicyOpt) -> None:
        """Package ledger, policy, versions, prompt hashes and a replay README into a directory."""
        _load(ledger, policy)
        try:
            write_bundle(ledger, policy, out)
        except (FileExistsError, ValueError) as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f"wrote bundle {out}")
