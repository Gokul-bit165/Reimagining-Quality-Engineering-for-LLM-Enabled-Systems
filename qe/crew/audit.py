"""Human audit sampling and invalid-test-rate measurement (T2.3).

The sample is a simple random sample of drafted tests, blind to Skeptic verdicts, so the
invalid-test rate is an unbiased estimate for the sampled population (exact CP interval).
Machine-rejected drafts (failed deterministic gates) are NOT in the population; count them
separately via `machine_rejected`.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Entry, Ledger
from qe.core.schemas import TestCase
from qe.crew.skeptic import Assessment
from qe.stats.intervals import clopper_pearson

LABELS = ("valid", "invalid", "ambiguous")


class AuditItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    test: TestCase
    source_text: str


class AuditLabel(BaseModel):
    model_config = ConfigDict(frozen=True)
    test_id: str
    label: str

    @field_validator("label")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in LABELS:
            raise ValueError(f"label must be one of {LABELS}")
        return v


class RateEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)
    k: int
    n: int
    lower: float
    upper: float
    confidence: float = 0.95

    @property
    def point(self) -> float:
        return self.k / self.n


def _rate(k: int, n: int) -> RateEstimate:
    if n <= 0:
        raise ValueError("no labelled items")
    lo, hi = clopper_pearson(k, n)
    return RateEstimate(k=k, n=n, lower=lo, upper=hi)


def drafted_tests(ledger: Ledger) -> list[AuditItem]:
    items = []
    for e in ledger.entries():
        p = e.event.payload
        if e.event.type is EventType.TEST_DRAFTED and p.get("status") == "drafted":
            items.append(AuditItem(test=TestCase.model_validate(p["test"]),
                                   source_text=str(p["source_text"])))
    return items


def machine_rejected(ledger: Ledger) -> int:
    return sum(
        1
        for e in ledger.entries()
        if e.event.type is EventType.TEST_DRAFTED and e.event.payload.get("status") == "rejected"
    )


def assessments(ledger: Ledger) -> dict[str, Assessment]:
    out: dict[str, Assessment] = {}
    for e in ledger.entries():
        p = e.event.payload
        if e.event.type is EventType.VALIDITY_VERDICT and p["test_id"] not in out:
            out[p["test_id"]] = Assessment(test_id=p["test_id"], status=p["status"],
                                           reason=p["reason"])
    return out


def sample(tests: Sequence[TestCase], n: int, seed: int) -> list[TestCase]:
    pool = sorted(tests, key=lambda t: t.id)
    return random.Random(seed).sample(pool, min(n, len(pool)))


def record_labels(ledger: Ledger, labels: Sequence[AuditLabel], auditor: str) -> list[Entry]:
    return [
        ledger.append(Event(
            key=f"audit:{lb.test_id}:{auditor}", type=EventType.SIGNOFF_RECORDED,
            producer=f"human:{auditor}", producer_kind=ProducerKind.HUMAN,
            payload={"kind": "audit_label", "test_id": lb.test_id, "label": lb.label,
                     "auditor": auditor},
        ))
        for lb in labels
    ]


def invalid_rate(labels: Sequence[AuditLabel]) -> RateEstimate:
    """Fraction of audited tests the human labelled invalid (ambiguous reported separately)."""
    return _rate(sum(1 for lb in labels if lb.label == "invalid"), len(labels))


def not_valid_rate(labels: Sequence[AuditLabel]) -> RateEstimate:
    return _rate(sum(1 for lb in labels if lb.label != "valid"), len(labels))


def skeptic_precision(
    labels: Sequence[AuditLabel], assess: Mapping[str, Assessment]
) -> RateEstimate:
    """Among audited tests the Skeptic called valid, the fraction humans also called valid."""
    called = [lb for lb in labels if lb.test_id in assess and assess[lb.test_id].status == "valid"]
    return _rate(sum(1 for lb in called if lb.label == "valid"), len(called))
