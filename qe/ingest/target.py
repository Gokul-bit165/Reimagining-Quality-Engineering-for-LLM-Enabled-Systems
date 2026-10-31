"""SandboxedRepoTarget: a RagTarget over a user's app. Repo code never runs on the host.

Modes: endpoint (user-deployed app over HTTP), docker (isolated container, no network),
static_only (nothing is executed; every ask() reports that explicitly).
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from qe.ingest.limits import (
    DOCKER_CPUS,
    DOCKER_IMAGE,
    DOCKER_MEMORY,
    DOCKER_PIDS,
    DOCKER_TIMEOUT_S,
    ENDPOINT_MAX_RESPONSE_BYTES,
    ENDPOINT_TIMEOUT_S,
)
from qe.ingest.models import ExecutionMode
from qe.ingest.netguard import EndpointError, ResolvedEndpoint, resolve_endpoint
from qe.ingest.vault import is_allowed_name
from qe.realeval.target import TargetAnswer

ANSWER_KEYS = ("answer", "output", "response", "result", "text", "message")
CONTEXT_KEYS = ("contexts", "context", "sources", "source_documents", "citations", "documents")
MARK = "@@QE_RESULT@@"

HARNESS = r"""
import importlib, json, os, sys
sys.path.insert(0, "/app")
mod = importlib.import_module(os.environ["QE_MODULE"])
fn = getattr(mod, os.environ["QE_FUNC"])
res = fn(os.environ["QE_QUESTION"])
print("@@QE_RESULT@@" + json.dumps(res, default=str))
"""


class _PinnedHTTP(http.client.HTTPConnection):
    """Connects to a pre-validated IP; Host header comes from the original hostname."""

    def __init__(self, ep: ResolvedEndpoint, timeout: float) -> None:
        super().__init__(ep.host, ep.port, timeout=timeout)
        self._ip = ep.ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    """TLS to a pre-validated IP with SNI and certificate checks for the original hostname."""

    def __init__(self, ep: ResolvedEndpoint, timeout: float) -> None:
        super().__init__(ep.host, ep.port, timeout=timeout,
                         context=ssl.create_default_context())
        self._ip = ep.ip

    def connect(self) -> None:
        raw = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)  # type: ignore[attr-defined]


def docker_available() -> bool:
    exe = shutil.which("docker")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "version", "--format", "{{.Server.Version}}"],  # noqa: S603
                           capture_output=True, timeout=5, check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def build_docker_args(name: str, workspace: Path, module: str, func: str,
                      secret_names: list[str], image: str = DOCKER_IMAGE) -> list[str]:
    args = ["docker", "run", "--rm", "--name", name, "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534", "--memory", DOCKER_MEMORY, "--cpus", DOCKER_CPUS,
            "--memory-swap", DOCKER_MEMORY, "--ipc", "none", "--init",
            "--ulimit", "nofile=256:256", "--ulimit", "nproc=128:128",
            "--pids-limit", DOCKER_PIDS, "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108
            "-v", f"{workspace}:/app:ro", "-w", "/app",
            "-e", f"QE_MODULE={module}", "-e", f"QE_FUNC={func}", "-e", "QE_QUESTION",
            "-e", "PYTHONDONTWRITEBYTECODE=1"]
    for s in secret_names:  # names only: values travel via the process env, not the arg list
        args += ["-e", s]
    return [*args, image, "python", "-I", "-c", HARNESS]


def parse_app_response(raw: Any) -> tuple[str, list[str]]:
    if isinstance(raw, str):
        return raw, []
    if isinstance(raw, list | tuple) and raw:
        ans = str(raw[0])
        ctx = raw[1] if len(raw) > 1 and isinstance(raw[1], list) else []
        return ans, [_ctx_text(c) for c in ctx]
    if isinstance(raw, dict):
        ans = next((str(raw[k]) for k in ANSWER_KEYS if raw.get(k) is not None), "")
        ctxs: list[str] = []
        for k in CONTEXT_KEYS:
            v = raw.get(k)
            if isinstance(v, list):
                ctxs = [_ctx_text(c) for c in v]
                break
            if isinstance(v, str) and v:
                ctxs = [v]
                break
        return ans, ctxs
    return str(raw), []


def _ctx_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        for k in ("text", "content", "page_content", "snippet", "chunk"):
            if isinstance(c.get(k), str):
                return str(c[k])
    return json.dumps(c, default=str)[:2000]


class SandboxedRepoTarget:
    def __init__(self, mode: ExecutionMode, *, endpoint_url: str | None = None,
                 workspace: Path | None = None, entry_file: str = "", entry_func: str = "",
                 secrets: dict[str, str] | None = None) -> None:
        self.mode = mode
        self.endpoint_url = endpoint_url
        self.workspace = workspace
        self.entry_file = entry_file
        self.entry_func = entry_func
        self._secrets = dict(secrets or {})
        self._container = f"qe-{uuid.uuid4().hex[:12]}"
        self._killed = False

    def kill(self) -> None:
        """Kill switch: stop any running container and refuse further asks."""
        self._killed = True
        if self.mode == "docker":
            subprocess.run(["docker", "kill", self._container],  # noqa: S603, S607
                           capture_output=True, timeout=10, check=False, shell=False)

    def ask(self, question: str) -> TargetAnswer:
        start = time.perf_counter()
        if self._killed:
            return TargetAnswer(error="target was stopped by the kill switch")
        try:
            if self.mode == "endpoint":
                ans, ctx = self._ask_endpoint(question)
            elif self.mode == "docker":
                ans, ctx = self._ask_docker(question)
            else:
                return TargetAnswer(error="static_only: not executed (no endpoint or Docker)")
        except (RuntimeError, EndpointError, OSError, ValueError,
                subprocess.SubprocessError) as exc:
            return TargetAnswer(latency_s=time.perf_counter() - start,
                                error=f"{type(exc).__name__}: {str(exc)[:300]}")
        return TargetAnswer(answer=ans, contexts=ctx, latency_s=time.perf_counter() - start)

    def _ask_endpoint(self, question: str) -> tuple[str, list[str]]:
        if not self.endpoint_url:
            raise RuntimeError("no endpoint_url configured")
        ep = resolve_endpoint(self.endpoint_url)  # validated + pinned on every call
        body = json.dumps({"question": question, "query": question, "input": question}).encode()
        conn: http.client.HTTPConnection = (
            _PinnedHTTPS(ep, ENDPOINT_TIMEOUT_S) if ep.scheme == "https"
            else _PinnedHTTP(ep, ENDPOINT_TIMEOUT_S))  # http.client never uses proxy env vars
        try:
            conn.request("POST", ep.path, body=body,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if 300 <= resp.status < 400:
                raise RuntimeError("endpoint answered with a redirect; redirects are not followed")
            data = resp.read(ENDPOINT_MAX_RESPONSE_BYTES + 1)
            status = resp.status
        finally:
            conn.close()
        if len(data) > ENDPOINT_MAX_RESPONSE_BYTES:
            raise RuntimeError("response exceeded the size limit")
        if status >= 400:
            raise RuntimeError(f"endpoint returned HTTP {status}")
        try:
            raw: Any = json.loads(data.decode("utf-8", errors="replace"))
        except ValueError:
            raw = data.decode("utf-8", errors="replace")
        return parse_app_response(raw)

    def _ask_docker(self, question: str) -> tuple[str, list[str]]:
        if self.workspace is None or not self.entry_file or not self.entry_func:
            raise RuntimeError("docker mode needs a workspace and a function entrypoint")
        module = self.entry_file.removesuffix(".py").replace("/", ".")
        names = sorted(k for k in self._secrets if is_allowed_name(k))
        args = build_docker_args(self._container, self.workspace.resolve(), module,
                                 self.entry_func, names)
        allowed = {k: v for k, v in self._secrets.items() if is_allowed_name(k)}
        env = {**_docker_client_env(), "QE_QUESTION": question, **allowed}
        try:
            proc = subprocess.run(args, env=env, capture_output=True, text=True,  # noqa: S603
                                  timeout=DOCKER_TIMEOUT_S, check=False, shell=False,
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            self.kill_container()
            raise RuntimeError(f"container timed out after {DOCKER_TIMEOUT_S}s") from None
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(MARK):
                return parse_app_response(json.loads(line[len(MARK):]))
        tail = (proc.stderr.strip().splitlines() or ["no output"])[-1]
        raise RuntimeError(f"app did not return a result: {tail[:300]}")

    def kill_container(self) -> None:
        subprocess.run(["docker", "kill", self._container],  # noqa: S603, S607
                       capture_output=True, timeout=10, check=False, shell=False)



_DOCKER_CLIENT_ENV = ("PATH", "SYSTEMROOT", "USERPROFILE", "HOME", "APPDATA", "TEMP", "TMP",
                      "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")


def _docker_client_env() -> dict[str, str]:
    """Minimal env for the docker CLI process: operator's docker config, no other host secrets."""
    return {k: v for k, v in os.environ.items() if k in _DOCKER_CLIENT_ENV}
