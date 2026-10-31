"""Build and run a user's repo as an isolated service (ADR-0007). Repo code never runs on the host.

Lifecycle of one run (`ManagedDockerTarget`):
  1. detect (runplan) -> stage a sanitised copy of the repo -> `docker build` (network ONLY here,
     no secrets, no build args, no socket/privileged flags, timeout, size caps);
  2. `docker network create --internal`; start the app on it (read-only rootfs, cap-drop ALL,
     no-new-privileges, non-root, pids/memory/cpu limits, no published ports, no mounts);
  3. start a gateway sidecar on bridge + the internal net: loopback-published ingress to the app
     and an opt-in allowlist CONNECT proxy for LLM egress (see docker_gateway);
  4. health-wait, then answer questions through the normal endpoint target (SSRF pinning,
     target_config mapping and response parsing stay in qe.ingest.target);
  5. `close()` always removes containers, network, image and the staging dir.
All docker calls are argument lists (never a shell).
"""

from __future__ import annotations

import atexit
import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping
from pathlib import Path

from qe.ingest import paths
from qe.ingest.docker_gateway import (
    GATEWAY_INGRESS_PORT,
    GATEWAY_PROXY_PORT,
    GATEWAY_SOURCE,
    validate_egress_hosts,
)
from qe.ingest.limits import (
    DOCKER_APP_CPUS,
    DOCKER_APP_MEMORY,
    DOCKER_APP_PIDS,
    DOCKER_BUILD_CPU_QUOTA,
    DOCKER_BUILD_MEMORY,
    DOCKER_BUILD_TIMEOUT_S,
    DOCKER_GATEWAY_MEMORY,
    DOCKER_HEALTH_TIMEOUT_S,
    DOCKER_LABEL,
    DOCKER_LOG_CHARS,
    DOCKER_MAX_CONTEXT_BYTES,
    DOCKER_MAX_IMAGE_BYTES,
    DOCKER_PYTHON_IMAGE,
    DOCKER_RUN_TTL_S,
)
from qe.ingest.models import RuntimeStatus
from qe.ingest.runplan import RunPlan, detect_run_plan
from qe.ingest.target import SandboxedRepoTarget, _docker_client_env
from qe.ingest.target_config import TargetConfig, scrub
from qe.ingest.vault import is_allowed_name
from qe.realeval.target import TargetAnswer

_PATH_OK = re.compile(r"^/[A-Za-z0-9._~/\-]{0,200}$")
_SKIP_COPY_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", ".tox"})
_ENV_EXAMPLE = (".example", ".sample", ".template")
_LOG_OPTS = ["--log-driver", "json-file", "--log-opt", "max-size=1m", "--log-opt", "max-file=1"]
StatusCallback = Callable[[RuntimeStatus], None]


class DockerRunError(Exception):
    """Build or start failed; the message is user-facing, scrubbed and truncated."""


# ---- docker CLI plumbing --------------------------------------------------------------------


