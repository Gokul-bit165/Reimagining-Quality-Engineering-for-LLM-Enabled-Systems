"""T2.4 coverage report and estimate-event schemas consumed by the viewer.

Both estimates are written as ESTIMATE_COMPUTED events by deterministic code:

* kind "risk_coverage": risk-register cells vs executed VALID tests, explicit UNCOVERED cells.
  Structural (app-model edge) coverage is LOGGED ONLY (H3: no claim that it predicts anything).
* kind "invalid_test_rate": exact interval from human-labelled audit rows.

Each payload also carries `metric` (same value as `kind`) and viewer-style keys (`cells[].cell,
covered, n_tests`; `k`, `n`, `point`, `lower`, `upper`) so existing readers keep working.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import Field

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ids import content_id
from qe.core.ledger import Entry, Ledger
from qe.core.schemas import Frozen, RunRecord
from qe.model.builder import AppModel, run_edges
from qe.risk.register import RiskRegister

PRODUCER = "p3_coverage"
STRUCTURAL_KINDS = ("retrieval", "tool_call", "handoff")
STRUCTURAL_NOTE = "logged only (H3): structural coverage is not claimed to predict defect finding"


class CellCoverage(Frozen):
    cell_id: str
    cell: str  # same as cell_id (viewer-style key)
    status: Literal["COVERED", "UNCOVERED"]
    covered: bool
    n_tests: int  # executed valid tests in this cell
    test_ids: tuple[str, ...]


class KindCoverage(Frozen):
    kind: str
    hit: int
    total: int


class RiskCoverageEstimate(Frozen):
    kind: Literal["risk_coverage"] = "risk_coverage"
    metric: Literal["risk_coverage"] = "risk_coverage"
    register_id: str
    n_cells: int
    n_covered: int
    n_uncovered: int
    uncovered_cells: tuple[str, ...]
    cells: tuple[CellCoverage, ...]
    structural: tuple[KindCoverage, ...] = ()
    structural_note: str = STRUCTURAL_NOTE


class InvalidTestRateEstimate(Frozen):
    kind: Literal["invalid_test_rate"] = "invalid_test_rate"
    metric: Literal["invalid_test_rate"] = "invalid_test_rate"
    k: int  # tests labelled invalid
    n: int  # tests labelled (valid + invalid + ambiguous)
    n_ambiguous: int
    point: float = Field(allow_inf_nan=False)
    lower: float = Field(allow_inf_nan=False)
    upper: float = Field(allow_inf_nan=False)
    confidence: float
    method: str = "clopper_pearson"
    strata: dict[str, dict[str, int]]  # stratum -> {n, k}
    sampling: str
    synthetic: bool  # True when labels came from the synthetic auto-labeller (pipeline test only)


def compute_risk_coverage(
    register: RiskRegister,
    test_cells: Mapping[str, str | None],
    validity: Mapping[str, str],
    executed: Iterable[str],
    model: AppModel | None = None,
    valid_runs: Iterable[RunRecord] = (),
) -> RiskCoverageEstimate:
    """A cell is COVERED iff >=1 test assigned to it is valid AND was executed."""
    executed_set = set(executed)
    by_cell: dict[str, list[str]] = {c: [] for c in register.cell_ids()}
    for tid, cell in sorted(test_cells.items()):
        if cell in by_cell and validity.get(tid) == "valid" and tid in executed_set:
            by_cell[cell].append(tid)
    cells = tuple(
        CellCoverage(
            cell_id=c, cell=c, status="COVERED" if ids else "UNCOVERED", covered=bool(ids),
            n_tests=len(ids), test_ids=tuple(ids),
        )
        for c, ids in sorted(by_cell.items())
    )
    uncovered = tuple(c.cell_id for c in cells if not c.covered)
    return RiskCoverageEstimate(
        register_id=register.register_id, n_cells=len(cells),
        n_covered=len(cells) - len(uncovered), n_uncovered=len(uncovered),
        uncovered_cells=uncovered, cells=cells,
        structural=structural_coverage(model, valid_runs) if model else (),
    )


def structural_coverage(model: AppModel, runs: Iterable[RunRecord]) -> tuple[KindCoverage, ...]:
    """Fraction of model edges (retrieval / tool_call / handoff) traversed by the given runs."""
    hit: set[tuple[str, str, str]] = set()
    for run in runs:
        hit |= run_edges(run.spans)
    out = []
    for kind in STRUCTURAL_KINDS:
        edges = {(e.src, e.dst, e.kind) for e in model.edges if e.kind == kind}
        out.append(KindCoverage(kind=kind, hit=len(edges & hit), total=len(edges)))
    return tuple(out)


def coverage_from_ledger(
    ledger: Ledger, register: RiskRegister, model: AppModel | None = None
) -> RiskCoverageEstimate:
    test_cells: dict[str, str | None] = {}
    validity: dict[str, str] = {}
    runs: dict[str, list[RunRecord]] = {}
    for e in ledger.entries():
        p, t = e.event.payload, e.event.type
        if t is EventType.TEST_DRAFTED:
            case = p["test_case"]
            test_cells[case["id"]] = case.get("risk_cell")
        elif t is EventType.VALIDITY_VERDICT:
            validity[p["test_id"]] = p["validity"]  # latest verdict wins
        elif t is EventType.RUN_RECORDED:
            run = RunRecord.model_validate(p)
            runs.setdefault(run.test_case_id, []).append(run)
    valid_runs = [r for tid, rs in runs.items() if validity.get(tid) == "valid" for r in rs]
    return compute_risk_coverage(register, test_cells, validity, runs, model, valid_runs)


def record_estimate(ledger: Ledger, estimate: Frozen) -> Entry:
    """Append an estimate as a deterministic ESTIMATE_COMPUTED event (idempotent by content)."""
    payload = estimate.model_dump(mode="json")
    key = f"estimate:{payload['kind']}:{content_id(payload)[:24]}"
    existing = ledger.find_by_key(key)
    if existing is not None:
        return existing
    return ledger.append(
        Event(key=key, type=EventType.ESTIMATE_COMPUTED, producer=PRODUCER,
              producer_kind=ProducerKind.DETERMINISTIC, payload=payload)
    )
