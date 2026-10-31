"""T2.1 app-model builder with per-edge uncertainty."""

from qe.core.schemas import Span
from qe.model.app_model import build_from_openapi, build_from_traces, merge


def sp(i: int, kind: str, **attrs: object) -> Span:
    return Span(span_id=f"s{i}", kind=kind, attributes=dict(attrs))


def trace_tool() -> tuple[Span, ...]:
    return (sp(0, "llm_call", role="planner"), sp(1, "tool_call", tool="search", status="ok"))


def trace_plain() -> tuple[Span, ...]:
    return (sp(0, "llm_call", role="planner"),)


def test_nodes_and_edges_from_traces_with_exact_intervals() -> None:
    m = build_from_traces([trace_tool(), trace_plain(), trace_plain(), trace_plain()])
    assert {n.id for n in m.nodes} == {"llm:planner", "tool:search"}
    e = next(e for e in m.edges if (e.src, e.dst) == ("llm:planner", "tool:search"))
    assert (e.observed, e.trials, e.provenance) == (1, 4, "observed")
    assert 0.0 < e.lower < 0.25 < e.upper < 1.0  # Clopper-Pearson for 1/4


def test_more_traces_tighten_interval() -> None:
    small = build_from_traces([trace_tool()] * 4)
    big = build_from_traces([trace_tool()] * 40)
    w = lambda m: m.edges[0].upper - m.edges[0].lower  # noqa: E731
    assert w(big) < w(small)


def test_handoff_edge_uses_from_to() -> None:
    m = build_from_traces([(sp(0, "handoff", **{"from": "planner", "to": "writer"}),)])
    assert [(e.src, e.dst) for e in m.edges] == [("agent:planner", "agent:writer")]


def test_empty_traces_gives_empty_model_not_error() -> None:
    m = build_from_traces([])
    assert m.nodes == () and m.edges == ()


def test_openapi_declared_edges_have_no_frequency_and_merge_flags_unobserved() -> None:
    spec = {"paths": {"/invoke": {"post": {"operationId": "invoke"}}, "/health": {"get": {}}}}
    declared = build_from_openapi(spec)
    assert {n.id for n in declared.nodes} == {"endpoint:POST /invoke", "endpoint:GET /health"}
    merged = merge(declared, build_from_traces([trace_tool()]))
    assert "endpoint:POST /invoke" in merged.unobserved_nodes()


def test_model_cid_is_deterministic_and_order_independent() -> None:
    a = build_from_traces([trace_tool(), trace_plain()])
    b = build_from_traces([trace_plain(), trace_tool()])
    assert a.cid() == b.cid()
