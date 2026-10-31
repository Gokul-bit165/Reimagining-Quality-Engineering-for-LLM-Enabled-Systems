"""`qe` command line: connect (capability negotiation) and report (from ledger only)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
import yaml

from qe.access.blackbox_http import negotiate
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.report.evidence_pack import build_pack, render_json, render_markdown

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def connect(url: str, name: str = "target") -> None:
    """Negotiate access with a sandbox target and print the observed profile."""
    try:
        profile = asyncio.run(negotiate(url, name))
    except ConnectionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(profile.model_dump_json(indent=2))


@app.command()
def report(ledger: Path, policy: Path, fmt: str = typer.Option("md", "--format")) -> None:
    """Render the Evidence Pack from a ledger file (offline, deterministic)."""
    if fmt not in ("md", "json"):
        typer.echo("error: --format must be md or json", err=True)
        raise typer.Exit(code=2)
    if not ledger.exists():
        typer.echo(f"error: no such ledger: {ledger}", err=True)
        raise typer.Exit(code=2)
    pol = Policy.model_validate(yaml.safe_load(policy.read_text(encoding="utf-8")))
    pack = build_pack(SQLiteLedger(ledger), pol)
    typer.echo(render_json(pack) if fmt == "json" else render_markdown(pack), nl=False)


if __name__ == "__main__":
    app()
