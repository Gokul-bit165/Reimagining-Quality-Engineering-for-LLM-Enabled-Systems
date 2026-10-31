import re
from pathlib import Path

import yaml
from typer.testing import CliRunner

from qe.cli.main import app
from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger, SQLiteLedger
from qe.core.schemas import ClaimState, MethodClass, Policy, Verdict
from qe.report.viewer import build_view, render_viewer

runner = CliRunner()
POLICY = Policy(policy_id="ex", version="1", loss_matrix={}, required_evidence=("citation_validity",),
                risk_appetite={"citation_validity": 0.10}, example_only=True)


def _det(key: str, etype: EventType, payload: dict[str, object]) -> Event:
    return Event(key=key, type=etype, producer="t", producer_kind=ProducerKind.DETERMINISTIC,
                 payload=payload)


def seed(ledger: Ledger, failing: int = 1, passing: int = 9) -> None:
    ledger.append(_det("cap", EventType.RUN_RECORDED, {
        "test_case_id": "x", "repeat_index": 0, "seed": 0, "visibility_level": "B",
        "request": {}, "response": {}, "spans": [], "versions": {}, "error": None}))
    for i in range(failing + passing):
        state = ClaimState.UNSUPPORTED if i < failing else ClaimState.SUPPORTED
        v = Verdict(claim_id=f"c{i}", method="m", method_class=MethodClass.DETERMINISTIC,
                    method_version="1", state=state)
        ledger.append(_det(f"v{i}", EventType.VERDICT_ISSUED,
                           {"metric": "citation_validity", "case_id": f"case{i}",
                            "verdict": v.model_dump(mode="json")}))


def test_core_sections_and_not_run_markers_when_optional_events_absent() -> None:
    ledger = SQLiteLedger(":memory:")
    seed(ledger)
    html = render_viewer(ledger, POLICY)
    for needle in ("Decision", "Access level", "Coverage", "Effective independent verifiers",
                   "Invalid-test rate", "ASR@budget", "Claims not made", "citation_validity"):
        assert needle in html
    assert html.count('class="notrun"') == 4  # coverage, n_eff, invalid, asr
    assert "EXAMPLE" in html
    assert re.search(r"0\.\d{3,4}.{0,40}0\.\d{3,4}", html)  # point and interval printed


def test_output_is_self_contained_deterministic_and_has_no_external_refs() -> None:
    ledger = SQLiteLedger(":memory:")
    seed(ledger)
    a, b = render_viewer(ledger, POLICY), render_viewer(ledger, POLICY)
    assert a == b
    assert not re.search(r"(?:src|href)\s*=\s*[\"']?(?:https?:)?//", a)
    assert "<link" not in a and "@import" not in a and "url(" not in a
    assert "prefers-reduced-motion" in a and 'name="viewport"' in a
    assert "Content-Security-Policy" in a


def test_untrusted_ledger_strings_are_escaped() -> None:
    ledger = SQLiteLedger(":memory:")
    seed(ledger)
    evil = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    ledger.append(_det("v-evil", EventType.VERDICT_ISSUED, {
        "metric": evil, "case_id": "e", "verdict": Verdict(
            claim_id="e", method="m", method_class=MethodClass.DETERMINISTIC, method_version="1",
            state=ClaimState.UNSUPPORTED).model_dump(mode="json")}))
    html = render_viewer(ledger, POLICY)
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(1)" in html


def test_optional_sections_render_from_events_with_intervals() -> None:
    ledger = SQLiteLedger(":memory:")
    seed(ledger)
    ledger.append(_det("cov", EventType.EVIDENCE_RECORDED, {"kind": "coverage_report", "cells": [
        {"cell": "rag/citation", "covered": True, "n_tests": 12},
        {"cell": "tool/exfil", "covered": False, "n_tests": 0}]}))
    ledger.append(_det("neff", EventType.ESTIMATE_COMPUTED, {"metric": "n_eff", "value": 1.8, "n": 3}))
    ledger.append(_det("inv", EventType.ESTIMATE_COMPUTED, {
        "metric": "invalid_test_rate", "k": 2, "n": 40, "point": 0.05, "lower": 0.006, "upper": 0.169}))
    ledger.append(_det("asr", EventType.ESTIMATE_COMPUTED, {
        "metric": "asr_at_budget", "k": 3, "n": 20, "budget": 50, "attacker_class": "adaptive"}))
    view = build_view(ledger, POLICY)
    assert view["coverage"]["uncovered"] == ["tool/exfil"]
    assert view["n_eff"]["value"] == 1.8
    assert view["invalid_test_rate"]["upper"] == 0.169
    asr = view["asr_at_budget"]
    assert asr["attacker_class"] == "adaptive" and 0.0 < asr["lower"] < asr["point"] < asr["upper"] < 1.0
    html = render_viewer(ledger, POLICY)
    assert 'class="notrun"' not in html
    assert "tool/exfil" in html and "adaptive" in html and "budget 50" in html


def test_rate_without_interval_or_counts_is_not_shown_as_bare_point() -> None:
    ledger = SQLiteLedger(":memory:")
    seed(ledger)
    ledger.append(_det("inv", EventType.ESTIMATE_COMPUTED, {"metric": "invalid_test_rate", "point": 0.1}))
    html = render_viewer(ledger, POLICY)
    assert "interval unavailable" in html
    assert "0.1000" not in html.split("Invalid-test rate")[1].split("</section>")[0]


def test_cli_view_writes_file_and_validates_inputs(tmp_path: Path) -> None:
    path = tmp_path / "l.sqlite"
    ledger = SQLiteLedger(path)
    seed(ledger)
    ledger.close()
    pol = tmp_path / "p.yaml"
    pol.write_text(yaml.safe_dump(POLICY.model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "r.html"
    res = runner.invoke(app, ["view", str(path), str(pol), "--out", str(out)])
    assert res.exit_code == 0 and out.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert runner.invoke(app, ["view", str(tmp_path / "no"), str(pol), "--out", str(out)]).exit_code == 2
