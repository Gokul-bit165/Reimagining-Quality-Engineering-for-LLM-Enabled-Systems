import json
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.core.ledger import SQLiteLedger
from qe.ingest import clone as clone_mod
from qe.ingest import jobs, store
from qe.ingest.target import SandboxedRepoTarget
from qe.ui.routes_projects import router

ROOT = Path(__file__).resolve().parents[2]
GOOD = {"repo_url": "https://github.com/acme/rag", "authorized": True}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from fastapi import FastAPI

    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path / "runs"))

    def fake_clone(ref: Any, dest: Path, token: str | None = None) -> None:
        dest.mkdir(parents=True)
        (dest / "app.py").write_text(
            "import openai, os\nKEY=os.environ['OPENAI_API_KEY']\n"
            "def ask(q):\n    return index.similarity_search(q)\n")
        (dest / "README.md").write_text("# Hello\nDocs about shipping.")
        (dest / "docs").mkdir()
        (dest / "docs" / "faq.md").write_text("FAQ text")

    monkeypatch.setattr(clone_mod, "clone_repo", fake_clone)
    monkeypatch.setattr(jobs, "docker_available", lambda: False)
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)


def _create(c: TestClient, **extra: Any) -> str:
    r = c.post("/api/projects", json={**GOOD, **extra})
    assert r.status_code == 202, r.text
    pid = r.json()["id"]
    jobs.wait(pid)
    return pid


def test_full_flow(client: TestClient) -> None:
    pid = _create(client)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["state"] == "ready" and p["authorized"] is True and p["authorized_at"]
    a = p["analysis"]
    assert a["execution_mode"] == "static_only" and a["executed"] is False
    assert a["summary"] and a["next_steps"] and "OPENAI_API_KEY=" in a["env_template"]
    assert "OPENAI_API_KEY" in a["env_vars"]
    for k in ("framework", "language", "entrypoints", "retriever", "vector_store",
              "llm_providers", "prompts", "doc_sources", "chunking", "risk_flags"):
        assert k in a
    assert any(f["id"] == "no-top-k-bound" for f in a["risk_flags"])
    assert [x["id"] for x in client.get("/api/projects").json()] == [pid]


def test_authorization_required_and_audited(client: TestClient, tmp_path: Path) -> None:
    assert client.post("/api/projects", json={"repo_url": GOOD["repo_url"]}).status_code == 422
    r = client.post("/api/projects", json={**GOOD, "authorized": False})
    assert r.status_code == 422
    pid = _create(client)
    ledger = SQLiteLedger(tmp_path / "runs" / "projects" / "audit.sqlite")
    ev = [e.event for e in ledger.entries() if e.event.key == f"authorization:{pid}"]
    assert ev and ev[0].payload["authorized"] is True
    assert ledger.verify().ok
    ledger.close()


@pytest.mark.parametrize("bad", [
    "http://github.com/a/b", "https://evil.com/a/b", "git@github.com:a/b.git",
    "https://github.com/-x/b", "https://u:p@github.com/a/b", "file:///etc",
])
def test_malicious_urls_rejected(client: TestClient, bad: str) -> None:
    assert client.post("/api/projects", json={"repo_url": bad, "authorized": True}
                       ).status_code == 422


def test_bad_endpoint_rejected(client: TestClient) -> None:
    r = client.post("/api/projects", json={**GOOD, "endpoint_url": "http://169.254.169.254/"})
    assert r.status_code == 422


def test_clone_failure_marks_failed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(ref: Any, dest: Path, token: str | None = None) -> None:
        raise clone_mod.IngestError("git clone failed: not found")

    monkeypatch.setattr(clone_mod, "clone_repo", boom)
    pid = _create(client)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["state"] == "failed" and "not found" in p["error"] and p["analysis"] is None


def test_inputs_roundtrip_and_limits(client: TestClient) -> None:
    pid = _create(client)
    body = {"documents": [{"name": "a.txt", "text": "hello"}],
            "qa_pairs": [{"question": "q?", "reference_answer": "a"}, {"question": "q2"}],
            "notes": "n", "risk_focus": ["hallucination"]}
    assert client.post(f"/api/projects/{pid}/inputs", json=body).status_code == 200
    got = client.get(f"/api/projects/{pid}").json()["inputs"]
    assert got["documents"][0]["name"] == "a.txt" and len(got["qa_pairs"]) == 2
    client.post(f"/api/projects/{pid}/inputs", json={"notes": "only notes"})
    got = client.get(f"/api/projects/{pid}/inputs").json()
    assert got["notes"] == "only notes" and got["documents"]  # untouched fields persist
    too_big = {"documents": [{"name": "x", "text": "a" * 300_000}]}
    assert client.post(f"/api/projects/{pid}/inputs", json=too_big).status_code == 422
    bad_name = {"documents": [{"name": "../../x", "text": "a"}]}
    assert client.post(f"/api/projects/{pid}/inputs", json=bad_name).status_code == 422
    assert client.post(f"/api/projects/{pid}/inputs",
                       json={"endpoint_url": "https://10.0.0.1/x"}).status_code == 422
    assert client.post("/api/projects/prj-0000000000/inputs", json={}).status_code == 404


