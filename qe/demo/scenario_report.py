"""Scenario report: every section is derived from the ledger only (R10). Pure function."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

from bench.asr import asr_at_budget
from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import Ledger
from qe.core.schemas import Policy
from qe.crew.attack_pairs import PAIRS
from qe.demo.pipeline import ATTACK_BUDGET, ATTACKERS, DIMENSION, VERDICT_ATTACKER
from qe.regress.store import SuiteStore
from qe.report.evidence_pack import build_pack
from qe.risk.taxonomy import load_taxonomy

BAD = {"contradicted", "unsupported"}
CHECKS_NOT_RUN = (
    "Free-text entailment / LLM-judge grounding: adapters exist but are not part of this demo, "
    "so only numeric claims and citation ids are checked.",
    "Bias and toxicity: no check is implemented.",
    "Real-model generation and real-model targets: generation and target are simulated.",
    "Continuous monitoring: described in the monitoring plan, not running.",
)
PAIR_INFO = {p.pair_id: {"surface": p.surface.value, "goal": p.goal} for p in PAIRS}


def _status(rate: dict[str, Any], appetite: float | None) -> str:
    if appetite is None:
        return "no_appetite"
    if rate["upper"] <= appetite:
        return "within"
    return "above" if rate["lower"] > appetite else "straddles"


def _attack_rows(ledger: Ledger) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    first: dict[tuple[str, str], int | None] = {}
    attempts: Counter[tuple[str, str]] = Counter()
    for e in ledger.entries():
        o = e.event.payload.get("outcome") if e.event.type is EventType.EVIDENCE_RECORDED else None
        if o is None:
            continue
        key = (o["pair_id"], o["attacker_class"])
        attempts[key] += 1
        first.setdefault(key, None)
        if o["breached"] and first[key] is None:
            first[key] = o["attempt_index"] + 1
    pair_ids = sorted({p for p, _ in first})
    rows = []
    for pid in pair_ids:
        row: dict[str, Any] = {"pair_id": pid, **PAIR_INFO.get(pid, {}),
                               "baseline_breached": first.get((pid, "baseline_none")) is not None}
        for cls in ATTACKERS:
            row[cls] = {"breached": first.get((pid, cls)) is not None,
                        "first_success": first.get((pid, cls)),
                        "attempts": attempts[(pid, cls)]}
        rows.append(row)
    asr: dict[str, Any] = {}
    for cls in ATTACKERS:
        by_pair = {pid: first.get((pid, cls)) for pid in pair_ids}
        if by_pair:
            asr[cls] = asdict(asr_at_budget(by_pair, ATTACK_BUDGET, cls))
    return rows, asr


def _consistency(runs: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    same = sum(1 for rs in runs.values() if len({r["response"]["output"] for r in rs}) == 1)
    return {"cases": len(runs), "identical_across_repeats": same}


def build_report(ledger: Ledger, policy: Policy) -> dict[str, Any]:
    entries = list(ledger.entries())
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    risks: list[dict[str, Any]] = []
    drafted = rejected = 0
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    verdicts: list[tuple[str, dict[str, Any]]] = []
    failures: list[dict[str, Any]] = []
    signoffs: list[dict[str, Any]] = []
    for e in entries:
        p, t = e.event.payload, e.event.type
        if t is EventType.EVIDENCE_RECORDED and "kind" in p:
            by_kind[p["kind"]].append(p)
        elif t is EventType.RISK_PROPOSED:
            risks.append({**p["item"], "status": p["status"],
                          "source": p.get("source", "simulated analyst"),
                          "reason": p.get("reason")})
        elif t is EventType.TEST_DRAFTED:
            drafted += p["status"] == "drafted"
            rejected += p["status"] == "rejected"
        elif t is EventType.RUN_RECORDED:
            runs[p["test_case_id"]].append(p)
        elif t is EventType.VERDICT_ISSUED:
            verdicts.append((e.event.key, p))
        elif t is EventType.FAILURE_RECORDED:
            failures.append(p)
        elif t is EventType.SIGNOFF_RECORDED:
            signoffs.append(p)
    scenario = (by_kind["scenario"] or [{}])[0]
    suite = (by_kind["generated_suite"] or [{"tests": {}, "rejected": [], "redundant": {}}])[0]
    plan = (by_kind["test_plan"] or [{"allocation": [], "unplanned": []}])[0]
    tests: dict[str, dict[str, str]] = suite["tests"]
    taxonomy = load_taxonomy("owasp_llm_2025")
    titles = {x.id: x.title for x in taxonomy.entries}
    allocation = {rid: n for rid, n in plan["allocation"]}
    risk_rows = []
    for r in risks:
        rid = _risk_id(r)
        risk_rows.append({**r, "risk_id": rid, "title": titles.get(r.get("taxonomy_id", ""), ""),
                          "planned_tests": allocation.get(rid, 0)})
    pack = build_pack(ledger, policy)
    appetite = dict(policy.risk_appetite)
    metrics = []
    for m in pack["metrics"]:
        if m["metric"].startswith("attack_oracle:"):
            continue
        row = {**m, "dimension": DIMENSION.get(m["metric"], "other"),
               "appetite": appetite.get(m["metric"])}
        if "failure_rate" in m:
            row["status"] = _status(m["failure_rate"], row["appetite"])
        row["failures"] = _examples(m["metric"], verdicts, tests, runs)
        metrics.append(row)
    attack_rows, asr = _attack_rows(ledger)
    store = SuiteStore(ledger)
    meta = {m["case_id"]: m for m in by_kind["regression_meta"]}
    cases = {c.id: c for c in store.cases()}
    regression = [{"case_id": rc.case_id, "minimized_from": rc.minimized_from,
                   "original_question": tests.get(rc.minimized_from, {}).get("question"),
                   "minimized_input": cases[rc.case_id].input,
                   "reproduced": list(rc.pass_k_admission),
                   "metric": meta.get(rc.case_id, {}).get("metric"),
                   "pieces": meta.get(rc.case_id, {}).get("pieces"),
                   "lineage": store.lineage(rc.case_id)} for rc in store.regression_cases()]
    taxonomy_counts = Counter(f["location"] for f in failures)
    return {
        "scenario": scenario,
        "labels": {"generation": _generation_label(scenario),
                   "target": _target_label(scenario),
                   "mode": scenario.get("mode", "simulated"),
                   "policy": "EXAMPLE policy: appetites are illustrative" if policy.example_only
                   else "user policy"},
        "risks": risk_rows, "plan": plan,
        "generation": {"drafted": drafted, "rejected_drafts": rejected,
                       "rejected_detail": suite["rejected"][:20], "redundant": suite["redundant"],
                       "tests": [{"case_id": cid, **t} for cid, t in tests.items()],
                       "unplanned_risks": plan["unplanned"]},
        "execution": {"runs": sum(len(rs) for rs in runs.values()),
                      "repeats": scenario.get("repeats"), "cases": len(runs),
                      "errors": len(pack["runs"]["with_errors"]),
                      "error_kinds": sorted({str(r["error"]) for rs in runs.values() for r in rs
                                             if r.get("error")})[:3],
                      "unrun": len(pack["runs"]["unrun_budget_or_kill"]),
                      "consistency": _consistency(runs)},
        "checks": {"ran": sorted({m["metric"] for m in metrics}),
                   "attack_oracles": sorted({v["metric"][14:] for _, v in verdicts
                                             if v["metric"].startswith("attack_oracle:")}),
                   "not_run": list(CHECKS_NOT_RUN)},
        "metrics": metrics,
        "attacks": {"budget": ATTACK_BUDGET, "verdict_attacker": VERDICT_ATTACKER,
                    "rows": attack_rows, "asr": asr},
        "failures": [{"case_id": f["case_id"], "metric": f["metric"], "location": f["location"],
                      "rule": f["rule"], "evidence": f["evidence"],
                      "substitution": f["substitution"], "source_id": f.get("source_id"),
                      "question": tests.get(f["case_id"], {}).get("question")} for f in failures],
        "failure_taxonomy": dict(taxonomy_counts),
        "regression": {"admitted": regression,
                       "rejected": [{k: m[k] for k in ("case_id", "metric", "reason")}
                                    for m in by_kind["regression_rejected"]]},
        "decision": pack["decision"], "policy": pack["policy"],
        "access": pack["access"], "ledger": pack["ledger"],
        "human_signoff": signoffs, "pack": pack,
    }


def _generation_label(sc: dict[str, Any]) -> str:
    if sc.get("mode") == "real":
        return (f"real model {sc.get('tester_model')} (tester) + one simulated second author; "
                "attacks run on the deterministic sandbox")
    return "simulated (deterministic stand-in, not a real model)"


def _target_label(sc: dict[str, Any]) -> str:
    if sc.get("mode") == "real":
        return f"real model {sc.get('target_model')} inside the sandbox app"
    return "FakeLLM sandbox application"


def _risk_id(r: dict[str, Any]) -> str:
    if r.get("risk_id"):
        return str(r["risk_id"])
    return "R-" + content_id([r["taxonomy_id"], r["component"]])[:10]


def _examples(metric: str, verdicts: list[tuple[str, dict[str, Any]]],
              tests: dict[str, dict[str, str]], runs: dict[str, list[dict[str, Any]]],
              limit: int = 5) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for key, p in verdicts:
        if p["metric"] != metric or p["verdict"]["state"] not in BAD or p["case_id"] in seen:
            continue
        seen.add(p["case_id"])
        run = (runs.get(p["case_id"]) or [{}])[0]
        resp = run.get("response", {})
        test = tests.get(p["case_id"], {})
        out.append({"case_id": p["case_id"], "question": test.get("question"),
                    "expected": test.get("expected"),
                    "state": p["verdict"]["state"], "detail": p["verdict"].get("detail"),
                    "evidence_key": key, "output": str(resp.get("output", ""))[:400],
                    "citations": resp.get("citations", [])})
        if len(out) >= limit:
            break
    return out
