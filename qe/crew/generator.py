"""GeneratorPort implementation for RAG scenarios. Needs no ragas; see ragas_adapter for that."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from qe.core.schemas import TestCase
from qe.crew.authors import AuthorSlot, author_scenarios
from qe.ports import GenerationSpec


class RagScenarioGenerator:
    """Produces DRAFT test cases from source docs via the Scenario Authors."""

    def __init__(
        self, slots: Sequence[AuthorSlot], docs: Mapping[str, str], risk_cell: str = "unassigned"
    ) -> None:
        self._slots = tuple(slots)
        self._docs = dict(docs)
        self._cell = risk_cell

    async def generate(self, spec: GenerationSpec) -> tuple[TestCase, ...]:
        unknown = [s for s in spec.source_ids if s not in self._docs]
        if unknown:
            raise KeyError(f"unknown source ids: {unknown}")
        docs = {s: self._docs[s] for s in (spec.source_ids or tuple(sorted(self._docs)))}
        per_slot = -(-spec.n // len(self._slots))  # ceil
        drafts = author_scenarios(self._slots, self._cell, docs, per_slot)
        return tuple(d.case for d in drafts[: spec.n])