def test_endpoint_input_switches_mode(client: TestClient) -> None:
    pid = _create(client)
    client.post(f"/api/projects/{pid}/inputs", json={"endpoint_url": "http://localhost:8101/ask"})
    assert client.get(f"/api/projects/{pid}").json()["analysis"]["execution_mode"] == "endpoint"


def test_suggested_inputs(client: TestClient) -> None:
    pid = _create(client)
    docs = client.get(f"/api/projects/{pid}/suggested-inputs").json()["documents"]
    assert {d["name"] for d in docs} == {"README.md", "docs/faq.md"}


def test_secrets_memory_only(client: TestClient, tmp_path: Path) -> None:
    pid = _create(client)
    assert client.get(f"/api/projects/{pid}/secrets").json()["missing"] == ["OPENAI_API_KEY"]
    r = client.post(f"/api/projects/{pid}/secrets", json={"values": {"OPENAI_API_KEY": "sk-SECRET"}})
    assert r.json()["names"] == ["OPENAI_API_KEY"] and "sk-SECRET" not in r.text
    assert "sk-SECRET" not in client.get(f"/api/projects/{pid}").text
    assert client.get(f"/api/projects/{pid}/secrets").json()["missing"] == []
    for f in (tmp_path / "runs").rglob("*"):
        if f.is_file():
            assert b"sk-SECRET" not in f.read_bytes()
    assert client.post(f"/api/projects/{pid}/secrets", json={"values": {"bad": "x"}}
                       ).status_code == 422


def test_delete_removes_workspace(client: TestClient, tmp_path: Path) -> None:
    pid = _create(client)
    ws = tmp_path / "runs" / "workspaces" / pid
    assert ws.exists()
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert not ws.exists() and client.get(f"/api/projects/{pid}").status_code == 404
    assert client.get("/api/projects/../../etc").status_code in (404, 405)
    assert store.get("..") is None


def test_upload_raw_zip(client: TestClient) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app.py", "import openai\ndef ask(q):\n    return q\n")
        z.writestr("README.md", "hi")
    h = {"content-type": "application/zip"}
    assert client.post("/api/projects/upload", content=buf.getvalue(), headers=h
                       ).status_code == 422  # not authorized
    r = client.post("/api/projects/upload?authorized=true&name=my%20app.zip",
                    content=buf.getvalue(), headers=h)
    assert r.status_code == 202
    jobs.wait(r.json()["id"])
    p = client.get(f"/api/projects/{r.json()['id']}").json()
    assert p["state"] == "ready" and p["repo_url"] == "upload://my_app.zip"
    assert client.post("/api/projects/upload?authorized=true", content=b"nope",
                       headers=h).status_code == 422


def test_upload_zip_slip_fails_project(client: TestClient) -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../evil.py", "x")
    r = client.post("/api/projects/upload?authorized=true", content=buf.getvalue(),
                    headers={"content-type": "application/zip"})
    jobs.wait(r.json()["id"])
    assert client.get(f"/api/projects/{r.json()['id']}").json()["state"] == "failed"


def test_real_endpoint_target_roundtrip() -> None:
    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            n = int(self.headers["content-length"])
            q = json.loads(self.rfile.read(n))["question"]
            body = json.dumps({"answer": f"echo {q}", "sources": ["ctx"]}).encode()
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: Any) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t = SandboxedRepoTarget("endpoint", endpoint_url=f"http://127.0.0.1:{srv.server_port}/ask")
        r = t.ask("hi")
        assert r.error is None and r.answer == "echo hi" and r.contexts == ["ctx"]
    finally:
        srv.shutdown()


def test_fixture_repo_via_git_init_and_analyzer(tmp_path: Path) -> None:
    """A real git repo of sandbox_apps/rag, analysed through sanitize+analyze (no network)."""
    import shutil

    from qe.ingest.analyzer import analyze_workspace

    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "sandbox_apps" / "rag", repo, ignore=shutil.ignore_patterns("__pycache__"))
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    stats = clone_mod.sanitize_workspace(repo)
    assert stats.files > 3 and not (repo / ".git").exists()
    assert analyze_workspace(repo).retriever == "bm25"


@pytest.mark.skip(reason="network: set manually to exercise a real clone")
def test_real_clone_network(tmp_path: Path) -> None:
    from qe.ingest.url import parse_repo_url

    clone_mod.clone_repo(parse_repo_url("https://github.com/octocat/Hello-World"), tmp_path / "w")
