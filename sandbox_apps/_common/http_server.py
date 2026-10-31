"""Loopback-only HTTP wrapper: POST /invoke, GET /health. Standard library only."""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sandbox_apps._common.base import VARIANTS, SandboxApp

LOOPBACK = "127.0.0.1"
MAX_BODY_BYTES = 1_000_000


def make_server(app: SandboxApp, host: str = LOOPBACK, port: int = 0) -> ThreadingHTTPServer:
    """Build (not start) a server. Only the loopback address is accepted."""
    if host != LOOPBACK:
        raise ValueError("sandbox servers bind to 127.0.0.1 only")
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send(200, {"status": "ok", "app": app.app_name, "variant": app.variant})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/invoke":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._send(413, {"error": "body too large"})
                return
            try:
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                with lock:
                    response = app.invoke(request)
            except (ValueError, UnicodeDecodeError) as exc:
                self._send(400, {"error": str(exc)})
                return
            self._send(200, response)

        def log_message(self, format: str, *args: Any) -> None:
            return  # silent: request bodies may be sensitive test inputs

    return ThreadingHTTPServer((host, port), Handler)


def run_cli(app_name: str, build_app: Callable[..., SandboxApp]) -> None:
    parser = argparse.ArgumentParser(prog=f"python -m sandbox_apps.{app_name}")
    parser.add_argument("--variant", choices=VARIANTS, default="clean")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--drift", action="store_true")
    args = parser.parse_args()
    app = build_app(args.variant, seed=args.seed, drift=args.drift)
    server = make_server(app, LOOPBACK, args.port)
    print(f"{app_name}/{args.variant} listening on http://{LOOPBACK}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
