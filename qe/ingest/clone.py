"""Safe shallow clone + workspace sanitising. Repo content is untrusted and never executed."""

from __future__ import annotations

import base64
import os
import shutil
import stat
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qe.ingest.limits import CLONE_TIMEOUT_S, MAX_REPO_BYTES, MAX_REPO_FILES
from qe.ingest.url import RepoRef

BLOB_LIMIT = "5m"
WATCHDOG_INTERVAL_S = 0.5
_ENV_PASSTHROUGH = ("PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "TEMP", "TMP",
                    "HTTPS_PROXY", "https_proxy", "NO_PROXY", "SSL_CERT_FILE")


class IngestError(RuntimeError):
    """User-presentable ingest failure (never includes secrets)."""


@dataclass(frozen=True)
class WorkspaceStats:
    files: int
    bytes: int
    symlinks_removed: int


def build_clone_args(ref: RepoRef, dest: Path) -> list[str]:
    args = [
        "git",
        "-c", f"core.hooksPath={os.devnull}",
        "-c", "protocol.file.allow=never",
        "-c", "protocol.allow=never",
        "-c", "protocol.https.allow=always",
        "-c", "core.symlinks=false",
        "-c", "core.fsmonitor=false",
        "-c", "credential.helper=",
        "clone", "--depth", "1", "--no-tags", "--single-branch",
        "--no-recurse-submodules", f"--filter=blob:limit={BLOB_LIMIT}",
    ]
    if ref.branch:
        args += ["--branch", ref.branch]
    return [*args, "--", ref.clone_url, str(dest)]


def build_env(token: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_PASSTHROUGH}
    env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ALLOW_PROTOCOL": "https",
                "GCM_INTERACTIVE": "never"})
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.extraHeader",
                    "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}"})
    return env


def rmtree(path: Path) -> None:
    def onexc(func: Callable[[str], Any], p: str, _exc: BaseException) -> None:
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=onexc)


def _is_link(p: str) -> bool:
    return os.path.islink(p) or os.path.isjunction(p)


def _unlink_any(p: str) -> None:
    if os.path.isdir(p) and not os.path.islink(p):
        os.rmdir(p)  # junction
    else:
        os.unlink(p)


def sanitize_workspace(root: Path) -> WorkspaceStats:
    """Delete .git and every symlink/junction; enforce size and file-count caps."""
    git_dir = root / ".git"
    if git_dir.exists() and not _is_link(str(git_dir)):
        rmtree(git_dir)
    files = total = removed = 0
    for cur, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs) + list(names):
            p = os.path.join(cur, name)
            if _is_link(p):
                _unlink_any(p)
                removed += 1
                if name in dirs:
                    dirs.remove(name)
        for name in names:
            p = os.path.join(cur, name)
            if os.path.lexists(p):
                files += 1
                total += os.lstat(p).st_size
        if files > MAX_REPO_FILES:
            raise IngestError(f"repository has more than {MAX_REPO_FILES} files")
        if total > MAX_REPO_BYTES:
            raise IngestError(f"repository larger than {MAX_REPO_BYTES // (1024 * 1024)} MiB")
    return WorkspaceStats(files=files, bytes=total, symlinks_removed=removed)


def resolve_subdir(root: Path, subdir: str) -> Path:
    base = root.resolve()
    target = (root / subdir).resolve() if subdir else base
    if not target.is_relative_to(base) or not target.is_dir():
        raise IngestError("subdir does not exist inside the repository")
    return target


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _dir_bytes(root: Path, limit: int) -> int:
    """Total size of regular files under root, stopping early once `limit` is exceeded."""
    total = 0
    stack = [str(root)]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    else:
                        total += e.stat(follow_symlinks=False).st_size
                        if total > limit:
                            return total
        except OSError:
            continue
    return total


def run_with_watchdog(args: list[str], dest: Path, env: dict[str, str] | None,
                      timeout: float) -> subprocess.CompletedProcess[str]:
    """Run git while polling the workspace size; kill it if it grows past MAX_REPO_BYTES."""
    proc = subprocess.Popen(args, env=env, shell=False, stdin=subprocess.DEVNULL,  # noqa: S603
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    try:
        while proc.poll() is None:
            if time.monotonic() > deadline:
                proc.kill()
                proc.communicate()
                raise subprocess.TimeoutExpired(args, timeout)
            if dest.exists() and _dir_bytes(dest, MAX_REPO_BYTES) > MAX_REPO_BYTES:
                proc.kill()
                proc.communicate()
                raise IngestError(f"repository larger than {MAX_REPO_BYTES // (1024 * 1024)} MiB")
            time.sleep(WATCHDOG_INTERVAL_S)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        raise
    out, err = proc.communicate()
    return subprocess.CompletedProcess(args, proc.returncode, out, err)


def _default_runner(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
    return run_with_watchdog(args, Path(args[-1]), kw.get("env"), kw["timeout"])


def clone_repo(ref: RepoRef, dest: Path, token: str | None = None,
               runner: Runner = _default_runner) -> WorkspaceStats:
    """Clone into `dest` (must not exist). Raises IngestError on any failure."""
    if dest.exists():
        raise IngestError("workspace already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = runner(build_clone_args(ref, dest), env=build_env(token), shell=False,
                      capture_output=True, text=True, timeout=CLONE_TIMEOUT_S, check=False,
                      stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        _cleanup(dest)
        raise IngestError(f"clone timed out after {CLONE_TIMEOUT_S}s") from None
    except IngestError:
        _cleanup(dest)
        raise
    except OSError as exc:
        raise IngestError(f"git is not available: {type(exc).__name__}") from None
    if proc.returncode != 0:
        _cleanup(dest)
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise IngestError(f"git clone failed: {_scrub(tail[0], token)}")
    try:
        return sanitize_workspace(dest)
    except IngestError:
        _cleanup(dest)
        raise


def _scrub(text: str, token: str | None) -> str:
    return (text.replace(token, "***") if token else text)[:300]


def _cleanup(dest: Path) -> None:
    if dest.exists():
        rmtree(dest)
