"""realeval tests: offline, fakes only, runs written under tmp_path."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FACTS = [f"Zavo{k} costs {100 + k} dollars." for k in range(40)]
DOC = {"name": "pricing.md", "text": " ".join(FACTS)}
QA = [{"question": f"How much does Zavo{k} cost?", "reference_answer": f"{100 + k} dollars"}
      for k in range(40)]


@pytest.fixture(autouse=True)
def _runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("QE_RUNS_DIR", str(tmp_path))
    for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "QE_ALLOW_REAL_LLM"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path
