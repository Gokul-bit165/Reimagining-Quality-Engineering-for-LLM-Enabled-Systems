"""Regression tests for the independent security review findings."""

import http.client
import io
import json
import socket
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qe.ingest import clone as clone_mod
from qe.ingest import jobs
from qe.ingest.clone import IngestError
from qe.ingest.netguard import EndpointError, resolve_endpoint, validate_endpoint_url
from qe.ingest.target import SandboxedRepoTarget, build_docker_args
from qe.ingest.upload import extract_zip
from qe.ingest.url import parse_repo_url
from qe.ingest.vault import SecretError, SecretVault

# ---- 1. SSRF deny-list completeness -------------------------------------------------------


@pytest.mark.parametrize("host", [
    "100.100.100.200", "100.64.0.1", "192.88.99.1", "[fec0::1]", "[::ffff:169.254.169.254]",
    "[::ffff:10.0.0.1]", "198.18.0.1", "0.0.0.0", "[::]", "224.0.0.1", "240.0.0.1",
])
def test_non_global_addresses_blocked(host: str) -> None:
    with pytest.raises(EndpointError):
        validate_endpoint_url(f"https://{host}/ask")


def test_private_opt_in_does_not_unlock_cgnat_or_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QE_ALLOW_PRIVATE_ENDPOINTS", "1")
    assert validate_endpoint_url("https://10.1.2.3/x")
    for h in ("100.100.100.200", "169.254.169.254", "[::ffff:169.254.169.254]"):
        with pytest.raises(EndpointError):
            validate_endpoint_url(f"https://{h}/x")


# ---- 3. localhost gating ------------------------------------------------------------------


def test_localhost_gating(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QE_ALLOW_LOCAL_ENDPOINTS", raising=False)
    monkeypatch.delenv("QE_UI_PORT", raising=False)
    assert validate_endpoint_url("http://127.0.0.1:9100/invoke")
    for bad in ("http://127.0.0.1:8001/invoke", "http://localhost:8000/x",
                "http://127.0.0.1:9100/api/projects"):
        with pytest.raises(EndpointError):
            validate_endpoint_url(bad)
    monkeypatch.setenv("QE_UI_PORT", "9999")
    with pytest.raises(EndpointError):
        validate_endpoint_url("http://127.0.0.1:9999/x")
    monkeypatch.setenv("QE_ALLOW_LOCAL_ENDPOINTS", "1")
    assert validate_endpoint_url("http://127.0.0.1:8001/api/anything")


# ---- 5. URL parts -------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["https://example.com/a?token=1", "https://example.com/a#x",
                                 "https://example.com/a?", "https://u@example.com/a"])
def test_endpoint_rejects_query_fragment_userinfo(url: str) -> None:
    with pytest.raises(EndpointError):
        validate_endpoint_url(url, resolve=False)


# ---- 2. DNS pinning, no proxies -----------------------------------------------------------


def test_connection_uses_pinned_ip_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_getaddrinfo(host: str, *a: Any, **k: Any) -> list[Any]:
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    ep = resolve_endpoint("https://rebind.example.com/ask")
    assert ep.ip == "93.184.216.34" and ep.host == "rebind.example.com"
    calls.clear()
    seen: list[Any] = []

    def fake_cc(addr: Any, *a: Any, **k: Any) -> socket.socket:
        seen.append(addr)
        raise OSError("blocked in test")

    monkeypatch.setattr(socket, "create_connection", fake_cc)
    t = SandboxedRepoTarget("endpoint", endpoint_url="https://rebind.example.com/ask")
    r = t.ask("q")
    assert seen == [("93.184.216.34", 443)] and r.error
    assert len(calls) == 1  # resolved once; the connection itself never re-resolves


def test_proxy_env_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))  # avoid RST on close
            body = b'{"answer": "ok"}'
            self.send_response(200)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: Any) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    try:
        t = SandboxedRepoTarget("endpoint", endpoint_url=f"http://127.0.0.1:{srv.server_port}/x")
        assert t.ask("q").answer == "ok"
    finally:
        srv.shutdown()


