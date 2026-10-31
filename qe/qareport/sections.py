"""Per-target report sections derived from one EvidenceInput (no I/O, no clock, no model)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from qe.core.ids import content_id
from qe.core.schemas import Policy
from qe.qareport.defects import build_defects, build_grounding, build_security
from qe.qareport.models import EvidenceInput
from qe.qareport.stats_util import latency_summary, rate
from qe.realeval.assemble import (
    MIN_N_NOTE,
    SCORECARD,
    TAXONOMY_NAMES,
    example_policy,
    root_ids,
)
from qe.realeval.exports import monitoring_plan

# failure class -> scorecard metrics that can detect it (mirrors assemble.classify)
CLASS_METRICS: dict[str, tuple[str, ...]] = {
    "QE-FAB": ("answer_correctness", "faithfulness", "refusal_correctness"),
    "QE-CIT": ("citation_validity",),
    "QE-CON": ("stability_pass_k",),
    "QE-RET": ("retrieval_hit_rate",),
    "QE-INJ": ("security_resistance",),
    "LLM02": ("security_resistance",),
    "QE-INC": ("completeness",),
    "target_error": ("error_rate",),
}


def policy_of(ev: EvidenceInput) -> Policy:
    raw = ev.config.get("policy")
    return Policy.model_validate(raw) if raw else example_policy()


def _scope(ev: EvidenceInput) -> dict[str, Any]:
    cfg = ev.config
    return {
        "name": ev.name, "evaluation_id": ev.eval_id, "project_id": ev.project_id,
        "state": ev.state, "created_epoch": ev.created,
        "endpoint_host": ev.meta.endpoint_host, "execution_mode": ev.meta.execution_mode,
        "authorization": {"attested": ev.meta.authorized, "attested_at": ev.meta.authorized_at},
        "versions": dict(ev.meta.versions), "meta_notes": list(ev.meta.notes),
        "documents": list(cfg.get("doc_names", [])), "seed": cfg.get("seed"),
        "repeats": cfg.get("repeats"), "max_questions": cfg.get("max_questions"),
        "budget": cfg.get("budget"), "risk_focus": list(cfg.get("risk_focus", [])),
        "include_security": cfg.get("include_security"),
        "notes": [*cfg.get("notes", []), *ev.source_notes],
        "dates_note": ("ledger events carry no timestamps; the date is the evaluation record's "
                       "creation time when supplied" if ev.created is None else ""),
    }


def _risk_label(row: dict[str, Any], scenarios: dict[str, str] | None = None) -> str:
    if scenarios and row["id"] in scenarios:
        return scenarios[row["id"]]
    if row["source"] == "security":
        return "security:" + str((row.get("probe") or {}).get("kind", "unknown"))
    return str(row.get("risk") or "baseline")


def _coverage(ev: EvidenceInput) -> dict[str, Any]:
    rows = ev.result["items"]
    done = {r["id"] for r in rows}
    planned_by: Counter[str] = Counter()
    for it in ev.items_planned:
        planned_by[_risk_label(it, ev.scenarios)] += 1
    matrix: dict[str, dict[str, Any]] = {}
    for r in rows:
        label = _risk_label(r, ev.scenarios)
        m = matrix.setdefault(label, {"executed": 0, "passed": 0, "failed": 0,
                                      "unchecked": 0, "classes": Counter()})
        m["executed"] += 1
        key = "unchecked" if r["passed"] is None else ("passed" if r["passed"] else "failed")
        m[key] += 1
        if r["failure_class"]:
            m["classes"][r["failure_class"]] += 1
    rows_out = []
    for label in sorted(set(matrix) | set(planned_by)):
        m = matrix.get(label, {"executed": 0, "passed": 0, "failed": 0, "unchecked": 0,
                               "classes": Counter()})
        rows_out.append({"risk": label, "planned": planned_by.get(label, 0),
                         "executed": m["executed"], "passed": m["passed"],
                         "failed": m["failed"], "unchecked": m["unchecked"],
                         "classes": dict(sorted(m["classes"].items()))})
    metrics = ev.result["metrics"]
    taxonomy = []
    probe_kinds = {(r.get("probe") or {}).get("kind") for r in rows if r["source"] == "security"}
    for cls, mets in CLASS_METRICS.items():
        n_by = {m: metrics[m]["n"] for m in mets if m in metrics}
        measured = any(n > 0 for n in n_by.values())
        if cls == "LLM02" and "canary_exfiltration" not in probe_kinds:
            measured = False
        taxonomy.append({
            "class": cls, "name": TAXONOMY_NAMES.get(cls, cls), "metrics": list(mets),
            "n_roots": n_by, "status": "covered" if measured else "NOT MEASURED",
            "failures_observed": sum(1 for r in rows if r["failure_class"] == cls)})
    gaps = [f"taxonomy class {t['class']} ({t['name']}) has no measurable test in this run"
            for t in taxonomy if t["status"] != "covered" and t["class"] != "target_error"]
    not_run = [it["id"] for it in ev.items_planned if it["id"] not in done]
    if not_run:
        gaps.append(f"{len(not_run)} planned item(s) were not executed")
    unchecked = ev.result["unchecked"]["count"]
    if unchecked:
        gaps.append(f"{unchecked} executed item(s) could not be checked (no reference answer and "
                    "answerable not declared)")
    for note in ev.config.get("notes", []):
        if "no mapped test scenario" in note or note.startswith("TRUNCATED"):
            gaps.append(note)
    if not ev.config.get("include_security", True):
        gaps.append("security probes were switched off")
    return {"planned": len(ev.items_planned), "executed": len(rows), "unchecked": unchecked,
            "not_executed_ids": not_run, "matrix": rows_out, "taxonomy": taxonomy, "gaps": gaps}


def _latency_and_errors(ev: EvidenceInput) -> dict[str, Any]:
    calls = [c for runs in ev.runs.values() for c in runs]
    ok = [float(c["latency_s"]) for c in calls if not c["error"]]
    errors = [c for c in calls if c["error"]]
    kinds = Counter(str(c["error"]).split(":", 1)[0] for c in errors)
    return {"latency_s": latency_summary(ok), "calls": len(calls),
            "error_calls": rate(len(errors), len(calls)),
            "errors_by_type": dict(sorted(kinds.items())),
            "latency_note": "wall-clock seconds recorded by the harness for successful calls; "
                            "single client, no load, network included"}


def _results(ev: EvidenceInput, policy: Policy) -> dict[str, Any]:
    res = ev.result
    card = []
    for dim, metric, _ in SCORECARD:
        v = res["scorecard"][dim]
        card.append({"dimension": dim, "metric": metric, "value": v["value"],
                     "ci_low": v["ci_low"], "ci_high": v["ci_high"], "n_roots": v["n_roots"],
                     "n_items": v.get("n_items"), "note": v["note"],
                     "appetite_max_failure": policy.risk_appetite.get(metric),
                     "required": metric in policy.required_evidence})
    metrics = [{"metric": k, "value": v["value"], "ci_low": v["ci_low"], "ci_high": v["ci_high"],
                "n": v["n"], "n_items": v.get("n_items"), "note": v["note"]}
               for k, v in res["metrics"].items()]
    return {"scorecard": card, "metrics": metrics, "sample": res["sample"],
            **_latency_and_errors(ev)}


def _regression(ev: EvidenceInput) -> dict[str, Any]:
    reg = ev.result["regression"]
    baseline = len(ev.config.get("prior_pass", {}))
    assessable = bool(reg["suite_rerun"] or baseline)
    return {**reg, "baseline_items": baseline, "assessable": assessable,
            "note": "" if assessable else
            "no regression suite was re-run and no prior evaluation exists: regression status "
            "cannot be assessed (this is a first run, not a clean bill)"}


def _review(ev: EvidenceInput) -> dict[str, Any]:
    decision = ev.result["decision"]
    sign = [s for s in ev.signoffs if s.get("kind") != "item_confirmation"]
    last = sign[-1] if sign else None
    status = "pending_review" if last is None else (
        "approved" if last.get("approved") else "rejected")
    return {"status": status, "signoffs": sign, "confirmations": list(ev.confirmations),
            "decision_id": decision["decision_id"],
            "note": ("no human has reviewed this recommendation" if last is None else ""),
            "decision_matches_signoff": (None if last is None else
                                         last.get("decision_id") == decision["decision_id"])}


def _recommendation(ev: EvidenceInput, policy: Policy, review: dict[str, Any]) -> dict[str, Any]:
    d = ev.result["decision"]
    return {"verdict": d["verdict"], "status": review["status"], "explanation": d["explanation"],
            "reasons": list(d["reasons"]), "decision_id": d["decision_id"],
            "policy": {"id": policy.policy_id, "version": policy.version,
                       "example_only": policy.example_only,
                       "required_evidence": list(policy.required_evidence),
                       "risk_appetite": dict(policy.risk_appetite),
                       "warning": ("EXAMPLE POLICY: not a real risk appetite; the verdict "
                                   "below does not reflect any organisation's release criteria"
                                   if policy.example_only else "")},
            "rule": "The verdict is computed by deterministic policy code from the measured 95% "
                    "intervals; severity labels and this report's prose never feed it."}


def _monitoring(ev: EvidenceInput) -> dict[str, Any]:
    res = ev.result
    like = {"id": ev.eval_id, "project_id": ev.project_id, "items": res["items"],
            "metrics": res["metrics"], "failure_taxonomy": res["failure_taxonomy"],
            "unchecked": res["unchecked"]}
    plan = monitoring_plan(like, ev.config.get("policy"), ev.monitoring)
    plan.pop("markdown", None)
    return plan


def limitations(ev: EvidenceInput, policy: Policy) -> list[str]:
    res = ev.result
    out = [
        "Scoring is lexical (token recall, number and negation checks, containment): it can "
        "miss paraphrases that change meaning and can reject correct answers phrased differently.",
        "Grounding checks compare answer sentences with the passage text the target returned; "
        "they are not semantic entailment, and are not measured when only ids are returned.",
        "A report covers one endpoint, one configuration and one point in time.",
    ]
    small = [k for k, v in res["metrics"].items()
             if 0 < v["n"] < MIN_N_NOTE and v.get("ci_low") is not None]
    if small:
        out.append(f"Small samples (n < {MIN_N_NOTE} root questions) give very wide intervals "
                   f"for: {', '.join(small)}.")
    if int(ev.config.get("repeats", 1)) == 1:
        out.append("Single run per item (repeats = 1): nondeterminism of the target was not "
                   "measured.")
    if res["advisory"]["unconfirmed"]:
        out.append(f"{res['advisory']['unconfirmed']} LLM-drafted item(s) are advisory and "
                   "excluded from the decision until a human confirms them.")
    if res["unchecked"]["count"]:
        out.append(f"{res['unchecked']['count']} item(s) were unchecked and excluded from every "
                   "rate.")
    if policy.example_only:
        out.append("The policy is an example, not a real risk appetite.")
    if not ev.chain_ok:
        out.append(f"LEDGER INTEGRITY FAILED: {ev.chain_reason}. Figures cannot be trusted.")
    out.append("Latency is measured by a single client without load and is not a capacity test.")
    return out


def _headline_risks(defects: list[dict[str, Any]], monitoring: dict[str, Any],
                    security: dict[str, Any]) -> list[str]:
    out = []
    sev = Counter(d["severity"] for d in defects)
    if defects:
        out.append(f"{len(defects)} defect cluster(s): " + ", ".join(
            f"{n} {s}" for s, n in sev.most_common()))
    if security.get("ran") and security.get("overall") and security["overall"]["k"]:
        o = security["overall"]
        out.append(f"security: attack success {o['k']}/{o['n']} root probes "
                   f"(95% CI {o['ci_low']:.3f} to {o['ci_high']:.3f})")
    for w in monitoring["watch"]:
        if w["status"] in ("failing", "uncertain"):
            out.append(f"{w['metric']}: {w['status']} against appetite {w['appetite']} "
                       f"(failure rate {w['failure_rate']:.3f}, CI "
                       f"{w['failure_rate_ci'][0]:.3f} to {w['failure_rate_ci'][1]:.3f})")
    return out


def _not_assessed(ev: EvidenceInput, coverage: dict[str, Any], policy: Policy) -> list[str]:
    out = [g for g in coverage["gaps"]]
    metrics = ev.result["metrics"]
    for name in policy.required_evidence:
        m = metrics.get(name)
        if m is None or m["n"] == 0:
            out.append(f"required metric {name} could not be measured")
    out.append("Semantic correctness beyond lexical matching; behaviour under load; "
               "non-tested languages and content domains; future drift.")
    return list(dict.fromkeys(out))


def _appendix(ev: EvidenceInput) -> dict[str, Any]:
    roots = {r["id"]: r for r in ev.result["items"]}
    rid = root_ids(list(roots.values()))
    items = []
    for r in ev.result["items"]:
        lat = [c["latency_s"] for c in ev.runs.get(r["id"], []) if not c["error"]]
        items.append({"id": r["id"], "root": rid[r["id"]], "source": r["source"],
                      "risk": r.get("risk"), "answerable": r.get("answerable"),
                      "passed": r["passed"], "failure_class": r["failure_class"],
                      "repeat_passes": r["scores"].get("repeat_passes"),
                      "latency_mean_s": (sum(lat) / len(lat)) if lat else None,
                      "question": r["question"]})
    cfg_hash = content_id({**ev.config, "items": ev.items_planned})
    return {"items": items, "config_hash": cfg_hash,
            "ledger": {"head": ev.head, "entries": ev.length, "chain_ok": ev.chain_ok,
                       "chain_reason": ev.chain_reason},
            "config": {k: v for k, v in ev.config.items() if k != "prior_pass"}}


def build_target(ev: EvidenceInput) -> dict[str, Any]:
    policy = policy_of(ev)
    metrics = ev.result["metrics"]
    defects = build_defects(ev)
    security = build_security(ev, metrics)
    monitoring = _monitoring(ev)
    coverage = _coverage(ev)
    review = _review(ev)
    by_class: dict[str, int] = defaultdict(int)
    for d in defects:
        by_class[d["failure_class"]] += 1
    return {
        "name": ev.name, "scope": _scope(ev), "coverage": coverage,
        "results": _results(ev, policy), "defects": defects, "security": security,
        "grounding": build_grounding(ev), "regression": _regression(ev),
        "recommendation": _recommendation(ev, policy, review), "review": review,
        "monitoring": monitoring, "limitations": limitations(ev, policy),
        "headline_risks": _headline_risks(defects, monitoring, security),
        "not_assessed": _not_assessed(ev, coverage, policy),
        "advisory": ev.result["advisory"], "appendix": _appendix(ev),
    }
