"""Versioned prompt files (qe/crew/prompts_files/<name>.md); the hash goes into the ledger."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from qe.core.ids import sha256_hex

_DIR = Path(__file__).parent / "prompts_files"
_NAME = re.compile(r"^[a-z_]+$")


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    version: str
    text: str
    sha256: str


def load_prompt(name: str) -> Prompt:
    path = _DIR / f"{name}.md"
    if not _NAME.match(name) or not path.is_file():
        raise KeyError(f"unknown prompt: {name}")
    raw = path.read_text(encoding="utf-8")
    first, _, body = raw.partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"prompt {name} lacks a 'version:' first line")
    return Prompt(
        name=name, version=first.split(":", 1)[1].strip(), text=body, sha256=sha256_hex(raw)
    )
