"""`qe` command line: connect (capability negotiation) and report (from ledger only)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
import yaml

from qe.access.blackbox_http import negotiate, record_access_profile
from qe.core.ledger import SQLiteLedger
from qe.core.replay import ReplayMismatchError, verify_replay
from qe.core.schemas import Policy, VisibilityLevel
from qe.report.evidence_pack import build_pack, render_json, render_markdown

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def connect(
    url: str,
    name: str = "target",
    ledger: Annotated[Path | None, typer.Option("--ledger")] = None,
    declared_level: Annotated[VisibilityLevel | None, typer.Option("--declared-level")] = None,
) -> None:
    """Negotiate access with a target, print the profile, optionally record it in a ledger.

    Levels C-E cannot be observed over HTTP; pass --declared-level (flagged unverified).
    """
    try:
        profile = asyncio.run(negotiate(url, name, declared_level))
    except ConnectionError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if ledger is not None:
        led = SQLiteLedger(ledger)
        record_access_profile(led, profile)
        led.close()
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


@app.command(name="replay")
def replay_cmd(ledger: Path, policy: Path,
               expect_digest: str = typer.Option(..., "--expect-digest")) -> None:
    """Re-render the pack from the ledger and check its digest (exit 1 on mismatch)."""
    if not ledger.exists() or not policy.exists():
        typer.echo("error: ledger or policy file not found", err=True)
        raise typer.Exit(code=2)
    pol = Policy.model_validate(yaml.safe_load(policy.read_text(encoding="utf-8")))
    try:
        result = verify_replay(SQLiteLedger(ledger), pol, expect_digest)
    except ReplayMismatchError as exc:
        typer.echo(f"MISMATCH: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"OK digest={result.digest} chain_ok={result.chain_ok}")


if __name__ == "__main__":
    app()
