import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from qe.core.telemetry import REQUIRED_FLAGS, enforce_telemetry_off, telemetry_violations
from qe.exec.egress import EgressBlockedError, EgressGuard
from qe.exec.sandbox import LocalSandbox
from qe.ports import BudgetExceededError, KillSwitchError, SandboxLimits


def test_all_dependency_telemetry_flags_are_off_after_importing_qe() -> None:
    assert telemetry_violations() == []


def test_importing_qe_overrides_hostile_environment(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in REQUIRED_FLAGS}
    env["DEEPEVAL_TELEMETRY_OPT_OUT"] = "0"  # hostile value
    code = (
        "import qe, os; from qe.core.telemetry import telemetry_violations;"
        "print(telemetry_violations())"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         check=True, cwd=tmp_path)
    assert out.stdout.strip() == "[]"


def test_violation_detector_catches_a_flipped_flag() -> None:
    env = dict(os.environ)
    enforce_telemetry_off(env)
    env["RAGAS_DO_NOT_TRACK"] = "false"
    assert telemetry_violations(env) == ["RAGAS_DO_NOT_TRACK"]


def test_egress_guard_blocks_and_records_external_connect() -> None:
    with EgressGuard(allowlist=()) as guard:
        with pytest.raises(EgressBlockedError):
            socket.create_connection(("93.184.216.34", 80), timeout=1)
        with pytest.raises(EgressBlockedError):
            socket.getaddrinfo("example.com", 80)
    assert any("93.184.216.34" in a for a in guard.attempts)
    assert any("example.com" in a for a in guard.attempts)


def test_egress_guard_allows_only_allowlisted_loopback() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    try:
        with EgressGuard(allowlist=()):
            with pytest.raises(EgressBlockedError):
                socket.create_connection(("127.0.0.1", port), timeout=1)
        with EgressGuard(allowlist=("127.0.0.1",)):
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
    finally:
        listener.close()


def test_egress_guard_restores_socket_functions() -> None:
    before = (socket.socket.connect, socket.getaddrinfo)
    with EgressGuard(allowlist=()):
        pass
    assert (socket.socket.connect, socket.getaddrinfo) == before


async def test_local_sandbox_blocks_egress_enforces_budget_and_kill_switch() -> None:
    async with LocalSandbox().session(SandboxLimits(max_calls=1, max_tokens=10)) as s:
        with pytest.raises(EgressBlockedError):
            socket.create_connection(("1.1.1.1", 443), timeout=1)
        assert any("1.1.1.1" in a for a in s.egress_attempts())
        s.charge()
        with pytest.raises(BudgetExceededError):
            s.charge()
        s.kill()
        with pytest.raises(KillSwitchError):
            s.charge()
