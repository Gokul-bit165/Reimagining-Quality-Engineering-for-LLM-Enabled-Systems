from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.realeval import audit, jobs, resolver
from qe.realeval.resolver import ResolvedProject, ResolveError
from qe.realeval.target import FakeRagTarget
from qe.ui.server import app
from tests.realeval.conftest import DOC, QA

client = TestClient(app)
STATE: dict[str, Any] = {"mode": "hallucinating", "authorized": True, "err": None}


def _resolve(pid: str) -> ResolvedProject:
    if STATE["err"]:
        raise ResolveError(*STATE["err"])
    return ResolvedProject(pid, "demo", FakeRagTarget([DOC["text"]], STATE["mode"]), [DOC],
                           QA[:12], risk_flags=["hallucination"], authorized=STATE["authorized"])


@pytest.fixture(autouse=True)
def _wire() -> Iterator[None]:
    STATE.update(mode="hallucinating", authorized=True, err=None)
    resolver.set_resolver(_resolve)
    yield
    resolver.set_resolver(None)


def start(**kw: Any) -> dict[str, Any]:
    r = client.post("/api/evaluations", json={"project_id": "p1", "max_questions": 12,
                                              "use_example_policy": True, **kw})
    assert r.status_code == 202, r.text
    return jobs.wait(r.json()["id"])


def test_contract_shape() -> None:
    r = client.post("/api/evaluations", json={"project_id": "p1", "max_questions": 12,
                                              "generate_questions": False,
                                              "use_example_policy": True})
    assert r.status_code == 202 and set(r.json()) == {"id", "state"}
    rec = jobs.wait(r.json()["id"])
    got = client.get(f"/api/evaluations/{rec['id']}").json()
    for key in ("id", "project_id", "state", "progress", "error", "metrics",
                "decision", "items", "scorecard", "failure_taxonomy", "regression"):
        assert key in got
    assert got["state"] == "done" and got["progress"]["done"] == got["progress"]["total"]
    m = got["metrics"]["answer_correctness"]
    assert {"value", "ci_low", "ci_high", "n", "note"} <= set(m)
    item = got["items"][0]
    assert {"id", "question", "reference_answer", "answer", "contexts", "scores", "passed",
            "failure_reason", "source", "failure_class"} <= set(item)
    assert set(got["scorecard"]) == {"accuracy", "grounding", "completeness", "safety",
                                     "consistency", "security"}
    assert got["decision"]["status"] == "pending_review"
    assert any(e["id"] == got["id"] for e in client.get("/api/evaluations").json())


def test_refuses_unauthorized_and_unready_projects() -> None:
    STATE["authorized"] = False
    r = client.post("/api/evaluations", json={"project_id": "p1"})
    assert r.status_code == 403
    STATE["err"] = (409, "project is static_only")
    assert client.post("/api/evaluations", json={"project_id": "p1"}).status_code == 409
    actions = [a["action"] for a in audit.read(jobs.evals_dir())]
    assert actions.count("evaluation_refused") == 2


def test_missing_ingest_gives_409_and_bad_policy_422() -> None:
    resolver.set_resolver(None)
    r = client.post("/api/evaluations", json={"project_id": "nope"})
    assert r.status_code in (404, 409)
    resolver.set_resolver(_resolve)
    bad = {"policy_id": "x", "version": "1", "loss_matrix": {}, "required_evidence": ["a"],
           "risk_appetite": {}}
    r = client.post("/api/evaluations", json={"project_id": "p1", "policy": bad})
    assert r.status_code == 422


def test_no_questions_and_no_generator_is_422_naming_env_vars(
        monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("QE_ALLOW_REAL_LLM", "GROQ_API_KEY", "OPENROUTER_API_KEY", "QE_LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    resolver.set_resolver(lambda pid: ResolvedProject(
        pid, "d", FakeRagTarget([DOC["text"]]), [DOC], [], authorized=True))
    r = client.post("/api/evaluations", json={"project_id": "p1", "use_example_policy": True})
    assert r.status_code == 422
    assert "QE_ALLOW_REAL_LLM" in r.text and "QE_LLM_MODEL" in r.text
    assert "synthetic" not in r.text.lower()


def test_signoff_regression_dataset_report_monitoring() -> None:
    rec = start(generate_questions=False)
    eid = rec["id"]
    assert rec["decision"]["verdict"] in ("REJECT", "INSUFFICIENT_EVIDENCE")
    assert rec["failure_taxonomy"]["QE-FAB"]["count"] > 0

    so = client.post(f"/api/evaluations/{eid}/signoff",
                     json={"reviewer": "dana", "decision": "reject", "rationale": "hallucinates"})
    assert so.status_code == 200 and so.json()["decision"]["status"] == "rejected"
    assert client.post(f"/api/evaluations/{eid}/signoff",
                       json={"reviewer": "dana", "decision": "approve"}).status_code == 409
    assert client.get(f"/api/evaluations/{eid}").json()["decision"]["signoff"]["reviewer"] == "dana"

    adm = client.post(f"/api/evaluations/{eid}/regression", json={}).json()
    assert adm["admitted"] and adm["suite_size"] == len(adm["admitted"])
    assert client.post(f"/api/evaluations/{eid}/regression", json={}).json()["admitted"] == []
    suite = client.get("/api/projects/p1/regression").json()
    assert suite["size"] == adm["suite_size"]

    ds = client.get(f"/api/evaluations/{eid}/dataset")
    rows = [json.loads(line) for line in ds.text.splitlines()]
    assert rows and {"question", "label", "lineage"} <= set(rows[0])
    md = client.get(f"/api/evaluations/{eid}/report")
    assert "Scorecard" in md.text and "EXAMPLE" in md.text
    assert client.get(f"/api/evaluations/{eid}/report?format=json").json()["id"] == eid
    plan = client.get(f"/api/evaluations/{eid}/monitoring-plan").json()
    assert plan["cadence_days"] is None and "NOT SET" in plan["cadence_note"]
    assert plan["thresholds"] and plan["drift_triggers"]
    actions = {a["action"] for a in audit.read(jobs.evals_dir())}
    assert {"evaluation_started", "signoff", "regression_admitted", "dataset_exported"} <= actions


