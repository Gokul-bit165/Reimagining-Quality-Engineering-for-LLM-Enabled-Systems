"""Regression suite store backed by the ledger (lineage = events, nothing else).

Uses EVIDENCE_RECORDED with payload kind "regression_case" (no new EventType needed; see
ADR-0002-p1). Admission evidence is stored with the case so the suite is auditable.
"""

from __future__ import annotations

from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import RegressionCase, TestCase
from qe.regress.admission import Admission

PRODUCER = "regress_store"
KIND = "regression_case"


class SuiteStore:
    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def admit(self, case: TestCase, *, minimized_from: str, admission: Admission,
              flake_rate: float, alpha: float) -> None:
        if not admission.admitted:
            raise ValueError(f"case {case.id} not admitted: {admission.reason}")
        self._ledger.append(Event(
            key=f"regress:{case.id}", type=EventType.EVIDENCE_RECORDED, producer=PRODUCER,
            producer_kind=ProducerKind.DETERMINISTIC,
            payload={"kind": KIND, "case": case.model_dump(mode="json"),
                     "minimized_from": minimized_from,
                     "admission": admission.model_dump(mode="json"),
                     "flake_rate": flake_rate, "alpha": alpha}))

    def _payloads(self) -> list[dict[str, Any]]:
        return [e.event.payload for e in self._ledger.entries()
                if e.event.type is EventType.EVIDENCE_RECORDED
                and e.event.payload.get("kind") == KIND]

    def cases(self) -> list[TestCase]:
        return [TestCase.model_validate(p["case"]) for p in self._payloads()]

    def regression_cases(self) -> list[RegressionCase]:
        return [RegressionCase(
            case_id=TestCase.model_validate(p["case"]).id,
            minimized_from=str(p["minimized_from"]),
            pass_k_admission=(int(p["admission"]["successes"]), int(p["admission"]["trials"])))
            for p in self._payloads()]

    def lineage(self, case_id: str) -> list[str]:
        parent = {rc.case_id: rc.minimized_from for rc in self.regression_cases()}
        chain, seen = [case_id], {case_id}
        while chain[-1] in parent and parent[chain[-1]] not in seen:
            chain.append(parent[chain[-1]])
            seen.add(chain[-1])
        return chain
