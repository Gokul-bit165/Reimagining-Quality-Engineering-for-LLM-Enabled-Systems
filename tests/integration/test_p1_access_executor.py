"""T1.1 levels C-E are declared, never inferred; T1.2 ExecutorAPI hand-off."""

from pathlib import Path

from qe.access.blackbox_http import BlackBoxHttpTarget, negotiate
from qe.core.events import EventType
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import TestCase, VisibilityLevel
from qe.exec.executor import ExecutorAPI
from qe.exec.sandbox import LocalSandbox
from qe.ports import SandboxLimits
from tests.integration.test_m1_spine import serve

LIMITS = SandboxLimits(max_calls=100, max_tokens=10**9, egress_allowlist=("127.0.0.1",))


async def test_declared_higher_level_is_flagged_unverified() -> None:
    with serve("clean") as url:
        p = await negotiate(url, declared=VisibilityLevel.C_OTEL)
        plain = await negotiate(url)
        lower = await negotiate(url, declared=VisibilityLevel.A_BLACKBOX)
    assert p.visibility_level is VisibilityLevel.C_OTEL
    assert "declared_level_unverified" in p.capabilities
    assert "declared_level_unverified" not in plain.capabilities
    assert lower.visibility_level is VisibilityLevel.B_SDK  # observed wins over a lower claim


async def test_executor_api_runs_and_records_negotiated_profile() -> None:
    ledger = SQLiteLedger(":memory:")
    cases = [TestCase(id="c1", input={"input": "hello"}, oracle_source="deterministic:x")]
    with serve("clean") as url:
        api = ExecutorAPI(ledger, LocalSandbox(), LIMITS)
        keys = await api.run_cases(BlackBoxHttpTarget(url), cases, repeats=3, seed=1)
        again = await api.run_cases(BlackBoxHttpTarget(url), cases, repeats=3, seed=1)
    assert len(keys) == 3 and again == []  # resumable, idempotent
    runs = [e for e in ledger.entries() if e.event.type is EventType.RUN_RECORDED]
    assert [e.event.payload["repeat_index"] for e in runs] == [0, 1, 2]


def test_cli_connect_records_profile_in_ledger(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from qe.cli.main import app
    path = tmp_path / "l.sqlite"
    with serve("clean") as url:
        res = CliRunner().invoke(app, ["connect", url, "--ledger", str(path),
                                       "--declared-level", "C"])
    assert res.exit_code == 0, res.output
    inv = [e for e in SQLiteLedger(path).entries()
           if e.event.type is EventType.CAPABILITY_INVENTORY]
    assert inv[0].event.payload["visibility_level"] == "C"
