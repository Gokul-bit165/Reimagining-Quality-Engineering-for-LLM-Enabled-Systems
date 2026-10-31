"""Assemble the QA report (a JSON-serialisable dict) from a ReportInput. Deterministic."""

from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from typing import Any

from qe.qareport.models import EvidenceInput, ReportInput
from qe.qareport.rubric import remediation, rubric
from qe.qareport.sections import build_target
from qe.qareport.stats_util import rate
from qe.realeval import scoring
from qe.realeval.assemble import MIN_N_NOTE, root_ids
from qe.stats.paired import mcnemar_exact

SCHEMA = "qe.qa-report/1"


def _methodology(inp: ReportInput) -> dict[str, Any]:
    src: Counter[str] = Counter()
    ops: Counter[str] = Counter()
    for t in inp.targets:
        for it in t.items_planned:
            src[it["source"]] += 1
            op = (it.get("lineage") or {}).get("operator")
            if op:
                ops[str(op)] += 1
    first = inp.targets[0]
    return {
        "test_derivation": {
            "items_by_source": dict(sorted(src.items())),
            "variant_operators": dict(sorted(ops.items())),
            "explanation": [
                "user: question/reference pairs supplied by the owner of the application.",
                "generated: questions drafted from the supplied documents by a model; advisory "
                "until a human confirms them, and never part of the decision while advisory.",
                "security: fixed adversarial probes (prompt injection, forbidden URL, planted "
                "canary exfiltration) judged by outcome oracles.",
                "variants: deterministic mutations (paraphrase, typo, injection wrapper, risk "
                "scenario operators) seeded for replay; a variant shares its parent's root."],
        },
        "oracles": [
            "Security verdicts come from deterministic outcome oracles run on the recorded "
            "answer (marker in output, forbidden-domain predicate, canary at sink): never from "
            "a model.",
            "Quality verdicts come from deterministic lexical scoring (qe.realeval.scoring). "
            "An optional LLM judge, if configured, is advisory and recorded separately; it is "
            "never part of a verdict."],
        "scoring_rules": {
            "constants": {"correct_recall": scoring.CORRECT_RECALL,
                          "numeric_recall": scoring.NUMERIC_RECALL,
                          "support_recall": scoring.SUPPORT_RECALL,
                          "negation_window_tokens": scoring.NEGATION_WINDOW},
            "rules": [
                "correct: reference contained in the answer, or all reference numbers present "
                "with token recall at or above numeric_recall, or token recall at or above "
                "correct_recall; refusals and negated references fail.",
                "faithful: every answer sentence is supported by the returned passage text "
                "(contained, or all numbers present and recall at or above support_recall).",
                "an item whose every gating check is unmeasurable is UNCHECKED, never a pass."],
            "known_limits": [
                "lexical proxies, not semantic truth; paraphrases that change meaning can pass",
                "grounding is not measured when the target returns ids or filenames only",
                "refusal detection is phrase-based and can misclassify unusual wording"]},
        "statistics": [
            "Rates are computed over distinct root questions, not raw items, so near-duplicate "
            "variants cannot inflate n; n_roots and n_items are both reported.",
            "Intervals are exact 95% Clopper-Pearson; no interval is reported for latency.",
            "Between targets: exact McNemar test on paired root outcomes, reported both raw and "
            "Bonferroni-adjusted over the pairs in the report.",
            f"Intervals with n below {MIN_N_NOTE} are flagged as too wide to conclude."],
        "independence": [
            "Verdicts are produced by deterministic code from recorded responses; models only "
            "propose tests and advisory judgements.",
            "A judge, if configured, must come from a different model family than the "
            "question generator (enforced at run time).",
            "The target is called through its public interface; the scorer does not see the "
            "target's internals."],
        "seeds": {t.name: t.config.get("seed") for t in inp.targets},
        "repeats": {t.name: t.config.get("repeats") for t in inp.targets},
        "severity_rubric": {"id": rubric()["rubric_id"], "version": rubric()["version"],
                            "levels": rubric()["levels"],
                            "note": "labels defects only; never feeds the verdict"},
        "guidance": {"id": remediation()["guidance_id"], "version": remediation()["version"],
                     "label": remediation()["label"]},
        "reference_run": first.name,
    }


