"""Markdown renderer for the document tree (charts are HTML-only; their data is in tables)."""

from __future__ import annotations

import re
from typing import Any

from qe.qareport.doc import build_doc


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _fence(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def render_markdown(report: dict[str, Any]) -> str:
    out: list[str] = []
    for b in build_doc(report):
        t = b["t"]
        if t == "h":
            out += ["#" * b["l"] + " " + b["text"], ""]
        elif t == "p":
            out += [b["text"], ""]
        elif t == "ul":
            out += [f"- {x}" for x in b["items"]] + [""]
        elif t == "ol":
            out += [f"{i}. {x}" for i, x in enumerate(b["items"], 1)] + [""]
        elif t == "table":
            out += [f"*{b['caption']}*", "", "| " + " | ".join(_cell(h) for h in b["head"]) + " |",
                    "|" + "---|" * len(b["head"])]
            out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in b["rows"]] + [""]
        elif t == "code":
            fence = _fence(b["text"])
            out += [f"**{b['label']}**", "", fence + "text", b["text"], fence, ""]
        elif t == "callout":
            tag = {"warn": "WARNING", "verdict": "RECOMMENDATION"}.get(b["kind"], "NOTE")
            out += [f"> **{tag}:** {b['text']}", ""]
        elif t == "kv":
            out += [f"- **{k}:** {v}" for k, v in b["rows"]] + [""]
    return "\n".join(out).rstrip() + "\n"
