"""Evidence Pack v0, generated ONLY from the ledger (R10); pure and deterministic.

Unit of analysis is the TEST CASE (a case fails for a metric if any of its repeats
produced a failing verdict), so repeats of one case are not counted as independent
trials. Verdicts that are not evaluable (unverifiable / source unavailable / abstain) are
reported separately and never counted as pass or fail (R9).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from qe.core.events import EventType
from qe.core.ids import canonical_json
from qe.core.ledger import Ledger
from qe.core.schemas import ClaimState, Policy
from qe.policy.engine import MetricEvidence, decide
from qe.stats.estimators import rate_estimate

FAILING = {ClaimState.CONTRADICTED.value, ClaimState.UNSUPPORTED.value}
NOT_EVALUABLE = {ClaimState.UNVERIFIABLE.value, ClaimState.SOURCE_UNAVAILABLE.value,
                 ClaimState.ABSTAIN.value}
CLAIMS_NOT_MADE = (
    "Rates describe the sampled test cases only, not unseen inputs.",
    "Missing/not-evaluable evidence is excluded from rates and listed above.",
    "No verifier-independence (n_eff) analysis in v0: deterministic checks only.",
    "No claim about production behaviour or real-world harm.",
)


def build_pack(ledger: Ledger, policy: Policy, confidence: float = 0.95) -> dict[str, Any]:
    entries = list(ledger.entries())
    runs = [e for e in entries if e.event.type is EventType.RUN_RECORDED]
    levels = sorted({e.event.payload["visibility_level"] for e in runs})
    errors = sorted(e.event.key for e in runs if e.event.payload.get("error"))
    missing = sorted(k for e in entries if e.event.type is EventType.MISSING_EVIDENCE
                     for k in e.event.payload.get("unrun", []))
    per_metric: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"fail": set(), "pass": set(), "n/a": set()})
    evidence: dict[str, list[str]] = defaultdict(list)
    for e in entries:
        if e.event.type is not EventType.VERDICT_ISSUED:
            continue
        p = e.event.payload
        state = p["verdict"]["state"]
        bucket = "fail" if state in FAILING else "n/a" if state in NOT_EVALUABLE else "pass"
        per_metric[p["metric"]][bucket].add(p["case_id"])
        evidence[p["metric"]].append(e.event.key)
    metrics: list[dict[str, Any]] = []
    for name in sorted(per_metric):
        b = per_metric[name]
        failed = b["fail"]
        passed = b["pass"] - failed
        n = len(failed) + len(passed)
        row: dict[str, Any] = {"metric": name, "failed_cases": len(failed),
                               "passed_cases": len(passed),
                               "not_evaluable_cases": len(b["n/a"] - failed - passed)}
        if n:
            est = rate_estimate(len(failed), n, confidence)
            row["failure_rate"] = est.model_dump()
        metrics.append(row)
    evidences = [
        MetricEvidence(name=r["metric"], failures=r["failed_cases"],
                       trials=r["failed_cases"] + r["passed_cases"],
                       lower=r["failure_rate"]["lower"], upper=r["failure_rate"]["upper"],
                       evidence_ids=tuple(sorted(evidence[r["metric"]])))
        for r in metrics if "failure_rate" in r
    ]
    decision = decide(policy, evidences)
    return {
        "ledger": {"entries": len(entries), "head": ledger.head(),
                   "verified": ledger.verify().ok},
        "access": {"visibility_levels": levels,
                   "note": "Findings cannot be localised below this access level."},
        "runs": {"recorded": len(runs), "with_errors": errors, "unrun_budget_or_kill": missing},
        "policy": {"id": policy.policy_id, "version": policy.version,
                   "example_only": policy.example_only},
        "metrics": metrics,
        "decision": decision.model_dump(mode="json"),
        "human_signoff": "REQUIRED before any RELEASE (none recorded in v0)",
        "claims_not_made": list(CLAIMS_NOT_MADE),
    }


def render_json(pack: dict[str, Any]) -> str:
    return canonical_json(pack)


def render_markdown(pack: dict[str, Any]) -> str:
    d = pack["decision"]
    lines = ["# Evidence Pack v0", "",
             f"**Decision: {d['decision']}** (policy {d['policy_version']})", ""]
    lines += [f"- {c}" for c in d["conditions"]] + ["", "## Access",
              f"Visibility levels: {', '.join(pack['access']['visibility_levels']) or 'none'}",
              pack["access"]["note"], "", "## Metrics (failure rate per test case, exact 95% CI)"]
    for m in pack["metrics"]:
        fr = m.get("failure_rate")
        rate = (f"{fr['point']:.4f} [{fr['lower']:.4f}, {fr['upper']:.4f}]" if fr
                else "not estimable")
        lines.append(f"- {m['metric']}: failed {m['failed_cases']}, passed {m['passed_cases']}, "
                     f"not evaluable {m['not_evaluable_cases']}; rate {rate}")
    lines += ["", "## Runs", f"Recorded: {pack['runs']['recorded']}; "
              f"errors: {len(pack['runs']['with_errors'])}; "
              f"unrun (budget/kill): {len(pack['runs']['unrun_budget_or_kill'])}",
              "", "## Ledger", f"Entries: {pack['ledger']['entries']}; "
              f"head: {pack['ledger']['head']}; chain verified: {pack['ledger']['verified']}",
              "", "## Claims NOT made"] + [f"- {c}" for c in pack["claims_not_made"]]
    return "\n".join(lines) + "\n"
