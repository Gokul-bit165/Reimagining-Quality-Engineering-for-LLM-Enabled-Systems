import io
import stat
import zipfile
from pathlib import Path

import pytest

from qe.ingest.clone import IngestError
from qe.ingest.netguard import EndpointError, validate_endpoint_url
from qe.ingest.target import (
    SandboxedRepoTarget,
    build_docker_args,
    parse_app_response,
)
from qe.ingest.upload import extract_zip
from qe.ingest.vault import SecretError, SecretVault
from qe.realeval.target import RagTarget


@pytest.mark.parametrize("url", [
    "http://example.com/ask", "https://169.254.169.254/latest/meta-data",
    "http://169.254.169.254/", "https://[fd00:ec2::254]/", "https://10.0.0.5/ask",
    "https://192.168.1.2/ask", "https://user:pw@example.com/",
    "ftp://example.com/", "file:///etc/passwd", "https:///nohost", "", "https://exa mple.com",
    "http://localhost.evil.com/", "http://169.254.169.254:80@localhost/",
])
def test_endpoint_rejected(url: str) -> None:
    with pytest.raises(EndpointError):
        validate_endpoint_url(url)


def test_endpoint_allowed() -> None:
    assert validate_endpoint_url("http://localhost:8101/ask")
    assert validate_endpoint_url("http://127.0.0.1:9/x")
    assert validate_endpoint_url("https://8.8.8.8/ask")
    assert validate_endpoint_url("https://example.com/ask", resolve=False)


def test_private_needs_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QE_ALLOW_PRIVATE_ENDPOINTS", "1")
    assert validate_endpoint_url("https://10.1.2.3/ask")
    with pytest.raises(EndpointError):
        validate_endpoint_url("https://169.254.169.254/")


def _zip(entries: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
        if symlink:
            zi = zipfile.ZipInfo(symlink)
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(zi, "/etc/passwd")
    return buf.getvalue()


def test_zip_ok(tmp_path: Path) -> None:
    st = extract_zip(_zip({"a/b.py": b"x", "c.md": b"y"}), tmp_path / "ws")
    assert st.files == 2 and (tmp_path / "ws" / "a" / "b.py").read_text() == "x"


@pytest.mark.parametrize("name", ["../evil.py", "a/../../evil.py", "/abs.py", "C:/x.py",
                                  "..\\evil.py"])
def test_zip_slip_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(IngestError):
        extract_zip(_zip({name: b"x"}), tmp_path / "ws")
    assert not (tmp_path / "ws").exists() and not (tmp_path / "evil.py").exists()


def test_zip_symlink_and_bomb_and_garbage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(IngestError, match="symlink"):
        extract_zip(_zip({"a.py": b"x"}, symlink="link"), tmp_path / "w1")
    monkeypatch.setattr("qe.ingest.upload.MAX_REPO_BYTES", 100)
    with pytest.raises(IngestError, match="size"):
        extract_zip(_zip({"big.txt": b"0" * 10_000}), tmp_path / "w2")
    with pytest.raises(IngestError, match="valid zip"):
        extract_zip(b"not a zip", tmp_path / "w3")


def test_vault_memory_only_and_validation() -> None:
    v = SecretVault()
    assert v.set("prj-1", {"OPENAI_API_KEY": "sk-x"}) == ["OPENAI_API_KEY"]
    assert v.names("prj-1") == ["OPENAI_API_KEY"] and "sk-x" not in repr(v)
    for bad in ({"lower": "x"}, {"PATH": "x"}, {"A": 5}, {"A": "x\x00"}):
        with pytest.raises(SecretError):
            v.set("prj-1", bad)
    v.clear("prj-1")
    assert v.get("prj-1") == {}


def test_static_only_is_explicitly_not_executed() -> None:
    t = SandboxedRepoTarget("static_only")
    assert isinstance(t, RagTarget)
    r = t.ask("q")
    assert r.error and "not executed" in r.error and r.answer == ""


def test_docker_args_locked_down(tmp_path: Path) -> None:
    args = build_docker_args("qe-x", tmp_path, "app.main", "ask", ["OPENAI_API_KEY"])
    joined = " ".join(args)
    for needle in ("--network none", "--read-only", "--cap-drop ALL", "--user 65534:65534",
                   "--memory", "--pids-limit", "no-new-privileges", ":/app:ro"):
        assert needle in joined
    assert "-e OPENAI_API_KEY" in joined and "sk-" not in joined
    assert "--privileged" not in joined


def test_kill_switch() -> None:
    t = SandboxedRepoTarget("static_only")
    t.kill()
    assert "kill switch" in (t.ask("q").error or "")


def test_endpoint_target_blocks_unsafe_and_unreachable() -> None:
    bad = SandboxedRepoTarget("endpoint", endpoint_url="https://169.254.169.254/")
    assert "EndpointError" in (bad.ask("q").error or "")
    none = SandboxedRepoTarget("endpoint")
    assert none.ask("q").error


def test_parse_app_response_shapes() -> None:
    assert parse_app_response("hi") == ("hi", [])
    assert parse_app_response({"answer": "a", "sources": [{"text": "c1"}, "c2"]}) == (
        "a", ["c1", "c2"])
    assert parse_app_response(["a", ["c"]]) == ("a", ["c"])
    assert parse_app_response({"output": "o"}) == ("o", [])
