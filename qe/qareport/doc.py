"""Neutral document tree built from the report dict; rendered to Markdown and HTML.

Blocks: h, p, ul, ol, table, code, callout, kv, chart. Text is plain; renderers escape it.
Missing numbers render as "n/a", never "None"/"NaN".
"""

from __future__ import annotations

import datetime as dt
from typing import Any

Block = dict[str, Any]
MAX_TEXT = 3000  # per response/request in the printed report; full text is in items.jsonl


def num(v: Any, digits: int = 3) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return "n/a" if v != v or v in (float("inf"), float("-inf")) else f"{v:.{digits}f}"
    return str(v)


def rate_text(value: Any, lo: Any, hi: Any, n: Any = None) -> str:
    if value is None:
        return f"n/a (n={num(n)})" if n is not None else "n/a"
    body = f"{num(value)}" if lo is None else f"{num(value)} [{num(lo)}, {num(hi)}]"
    return f"{body} (n={num(n)})" if n is not None else body


def clip(text: str, limit: int = MAX_TEXT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated: {len(text) - limit} more characters in items.jsonl]"


def date_text(epoch: Any) -> str:
    if epoch is None:
        return "not recorded"
    return dt.datetime.fromtimestamp(float(epoch), dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def _h(level: int, text: str) -> Block:
    return {"t": "h", "l": level, "text": text}


def _p(text: str) -> Block:
    return {"t": "p", "text": text}


def _ul(items: list[str]) -> Block:
    return {"t": "ul", "items": items or ["none"]}


def _table(caption: str, head: list[str], rows: list[list[str]]) -> Block:
    return {"t": "table", "caption": caption, "head": head,
            "rows": rows or [["none"] + [""] * (len(head) - 1)]}


def _code(label: str, text: str) -> Block:
    return {"t": "code", "label": label, "text": clip(text) if text else "(empty)"}


def _kv(rows: list[tuple[str, str]]) -> Block:
    return {"t": "kv", "rows": rows}


def _callout(kind: str, text: str) -> Block:
    return {"t": "callout", "kind": kind, "text": text}


def _each(report: dict[str, Any], fn: Any, level: int) -> list[Block]:
    """Apply a per-target block builder; campaigns get an h(level) heading per target."""
    out: list[Block] = []
    multi = report["kind"] == "campaign"
    for t in report["targets"]:
        if multi:
            out.append(_h(level, f"Target: {t['name']}"))
        out += fn(t, level + 1 if multi else level)
    return out


def _executive(report: dict[str, Any]) -> list[Block]:
    ex = report["executive_summary"]
    out = [_h(2, "1. Executive summary")]
    if ex["example_policy_warning"]:
        out.append(_callout("warn", "EXAMPLE POLICY IN USE. The recommendation was computed "
                            "against a non-binding example policy, not a real risk appetite."))
    if ex["integrity_failed"]:
        out.append(_callout("warn", "LEDGER INTEGRITY CHECK FAILED for: " +
                            ", ".join(ex["integrity_failed"]) + ". Do not rely on these figures."))
    for r in ex["targets"]:
        out.append(_callout("verdict", f"{r['target']}: {r['verdict']} (status: {r['status']})"))
    out.append(_callout("info", ex["status_note"]))
    out.append(_table("Recommendation per target",
                      ["Target", "Recommendation", "Status", "Policy", "Defect clusters"],
                      [[r["target"], r["verdict"], r["status"], r["policy"] + (
                          " (EXAMPLE)" if r["policy_is_example"] else ""),
                        str(r["defect_clusters"])] for r in ex["targets"]]))
    for r in ex["targets"]:
        out += [_h(3, f"Headline risks: {r['target']}"), _ul(r["headline_risks"] or [
            "no failing or uncertain metric and no defect recorded"]),
            _h(3, f"What we could not assess: {r['target']}"), _ul(r["not_assessed"])]
    return out


def _scope_one(t: dict[str, Any], lvl: int) -> list[Block]:
    s = t["scope"]
    auth = s["authorization"]
    rows = [
        ("Evaluation id", s["evaluation_id"]), ("Project", s["project_id"]),
        ("Endpoint host", s["endpoint_host"] or "not recorded"),
        ("Execution mode", s["execution_mode"] or "not recorded"),
        ("Authorization attested", ("yes" if auth["attested"] else "NO") if
         auth["attested"] is not None else "not recorded"),
        ("Attested at", date_text(auth["attested_at"])),
        ("Evaluation created", date_text(s["created_epoch"])),
        ("Run state", s["state"]),
        ("Target versions", ", ".join(f"{k}={v}" for k, v in s["versions"].items())
         or "not recorded"),
        ("Documents", ", ".join(s["documents"]) or "none"),
        ("Seed / repeats / max questions",
         f"{num(s['seed'])} / {num(s['repeats'])} / {num(s['max_questions'])}"),
        ("Call budget", ", ".join(f"{k}={num(v)}" for k, v in (s["budget"] or {}).items())
         or "not recorded"),
    ]
    out = [_kv(rows)]
    if s["notes"]:
        out += [_p("Run notes (from the ledger configuration):"), _ul(s["notes"])]
    if s["meta_notes"]:
        out.append(_ul(s["meta_notes"]))
    return out


def _scope(report: dict[str, Any]) -> list[Block]:
    tool = report["tool"]
    out = [_h(2, "2. Scope and target"),
           _kv([("Report", f"{report['id']} ({report['kind']})"),
                ("Report schema", report["schema"]),
                ("Evidence created", date_text(report["created_epoch"])),
                ("Tool", f"{tool['name']} {tool['version']}"),
                ("Tool commit", (tool["git_commit"] or "unknown") + (
                    " (working tree has uncommitted changes under qe/)" if tool["git_dirty"]
                    else ""))])]
    return out + _each(report, _scope_one, 3)


def _methodology(report: dict[str, Any]) -> list[Block]:
    m = report["methodology"]
    d = m["test_derivation"]
    sc = m["scoring_rules"]
    return [
        _h(2, "3. Methodology"),
        _h(3, "How tests were derived"),
        _table("Planned items by source", ["Source", "Items"],
               [[k, str(v)] for k, v in d["items_by_source"].items()]),
        _table("Variant operators", ["Operator", "Items"],
               [[k, str(v)] for k, v in d["variant_operators"].items()]),
        _ul(d["explanation"]),
        _h(3, "Oracle types"), _ul(m["oracles"]),
        _h(3, "Scoring rules and their known limits"),
        _table("Constants (from qe.realeval.scoring)", ["Constant", "Value"],
               [[k, num(v)] for k, v in sc["constants"].items()]),
        _ul(sc["rules"]), _p("Known limits:"), _ul(sc["known_limits"]),
        _h(3, "Statistics"), _ul(m["statistics"]),
        _h(3, "Independence and isolation"), _ul(m["independence"]),
        _h(3, "Seeds and repeats"),
        _table("Per target", ["Target", "Seed", "Repeats"],
               [[k, num(m["seeds"][k]), num(m["repeats"][k])] for k in m["seeds"]]),
        _h(3, "Severity rubric and guidance"),
        _p(f"Severity labels follow rubric {m['severity_rubric']['id']} v"
           f"{m['severity_rubric']['version']}; they {m['severity_rubric']['note']}."),
        _table("Levels", ["Level", "Meaning"],
               [[k, v] for k, v in m["severity_rubric"]["levels"].items()]),
        _p(f"Remediation text comes from {m['guidance']['id']} v{m['guidance']['version']}: "
           f"{m['guidance']['label']}."),
    ]


def _coverage_one(t: dict[str, Any], lvl: int) -> list[Block]:
    c = t["coverage"]
    classes = sorted({k for r in c["matrix"] for k in r["classes"]})
    return [
        _p(f"Planned {c['planned']}, executed {c['executed']}, unchecked {c['unchecked']}."),
        _table("Risk by outcome (tests)",
               ["Risk / scenario", "Planned", "Executed", "Passed", "Failed", "Unchecked"] +
               classes,
               [[r["risk"], str(r["planned"]), str(r["executed"]), str(r["passed"]),
                 str(r["failed"]), str(r["unchecked"])] +
                [str(r["classes"].get(k, 0)) for k in classes] for r in c["matrix"]]),
        _table("Taxonomy coverage", ["Class", "Name", "Detected by", "n (roots)", "Status",
                                     "Failures observed"],
               [[x["class"], x["name"], ", ".join(x["metrics"]),
                 ", ".join(f"{k}={v}" for k, v in x["n_roots"].items()), x["status"],
                 str(x["failures_observed"])] for x in c["taxonomy"]]),
        _p("Gaps:"), _ul(c["gaps"] or ["no gap detected by the checks above"]),
    ]


def _results_one(t: dict[str, Any], lvl: int) -> list[Block]:
    r = t["results"]
    lat = r["latency_s"]
    chart_rows = [{"label": s["dimension"], "value": s["value"], "lo": s["ci_low"],
                   "hi": s["ci_high"], "n": s["n_roots"],
                   "marker": (None if s["appetite_max_failure"] is None
                              else 1 - s["appetite_max_failure"])} for s in r["scorecard"]]
    return [
        _p(f"Distinct root questions: {r['sample']['n_roots']}; items: {r['sample']['n_items']}."),
        _table("Scorecard (success rates, 95% Clopper-Pearson)",
               ["Dimension", "Metric", "Value [95% CI]", "n roots", "n items", "Appetite (max "
                "failure)", "Required"],
               [[s["dimension"], s["metric"], rate_text(s["value"], s["ci_low"], s["ci_high"]),
                 num(s["n_roots"]), num(s["n_items"]), num(s["appetite_max_failure"]),
                 num(s["required"])] for s in r["scorecard"]]),
        {"t": "chart", "kind": "intervals", "title": "Scorecard intervals", "data": chart_rows,
         "desc": "Dot is the point estimate, bar the 95% interval; the tick marks the success "
                 "rate the policy requires (1 minus the maximum tolerated failure rate)."},
        _table("All metrics", ["Metric", "Value [95% CI]", "n", "Note"],
               [[m["metric"], rate_text(m["value"], m["ci_low"], m["ci_high"]), num(m["n"]),
                 m["note"]] for m in r["metrics"]]),
        _table("Latency (seconds, successful calls)",
               ["n", "p50", "p90", "p95", "p99", "min", "max", "mean"],
               [[num(lat["n"])] + [num(lat[k], 4) for k in
                                   ("p50", "p90", "p95", "p99", "min", "max", "mean")]]),
        {"t": "chart", "kind": "latency", "title": "Latency percentiles", "data": lat,
         "desc": "Bars show p50, p90, p95 and p99 latency in seconds."},
        _p(r["latency_note"]),
        _table("Errors", ["Calls", "Errored", "Error rate [95% CI]", "By type"],
               [[num(r["calls"]), num(r["error_calls"]["k"]),
                 rate_text(r["error_calls"]["value"], r["error_calls"]["ci_low"],
                           r["error_calls"]["ci_high"]),
                 ", ".join(f"{k}: {v}" for k, v in r["errors_by_type"].items()) or "none"]]),
    ]


def _defect(d: dict[str, Any], lvl: int) -> list[Block]:
    out = [_h(lvl, f"{d['id']}: {d['class_name']} [{d['severity']}]"),
           _kv([("Defect id", d["id"]), ("Taxonomy class", f"{d['failure_class']} "
                                                              f"({d['class_name']})"),
                ("Severity", f"{d['severity']} (label from the rubric; not part of the verdict)"),
                ("Severity basis", d["severity_basis"]),
                ("Cluster", f"{len(d['members'])} item(s); {d['duplicates']} duplicate(s) "
                            f"folded in; root {d['root']}")])]
    for m in d["members"]:
        rep = m["repeats"]
        led = m["ledger"]
        refs = [f"{x['key']} seq {x['seq']} hash {x['hash']}" for x in
                (led["run"], led["verdict"]) if x]
        orc = m["oracle"]
        if orc["kind"] == "scoring":
            fired = "check failed" if orc["fired"] else "no check failed"
        else:
            fired = "oracle fired" if orc["fired"] else "oracle did not fire"
        out += [
            _p(f"Item {m['item_id']} ({m['source']}"
               f"{', advisory' if m['advisory'] else ''}); failed on {rep['failed']} of "
               f"{rep['total']} repeat(s); repeat {rep['shown_rep']} shown."),
            {"t": "ol", "items": [
                "Send the exact request below to the target as a single question.",
                "Capture the response and any returned passages.",
                f"Apply the check: {orc['type']}."]},
            _code("Request (exact)", m["request"]),
            _code("Response (exact)" + (f", error: {m['response_error']}"
                                        if m["response_error"] else ""), m["response"]),
            _kv([("Expected", m["expected"]), ("Actual", m["actual"]),
                 ("Oracle", f"{orc['type']}: {fired}" +
                  (f"; {orc['detail']}" if orc.get("detail") else "") +
                  (f"; failed checks: {', '.join(orc['failed_checks'])}"
                   if orc.get("failed_checks") else "")),
                 ("Ledger events", "; ".join(refs) or "not found")]),
        ]
    out += [_p("Guidance (static, not derived from this run's evidence):"),
            _ul(d["guidance"])]
    return out


def _defects_one(t: dict[str, Any], lvl: int) -> list[Block]:
    ds = t["defects"]
    out: list[Block] = [_table("Defect register", ["Id", "Severity", "Class", "Items", "Title"],
                               [[d["id"], d["severity"], d["failure_class"],
                                 str(len(d["members"])), d["title"]] for d in ds])]
    if not ds:
        out.append(_p("No defect was recorded: no item failed. This does not show the "
                      "absence of defects outside the tests listed in section 4."))
    for d in ds:
        out += _defect(d, lvl)
    return out


def _security_one(t: dict[str, Any], lvl: int) -> list[Block]:
    s = t["security"]
    if not s["ran"]:
        return [_callout("warn", s["note"].upper())]
    o = s["overall"]
    out: list[Block] = []
    if o:
        out.append(_p(f"Attack success rate over {o['n']} root probe(s): "
                      f"{rate_text(o['value'], o['ci_low'], o['ci_high'])} "
                      f"({o['k']} breached). Budget: {o['budget']['probes']} probe(s), "
                      f"{o['budget']['calls']} call(s)."))
    out.append(_table("By attacker class", ["Attacker class", "Kind", "Oracles", "Probes",
                                            "Breached", "ASR [95% CI]", "Attempts",
                                            "Successful attempts", "Errored attempts"],
                      [[k["attacker_class"], k["kind"], ", ".join(k["oracles"]),
                        str(k["probes"]), str(k["probes_breached"]),
                        rate_text(k["asr_probes"]["value"], k["asr_probes"]["ci_low"],
                                  k["asr_probes"]["ci_high"]),
                        str(k["attempts"]), str(k["successful_attempts"]),
                        str(k["errored_attempts"])] for k in s["by_kind"]]))
    for p in s["probes"]:
        led = p["ledger"]
        out += [_h(lvl, f"Failed probe {p['item_id']}"),
                _kv([("Attacker class", p["attacker_class"]),
                     ("Oracle", f"{p['oracle']['type']}: " + (
                         f"fired. {p['oracle'].get('detail') or ''}" if p["oracle"]["fired"]
                         else "did not fire (target error)")),
                     ("Ledger events", "; ".join(
                         f"{x['key']} seq {x['seq']} hash {x['hash']}"
                         for x in (led["run"], led["verdict"]) if x) or "not found")]),
                _code("Attack request (exact)", p["request"]),
                _code("Response (exact)", p["response"])]
    return out


def _grounding_one(t: dict[str, Any], lvl: int) -> list[Block]:
    g = t["grounding"]
    out: list[Block] = [_p(f"Answers checked: {g['checked']}; not measurable: "
                           f"{g['not_measurable']}. {g['note']}")]
    if not g["unsupported"]:
        out.append(_p("No unsupported claim was found in the answers that could be checked."))
    for u in g["unsupported"]:
        out += [_h(lvl, f"Unsupported claims in {u['item_id']}"),
                _code("Request (exact)", u["request"]), _code("Answer (exact)", u["response"]),
                _p("Unsupported claims:"), _ul(u["unsupported_claims"]),
                _p("Context returned by the target (cited):"),
                _ul([clip(c, 600) for c in u["cited_contexts"]] or ["no context returned"])]
    return out


def _regression_one(t: dict[str, Any], lvl: int) -> list[Block]:
    r = t["regression"]
    if not r["assessable"]:
        return [_callout("warn", r["note"])]
    return [_table("Regression status", ["Category", "Count", "Item ids"],
                   [["re-run from suite", str(r["suite_rerun"]), ""],
                    ["fixed", str(len(r["fixed"])), ", ".join(r["fixed"])],
                    ["still failing", str(len(r["still_failing"])),
                     ", ".join(r["still_failing"])],
                    ["new failures", str(len(r["new_failures"])), ", ".join(r["new_failures"])]]),
            _p(f"Baseline of previously passing items: {r['baseline_items']}.")]


def _recommendation_one(t: dict[str, Any], lvl: int) -> list[Block]:
    r = t["recommendation"]
    pol = r["policy"]
    out: list[Block] = []
    if pol["warning"]:
        out.append(_callout("warn", pol["warning"]))
    out += [_kv([("Recommendation", r["verdict"]), ("Status", r["status"]),
                 ("Decision id", r["decision_id"]),
                 ("Policy", f"{pol['id']}@{pol['version']}")]),
            _p(r["explanation"]), _p("Reasons:"), _ul(r["reasons"] or ["none"]),
            _table("Policy risk appetite (max tolerated failure rate)",
                   ["Metric", "Max failure rate", "Required"],
                   [[k, num(v), num(k in pol["required_evidence"])]
                    for k, v in pol["risk_appetite"].items()]),
            _p(r["rule"])]
    return out


def _review_one(t: dict[str, Any], lvl: int) -> list[Block]:
    r = t["review"]
    out: list[Block] = [_kv([("Status", r["status"]), ("Decision id", r["decision_id"])])]
    if r["note"]:
        out.append(_callout("warn", r["note"]))
    for s in r["signoffs"]:
        out.append(_kv([
            ("Reviewer", str(s.get("approver"))),
            ("Decision", "approved" if s.get("approved") else "rejected"),
            ("Rationale", str(s.get("note") or "none")),
            ("Ledger event", f"seq {s['seq']} hash {s['hash']}")]))
    if r["decision_matches_signoff"] is False:
        out.append(_callout("warn", "The sign-off refers to a different decision id than the "
                                    "decision recomputed from the ledger."))
    out.append(_table("Advisory item confirmations", ["Item", "Reviewer", "Ledger seq"],
                      [[str(c.get("item_id")), str(c.get("reviewer")), str(c["seq"])]
                       for c in r["confirmations"]]))
    return out


def _monitoring_one(t: dict[str, Any], lvl: int) -> list[Block]:
    m = t["monitoring"]
    return [
        _p(m["status"]), _p(f"Cadence: {num(m['cadence_days'])} day(s). {m['cadence_note']}."),
        _table("Watched metrics", ["Metric", "Required", "Status", "Failure rate", "Appetite"],
               [[w["metric"], num(w["required"]), w["status"], num(w["failure_rate"]),
                 num(w["appetite"])] for w in m["watch"]]),
        _p("Drift triggers (re-run on any of these):"), _ul(m["drift_triggers"]),
        _p("Alert rule: " + m["alert_rule"] + "."),
        _p("Required metrics not measured: " + (", ".join(m["unmeasured_required"]) or "none")),
    ]


def _limits_one(t: dict[str, Any], lvl: int) -> list[Block]:
    return [_ul(t["limitations"])]


def _appendix_one(t: dict[str, Any], lvl: int) -> list[Block]:
    a = t["appendix"]
    led = a["ledger"]
    return [
        _kv([("Ledger head hash", led["head"]), ("Ledger entries", str(led["entries"])),
             ("Hash chain verified", num(led["chain_ok"])),
             ("Configuration hash", a["config_hash"])]),
        _table("Item table (questions truncated to 80 characters; full text in items.jsonl)",
               ["Id", "Root", "Source", "Risk", "Class", "Passed", "Repeats", "Question"],
               [[i["id"], i["root"], i["source"], i["risk"] or "", i["failure_class"] or "",
                 "unchecked" if i["passed"] is None else num(i["passed"]),
                 "".join("-" if p is None else ("P" if p else "F")
                         for p in (i["repeat_passes"] or [])), i["question"][:80]]
                for i in a["items"]]),
    ]


def _comparison(report: dict[str, Any]) -> list[Block]:
    c = report["comparison"]
    if not c:
        return []
    names = list(c["latency"])
    out = [_h(3, "Comparison between targets"),
           _table("Metrics by target (value [95% CI], n roots)", ["Metric"] + names,
                  [[row["metric"]] + [rate_text(row["targets"][n]["value"],
                                                 row["targets"][n]["ci_low"],
                                                 row["targets"][n]["ci_high"],
                                                 row["targets"][n]["n"]) for n in names]
                   for row in c["metrics"]]),
           _table("Paired comparison (exact McNemar on root questions)",
                  ["A", "B", "Shared roots", "A-only pass", "B-only pass", "Discordant",
                   "p (exact)", "p (Bonferroni)"],
                  [[p["a"], p["b"], str(p["shared_roots"]), str(p["a_only_pass"]),
                    str(p["b_only_pass"]), str(p["discordant"]), num(p["p_value_exact"], 4),
                    num(p["p_value_bonferroni"], 4)]
                   for p in c["pairs"]]),
           _p(c["note"])]
    if not c["same_item_set"]:
        out.append(_callout("warn", "The targets were NOT evaluated on identical item sets; "
                                    "rates are not directly comparable."))
    return out


def build_doc(report: dict[str, Any]) -> list[Block]:
    doc: list[Block] = [_h(1, report["title"])]
    doc += _executive(report)
    doc += _scope(report)
    doc += _methodology(report)
    sections: list[tuple[str, Any, list[Block]]] = [
        ("4. Test coverage", _coverage_one, []),
        ("5. Results", _results_one, _comparison(report)),
        ("6. Defect register", _defects_one, []),
        ("7. Security findings", _security_one, []),
        ("8. Grounding findings", _grounding_one, []),
        ("9. Regression status", _regression_one, []),
        ("10. Recommendation and reasoning", _recommendation_one, []),
        ("11. Human review and sign-off", _review_one, []),
        ("12. Monitoring plan", _monitoring_one, []),
        ("13. Limitations and threats to validity", _limits_one, []),
        ("14. Appendix", _appendix_one, []),
    ]
    for title, fn, pre in sections:
        doc.append(_h(2, title))
        doc += pre
        doc += _each(report, fn, 3)
    return doc
