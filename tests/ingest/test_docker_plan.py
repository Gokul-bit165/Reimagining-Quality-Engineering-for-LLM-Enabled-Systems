"""Unit tests: run-plan detection, Dockerfile generation and docker argv construction.

No docker daemon is needed: argument lists are asserted, the CLI is mocked where state matters.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from qe.ingest import docker_runner as dr
from qe.ingest.docker_gateway import validate_egress_hosts
from qe.ingest.models import ProjectAnalysis
from qe.ingest.runplan import NotRunnableError, detect_run_plan
from qe.ingest.summary import choose_mode_detailed


def _w(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ---- detection ------------------------------------------------------------------------------


def test_repo_dockerfile_wins_and_reads_expose(tmp_path: Path) -> None:
    _w(tmp_path, "Dockerfile", 'FROM python:3.12\nEXPOSE 9000\nCMD ["python", "x.py"]\n')
    _w(tmp_path, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n"
                            "@app.post('/chat')\ndef chat(q): ...\n")
    plan = detect_run_plan(tmp_path)
    assert plan.kind == "dockerfile" and plan.use_repo_dockerfile
    assert plan.port == 9000 and plan.http_path == "/chat" and plan.dockerfile == ""


def test_fastapi_detected_with_route_and_extras(tmp_path: Path) -> None:
    _w(tmp_path, "requirements.txt", "langchain==0.2.0\n")
    _w(tmp_path, "src/api.py", "from fastapi import FastAPI\nserver = FastAPI()\n"
                               "@server.get('/health')\ndef h(): ...\n"
                               "@server.post('/ask')\nasync def ask(body): ...\n")
    plan = detect_run_plan(tmp_path)
    assert plan.kind == "python-asgi" and plan.entry == "src.api:server"
    assert plan.http_path == "/ask"
    assert "pip install --no-cache-dir -r requirements.txt" in plan.dockerfile
    assert "pip install --no-cache-dir uvicorn fastapi" in plan.dockerfile  # not in the manifest
    assert '"uvicorn", "src.api:server"' in plan.dockerfile


def test_flask_and_function_and_node(tmp_path: Path) -> None:
    flask = tmp_path / "f"
    _w(flask, "app.py", "from flask import Flask\napp = Flask(__name__)\n"
                        "@app.route('/query', methods=['POST'])\ndef q(): ...\n")
    p = detect_run_plan(flask)
    assert p.kind == "python-flask" and p.http_path == "/query"
    assert "pip install --no-cache-dir flask" in p.dockerfile

    fn = tmp_path / "fn"
    _w(fn, "pyproject.toml", "[project]\nname='x'\ndependencies=['requests']\n")
    _w(fn, "rag/core.py", "def answer_question(question):\n    return 'a'\n")
    p = detect_run_plan(fn)
    assert p.kind == "python-function" and p.entry == "rag.core.answer_question"
    assert "ENV QE_MODULE=rag.core QE_FUNC=answer_question" in p.dockerfile
    assert "RUN pip install --no-cache-dir ." in p.dockerfile
    assert "_qe_server.py" in p.extra_files

    node = tmp_path / "n"
    _w(node, "package.json", json.dumps({"scripts": {"start": "node server.js"}}))
    _w(node, "server.js", "const app=require('express')();\napp.post('/ask',()=>{});\n"
                          "app.listen(3000)\n")
    p = detect_run_plan(node)
    assert p.kind == "node" and p.port == 3000 and p.http_path == "/ask"
    assert 'CMD ["npm", "start"]' in p.dockerfile and "FROM node:22-slim" in p.dockerfile


@pytest.mark.parametrize("files,reason", [
    ({"README.md": "hi"}, "no entrypoint detected"),
    ({"package.json": "{}"}, "no 'start' script"),
    ({"a.py": "def helper(x, y):\n    return 1\n"}, "no entrypoint detected"),
    ({"a.py": "def ask(q, k):\n    return 1\n"}, "no entrypoint detected"),  # 2 required args
])
def test_not_runnable_reasons(tmp_path: Path, files: dict[str, str], reason: str) -> None:
    for rel, text in files.items():
        _w(tmp_path, rel, text)
    with pytest.raises(NotRunnableError, match=reason):
        detect_run_plan(tmp_path)


def test_overrides_apply(tmp_path: Path) -> None:
    _w(tmp_path, "m.py", "def ask(question):\n    return 'a'\n")
    plan = detect_run_plan(tmp_path, app_port=9001, app_path="/x")
    assert plan.port == 9001 and plan.http_path == "/x" and "EXPOSE 9001" in plan.dockerfile


# ---- generated Dockerfile hygiene -----------------------------------------------------------


def test_generated_dockerfile_is_deterministic_and_unprivileged(tmp_path: Path) -> None:
    _w(tmp_path, "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    a, b = detect_run_plan(tmp_path), detect_run_plan(tmp_path)
    assert a.dockerfile == b.dockerfile
    text = a.dockerfile
    assert text.startswith("FROM python:3.12-slim\n") and "@sha256" not in text
    assert "USER 65534:65534" in text
    for banned in ("ARG ", "--mount", "ADD http", "curl", "sudo", "--privileged"):
        assert banned not in text


# ---- docker argv ----------------------------------------------------------------------------


def test_build_args_have_no_dangerous_flags(tmp_path: Path) -> None:
    args = dr.build_image_args("t:latest", tmp_path, "Dockerfile.qe", ["--label", "qe-run=1"])
    assert all(isinstance(a, str) for a in args) and args[:2] == ["docker", "build"]
    j = " ".join(args)
    for bad in ("--build-arg", "--secret", "--ssh", "--allow", "--privileged", "host",
                "docker.sock"):
        assert bad not in j
    assert "--network default" in j and "--memory 2g" in j and "--force-rm" in j


def test_app_args_are_locked_down() -> None:
    args = dr.app_run_args("qe-b-app", "qe-b-net", "img:latest", 8000, ["OPENAI_API_KEY"],
                           "http://qegw:3128", ["--label", "qe-run=1"])
    j = " ".join(args)
    for needle in ("--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                   "--user 65534:65534", "--network qe-b-net", "--pids-limit 256",
                   "--memory 1g", "--memory-swap 1g", "--cpus 1", "--ipc none", "--init",
                   "--tmpfs /tmp:rw,noexec,nosuid", "HTTPS_PROXY=http://qegw:3128"):
        assert needle in j, needle
    for bad in ("--privileged", " -p ", "--publish", " -v ", "--mount", "docker.sock",
                "--network host", "--cap-add", "--pid host", "--device"):
        assert bad not in f" {j} "
    assert "OPENAI_API_KEY" in args and "OPENAI_API_KEY=" not in j  # name only, never a value
    assert args[-1] == "img:latest"


def test_app_args_without_allowlist_have_no_proxy() -> None:
    j = " ".join(dr.app_run_args("a", "n", "i", 8000, [], None, []))
    assert "PROXY" not in j.upper()


def test_gateway_and_network_args() -> None:
    gw = dr.gateway_run_args("qe-b-gw", 8000, ["api.openai.com"], [])
    j = " ".join(gw)
    assert "-p 127.0.0.1::8000" in j and "QE_ALLOW=api.openai.com" in j
    for needle in ("--read-only", "--cap-drop ALL", "no-new-privileges", "--user 65534:65534"):
        assert needle in j
    assert "--privileged" not in j and "docker.sock" not in j
    net = dr.create_network_args("qe-b-net", ["--label", "qe-run=1"])
    assert "--internal" in net and net[:3] == ["docker", "network", "create"]


def test_egress_host_validation() -> None:
    assert validate_egress_hosts(["API.OpenAI.com", "api.openai.com", "*.azure.com"]) == [
        "api.openai.com", "*.azure.com"]
    for bad in ("https://api.openai.com", "api.openai.com:443", "1.2.3.4", "localhost", "*",
                "a b.com", "-x.com", "x.com/path", ""):
        with pytest.raises(ValueError):
            validate_egress_hosts([bad])


# ---- staging --------------------------------------------------------------------------------


def test_stage_context_strips_secrets_git_and_links(tmp_path: Path) -> None:
    root, dest = tmp_path / "repo", tmp_path / "ctx"
    _w(root, "app.py", "def ask(question):\n    return 'x'\n")
    _w(root, ".env", "OPENAI_API_KEY=sk-secret")
    _w(root, ".env.production", "X=1")
    _w(root, ".env.example", "X=")
    _w(root, "server.pem", "-----BEGIN")
    _w(root, ".git/config", "[core]")
    _w(root, "node_modules/x/index.js", "1")
    plan = detect_run_plan(root)
    name = dr.stage_context(root, dest, plan)
    got = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert name == "Dockerfile.qe"
    assert {"app.py", ".env.example", "Dockerfile.qe", "_qe_server.py"} <= got
    assert not ({".env", ".env.production", "server.pem", ".git/config"} & got)
    assert not any(g.startswith("node_modules") for g in got)


# ---- mode selection -------------------------------------------------------------------------


def test_choose_mode_reasons(tmp_path: Path) -> None:
    a = ProjectAnalysis()
    _w(tmp_path, "m.py", "def ask(question):\n    return 'x'\n")
    mode, why, plan = choose_mode_detailed(None, a, True, tmp_path)
    assert (mode, why) == ("docker", "") and plan is not None
    mode, why, _ = choose_mode_detailed(None, a, False, tmp_path, "docker daemon not running")
    assert (mode, why) == ("static_only", "docker daemon not running")
    empty = tmp_path / "e"
    empty.mkdir()
    mode, why, _ = choose_mode_detailed(None, a, True, empty)
    assert mode == "static_only" and "no entrypoint detected" in why
    assert choose_mode_detailed("https://x.example/ask", a, False, empty)[0] == "endpoint"


# ---- managed target with a mocked docker CLI ------------------------------------------------


def test_daemon_down_is_a_clear_error_and_no_retry_storm(monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:
    _w(tmp_path, "m.py", "def ask(question):\n    return 'x'\n")
    calls: list[int] = []

    def down() -> tuple[bool, str]:
        calls.append(1)
        return False, "docker daemon not running"

    monkeypatch.setattr(dr, "_daemon_ok", down)
    t = dr.ManagedDockerTarget("prj-0123456789", tmp_path, builds_dir=tmp_path / "b")
    first, second = t.ask("q"), t.ask("q")
    assert first.error == "docker daemon not running" == second.error
    assert len(calls) == 1 and t.status.state == "failed"  # failure is remembered
    t.close()


def test_failed_build_cleans_up_and_reports(monkeypatch: pytest.MonkeyPatch,
                                            tmp_path: Path) -> None:
    _w(tmp_path / "repo", "m.py", "def ask(question):\n    return 'x'\n")
    monkeypatch.setattr(dr, "_daemon_ok", lambda: (True, ""))
    seen: list[list[str]] = []

    class FakeProc:
        returncode = 1
        stdout = iter(["Step 1/5\n", "ERROR: no matching distribution for sk-abcdefghijklmnop\n"])

        def poll(self) -> int:
            return 1

        def wait(self) -> int:
            return 1

        def kill(self) -> None:
            pass

    monkeypatch.setattr(dr.subprocess, "Popen", lambda *a, **k: FakeProc())

    def fake_docker(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dr, "_docker", fake_docker)
    states: list[str] = []
    t = dr.ManagedDockerTarget("prj-0123456789", tmp_path / "repo", builds_dir=tmp_path / "b",
                               on_status=lambda s: states.append(s.state))
    ans = t.ask("q")
    assert ans.error and ans.error.startswith("build failed")
    assert "sk-abcdefghijklmnop" not in (ans.error + t.status.build_log)  # scrubbed
    assert states[0] == "building" and states[-1] == "failed"
    assert not (tmp_path / "b" / t.run_id).exists()  # staging dir removed
    assert any(a[:2] == ["image", "rm"] for a in seen)  # image removal attempted
    assert t.run_id not in dr._ACTIVE  # deregistered


def test_reaper_removes_dead_owner_and_expired_only(monkeypatch: pytest.MonkeyPatch) -> None:
    removed: list[str] = []
    me = os.getpid()
    listing = f"dead1|99999999|{2**40}\nlive1|{me}|{2**40}\nold1|{me}|5\n"

    def fake(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, listing, "")
        if args[:2] == ["rm", "-f"]:
            removed.append(args[2])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(dr, "_docker", fake)
    dr.reap_orphans(now=1000.0)
    assert sorted(removed) == ["dead1", "old1"]


# ---- wiring: routes, resolver and evaluation-job lifecycle ----------------------------------


@pytest.fixture
def ingested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qe.ingest import clone as clone_mod
    from qe.ingest import jobs
    from qe.ui.routes_projects import router

    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path / "runs"))

    def fake_clone(ref: Any, dest: Path, token: str | None = None) -> None:
        dest.mkdir(parents=True)
        (dest / "app.py").write_text("def ask(question):\n    return 'x'\n")

    monkeypatch.setattr(clone_mod, "clone_repo", fake_clone)
    monkeypatch.setattr(jobs, "docker_available", lambda: True)
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.post("/api/projects", json={"repo_url": "https://github.com/acme/rag",
                                      "authorized": True})
    jobs.wait(r.json()["id"])
    return c, r.json()["id"]


def test_project_reports_docker_mode_and_validates_egress(ingested: Any) -> None:
    c, pid = ingested
    a = c.get(f"/api/projects/{pid}").json()["analysis"]
    assert a["execution_mode"] == "docker" and a["run_kind"] == "python-function"
    assert a["mode_reason"] == ""
    bad = c.post(f"/api/projects/{pid}/inputs", json={"egress_allowlist": ["https://x.com"]})
    assert bad.status_code == 422
    ok = c.post(f"/api/projects/{pid}/inputs", json={"egress_allowlist": ["api.openai.com"],
                                                     "app_path": "/ask"})
    assert ok.status_code == 200 and ok.json()["egress_allowlist"] == ["api.openai.com"]
    assert c.post(f"/api/projects/{pid}/inputs", json={"app_path": "/a?b=1"}).status_code == 422


def test_resolver_builds_lazy_managed_target(ingested: Any, monkeypatch: pytest.MonkeyPatch,
                                             ) -> None:
    from qe.ingest import store
    from qe.realeval.resolver import resolve_target

    c, pid = ingested
    c.post(f"/api/projects/{pid}/inputs", json={"egress_allowlist": ["api.openai.com"]})
    monkeypatch.setattr("qe.ingest.target.docker_status", lambda: (True, ""))
    rp = resolve_target(pid)
    assert isinstance(rp.target, dr.ManagedDockerTarget)
    assert rp.target.status.state == "idle"  # nothing built at resolve time
    assert rp.target.egress_summary() == "allowlist: api.openai.com"
    # status transitions are persisted on the project record
    rp.target._set("building", "x", build_log="log")  # type: ignore[attr-defined]
    p = store.get(pid)
    assert p is not None and p.runtime is not None and p.runtime.state == "building"
    assert c.get(f"/api/projects/{pid}").json()["runtime"]["build_log"] == "log"
    monkeypatch.setattr("qe.ingest.target.docker_status", lambda: (False, "docker daemon not running"))
    from qe.realeval.resolver import ResolveError
    with pytest.raises(ResolveError, match="docker daemon not running"):
        resolve_target(pid)


def test_evaluation_job_always_closes_target(tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """prepare() failure and normal completion both end in close() (no leaked containers)."""
    from qe.realeval import jobs as ejobs
    from qe.realeval.resolver import ResolvedProject
    from qe.realeval.runner import Budget, EvalParams, Inputs

    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path / "runs"))
    events: list[str] = []

    class T:
        def prepare(self) -> None:
            events.append("prepare")
            raise RuntimeError("build failed: boom")

        def ask(self, q: str) -> Any:
            raise AssertionError("must not ask after a failed prepare")

        def close(self) -> None:
            events.append("close")

    proj = ResolvedProject(project_id="prj-0123456789", name="n", target=T(),  # type: ignore[arg-type]
                           qa_pairs=[{"question": "q", "reference_answer": "a"}], authorized=True)
    out = ejobs.start("prj-0123456789", EvalParams(generate_questions=False),
                      Inputs(project=proj), Budget(10, 30))
    rec = ejobs.wait(out["id"], 20)
    assert rec["state"] == "failed" and "build failed: boom" in rec["error"]
    assert events == ["prepare", "close"]
