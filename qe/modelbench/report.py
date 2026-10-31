"""Benchmark report: derived from the ledger only. No composite score, no ranking claim unless
the 95% intervals of two models do not overlap on a metric."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from qe.core.events import EventType
from qe.core.ledger import Ledger
from qe.modelbench.suite import METRICS
from qe.stats.estimators import rate_estimate

BAD = {"contradicted", "unsupported"}
NOT_EVAL = {"unverifiable", "source_unavailable", "abstain"}


def build_bench_report(ledger: Ledger) -> dict[str, Any]:
    bench: dict[str, Any] = {}
    questions: dict[str, dict[str, Any]] = {}
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outputs: dict[tuple[str, str], str] = {}
    states: dict[tuple[str, str, str], list[tuple[str, str | None]]] = defaultdict(list)
    for e in ledger.entries():
        p, t = e.event.payload, e.event.type
        if t is EventType.EVIDENCE_RECORDED and p.get("kind") == "benchmark":
            bench = p
        elif t is EventType.EVIDENCE_RECORDED and p.get("kind") == "suite":
            questions = {x["test_id"]: x for x in p["tests"]}
        elif t is EventType.RUN_RECORDED:
            runs[p["model"]].append(p)
            if p["repeat"] == 0 and not p["error"]:
                outputs[(p["model"], p["test_id"])] = p["output"]
        elif t is EventType.VERDICT_ISSUED:
            states[(p["model"], p["metric"], p["case_id"])].append(
                (p["verdict"]["state"], p["verdict"].get("detail")))
    models: dict[str, Any] = {}
    for model in bench.get("models", []):
        rs = runs[model]
        errors = [r for r in rs if r["error"]]
        per_metric: dict[str, Any] = {}
        for metric in METRICS:
            cases = {c: v for (m, mt, c), v in states.items() if m == model and mt == metric}
            failed = [c for c, v in cases.items() if any(s in BAD for s, _ in v)]
            passed = [c for c, v in cases.items() if c not in failed
                      and any(s not in NOT_EVAL for s, _ in v)]
            na = len(cases) - len(failed) - len(passed)
            row: dict[str, Any] = {"failed": len(failed), "passed": len(passed),
                                   "not_evaluable": na, "examples": []}
            if failed or passed:
                n = len(failed) + len(passed)
                row["rate"] = rate_estimate(len(failed), n, 0.95).model_dump()
            for c in failed[:3]:
                detail = next((d for s, d in cases[c] if s in BAD and d), None)
                q = questions.get(c, {})
                row["examples"].append({"test_id": c, "style": q.get("style"),
                                        "question": q.get("question"),
                                        "expected": q.get("expected"),
                                        "output": outputs.get((model, c), "")[:300],
                                        "detail": detail})
            per_metric[metric] = row
        models[model] = {
            "simulated": bench["simulated"][model], "metrics": per_metric,
            "runs": {"total": len(rs), "errors": len(errors),
                     "error_kinds": sorted({str(r["error"]) for r in errors})[:3]}}
    comparison = []
    for metric, meaning in METRICS.items():
        cells = {m: models[m]["metrics"][metric].get("rate") for m in models}
        statements = []
        names = [m for m, r in cells.items() if r]
        for a in names:
            for b in names:
                if a != b and cells[a]["upper"] < cells[b]["lower"]:
                    statements.append(f"{a} fails less often than {b} "
                                      f"(95% intervals do not overlap)")
        comparison.append({"metric": metric, "meaning": meaning, "cells": cells,
                           "separable": statements})
    return {"benchmark": {k: bench.get(k) for k in
                          ("models", "focus", "n_tests", "repeats", "suite", "suite_generator",
                           "pace_s")},
            "models": models, "comparison": comparison,
            "tests": list(questions.values()),
            "ledger": {"entries": len(ledger), "head": ledger.head(),
                       "verified": ledger.verify().ok},
            "notes": ["Rates are failures per evaluable test with exact 95% intervals; there is "
                      "no composite score and no ranking unless intervals do not overlap.",
                      "Calls that failed are missing evidence, never counted as failures.",
                      "Simulated reference models are deterministic stand-ins, not real LLMs.",
                      "Abstention is detected by keywords; free-text judging is not performed."]}
