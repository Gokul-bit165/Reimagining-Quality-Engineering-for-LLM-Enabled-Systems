"""Campaign reports: built from a real campaign directory (plan.json + ledger + campaign.json)
created with qe.campaign's own store and execution code and two fake targets."""

from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qe.campaign import execute, manager, store
from qe.campaign.models import CampaignParams, TargetSpec
from qe.campaign.plan import build_plan
from qe.qareport.verify import verify_bundle
from qe.realeval.resolver import ResolvedProject
from qe.realeval.target import FakeRagTarget
from qe.ui.server import app
from tests.qareport.conftest import DOC, POLICY, QA

client = TestClient(app)
CID = "cmp-0000abcd"


def _make_campaign(state: str = "done") -> None:
    docs = [DOC["text"]]
    project = ResolvedProject("proj-1", "demo", FakeRagTarget(docs), [DOC], QA[:12],
                              canaries=[], authorized=True)
    params = CampaignParams(name="two systems", project_id="proj-1", repeats=2, max_cases=24,
                            seed=3, generate_with_llm=False, policy=POLICY)
    plan = build_plan(project, params, {"risks": [], "unmapped": []}, None, [], 2)
    specs = [TargetSpec(label="good", kind="endpoint", endpoint_url="http://u:pw@good.test:9000/ask?token=SECRET9"),
             TargetSpec(label="bad", kind="endpoint", endpoint_url="http://bad.test/ask")]
    rec = manager.create_record(CID, project, params, specs)
    rec.update(state=state, notes=list(plan["notes"]))
    store.save(rec)
    store.save_plan(CID, plan)
    store.audit(CID, "plan_created", plan_id=plan["plan_id"], source=plan["source"])
    targets = {"good": FakeRagTarget(docs, "perfect"), "bad": FakeRagTarget(docs, "hallucinating")}
    with store.ledger(CID) as lg:
        out = execute.run_execution(items=plan["cases"], repeats=2, targets=targets, lg=lg,
                                    cancel=threading.Event(), max_calls=10_000, timeout_s=60)
    assert out.state == "complete"


@pytest.fixture
def campaign(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    _make_campaign()
    return CID


def test_campaign_report_compares_targets_with_paired_tests(campaign: str) -> None:
    r = client.get(f"/api/campaigns/{campaign}/qa-report?format=json")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["kind"] == "campaign" and [t["name"] for t in rep["targets"]] == ["good", "bad"]
    pair = rep["comparison"]["pairs"][0]
    assert pair["shared_roots"] > 5 and pair["a_only_pass"] > pair["b_only_pass"]
    assert pair["p_value_bonferroni"] >= pair["p_value_exact"]
    good, bad = rep["targets"]
    assert good["results"]["scorecard"][0]["value"] > bad["results"]["scorecard"][0]["value"]
    assert bad["defects"] and not good["defects"] or len(bad["defects"]) > len(good["defects"])
    assert rep["comparison"]["same_item_set"] is True


def test_campaign_endpoint_hosts_are_stripped_of_credentials_and_query(campaign: str) -> None:
    rep = client.get(f"/api/campaigns/{campaign}/qa-report?format=json").json()
    assert rep["targets"][0]["scope"]["endpoint_host"] == "good.test:9000"
    assert "SECRET9" not in client.get(f"/api/campaigns/{campaign}/qa-report?format=md").text


def test_campaign_html_and_md_render_each_target(campaign: str) -> None:
    html = client.get(f"/api/campaigns/{campaign}/qa-report?format=html").text
    assert "Target: good" in html and "Target: bad" in html
    assert "Comparison between targets" in html and "NaN" not in html
    md = client.get(f"/api/campaigns/{campaign}/qa-report?format=md")
    assert md.headers["content-disposition"].endswith(f'qa-report-{campaign}.md"')


def test_campaign_bundle_verifies_and_detects_a_swapped_plan(campaign: str,
                                                             tmp_path: Path) -> None:
    r = client.get(f"/api/campaigns/{campaign}/evidence-bundle")
    assert r.status_code == 200
    good = tmp_path / "c.zip"
    good.write_bytes(r.content)
    res = verify_bundle(good)
    assert res.ok, res.problems
    with zipfile.ZipFile(good) as z:
        files = {n: z.read(n) for n in z.namelist()}
    assert "campaign_plan.json" in files and "SECRET9" not in b"".join(files.values()).decode(
        "latin-1")
    # replace the plan by a different one and fix the manifest: the anchored plan id catches it
    import hashlib
    import json
    plan = json.loads(files["campaign_plan.json"])
    plan["cases"] = plan["cases"][:-1]
    files["campaign_plan.json"] = json.dumps(plan).encode()
    manifest = json.loads(files["MANIFEST.json"])
    manifest["files"]["campaign_plan.json"]["sha256"] = hashlib.sha256(
        files["campaign_plan.json"]).hexdigest()
    files["MANIFEST.json"] = json.dumps(manifest).encode()
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    res2 = verify_bundle(bad)
    assert not res2.ok and any("anchored" in p for p in res2.problems)


def test_running_campaign_is_409(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    _make_campaign(state="running")
    assert client.get(f"/api/campaigns/{CID}/qa-report").status_code == 409
    assert client.get(f"/api/campaigns/{CID}/evidence-bundle").status_code == 409


def test_campaign_bundle_zip_is_valid(campaign: str) -> None:
    z = client.get(f"/api/campaigns/{campaign}/evidence-bundle").content
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        assert zf.testzip() is None
