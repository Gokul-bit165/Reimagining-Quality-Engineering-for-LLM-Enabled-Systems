"""`qe audit` core: seeded stratified sampling of drafted tests for human labelling (CSV out/in)
and the invalid-test rate with an exact interval computed from labelled rows.

Sampling is proportional allocation across strata (risk cells) with seeded within-stratum draws.
The pooled interval treats labelled rows as a simple random sample; under proportional allocation
that is an approximation (documented in ADR-0004-p3).
"""

from __future__ import annotations

import csv
import io
import random
from collections.abc import Sequence

from qe.core.events import EventType
from qe.core.ledger import Ledger
from qe.core.schemas import Frozen
from qe.risk.coverage import InvalidTestRateEstimate
from qe.stats.intervals import clopper_pearson

COLUMNS = ("test_id", "stratum", "question", "oracle_source", "expected_span",
           "human_label", "label_source", "notes")
LABELS = ("valid", "invalid", "ambiguous")
SYNTHETIC_SOURCE = "synthetic_autolabel"
SAMPLING = "proportional-stratified-by-risk-cell, seeded"


class AuditItem(Frozen):
    test_id: str
    stratum: str
    question: str
    oracle_source: str
    expected_span: str


def items_from_ledger(ledger: Ledger) -> list[AuditItem]:
    out: dict[str, AuditItem] = {}
    for e in ledger.entries():
        if e.event.type is not EventType.TEST_DRAFTED:
            continue
        p = e.event.payload
        case = p["test_case"]
        out[case["id"]] = AuditItem(
            test_id=case["id"], stratum=str(case.get("risk_cell") or "unassigned"),
            question=str(case["input"].get("input", "")), oracle_source=case["oracle_source"],
            expected_span=str(p.get("expected_span") or ""),
        )
    return [out[k] for k in sorted(out)]


def _allocate(sizes: dict[str, int], n: int) -> dict[str, int]:
    total = sum(sizes.values())
    shares = {k: n * v / total for k, v in sizes.items()}
    alloc = {k: int(s) for k, s in shares.items()}
    for k in sorted(shares, key=lambda k: (-(shares[k] - alloc[k]), k))[: n - sum(alloc.values())]:
        alloc[k] += 1
    return alloc


def sample(items: Sequence[AuditItem], n: int, seed: int) -> list[AuditItem]:
    if n < 1 or n > len(items):
        raise ValueError(f"n must be in [1, {len(items)}]")
    strata: dict[str, list[AuditItem]] = {}
    for it in sorted(items, key=lambda i: i.test_id):
        strata.setdefault(it.stratum, []).append(it)
    alloc = _allocate({k: len(v) for k, v in strata.items()}, n)
    picked: list[AuditItem] = []
    for k in sorted(strata):
        rng = random.Random(f"{seed}:{k}")
        picked += rng.sample(strata[k], min(alloc[k], len(strata[k])))
    return sorted(picked, key=lambda i: i.test_id)


def to_csv(items: Sequence[AuditItem]) -> str:
    """Blind sheet: no skeptic verdict is included, labellers decide independently."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for it in items:
        w.writerow({**it.model_dump(), "human_label": "", "label_source": "", "notes": ""})
    return buf.getvalue()


def score(csv_text: str, confidence: float = 0.95) -> InvalidTestRateEstimate:
    """Invalid-test rate (k invalid / n labelled) with an exact Clopper-Pearson interval."""
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    n = k = amb = 0
    strata: dict[str, dict[str, int]] = {}
    synthetic = False
    for i, row in enumerate(rows, start=2):
        label = (row.get("human_label") or "").strip().lower()
        if not label:
            continue
        if label not in LABELS:
            raise ValueError(f"row {i}: label must be one of {LABELS}, got {label!r}")
        synthetic = synthetic or (row.get("label_source") or "").strip() == SYNTHETIC_SOURCE
        s = strata.setdefault(row.get("stratum", "unassigned"), {"n": 0, "k": 0})
        n, s["n"] = n + 1, s["n"] + 1
        if label == "invalid":
            k, s["k"] = k + 1, s["k"] + 1
        elif label == "ambiguous":
            amb += 1
    if n == 0:
        raise ValueError("no labelled rows")
    lo, hi = clopper_pearson(k, n, confidence)
    return InvalidTestRateEstimate(
        k=k, n=n, n_ambiguous=amb, point=k / n, lower=lo, upper=hi, confidence=confidence,
        strata=strata, sampling=SAMPLING, synthetic=synthetic,
    )
