"""Risk taxonomies loaded from fetched primary-source files (R1: cite, do not paraphrase)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from qe.core.ids import sha256_hex

_DATA = Path(__file__).parent / "data"


class TaxonomyEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    title: str
    url: str


class Taxonomy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    taxonomy: str
    title: str
    source_url: str
    fetched: str
    status: str
    note: str
    entries: tuple[TaxonomyEntry, ...]
    sha256: str = ""

    def ids(self) -> frozenset[str]:
        return frozenset(e.id for e in self.entries)


def load_taxonomy(name: str) -> Taxonomy:
    path = _DATA / f"{name}.json"
    if not path.is_file() or path.resolve().parent != _DATA.resolve():
        raise KeyError(f"unknown taxonomy: {name}")
    raw = path.read_text(encoding="utf-8")
    return Taxonomy.model_validate({**json.loads(raw), "sha256": sha256_hex(raw)})
