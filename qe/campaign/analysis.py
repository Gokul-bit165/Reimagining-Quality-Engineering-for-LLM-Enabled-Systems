"""Pure analysis of recorded runs: verification, classification, scoring, comparison,
recommendation. Inputs are the plan and the ledger's recorded responses; no I/O, no clock, no
model, no randomness (replayable, R10). Verdicts come from qe.realeval's deterministic scoring
and qe.policy (R3); statistics from qe.stats and qe.campaign.paired_ci.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

from qe.campaign.paired_ci import newcombe_paired
from qe.core.schemas import Policy
from qe.realeval.assemble import MIN_N_NOTE, assemble, root_ids
from qe.stats.estimators import rate_estimate
from qe.stats.paired import mcnemar_exact

COMPARED = ("overall_pass_rate", "answer_correctness", "faithfulness", "citation_validity",
            "refusal_correctness", "injection_resistance")
_SCORE_KEY = {"answer_correctness": "correct", "faithfulness": "faithful",
              "citation_validity": "citation_valid", "refusal_correctness": "refusal_correct"}
MAX_TRIMMED_ITEMS = 300
ANSWER_PREVIEW = 400


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile on the sorted values (same rule as qe.realeval.assemble)."""
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def common_items(plan_cases: Sequence[Mapping[str, Any]], labels: Sequence[str],
                 runs: Mapping[str, Mapping[str, list[dict[str, Any]]]],
                 repeats: int) -> list[Mapping[str, Any]]:
    """Cases that every target answered on every repeat (the paired, comparable set)."""
    return [c for c in plan_cases
            if all(len(runs.get(lbl, {}).get(str(c["id"]), [])) >= repeats for lbl in labels)]


def verify(plan: Mapping[str, Any], cases: Sequence[Mapping[str, Any]], label: str,
           runs: Mapping[str, Mapping[str, list[dict[str, Any]]]], policy: Policy | None,
           incomplete: str | None, confirmed: Sequence[str]) -> dict[str, Any]:
    """Deterministic scoring + policy decision for one target (qe.realeval.assemble)."""
    config = {
        "items": [dict(c) for c in cases], "doc_names": plan["doc_names"],
        "repeats": plan["repeats"], "include_security": plan["include_security"],
        "require_citations": plan["require_citations"],
        "policy": policy.model_dump(mode="json") if policy else None,
        "incomplete": incomplete, "prior_pass": {}}
    mine = runs.get(label, {})
    return assemble(config, {str(c["id"]): mine[str(c["id"])][: plan["repeats"]] for c in cases},
                    None, confirmed)


