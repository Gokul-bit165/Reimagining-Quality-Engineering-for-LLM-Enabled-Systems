"""Local fake judge servers speaking the OpenAI chat format. No real model is ever called."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from sandbox_apps._common.llm import OpenAICompatibleLLM

KEY_ENV = "FAKE_JUDGE_KEY"
Responder = Callable[[str, str], str]


def field(user: str, name: str) -> str:
    m = re.search(rf"<untrusted_{name}>\n(.*?)\n</untrusted_{name}>", user, re.S)
    return m.group(1) if m else ""


class Scripted:
    """Rule-based stand-in for a judge model. rubric: answer substring -> label; claims: claim
    substring -> (verdict, quote). Unmatched: 'incorrect' / 'not_enough_info'."""

    def __init__(self, rubric: dict[str, str] | None = None,
                 claims: dict[str, tuple[str, str]] | None = None, raw: str | None = None) -> None:
        self.rubric, self.claims, self.raw = rubric or {}, claims or {}, raw
        self.requests: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.requests.append((system, user))
        if self.raw is not None:
            return self.raw
        if "<untrusted_claim>" in user:
            claim = field(user, "claim")
            for sub, (verdict, quote) in self.claims.items():
                if sub in claim:
                    return json.dumps({"verdict": verdict, "quote": quote})
            return json.dumps({"verdict": "not_enough_info", "quote": ""})
        answer = field(user, "answer")
        for sub, label in self.rubric.items():
            if sub in answer:
                return json.dumps({"label": label})
        return json.dumps({"label": "incorrect"})


@contextmanager
def fake_server(responder: Responder) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            msgs = body["messages"]
            system = " ".join(m["content"] for m in msgs if m["role"] == "system")
            user = msgs[-1]["content"]
            out = json.dumps({"choices": [{"message": {"content": responder(system, user)}}]})
            data = out.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def client(url: str, model: str) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(url, model, api_key_env=KEY_ENV, timeout=10.0)
