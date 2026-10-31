import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from qe.access.blackbox_http import BlackBoxHttpTarget, negotiate
from qe.core.events import EventType
from qe.core.ids import content_id
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import DecisionState, Policy, TestCase, Verdict, VisibilityLevel
from qe.exec.executor import execute
from qe.exec.sandbox import LocalSandbox
from qe.ports import SandboxLimits
from qe.report.evidence_pack import build_pack, render_json, render_markdown
from qe.verify.deterministic import citation_exists
from qe.verify.runner import verify_runs
from sandbox_apps._common.http_server import make_server
from sandbox_apps.rag import build_app
from sandbox_apps.rag.corpus import official_docs

ROOT = Path(__file__).resolve().parents[2]
CORPUS = {k: v["text"] for k, v in official_docs().items()}
POLICY = Policy(policy_id="example", version="1", loss_matrix={},
                required_evidence=("citation_validity",),
                risk_appetite={"citation_validity": 0.10}, example_only=True)


@contextmanager
def serve(variant: str) -> Iterator[str]:
    server = make_server(build_app(variant), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def cases() -> list[TestCase]:
    probes = yaml.safe_load((ROOT / "sandbox_apps/rag/probes.yaml").read_text(encoding="utf-8"))
    out = []
    for pid, spec in sorted(probes.items()):
        for i, req in enumerate(spec["requests"]):
            out.append(TestCase(id=content_id([pid, i, req]), input=req,
                                oracle_source="deterministic:citation_exists"))
    return out


def citation_check(run: dict[str, Any]) -> Verdict | None:
    return citation_exists(run["test_case_id"], run["response"]["citations"], CORPUS)


CHECKS = [("citation_validity", citation_check)]
LIMITS = SandboxLimits(max_calls=1000, max_tokens=10**9, egress_allowlist=("127.0.0.1",))


async def run_variant(variant: str, ledger: SQLiteLedger, repeats: int = 2) -> None:
    with serve(variant) as url:
        target = BlackBoxHttpTarget(url, (await negotiate(url)).visibility_level)
        async with LocalSandbox().session(LIMITS) as session:
            await execute(ledger, target, cases(), repeats=repeats, seed=7, session=session)
    verify_runs(ledger, CHECKS)


async def test_negotiation_records_observed_level() -> None:
    with serve("clean") as url:
        profile = await negotiate(url)
    assert profile.visibility_level is VisibilityLevel.B_SDK  # app returns trace on request
    assert "trace_in_response" in profile.capabilities


async def test_seeded_invalid_citations_detected_clean_not() -> None:
    clean, seeded = SQLiteLedger(":memory:"), SQLiteLedger(":memory:")
    await run_variant("clean", clean)
    await run_variant("seeded", seeded)
    def failed(p: dict[str, Any]) -> int:
        return int(next(m["failed_cases"] for m in p["metrics"] if m["metric"] == "citation_validity"))
    assert failed(build_pack(clean, POLICY)) == 0
    assert failed(build_pack(seeded, POLICY)) >= 1  # RAG-002 legacy ids are not in the corpus


async def test_resume_does_not_duplicate_runs() -> None:
    ledger = SQLiteLedger(":memory:")
    await run_variant("clean", ledger, repeats=2)
    n = len(ledger)
    await run_variant("clean", ledger, repeats=2)
    assert len(ledger) == n


async def test_budget_exhaustion_logs_missing_evidence_not_silent_skip() -> None:
    ledger = SQLiteLedger(":memory:")
    tight = SandboxLimits(max_calls=3, max_tokens=10**9, egress_allowlist=("127.0.0.1",))
    with serve("clean") as url:
        async with LocalSandbox().session(tight) as session:
            done = await execute(ledger, BlackBoxHttpTarget(url), cases(), repeats=1, seed=0,
                                 session=session)
    assert len(done) == 3
    miss = [e for e in ledger.entries() if e.event.type is EventType.MISSING_EVIDENCE]
    assert len(miss) == 1 and len(miss[0].event.payload["unrun"]) == len(cases()) - 3
    assert build_pack(ledger, POLICY)["runs"]["unrun_budget_or_kill"]


async def test_kill_switch_stops_run() -> None:
    ledger = SQLiteLedger(":memory:")
    calls = {"n": 0}
    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] > 2
    with serve("clean") as url:
        async with LocalSandbox().session(LIMITS) as session:
            done = await execute(ledger, BlackBoxHttpTarget(url), cases(), repeats=1, seed=0,
                                 session=session, should_stop=stop)
    assert len(done) == 2
    assert any(e.event.type is EventType.MISSING_EVIDENCE for e in ledger.entries())


async def test_replay_is_byte_identical_and_missing_evidence_blocks_release(tmp_path: Path) -> None:
    path = tmp_path / "l.sqlite"
    ledger = SQLiteLedger(path)
    await run_variant("clean", ledger)
    first = build_pack(ledger, POLICY)
    ledger.close()
    copy = tmp_path / "copy.sqlite"
    shutil.copy(path, copy)
    replay = build_pack(SQLiteLedger(copy), POLICY)
    assert render_json(first) == render_json(replay)
    assert render_markdown(first) == render_markdown(replay)
    # 0 failures in the small probe set cannot establish a 10% appetite -> not RELEASE
    assert first["decision"]["decision"] == DecisionState.INSUFFICIENT_EVIDENCE.value
    assert "EXAMPLE" in render_markdown(first)
