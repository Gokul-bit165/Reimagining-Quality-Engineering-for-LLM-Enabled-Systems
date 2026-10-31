from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.campaign import manager, store
from qe.ui.server import app
from tests.campaign.conftest import CHAT_KEY, Server

client = TestClient(app)


def ep(label: str, srv: Server, **meta: Any) -> dict[str, Any]:
    return {"label": label, "kind": "endpoint", "endpoint_url": srv.url + "/ask",
            "metadata": meta}


def create(targets: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    body = {"project_id": "p1", "name": "t", "targets": targets, "use_example_policy": True,
            "generate_with_llm": False, "max_cases": 30, "repeats": 2, **kw}
    r = client.post("/api/campaigns", json=body)
    assert r.status_code == 202, r.text
    return r.json()


def run(targets: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    cid = create(targets, **kw)["id"]
    manager.wait(cid)
    return client.get(f"/api/campaigns/{cid}").json()


def pairs(rec: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    return [p for p in rec["comparisons"]["pairs"] if p["metric"] == metric]


def test_contract_and_identical_plan_across_targets(servers: dict[str, Server]) -> None:
    rec = run([ep("current", servers["good"]), ep("new", servers["bad"])])
    assert rec["state"] == "done", rec.get("error")
    assert set(rec["stages"]) == set(manager.STAGES)
    assert all(rec["stages"][s]["status"] in ("done", "awaiting_review") for s in rec["stages"])
    assert rec["stages"]["test_plan"]["inputs_hash"] and rec["stages"]["execution"]["started"]
    plan = client.get(f"/api/campaigns/{rec['id']}/plan").json()
    assert plan["plan_id"] == rec["plan"]["plan_id"]
    case_ids = [c["id"] for c in plan["cases"]]
    # both targets were asked exactly the same cases, repeats times each
    for label in ("current", "new"):
        assert rec["results"][label]["sample"]["n_items"] == len(case_ids)
        assert rec["results"][label]["performance"]["calls"] == len(case_ids) * 2
    assert sorted(servers["good"].hits) == sorted(servers["bad"].hits)
    assert set(rec["decisions"]) == {"current", "new"}
    assert rec["decisions"]["current"]["policy_is_example"] is True
    assert rec["plan"]["authoring"]["statement"] == "rule-based only; no LLM-authored tests"
    perf = rec["results"]["current"]["performance"]
    assert {"latency_p50_s", "latency_p95_s", "latency_p99_s", "error_rate_calls",
            "response_chars_mean", "tokens"} <= set(perf)
    assert any(c["id"] == rec["id"] for c in client.get("/api/campaigns").json())


def test_interleaved_execution_order(servers: dict[str, Server]) -> None:
    rec = run([ep("a", servers["good"]), ep("b", servers["good"])], max_cases=6, repeats=2)
    with store.ledger(rec["id"]) as lg:
        keys = [e.event.key for e in lg.entries() if e.event.key.startswith("crun:")]
    first_per_round: dict[tuple[str, str], str] = {}
    for k in keys:
        _, label, item, rep = k.split(":")
        first_per_round.setdefault((item, rep), label)
    assert {"a", "b"} == set(first_per_round.values())  # neither target always goes first


def test_paired_direction_good_beats_hallucinating(servers: dict[str, Server]) -> None:
    rec = run([ep("good", servers["good"]), ep("bad", servers["bad"])])
    p = pairs(rec, "overall_pass_rate")[0]
    assert p["outcome"] == "A_BETTER" and p["winner"] == "good"
    assert p["diff"] > 0.3 and p["ci_low"] > 0 and p["p_adjusted"] < 0.05
    assert rec["comparisons"]["multiplicity"].startswith("Bonferroni")
    assert rec["recommendation"]["better_target"] == "good"
    assert rec["results"]["bad"]["decision"]["verdict"] in ("REJECT", "INSUFFICIENT_EVIDENCE")
    # swapping the order flips the label, not the conclusion
    swapped = run([ep("bad", servers["bad"]), ep("good", servers["good"])])
    q = pairs(swapped, "overall_pass_rate")[0]
    assert q["outcome"] == "B_BETTER" and q["winner"] == "good"


def test_injectable_target_loses_on_security(servers: dict[str, Server]) -> None:
    rec = run([ep("safe", servers["good"]), ep("inj", servers["inj"])], max_cases=30)
    inj = rec["results"]["inj"]["metrics"]["injection_resistance"]
    safe = rec["results"]["safe"]["metrics"]["injection_resistance"]
    assert inj["value"] is not None and safe["value"] is not None
    assert inj["value"] < safe["value"]
    assert "QE-INJ" in rec["results"]["inj"]["failure_taxonomy"]


def test_same_target_twice_is_no_significant_difference(servers: dict[str, Server]) -> None:
    rec = run([ep("one", servers["good"]), ep("two", servers["good"])])
    p = pairs(rec, "overall_pass_rate")[0]
    assert p["outcome"] == "NO_SIGNIFICANT_DIFFERENCE" and p["winner"] is None
    assert rec["recommendation"]["better_target"] is None


def test_small_n_is_insufficient_evidence(servers: dict[str, Server]) -> None:
    rec = run([ep("good", servers["good"]), ep("bad", servers["bad"])], max_cases=4,
              include_security=False)
    assert rec["state"] == "done"
    outs = {p["outcome"] for p in rec["comparisons"]["pairs"]}
    assert "A_BETTER" not in outs and "INSUFFICIENT_EVIDENCE" in outs
    assert rec["recommendation"]["better_target"] is None
    assert rec["results"]["good"]["decision"]["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_flaky_target_errors_are_measured(servers: dict[str, Server]) -> None:
    rec = run([ep("good", servers["good"]), ep("flaky", servers["flaky"])], include_security=False)
    perf = rec["results"]["flaky"]["performance"]
    assert perf["errors"] > 0 and perf["error_rate_calls"] > 0.2
    assert rec["results"]["good"]["performance"]["errors"] == 0


def test_slow_target_latency_is_visible(servers: dict[str, Server]) -> None:
    rec = run([ep("fast", servers["good"]), ep("slow", servers["slow"])], max_cases=6,
              include_security=False)
    fast = rec["results"]["fast"]["performance"]["latency_p50_s"]
    slow = rec["results"]["slow"]["performance"]["latency_p50_s"]
    assert slow > fast and slow >= 0.1


def test_resume_after_kill(servers: dict[str, Server], monkeypatch: pytest.MonkeyPatch) -> None:
    class Kill(BaseException):
        pass

    from qe.ingest.target import SandboxedRepoTarget

    real_ask = SandboxedRepoTarget.ask
    counter = {"n": 0}

    def dying(self: SandboxedRepoTarget, q: str) -> Any:
        counter["n"] += 1
        if counter["n"] == 7:
            raise Kill()
        return real_ask(self, q)

    monkeypatch.setattr(SandboxedRepoTarget, "ask", dying)
    cid = create([ep("a", servers["good"]), ep("b", servers["bad"])], max_cases=8,
                 include_security=False, repeats=2)["id"]
    deadline = time.time() + 20
    while manager.load(cid)["state"] != "interrupted" and time.time() < deadline:  # type: ignore[index]
        time.sleep(0.02)
    killed = client.get(f"/api/campaigns/{cid}").json()
    assert killed["state"] == "interrupted" and killed["resumable"] is True
    with store.ledger(cid) as lg:
        before = [e.event.key for e in lg.entries() if e.event.key.startswith("crun:")]
    assert len(before) == 6  # calls 1..6 were durably recorded; call 7 died mid-flight

    monkeypatch.setattr(SandboxedRepoTarget, "ask", real_ask)
    hits_before = len(servers["good"].hits) + len(servers["bad"].hits)
    assert client.post(f"/api/campaigns/{cid}/resume").status_code == 202
    rec = manager.wait(cid)
    assert rec["state"] == "done", rec.get("error")
    with store.ledger(cid) as lg:
        after = [e.event.key for e in lg.entries() if e.event.key.startswith("crun:")]
        assert lg.verify().ok
    assert after[:6] == before and len(after) == len(set(after)) == 8 * 2 * 2
    # the 6 recorded calls were not repeated against the targets
    assert len(servers["good"].hits) + len(servers["bad"].hits) - hits_before == 32 - 6
    assert client.post(f"/api/campaigns/{cid}/resume").status_code == 409  # done: not resumable
    actions = [e["action"] for e in client.get(f"/api/campaigns/{cid}/events").json()["entries"]]
    assert "campaign_resumed" in actions


def test_cancel_marks_incomplete_and_resume_finishes(servers: dict[str, Server]) -> None:
    cid = create([ep("slow", servers["slow"]), ep("good", servers["good"])], max_cases=10,
                 include_security=False)["id"]
    deadline = time.time() + 20
    while manager.load(cid)["progress"]["done"] < 2 and time.time() < deadline:  # type: ignore[index]
        time.sleep(0.02)
    assert client.post(f"/api/campaigns/{cid}/cancel").status_code == 202
    rec = manager.wait(cid)
    assert rec["state"] == "cancelled" and rec["incomplete"]
    assert rec["stages"]["execution"]["status"] == "cancelled"
    assert all(d["verdict"] == "INSUFFICIENT_EVIDENCE" for d in rec["decisions"].values())
    assert client.post(f"/api/campaigns/{cid}/signoff", json={
        "reviewer": "r", "decision": "approve", "target_label": "good"}).status_code == 409
    assert client.post(f"/api/campaigns/{cid}/resume").status_code == 202
    done = manager.wait(cid, 120)
    assert done["state"] == "done" and done["incomplete"] is None


def test_wall_clock_budget_stops_the_run(servers: dict[str, Server]) -> None:
    rec = run([ep("slow", servers["slow"]), ep("good", servers["good"])], timeout_s=0.3,
              max_cases=20, include_security=False)
    assert rec["state"] == "failed" and "wall-clock" in rec["error"]
    assert rec["decisions"]["slow"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert rec["resumable"] is True


def test_call_budget_truncates_the_plan_not_the_comparison(servers: dict[str, Server]) -> None:
    rec = run([ep("a", servers["good"]), ep("b", servers["bad"])], max_calls=40, repeats=2,
              max_cases=30)
    assert rec["state"] == "done"
    assert rec["plan"]["n_cases"] == 10  # 40 calls / (2 repeats x 2 targets)
    assert any("max_calls" in n for n in rec["notes"])
    assert rec["progress"]["done"] == rec["progress"]["total"] == 40
    r = client.post("/api/campaigns", json={
        "project_id": "p1", "name": "x", "use_example_policy": True, "max_calls": 3,
        "repeats": 3, "targets": [ep("a", servers["good"]), ep("b", servers["bad"])]})
    assert r.status_code == 422 and "max_calls" in r.text


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/ask", "https://127.0.0.1x/",
    "http://127.0.0.1:8001/ask", "http://127.0.0.1:9/api/projects"])
def test_ssrf_urls_are_refused(url: str) -> None:
    for spec in ({"label": "x", "kind": "endpoint", "endpoint_url": url},
                 {"label": "x", "kind": "model", "model": "m", "base_url": url}):
        r = client.post("/api/campaigns", json={"project_id": "p1", "name": "n",
                                                "use_example_policy": True, "targets": [spec]})
        assert r.status_code == 422, (url, r.text)


def test_refuses_unauthorized_and_bad_requests(servers: dict[str, Server],
                                               proj: dict[str, Any]) -> None:
    t = [ep("a", servers["good"])]
    proj["authorized"] = False
    assert client.post("/api/campaigns", json={"project_id": "p1", "name": "n",
                                               "use_example_policy": True,
                                               "targets": t}).status_code == 403
    proj["authorized"] = True
    base = {"project_id": "p1", "name": "n", "targets": t}
    assert client.post("/api/campaigns", json=base).status_code == 422  # no policy chosen
    assert client.post("/api/campaigns", json={**base, "targets": []}).status_code == 422
    dup = [ep("a", servers["good"]), ep("A", servers["bad"])]
    assert client.post("/api/campaigns", json={**base, "targets": dup,
                                               "use_example_policy": True}).status_code == 422
    bad = {"label": "m", "kind": "model", "model": "x", "base_url": servers["chat"].url + "/v1",
           "api_key_secret": "NOT_IN_VAULT"}
    assert client.post("/api/campaigns", json={**base, "targets": [bad],
                                               "use_example_policy": True}).status_code == 422
    assert client.get("/api/campaigns/cmp-00000000").status_code == 404
    assert client.get("/api/campaigns/..%2Fx").status_code in (404, 422)


def test_coverage_matrix_reports_gaps_explicitly(servers: dict[str, Server],
                                                 proj: dict[str, Any]) -> None:
    proj["flags"] = ["no_citation_handling", "moon phase drift"]
    rec = run([ep("a", servers["good"])], risk_focus=["hallucination", "made up risk"],
              include_security=False)
    cov = rec["coverage"]
    by = {r["scenario"]: r for r in cov["matrix"] if r["scenario"]}
    assert by["hallucination"]["status"] == "COVERED" and by["hallucination"]["n_tests"] > 0
    assert by["hallucination"]["taxonomy_ids"] == ["LLM09", "QE-FAB"]
    assert by["citation_check"]["status"] == "CHECK_ONLY"
    unmapped = [r for r in cov["matrix"] if r["scenario"] is None]
    assert {u["label"] for u in unmapped} == {"made up risk", "moon phase drift"}
    assert all(u["status"] == "GAP" and u["gap_reason"] for u in unmapped)
    assert {g["risk_id"] for g in cov["gaps"]} >= {"made up risk", "RK-citation_check"}
    assert "LLM03" in cov["taxonomy"]["owasp_llm_2025_unassessed"]
    # security was switched off: its scenarios (if in the register) are explicit gaps
    sec = [r for r in cov["matrix"] if r["scenario"] in ("prompt_injection", "data_leak")]
    assert all(r["status"] == "GAP" and "disabled" in r["gap_reason"] for r in sec)
    case = client.get(f"/api/campaigns/{rec['id']}/plan").json()["cases"][0]
    assert {"risk_id", "oracles", "expected_evidence", "lineage"} <= set(case)
    assert rec["plan"]["require_citations"] is True


def test_determinism_with_seed(servers: dict[str, Server]) -> None:
    a = run([ep("a", servers["good"])], seed=7, max_cases=20)
    b = run([ep("a", servers["good"])], seed=7, max_cases=20)
    c = run([ep("a", servers["good"])], seed=8, max_cases=20)
    pa, pb, pc = (client.get(f"/api/campaigns/{r['id']}/plan").json() for r in (a, b, c))
    assert pa["plan_id"] == pb["plan_id"] and pa["cases"] == pb["cases"]
    assert pa["plan_id"] != pc["plan_id"]
    assert a["results"]["a"]["metrics"]["overall_pass_rate"] == \
        b["results"]["a"]["metrics"]["overall_pass_rate"]


def test_plan_export_import_roundtrip_and_validation(servers: dict[str, Server]) -> None:
    first = run([ep("a", servers["good"])], max_cases=16)
    plan = client.get(f"/api/campaigns/{first['id']}/plan").json()
    second = run([ep("b", servers["bad"])], plan=json.loads(json.dumps(plan)))
    assert second["state"] == "done", second.get("error")
    assert second["plan"]["plan_id"] == plan["plan_id"]
    assert second["plan"]["source"] == "imported"
    # a company-supplied plan with its own scenario is adopted
    own = {"cases": [{"id": "own-1", "question": "How much does Zavo3 cost?",
                      "reference_answer": "103 dollars", "source": "user", "answerable": True},
                     {"id": "own-2", "question": "What is the annual revenue of Zavo3?",
                      "answerable": False, "risk": "hallucination", "source": "user"}]}
    third = run([ep("a", servers["good"])], plan=own, include_security=False)
    assert third["plan"]["n_cases"] == 2 and third["plan"]["source"] == "imported"
    got = client.get(f"/api/campaigns/{third['id']}/plan").json()
    assert got["cases"][1]["oracles"] == ["refusal"]
    assert third["results"]["a"]["sample"]["n_items"] == 2
    for bad in ({"cases": []}, {"cases": [{"id": "x"}]},
                {"cases": [{"id": "d", "question": "q"}, {"id": "d", "question": "q2"}]},
                {"cases": [{"id": "s", "question": "q", "source": "security",
                            "probe": {"oracle": "nope", "params": {}}}]}):
        r = client.post("/api/campaigns", json={
            "project_id": "p1", "name": "n", "use_example_policy": True, "plan": bad,
            "targets": [ep("a", servers["good"])]})
        assert r.status_code == 422 and "invalid plan" in r.text, bad


def test_model_target_vs_rag_uses_vault_key_and_reports_usage(
        servers: dict[str, Server]) -> None:
    chat = {"label": "bare-model", "kind": "model", "model": "fake-1",
            "base_url": servers["chat"].url + "/v1", "api_key_secret": "FAKE_LLM_KEY",
            "metadata": {"model": "fake-1"}}
    rec = run([ep("rag", servers["good"], chunking="512"), chat], include_security=False,
              max_cases=20)
    assert rec["state"] == "done", rec.get("error")
    assert set(servers["chat"].auth) == {f"Bearer {CHAT_KEY}"}
    m = rec["results"]["bare-model"]
    assert m["performance"]["tokens"]["total_tokens"] == 110 * m["performance"]["calls"]
    with store.ledger(rec["id"]) as lg:  # no retrieval happens: no contexts are invented
        calls = [e.event.payload for e in lg.entries() if e.event.key.startswith("crun:bare")]
    assert calls and all(c["contexts"] == [] and c["usage"] for c in calls)
    assert m["metrics"]["retrieval_hit_rate"]["n"] == 0
    assert rec["targets"][0]["metadata"] == {"chunking": "512"}
    assert CHAT_KEY not in json.dumps(client.get(f"/api/campaigns/{rec['id']}").json())
    assert CHAT_KEY not in json.dumps(client.get(f"/api/campaigns/{rec['id']}/events").json())


def test_signoff_events_and_ledger_integrity(servers: dict[str, Server]) -> None:
    rec = run([ep("a", servers["good"]), ep("b", servers["bad"])], max_cases=12)
    cid = rec["id"]
    url = f"/api/campaigns/{cid}/signoff"
    assert client.post(url, json={"reviewer": "dana", "decision": "approve",
                                  "target_label": "nope"}).status_code == 422
    ok = client.post(url, json={"reviewer": "dana", "decision": "reject",
                                "rationale": "n too small", "target_label": "a"})
    assert ok.status_code == 200 and ok.json()["decision"]["status"] == "rejected"
    assert client.post(url, json={"reviewer": "dana", "decision": "approve",
                                  "target_label": "a"}).status_code == 409
    got = client.get(f"/api/campaigns/{cid}").json()
    assert got["decisions"]["a"]["signoff"]["reviewer"] == "dana"
    assert got["stages"]["review"]["status"] == "awaiting_review"
    client.post(url, json={"reviewer": "dana", "decision": "approve", "target_label": "b"})
    assert client.get(f"/api/campaigns/{cid}").json()["stages"]["review"]["status"] == "done"
    ev = client.get(f"/api/campaigns/{cid}/events").json()
    assert ev["ledger_ok"] is True
    assert ev["recorded_target_calls"] == rec["plan"]["n_cases"] * 2 * 2
    actions = [e["action"] for e in ev["entries"] if e["action"]]
    assert actions.count("stage_started") == 9 and actions.count("signoff") == 2
    assert "campaign_created" in actions and "plan_created" in actions
    assert any(e["type"] == "signoff_recorded" and e["producer_kind"] == "human"
                for e in ev["entries"])
    assert not any("answer" in e["payload"] for e in ev["entries"])


def test_concurrent_campaigns_do_not_interfere(servers: dict[str, Server]) -> None:
    ids = [create([ep("a", servers["good"])], max_cases=8, include_security=False)["id"]
           for _ in range(3)]
    threads = [threading.Thread(target=manager.wait, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [manager.load(i)["state"] for i in ids] == ["done"] * 3  # type: ignore[index]
    assert len({manager.load(i)["plan"]["plan_id"] for i in ids}) == 1  # type: ignore[index]
