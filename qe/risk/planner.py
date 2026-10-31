"""Deterministic Planner: ranks risk cells and allocates a test budget from a user weights file.

No weights are invented here: a category with no user weight is listed as unweighted, gets no
allocation and is reported, never silently given a default.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import field_validator

from qe.core.schemas import Frozen
from qe.risk.register import RiskRegister


class Weights(Frozen):
    label: str
    example_only: bool = False
    policy_ref: str = ""
    budget_tests: int
    min_per_cell: int = 0
    weights: dict[str, float]

    @field_validator("weights")
    @classmethod
    def _non_negative(cls, v: dict[str, float]) -> dict[str, float]:
        if any(w < 0 for w in v.values()):
            raise ValueError("weights must be non-negative")
        return v

    @field_validator("budget_tests", "min_per_cell")
    @classmethod
    def _non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("must be >= 0")
        return v


def load_weights(path: Path) -> Weights:
    return Weights.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class CellPlan(Frozen):
    cell_id: str
    category: str
    component: str
    weight: float | None  # None = unweighted by the user
    allocated_tests: int


class Plan(Frozen):
    cells: tuple[CellPlan, ...]  # ranked: weight desc, then cell id
    budget_tests: int
    unweighted: tuple[str, ...]
    example_only: bool
    over_budget_by_floor: int = 0  # min_per_cell floors exceeding the budget (reported)


def _largest_remainder(shares: dict[str, float], total: int) -> dict[str, int]:
    alloc = {k: int(s) for k, s in shares.items()}
    leftover = total - sum(alloc.values())
    for k in sorted(shares, key=lambda k: (-(shares[k] - alloc[k]), k))[:leftover]:
        alloc[k] += 1
    return alloc


def plan(register: RiskRegister, w: Weights) -> Plan:
    rows = [(i.cell_id, i.category, i.component, w.weights.get(i.category)) for i in register.items]
    rows.sort(key=lambda r: (-(r[3] if r[3] is not None else -1.0), r[0]))
    weighted = [r for r in rows if r[3] is not None]
    floor_total = w.min_per_cell * len(weighted)
    remaining = max(0, w.budget_tests - floor_total)
    total_weight = sum(r[3] or 0.0 for r in weighted)
    alloc: dict[str, int] = {r[0]: 0 for r in weighted}
    if total_weight > 0 and remaining > 0:
        shares = {r[0]: remaining * (r[3] or 0.0) / total_weight for r in weighted}
        alloc = _largest_remainder(shares, remaining)
    cells = tuple(
        CellPlan(
            cell_id=r[0], category=r[1], component=r[2], weight=r[3],
            allocated_tests=(w.min_per_cell + alloc[r[0]]) if r[3] is not None else 0,
        )
        for r in rows
    )
    return Plan(
        cells=cells, budget_tests=w.budget_tests,
        unweighted=tuple(r[0] for r in rows if r[3] is None),
        example_only=w.example_only,
        over_budget_by_floor=max(0, floor_total - w.budget_tests),
    )
