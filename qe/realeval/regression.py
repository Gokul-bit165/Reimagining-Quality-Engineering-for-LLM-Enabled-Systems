"""Per-project regression suite: failed evaluation items admitted into qe.regress.SuiteStore.

Deviation, stated plainly: qe.regress admission is statistical and needs a known-defective and a
known-clean build. A user's app has no clean baseline here, so cases are admitted with
`threshold=1` and a reason saying "observed failing in evaluation X", not statistically admitted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qe.core.ledger import ConflictError, SQLiteLedger
from qe.core.schemas import TestCase
from qe.realeval.dataset import EvalItem
from qe.regress.admission import Admission
from qe.regress.store import SuiteStore

PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _path(base: Path, project_id: str) -> Path:
    if not PROJECT_ID.match(project_id):
        raise ValueError("invalid project id")
    return base / "regression" / f"{project_id}.sqlite"


def admit(base: Path, project_id: str, eval_id: str, failed: list[dict[str, Any]],
          items: dict[str, EvalItem]) -> list[str]:
    path = _path(base, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = SQLiteLedger(path)
    admitted: list[str] = []
    try:
        store = SuiteStore(ledger)
        have = {c.id for c in store.cases()}
        for row in failed:
            if row["id"] in have:
                continue
            item = items[row["id"]]
            case = TestCase(id=item.id, risk_cell=row["failure_class"],
                            input={"item": item.model_dump(mode="json"),
                                   "failure_class": row["failure_class"],
                                   "failure_reason": row["failure_reason"]},
                            oracle_source=("outcome_oracle" if item.source == "security"
                                           else "user_reference" if item.reference_answer
                                           else "deterministic:grounding"),
                            lineage=(eval_id,))
            reps = len(row["scores"].get("repeat_passes", [False]))
            adm = Admission(admitted=True, successes=reps - sum(row["scores"]["repeat_passes"]),
                            trials=reps, threshold=1,
                            reason=f"observed failing in {eval_id}; no clean-build baseline")
            try:
                store.admit(case, minimized_from=item.id, admission=adm, flake_rate=0.0, alpha=0.0)
                admitted.append(item.id)
            except ConflictError:
                continue  # already in the suite from an earlier evaluation
    finally:
        ledger.close()
    return admitted


def suite(base: Path, project_id: str) -> list[dict[str, Any]]:
    path = _path(base, project_id)
    if not path.is_file():
        return []
    ledger = SQLiteLedger(path)
    try:
        return [dict(c.input) | {"case_id": c.id, "risk_cell": c.risk_cell,
                                 "admitted_from": list(c.lineage)}
                for c in SuiteStore(ledger).cases()]
    finally:
        ledger.close()


def suite_items(base: Path, project_id: str) -> list[EvalItem]:
    return [EvalItem.model_validate(c["item"]).model_copy(update={"regression": True})
            for c in suite(base, project_id)]
