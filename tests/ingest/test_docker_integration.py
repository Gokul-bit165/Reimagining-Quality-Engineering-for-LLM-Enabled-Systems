"""REAL docker integration (skipped when no daemon): build, run, isolate, answer, clean up.

The fixture is a stdlib-only function app, so the build needs no package index. Resources are
named with the prefix `qe-b` and removed in a finalizer even when the test fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from qe.ingest import docker_runner as dr
from qe.ingest.target import docker_available

pytestmark = [pytest.mark.docker,
              pytest.mark.skipif(not docker_available(), reason="docker daemon not reachable")]

PREFIX = "qe-b"
APP = '''
import json, os, socket


def _try(host, port):
    try:
        socket.create_connection((host, port), timeout=3).close()
        return "reachable"
    except OSError:
        return "blocked"


def _proxy_connect(host):
    proxy = os.environ.get("HTTPS_PROXY", "")
    if not proxy:
        return "no-proxy-env"
    ph, pp = proxy.removeprefix("http://").split(":")
    s = socket.create_connection((ph, int(pp)), timeout=10)
    s.sendall(("CONNECT %s:443 HTTP/1.1\\r\\nHost: %s:443\\r\\n\\r\\n" % (host, host)).encode())
    return s.recv(200).decode("latin-1").split("\\r\\n")[0]


def ask(question):
    if question == "__egress__":
        try:
            socket.getaddrinfo("example.com", 443)
            dns = "resolved"
        except OSError:
            dns = "blocked"
        return {"answer": json.dumps({"1.1.1.1:443": _try("1.1.1.1", 443),
                                      "8.8.8.8:53": _try("8.8.8.8", 53), "dns": dns,
                                      "user": os.getuid(), "proxy": os.environ.get("HTTPS_PROXY", "")}),
                "contexts": []}
    if question.startswith("__connect__:"):
        return {"answer": _proxy_connect(question.split(":", 1)[1]), "contexts": []}
    if question == "__write__":
        try:
            open("/app/x", "w").write("x")
            return "wrote"
        except OSError:
            return "read-only"
    return {"answer": "echo: " + question, "contexts": ["ctx one", "ctx two"]}
'''


def _docker_lines(*args: str) -> list[str]:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    return r.stdout.split()


def _leftovers() -> dict[str, list[str]]:
    return {
        "containers": _docker_lines("ps", "-a", "--filter", f"name={PREFIX}-", "--format",
                                    "{{.Names}}"),
        "networks": _docker_lines("network", "ls", "--filter", f"name={PREFIX}-", "--format",
                                  "{{.Name}}"),
        "images": _docker_lines("image", "ls", "--format", "{{.Repository}}",
                                "--filter", f"reference={PREFIX}-*"),
    }


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text(APP, encoding="utf-8")
    (root / ".env").write_text("SECRET_FROM_REPO=must-not-be-baked", encoding="utf-8")
    yield root
    for kind, args in (("containers", ["rm", "-f"]), ("networks", ["network", "rm"]),
                       ("images", ["image", "rm", "-f"])):
        for name in _leftovers()[kind]:
            subprocess.run(["docker", *args, name], capture_output=True, check=False)


def _target(repo: Path, tmp_path: Path, **kw: object) -> dr.ManagedDockerTarget:
    return dr.ManagedDockerTarget("prj-0123456789", repo, prefix=PREFIX,
                                  builds_dir=tmp_path / "builds", **kw)  # type: ignore[arg-type]


def test_build_run_isolate_answer_cleanup(repo: Path, tmp_path: Path) -> None:
    states: list[str] = []
    t = _target(repo, tmp_path, secrets={"MY_TEST_KEY": "s3cret-value-123"},
                on_status=lambda s: states.append(s.state))
    try:
        t.prepare()
        assert states[:2] == ["building", "building"] and "starting" in states
        assert t.status.state == "ready" and t.status.egress == "none"
        running = _leftovers()
        assert len(running["containers"]) == 2 and len(running["networks"]) == 1

        ans = t.ask("What is the capital?")
        assert ans.error is None, ans.error
        assert ans.answer == "echo: What is the capital?"
        assert ans.contexts == ["ctx one", "ctx two"]

        probe = t.ask("__egress__")
        assert probe.error is None, probe.error
        res = json.loads(probe.answer)
        assert res["1.1.1.1:443"] == "blocked" and res["8.8.8.8:53"] == "blocked"
        assert res["dns"] == "blocked"
        assert res["user"] == 65534 and res["proxy"] == ""  # non-root, no proxy when no allowlist
        assert t.ask("__write__").answer == "read-only"

        inspect = subprocess.run(
            ["docker", "inspect", f"{PREFIX}-{t.run_id}-app", "--format",
             "{{.HostConfig.ReadonlyRootfs}} {{.HostConfig.CapDrop}} {{.HostConfig.Privileged}} "
             "{{.HostConfig.PortBindings}} {{.HostConfig.Binds}} {{.HostConfig.PidsLimit}}"],
            capture_output=True, text=True, check=True).stdout
        assert inspect.strip() == "true [ALL] false map[] [] 256"
        net = subprocess.run(["docker", "network", "inspect", f"{PREFIX}-{t.run_id}-net",
                              "--format", "{{.Internal}}"], capture_output=True, text=True,
                             check=True).stdout.strip()
        assert net == "true"
    finally:
        t.close()
    assert t.status.state == "stopped"
    assert _leftovers() == {"containers": [], "networks": [], "images": []}
    assert not (tmp_path / "builds" / t.run_id).exists()
    assert t.ask("again").error  # stopped targets refuse questions
    assert "must-not-be-baked" not in t.status.build_log


def test_allowlist_proxy_denies_unlisted_hosts_and_logs_evidence(repo: Path,
                                                                 tmp_path: Path) -> None:
    t = _target(repo, tmp_path, egress_allow=["example.com"])
    try:
        t.prepare()
        assert t.status.egress == "allowlist: example.com"
        probe = json.loads(t.ask("__egress__").answer)
        assert probe["1.1.1.1:443"] == "blocked" and probe["proxy"].startswith("http://qegw:")
        denied = t.ask("__connect__:evil.example.org").answer
        assert " 403 " in denied, denied
        allowed = t.ask("__connect__:example.com").answer
        assert " 403 " not in allowed, allowed  # 200 with internet, 502 without; never denied
        wild = t.ask("__connect__:example.com.evil.net").answer
        assert " 403 " in wild, wild
    finally:
        t.close()
    log = "\n".join(t.status.egress_log)
    assert "DENY evil.example.org:443 (host not in allowlist)" in log
    assert "DENY example.com.evil.net:443" in log
    assert _leftovers() == {"containers": [], "networks": [], "images": []}


def test_failed_start_leaves_nothing_behind(tmp_path: Path) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "app.py").write_text("def ask(question):\n    raise SystemExit(3)\nimport nope_x\n",
                                 encoding="utf-8")
    t = _target(root, tmp_path, health_timeout_s=30)
    ans = t.ask("q")
    assert ans.error and "exited during startup" in ans.error
    assert t.status.state == "failed" and "ModuleNotFoundError" in t.status.run_log
    assert _leftovers() == {"containers": [], "networks": [], "images": []}


def test_reaper_removes_orphans_of_dead_owner(repo: Path) -> None:
    name = f"{PREFIX}-orphan"
    subprocess.run(["docker", "run", "-d", "--name", name, "--label", "qe-run=1", "--label",
                    "qe-run-owner=99999999", "--label", "qe-run-expires=99999999999",
                    "python:3.12-slim", "sleep", "60"], check=True, capture_output=True)
    try:
        assert name in _docker_lines("ps", "-a", "--format", "{{.Names}}")
        dr.reap_orphans()
        assert name not in _docker_lines("ps", "-a", "--format", "{{.Names}}")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        shutil.rmtree(repo, ignore_errors=True)
