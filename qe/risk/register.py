"""Risk register: accepted risk proposals as (category x component) cells."""

from __future__ import annotations

from collections.abc import Sequence

from qe.core.ids import content_id
from qe.core.schemas import Frozen


class RiskItem(Frozen):
    category: str
    component: str  # app-model node id or "app"
    rationale: str = ""

    @property
    def cell_id(self) -> str:
        return f"{self.category}@{self.component}"


class RiskRegister(Frozen):
    items: tuple[RiskItem, ...]

    @property
    def register_id(self) -> str:
        return content_id([i.cell_id for i in self.items])[:16]

    def cell_ids(self) -> tuple[str, ...]:
        return tuple(sorted({i.cell_id for i in self.items}))


def build_register(items: Sequence[RiskItem]) -> RiskRegister:
    """Deduplicate by cell id (first rationale wins) and sort deterministically."""
    seen: dict[str, RiskItem] = {}
    for item in items:
        seen.setdefault(item.cell_id, item)
    return RiskRegister(items=tuple(seen[k] for k in sorted(seen)))
