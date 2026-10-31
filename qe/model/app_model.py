"""App-model builder (T2.1): graph of components with per-edge uncertainty.

Edge uncertainty = exact Clopper-Pearson interval for the fraction of traces in which the edge
appears (`observed`/`trials`). It describes sampling uncertainty of *observed* behaviour only;
edges that were never observed are not shown absent, and declared (OpenAPI) nodes that no trace
touched are listed by `unobserved_nodes()`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from qe.core.schemas import Frozen, Span
from qe.stats.intervals import clopper_pearson


class Node(Frozen):
    id: str
    kind: str  # llm | tool | agent | retriever | memory | endpoint | other


class Edge(Frozen):
    src: str
    dst: str
    provenance: str  # observed | declared
    observed: int = 0
    trials: int = 0
    lower: float = 0.0
    upper: float = 1.0  # no data -> maximal uncertainty


class AppModel(Frozen):
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    n_traces: int = 0

    def unobserved_nodes(self) -> tuple[str, ...]:
        seen = {e.src for e in self.edges if e.provenance == "observed"} | {
            e.dst for e in self.edges if e.provenance == "observed"
        }
        return tuple(sorted(n.id for n in self.nodes if n.id not in seen))

    def node_ids(self) -> frozenset[str]:
        return frozenset(n.id for n in self.nodes)


def _node_of(s: Span) -> tuple[str, str]:
    a = s.attributes
    if s.kind == "tool_call":
        return f"tool:{a.get('tool', 'unknown')}", "tool"
    if s.kind == "llm_call":
        return f"llm:{a.get('role', 'unknown')}", "llm"
    if s.kind == "retrieval":
        return "retriever:main", "retriever"
    if s.kind in ("memory_read", "memory_write"):
        return "memory:main", "memory"
    return f"other:{s.kind}", "other"


def build_from_traces(traces: Sequence[Sequence[Span]]) -> AppModel:
    nodes: dict[str, str] = {}
    counts: Counter[tuple[str, str]] = Counter()
    for trace in traces:
        edges_here: set[tuple[str, str]] = set()
        prev: str | None = None
        for s in trace:
            if s.kind == "handoff":
                src, dst = f"agent:{s.attributes.get('from')}", f"agent:{s.attributes.get('to')}"
                nodes[src] = nodes[dst] = "agent"
                edges_here.add((src, dst))
                prev = dst
                continue
            nid, kind = _node_of(s)
            nodes[nid] = kind
            if prev is not None and prev != nid:
                edges_here.add((prev, nid))
            prev = nid
        counts.update(edges_here)
    n = len(traces)
    edges = []
    for (src, dst), k in sorted(counts.items()):
        lo, hi = clopper_pearson(k, n)
        edges.append(
            Edge(src=src, dst=dst, provenance="observed", observed=k, trials=n, lower=lo, upper=hi)
        )
    return AppModel(
        nodes=tuple(Node(id=i, kind=k) for i, k in sorted(nodes.items())),
        edges=tuple(edges),
        n_traces=n,
    )


def build_from_openapi(spec: dict[str, Any]) -> AppModel:
    """Declared endpoints only (no edges are inferred from a spec)."""
    ids: list[str] = []
    for path, ops in (spec.get("paths") or {}).items():
        for method in ops:
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                ids.append(f"endpoint:{method.upper()} {path}")
    return AppModel(nodes=tuple(Node(id=i, kind="endpoint") for i in sorted(ids)), edges=())


def merge(a: AppModel, b: AppModel) -> AppModel:
    nodes = {n.id: n for n in (*a.nodes, *b.nodes)}
    edges = {(e.src, e.dst, e.provenance): e for e in (*a.edges, *b.edges)}
    return AppModel(
        nodes=tuple(nodes[k] for k in sorted(nodes)),
        edges=tuple(edges[k] for k in sorted(edges)),
        n_traces=max(a.n_traces, b.n_traces),
    )
