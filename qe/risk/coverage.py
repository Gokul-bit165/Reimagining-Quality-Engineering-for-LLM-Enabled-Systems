"""Risk-register coverage report (T2.4) incl. UNCOVERED cells.

A cell is a proposed risk (taxonomy id x app component). Statuses:
  COVERED               >= 1 drafted test judged valid by the Skeptic (a proposal, not human truth)
  DRAFTED_NOT_VALIDATED tests exist but none judged valid
  UNCOVERED             no drafted test
Taxonomy ids with no proposed risk are listed as UNASSESSED (never silently "fine").
Structural coverage (nodes/edges of the app model exercised by run traces) is only LOGGED (H3):
nothing here claims it predicts defect detection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Entry, Ledger
from qe.core.schemas import Span, TestCase
from qe.model.app_model import AppModel, build_from_traces
from qe.risk.register import RiskProposal
from qe.risk.taxonomy import Taxonomy


class Cell(BaseModel):
    model_config = ConfigDict(frozen=True)
    risk_id: str
    taxonomy_id: str
    component: str
    n_drafted: int
    n_valid: int
    status: str


class Structural(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str = "logged_not_validated_H3"
    nodes_total: int
    nodes_exercised: int
    edges_total: int
    edges_exercised: int


class CoverageReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    taxonomy: str
    cells: tuple[Cell, ...]
    unassessed_taxonomy_ids: tuple[str, ...]
    components_without_risk: tuple[str, ...]
    n_tests: int
    n_skeptic_valid: int
    structural: Structural


def build_coverage(
    taxonomy: Taxonomy,
    risks: Sequence[RiskProposal],
    tests: Sequence[TestCase],
    assessments: Mapping[str, str],
    model: AppModel,
    run_traces: Sequence[Sequence[Span]],
) -> CoverageReport:
    cells: list[Cell] = []
    for r in sorted(risks, key=lambda r: r.risk_id):
        mine = [t for t in tests if t.risk_cell == r.risk_id]
        valid = sum(1 for t in mine if assessments.get(t.id) == "valid")
        status = "COVERED" if valid else ("DRAFTED_NOT_VALIDATED" if mine else "UNCOVERED")
        cells.append(Cell(risk_id=r.risk_id, taxonomy_id=r.taxonomy_id, component=r.component,
                          n_drafted=len(mine), n_valid=valid, status=status))
    seen = build_from_traces(run_traces)
    seen_edges = {(e.src, e.dst) for e in seen.edges}
    model_edges = {(e.src, e.dst) for e in model.edges}
    return CoverageReport(
        taxonomy=taxonomy.taxonomy,
        cells=tuple(cells),
        unassessed_taxonomy_ids=tuple(sorted(taxonomy.ids() - {r.taxonomy_id for r in risks})),
        components_without_risk=tuple(
            sorted(model.node_ids() - {r.component for r in risks})
        ),
        n_tests=len(tests),
        n_skeptic_valid=sum(1 for t in tests if assessments.get(t.id) == "valid"),
        structural=Structural(
            nodes_total=len(model.nodes),
            nodes_exercised=len(model.node_ids() & seen.node_ids()),
            edges_total=len(model_edges),
            edges_exercised=len(model_edges & seen_edges),
        ),
    )


def render_markdown(rep: CoverageReport) -> str:
    out = [f"# Coverage report ({rep.taxonomy})", "",
           "Statuses use Skeptic verdicts (proposals), not human-audited validity.", "",
           "| risk | taxonomy | component | drafted | skeptic-valid | status |",
           "|---|---|---|---|---|---|"]
    out += [f"| {c.risk_id} | {c.taxonomy_id} | {c.component} | {c.n_drafted} | {c.n_valid} "
            f"| {c.status} |" for c in rep.cells]
    unassessed = ", ".join(rep.unassessed_taxonomy_ids) or "none"
    out += ["", f"UNASSESSED taxonomy ids (no risk proposed): {unassessed}",
            f"Components without any risk: {', '.join(rep.components_without_risk) or 'none'}",
            "", f"Structural ({rep.structural.label}; logged, not a claim): "
            f"nodes {rep.structural.nodes_exercised}/{rep.structural.nodes_total}, "
            f"edges {rep.structural.edges_exercised}/{rep.structural.edges_total}", ""]
    return "\n".join(out)


def record_coverage(ledger: Ledger, rep: CoverageReport) -> Entry:
    from qe.core.ids import content_id

    payload = {"kind": "coverage_report", **rep.model_dump(mode="json")}
    return ledger.append(Event(key=f"coverage:{content_id(payload)}",
                               type=EventType.EVIDENCE_RECORDED, producer="qe.risk.coverage",
                               producer_kind=ProducerKind.DETERMINISTIC, payload=payload))
