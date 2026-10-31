"""Static HTML report viewer, generated from the ledger only (R10), one self-contained file.

Optional sections read ledger events when present and otherwise say "not run" (never blank):
  coverage          EVIDENCE_RECORDED {kind: "coverage_report", cells: [{cell, covered, n_tests}]}
  n_eff             ESTIMATE_COMPUTED {metric: "n_eff", value, n}
  invalid-test rate ESTIMATE_COMPUTED {metric: "invalid_test_rate", k, n [, point, lower, upper]}
  ASR@budget        ESTIMATE_COMPUTED {metric: "asr_at_budget", k, n, budget, attacker_class
                                       [, point, lower, upper]}
A rate with neither an interval nor counts to derive one is shown as "interval unavailable"
(R11: no bare point estimates). Every ledger-derived string is HTML-escaped (untrusted).
"""

from __future__ import annotations

from html import escape
from typing import Any

from qe.core.events import EventType
from qe.core.ledger import Ledger
from qe.core.schemas import Policy
from qe.report.evidence_pack import build_pack
from qe.report.viewer_template import CSS, JS
from qe.stats.estimators import rate_estimate

RATE_METRICS = {"invalid_test_rate": "Invalid-test rate", "asr_at_budget": "ASR@budget"}
DECISION_CLASS = {"RELEASE": "release", "REJECT": "reject", "CONDITIONAL": "conditional",
                  "INSUFFICIENT_EVIDENCE": "insufficient"}
ACCESS_NAMES = {"A": "black-box", "B": "SDK / trace in response", "C": "OpenTelemetry traces",
                "D": "repository", "E": "gateway"}
NAV = (("decision", "Decision"), ("access", "Access level"), ("evidence", "Evidence"),
       ("coverage", "Coverage"), ("validity", "Statistical validity"), ("runs", "Runs"),
       ("claims", "Claims not made"))


def build_view(ledger: Ledger, policy: Policy) -> dict[str, Any]:
    pack = build_pack(ledger, policy)
    view: dict[str, Any] = {"pack": pack, "appetite": dict(policy.risk_appetite),
                            "coverage": None, "n_eff": None,
                            "invalid_test_rate": None, "asr_at_budget": None}
    for entry in ledger.entries():
        p = entry.event.payload
        if entry.event.type is EventType.EVIDENCE_RECORDED and p.get("kind") == "coverage_report":
            view["coverage"] = _coverage(p)
        elif entry.event.type is EventType.ESTIMATE_COMPUTED:
            name = p.get("metric")
            if name == "n_eff":
                view["n_eff"] = {"value": p.get("value"), "n": p.get("n")}
            elif name in RATE_METRICS:
                view[name] = _rate(p)
    return view


def _coverage(p: dict[str, Any]) -> dict[str, Any]:
    cells = [c for c in p.get("cells", []) if isinstance(c, dict) and "cell" in c]
    return {"cells": cells,
            "uncovered": sorted(str(c["cell"]) for c in cells if not c.get("covered"))}


def _rate(p: dict[str, Any]) -> dict[str, Any]:
    out = {k: p.get(k) for k in ("k", "n", "point", "lower", "upper", "budget", "attacker_class")}
    k, n = p.get("k"), p.get("n")
    if (out["lower"] is None or out["upper"] is None) and isinstance(k, int) \
            and isinstance(n, int) and n > 0 and 0 <= k <= n:
        est = rate_estimate(k, n)
        out.update(point=est.point, lower=est.lower, upper=est.upper)
    if out["lower"] is None or out["upper"] is None:
        out.update(point=None, lower=None, upper=None)
    return out


def render_viewer(ledger: Ledger, policy: Policy) -> str:
    return render_html(build_view(ledger, policy))


# --- rendering ---------------------------------------------------------------------------
def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _fmt(x: float) -> str:
    return f"{x:.4f}"


def _interval_text(lower: float, upper: float, point: float | None) -> str:
    pt = f"{_fmt(point)} " if point is not None else ""
    return f"{pt}[{_fmt(lower)}, {_fmt(upper)}]"