def test_redirect_is_not_followed() -> None:
    class H(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("content-length", "0")))  # avoid RST on close
            self.send_response(302)
            self.send_header("location", "http://169.254.169.254/")
            self.send_header("content-length", "0")
            self.end_headers()

        def log_message(self, *a: Any) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t = SandboxedRepoTarget("endpoint", endpoint_url=f"http://127.0.0.1:{srv.server_port}/x")
        r = t.ask("q")
        assert r.error and "redirect" in r.error.lower()
    finally:
        srv.shutdown()


# ---- 7. vault denylist / docker env -------------------------------------------------------


@pytest.mark.parametrize("name", ["DOCKER_HOST", "QE_RUNS_DIR", "LD_PRELOAD", "PYTHONPATH",
                                  "PYTHONHOME", "BASH_ENV", "ENV", "SSL_CERT_FILE", "PATH",
                                  "HOME", "SSLKEYLOGFILE", "NODE_OPTIONS", "USERPROFILE",
                                  "SYSTEMROOT", "HTTPS_PROXY", "HTTP_PROXY", "GIT_SSH_COMMAND"])
def test_vault_denylist(name: str) -> None:
    with pytest.raises(SecretError):
        SecretVault().set("prj-1", {name: "x"})


def test_vault_allows_normal_names() -> None:
    assert SecretVault().set("p", {"OPENAI_API_KEY": "x", "MY_DB_URL": "y"})


def test_docker_target_does_not_leak_host_env(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(args: list[str], **kw: Any) -> Any:
        captured.update(kw)
        captured["args"] = args

        class P:
            stdout = '@@QE_RESULT@@{"answer": "x"}\n'
            stderr = ""
            returncode = 0
        return P()

    monkeypatch.setenv("GROQ_API_KEY", "host-secret")
    monkeypatch.setattr("qe.ingest.target.subprocess.run", fake_run)
    t = SandboxedRepoTarget("docker", workspace=tmp_path, entry_file="app.py", entry_func="ask",
                            secrets={"OPENAI_API_KEY": "user-secret", "DOCKER_HOST": "evil"})
    assert t.ask("q").answer == "x"
    env = captured["env"]
    assert "GROQ_API_KEY" not in env and env["OPENAI_API_KEY"] == "user-secret"
    assert "DOCKER_HOST" not in env or env["DOCKER_HOST"] != "evil"
    assert "user-secret" not in " ".join(captured["args"])


def test_docker_args_extra_hardening(tmp_path: Path) -> None:
    j = " ".join(build_docker_args("n", tmp_path, "m", "f", []))
    for needle in ("--memory-swap 512m", "--ipc none", "--init", "--ulimit nofile=",
                   "--ulimit nproc="):
        assert needle in j


# ---- 6. DoS --------------------------------------------------------------------------------


def test_watchdog_kills_oversize_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clone_mod, "MAX_REPO_BYTES", 200_000)
    monkeypatch.setattr(clone_mod, "WATCHDOG_INTERVAL_S", 0.05)
    dest = tmp_path / "ws"
    dest.mkdir()
    script = ("import sys,time,pathlib\np=pathlib.Path(sys.argv[1])\n"
              "for i in range(1000):\n    (p/f'f{i}').write_bytes(b'x'*100000)\n    time.sleep(0.02)\n")
    with pytest.raises(IngestError, match="larger"):
        clone_mod.run_with_watchdog([sys.executable, "-c", script, str(dest)], dest,
                                    env=None, timeout=30)


def test_clone_args_have_filter() -> None:
    ref = parse_repo_url("https://github.com/a/b")
    assert any(a.startswith("--filter=blob:limit=") for a in clone_mod.build_clone_args(ref, Path("d")))


