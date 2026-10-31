"""Delta-debugging (ddmin, Zeller & Hildebrandt) over input sentences and context documents.

The failure predicate is noisy, so each probe is repeated `repeats_needed(flake, alpha)` times
and counts as failing if ANY repeat fails. A spurious "pass" (probability <= alpha per probe)
can only make the result less minimal, never make a non-failing candidate look failing, so a
minimized case still fails on the probes that kept it. Minimal = 1-minimal w.r.t. these pieces.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from qe.core.ids import content_id
from qe.core.schemas import TestCase
from qe.regress.admission import repeats_needed

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [p for p in (s.strip() for s in _SENTENCE_END.split(text)) if p]


def ddmin[T](items: Sequence[T], fails: Callable[[list[T]], bool]) -> list[T]:
    current = list(items)
    if not fails(current):
        raise ValueError("the full input does not fail; nothing to minimize")
    if not current or fails([]):
        return []
    n = 2
    while len(current) >= 2:
        chunks = _chunks(current, n)
        reduced = _first_failing(chunks, fails)
        if reduced is not None:
            current, n = reduced, 2
            continue
        complements = [[x for j, c in enumerate(chunks) if j != i for x in c]
                       for i in range(len(chunks))]
        reduced = _first_failing(complements, fails)
        if reduced is not None:
            current, n = reduced, max(n - 1, 2)
        elif n < len(current):
            n = min(len(current), 2 * n)
        else:
            break
    return current


def _chunks[T](seq: list[T], n: int) -> list[list[T]]:
    size, extra = divmod(len(seq), n)
    out, start = [], 0
    for i in range(n):
        end = start + size + (1 if i < extra else 0)
        out.append(seq[start:end])
        start = end
    return [c for c in out if c]


def _first_failing[T](
    candidates: list[list[T]], fails: Callable[[list[T]], bool]
) -> list[T] | None:
    for cand in candidates:
        if fails(cand):
            return cand
    return None


class Minimized(BaseModel):
    model_config = ConfigDict(frozen=True)
    case: TestCase
    original_pieces: int
    final_pieces: int
    probes: int


def minimize_case(
    case: TestCase, fails: Callable[[dict[str, Any]], bool], *, flake_rate: float, alpha: float,
) -> Minimized:
    """Minimize `case.input['input']` (by sentence) and `case.input['context']` (by item)."""
    repeats = repeats_needed(flake_rate, alpha)
    pieces: list[tuple[str, str]] = [("q", s) for s in split_sentences(str(case.input["input"]))]
    pieces += [("c", str(c)) for c in case.input.get("context", [])]
    probes = 0

    def build(sub: Sequence[tuple[str, str]]) -> dict[str, Any]:
        out = {k: v for k, v in case.input.items() if k not in ("input", "context")}
        out["input"] = " ".join(t for kind, t in sub if kind == "q")
        out["context"] = [t for kind, t in sub if kind == "c"]
        return out

    def noisy_fails(sub: list[tuple[str, str]]) -> bool:
        nonlocal probes
        candidate = build(sub)
        for _ in range(repeats):
            probes += 1
            if fails(candidate):
                return True
        return False

    try:
        kept = ddmin(pieces, noisy_fails)
    except ValueError as exc:
        raise ValueError(f"case {case.id} does not reproduce: {exc}") from exc
    new_input = build(kept)
    if not case.input.get("context"):
        new_input.pop("context", None)
    minimized = TestCase(
        id=content_id({"minimized_from": case.id, "input": new_input}),
        risk_cell=case.risk_cell, input=new_input, oracle_source=case.oracle_source,
        lineage=(*case.lineage, case.id), validity=case.validity)
    return Minimized(case=minimized, original_pieces=len(pieces), final_pieces=len(kept),
                     probes=probes)