def _ruler(lower: float, upper: float, point: float | None, appetite: float | None,
           label: str) -> str:
    scale = 100.0 / (max(upper, appetite or 0.0, 1e-9) * 1.15)

    def x(v: float) -> float:
        return round(v * scale, 2)

    width = max(x(upper) - x(lower), 0.4)
    parts = [f'<svg class="ruler" viewBox="0 0 100 14" role="img" aria-label="{_e(label)}" '
             'preserveAspectRatio="none"><line class="track" x1="0" x2="100" y1="9" y2="9"/>',
             f'<rect class="ci" x="{x(lower)}" y="6" height="6" width="{width:.2f}"/>']
    if point is not None:
        parts.append(f'<line class="pt" x1="{x(point)}" x2="{x(point)}" y1="3" y2="14"/>')
    if appetite is not None:
        parts.append(f'<line class="appetite" x1="{x(appetite)}" x2="{x(appetite)}" '
                     'y1="0" y2="14"/>')
    return "".join(parts) + "</svg>"


def _notrun(reason: str) -> str:
    return f'<p class="notrun"><strong>Not run.</strong> {_e(reason)}</p>'


def _metric_row(m: dict[str, Any], appetite: float | None) -> str:
    fr = m.get("failure_rate")
    counts = (f'{m["failed_cases"]} failed, {m["passed_cases"]} passed, '
              f'{m["not_evaluable_cases"]} not evaluable')
    if fr:
        text = _interval_text(fr["lower"], fr["upper"], fr["point"])
        note = f"; appetite {_e(appetite)}" if appetite is not None else ""
        label = f'{m["metric"]} failure rate {text}' + (
            f", appetite {appetite}" if appetite is not None else "")
        body = (_ruler(fr["lower"], fr["upper"], fr["point"], appetite, label)
                + f'<p class="num">{text} <span class="muted">exact 95% interval{note}</span></p>')
    else:
        body = '<p class="num muted">not estimable (no evaluable cases)</p>'
    return (f'<div class="row"><dt>{_e(m["metric"])}</dt><dd>{body}'
            f'<p class="muted">{_e(counts)}</p></dd></div>')


def _metrics_section(view: dict[str, Any]) -> str:
    rows = "".join(_metric_row(m, view["appetite"].get(m["metric"]))
                   for m in view["pack"]["metrics"])
    return f'<dl class="metrics">{rows}</dl>' if rows else _notrun(
        "No verdicts are recorded in this ledger.")


def _rate_section(view: dict[str, Any], key: str, title: str) -> str:
    r = view[key]
    if r is None:
        return _notrun(f"No {title} estimate is recorded in this ledger.")
    head = ""
    if r.get("budget") is not None or r.get("attacker_class") is not None:
        head = (f'<p class="muted">budget {_e(r.get("budget"))}, '
                f'attacker class {_e(r.get("attacker_class"))}</p>')
    if r["lower"] is None:
        return head + ('<p class="num">interval unavailable <span class="muted">(no counts or '
                       'bounds recorded; point estimate withheld)</span></p>')
    text = _interval_text(r["lower"], r["upper"], r["point"])
    return (head + _ruler(r["lower"], r["upper"], r["point"], None, f"{title} {text}")
            + f'<p class="num">{text} <span class="muted">k={_e(r["k"])}, '
            f'n={_e(r["n"])}</span></p>')


def _neff_section(view: dict[str, Any]) -> str:
    neff = view["n_eff"]
    if neff is None:
        return _notrun("No verifier-independence estimate is recorded in this ledger.")
    return (f'<p class="num">n_eff = {_e(neff["value"])} '
            f'<span class="muted">of n = {_e(neff["n"])} verifiers</span></p>')


def _coverage_section(view: dict[str, Any]) -> str:
    cov = view["coverage"]
    declared = view["pack"]["decision"].get("uncovered_risks", [])
    if cov is None:
        base = _notrun("No coverage report is recorded in this ledger.")
        if declared:
            base += "<p>Uncovered risks declared by the decision: " + _e(", ".join(declared))
            base += "</p>"
        return base
    uncovered = sorted(set(cov["uncovered"]) | set(declared))
    covered = len(cov["cells"]) - len(cov["uncovered"])
    items = "".join(f"<li>{_e(c)}</li>" for c in uncovered)
    summary = (f'<p class="num">{covered} of {len(cov["cells"])} risk cells '
               "have at least one test.</p>")
    if not uncovered:
        return summary + '<p class="muted">No uncovered cells recorded.</p>'
    return summary + f'<h3>Uncovered risks</h3><ul class="uncovered">{items}</ul>'


