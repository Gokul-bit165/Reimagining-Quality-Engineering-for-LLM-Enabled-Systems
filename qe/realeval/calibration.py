"""Judge calibration against a USER-labelled set, the gating decision, and judge-error correction
(ADR-0009).

A judge may gate correctness/faithfulness only when (a) the policy declares `judge_min_agreement`
(no value is invented here), (b) a calibration record exists for the CURRENT judge models and
prompt hashes, and (c) the record's measured agreement (lower bound of the exact interval, every
member) reaches that minimum. Otherwise it stays advisory. Collapsed to defect / no-defect:
positive = the human labelled the answer anything other than "correct".
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qe.realeval import claims, scoring
from qe.realeval.judge import (
    LABELS,
    JudgeMember,
    Label,
    SemanticJudge,
    prompt_hashes,
)
from qe.stats.agreement import cohen_kappa, error_correlation, panel_n_eff
from qe.stats.intervals import clopper_pearson
from qe.stats.judge_correction import judge_corrected_rate

MAX_ITEMS = 300
MAX_TEXT = 4000
Kind = Literal["correctness", "faithfulness"]
ROOT = Path(__file__).resolve().parents[2]


def calibration_dir() -> Path:
    return Path(os.environ.get("QE_RUNS_DIR", ROOT / "runs")) / "calibration"


class CalibrationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(default="", max_length=MAX_TEXT)
    reference: str | None = Field(default=None, max_length=MAX_TEXT)
    context: str | list[str] | None = None
    answer: str = Field(max_length=MAX_TEXT)
    label: Label
    kind: Kind | None = None

    @model_validator(mode="after")
    def _check(self) -> CalibrationItem:
        if not self.reference and not self.context:
            raise ValueError("an item needs a reference (correctness) or context (faithfulness)")
        if isinstance(self.context, list) and (
                len(self.context) > 20 or any(len(c) > MAX_TEXT for c in self.context)):
            raise ValueError("context too large")
        if isinstance(self.context, str) and len(self.context) > MAX_TEXT * 4:
            raise ValueError("context too large")
        return self

    @property
    def unit(self) -> Kind:
        return self.kind or ("correctness" if self.reference else "faithfulness")

    @property
    def passages(self) -> list[str]:
        ctx = [self.context] if isinstance(self.context, str) else list(self.context or [])
        return [c for c in ctx if c]


class Confusion(BaseModel):
    model_config = ConfigDict(frozen=True)
    tp: int = 0   # judge flags a defect, human says defect
    fn: int = 0   # judge says fine, human says defect (a FALSE PASS)
    tn: int = 0
    fp: int = 0   # judge flags a defect, human says fine


class MemberCalibration(BaseModel):
    model_config = ConfigDict(frozen=True)
    model: str
    family: str | None
    n_decided: int
    n_abstain: int
    confusion: Confusion
    by_kind: dict[str, Confusion]
    agreement: float | None
    agreement_ci: tuple[float, float] | None
    kappa: float | None
    false_pass_rate: float | None
    false_pass_ci: tuple[float, float] | None
    label_accuracy: float | None   # exact five-way label match, informational


class CalibrationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    created_at: str
    judge_key: str
    models: list[str]
    prompt_hashes: dict[str, str]
    items_sha256: str
    n: int
    confidence: float
    members: list[MemberCalibration]
    agreement: float | None        # primary judge
    agreement_ci: tuple[float, float] | None
    kappa: float | None
    false_pass_rate: float | None
    false_pass_ci: tuple[float, float] | None
    panel: dict[str, Any] | None   # second judge: pairwise kappa, error correlation, n_eff
    budget_exhausted: bool = False


def _confusion(pairs: Sequence[tuple[bool, bool]]) -> Confusion:
    """pairs of (human_defect, judge_defect)."""
    return Confusion(tp=sum(h and j for h, j in pairs), fn=sum(h and not j for h, j in pairs),
                     tn=sum(not h and not j for h, j in pairs),
                     fp=sum(not h and j for h, j in pairs))


def _predict(member: JudgeMember, item: CalibrationItem) -> Label | None:
    """The judge's collapsed-comparable prediction: a rubric label, or for faithfulness
    'correct' (every claim verified supported) / 'incorrect' (a claim verified bad)."""
    if item.unit == "correctness":
        return member.rubric(item.question, item.reference or "", item.answer)
    audit = claims.audit_claims(item.answer, scoring.passages(item.passages), member)
    return audit.judge_view


def _member_stats(member: JudgeMember, items: Sequence[CalibrationItem],
                  preds: Sequence[Label | None], confidence: float) -> MemberCalibration:
    decided = [(i, p) for i, p in zip(items, preds, strict=True) if p is not None]
    pairs = [(i.label != "correct", p != "correct") for i, p in decided]
    c = _confusion(pairs)
    n = len(pairs)
    by_kind = {k: _confusion([(i.label != "correct", p != "correct")
                              for i, p in decided if i.unit == k])
               for k in ("correctness", "faithfulness")}
    pos, ok = c.tp + c.fn, c.tp + c.tn
    return MemberCalibration(
        model=member.model, family=member.family, n_decided=n, n_abstain=len(items) - n,
        confusion=c, by_kind=by_kind,
        agreement=None if n == 0 else ok / n,
        agreement_ci=None if n == 0 else clopper_pearson(ok, n, confidence),
        kappa=cohen_kappa(["d" if h else "o" for h, _ in pairs],
                          ["d" if j else "o" for _, j in pairs]),
        false_pass_rate=None if pos == 0 else c.fn / pos,
        false_pass_ci=None if pos == 0 else clopper_pearson(c.fn, pos, confidence),
        label_accuracy=None if n == 0 else sum(i.label == p for i, p in decided) / n)


def _panel(items: Sequence[CalibrationItem], preds: Sequence[Sequence[Label | None]],
           ) -> dict[str, Any]:
    """Second judge vs first: pairwise kappa and error correlation against the human labels."""
    err = [[None if p is None else (p != "correct") != (i.label != "correct")
            for i, p in zip(items, ps, strict=True)] for ps in preds[:2]]
    both = sum(a is True and b is True for a, b in zip(err[0], err[1], strict=True))
    corr = error_correlation(err[0], err[1])
    return {"kappa": cohen_kappa([None if p is None else p == "correct" for p in preds[0]],
                                 [None if p is None else p == "correct" for p in preds[1]]),
            "error_correlation": corr, "both_wrong": both,
            "n_eff": panel_n_eff([[1.0, corr], [corr, 1.0]]),
            "correlated_errors": corr > 0 and both > 0}


def calibrate(items: Sequence[CalibrationItem], judge: SemanticJudge,
              confidence: float = 0.95) -> CalibrationRecord:
    """Run every judge member over the labelled items (live or replayed) and record the result."""
    if not items or len(items) > MAX_ITEMS:
        raise ValueError(f"need 1..{MAX_ITEMS} calibration items")
    preds = [[_predict(m, i) for i in items] for m in judge.members]
    members = [_member_stats(m, items, p, confidence) for m, p in zip(judge.members, preds,
                                                                      strict=True)]
    primary = members[0]
    items_sha = hashlib.sha256(json.dumps([i.model_dump(mode="json") for i in items],
                                          sort_keys=True).encode("utf-8")).hexdigest()
    body = {"judge_key": judge.key, "items": items_sha,
            "members": [m.model_dump(mode="json") for m in members]}
    rid = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return CalibrationRecord(
        id=rid, created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        judge_key=judge.key, models=[m.model for m in judge.members],
        prompt_hashes=prompt_hashes(), items_sha256=items_sha, n=len(items),
        confidence=confidence, members=members, agreement=primary.agreement,
        agreement_ci=primary.agreement_ci, kappa=primary.kappa,
        false_pass_rate=primary.false_pass_rate, false_pass_ci=primary.false_pass_ci,
        panel=_panel(items, preds) if len(preds) > 1 else None,
        budget_exhausted=bool(judge.budget and judge.budget.exhausted))


# ----------------------------------------------------------------------------- storage
def save(record: CalibrationRecord, calls: Sequence[Mapping[str, Any]],
         directory: Path | None = None) -> Path:
    d = directory or calibration_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{record.id}.json"
    path.write_text(json.dumps({"record": record.model_dump(mode="json"), "calls": list(calls)},
                               indent=2), encoding="utf-8")
    return path


def _read(path: Path) -> CalibrationRecord | None:
    try:
        return CalibrationRecord.model_validate(
            json.loads(path.read_text(encoding="utf-8"))["record"])
    except (OSError, ValueError, KeyError):
        return None


def load_all(directory: Path | None = None) -> list[CalibrationRecord]:
    d = directory or calibration_dir()
    recs = [r for p in sorted(d.glob("*.json")) if (r := _read(p)) is not None] \
        if d.is_dir() else []
    return sorted(recs, key=lambda r: r.created_at)


def load_for(judge_key: str, directory: Path | None = None) -> CalibrationRecord | None:
    """Newest record measured for exactly this judge configuration, else None."""
    matching = [r for r in load_all(directory) if r.judge_key == judge_key]
    return matching[-1] if matching else None


def load_calls(record_id: str, directory: Path | None = None) -> list[dict[str, Any]]:
    path = (directory or calibration_dir()) / f"{record_id}.json"
    return list(json.loads(path.read_text(encoding="utf-8"))["calls"])


# ----------------------------------------------------------------------------- gating
def gate_agreement(record: CalibrationRecord) -> float:
    """The agreement the gate compares with the policy minimum: the LOWEST lower interval bound
    over all judge members (a conservative, interval-aware reading of 'measured agreement')."""
    lows = [m.agreement_ci[0] if m.agreement_ci else 0.0 for m in record.members]
    return min(lows) if lows else 0.0


def decide_gate(judge: SemanticJudge | None, min_agreement: float | None,
                record: CalibrationRecord | None) -> dict[str, Any]:
    """{'enabled': bool, 'reason': str, ...}. Enabled only if every condition holds."""
    def off(reason: str) -> dict[str, Any]:
        return {"enabled": False, "reason": reason, "min_agreement": min_agreement,
                "calibration_id": None if record is None else record.id}

    if judge is None:
        return off("no judge configured")
    ind = judge.independence
    if ind is None or not ind.independent:
        return off("judge independence is not verified (R4)")
    if min_agreement is None:
        return off("policy declares no judge_min_agreement: judge is advisory")
    if record is None:
        return off("no calibration record for the current judge and prompts: judge is advisory")
    if record.judge_key != judge.key:
        return off("calibration record is stale (judge model or prompt changed): advisory")
    got = gate_agreement(record)
    if got < min_agreement:
        return off(f"measured agreement lower bound {got:.3f} is below the policy minimum "
                   f"{min_agreement}: advisory")
    primary = record.members[0]
    counts = {k: v.model_dump() for k, v in primary.by_kind.items()}
    return {"enabled": True, "reason": "calibrated: agreement lower bound "
            f"{got:.3f} >= policy minimum {min_agreement}", "min_agreement": min_agreement,
            "calibration_id": record.id, "agreement_lower": got, "counts": counts}


def status_block(record: CalibrationRecord | None, judge_key_now: str | None,
                 ) -> dict[str, Any] | None:
    if record is None:
        return None
    return {"n": record.n, "agreement": record.agreement,
            "ci": None if record.agreement_ci is None else list(record.agreement_ci),
            "kappa": record.kappa, "false_pass_rate": record.false_pass_rate,
            "false_pass_ci": None if record.false_pass_ci is None
            else list(record.false_pass_ci),
            "prompt_hash": record.prompt_hashes, "id": record.id,
            "stale": judge_key_now is not None and record.judge_key != judge_key_now,
            "created_at": record.created_at}


# ----------------------------------------------------------------------------- aggregate report
def _corrected(flagged: int, n: int, counts: Mapping[str, int]) -> dict[str, Any]:
    pos, neg = counts["tp"] + counts["fn"], counts["fp"] + counts["tn"]
    try:
        r = judge_corrected_rate(flagged, n, tp=counts["tp"], positives=pos, fp=counts["fp"],
                                 negatives=neg)
    except ValueError as exc:
        return {"corrected": None, "reason": str(exc), "n_judged": n}
    return {"observed_defect_rate": r.observed, "corrected_defect_rate": r.corrected,
            "ci_low": r.lower, "ci_high": r.upper, "tpr": r.tpr, "fpr": r.fpr,
            "n_judged": n, "method": r.method}


def judge_report(rows: Sequence[Mapping[str, Any]], judge: SemanticJudge) -> dict[str, Any]:
    """Result block `judge`: gate state, usage, panel agreement, conflicts sent to human review,
    and (only when gating) judge-error-corrected defect rates with propagated intervals."""
    details = {r["id"]: (r.get("detail") or {}) for r in rows}
    conflicts = [rid for rid, d in details.items() if d.get("needs_review")]
    out: dict[str, Any] = {"enabled": True, "gating": judge.gating, "gate": judge.gate,
                           "models": [m.model for m in judge.members],
                           "prompt_hashes": prompt_hashes(), "usage": judge.usage(),
                           "panel": judge.panel(), "conflicts": conflicts}
    if judge.gating:
        counts = judge.gate.get("counts") or {}
        corrected: dict[str, Any] = {}
        for kind in ("correctness", "faithfulness"):
            views = [(d.get("judge") or {}).get(kind) for d in details.values()]
            seen = [v for v in views if v is not None]
            if seen and kind in counts:
                corrected[kind] = _corrected(sum(v == "incorrect" for v in seen), len(seen),
                                             counts[kind])
        out["corrected"] = corrected
    return out


__all__ = ["LABELS", "CalibrationItem", "CalibrationRecord", "calibrate", "decide_gate"]
