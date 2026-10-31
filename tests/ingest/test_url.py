import pytest

from qe.ingest.url import RepoUrlError, parse_repo_url


def test_plain_url() -> None:
    ref = parse_repo_url("https://github.com/acme/rag-app")
    assert (ref.owner, ref.repo, ref.branch, ref.subdir) == ("acme", "rag-app", None, "")
    assert ref.clone_url == "https://github.com/acme/rag-app.git"


def test_dot_git_and_tree() -> None:
    assert parse_repo_url("https://github.com/acme/rag.git").repo == "rag"
    ref = parse_repo_url("https://github.com/acme/rag/tree/dev/services/api")
    assert (ref.branch, ref.subdir) == ("dev", "services/api")


def test_explicit_branch_subdir_override() -> None:
    ref = parse_repo_url("https://github.com/acme/rag", branch="main", subdir="app")
    assert (ref.branch, ref.subdir) == ("main", "app")


@pytest.mark.parametrize("bad", [
    "http://github.com/acme/rag",
    "https://gitlab.com/acme/rag",
    "https://github.com.evil.com/acme/rag",
    "https://evil.com/github.com/acme/rag",
    "git@github.com:acme/rag.git",
    "ssh://git@github.com/acme/rag",
    "file:///etc/passwd",
    "/etc/passwd",
    "https://user:pw@github.com/acme/rag",
    "https://user@github.com/acme/rag",
    "https://github.com:443/acme/rag",
    "https://github.com/-evil/rag",
    "https://github.com/acme/--upload-pack=x",
    "https://github.com/acme/-rag",
    "https://github.com/acme/../rag",
    "https://github.com/acme/rag/tree/dev/../../etc",
    "https://github.com/acme/rag/tree/-x/app",
    "https://github.com/acme",
    "https://github.com/acme/rag/blob/main/x.py",
    "https://github.com/acme/rag?x=1",
    "https://github.com/acme/rag#frag",
    "https://github.com/acme/rag extra",
    "https://github.com/acme/rag\n--upload-pack=x",
    "",
    "-c core.sshCommand=x",
    "https://github.com/ac me/rag",
    "https://github.com/acme/rag/tree/dev/%2e%2e/x",
    "https://github.com/acme/rag/tree/dev/a\b",
])
def test_rejects_malicious(bad: str) -> None:
    with pytest.raises(RepoUrlError):
        parse_repo_url(bad)


@pytest.mark.parametrize(("branch", "subdir"), [
    ("-x", ""), ("a..b", ""), ("a b", ""), ("x;y", ""), ("", "../x"), ("", "/abs"),
    ("", "a/../b"), ("", "a\b"), ("", "C:/x"), ("main", "-x"),
])
def test_rejects_bad_branch_subdir(branch: str, subdir: str) -> None:
    with pytest.raises(RepoUrlError):
        parse_repo_url("https://github.com/acme/rag", branch=branch or None, subdir=subdir)
