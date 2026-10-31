"""Load risk taxonomies from data files (T2.2). External lists are UNVERIFIED transcriptions."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import model_validator

from qe.core.schemas import Frozen

TAXONOMY_DIR = Path(__file__).parent / "taxonomy"


class Category(Frozen):
    id: str
    name: str
    description: str


class Taxonomy(Frozen):
    name: str
    label: str
    verified: bool
    categories: tuple[Category, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Taxonomy:
        ids = [c.id for c in self.categories]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate category ids in {self.name}")
        return self

    def ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.categories)


def load_taxonomy(name: str, directory: Path = TAXONOMY_DIR) -> Taxonomy:
    path = directory / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"taxonomy not found: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Taxonomy(
        name=str(data["name"]),
        label=str(data["label"]),
        verified=bool(data.get("verified", False)),
        categories=tuple(Category(**c) for c in data["categories"]),
    )


def load_all(directory: Path = TAXONOMY_DIR) -> tuple[Taxonomy, ...]:
    return tuple(load_taxonomy(p.stem, directory) for p in sorted(directory.glob("*.yaml")))


def allowed_ids(taxonomies: tuple[Taxonomy, ...]) -> frozenset[str]:
    out: frozenset[str] = frozenset()
    for t in taxonomies:
        out |= t.ids()
    return out
