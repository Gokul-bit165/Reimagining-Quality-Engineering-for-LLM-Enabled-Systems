"""Defect register, security and grounding findings: deterministic, from ledger-derived rows.

A defect is a CLUSTER: failed items of the same failure class that share a root question
(variants, paraphrases and repeats of one problem are one defect, listed as members).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from qe.core.ids import sha256_hex
from qe.core.schemas import ClaimState
from qe.exec.attack_model import OracleSpec
from qe.exec.oracles import OracleContext, evaluate_oracle
from qe.qareport.models import EvidenceInput
from qe.qareport.rubric import SEVERITY_ORDER, attacker_class, guidance_for, severity_of
from qe.qareport.stats_util import rate
from qe.realeval.assemble import TAXONOMY_NAMES, root_ids

CHECK_TEXT = {
    "correct": "answer does not match the reference answer",
    "faithful": "answer contains claims not supported by the passages the target returned",
    "refusal_correct": "target answered although a refusal was expected",
    "answered": "target refused or gave no answer to an answerable question",
    "citation_valid": "a citation does not resolve to a known document or passage",
}


def oracle_fired(probe: dict[str, Any], item_id: str, answer: str) -> tuple[bool, str | None]:
    """Re-run the deterministic outcome oracle on one recorded answer."""
    spec = OracleSpec(kind=probe["oracle"], params=probe["params"])
    ctx = OracleContext(before={}, after={}, sinks=(), outputs={"victim": (answer,)})
    verdict = evaluate_oracle(item_id, spec, ctx)
    fired = verdict.state is ClaimState.CONTRADICTED
    return fired, (verdict.detail if fired else None)


def _ref(ev: EvidenceInput, key: str | None) -> dict[str, Any] | None:
    e = None if key is None else ev.entries.get(key)
    return None if e is None else {"key": key, "seq": e.seq, "hash": e.hash}


def _failing_rep(row: dict[str, Any], n_runs: int) -> int:
    passes = row["scores"].get("repeat_passes") or []
    for i, p in enumerate(passes):
        if p is False and i < n_runs:
            return i
    return 0


def _expected(row: dict[str, Any]) -> str:
    probe = row.get("probe")
    if row["source"] == "security" and probe:
        return f"attack resisted: outcome oracle `{probe['oracle']}` must not fire"
    if row.get("answerable") is False:
        return "a refusal: the supplied documents do not answer this question"
    if row.get("reference_answer"):
        return f"an answer matching the reference: {row['reference_answer']}"
    return "an answer to an answerable question (no reference answer was declared)"


def _actual(row: dict[str, Any], run: dict[str, Any]) -> str:
    if run.get("error"):
        return f"target error: {run['error']}"
    reason = row.get("failure_reason") or ""
    checks = [c.strip() for c in reason.split(",") if c.strip()]
    texts = [CHECK_TEXT[c] for c in checks if c in CHECK_TEXT]
    if row["source"] == "security":
        return "oracle fired: the attack succeeded"
    return "; ".join(texts) if texts else (reason or "check failed")


def _member(ev: EvidenceInput, row: dict[str, Any]) -> dict[str, Any]:
    runs = ev.runs.get(row["id"], [])
    rep = _failing_rep(row, len(runs))
    run = runs[rep] if runs else {"answer": "", "contexts": [], "error": None, "latency_s": None}
    passes = row["scores"].get("repeat_passes") or []
    probe = row.get("probe")
    if row["source"] == "security" and probe and not run.get("error"):
        fired, detail = oracle_fired(probe, row["id"], run["answer"])
        oracle: dict[str, Any] = {"type": probe["oracle"], "kind": probe["kind"],
                                  "fired": fired, "detail": detail}
    else:
        reason = row.get("failure_reason") or ""
        failed = [c.strip() for c in reason.split(",") if c.strip() in CHECK_TEXT]
        oracle = {"type": "deterministic lexical checks (qe.realeval.scoring)", "kind": "scoring",
                  "fired": bool(failed), "failed_checks": failed}
    return {
        "item_id": row["id"], "source": row["source"], "risk": row.get("risk"),
        "operator": (row.get("lineage") or {}).get("operator"),
        "advisory": bool((row.get("lineage") or {}).get("advisory")
                         and not (row.get("lineage") or {}).get("confirmed")),
        "repeats": {"total": len(passes), "failed": sum(1 for p in passes if p is False),
                    "shown_rep": rep},
        "request": row["question"],
        "response": run["answer"], "response_contexts": run.get("contexts", []),
        "response_error": run.get("error"), "latency_s": run.get("latency_s"),
        "expected": _expected(row), "actual": _actual(row, run), "oracle": oracle,
        "ledger": {"run": _ref(ev, ev.run_key(row["id"], rep)),
                   "verdict": _ref(ev, ev.verdict_key(row["id"]))},
    }


def build_defects(ev: EvidenceInput) -> list[dict[str, Any]]:
    rows = ev.result["items"]
    roots = root_ids(rows)
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["passed"] is False and r["failure_class"]:
            clusters[(r["failure_class"], roots[r["id"]])].append(r)
    out: list[dict[str, Any]] = []
    for (cls, root), members in clusters.items():
        members = sorted(members, key=lambda r: (r["id"] != root, r["id"]))
        severity, basis = severity_of(cls)
        out.append({
            "id": "DEF-" + sha256_hex(f"{cls}|{root}")[:8].upper(),
            "failure_class": cls, "class_name": TAXONOMY_NAMES.get(cls, cls),
            "severity": severity, "severity_basis": basis, "root": root,
            "title": members[0]["question"][:120],
            "duplicates": len(members) - 1,
            "members": [_member(ev, m) for m in members],
            "guidance": guidance_for(cls),
        })
    out.sort(key=lambda d: (SEVERITY_ORDER.index(d["severity"]), d["failure_class"], d["id"]))
    return out


def build_security(ev: EvidenceInput, metrics: dict[str, Any]) -> dict[str, Any]:
    rows = [r for r in ev.result["items"] if r["source"] == "security"]
    if not rows:
        return {"ran": False, "note": "no security probes ran: security was NOT tested",
                "overall": None, "by_kind": [], "probes": []}
    sec = metrics["security_resistance"]
    breached_n = None if sec["value"] is None else round((1 - sec["value"]) * sec["n"])
    overall = None if breached_n is None else {
        **rate(breached_n, sec["n"]), "label": "attack success rate over distinct root probes",
        "budget": {"probes": len(rows), "calls": sum(len(ev.runs.get(r["id"], [])) for r in rows)}}
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_kind[(r.get("probe") or {}).get("kind", "unknown")].append(r)
    kinds = []
    for kind, krs in sorted(by_kind.items()):
        calls = [(r, c) for r in krs for c in ev.runs.get(r["id"], [])]
        successes = sum(1 for r, c in calls if not c["error"] and r.get("probe")
                        and oracle_fired(r["probe"], r["id"], c["answer"])[0])
        errors = sum(1 for _, c in calls if c["error"])
        probes_breached = sum(1 for r in krs if r["scores"].get("oracle_breached"))
        kinds.append({"kind": kind, "attacker_class": attacker_class(kind),
                      "probes": len(krs), "attempts": len(calls),
                      "successful_attempts": successes, "errored_attempts": errors,
                      "probes_breached": probes_breached,
                      "asr_probes": rate(probes_breached, len(krs)),
                      "oracles": sorted({(r.get("probe") or {}).get("oracle", "") for r in krs})})
    probes = []
    for r in rows:
        if r["passed"] is not False:
            continue
        m = _member(ev, r)
        probes.append({"item_id": r["id"], "kind": m["oracle"].get("kind"),
                       "attacker_class": attacker_class(m["oracle"].get("kind")),
                       "oracle": m["oracle"], "request": m["request"], "response": m["response"],
                       "errored": bool(m["response_error"]), "ledger": m["ledger"]})
    return {"ran": True, "note": "", "overall": overall, "by_kind": kinds, "probes": probes}


def build_grounding(ev: EvidenceInput) -> dict[str, Any]:
    rows = [r for r in ev.result["items"] if r["source"] != "security"]
    unsupported = []
    unmeasured = 0
    for r in rows:
        if r["scores"].get("faithful") is None and not r["errored"]:
            unmeasured += 1
        claims = (r.get("detail") or {}).get("unsupported_claims") or []
        if claims:
            unsupported.append({
                "item_id": r["id"], "request": r["question"], "response": r["answer"],
                "unsupported_claims": claims, "cited_contexts": r["contexts"],
                "ledger": {"run": _ref(ev, ev.run_key(r["id"], 0)),
                           "verdict": _ref(ev, ev.verdict_key(r["id"]))}})
    return {"checked": len(rows) - unmeasured, "not_measurable": unmeasured,
            "unsupported": unsupported,
            "note": "Lexical support check against the passage text the target returned; "
                    "not a semantic entailment judgement."}
