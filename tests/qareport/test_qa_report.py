"""Report content: every figure traces to the ledger; golden Markdown; no model text."""

from __future__ import annotations

import json
import os
from pathlib import Path

from qe.core.ledger import SQLiteLedger
from qe.qareport import rubric as rubric_mod
from qe.qareport.build import build_report
from qe.qareport.render_md import render_markdown
from qe.qareport.stats_util import percentile
from qe.realeval.runner import replay
from tests.qareport.conftest import FaultyTarget, Fixture, make_fixture

GOLDEN = Path(__file__).parent / "golden" / "report.md"


def test_markdown_matches_golden_file(fx: Fixture) -> None:
    md = render_markdown(build_report(fx.inp))
    if os.environ.get("QE_UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(md, encoding="utf-8", newline="\n")
    assert md == GOLDEN.read_text(encoding="utf-8")


def test_report_has_every_required_section(fx: Fixture) -> None:
    md = render_markdown(build_report(fx.inp))
    for heading in ("1. Executive summary", "2. Scope and target", "3. Methodology",
                    "4. Test coverage", "5. Results", "6. Defect register",
                    "7. Security findings", "8. Grounding findings", "9. Regression status",
                    "10. Recommendation and reasoning", "11. Human review and sign-off",
                    "12. Monitoring plan", "13. Limitations and threats to validity",
                    "14. Appendix"):
        assert f"## {heading}" in md


def test_scorecard_and_decision_equal_ledger_replay(fx: Fixture) -> None:
    report = build_report(fx.inp)
    replayed = replay(fx.ledger)
    t = report["targets"][0]
    for row in t["results"]["scorecard"]:
        m = replayed["scorecard"][row["dimension"]]
        assert (row["value"], row["ci_low"], row["ci_high"], row["n_roots"]) == (
            m["value"], m["ci_low"], m["ci_high"], m["n_roots"])
    assert t["recommendation"]["verdict"] == replayed["decision"]["verdict"]
    assert t["recommendation"]["reasons"] == replayed["decision"]["reasons"]


def test_latency_percentiles_agree_with_scorecard_metrics(fx: Fixture) -> None:
    t = build_report(fx.inp)["targets"][0]
    metrics = {m["metric"]: m for m in t["results"]["metrics"]}
    assert t["results"]["latency_s"]["p50"] == metrics["latency_p50_s"]["value"]
    assert t["results"]["latency_s"]["p95"] == metrics["latency_p95_s"]["value"]
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0


def test_every_defect_traces_to_real_ledger_entries(fx: Fixture) -> None:
    report = build_report(fx.inp)
    defects = report["targets"][0]["defects"]
    assert defects
    ledger = SQLiteLedger(fx.ledger)
    try:
        by_key = {e.event.key: e for e in ledger.entries()}
    finally:
        ledger.close()
    for d in defects:
        assert d["id"].startswith("DEF-") and d["severity"] and d["guidance"]
        for m in d["members"]:
            run = m["ledger"]["run"]
            assert run is not None
            assert by_key[run["key"]].hash == run["hash"] and by_key[run["key"]].seq == run["seq"]
            # the exact response in the report is the response recorded in that ledger event
            payload = by_key[run["key"]].event.payload
            assert m["response"] == payload["answer"] and m["request"]
            assert m["expected"] and m["actual"] and m["oracle"]["type"]


def test_duplicates_are_clustered_by_root(fx: Fixture) -> None:
    defects = build_report(fx.inp)["targets"][0]["defects"]
    assert any(d["duplicates"] >= 1 for d in defects)  # a paraphrase folded under its root
    ids = [d["id"] for d in defects]
    assert len(ids) == len(set(ids))


def test_security_section_reports_asr_with_interval_and_canary_evidence(fx: Fixture) -> None:
    sec = build_report(fx.inp)["targets"][0]["security"]
    assert sec["ran"] and sec["overall"]["k"] > 0
    assert sec["overall"]["ci_low"] <= sec["overall"]["value"] <= sec["overall"]["ci_high"]
    kinds = {k["kind"]: k for k in sec["by_kind"]}
    assert {"prompt_injection", "canary_exfiltration"} <= set(kinds)
    canary = [p for p in sec["probes"] if p["kind"] == "canary_exfiltration"]
    assert canary and canary[0]["oracle"]["fired"] and "CANARY-ABC123" in canary[0]["response"]


def test_grounding_findings_list_unsupported_claims_with_context(fx: Fixture) -> None:
    g = build_report(fx.inp)["targets"][0]["grounding"]
    assert g["unsupported"]
    u = g["unsupported"][0]
    assert u["unsupported_claims"] and u["cited_contexts"] and u["ledger"]["run"]


def test_severity_labels_never_feed_the_verdict(fx: Fixture, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    before = build_report(fx.inp)["targets"][0]["recommendation"]
    data = dict(rubric_mod.rubric())
    flipped = {**data, "classes": {k: {**v, "severity": "low"} for k, v in
                                   data["classes"].items()}, "default": data["default"]}
    monkeypatch.setattr(rubric_mod, "rubric", lambda: flipped)
    after_report = build_report(fx.inp)
    assert {d["severity"] for d in after_report["targets"][0]["defects"]} == {"low"}
    assert after_report["targets"][0]["recommendation"] == before


def test_pending_status_without_signoff_and_warning_banner(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path, signoff=False)
    t = build_report(fixture.inp)["targets"][0]
    assert t["review"]["status"] == "pending_review" and t["review"]["note"]
    assert t["recommendation"]["status"] == "pending_review"


def test_signoff_record_is_taken_from_the_ledger(fx: Fixture) -> None:
    review = build_report(fx.inp)["targets"][0]["review"]
    assert review["status"] == "approved"
    assert review["signoffs"][0]["approver"] == "Dana QA"
    assert review["decision_matches_signoff"] is True


def test_example_policy_is_flagged_loudly(fx: Fixture) -> None:
    ev = fx.inp.targets[0].model_copy(update={"config": {**fx.inp.targets[0].config,
                                                         "policy": None}})
    inp = fx.inp.model_copy(update={"targets": [ev]})
    md = render_markdown(build_report(inp))
    assert "EXAMPLE POLICY IN USE" in md and "(EXAMPLE)" in md


def test_gaps_are_listed_not_hidden(fx: Fixture) -> None:
    t = build_report(fx.inp)["targets"][0]
    gap_text = " ".join(t["coverage"]["gaps"])
    assert "QE-CIT" in gap_text  # no citation metric measurable in this run
    assert t["not_assessed"]


def test_tampered_ledger_is_flagged_in_the_report(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    ev = fixture.inp.targets[0].model_copy(update={"chain_ok": False,
                                                   "chain_reason": "entry hash mismatch"})
    md = render_markdown(build_report(fixture.inp.model_copy(update={"targets": [ev]})))
    assert "LEDGER INTEGRITY CHECK FAILED" in md


def test_report_json_is_deterministic(fx: Fixture) -> None:
    a = json.dumps(build_report(fx.inp), sort_keys=True)
    b = json.dumps(build_report(fx.inp), sort_keys=True)
    assert a == b


def test_faulty_target_fixture_is_what_the_report_says() -> None:
    assert FaultyTarget().ask("How much does Zavo1 cost?").answer.startswith("Zavo1 costs")
