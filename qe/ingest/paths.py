"""Filesystem layout for projects (all under the gitignored runs/ directory)."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = re.compile(r"^prj-[0-9a-f]{10}$")


def runs_root() -> Path:
    return Path(os.environ.get("QE_RUNS_DIR", ROOT / "runs"))


def projects_dir() -> Path:
    return runs_root() / "projects"


def workspace_dir(project_id: str) -> Path:
    if not PROJECT_ID.match(project_id):
        raise ValueError("invalid project id")
    return runs_root() / "workspaces" / project_id
