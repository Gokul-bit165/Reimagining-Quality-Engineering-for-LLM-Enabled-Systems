"""Manifest schema, coverage, no-network, loopback-HTTP and LLM-client safety checks."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sandbox_apps._common.coverage_table import coverage_matrix, render  # noqa: E402
from sandbox_apps._common.http_server import make_server  # noqa: E402
from sandbox_apps._common.llm import FakeLLM, OpenAICompatibleLLM  # noqa: E402
from sandbox_apps._common.probe_utils import (  # noqa: E402
    APPS,
    DEFECT_CLASSES,
    block_network,
    build,
    load_manifest,
    load_probes,
)

REQUIRED_FIELDS = {
    "id", "class", "app", "variant", "location", "trigger", "trigger_rate_note",
    "severity", "expected_observable", "required_visibility", "held_out_family", "description",
}  # fmt: skip
PREFIX = {"chatbot": "CHAT", "rag": "RAG", "multiagent": "MA", "toolagent": "TOOL"}
RATES = {"always", "common", "rare"}
SEVERITIES = {"low", "medium", "high", "critical"}
VISIBILITIES = {"blackbox", "trace", "state"}


def _all_defects() -> list[dict[str, Any]]:
    return [d for app in APPS for d in load_manifest(app)["defects"]]


@pytest.mark.parametrize("app", APPS)
def test_manifest_schema(app: str) -> None:
    manifest = load_manifest(app)
    assert manifest["app"] == app and manifest["version"]
    assert manifest["author_note"] == "authored independently of qe/"
    seen: set[str] = set()
    for d in manifest["defects"]:
        assert REQUIRED_FIELDS <= set(d), d["id"]
        assert d["id"].startswith(PREFIX[app] + "-") and d["id"] not in seen
        seen.add(d["id"])
        assert d["app"] == app and d["variant"] == "seeded"
        assert d["class"] in DEFECT_CLASSES
        assert d["trigger_rate_note"] in RATES and d["severity"] in SEVERITIES
        assert d["required_visibility"] in VISIBILITIES
        assert isinstance(d["held_out_family"], bool)
        assert all(
            isinstance(d[k], str) and d[k].strip() for k in REQUIRED_FIELDS - {"held_out_family"}
        )


@pytest.mark.parametrize("app", APPS)
def test_each_app_has_a_held_out_family_and_probes_for_every_defect(app: str) -> None:
    defects = load_manifest(app)["defects"]
    assert any(d["held_out_family"] for d in defects)
    assert set(load_probes(app)) == {d["id"] for d in defects}


def test_all_ten_defect_classes_are_covered() -> None:
    matrix = coverage_matrix()
    for cls in DEFECT_CLASSES:
        assert any(matrix[cls][app] for app in APPS), cls
    assert {d["class"] for d in _all_defects()} == set(DEFECT_CLASSES)


def test_at_least_two_low_trigger_rate_defects_and_varied_severity() -> None:
    defects = _all_defects()
    assert sum(d["trigger_rate_note"] == "rare" for d in defects) >= 2
    assert len({d["severity"] for d in defects}) >= 3
    assert len({d["required_visibility"] for d in defects}) == 3


def test_coverage_table_renders_every_class() -> None:
    table = render()
    assert all(cls in table for cls in DEFECT_CLASSES)


def test_sandbox_sources_never_import_qe_and_stay_under_800_lines() -> None:
    for path in (ROOT / "sandbox_apps").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import qe" not in text and "from qe" not in text, path
        assert len(text.splitlines()) < 800, path


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("variant", ["clean", "seeded"])
def test_all_probes_run_offline_with_fake_llm(
    app: str, variant: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    block_network(monkeypatch)
    instance = build(app, variant)
    assert isinstance(instance.llm, FakeLLM)
    for probe in load_probes(app).values():
        for request in probe["requests"]:
            instance.invoke(request)


# -- HTTP wrapper ---------------------------------------------------------------------------
def test_http_wrapper_binds_loopback_only_and_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    with pytest.raises(ValueError):
        make_server(build("chatbot", "clean"), host="0.0.0.0")
    with pytest.raises(ValueError):
        make_server(build("chatbot", "clean"), host="")
    server = make_server(build("chatbot", "clean"), port=0)
    assert server.server_address[0] == "127.0.0.1"
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        block_network(monkeypatch, allow_loopback=True)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            assert json.loads(resp.read())["status"] == "ok"
        body = json.dumps({"input": "How do I cancel?", "want_trace": False}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/invoke", data=body, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        assert "Settings > Billing" in payload["output"] and "trace" not in payload
        bad = urllib.request.Request(f"http://127.0.0.1:{port}/invoke", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad, timeout=5)
        assert err.value.code == 400
        with pytest.raises(OSError):  # non-loopback is blocked by the test guard itself
            import socket

            socket.create_connection(("192.0.2.1", 80), timeout=1)
    finally:
        server.shutdown()
        server.server_close()


# -- real LLM client safety -------------------------------------------------------------------
def test_openai_compatible_client_is_not_created_by_apps_and_never_leaks_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    block_network(monkeypatch)
    client = OpenAICompatibleLLM("https://example.invalid/v1", "m", api_key_env="SANDBOX_TEST_KEY")
    monkeypatch.delenv("SANDBOX_TEST_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SANDBOX_TEST_KEY"):
        client.complete([{"role": "user", "content": "hi"}])
    secret = "sk-test-do-not-leak"
    monkeypatch.setenv("SANDBOX_TEST_KEY", secret)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.URLError(f"failed {secret}")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError) as err:
        client.complete([{"role": "user", "content": "hi"}])
    assert secret not in str(err.value)
    with pytest.raises(ValueError):
        OpenAICompatibleLLM("ftp://x", "m")
    for app in APPS:
        assert isinstance(build(app, "clean").llm, FakeLLM)