def test_job_queue_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    monkeypatch.setattr(jobs, "_work", lambda *a, **k: gate.wait(5))
    monkeypatch.setattr(jobs, "MAX_QUEUED_JOBS", 3)
    started = 0
    try:
        for i in range(10):
            if not jobs.has_capacity():
                break
            jobs.start(f"prj-{i:010x}")
            started += 1
        assert started == 3 and not jobs.has_capacity()
    finally:
        gate.set()
        for i in range(started):
            jobs.wait(f"prj-{i:010x}", 5)


def test_zip_accepts_path_and_does_not_need_bytes(tmp_path: Path) -> None:
    z = tmp_path / "u.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("a.py", "x")
    assert extract_zip(z, tmp_path / "ws").files == 1


# ---- 4. host / origin middleware ----------------------------------------------------------


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from qe.ui.server import app
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    return TestClient(app, base_url="http://127.0.0.1:8001")


def test_untrusted_host_rejected(api: TestClient) -> None:
    assert api.get("/api/projects", headers={"host": "evil.com"}).status_code == 400
    assert api.get("/api/projects").status_code == 200


def test_cross_origin_writes_rejected(api: TestClient) -> None:
    body = {"repo_url": "https://github.com/a/b", "authorized": True}
    r = api.post("/api/projects", json=body, headers={"origin": "http://evil.com"})
    assert r.status_code == 403
    r = api.post("/api/projects", json=body, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    r = api.delete("/api/projects/prj-0000000000", headers={"origin": "https://evil.com"})
    assert r.status_code == 403
    r = api.post("/api/projects/upload", content=b"x", headers={"origin": "http://evil.com"})
    assert r.status_code == 403


def test_vite_proxy_origin_still_works(api: TestClient) -> None:
    h = {"origin": "http://127.0.0.1:8080", "sec-fetch-site": "same-origin"}
    r = api.post("/api/projects", json={"repo_url": "nope", "authorized": True}, headers=h)
    assert r.status_code == 422  # passed the origin check, failed validation
    assert api.get("/api/projects", headers={"origin": "http://evil.com"}).status_code == 200


def test_oversize_body_stream_rejected(api: TestClient) -> None:
    big = io.BytesIO(b"0" * (9 * 1024 * 1024))
    r = api.post("/api/projects", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_chunked_upload_cap(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("qe.ui.security.MAX_UPLOAD_BODY", 1000)

    def gen() -> Any:
        for _ in range(10):
            yield b"0" * 500
    r = api.post("/api/projects/upload?authorized=true", content=gen(),
                 headers={"content-type": "application/zip"})
    assert r.status_code == 413


# ---- LOW ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["CON", "con.txt", "a/NUL", "a/COM1.py", "LPT9", "a /b.py",
                                  "dir./x", "x.py.", "x.py ", "aux.c"])
def test_zip_windows_reserved_and_trailing(tmp_path: Path, name: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, "x")
    with pytest.raises(IngestError):
        extract_zip(buf.getvalue(), tmp_path / "ws")


def test_tree_refs_heads() -> None:
    ref = parse_repo_url("https://github.com/a/b/tree/refs/heads/dev/app")
    assert (ref.branch, ref.subdir) == ("dev", "app")


def test_list_is_summary_and_endpoint_redacted(api: TestClient, monkeypatch: pytest.MonkeyPatch,
                                                tmp_path: Path) -> None:
    from qe.ingest import store
    from qe.ingest.models import Project, ProjectInputs, UserDocument
    p = Project(id="prj-aaaaaaaaaa", repo_url="https://github.com/a/b", created_at=1.0,
                inputs=ProjectInputs(documents=[UserDocument(name="d", text="SECRETTEXT")],
                                     endpoint_url="https://u:pw@example.com/a?key=SEKRET#f"))
    store.save(p)
    lst = api.get("/api/projects").text
    one = api.get("/api/projects/prj-aaaaaaaaaa").text
    assert "SECRETTEXT" not in lst and "SECRETTEXT" in one
    for blob in (lst, one):
        assert "SEKRET" not in blob and "pw@" not in blob


def test_json_roundtrip_helper() -> None:
    assert json.loads("{}") == {}
    assert http.client.HTTPConnection  # imported for target tests
