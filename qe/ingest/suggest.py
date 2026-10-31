"""Propose knowledge-base documents found in a workspace (never executes or follows symlinks)."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from qe.ingest.analyzer import SKIP_DIRS
from qe.ingest.limits import MAX_DOC_TEXT, MAX_DOCUMENTS, MAX_TOTAL_DOC_TEXT

DOC_EXT = frozenset({".md", ".txt", ".rst"})
DOC_DIRS = frozenset({"docs", "doc", "data", "documents", "knowledge", "kb", "corpus"})


class SuggestedDocument(BaseModel):
    name: str
    path: str
    chars: int
    text: str


def _wanted(rel: Path) -> bool:
    if rel.suffix.lower() not in DOC_EXT:
        return False
    top = rel.parts[0].lower() if len(rel.parts) > 1 else ""
    return rel.name.lower().startswith("readme") or top in DOC_DIRS


def suggest_documents(root: Path) -> list[SuggestedDocument]:
    base = root.resolve()
    out: list[SuggestedDocument] = []
    total = 0
    for cur, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for n in sorted(names):
            p = Path(cur) / n
            if p.is_symlink() or not p.resolve().is_relative_to(base):
                continue
            rel = p.resolve().relative_to(base)
            if not _wanted(rel):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")[:MAX_DOC_TEXT]
            except OSError:
                continue
            if not text.strip() or total + len(text) > MAX_TOTAL_DOC_TEXT:
                continue
            total += len(text)
            out.append(SuggestedDocument(name=rel.as_posix()[:200], path=rel.as_posix(),
                                         chars=len(text), text=text))
            if len(out) >= MAX_DOCUMENTS:
                return out
    return out
