"""Real-model plumbing, tested with stubs only: no network, no key, no spend."""

import asyncio
import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from qe.core.dotenv import load_dotenv
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.demo.pipeline import run_scenario_variant
from qe.demo.scenario_report import build_report
from qe.demo.sim_llm import SimulatedCrewLLM
from qe.exec.egress import EgressBlockedError, EgressGuard, exempt_hosts
from qe.llm.real import (
    CallBudget,
    RealCrewLLM,
    RealLLMNotAllowedError,
    RealRuntime,
    RealSettings,
    clean_json_text,
    real_settings_from_env,
)
from sandbox_apps._common.llm import FakeLLM

FREE = {"QE_ALLOW_REAL_LLM": "1", "OPENROUTER_API_KEY": "k", "QE_AGENT_MODEL": "a:free",
        "QE_TARGET_MODEL": "t:free"}


def test_dotenv_reads_only_allow_listed_names_and_never_overrides(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("# c\nOPENROUTER_API_KEY=abc\nEVIL=1\nQE_AGENT_MODEL='m:free'\nQE_TARGET_MODEL=\n",
                 encoding="utf-8")
    env: dict[str, str] = {"QE_AGENT_MODEL": "keep"}
    assert load_dotenv(f, env) == ["OPENROUTER_API_KEY"]
    assert env == {"QE_AGENT_MODEL": "keep", "OPENROUTER_API_KEY": "abc"}
    assert load_dotenv(tmp_path / "missing", env) == []


@pytest.mark.parametrize("drop", ["QE_ALLOW_REAL_LLM", "OPENROUTER_API_KEY", "QE_AGENT_MODEL",
                                  "QE_TARGET_MODEL"])
def test_real_mode_requires_opt_in_key_and_both_models(drop: str) -> None:
    with pytest.raises(RealLLMNotAllowedError):
        real_settings_from_env({k: v for k, v in FREE.items() if k != drop})


def test_free_models_need_no_budget_but_paid_models_do() -> None:
    assert real_settings_from_env(FREE).max_calls == 120
    paid = {**FREE, "QE_TARGET_MODEL": "t/paid"}
    with pytest.raises(RealLLMNotAllowedError):
        real_settings_from_env(paid)
    assert real_settings_from_env({**paid, "QE_LLM_SPEND_BUDGET_USD": "1"}).target_model == "t/paid"
    with pytest.raises(RealLLMNotAllowedError):
        real_settings_from_env({**paid, "QE_LLM_SPEND_BUDGET_USD": "0"})


def test_clean_json_text_strips_reasoning_and_prose() -> None:
    raw = '<think>x [1] y</think>Sure! Here you go: [{"a": "b]c"}, {"d": [1, 2]}] Thanks.'
    assert json.loads(clean_json_text(raw)) == [{"a": "b]c"}, {"d": [1, 2]}]
    assert clean_json_text("no json here") == "no json here"


class StubClient:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        self.calls += 1
        return "<think>hmm</think>[]"


def test_crew_llm_caches_replays_offline_and_enforces_the_call_cap(tmp_path: Path) -> None:
    client, cache = StubClient(), tmp_path / "c.jsonl"
    llm = RealCrewLLM(client, "m:free", "fam", CallBudget(2), cache)
    assert asyncio.run(llm.complete("s", "u1")) == "[]"
    assert asyncio.run(llm.complete("s", "u1")) == "[]" and client.calls == 1  # cache hit
    asyncio.run(llm.complete("s", "u2"))
    with pytest.raises(RealLLMNotAllowedError):
        asyncio.run(llm.complete("s", "u3"))
    assert llm.model.provider == "openrouter"


def test_exempt_host_opens_only_that_host_and_only_while_active() -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(2)
    port = srv.getsockname()[1]
    try:
        with EgressGuard(allowlist=()):
            with pytest.raises(EgressBlockedError):
                socket.create_connection(("127.0.0.1", port), timeout=1)
            with exempt_hosts("127.0.0.1"):
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                with pytest.raises(EgressBlockedError):
                    socket.create_connection(("93.184.216.34", 80), timeout=1)
            with pytest.raises(EgressBlockedError):
                socket.create_connection(("127.0.0.1", port), timeout=1)
    finally:
        srv.close()


@dataclass(frozen=True)
class StubRuntime(RealRuntime):
    """A RealRuntime whose 'models' are local stubs: crew replies come from the simulator."""

    def client(self, model: str, timeout: float = 90.0) -> Any:
        return StubModel() if model == self.settings.agent_model else FakeLLM(seed=0)


class StubModel:
    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        system, user = messages[0]["content"], messages[1]["content"]
        sim = SimulatedCrewLLM("stub")
        return asyncio.run(sim.complete(system, user))


def test_real_mode_pipeline_wiring_labels_budget_and_honest_skips(tmp_path: Path) -> None:
    rt = StubRuntime(RealSettings("agent:free", "target:free", 500), CallBudget(500),
                     tmp_path / "cache.jsonl")
    asyncio.run(run_scenario_variant(
        tmp_path, "real-rag-seeded", "rag", "seeded", "LLM09",
        "Customers get invented policy facts", None, 6, rt))
    ledger = SQLiteLedger(tmp_path / "real-rag-seeded.sqlite")
    policy = Policy.model_validate_json((tmp_path / "real-rag-seeded.policy.json").read_text("utf-8"))
    rep = build_report(ledger, policy)
    assert rep["labels"]["mode"] == "real" and "agent:free" in rep["labels"]["generation"]
    assert "target:free" in rep["labels"]["target"]
    assert rep["scenario"]["repeats"] == 2 and rt.budget.used > 0
    assert rep["regression"]["admitted"] == []
    assert "skipped" in rep["scenario"]["regression"]
    providers = {e.event.payload["model"]["provider"] for e in ledger.entries()
                 if "model" in e.event.payload}
    assert providers == {"openrouter", "simulated"}  # one real author + one simulated author
    assert rep["generation"]["tests"] and ledger.verify().ok