def performance(label_runs: Mapping[str, list[dict[str, Any]]],
                cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    recs = [r for c in cases for r in label_runs.get(str(c["id"]), [])]
    ok = [r["latency_s"] for r in recs if not r["error"]]
    sizes = [r.get("size_chars", 0) for r in recs]
    usages = [r["usage"] for r in recs if r.get("usage")]
    tokens: dict[str, int] | None = None
    if usages:
        tokens = {k: sum(int(u.get(k) or 0) for u in usages)
                  for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        tokens["calls_with_usage"] = len(usages)
    n = len(recs)
    errs = sum(1 for r in recs if r["error"])
    return {"calls": n, "errors": errs, "error_rate_calls": (errs / n) if n else None,
            "latency_p50_s": percentile(ok, 0.5), "latency_p95_s": percentile(ok, 0.95),
            "latency_p99_s": percentile(ok, 0.99),
            "response_chars_mean": (sum(sizes) / n) if n else None,
            "response_chars_max": max(sizes) if sizes else None,
            "tokens": tokens,
            "cost": None,
            "cost_note": "no price table is configured; token usage is reported when the "
                         "response carries it (OpenAI-style `usage`), cost is not invented"}


def per_risk(rows: Sequence[dict[str, Any]], scenario_of: Mapping[str, str],
             ) -> dict[str, dict[str, Any]]:
    """Pass rate per risk scenario over distinct root questions (95% Clopper-Pearson)."""
    roots = root_ids(rows)
    groups: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["passed"] is not None:
            groups[scenario_of.get(r["id"], "grounded_qa")][roots[r["id"]]].append(r["passed"])
    out: dict[str, dict[str, Any]] = {}
    for sc, by_root in sorted(groups.items()):
        k = sum(all(v) for v in by_root.values())
        n = len(by_root)
        e = rate_estimate(k, n)
        out[sc] = {"n_roots": n, "passed": k, "rate": e.point, "ci_low": e.lower,
                   "ci_high": e.upper,
                   "note": f"n={n} < {MIN_N_NOTE}: interval too wide to conclude"
                   if n < MIN_N_NOTE else ""}
    return out


def trim_items(rows: Sequence[dict[str, Any]], scenario_of: Mapping[str, str],
               ) -> list[dict[str, Any]]:
    out = []
    for r in rows[:MAX_TRIMMED_ITEMS]:
        out.append({"id": r["id"], "question": r["question"],
                    "answer": (r["answer"] or "")[:ANSWER_PREVIEW], "passed": r["passed"],
                    "failure_class": r["failure_class"], "failure_reason": r["failure_reason"],
                    "source": r["source"], "scenario": scenario_of.get(r["id"]),
                    "advisory": bool((r["lineage"] or {}).get("advisory")
                                     and not (r["lineage"] or {}).get("confirmed")),
                    "errored": r["errored"]})
    return out


def root_outcomes(rows: Sequence[dict[str, Any]], metric: str) -> dict[str, bool]:
    """root question id -> passed this metric (all measurable items under the root passed)."""
    roots = root_ids(rows)
    vals: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        if metric == "overall_pass_rate":
            v = r["passed"]
        elif metric == "injection_resistance":
            v = r["passed"] if r["source"] == "security" else None
        elif r["source"] == "security":
            v = None
        elif metric == "refusal_correctness":
            v = r["scores"].get("refusal_correct") if r["answerable"] is False else None
        else:
            v = r["scores"].get(_SCORE_KEY[metric])
        if v is not None:
            vals[roots[r["id"]]].append(bool(v))
    return {root: all(v) for root, v in vals.items()}


def _compare_metric(metric: str, a_label: str, b_label: str, a: Mapping[str, bool],
                    b: Mapping[str, bool]) -> dict[str, Any]:
    shared = sorted(set(a) & set(b))
    base: dict[str, Any] = {"metric": metric, "a": a_label, "b": b_label, "n_pairs": len(shared)}
    if not shared:
        return {**base, "outcome": "NOT_MEASURABLE", "winner": None, "p_value": None,
                "note": "no root question is measurable on both targets"}
    both = sum(a[r] and b[r] for r in shared)
    a_only = sum(a[r] and not b[r] for r in shared)
    b_only = sum(b[r] and not a[r] for r in shared)
    neither = len(shared) - both - a_only - b_only
    d = newcombe_paired(both, a_only, b_only, neither)
    mc = mcnemar_exact([a[r] for r in shared], [b[r] for r in shared])
    return {**base, "a_rate": d.p_a, "b_rate": d.p_b, "diff": d.diff,
            "ci_low": d.ci_low, "ci_high": d.ci_high, "cohens_h": d.cohens_h,
            "a_only_ok": a_only, "b_only_ok": b_only, "discordant": mc.discordant,
            "p_value": mc.p_value, "ci_method": "Newcombe paired (method 10, Wilson)",
            "test": "exact McNemar on discordant root questions"}


def _outcome(row: dict[str, Any], alpha: float, family: int) -> None:
    """Decide the label from the Bonferroni-adjusted p-value; never invents a winner."""
    if row.get("outcome") == "NOT_MEASURABLE":
        return
    row["p_adjusted"] = min(1.0, row["p_value"] * family)
    row["alpha"] = alpha
    if row["n_pairs"] < MIN_N_NOTE:
        row.update(outcome="INSUFFICIENT_EVIDENCE", winner=None,
                   note=f"only {row['n_pairs']} paired root questions (< {MIN_N_NOTE}): too few "
                        "to conclude anything")
    elif row["p_adjusted"] < alpha:
        better_a = row["diff"] > 0
        row.update(outcome="A_BETTER" if better_a else "B_BETTER",
                   winner=row["a"] if better_a else row["b"],
                   note=f"significant after Bonferroni over {family} test(s)")
    else:
        row.update(outcome="NO_SIGNIFICANT_DIFFERENCE", winner=None,
                   note="the paired data do not separate these targets "
                        f"(adjusted p={row['p_adjusted']:.3g}); absence of evidence, not "
                        "evidence of equality")


def compare(rows_by_label: Mapping[str, Sequence[dict[str, Any]]], alpha: float,
            ) -> dict[str, Any]:
    labels = list(rows_by_label)
    out: list[dict[str, Any]] = []
    for a_label, b_label in combinations(labels, 2):
        for metric in COMPARED:
            out.append(_compare_metric(
                metric, a_label, b_label, root_outcomes(rows_by_label[a_label], metric),
                root_outcomes(rows_by_label[b_label], metric)))
    family = max(1, sum(1 for r in out if r.get("outcome") != "NOT_MEASURABLE"))
    for r in out:
        _outcome(r, alpha, family)
    return {"alpha": alpha, "family_size": family,
            "multiplicity": f"Bonferroni across {family} paired test(s) "
                            f"({len(COMPARED)} metrics x {len(labels) * (len(labels) - 1) // 2} "
                            "pair(s)); metrics are correlated so this is conservative",
            "pairs": out}


def recommend(results: Mapping[str, Mapping[str, Any]], comparison: Mapping[str, Any],
              incomplete: str | None) -> dict[str, Any]:
    labels = list(results)
    caveats: list[str] = []
    if incomplete:
        caveats.append(f"run incomplete: {incomplete}")
    decisions = {lbl: results[lbl]["decision"]["verdict"] for lbl in labels}
    if len(labels) < 2:
        return {"better_target": None, "decisions": decisions, "caveats": caveats,
                "summary": "single target: no comparison; see the policy decision for it."}
    pairs = comparison["pairs"]

    def wins(lbl: str, metric: str) -> int:
        return sum(1 for p in pairs if p["metric"] == metric and p["winner"] == lbl)

    def losses(lbl: str) -> list[str]:
        return [p["metric"] for p in pairs
                if p["winner"] and p["winner"] != lbl and lbl in (p["a"], p["b"])]

    best = [lbl for lbl in labels if wins(lbl, "overall_pass_rate") == len(labels) - 1]
    if len(best) == 1 and not losses(best[0]):
        pick = best[0]
        summary = (f"{pick} is significantly better on overall_pass_rate than every other "
                   "target and significantly worse on none of the compared metrics.")
        if decisions[pick] in ("REJECT", "INSUFFICIENT_EVIDENCE"):
            caveats.append(f"{pick} still has policy decision {decisions[pick]}: better than the "
                           "others is not the same as releasable")
        return {"better_target": pick, "decisions": decisions, "caveats": caveats,
                "summary": summary}
    if len(best) == 1:
        caveats.append(f"{best[0]} wins overall_pass_rate but is significantly worse on "
                       f"{sorted(set(losses(best[0])))}")
    insufficient = [p for p in pairs if p.get("outcome") == "INSUFFICIENT_EVIDENCE"]
    if insufficient:
        caveats.append(f"{len(insufficient)} paired comparison(s) have too few root questions; "
                       "add cases or repeats of distinct questions to separate the targets")
    return {"better_target": None, "decisions": decisions, "caveats": caveats,
            "summary": "no target is established as better: the paired evidence does not "
                       "support a winner (no significant difference, mixed results or "
                       "insufficient evidence)."}
