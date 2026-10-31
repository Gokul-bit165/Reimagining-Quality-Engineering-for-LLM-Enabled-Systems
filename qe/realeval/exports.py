"""Exports of a finished evaluation: reusable dataset (JSONL), evidence report, monitoring plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qe.core.schemas import Policy
from qe.realeval.assemble import example_policy

PLAN_DOC = Path(__file__).resolve().parents[2] / "docs" / "MONITORING_PLAN.md"
TRIGGERS = (
    "any model or prompt version change in the target app",
    "any knowledge-base / document corpus update",
    "any tool or permission change",
    "a fixed schedule (length is a policy choice, not set here)",
)


def dataset_jsonl(result: dict[str, Any]) -> str:
    """One JSON object per line: the test (question, reference, probe, lineage) and its label."""
    lines = []
    for row in result["items"]:
        lines.append(json.dumps({
            "id": row["id"], "question": row["question"],
            "reference_answer": row["reference_answer"], "source": row["source"],
            "answerable": row["answerable"], "risk": row["risk"], "lineage": row["lineage"],
            "label": {"passed": row["passed"], "failure_class": row["failure_class"],
                      "failure_reason": row["failure_reason"]},
            "evaluation_id": result["id"],
        }, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")


def _fmt(m: dict[str, Any]) -> str:
    if m["value"] is None:
        return f"n/a (n={m['n']})"
    if m["ci_low"] is None:
        return f"{m['value']:.3f} (n={m['n']})"
    return f"{m['value']:.3f} [{m['ci_low']:.3f}, {m['ci_high']:.3f}] (n={m['n']})"


def report_markdown(result: dict[str, Any]) -> str:
    d = result["decision"]
    out = [f"# Evaluation report {result['id']}", "",
           f"Project: `{result['project_id']}`  |  State: {result['state']}", ""]
    out += ["> Use anonymised data only when testing; do not load real personal "
            "data.", "",
            f"## Recommendation: {d['verdict']} ({d['status']})", "", d["explanation"], ""]
    out += [f"- {r}" for r in d["reasons"]]
    if d.get("policy_is_example"):
        out += ["", "_The policy used is an EXAMPLE, not a real risk appetite._"]
    out += ["", "## Scorecard", "", "| Dimension | Value [95% CI] | Note |", "|---|---|---|"]
    out += [f"| {k} | {_fmt(v)} | {v['note']} |" for k, v in result["scorecard"].items()]
    out += ["", "## Failure taxonomy", ""]
    out += [f"- **{k}** {v['name']}: {v['count']}" for k, v in result["failure_taxonomy"].items()
            ] or ["- none"]
    reg = result["regression"]
    out += ["", "## Regression", "",
            f"Suite re-run: {reg['suite_rerun']}; fixed: {len(reg['fixed'])}; still failing: "
            f"{len(reg['still_failing'])}; new failures: {len(reg['new_failures'])}", "",
            "## Metrics", ""]
    out += [f"- {k}: {_fmt(v)}" for k, v in result["metrics"].items()]
    out += ["", "## Failed items", ""]
    out += [f"- `{r['id']}` [{r['failure_class']}] {r['question']} -> {r['failure_reason']}"
            for r in result["items"] if r["passed"] is False] or ["- none"]
    if d.get("signoff"):
        s = d["signoff"]
        out += ["", f"## Human review: {s['decision']} by {s['reviewer']}", "", s["rationale"]]
    return "\n".join(out) + "\n"


def _watch(name: str, m: dict[str, Any], appetite: float, required: bool) -> dict[str, Any]:
    """One monitored metric: failure rate vs the policy appetite, from the evaluation itself."""
    if m["n"] == 0 or m["value"] is None or m["ci_low"] is None:
        status, rate, lo, hi = "unmeasured", None, None, None
    else:
        flip = name != "error_rate"  # rates are success rates except error_rate
        rate = (1 - m["value"]) if flip else m["value"]
        lo = (1 - m["ci_high"]) if flip else m["ci_low"]
        hi = (1 - m["ci_low"]) if flip else m["ci_high"]
        status = "failing" if lo > appetite else ("uncertain" if hi > appetite else "within")
    return {"metric": name, "required": required, "status": status, "failure_rate": rate,
            "failure_rate_ci": [lo, hi], "appetite": appetite, "n_roots": m.get("n_roots", m["n"])}


def monitoring_plan(result: dict[str, Any], policy: dict[str, Any] | None,
                    monitoring: dict[str, Any] | None) -> dict[str, Any]:
    """A plan derived from THIS evaluation: which metrics failed or could not be measured, which
    failure classes occurred, what to re-run. The cadence is null unless the user set it."""
    pol = Policy.model_validate(policy) if policy else example_policy()
    cadence = (monitoring or {}).get("cadence_days")
    failed = [r["id"] for r in result["items"] if r["passed"] is False]
    watch = [_watch(n, result["metrics"][n], a, n in pol.required_evidence)
             for n, a in pol.risk_appetite.items() if n in result["metrics"]]
    classes = {k: v["count"] for k, v in result["failure_taxonomy"].items()}
    triggers = list(TRIGGERS)
    if {"QE-INJ", "LLM02"} & set(classes):
        triggers.insert(0, "security probes failed: re-run them first after ANY prompt, retrieval "
                           "or tool-permission change")
    if "QE-RET" in classes:
        triggers.insert(0, "retrieval failures seen: re-run after any retriever, embedding or "
                           "chunking change")
    return {
        "evaluation_id": result["id"], "project_id": result["project_id"],
        "derived_from": {"failed_items": len(failed), "failure_classes": classes,
                         "unchecked_items": (result.get("unchecked") or {}).get("count", 0)},
        "rerun": {"failed_items": failed,
                  "security_probes": [r["id"] for r in result["items"]
                                      if r["source"] == "security"],
                  "regression_suite": f"GET /api/projects/{result['project_id']}/regression"},
        "watch": watch,
        "attention": [w["metric"] for w in watch if w["status"] in ("failing", "uncertain")],
        "unmeasured_required": [w["metric"] for w in watch
                                if w["required"] and w["status"] == "unmeasured"],
        "cadence_days": cadence,
        "cadence_note": ("user-declared" if cadence else
                         "NOT SET: the cadence is a policy choice and is not invented here"),
        "drift_triggers": triggers,
        "thresholds": {m: {"max_failure_rate": a, "policy": f"{pol.policy_id}@{pol.version}",
                           "example": pol.example_only}
                       for m, a in pol.risk_appetite.items() if m in pol.required_evidence},
        "alert_rule": "re-evaluate on a trigger; alert when a metric's 95% interval lies wholly "
                      "above its appetite, or an oracle-confirmed security breach appears",
        "status": "a plan, not a running system: nothing here is scheduled",
        "markdown": PLAN_DOC.read_text("utf-8") if PLAN_DOC.is_file() else "",
    }