def test_regression_suite_rerun_reports_fixed_and_new() -> None:
    first = start(generate_questions=False)
    client.post(f"/api/evaluations/{first['id']}/regression", json={})
    STATE["mode"] = "perfect"  # the app got fixed
    second = start(generate_questions=False)
    reg = second["regression"]
    assert reg["suite_rerun"] > 0 and len(reg["fixed"]) > 0 and reg["still_failing"] == []
    assert any(r["regression"] for r in second["items"])


def test_cancel_unknown_and_get_unknown() -> None:
    assert client.post("/api/evaluations/eval-deadbeef/cancel").status_code == 404
    assert client.get("/api/evaluations/eval-deadbeef").status_code == 404
    assert client.get("/api/evaluations/../etc").status_code in (404, 422)


def test_new_failures_reported_against_previous_run() -> None:
    STATE["mode"] = "perfect"
    start(generate_questions=False)
    STATE["mode"] = "hallucinating"
    second = start(generate_questions=False)
    assert len(second["regression"]["new_failures"]) > 0


def test_default_resolver_uses_ingest_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from qe.ingest import store
    from qe.ingest.models import Project, ProjectAnalysis, ProjectInputs

    base = Project(id="p9", repo_url="x", created_at=0.0, state="ready", authorized=True,
                   analysis=ProjectAnalysis(execution_mode="endpoint"),
                   inputs=ProjectInputs(endpoint_url="http://127.0.0.1:9/ask"))
    projects = {"p9": base,
                "p8": base.model_copy(update={"analysis": ProjectAnalysis(
                    execution_mode="static_only")}),
                "p7": base.model_copy(update={"state": "analyzing"})}
    monkeypatch.setattr(store, "get", lambda pid: projects.get(pid))
    resolver.set_resolver(None)
    got = resolver.resolve_target("p9")
    assert got.authorized and got.target.ask("q").error  # nothing listens: error is data
    for pid, code in (("p8", 409), ("p7", 409), ("nope", 404)):
        with pytest.raises(ResolveError) as ei:
            resolver.resolve_target(pid)
        assert ei.value.status == code


class AdvisoryGen:
    """Stands in for an LLM question generator: items are advisory until a human confirms."""

    family = "fake-llm"

    def generate(self, documents: list[dict[str, str]], n: int) -> list[Any]:
        from qe.realeval.dataset import EvalItem
        return [EvalItem(id=f"g-{k}", question=q["question"], source="generated",
                         reference_answer=q["reference_answer"],
                         lineage={"operator": "llm_question", "parent": None, "seed": None,
                                  "advisory": True, "confirmed": False})
                for k, q in enumerate(QA[:n])]


def test_advisory_items_do_not_gate_and_confirmation_recomputes(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from qe.ui import routes_eval
    monkeypatch.setattr(routes_eval, "generator_from_env", lambda *a, **k: AdvisoryGen())
    resolver.set_resolver(lambda pid: ResolvedProject(
        pid, "d", FakeRagTarget([DOC["text"]], "hallucinating"), [DOC], [], authorized=True))
    rec = start(max_questions=30, include_security=False)
    # a hallucinating app would be REJECTed on 30 failing items, but they are all advisory
    assert rec["metrics"]["answer_correctness"]["n"] > 0  # still scored and reported
    assert rec["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert "advisory until confirmed" in " ".join(rec["decision"]["reasons"])
    assert rec["advisory"]["unconfirmed"] >= 30
    eid = rec["id"]
    for row in rec["items"]:
        if (row["lineage"] or {}).get("advisory"):
            r = client.post(f"/api/evaluations/{eid}/items/{row['id']}/confirm",
                            json={"reviewer": "dana"})
            assert r.status_code == 200, r.text
    after = client.get(f"/api/evaluations/{eid}").json()
    assert after["advisory"]["unconfirmed"] == 0
    assert after["decision"]["verdict"] == "REJECT"
    assert client.post(f"/api/evaluations/{eid}/items/nope/confirm",
                       json={"reviewer": "d"}).status_code == 404
    kinds = [a["action"] for a in audit.read(jobs.evals_dir())]
    assert "item_confirmed" in kinds
    from qe.core.events import EventType
    from qe.core.ledger import SQLiteLedger
    ledger = SQLiteLedger(jobs.evals_dir() / f"{eid}.sqlite")
    humans = [e for e in ledger.entries() if e.event.type is EventType.SIGNOFF_RECORDED]
    ledger.close()
    assert humans and all(e.event.producer_kind.value == "human" for e in humans)


def test_previous_uses_project_index_not_full_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    import time as _t
    for n in range(30):
        jobs._save({"id": f"eval-{n:08x}", "project_id": f"pp{n % 10}", "state": "done",
                    "created": _t.time() + n, "items": [{"id": "x"}], "progress": {}})
    reads: list[str] = []
    real = jobs._read
    monkeypatch.setattr(jobs, "_read", lambda eid: (reads.append(eid), real(eid))[1])
    got = jobs.previous("pp3")
    assert got is not None and got["id"] == "eval-00000017"  # latest of pp3 (n=3,13,23)
    assert len(reads) == 1
