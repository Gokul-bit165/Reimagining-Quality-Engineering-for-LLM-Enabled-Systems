"""Campaign test fixtures: local HTTP fake RAG services of known quality + a fake chat server.

All fixtures live here only; nothing in qe/ produces simulated data.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qe.ingest.vault import VAULT  # noqa: E402
from qe.realeval import resolver  # noqa: E402
from qe.realeval.resolver import ResolvedProject  # noqa: E402
from qe.realeval.target import FakeRagTarget  # noqa: E402

FACTS = [f"Zavo{k} costs {100 + k} dollars." for k in range(40)]
DOC = {"name": "pricing.md", "text": " ".join(FACTS)}
QA = [{"question": f"How much does Zavo{k} cost?", "reference_answer": f"{100 + k} dollars"}
      for k in range(40)]
CHAT_KEY = "sk-test-campaign-0123456789"


class Server:
    def __init__(self, httpd: ThreadingHTTPServer, thread: threading.Thread) -> None:
        self.httpd, self.thread = httpd, thread
        self.hits: list[str] = []
        self.auth: list[str] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _serve(handler: type[BaseHTTPRequestHandler]) -> Server:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    srv = Server(httpd, thread)
    httpd.srv = srv  # type: ignore[attr-defined]
    return srv


def rag_server(mode: str, delay: float = 0.0) -> Server:
    """A fake RAG service. mode: perfect | hallucinating | injectable | flaky."""
    fake = FakeRagTarget([DOC["text"]], mode)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.srv.hits.append(body["question"])  # type: ignore[attr-defined]
            if delay:
                time.sleep(delay)
            with lock:
                ans = fake.ask(body["question"])
            if ans.error:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(ans.error.encode())
                return
            out = json.dumps({"answer": ans.answer, "contexts": ans.contexts}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    return _serve(Handler)


def chat_server() -> Server:
    """A fake OpenAI-compatible server: answers from the stuffed documents, reports usage."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a: Any) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            srv = self.server.srv  # type: ignore[attr-defined]
            srv.auth.append(self.headers.get("Authorization", ""))
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            system, question = body["messages"][0]["content"], body["messages"][1]["content"]
            docs = system.split("<documents>")[1].split("</documents>")[0]
            fake = FakeRagTarget([docs.split("]", 1)[1] if "]" in docs else docs])
            ans = fake.ask(question)
            text = (f"{ans.answer} [pricing.md]" if ans.answer and not ans.error
                    else "I do not know based on the provided documents.")
            out = json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}],
                              "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                                        "total_tokens": 110}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

    return _serve(Handler)


@pytest.fixture
def proj() -> dict[str, Any]:
    """Mutable description of the project the injected resolver returns."""
    return {"authorized": True, "qa": QA, "flags": []}


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
         proj: dict[str, Any]) -> Iterator[None]:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "QE_ALLOW_REAL_LLM"):
        monkeypatch.delenv(k, raising=False)
    state = proj

    def _resolve(pid: str) -> ResolvedProject:
        return ResolvedProject(pid, "demo", FakeRagTarget([DOC["text"]]), [DOC],
                               list(state["qa"]), risk_flags=list(state["flags"]),
                               authorized=state["authorized"])

    resolver.set_resolver(_resolve)
    VAULT.set("p1", {"FAKE_LLM_KEY": CHAT_KEY})
    yield
    resolver.set_resolver(None)
    VAULT.clear("p1")


@pytest.fixture
def servers() -> Iterator[dict[str, Server]]:
    made = {"good": rag_server("perfect"), "bad": rag_server("hallucinating"),
            "inj": rag_server("injectable"), "flaky": rag_server("flaky"),
            "slow": rag_server("perfect", delay=0.12), "chat": chat_server()}
    yield made
    for s in made.values():
        s.stop()
