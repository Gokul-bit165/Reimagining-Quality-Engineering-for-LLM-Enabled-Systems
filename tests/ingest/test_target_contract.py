"""Item 8: configurable target contract (request template, response paths, SSE, text), vault-
referenced header secrets, scrubbed/truncated errors, and the test-connection endpoint. All against
local http.server fixtures; SSRF protections stay in force."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.ingest import store
from qe.ingest.models import Project
from qe.ingest.target import SandboxedRepoTarget
from qe.ingest.target_config import TargetConfig, extract_paths
from qe.ingest.vault import VAULT
from qe.ui.server import app

client = TestClient(app)
Reply = tuple[int, str, bytes]
PID = "prj-a0b1c2d3e4"


class Fixture:
    def __init__(self, reply: Callable[[dict[str, Any], dict[str, str]], Reply]) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n).decode()
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = {"_raw": raw}
                headers = {k.lower(): v for k, v in self.headers.items()}
                outer.requests.append({"body": body, "headers": headers, "path": self.path})
                self._send(*reply(body, headers))

            def do_GET(self) -> None:  # noqa: N802
                headers = {k.lower(): v for k, v in self.headers.items()}
                outer.requests.append({"body": None, "headers": headers, "path": self.path})
                self._send(*reply({}, headers))

            def _send(self, status: int, ctype: str, data: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a: Any) -> None:
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/chat"

    def close(self) -> None:
        self.srv.shutdown()


@pytest.fixture
def serve() -> Iterator[Callable[..., Fixture]]:
    made: list[Fixture] = []

    def make(reply: Callable[[dict[str, Any], dict[str, str]], Reply]) -> Fixture:
        fx = Fixture(reply)
        made.append(fx)
        return fx

    yield make
    for fx in made:
        fx.close()
    VAULT.clear(PID)


def js(obj: Any) -> Reply:
    return 200, "application/json", json.dumps(obj).encode()


def ask(fx: Fixture, cfg: TargetConfig | None, q: str = "What is the refund window?",
        secrets: dict[str, str] | None = None) -> Any:
    return SandboxedRepoTarget("endpoint", endpoint_url=fx.url, target_config=cfg,
                               secrets=secrets).ask(q)


# ---- path syntax
def test_extract_paths() -> None:
    data = {"data": {"answer": "a", "sources": [{"text": "x"}, {"text": "y"}]},
            "choices": [{"message": {"content": "hi"}}], "m": {"k": {"a": "1", "b": "2"}}}
    assert extract_paths(data, "data.answer") == ["a"]
    assert extract_paths(data, "$.choices[0].message.content") == ["hi"]
    assert extract_paths(data, "choices.0.message.content") == ["hi"]
    assert extract_paths(data, "data.sources.*.text") == ["x", "y"]
    assert extract_paths(data, "m.k.*") == ["1", "2"]
    assert extract_paths(data, "data.nope") == []
    assert extract_paths(data, "data.sources.9.text") == []


# ---- the five response shapes
def test_openai_style_with_vault_header_and_template(serve: Any) -> None:
    fx = serve(lambda b, h: js({"choices": [{"message": {"content": "30 days."}}]}))
    cfg = TargetConfig(
        request_template={"model": "m", "messages": [{"role": "user", "content": "{question}"}]},
        answer_path="choices.0.message.content",
        headers={"Authorization": "Bearer ${SERVICE_TOKEN}"})
    out = ask(fx, cfg, secrets={"SERVICE_TOKEN": "tok-12345678"})
    assert out.error is None and out.answer == "30 days." and out.contexts == []
    sent = fx.requests[0]
    assert sent["body"]["messages"][0]["content"] == "What is the refund window?"
    assert sent["body"]["model"] == "m"
    assert sent["headers"]["authorization"] == "Bearer tok-12345678"


def test_data_answer_and_nested_context_paths(serve: Any) -> None:
    fx = serve(lambda b, h: js({"data": {"answer": "7 days", "sources": [
        {"text": "Refunds within 7 days."}, {"text": "Contact support."}]}}))
    cfg = TargetConfig(request_template={"q": "{question}"}, answer_path="data.answer",
                       context_paths=["data.sources.*.text"])
    out = ask(fx, cfg)
    assert out.answer == "7 days"
    assert out.contexts == ["Refunds within 7 days.", "Contact support."]


def test_reply_and_docs_list_of_strings(serve: Any) -> None:
    fx = serve(lambda b, h: js({"reply": "Yes.", "docs": ["doc-1", "doc-2"]}))
    out = ask(fx, TargetConfig(request_template={"msg": "{question}"}, answer_path="reply",
                               context_paths=["docs"]))
    assert out.answer == "Yes." and out.contexts == ["doc-1", "doc-2"]


def test_sse_stream_deltas_are_concatenated(serve: Any) -> None:
    events = [{"choices": [{"delta": {"content": "Refunds "}}]},
              {"choices": [{"delta": {"content": "take 7 days."}}]}]
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    fx = serve(lambda b, h: (200, "text/event-stream", body.encode()))
    out = ask(fx, TargetConfig(request_template={"q": "{question}"}))
    assert out.error is None and out.answer == "Refunds take 7 days."


def test_sse_with_custom_path_and_contexts(serve: Any) -> None:
    body = ('data: {"tok": "A"}\n\ndata: {"tok": "B", "src": ["s1"]}\n\n'
            'data: {"tok": "C", "src": ["s1", "s2"]}\n\n')
    fx = serve(lambda b, h: (200, "text/event-stream", body.encode()))
    out = ask(fx, TargetConfig(request_template={"q": "{question}"}, answer_path="tok",
                               context_paths=["src.*"]))
    assert out.answer == "ABC" and out.contexts == ["s1", "s2"]


def test_plain_text_response(serve: Any) -> None:
    fx = serve(lambda b, h: (200, "text/plain", b"Thirty days, per the policy."))
    out = ask(fx, None)
    assert out.error is None and out.answer == "Thirty days, per the policy."


def test_default_request_tries_question_query_input(serve: Any) -> None:
    fx = serve(lambda b, h: js({"answer": "ok", "contexts": ["c"]}))
    out = ask(fx, None, "Hello?")
    assert out.answer == "ok" and out.contexts == ["c"]
    assert fx.requests[0]["body"] == {"question": "Hello?", "query": "Hello?", "input": "Hello?"}


def test_get_method_sends_template_as_query(serve: Any) -> None:
    fx = serve(lambda b, h: js({"answer": "ok"}))
    out = ask(fx, TargetConfig(method="GET", request_template={"q": "{question}"}), "a b&c")
    assert out.answer == "ok"
    assert fx.requests[0]["path"].startswith("/chat?q=a+b%26c")


# ---- failures are precise, truncated and scrubbed
def test_unresolved_path_error_is_clear_truncated_and_scrubbed(serve: Any) -> None:
    secret = "tok-12345678"
    fx = serve(lambda b, h: js({"unexpected": "x" * 2000, "echo": secret}))
    out = ask(fx, TargetConfig(request_template={"q": "{question}"}, answer_path="data.answer",
                               headers={"X-Api-Key": "${SERVICE_TOKEN}"}),
              secrets={"SERVICE_TOKEN": secret})
    assert out.answer == "" and out.error
    assert "answer_path" in out.error and "data.answer" in out.error
    assert "unexpected" in out.error  # the keys actually present are named
    assert secret not in out.error and len(out.error) < 900


def test_missing_vault_secret_is_a_clear_error(serve: Any) -> None:
    fx = serve(lambda b, h: js({"answer": "x"}))
    out = ask(fx, TargetConfig(headers={"Authorization": "Bearer ${SERVICE_TOKEN}"}))
    assert out.error and "SERVICE_TOKEN" in out.error and "vault" in out.error.lower()


def test_http_error_body_is_scrubbed(serve: Any) -> None:
    fx = serve(lambda b, h: (401, "text/plain", b"bad key sk-abcdefghijklmnop1234"))
    out = ask(fx, None)
    assert out.error and "401" in out.error and "sk-abcdefghijklmnop1234" not in out.error


def test_json_without_any_answer_is_an_error_not_an_empty_pass(serve: Any) -> None:
    fx = serve(lambda b, h: js({"status": "ok"}))
    out = ask(fx, None)
    assert out.error and "no answer" in out.error.lower()


def test_ssrf_protection_still_applies() -> None:
    out = SandboxedRepoTarget("endpoint", endpoint_url="http://169.254.169.254/latest",
                              target_config=TargetConfig()).ask("q")
    assert out.error and out.answer == ""


# ---- config validation
@pytest.mark.parametrize("bad", [
    {"request_template": {"q": "no placeholder"}},
    {"headers": {"Authorization": "Bearer literal-secret-value"}},
    {"headers": {"Host": "${X_Y}"}},
    {"headers": {"Content-Length": "${X_Y}"}},
    {"headers": {"Bad Name": "${X_Y}"}},
    {"headers": {"X-A": "line\r\nbreak ${X_Y}"}},
    {"answer_path": "a b; rm"},
    {"answer_path": "x" * 300},
    {"method": "DELETE"},
    {"context_paths": ["a"] * 11},
])
def test_config_validation_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TargetConfig.model_validate(bad)


def test_benign_literal_headers_are_allowed() -> None:
    TargetConfig(headers={"Accept": "application/json", "X-Api-Key": "${MY_KEY}"})


# ---- endpoints
@pytest.fixture
def project(serve: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
            ) -> Iterator[tuple[str, Callable[..., Fixture]]]:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    store.save(Project(id=PID, repo_url="https://github.com/a/b", created_at=1.0, state="ready",
                       authorized=True))
    yield PID, serve
    store.delete(PID)


def test_target_config_and_test_connection_endpoints(project: Any) -> None:
    pid, serve = project
    fx = serve(lambda b, h: js({"data": {"answer": "7 days", "sources": [{"text": "Refunds are accepted within seven days."}]}}))
    assert client.post(f"/api/projects/{pid}/inputs",
                       json={"endpoint_url": fx.url}).status_code == 200
    bad = client.post(f"/api/projects/{pid}/target-config",
                      json={"headers": {"Authorization": "Bearer abc"}})
    assert bad.status_code == 422
    cfg = {"request_template": {"q": "{question}"}, "answer_path": "data.answer",
           "context_paths": ["data.sources.*.text"],
           "headers": {"Authorization": "Bearer ${SERVICE_TOKEN}"}}
    ok = client.post(f"/api/projects/{pid}/target-config", json=cfg)
    assert ok.status_code == 200 and ok.json()["answer_path"] == "data.answer"
    assert client.get(f"/api/projects/{pid}").json()["target_config"]["answer_path"] \
        == "data.answer"
    assert client.post(f"/api/projects/{pid}/secrets",
                       json={"values": {"SERVICE_TOKEN": "tok-12345678"}}).status_code == 200
    res = client.post(f"/api/projects/{pid}/target-test", json={"question": "refund window?"})
    body = res.json()
    assert res.status_code == 200 and body["ok"] is True
    assert body["answer"] == "7 days" and body["contexts"] == ["Refunds are accepted within seven days."]
    assert body["contexts_kind"] == "text" and body["error"] is None
    assert "tok-12345678" not in res.text
    assert fx.requests[0]["headers"]["authorization"] == "Bearer tok-12345678"


def test_target_test_reports_precise_failure(project: Any) -> None:
    pid, serve = project
    fx = serve(lambda b, h: js({"other": 1}))
    client.post(f"/api/projects/{pid}/inputs", json={"endpoint_url": fx.url})
    client.post(f"/api/projects/{pid}/target-config", json={"answer_path": "data.answer"})
    body = client.post(f"/api/projects/{pid}/target-test", json={"question": "q"}).json()
    assert body["ok"] is False and "data.answer" in body["error"] and body["answer"] == ""


def test_target_test_needs_endpoint_and_known_project(project: Any) -> None:
    pid, _ = project
    r = client.post(f"/api/projects/{pid}/target-test", json={"question": "q"})
    assert r.status_code == 409
    assert client.post("/api/projects/prj-ffffffffff/target-test",
                       json={"question": "q"}).status_code == 404
