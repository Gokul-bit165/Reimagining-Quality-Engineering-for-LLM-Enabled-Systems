import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from qe.ingest import clone as c
from qe.ingest.url import parse_repo_url

REF = parse_repo_url("https://github.com/acme/rag", branch="main")


def test_clone_args_are_hardened_list() -> None:
    args = c.build_clone_args(REF, Path("dest"))
    assert isinstance(args, list)
    for flag in ("--depth", "--no-tags", "--single-branch", "--no-recurse-submodules"):
        assert flag in args
    assert "protocol.file.allow=never" in args
    assert any(a.startswith("core.hooksPath=") for a in args)
    assert args[-3:] == ["--", "https://github.com/acme/rag.git", "dest"]


def test_env_noninteractive_and_token_not_in_args() -> None:
    env = c.build_env("tok123")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "tok123" not in " ".join(c.build_clone_args(REF, Path("d")))
    assert "GIT_CONFIG_COUNT" not in c.build_env(None)


def test_clone_uses_runner_without_shell(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def fake(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kw)
        dest = Path(args[-1])
        dest.mkdir()
        (dest / ".git").mkdir()
        (dest / ".git" / "config").write_text("x")
        (dest / "a.py").write_text("print(1)")
        return subprocess.CompletedProcess(args, 0, "", "")

    stats = c.clone_repo(REF, tmp_path / "ws", runner=fake)
    assert seen["shell"] is False and seen["timeout"] == c.CLONE_TIMEOUT_S
    assert stats.files == 1 and not (tmp_path / "ws" / ".git").exists()


def test_clone_failure_scrubs_token_and_cleans(tmp_path: Path) -> None:
    def fake(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        Path(args[-1]).mkdir()
        return subprocess.CompletedProcess(args, 128, "", "fatal: bad tok123 here")

    with pytest.raises(c.IngestError) as ei:
        c.clone_repo(REF, tmp_path / "ws", token="tok123", runner=fake)
    assert "tok123" not in str(ei.value) and not (tmp_path / "ws").exists()


def test_clone_timeout(tmp_path: Path) -> None:
    def fake(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, 1)

    with pytest.raises(c.IngestError, match="timed out"):
        c.clone_repo(REF, tmp_path / "ws", runner=fake)


def test_symlink_escape_removed(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "ok.py").write_text("x")
    try:
        os.symlink(secret, ws / "link.txt")
        os.symlink(tmp_path, ws / "dirlink", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this OS account")
    stats = c.sanitize_workspace(ws)
    assert stats.symlinks_removed == 2 and secret.exists()
    assert [p.name for p in ws.iterdir()] == ["ok.py"]


def test_oversize_file_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "MAX_REPO_FILES", 3)
    for i in range(5):
        (tmp_path / f"f{i}").write_text("x")
    with pytest.raises(c.IngestError, match="files"):
        c.sanitize_workspace(tmp_path)


def test_oversize_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "MAX_REPO_BYTES", 10)
    (tmp_path / "big").write_text("x" * 100)
    with pytest.raises(c.IngestError, match="larger"):
        c.sanitize_workspace(tmp_path)


def test_oversize_clone_is_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(c, "MAX_REPO_BYTES", 10)

    def fake(args: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        Path(args[-1]).mkdir()
        (Path(args[-1]) / "big").write_text("x" * 100)
        return subprocess.CompletedProcess(args, 0, "", "")

    with pytest.raises(c.IngestError):
        c.clone_repo(REF, tmp_path / "ws", runner=fake)
    assert not (tmp_path / "ws").exists()


def test_resolve_subdir(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    assert c.resolve_subdir(tmp_path, "app").name == "app"
    assert c.resolve_subdir(tmp_path, "") == tmp_path.resolve()
    with pytest.raises(c.IngestError):
        c.resolve_subdir(tmp_path, "nope")