def _section(sid: str, title: str, inner: str) -> str:
    return (f'<section id="{sid}" aria-labelledby="h-{sid}">'
            f'<h2 id="h-{sid}">{title}</h2>{inner}</section>')


def _header(pack: dict[str, Any]) -> str:
    led = pack["ledger"]
    pol = pack["policy"]
    banner = ""
    if pol["example_only"]:
        banner = ('<p class="banner">EXAMPLE policy: not a real risk appetite. '
                  "Do not release on this.</p>")
    return (
        '<header><p class="eyebrow">Pre-release evidence report</p>'
        f'<p class="meta">Policy {_e(pol["id"])} v{_e(pol["version"])} &middot; '
        f'ledger {led["entries"]} entries &middot; chain verified: {_e(led["verified"])} '
        f'&middot; head <button type="button" class="copy" data-copy="{_e(led["head"])}" '
        f'title="Copy full hash">{_e(led["head"][:12])}</button></p></header>{banner}')


def _decision_section(pack: dict[str, Any]) -> str:
    d = pack["decision"]
    cls = DECISION_CLASS.get(d["decision"], "insufficient")
    reasons = "".join(f"<li>{_e(c)}</li>" for c in d["conditions"]) or "<li>No notes.</li>"
    return _section("decision", "Decision",
                    f'<p class="decision {cls}">{_e(d["decision"])}</p>'
                    f'<ul class="reasons">{reasons}</ul>'
                    f'<p class="muted">{_e(pack["human_signoff"])}</p>')


def _access_section(pack: dict[str, Any]) -> str:
    levels = pack["access"]["visibility_levels"]
    names = ", ".join(f"{_e(v)} ({_e(ACCESS_NAMES.get(v, 'unknown'))})" for v in levels)
    return _section("access", "Access level",
                    f'<p class="num">Visibility: {names or "none recorded"}</p>'
                    f'<p class="muted">{_e(pack["access"]["note"])}</p>')


def _validity_section(view: dict[str, Any]) -> str:
    return _section(
        "validity", "Statistical validity",
        "<h3>Effective independent verifiers (n_eff)</h3>" + _neff_section(view)
        + "<h3>Invalid-test rate</h3>"
        + _rate_section(view, "invalid_test_rate", "invalid-test rate")
        + "<h3>ASR@budget</h3>" + _rate_section(view, "asr_at_budget", "ASR@budget"))


def _runs_section(pack: dict[str, Any]) -> str:
    r = pack["runs"]
    return _section("runs", "Runs",
                    f'<p class="num">{r["recorded"]} recorded; {len(r["with_errors"])} with '
                    f'errors; {len(r["unrun_budget_or_kill"])} not run (budget/kill).</p>')


def render_html(view: dict[str, Any]) -> str:
    pack = view["pack"]
    nav = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in NAV)
    claims = "".join(f"<li>{_e(c)}</li>" for c in pack["claims_not_made"])
    evidence = ('<p class="muted">Failure rate per test case. Bar = interval, dot = estimate, '
                "vertical line = policy risk appetite.</p>" + _metrics_section(view))
    body = (_header(pack) + _decision_section(pack) + _access_section(pack)
            + _section("evidence", "Evidence", evidence)
            + _section("coverage", "Coverage and uncovered risks", _coverage_section(view))
            + _validity_section(view) + _runs_section(pack)
            + _section("claims", "Claims not made", f"<ul>{claims}</ul>")
            + '<footer class="muted">Generated from the ledger only; the same ledger and '
              "policy give the same file.</footer>")
    csp = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{csp}">\n'
        f'<title>Evidence report: {_e(pack["decision"]["decision"])}</title>'
        f"<style>{CSS}</style></head>\n"
        f'<body><div class="page"><nav aria-label="Sections"><ol>{nav}</ol></nav>'
        f"<main>{body}</main></div>\n<script>{JS}</script></body></html>\n")
