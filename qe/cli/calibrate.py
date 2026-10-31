"""`qe calibrate`: split-conformal threshold + panel independence report from labelled verdicts.

Input JSONL, one object per labelled claim:
  {"truth": "supported", "verdicts": {"<verifier name>": "<state>", ...}}
Output JSON: conformal qhat (null = calibration set too small for alpha), panel n_eff and
pairwise error correlation (qe.verify.aggregate.panel_report), optional held-out coverage.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import typer

from qe.core.schemas import ClaimState, MethodClass, Verdict
from qe.verify.aggregate import panel_report
from qe.verify.conformal import SplitConformal, vote_probs


def _parse_rows(path: Path) -> list[tuple[ClaimState, dict[str, ClaimState]]]:
    rows: list[tuple[ClaimState, dict[str, ClaimState]]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            rows.append((ClaimState(obj["truth"]),
                         {k: ClaimState(v) for k, v in obj["verdicts"].items()}))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"line {i}: invalid row ({type(exc).__name__})") from exc
    if not rows:
        raise ValueError("no labelled rows")
    names = {tuple(sorted(v)) for _, v in rows}
    if len(names) != 1:
        raise ValueError("every row must have the same set of verifiers")
    return rows


def _probs(verdicts: dict[str, ClaimState]) -> dict[ClaimState, float]:
    vs = [Verdict(claim_id="x", method=n, method_class=MethodClass.LLM_JUDGE,
                  method_version="0", state=s) for n, s in verdicts.items()]
    return vote_probs(vs)


def compute(rows: list[tuple[ClaimState, dict[str, ClaimState]]], alpha: float,
            holdout: float) -> dict[str, Any]:
    n_hold = int(len(rows) * holdout)
    calib, held = rows[: len(rows) - n_hold], rows[len(rows) - n_hold:]
    cp = SplitConformal.fit([(_probs(v), t) for t, v in calib], alpha)
    names = sorted(rows[0][1])
    report = panel_report({n: [v[n] for _, v in calib] for n in names}, [t for t, _ in calib])
    out: dict[str, Any] = {
        "alpha": alpha, "n_calibration": cp.n_calibration,
        "qhat": None if math.isinf(cp.qhat) else cp.qhat,
        "qhat_note": "null: n too small for this alpha; the prediction set is every label",
        "ncm": "1 - vote_share(label)  (NCM = nonconformity measure; meaning unconfirmed)",
        "panel": report.model_dump(mode="json"),
        "heldout_coverage": None,
    }
    if held:
        out["heldout_coverage"] = cp.coverage([(_probs(v), t) for t, v in held])
        out["n_heldout"] = len(held)
    return out


def calibrate(
    data: Path = typer.Argument(..., help="labelled verdicts JSONL"),
    alpha: float = typer.Option(0.1, help="miscoverage level"),
    holdout: float = typer.Option(0.0, help="trailing fraction held out to measure coverage"),
    out: Path | None = typer.Option(None, help="write JSON here instead of stdout"),
) -> None:
    """Fit split-conformal abstention and report panel n_eff / error correlation."""
    if not data.exists():
        typer.echo(f"error: no such file: {data}", err=True)
        raise typer.Exit(code=2)
    if not 0.0 <= holdout < 1.0:
        typer.echo("error: --holdout must be in [0, 1)", err=True)
        raise typer.Exit(code=2)
    try:
        result = compute(_parse_rows(data), alpha, holdout)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if out is None:
        typer.echo(text, nl=False)
    else:
        out.write_text(text, encoding="utf-8")
