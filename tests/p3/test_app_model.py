import json
from typing import Any

from qe.core.schemas import RunRecord, Span, VisibilityLevel
from qe.model.builder import AppModel, build_model, spans_from_trace
from sandbox_apps.rag import build_app as build_rag
from sandbox_apps.toolagent import build_app as build_tool

QUESTIONS = ["How many days do I have to return an item?", "Can you ship lithium batteries?"]


def run(app_builder: Any, variant: str, reqs: list[dict[str, Any]]) -> list[RunRecord]:
    out = []
    for i, r in enumerate(reqs):
        app = app_builder(variant)
        resp = app.invoke({**r, "want_trace": True})
        out.append(
            RunRecord(
                test_case_id=f"t{i}", repeat_index=0, seed=0,
                visibility_level=VisibilityLevel.B_SDK, request=r, response={},
                spans=spans_from_trace(resp["trace"]),
            )
        )
    return out


def test_rag_model_has_retrieval_and_llm_edges_with_uncertainty() -> None:
    runs = run(build_rag, "clean", [{"input": q} for q in QUESTIONS])
    model = build_model(runs)
    kinds = {e.kind for e in model.edges}
    assert {"retrieval", "llm_call", "retrieves_doc"} <= kinds
    assert model.n_runs == 2
    top = next(e for e in model.edges if e.kind == "retrieval")
    assert top.n_observed == 2 and top.p_upper == 1.0 and 0.0 < top.p_lower < 1.0
    once = [e for e in model.edges if e.kind == "retrieves_doc" and e.n_observed == 1]
    assert once and all(0.0 < e.p_lower < e.p_upper < 1.0 for e in once)


def test_model_is_deterministic_and_order_independent() -> None:
    runs = run(build_rag, "clean", [{"input": q} for q in QUESTIONS])
    a, b = build_model(runs), build_model(list(reversed(runs)))
    assert a.cid() == b.cid()
    assert json.loads(a.model_dump_json()) == json.loads(b.model_dump_json())


def test_toolagent_model_has_tool_edges() -> None:
    runs = run(build_tool, "clean", [{"input": "summarize my notes", "user": "alice"}])
    model = build_model(runs)
    assert any(n.id == "tool:search_notes" for n in model.nodes)
    assert any(e.kind == "tool_call" for e in model.edges)


def test_openapi_adds_declared_unobserved_edges() -> None:
    runs = run(build_rag, "clean", [{"input": QUESTIONS[0]}])
    spec = {"paths": {"/invoke": {"post": {}}, "/health": {"get": {}}}}
    model = build_model(runs, openapi=spec)
    api = [e for e in model.edges if e.kind == "api"]
    assert {e.dst for e in api} == {"api:POST /invoke", "api:GET /health"}
    assert all(e.n_observed == 0 and e.sources == ("openapi",) for e in api)
    assert all(e.p_upper < 1.0 for e in api)  # 0 of 1 runs: bounded, not certainly absent


def test_empty_runs_gives_maximal_uncertainty_model() -> None:
    model = build_model([], openapi={"paths": {"/x": {"get": {}}}})
    assert isinstance(model, AppModel) and model.n_runs == 0
    assert (model.edges[0].p_lower, model.edges[0].p_upper) == (0.0, 1.0)


def test_unknown_span_kind_is_ignored() -> None:
    rr = RunRecord(test_case_id="t", repeat_index=0, seed=0,
                   visibility_level=VisibilityLevel.B_SDK, request={}, response={},
                   spans=(Span(span_id="s0", kind="other"),))
    assert build_model([rr]).edges == ()
