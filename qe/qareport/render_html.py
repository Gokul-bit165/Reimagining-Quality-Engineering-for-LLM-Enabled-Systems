"""Self-contained single-file HTML: inline CSS and SVG, no JavaScript, no external assets.

Typography and colour roles follow frontend/src/styles/tokens.css (paper, ink, rule, state
colours). The recommendation is conveyed by text, never by colour alone.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from qe.qareport.charts import interval_chart, latency_chart
from qe.qareport.doc import build_doc

CSS = """
:root{--font-serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--font-sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
--font-mono:ui-monospace,"Cascadia Code","SF Mono",Consolas,monospace;
--text-xs:.75rem;--text-sm:.875rem;--text-md:1rem;--text-lg:1.25rem;--text-xl:1.75rem;
--text-display:clamp(2rem,1.4rem + 2.4vw,3.25rem);
--space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;--space-5:24px;--space-6:32px;
--space-7:48px;--radius:2px;--paper:#faf8f3;--paper-sunk:#f1eee6;--ink:#1d1b17;
--ink-soft:#5a554b;--rule:#d9d4c7;--focus:#1f4fd8;--reject:#a3281f;--conditional:#8a5a00}
*{box-sizing:border-box}
html{background:var(--paper);color:var(--ink);font-family:var(--font-sans);
font-size:100%;line-height:1.55}
body{margin:0 auto;padding:var(--space-5) var(--space-4) var(--space-7);max-width:62rem}
h1,h2,h3,h4{font-family:var(--font-serif);line-height:1.2;font-weight:600;
overflow-wrap:anywhere}
h1{font-size:var(--text-display);margin:var(--space-5) 0 var(--space-4)}
h2{font-size:var(--text-xl);margin:var(--space-7) 0 var(--space-3);
border-top:1px solid var(--rule);padding-top:var(--space-5)}
h3{font-size:var(--text-lg);margin:var(--space-6) 0 var(--space-2)}
h4{font-size:var(--text-md);margin:var(--space-5) 0 var(--space-2)}
p,ul,ol{margin:var(--space-2) 0 var(--space-3)}
li{margin:var(--space-1) 0;overflow-wrap:anywhere}
a{color:var(--focus)}
a:focus-visible,[tabindex]:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.skip{position:absolute;left:-999px}.skip:focus{left:var(--space-3);top:var(--space-3);
background:var(--paper);padding:var(--space-2);z-index:2}
nav.toc{background:var(--paper-sunk);padding:var(--space-3) var(--space-4);
border-left:3px solid var(--rule);font-size:var(--text-sm)}
nav.toc ol{margin:0;padding:0;list-style:none;columns:2 16rem}
.scroll{overflow-x:auto;margin:var(--space-3) 0}
table{border-collapse:collapse;width:100%;min-width:36rem;font-size:var(--text-sm);
font-variant-numeric:tabular-nums}
caption{text-align:left;font-weight:600;padding:var(--space-2) 0;color:var(--ink-soft)}
th,td{border-bottom:1px solid var(--rule);padding:var(--space-2) var(--space-3);
text-align:left;vertical-align:top;overflow-wrap:break-word}
td:first-child{white-space:nowrap}
thead th{background:var(--paper-sunk);border-bottom:2px solid var(--ink)}
pre{background:var(--paper-sunk);border:1px solid var(--rule);border-radius:var(--radius);
padding:var(--space-3);overflow:auto;font-family:var(--font-mono);font-size:var(--text-sm);
white-space:pre-wrap;overflow-wrap:anywhere;margin:var(--space-1) 0 var(--space-3)}
.label{font-size:var(--text-sm);font-weight:600;color:var(--ink-soft);margin-top:var(--space-3)}
dl.kv{display:grid;grid-template-columns:minmax(9rem,14rem) 1fr;gap:var(--space-1) var(--space-4);
margin:var(--space-3) 0}
dl.kv dt{font-weight:600;color:var(--ink-soft)}dl.kv dd{margin:0;overflow-wrap:anywhere}
.callout{border:1px solid var(--rule);border-left:6px solid var(--ink-soft);
padding:var(--space-3) var(--space-4);margin:var(--space-3) 0;background:var(--paper-sunk)}
.callout.warn{border-left-color:var(--reject);font-weight:600}
figure{margin:var(--space-4) 0}figcaption{font-size:var(--text-sm);color:var(--ink-soft)}
.verdict{font-family:var(--font-serif);font-size:var(--text-lg);font-weight:600}
.meta{color:var(--ink-soft);font-size:var(--text-sm)}
@media (max-width:40rem){dl.kv{grid-template-columns:1fr}dl.kv dd{margin-bottom:var(--space-2)}
body{padding:var(--space-4) var(--space-3) var(--space-6)}}
@media print{html{background:#fff;font-size:10.5pt}body{max-width:none;padding:0}
h2{break-after:avoid}table,pre,figure,.callout{break-inside:avoid}nav.toc,.skip{display:none}
a{color:inherit}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def _slug(text: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}-{n}", n + 1
    used.add(slug)
    return slug


def _table(b: dict[str, Any]) -> str:
    head = "".join(f'<th scope="col">{escape(h)}</th>' for h in b["head"])
    rows = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>"
                   for r in b["rows"])
    cap = escape(b["caption"])
    return (f'<div class="scroll" role="region" aria-label="{cap}" tabindex="0"><table>'
            f"<caption>{cap}</caption><thead><tr>{head}</tr></thead><tbody>{rows}</tbody>"
            "</table></div>")


def _chart(b: dict[str, Any], uid: str) -> str:
    svg = (interval_chart(b["data"], b["title"], b["desc"], uid) if b["kind"] == "intervals"
           else latency_chart(b["data"], b["title"], b["desc"], uid))
    cap = f"{escape(b['title'])}. {escape(b['desc'])}"
    return f"<figure>{svg}<figcaption>{cap}</figcaption></figure>"


def render_html(report: dict[str, Any]) -> str:
    used: set[str] = set()
    toc: list[tuple[str, str]] = []
    body: list[str] = []
    charts = 0
    for b in build_doc(report):
        t = b["t"]
        if t == "h":
            slug = _slug(b["text"], used)
            if b["l"] == 2:
                toc.append((slug, b["text"]))
            body.append(f'<h{b["l"]} id="{slug}">{escape(b["text"])}</h{b["l"]}>')
        elif t == "p":
            body.append(f"<p>{escape(b['text'])}</p>")
        elif t in ("ul", "ol"):
            items = "".join(f"<li>{escape(x)}</li>" for x in b["items"])
            body.append(f"<{t}>{items}</{t}>")
        elif t == "table":
            body.append(_table(b))
        elif t == "code":
            body.append(f'<div class="label">{escape(b["label"])}</div>'
                        f'<pre tabindex="0">{escape(b["text"])}</pre>')
        elif t == "callout" and b["kind"] == "verdict":
            body.append(f'<p class="verdict">{escape(b["text"])}</p>')
        elif t == "callout":
            role = ' role="alert"' if b["kind"] == "warn" else ""
            prefix = "Warning: " if b["kind"] == "warn" else "Note: "
            body.append(f'<div class="callout {b["kind"]}"{role}>{prefix}{escape(b["text"])}</div>')
        elif t == "kv":
            body.append('<dl class="kv">' + "".join(
                f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in b["rows"]) + "</dl>")
        elif t == "chart":
            charts += 1
            body.append(_chart(b, f"chart{charts}"))
    nav = "".join(f'<li><a href="#{s}">{escape(x)}</a></li>' for s, x in toc)
    title = escape(report["title"])
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{CSS}</style></head><body>"
        '<a class="skip" href="#main">Skip to report</a>'
        f'<header><p class="meta">Quality-tester report - schema {escape(report["schema"])}</p>'
        "</header>"
        f'<nav class="toc" aria-label="Contents"><ol>{nav}</ol></nav>'
        f'<main id="main">{"".join(body)}</main></body></html>\n')