def _docker(args: list[str], *, timeout: float = 30, extra_env: Mapping[str, str] | None = None,
            ) -> subprocess.CompletedProcess[str]:
    env = {**_docker_client_env(), **(extra_env or {})}
    try:
        return subprocess.run([shutil.which("docker") or "docker", *args], env=env,  # noqa: S603
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, check=False, shell=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", f"docker {args[0]} timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", f"docker not executable: {exc}")


def _labels(run_id: str, project_id: str, owner: int, expires: int) -> list[str]:
    pairs = {DOCKER_LABEL: "1", f"{DOCKER_LABEL}-id": run_id, f"{DOCKER_LABEL}-project": project_id,
             f"{DOCKER_LABEL}-owner": str(owner), f"{DOCKER_LABEL}-expires": str(expires)}
    return [x for k, v in pairs.items() for x in ("--label", f"{k}={v}")]


def build_image_args(tag: str, context: Path, dockerfile: str, labels: list[str]) -> list[str]:
    """`docker build` argv. Deliberately absent: --build-arg, --secret, --ssh, --allow,
    --privileged, --network host. Network is the default bridge: needed for package indexes, and
    the only phase where the repo's build steps can reach the network (see ADR-0007)."""
    return ["docker", "build", "--progress=plain", "--network", "default", "--force-rm",
            "--memory", DOCKER_BUILD_MEMORY, "--memory-swap", DOCKER_BUILD_MEMORY,
            "--cpu-period", "100000", "--cpu-quota", DOCKER_BUILD_CPU_QUOTA,
            "--file", str(context / dockerfile), "--tag", tag, *labels, str(context)]


def _hardening(memory: str, cpus: str, pids: str) -> list[str]:
    return ["--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "65534:65534", "--memory", memory, "--memory-swap", memory, "--cpus", cpus,
            "--pids-limit", pids, "--ipc", "none", "--init", "--restart", "no",
            "--stop-timeout", "2", "--ulimit", "nofile=1024:1024",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",  # noqa: S108
            *_LOG_OPTS]


def create_network_args(name: str, labels: list[str]) -> list[str]:
    return ["docker", "network", "create", "--driver", "bridge", "--internal", *labels, name]


def app_run_args(name: str, network: str, image: str, port: int, secret_names: list[str],
                 proxy_url: str | None, labels: list[str]) -> list[str]:
    """The user's app: internal network only, no published ports, no mounts. Secret VALUES are
    never in argv (`-e NAME` copies them from the docker CLI's environment)."""
    args = ["docker", "run", "-d", "--name", name, "--network", network,
            "--network-alias", "qeapp", *_hardening(DOCKER_APP_MEMORY, DOCKER_APP_CPUS,
                                                    DOCKER_APP_PIDS),
            "-e", "HOME=/tmp", "-e", f"PORT={port}", "-e", "PYTHONDONTWRITEBYTECODE=1", *labels]
    if proxy_url:
        for k in ("HTTPS_PROXY", "https_proxy"):
            args += ["-e", f"{k}={proxy_url}"]
        args += ["-e", "NO_PROXY=localhost,127.0.0.1"]
    for s in secret_names:
        args += ["-e", s]
    return [*args, image]


def gateway_run_args(name: str, upstream_port: int, allow: list[str], labels: list[str],
                     image: str = DOCKER_PYTHON_IMAGE) -> list[str]:
    return ["docker", "run", "-d", "--name", name, "--network", "bridge",
            "-p", f"127.0.0.1::{GATEWAY_INGRESS_PORT}",
            *_hardening(DOCKER_GATEWAY_MEMORY, "0.5", "128"),
            "-e", "QE_UPSTREAM_HOST=qeapp", "-e", f"QE_UPSTREAM_PORT={upstream_port}",
            "-e", f"QE_ALLOW={','.join(allow)}", *labels, image, "python", "-I", "-c",
            GATEWAY_SOURCE]


# ---- staging --------------------------------------------------------------------------------


def _skip_file(name: str) -> bool:
    if name == ".env" or (name.startswith(".env.") and not name.endswith(_ENV_EXAMPLE)):
        return True
    return name.endswith((".pem", ".key", ".p12", ".pfx")) or name.startswith("id_rsa")


def stage_context(root: Path, dest: Path, plan: RunPlan) -> str:
    """Copy a sanitised snapshot of the repo (no .git, symlinks, dotenv files or key files) and
    write the generated Dockerfile + helper files. Returns the Dockerfile name to build."""
    total = 0
    dest.mkdir(parents=True, exist_ok=True)
    for cur, dirs, names in os.walk(root, followlinks=False):
        rel = Path(cur).relative_to(root)
        dirs[:] = [d for d in dirs if d not in _SKIP_COPY_DIRS
                   and not (Path(cur) / d).is_symlink()]
        (dest / rel).mkdir(parents=True, exist_ok=True)
        for n in names:
            src = Path(cur) / n
            if src.is_symlink() or _skip_file(n):
                continue
            total += src.stat().st_size
            if total > DOCKER_MAX_CONTEXT_BYTES:
                raise DockerRunError("build context exceeds the size cap "
                                     f"({DOCKER_MAX_CONTEXT_BYTES // 1024 // 1024} MiB)")
            shutil.copyfile(src, dest / rel / n)
    if plan.use_repo_dockerfile:
        return "Dockerfile"
    for name, text in plan.extra_files.items():
        (dest / name).write_text(text, encoding="utf-8")
    (dest / "Dockerfile.qe").write_text(plan.dockerfile, encoding="utf-8")
    return "Dockerfile.qe"


# ---- orphan reaper --------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined,unused-ignore]
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap_orphans(now: float | None = None) -> list[str]:
    """Remove containers/networks/images labelled qe-run whose owning process is gone or whose
    TTL elapsed. Safe to call at server start; never touches runs of live processes."""
    now = time.time() if now is None else now
    lab = DOCKER_LABEL
    fmt = f'{{{{.ID}}}}|{{{{.Label "{lab}-owner"}}}}|{{{{.Label "{lab}-expires"}}}}'
    r = _docker(["ps", "-a", "--filter", f"label={DOCKER_LABEL}=1", "--format", fmt])
    removed: list[str] = []
    if r.returncode != 0:
        return removed
    for line in r.stdout.splitlines():
        cid, _, rest = line.partition("|")
        owner, _, expires = rest.partition("|")
        dead = not (owner.isdigit() and _pid_alive(int(owner)))
        expired = expires.isdigit() and int(expires) < now
        if cid and (dead or expired):
            _docker(["rm", "-f", cid])
            removed.append(cid)
    for kind, fmt2 in (("network", "{{.ID}}"),):
        r2 = _docker([kind, "ls", "--filter", f"label={DOCKER_LABEL}=1", "--format", fmt2])
        for nid in r2.stdout.split():
            if _docker([kind, "rm", nid]).returncode == 0:
                removed.append(nid)  # fails harmlessly while containers still use it
    return removed


# ---- the managed target ---------------------------------------------------------------------

_ACTIVE: dict[str, ManagedDockerTarget] = {}
_ACTIVE_LOCK = threading.Lock()


def close_all() -> None:
    with _ACTIVE_LOCK:
        runs = list(_ACTIVE.values())
    for run in runs:
        run.close()


atexit.register(close_all)


def _tail(lines: str, secrets: Mapping[str, str]) -> str:
    return scrub(lines[-DOCKER_LOG_CHARS * 2:], secrets, DOCKER_LOG_CHARS)


class ManagedDockerTarget:
    """RagTarget over a built-and-running container. `prepare()` builds+starts (called by the
    evaluation job so failures surface as a clear job error); `close()` always cleans up."""

    def __init__(self, project_id: str, root: Path, *, secrets: Mapping[str, str] | None = None,
                 egress_allow: list[str] | None = None, target_config: TargetConfig | None = None,
                 app_port: int | None = None, app_path: str | None = None,
                 on_status: StatusCallback | None = None, prefix: str = "qe-run",
                 ttl_s: int = DOCKER_RUN_TTL_S, build_timeout_s: float = DOCKER_BUILD_TIMEOUT_S,
                 health_timeout_s: float = DOCKER_HEALTH_TIMEOUT_S,
                 builds_dir: Path | None = None) -> None:
        self.project_id, self.root = project_id, root
        self._secrets = {k: v for k, v in (secrets or {}).items() if is_allowed_name(k)}
        self._allow = validate_egress_hosts(list(egress_allow or []))
        self._config, self._app_port, self._app_path = target_config, app_port, app_path
        self._on_status, self._prefix, self._ttl = on_status, prefix, ttl_s
        self._build_timeout, self._health_timeout = build_timeout_s, health_timeout_s
        self._builds_dir = builds_dir or paths.runs_root() / "builds"
        self.run_id = uuid.uuid4().hex[:10]
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._closed = False
        self._ready = False
        self._failure = ""
        self._timer: threading.Timer | None = None
        self._inner: SandboxedRepoTarget | None = None
        self._created: list[tuple[str, str]] = []  # (kind, name) to remove on close
        self.capture_raw = False
        self.last_raw: str | None = None
        self.status = RuntimeStatus(egress=self.egress_summary())

    # names
    def _n(self, suffix: str) -> str:
        return f"{self._prefix}-{self.run_id}-{suffix}"

    def egress_summary(self) -> str:
        return "allowlist: " + ", ".join(self._allow) if self._allow else "none"

    def _set(self, state: str, detail: str = "", **kw: object) -> None:
        self.status = self.status.model_copy(update={
            "state": state, "detail": detail[:500], "updated_at": time.time(), **kw})
        if self._on_status:
            try:
                self._on_status(self.status)
            except Exception:  # noqa: BLE001, S110 - status reporting must never break the run
                pass

    # ---- lifecycle
    def prepare(self) -> None:
        with self._lock:
            if self._ready:
                return
            if self._failure:
                raise DockerRunError(self._failure)
            if self._closed or self._cancel.is_set():
                raise DockerRunError("run was stopped")
            with _ACTIVE_LOCK:
                _ACTIVE[self.run_id] = self
            try:
                self._build_and_start()
            except DockerRunError as exc:
                self._fail(str(exc))
                raise
            except Exception as exc:  # noqa: BLE001 - never leak raw internals; always clean up
                msg = f"{type(exc).__name__}: {str(exc)[:200]}"
                self._fail(msg)
                raise DockerRunError(msg) from None

    def _fail(self, message: str) -> None:
        self._failure = message
        logs = self._collect_logs()
        self._teardown()
        self._set("failed", message, run_log=logs[0], egress_log=logs[1])

    def _build_and_start(self) -> None:
        ok, why = _daemon_ok()
        if not ok:
            raise DockerRunError(why)
        self._set("building", "detecting how to run the app")
        from qe.ingest.runplan import NotRunnableError
        try:
            plan = detect_run_plan(self.root, self._app_port, self._app_path)
        except NotRunnableError as exc:
            raise DockerRunError(str(exc)) from None
        self._set("building", f"building image: {plan.description}", kind=plan.kind)
        owner, expires = os.getpid(), int(time.time() + self._ttl + 120)
        labels = _labels(self.run_id, self.project_id, owner, expires)
        image = f"{self._prefix}-{self.run_id}-img:latest"
        self._build(plan, image, labels)
        self._set("starting", "starting isolated network and containers",
                  build_log=self.status.build_log)
        net, app, gw = self._n("net"), self._n("app"), self._n("gw")
        self._created.append(("network", net))
        self._must(create_network_args(net, labels), "network create")
        proxy = f"http://qegw:{GATEWAY_PROXY_PORT}" if self._allow else None
        self._created.append(("container", app))
        self._must(app_run_args(app, net, image, plan.port, sorted(self._secrets), proxy, labels),
                   "app start", extra_env=self._secrets)
        self._created.append(("container", gw))
        self._must(gateway_run_args(gw, plan.port, self._allow, labels), "gateway start")
        self._must(["docker", "network", "connect", "--alias", "qegw", net, gw],
                   "gateway network connect")
        host_port = self._published_port(gw)
        path = plan.http_path if _PATH_OK.match(plan.http_path) else "/"
        self._wait_healthy(app, host_port)
        self._inner = SandboxedRepoTarget(
            "endpoint", endpoint_url=f"http://127.0.0.1:{host_port}{path}",
            secrets=self._secrets, target_config=self._config, trusted_local=True)
        self._ready = True
        self._timer = threading.Timer(self._ttl, self.close)
        self._timer.daemon = True
        self._timer.start()
        self._set("ready", f"app is answering on an isolated network (path {path})")

    def _must(self, args: list[str], what: str, extra_env: Mapping[str, str] | None = None) -> str:
        r = _docker(args[1:], timeout=120, extra_env=extra_env)
        if r.returncode != 0:
            raise DockerRunError(f"{what} failed: " + scrub((r.stderr or r.stdout).strip(),
                                                            self._secrets, 400))
        return r.stdout.strip()

    def _build(self, plan: RunPlan, image: str, labels: list[str]) -> None:
        ctx = self._builds_dir / self.run_id
        self._created.append(("dir", str(ctx)))
        dockerfile = stage_context(self.root, ctx, plan)
        args = build_image_args(image, ctx, dockerfile, labels)
        self._created.append(("image", image))
        proc = subprocess.Popen(  # noqa: S603
            [shutil.which("docker") or "docker", *args[1:]], env=_docker_client_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", shell=False, stdin=subprocess.DEVNULL)
        tail: deque[str] = deque(maxlen=400)

        def pump() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                tail.append(line.rstrip())

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        deadline, reason = time.monotonic() + self._build_timeout, ""
        while proc.poll() is None:
            if time.monotonic() > deadline:
                reason = f"build timed out after {int(self._build_timeout)}s"
            elif self._cancel.is_set():
                reason = "build cancelled"
            if reason:
                proc.kill()
                break
            time.sleep(0.2)
        proc.wait()
        reader.join(5)
        log = _tail("\n".join(tail), self._secrets)
        self._set("building", "build finished", build_log=log)
        if reason or proc.returncode != 0:
            last = next((x for x in reversed(tail) if x.strip()), "no output")
            raise DockerRunError(f"build failed: {reason or scrub(last, self._secrets, 300)}")
        size = self._must(["docker", "image", "inspect", "-f", "{{.Size}}", image], "image inspect")
        if size.isdigit() and int(size) > DOCKER_MAX_IMAGE_BYTES:
            raise DockerRunError(f"build failed: image is {int(size) // 1024**2} MiB, over the "
                                 f"{DOCKER_MAX_IMAGE_BYTES // 1024**2} MiB cap")

    def _published_port(self, gw: str) -> int:
        out = self._must(["docker", "port", gw, f"{GATEWAY_INGRESS_PORT}/tcp"], "port lookup")
        for line in out.splitlines():
            m = re.match(r"^(?:127\.0\.0\.1|0\.0\.0\.0):(\d+)$", line.strip())
            if m:
                return int(m.group(1))
        raise DockerRunError("could not determine the loopback port of the gateway")

    def _wait_healthy(self, app: str, host_port: int) -> None:
        deadline = time.monotonic() + self._health_timeout
        while time.monotonic() < deadline:
            if self._cancel.is_set():
                raise DockerRunError("start cancelled")
            st = _docker(["inspect", "-f", "{{.State.Running}}", app]).stdout.strip()
            if st != "true":
                raise DockerRunError("app container exited during startup")
            if _http_up(host_port):
                return
            time.sleep(0.5)
        raise DockerRunError(f"app did not answer HTTP within {int(self._health_timeout)}s "
                             "(wrong port? set app_port in the project inputs)")

    def _collect_logs(self) -> tuple[str, list[str]]:
        app = self._tail_logs(self._n("app"), 200)
        gw = self._tail_logs(self._n("gw"), 400)
        events: list[str] = []
        for line in gw.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") in ("deny", "allow"):
                tail = f" ({ev['reason']})" if ev.get("reason") else ""
                events.append(f"{str(ev['event']).upper()} {ev.get('host')}:{ev.get('port')}{tail}")
        return app, events[-100:]

    def _tail_logs(self, name: str, n: int) -> str:
        if not any(k == "container" and v == name for k, v in self._created):
            return ""
        r = _docker(["logs", "--tail", str(n), name], timeout=15)
        return _tail((r.stdout or "") + (r.stderr or ""), self._secrets)

    def _teardown(self) -> None:
        """Remove everything this run created. Idempotent; never raises."""
        if self._timer is not None:
            self._timer.cancel()
        for kind, name in reversed(self._created):
            if kind == "container":
                _docker(["rm", "-f", name], timeout=30)
            elif kind == "network":
                _docker(["network", "rm", name], timeout=30)
            elif kind == "image":
                _docker(["image", "rm", "-f", name], timeout=60)
            elif kind == "dir":
                shutil.rmtree(name, ignore_errors=True)
        self._created.clear()
        with _ACTIVE_LOCK:
            _ACTIVE.pop(self.run_id, None)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._cancel.set()
            was_ready = self._ready
            logs = self._collect_logs() if was_ready else ("", [])
            self._ready = False
            self._teardown()
            if was_ready:
                self._set("stopped", "run finished; containers, network and image removed",
                          run_log=logs[0], egress_log=logs[1])

    def kill(self) -> None:
        """Kill switch: interrupt a build/start in progress and tear everything down."""
        self._cancel.set()
        threading.Thread(target=self.close, daemon=True).start()

    # ---- RagTarget
    def ask(self, question: str) -> TargetAnswer:
        if self._closed or self._cancel.is_set():
            return TargetAnswer(error="target was stopped (kill switch, TTL or run finished)")
        if not self._ready:
            try:
                self.prepare()
            except DockerRunError as exc:
                return TargetAnswer(error=str(exc)[:900])
        inner = self._inner
        if inner is None:
            return TargetAnswer(error="app is not running")
        inner.capture_raw = self.capture_raw
        ans = inner.ask(question)
        self.last_raw = inner.last_raw
        return ans


def _daemon_ok() -> tuple[bool, str]:
    from qe.ingest.target import docker_status
    return docker_status()


def _http_up(port: int) -> bool:
    """True once the app answers any HTTP response through the gateway (loopback, own port)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("GET", "/")
        conn.getresponse().read(1)
        return True
    except (TimeoutError, OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()
