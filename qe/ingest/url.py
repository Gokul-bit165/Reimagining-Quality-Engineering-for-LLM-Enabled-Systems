"""Strict GitHub URL validation. Everything not matching the allowlist is rejected."""

from __future__ import annotations

import re
from dataclasses import dataclass

from qe.ingest.limits import MAX_URL_LEN

_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,99}$")
_BRANCH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]{0,199}$")
_SEG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._ -]{0,99}$")
_PREFIX = "https://github.com/"


class RepoUrlError(ValueError):
    pass


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    branch: str | None
    subdir: str

    @property
    def clone_url(self) -> str:
        return f"{_PREFIX}{self.owner}/{self.repo}.git"

    @property
    def display_url(self) -> str:
        return f"{_PREFIX}{self.owner}/{self.repo}"


def check_branch(branch: str) -> str:
    if not _BRANCH.match(branch) or ".." in branch or branch.endswith(("/", ".lock")) \
            or "//" in branch or "@{" in branch:
        raise RepoUrlError("invalid branch name")
    return branch


def check_subdir(subdir: str) -> str:
    if subdir == "":
        return ""
    parts = subdir.split("/")
    for p in parts:
        if p in ("", ".", "..") or not _SEG.match(p):
            raise RepoUrlError("invalid subdir")
    return "/".join(parts)


def parse_repo_url(url: str, branch: str | None = None, subdir: str = "") -> RepoRef:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LEN:
        raise RepoUrlError("repo_url must be a non-empty string of reasonable length")
    if not url.startswith(_PREFIX):
        raise RepoUrlError("only https://github.com/<owner>/<repo> URLs are accepted")
    rest = url[len(_PREFIX):]
    if any(c in rest for c in "?#\\%@:") or not rest.isascii() or not rest.isprintable() \
            or " " in rest:
        raise RepoUrlError("URL contains forbidden characters")
    parts = rest.rstrip("/").split("/")
    if len(parts) < 2:
        raise RepoUrlError("URL must include owner and repo")
    owner, repo = parts[0], parts[1]
    repo = repo[:-4] if repo.endswith(".git") else repo
    if not _OWNER.match(owner) or not _REPO.match(repo) or repo in (".", ".."):
        raise RepoUrlError("invalid owner or repo name")
    url_branch: str | None = None
    url_subdir = ""
    if len(parts) > 2:
        if parts[2] != "tree" or len(parts) < 4 or repo.endswith(".git"):
            raise RepoUrlError("only /tree/<branch>[/<subdir>] paths are accepted")
        rest_parts = parts[3:]
        if rest_parts[:2] == ["refs", "heads"]:
            rest_parts = rest_parts[2:]
        if not rest_parts:
            raise RepoUrlError("branch missing after /tree/")
        url_branch = check_branch(rest_parts[0])
        url_subdir = check_subdir("/".join(rest_parts[1:]))
    final_branch = check_branch(branch) if branch else url_branch
    final_subdir = check_subdir(subdir) if subdir else url_subdir
    return RepoRef(owner=owner, repo=repo, branch=final_branch, subdir=final_subdir)
