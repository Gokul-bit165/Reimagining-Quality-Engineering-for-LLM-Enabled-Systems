"""T2.1 app-model builder: a graph from trace spans (and optional OpenAPI JSON), deterministic.

Each edge records how many runs traversed it and an exact (Clopper-Pearson) interval on the
per-run traversal probability. Edges declared only by OpenAPI have n_observed = 0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import Field

from qe.core.events import EventType
from qe.core.ledger import Ledger
from qe.core.schemas import Frozen, RunRecord, Span
from qe.stats.intervals import clopper_pearson

ENTRY = "entry"


class ModelNode(Frozen):
    id: str
    kind: str  # entry | retriever | doc | tool | llm | agent | memory | api


class ModelEdge(Frozen):
    src: str
    dst: str
    kind: str  # retrieval | tool_call | llm_call | handoff | memory_read | memory_write | ...
    n_observed: int  # runs in which the edge was traversed
    p_lower: float = Field(allow_inf_nan=False)
    p_upper: float = Field(allow_inf_nan=False)
    sources: tuple[str, ...]  # "trace" and/or "openapi"

    @property
    def uncertainty(self) -> float:
        return self.p_upper - self.p_lower


class AppModel(Frozen):
    n_runs: int
    confidence: float
    nodes: tuple[ModelNode, ...]
    edges: tuple[ModelEdge, ...]


def spans_from_trace(trace: Iterable[Mapping[str, Any]]) -> tuple[Span, ...]:
    """Convert raw sandbox/SDK trace events into Span objects (kind = event type)."""
    return tuple(
        Span(span_id=f"s{i}", kind=str(ev.get("type", "other")), attributes=dict(ev))
        for i, ev in enumerate(trace)
    )


def runs_from_ledger(ledger: Ledger) -> list[RunRecord]:
    return [
        RunRecord.model_validate(e.event.payload)
        for e in ledger.entries()
        if e.event.type is EventType.RUN_RECORDED
    ]


def _node_kind(node_id: str) -> str:
    return node_id.split(":", 1)[0] if ":" in node_id else node_id


def _step(span: Span) -> tuple[str, str] | None:
    """(node id, edge kind) a span moves the flow to; None for kinds the model ignores."""
    a = span.attributes
    if span.kind == "retrieval":
        return "retriever", "retrieval"
    if span.kind == "tool_call":
        return f"tool:{a.get('tool', 'unknown')}", "tool_call"
    if span.kind == "llm_call":
        return f"llm:{a.get('role', 'unknown')}", "llm_call"
    if span.kind in ("memory_read", "memory_write"):
        return f"memory:{a.get('scope', 'unknown')}", span.kind
    return None


def run_edges(spans: Sequence[Span]) -> set[tuple[str, str, str]]:
    """Distinct (src, dst, kind) edges traversed by one run."""
    edges: set[tuple[str, str, str]] = set()
    prev = ENTRY
    for span in spans:
        if span.kind == "handoff":
            src = f"agent:{span.attributes.get('from', 'unknown')}"
            dst = f"agent:{span.attributes.get('to', 'unknown')}"
            edges.add((src, dst, "handoff"))
            prev = dst
            continue
        step = _step(span)
        if step is None:
            continue
        node, kind = step
        edges.add((prev, node, kind))
        if span.kind == "retrieval":
            for hit in span.attributes.get("results", []):
                edges.add((node, f"doc:{hit.get('doc_id', 'unknown')}", "retrieves_doc"))
        prev = node
    return edges


def _openapi_edges(spec: Mapping[str, Any]) -> set[tuple[str, str, str]]:
    edges: set[tuple[str, str, str]] = set()
    for path, ops in dict(spec.get("paths", {})).items():
        for method in dict(ops):
            edges.add((ENTRY, f"api:{str(method).upper()} {path}", "api"))
    return edges


def build_model(
    runs: Sequence[RunRecord],
    openapi: Mapping[str, Any] | None = None,
    confidence: float = 0.95,
) -> AppModel:
    counts: dict[tuple[str, str, str], int] = {}
    for run in runs:
        for edge in run_edges(run.spans):
            counts[edge] = counts.get(edge, 0) + 1
    declared = _openapi_edges(openapi) if openapi else set()
    n = len(runs)
    edges: list[ModelEdge] = []
    for edge in sorted(set(counts) | declared):
        k = counts.get(edge, 0)
        lo, hi = clopper_pearson(k, n, confidence) if n > 0 else (0.0, 1.0)
        sources = tuple(s for s, on in (("trace", k > 0), ("openapi", edge in declared)) if on)
        edges.append(
            ModelEdge(src=edge[0], dst=edge[1], kind=edge[2], n_observed=k,
                      p_lower=lo, p_upper=hi, sources=sources)
        )
    ids = sorted({e.src for e in edges} | {e.dst for e in edges})
    nodes = tuple(ModelNode(id=i, kind=_node_kind(i)) for i in ids)
    return AppModel(n_runs=n, confidence=confidence, nodes=nodes, edges=tuple(edges))