def _roots_pass(ev: EvidenceInput) -> dict[str, bool]:
    rows = ev.result["items"]
    roots = root_ids(rows)
    out: dict[str, bool] = {}
    for r in rows:
        if r["passed"] is None:
            continue
        rid = roots[r["id"]]
        out[rid] = out.get(rid, True) and bool(r["passed"])
    return out


def _comparison(inp: ReportInput) -> dict[str, Any] | None:
    if len(inp.targets) < 2:
        return None
    passes = {t.name: _roots_pass(t) for t in inp.targets}
    metrics_names = list(inp.targets[0].result["metrics"])
    table = []
    for name in metrics_names:
        row: dict[str, Any] = {"metric": name, "targets": {}}
        for t in inp.targets:
            m = t.result["metrics"][name]
            row["targets"][t.name] = {"value": m["value"], "ci_low": m["ci_low"],
                                      "ci_high": m["ci_high"], "n": m["n"]}
        table.append(row)
    pairs = []
    n_pairs = len(list(combinations(inp.targets, 2)))
    for a, b in combinations(inp.targets, 2):
        shared = sorted(set(passes[a.name]) & set(passes[b.name]))
        res = mcnemar_exact([passes[a.name][r] for r in shared],
                            [passes[b.name][r] for r in shared])
        pairs.append({
            "a": a.name, "b": b.name, "shared_roots": len(shared),
            "excluded_roots": len(set(passes[a.name]) ^ set(passes[b.name])),
            "a_only_pass": res.b, "b_only_pass": res.c, "discordant": res.discordant,
            "p_value_exact": res.p_value, "comparisons_in_report": n_pairs,
            "p_value_bonferroni": min(1.0, res.p_value * n_pairs),
            "pass_rate_a": rate(sum(passes[a.name][r] for r in shared), len(shared)),
            "pass_rate_b": rate(sum(passes[b.name][r] for r in shared), len(shared))})
    sets = {tuple(sorted(i["id"] for i in t.items_planned)) for t in inp.targets}
    return {"metrics": table, "pairs": pairs,
            "same_item_set": len(sets) == 1,
            "latency": {t.name: {"p50": t.result["metrics"]["latency_p50_s"]["value"],
                                 "p95": t.result["metrics"]["latency_p95_s"]["value"]}
                        for t in inp.targets},
            "note": "Paired on root questions both targets were checked on. p-values are "
                    "exact two-sided McNemar; the Bonferroni column multiplies by the number of "
                    "pairs in this report. A non-significant result is not evidence of "
                    "equivalence."}


def _executive(inp: ReportInput, targets: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for t in targets:
        rec = t["recommendation"]
        rows.append({"target": t["name"], "verdict": rec["verdict"], "status": rec["status"],
                     "policy": f"{rec['policy']['id']}@{rec['policy']['version']}",
                     "policy_is_example": rec["policy"]["example_only"],
                     "headline_risks": t["headline_risks"], "not_assessed": t["not_assessed"],
                     "defect_clusters": len(t["defects"])})
    pending = any(r["status"] == "pending_review" for r in rows)
    return {"targets": rows,
            "integrity_failed": [t["name"] for t in targets
                                 if not t["appendix"]["ledger"]["chain_ok"]],
            "status_note": ("PENDING: this is a recommendation from measured evidence; it is "
                            "not a release approval until a human signs off." if pending else
                            "A human review is recorded in the sign-off section."),
            "example_policy_warning": any(r["policy_is_example"] for r in rows)}


def build_report(inp: ReportInput) -> dict[str, Any]:
    targets = [build_target(t) for t in inp.targets]
    report = {
        "schema": SCHEMA, "kind": inp.kind, "id": inp.id, "title": inp.title,
        "created_epoch": inp.created, "tool": inp.tool.model_dump(),
        "notes": list(inp.notes),
        "executive_summary": _executive(inp, targets),
        "methodology": _methodology(inp),
        "comparison": _comparison(inp),
        "targets": targets,
    }
    # JSON round trip with sorted keys: the in-memory report is exactly what report.json holds,
    # so renderings of the live report and of a reloaded report.json are identical.
    normalized: dict[str, Any] = json.loads(json.dumps(report, sort_keys=True, allow_nan=False))
    return normalized
