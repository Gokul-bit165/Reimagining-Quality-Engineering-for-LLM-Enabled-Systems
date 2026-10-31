"""Semantic judge status and calibration API (ADR-0009). Names of env settings only; no values."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from qe.realeval import calibration as cal
from qe.realeval.judge import (
    ClientFactory,
    build_judge,
    generator_model_from_env,
    judge_key,
    model_family,
)

router = APIRouter()
_FACTORY: list[ClientFactory | None] = [None]  # tests inject a fake-server client factory


def set_client_factory(factory: ClientFactory | None) -> None:
    _FACTORY[0] = factory


class CalibrateRequest(BaseModel):
    items: list[cal.CalibrationItem] = Field(min_length=1, max_length=cal.MAX_ITEMS)
    confidence: float = Field(default=0.95, gt=0.5, lt=1.0)


@router.get("/api/judge/status")
def judge_status() -> dict[str, Any]:
    env = os.environ
    generator = generator_model_from_env(env)
    build = build_judge(env, generator, _FACTORY[0])
    ind = build.independence
    models = build.judge.key if build.judge else (
        judge_key([build.judge_model]) if build.judge_model else None)
    record = cal.load_for(models) if models else None
    everything = cal.load_all()
    latest = record or (everything[-1] if everything else None)
    return {
        "configured": build.judge is not None,
        "generator_family": model_family(generator),
        "judge_family": ind.judge_family if ind else None,
        "independent": bool(ind and ind.independent),
        "independence_reason": ind.reason if ind else "no judge model configured",
        "judge_model": build.judge_model,
        "second_judge": len(build.judge.members) > 1 if build.judge else False,
        "calibration": cal.status_block(latest, models),
        "gating": "advisory unless the policy sets judge_min_agreement and a fresh "
                  "calibration record meets it",
        "missing": build.missing,
        "notes": build.notes,
    }


@router.post("/api/judge/calibrate")
def judge_calibrate(req: CalibrateRequest) -> dict[str, Any]:
    build = build_judge(os.environ, generator_model_from_env(os.environ), _FACTORY[0])
    if build.judge is None:
        raise HTTPException(status_code=409, detail={
            "error": "judge not available", "missing": build.missing, "notes": build.notes})
    record = cal.calibrate(req.items, build.judge, req.confidence)
    cal.save(record, build.judge.calls())
    return {**record.model_dump(mode="json"), "usage": build.judge.usage()}


@router.get("/api/judge/calibration")
def judge_calibration() -> dict[str, Any]:
    records = cal.load_all()
    return {"latest": records[-1].model_dump(mode="json") if records else None,
            "records": [{"id": r.id, "created_at": r.created_at, "n": r.n,
                         "agreement": r.agreement, "judge_key": r.judge_key}
                        for r in reversed(records)]}
