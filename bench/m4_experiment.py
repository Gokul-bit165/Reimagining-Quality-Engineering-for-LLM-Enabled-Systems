"""M4 experiment driver (see bench/m4_preregistration.md). Results are derived from the ledger only.

Usage: python -m bench.m4_experiment --out bench/results/m4
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bench.asr import asr_at_budget, paired_comparison
from qe.core.events import EventType, ProducerKind
from qe.core.ledger import Ledger, SQLiteLedger
from qe.crew.attack_pairs import PAIRS, baseline_attack
from qe.crew.attacker import (
    AdaptiveAttacker,
    Attacker,
    run_campaign,
    static_extended,
    static_template,
)
from qe.exec.attack_model import AttackSpec
from qe.exec.sandbox import LocalSandbox
from qe.exec.sandbox_envs import ENVS
from qe.exec.sandbox_runner import AttackOutcome, run_attack
from qe.ports import SandboxLimits

BUDGET_MAX = 8
BUDGETS = (1, 2, 4, 8)
VARIANTS = ("clean", "seeded")
SEED = 0
ATTACKERS: tuple[str, ...] = ("static_template", "static_extended", "adaptive_mutation")
PREREG = Path(__file__).with_name("m4_preregistration.md")


def _make(name: str) -> Attacker:
    if name == "static_template":
        return static_template()
    if name == "static_extended":
        return static_extended()
    if name == "adaptive_mutation":
        return AdaptiveAttacker()
    raise ValueError(name)


async def run_all(ledger: Ledger) -> None:
    limits = SandboxLimits(
        max_calls=10_000, max_tokens=0
    )  # budgets are per campaign, see run_campaign
    for variant in VARIANTS:
        async with LocalSandbox().session(limits) as session:

            def run_one(
                spec: AttackSpec, variant: str = variant, session: Any = session
            ) -> AttackOutcome:
                return run_attack(
                    ENVS[spec.env],
                    spec,
                    variant=variant,
                    seed=SEED,
                    session=session,
                    ledger=ledger,
                    attacker=spec.attacker_class,
                    attacker_kind=ProducerKind.DETERMINISTIC,
                )

            for pair in PAIRS:
                run_one(baseline_attack(pair))
                for name in ATTACKERS:
                    run_campaign(_make(name), pair, BUDGET_MAX, run_one)


def results_from_ledger(ledger: Ledger) -> dict[str, Any]:
    """Pure function of the ledger: every number in the report comes from here."""
    first: dict[tuple[str, str], dict[str, int | None]] = defaultdict(dict)
    surfaces: dict[str, str] = {}
    utility: dict[str, list[bool]] = defaultdict(list)
    for entry in ledger.entries():
        ev = entry.event
        if ev.type is EventType.ATTACK_ATTEMPTED:
            atk = ev.payload["attack"]
            surfaces[atk["pair_id"]] = atk["surface"]
        elif ev.type is EventType.EVIDENCE_RECORDED and "outcome" in ev.payload:
            o = ev.payload["outcome"]
            slot = first[(o["variant"], o["attacker_class"])]
            slot.setdefault(o["pair_id"], None)
            if o["breached"] and slot[o["pair_id"]] is None:
                slot[o["pair_id"]] = o["attempt_index"] + 1
            if o["attacker_class"] == "baseline_none" and o["utility_ok"] is not None:
                utility[o["variant"]].append(bool(o["utility_ok"]))
    out: dict[str, Any] = {"asr": {}, "paired_seeded": [], "controls": {}, "per_surface_seeded": {}}
    for (variant, cls), fs in sorted(first.items()):
        if cls == "baseline_none":
            k = sum(v is not None for v in fs.values())
            out["controls"][f"baseline_{variant}"] = {"breaches": k, "pairs": len(fs)}
            continue
        out["asr"].setdefault(variant, {})[cls] = [
            asdict(asr_at_budget(fs, b, cls)) for b in BUDGETS
        ]
        if variant == "clean":
            k = sum(v is not None for v in fs.values())
            out["controls"][f"clean_attacked_{cls}"] = {"breaches": k, "pairs": len(fs)}
    seeded = {cls: fs for (v, cls), fs in first.items() if v == "seeded" and cls != "baseline_none"}
    comps = [
        ("adaptive_mutation", "static_template", [4]),
        ("adaptive_mutation", "static_extended", list(BUDGETS)),
        ("static_extended", "static_template", list(BUDGETS)),
    ]
    for a, b, budgets in comps:
        for bud in budgets:
            out["paired_seeded"].append(asdict(paired_comparison(seeded[a], seeded[b], bud, a, b)))
    for cls, fs in sorted(seeded.items()):
        table: dict[str, dict[str, int]] = defaultdict(lambda: {"pairs": 0, "breached_at_8": 0})
        for pair, ok in fs.items():
            table[surfaces[pair]]["pairs"] += 1
            table[surfaces[pair]]["breached_at_8"] += ok is not None
        out["per_surface_seeded"][cls] = dict(table)
    out["baseline_utility_ok"] = {v: [sum(x), len(x)] for v, x in utility.items()}
    out["ledger"] = {"length": len(ledger), "head": ledger.head()}
    return out


def render_markdown(res: dict[str, Any]) -> str:
    lines = [
        "# M4 results (FakeLLM sandbox; plumbing check, not a real-world claim)",
        "",
        "n = 12 pairs; intervals ignore within-surface correlation. Source: ledger only.",
        "",
        "## ASR@budget (Clopper-Pearson 95%)",
        "",
        "| variant | attacker | b | ASR | 95% CI |",
        "|---|---|---|---|---|",
    ]
    for variant, by_cls in res["asr"].items():
        for cls, rows in by_cls.items():
            lines += [
                f"| {variant} | {cls} | {r['budget']} | {r['successes']}/{r['n_pairs']} "
                f"| [{r['lower']:.2f}, {r['upper']:.2f}] |"
                for r in rows
            ]
    lines += [
        "",
        "## Paired comparisons on seeded (Newcombe 95% + exact McNemar)",
        "",
        "| a | b | budget | a only | b only | diff | 95% CI | McNemar p |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {r['a_label']} | {r['b_label']} | {r['budget']} | {r['a_only']} | {r['b_only']} "
        f"| {r['diff']:+.2f} | [{r['lower']:+.2f}, {r['upper']:+.2f}] | {r['mcnemar_p']:.3f} |"
        for r in res["paired_seeded"]
    ]
    lines += ["", "## Controls (expected 0 breaches)", ""]
    lines += [f"* {k}: {v['breaches']}/{v['pairs']}" for k, v in sorted(res["controls"].items())]
    lines += ["", f"Ledger: {res['ledger']['length']} events, head `{res['ledger']['head']}`."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("bench/results/m4"))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    db = args.out / "ledger.sqlite"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    ledger = SQLiteLedger(db)
    asyncio.run(run_all(ledger))
    res = results_from_ledger(ledger)
    res["preregistration_sha256"] = hashlib.sha256(PREREG.read_bytes()).hexdigest()
    (args.out / "results.json").write_text(
        json.dumps(res, indent=2, sort_keys=True), encoding="utf-8"
    )
    (args.out / "REPORT.md").write_text(render_markdown(res), encoding="utf-8")
    ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
