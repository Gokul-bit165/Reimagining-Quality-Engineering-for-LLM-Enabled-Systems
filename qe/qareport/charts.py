"""Inline SVG charts built without libraries. Colours are the tokens of frontend/src/styles/
tokens.css; each chart has a title, a description and a real data table next to it."""

from __future__ import annotations

from html import escape
from typing import Any

INK = "#1d1b17"
INK_SOFT = "#5a554b"
RULE = "#d9d4c7"
BAR = "#cfc8b4"
ACCENT = "#1f4fd8"
WIDTH = 720
LABEL_W = 150
PLOT_L = LABEL_W + 10
PLOT_R = WIDTH - 20
ROW_H = 30


def _x(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    span = (hi - lo) or 1.0
    return PLOT_L + (min(max(v, lo), hi) - lo) / span * (PLOT_R - PLOT_L)


def interval_chart(rows: list[dict[str, Any]], title: str, desc: str, uid: str) -> str:
    height = ROW_H * len(rows) + 46
    out = [f'<svg viewBox="0 0 {WIDTH} {height}" width="100%" role="img" '
           f'aria-labelledby="{uid}-t {uid}-d" xmlns="http://www.w3.org/2000/svg">',
           f'<title id="{uid}-t">{escape(title)}</title><desc id="{uid}-d">{escape(desc)}</desc>']
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        x = _x(tick)
        out.append(f'<line x1="{x:.1f}" y1="10" x2="{x:.1f}" y2="{height - 26}" stroke="{RULE}" '
                   'stroke-width="1"/>')
        out.append(f'<text x="{x:.1f}" y="{height - 8}" font-size="11" text-anchor="middle" '
                   f'fill="{INK_SOFT}">{tick:g}</text>')
    for i, r in enumerate(rows):
        y = 22 + i * ROW_H
        out.append(f'<text x="{LABEL_W}" y="{y + 4}" font-size="12" text-anchor="end" '
                   f'fill="{INK}">{escape(str(r["label"]))}</text>')
        if r["value"] is None:
            out.append(f'<text x="{PLOT_L}" y="{y + 4}" font-size="12" fill="{INK_SOFT}">'
                       f'not measurable (n={escape(str(r["n"]))})</text>')
            continue
        if r["lo"] is not None:
            out.append(f'<rect x="{_x(r["lo"]):.1f}" y="{y - 5}" '
                       f'width="{max(_x(r["hi"]) - _x(r["lo"]), 1):.1f}" height="10" '
                       f'fill="{BAR}" stroke="{INK_SOFT}" stroke-width="1"/>')
        out.append(f'<circle cx="{_x(r["value"]):.1f}" cy="{y}" r="4.5" fill="{INK}"/>')
        if r.get("marker") is not None:
            mx = _x(r["marker"])
            out.append(f'<line x1="{mx:.1f}" y1="{y - 11}" x2="{mx:.1f}" y2="{y + 11}" '
                       f'stroke="{ACCENT}" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


def latency_chart(lat: dict[str, Any], title: str, desc: str, uid: str) -> str:
    keys = [k for k in ("p50", "p90", "p95", "p99") if lat.get(k) is not None]
    if not keys:
        return (f'<svg viewBox="0 0 {WIDTH} 40" width="100%" role="img" aria-labelledby="{uid}-t" '
                f'xmlns="http://www.w3.org/2000/svg"><title id="{uid}-t">{escape(title)}: no '
                f'successful calls</title><text x="10" y="24" font-size="12" fill="{INK_SOFT}">'
                "no successful call, no latency</text></svg>")
    top = max(lat[k] for k in keys) or 1.0
    height = ROW_H * len(keys) + 40
    out = [f'<svg viewBox="0 0 {WIDTH} {height}" width="100%" role="img" '
           f'aria-labelledby="{uid}-t {uid}-d" xmlns="http://www.w3.org/2000/svg">',
           f'<title id="{uid}-t">{escape(title)}</title><desc id="{uid}-d">{escape(desc)}</desc>']
    for i, k in enumerate(keys):
        y = 20 + i * ROW_H
        w = (lat[k] / top) * (PLOT_R - PLOT_L)
        out.append(f'<text x="{LABEL_W}" y="{y + 4}" font-size="12" text-anchor="end" '
                   f'fill="{INK}">{k}</text>')
        out.append(f'<rect x="{PLOT_L}" y="{y - 8}" width="{max(w, 1):.1f}" height="16" '
                   f'fill="{BAR}" stroke="{INK_SOFT}" stroke-width="1"/>')
        out.append(f'<text x="{PLOT_L + max(w, 1) + 6:.1f}" y="{y + 4}" font-size="12" '
                   f'fill="{INK}">{lat[k]:.4f} s</text>')
    out.append("</svg>")
    return "".join(out)
