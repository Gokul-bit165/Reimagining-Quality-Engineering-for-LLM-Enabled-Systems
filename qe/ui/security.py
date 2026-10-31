"""Local-API hardening: Host allowlist, cross-origin write rejection, request body caps."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from qe.ingest.limits import MAX_JSON_BODY

BASE_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1", "testserver")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_UPLOAD_BODY = 52 * 1024 * 1024  # zip cap (50 MiB) + multipart overhead
UPLOAD_PATH = "/api/projects/upload"


def allowed_hosts() -> list[str]:
    extra = [h.strip() for h in os.environ.get("QE_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return [*BASE_HOSTS, *extra]


class _TooLarge(Exception):
    pass


class OriginGuard:
    """Reject cross-origin state-changing requests (CSRF / DNS-rebinding browser attacks)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _bad(scope: Scope) -> bool:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if headers.get("sec-fetch-site") == "cross-site":
            return True
        origin = headers.get("origin")
        if origin is None:
            return False
        host = (urlsplit(origin).hostname or "").lower()
        return host not in {h.strip("[]") for h in allowed_hosts()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS and self._bad(scope):
            await _respond(send, 403, b'{"detail":"cross-origin request rejected"}')
            return
        await self.app(scope, receive, send)


class BodyLimit:
    """Cap request bytes by streaming count (also covers chunked and multipart bodies)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _limit(scope: Scope) -> int | None:
        path = scope["path"]
        if path == UPLOAD_PATH:
            return MAX_UPLOAD_BODY
        if path.startswith("/api/") and scope["method"] in ("POST", "PUT", "PATCH"):
            return MAX_JSON_BODY
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limit(scope) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        for k, v in scope["headers"]:
            if k == b"content-length" and v.isdigit() and int(v) > limit:
                await _respond(send, 413, b'{"detail":"request body too large"}')
                return
        seen = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise _TooLarge
            return msg

        async def tracking_send(msg: Message) -> None:
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _respond(send, 413, b'{"detail":"request body too large"}')


async def _respond(send: Send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def install(app: object) -> None:
    """Add middleware (last added is outermost: Host check, then origin, then body cap)."""
    add = app.add_middleware  # type: ignore[attr-defined]
    add(BodyLimit)
    add(OriginGuard)
    add(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
