"""Generic model benchmark: suite, oracles, reference models, errors as missing evidence, API."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import qe.llm.real as real_mod
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import ClaimState
from qe.llm.real import CallBudget, RealRuntime, RealSettings
from qe.modelbench.report import build_bench_report
from qe.modelbench.runner import run_benchmark
from qe.modelbench.suite import STYLES, BenchTest, build_suite, score
from qe.ui.server import app

SIMS = ["sim:faithful", "sim:hallucinator", "sim:injectable"]


def bench(tmp: Path, models: list[str], n: int = 10, repeats: int = 2, focus: str = "",
          real: RealRuntime | None = None) -> dict[str, Any]:
    run_benchmark(tmp / "b.sqlite", models, focus, n, repeats, real, pace_s=0.0)
    ledger = SQLiteLedger(tmp / "b.sqlite")
    try:
        return build_bench_report(ledger)
    finally:
        ledger.close()


def fails(rep: dict[str, Any], model: str, metric: str) -> tuple[int, int]:
    m = rep["models"][model]["metrics"][metric]
    return m["failed"], m["failed"] + m["passed"]


def test_suite_is_deterministic_covers_every_style_and_varies_with_focus() -> None:
    a, b = build_suite("", 10, 0), build_suite("", 10, 0)
    assert a == b and {t.style for t in a} == set(STYLES)
    assert {t.test_id for t in a} != {t.test_id for t in build_suite("returns refunds damaged", 10, 0)}
    assert {t.test_id for t in a} != {t.test_id for t in build_suite("", 10, 1)}
    assert all((t.canary is not None) == t.style.endswith("injection") for t in a)
    assert all(t.canary in t.question or t.canary in t.context for t in a if t.canary)


def test_each_oracle_flags_exactly_what_it_should() -> None:
    def one(style: str) -> BenchTest:
        return next(t for t in build_suite("", 10, 0) if t.style == style)

    inj = one("direct_injection")
    assert score(inj, inj.canary or "")["injection_resistance"].state is ClaimState.CONTRADICTED
    assert score(inj, "ok")["injection_resistance"].state is ClaimState.SUPPORTED
    un = one("unanswerable")
    assert score(un, "I do not know.")["abstention"].state is ClaimState.SUPPORTED
    assert score(un, "It costs 42 USD.")["abstention"].state is ClaimState.CONTRADICTED
    assert score(un, "I do not know, maybe 42 USD.")["abstention"].state is ClaimState.CONTRADICTED
    ask = one("ask")
    assert score(ask, ask.expected)["answer_accuracy"].state is ClaimState.SUPPORTED
    assert score(ask, "It is 9999.")["faithfulness"].state is ClaimState.CONTRADICTED
    assert "faithfulness" not in score(inj, "x")  # injection tests are not scored for figures


def test_reference_models_show_their_known_behaviour(tmp_path: Path) -> None:
    rep = bench(tmp_path, SIMS, n=20)
    assert all(fails(rep, "sim:faithful", m)[0] == 0 for m in rep["models"]["sim:faithful"]["metrics"])
    h_fail, h_n = fails(rep, "sim:hallucinator", "abstention")
    assert h_fail == h_n > 0
    assert fails(rep, "sim:hallucinator", "faithfulness")[0] > 0
    i_fail, i_n = fails(rep, "sim:injectable", "injection_resistance")
    assert i_fail == i_n > 0 and fails(rep, "sim:injectable", "abstention")[0] == 0
    assert rep["ledger"]["verified"]


def test_every_rate_has_an_interval_and_no_ranking_without_separation(tmp_path: Path) -> None:
    rep = bench(tmp_path, SIMS, n=5)
    for model in rep["models"].values():
        for m in model["metrics"].values():
            if m["failed"] + m["passed"]:
                assert 0 <= m["rate"]["lower"] <= m["rate"]["point"] <= m["rate"]["upper"] <= 1
    for c in rep["comparison"]:  # tiny samples: intervals overlap, so nothing may be ranked
        assert c["separable"] == []
    assert "composite" not in str(rep["comparison"]).lower()


def test_separation_is_claimed_only_when_intervals_do_not_overlap(tmp_path: Path) -> None:
    rep = bench(tmp_path, ["sim:faithful", "sim:injectable"], n=20, repeats=1)
    said = [s for c in rep["comparison"] if c["metric"] == "injection_resistance"
            for s in c["separable"]]
    cells = next(c for c in rep["comparison"] if c["metric"] == "injection_resistance")["cells"]
    separated = cells["sim:faithful"]["upper"] < cells["sim:injectable"]["lower"]
    assert bool(said) == separated


@dataclass(frozen=True)
class StubRuntime(RealRuntime):
    behaviour: str = "ok"

    def client(self, model: str, timeout: float = 90.0) -> Any:
        return RateLimited() if self.behaviour == "429" else Answers()


class RateLimited:
    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        raise RuntimeError("LLM HTTP error 429")


class Answers:
    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        return "I do not know based on the provided context."


def stub(behaviour: str) -> StubRuntime:
    return StubRuntime(RealSettings("a:free", "t:free", 10_000), CallBudget(10_000), Path("c"),
                       behaviour)


def test_rate_limited_calls_are_missing_evidence_never_failures(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(real_mod, "RETRY_DELAYS", ())
    rep = bench(tmp_path, ["vendor/model:free"], n=5, repeats=2, real=stub("429"))
    m = rep["models"]["vendor/model:free"]
    assert m["runs"]["errors"] == m["runs"]["total"] == 10
    assert "429" in m["runs"]["error_kinds"][0]
    assert all("rate" not in x and x["failed"] == 0 for x in m["metrics"].values())
    assert not m["simulated"]


def test_real_model_path_scores_answers_and_is_labelled_real(tmp_path: Path) -> None:
    rep = bench(tmp_path, ["vendor/model:free"], n=10, repeats=2, real=stub("ok"))
    m = rep["models"]["vendor/model:free"]
    assert m["runs"]["errors"] == 0 and not m["simulated"]
    assert fails(rep, "vendor/model:free", "injection_resistance")[0] == 0
    assert fails(rep, "vendor/model:free", "answer_accuracy")[0] > 0  # always abstaining is wrong


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    for var in ("QE_ALLOW_REAL_LLM", "OPENROUTER_API_KEY", "QE_LLM_SPEND_BUDGET_USD"):
        monkeypatch.delenv(var, raising=False)
    return TestClient(app)


def wait_done(client: TestClient, bid: str) -> dict[str, Any]:
    for _ in range(100):
        body = client.get(f"/api/benchmarks/{bid}").json()
        if body["status"]["state"] != "running":
            return body  # type: ignore[no-any-return]
        time.sleep(0.2)
    raise AssertionError("benchmark did not finish")


def test_api_runs_a_simulated_benchmark_and_serves_the_report(client: TestClient) -> None:
    res = client.post("/api/benchmarks", json={"models": SIMS, "n_tests": 10, "repeats": 2})
    assert res.status_code == 200
    bid = res.json()["id"]
    body = wait_done(client, bid)
    assert body["status"]["state"] == "done" and body["status"]["done"] == body["status"]["total"]
    assert set(body["report"]["models"]) == set(SIMS) and body["report"]["ledger"]["verified"]
    assert bid in [s["id"] for s in client.get("/api/benchmarks").json()]
    listing = client.get("/api/benchmarks/models").json()
    assert {m["id"] for m in listing["simulated"]} == set(SIMS)
    assert listing["real_available"] is False


@pytest.mark.parametrize("body", [
    {"models": []}, {"models": ["sim:nope"]}, {"models": ["bad id!"]},
    {"models": ["a/b:free", "a/b:free"]}, {"models": ["a/b:free"]},  # real, not opted in
    {"models": SIMS, "n_tests": 2}, {"models": SIMS, "repeats": 9},
    {"models": ["m1", "m2", "m3", "m4", "m5"]},
])
def test_api_rejects_bad_benchmark_requests(client: TestClient, body: dict[str, Any]) -> None:
    assert client.post("/api/benchmarks", json=body).status_code in (400, 422)


def test_paid_models_need_an_owner_budget(client: TestClient,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {"QE_ALLOW_REAL_LLM": "1", "OPENROUTER_API_KEY": "k", "QE_AGENT_MODEL": "a:free",
                 "QE_TARGET_MODEL": "t:free"}.items():
        monkeypatch.setenv(k, v)
    res = client.post("/api/benchmarks", json={"models": ["vendor/paid-model"]})
    assert res.status_code == 400 and "QE_LLM_SPEND_BUDGET_USD" in res.json()["detail"]


def test_benchmark_ids_are_validated_and_unknown_ones_404(client: TestClient) -> None:
    assert client.get("/api/benchmarks/..%2Fx").status_code in (400, 404)
    assert client.get("/api/benchmarks/bench-zzzzzzzz").status_code == 404
