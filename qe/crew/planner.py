"""Budgeted planner: deterministic round-robin over policy-ranked risks (no invented weights)."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from qe.risk.register import RankedRisk


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)
    allocation: tuple[tuple[str, int], ...]  # (risk_id, n_tests), rank order
    unplanned: tuple[str, ...]  # got nothing: reported as UNCOVERED, never dropped


def plan(ranked: Sequence[RankedRisk], budget: int) -> Plan:
    if budget < 0:
        raise ValueError("budget must be >= 0")
    ids = [r.proposal.risk_id for r in ranked]
    counts = dict.fromkeys(ids, 0)
    for i in range(budget):
        if not ids:
            break
        counts[ids[i % len(ids)]] += 1
    return Plan(
        allocation=tuple((i, counts[i]) for i in ids if counts[i] > 0),
        unplanned=tuple(i for i in ids if counts[i] == 0),
    )
