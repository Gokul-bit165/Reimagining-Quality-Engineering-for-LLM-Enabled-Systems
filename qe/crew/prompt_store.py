"""Load versioned prompt files and expose their sha256 for ledger events."""

from __future__ import annotations

from pathlib import Path

from qe.core.ids import sha256_hex
from qe.core.schemas import Frozen

PROMPT_DIR = Path(__file__).parent / "prompt_texts_v1"


class Prompt(Frozen):
    name: str  # e.g. "risk_analyst_v1"
    role: str
    text: str
    sha256: str


def load_prompt(name: str, directory: Path = PROMPT_DIR) -> Prompt:
    path = directory / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"prompt file not found: {name}")
    text = path.read_text(encoding="utf-8")
    role = next(
        (ln.split(":", 1)[1].strip() for ln in text.splitlines() if ln.startswith("ROLE:")), name
    )
    return Prompt(name=name, role=role, text=text, sha256=sha256_hex(text))
