"""Judge-corrected prevalence (evaluation_metrics.md, "Calibration" and "Interval methods").

A judge flags items with sensitivity Se and specificity Sp (estimated on a HUMAN-labelled
calibration set). If a fraction q of production items is flagged, the Rogan-Gladen estimate of
the true rate is  theta = (q + Sp - 1) / (Se + Sp - 1)  (clipped to [0, 1]).

Interval: Monte-Carlo over independent Jeffreys-Beta posteriors for q, Se and Sp, so calibration
noise widens the interval. Draws whose Youden index J = Se + Sp - 1 <= 0 carry no information;
they are dropped and reported as `unidentified_fraction` (a large value means the judge cannot
support a corrected estimate and the caller must treat the result as INSUFFICIENT).
Assumption (not tested here): judge errors are conditionally independent of the true rate,
i.e. the calibration set is representative of the evaluated population.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, ConfigDict, model_validator

from qe.stats.bayes import JEFFREYS


class CalibrationCounts(BaseModel):
    """Human-labelled calibration confusion counts; 'positive' = defect present."""

    model_config = ConfigDict(frozen=True)
    tp: int  # judge flags, human says defect
    fn: int  # judge silent, human says defect
    tn: int
    fp: int

    @model_validator(mode="after")
    def _check(self) -> CalibrationCounts:
        if min(self.tp, self.fn, self.tn, self.fp) < 0:
            raise ValueError("counts must be >= 0")
        if self.tp + self.fn == 0 or self.tn + self.fp == 0:
            raise ValueError("need labelled positives and negatives to estimate Se and Sp")
        return self

    @property
    def sensitivity(self) -> float:
        return self.tp / (self.tp + self.fn)

    @property
    def specificity(self) -> float:
        return self.tn / (self.tn + self.fp)


class JudgeCorrectedEstimate(BaseModel):
    model_config = ConfigDict(frozen=True)
    flagged: int
    n: int
    apparent_rate: float
    point: float
    lower: float
    upper: float
    confidence: float
    unidentified_fraction: float
    draws: int
    seed: int
    method: str = "rogan_gladen_bayes_mc"


def rogan_gladen(q: float, sensitivity: float, specificity: float) -> float:
    j = sensitivity + specificity - 1.0
    if j <= 0.0:
        raise ValueError("Youden index <= 0: judge is no better than chance")
    return min(1.0, max(0.0, (q + specificity - 1.0) / j))


def judge_corrected_rate(
    flagged: int,
    n: int,
    cal: CalibrationCounts,
    confidence: float = 0.95,
    draws: int = 20_000,
    seed: int = 0,
) -> JudgeCorrectedEstimate:
    if n <= 0 or flagged < 0 or flagged > n:
        raise ValueError("need n >= 1 and 0 <= flagged <= n")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if draws < 100:
        raise ValueError("draws must be >= 100")
    rng = random.Random(seed)
    a0, b0 = JEFFREYS
    vals: list[float] = []
    for _ in range(draws):
        q = rng.betavariate(a0 + flagged, b0 + n - flagged)
        se = rng.betavariate(a0 + cal.tp, b0 + cal.fn)
        sp = rng.betavariate(a0 + cal.tn, b0 + cal.fp)
        j = se + sp - 1.0
        if j > 0.0:
            vals.append(min(1.0, max(0.0, (q + sp - 1.0) / j)))
    unidentified = 1.0 - len(vals) / draws
    if len(vals) < 2:
        raise ValueError("judge unidentified in (almost) all posterior draws")
    vals.sort()
    alpha = 1.0 - confidence
    lo = vals[int(alpha / 2 * (len(vals) - 1))]
    hi = vals[int((1.0 - alpha / 2) * (len(vals) - 1))]
    point = rogan_gladen(flagged / n, cal.sensitivity, cal.specificity)
    return JudgeCorrectedEstimate(
        flagged=flagged, n=n, apparent_rate=flagged / n, point=point, lower=min(lo, point),
        upper=max(hi, point), confidence=confidence, unidentified_fraction=unidentified,
        draws=draws, seed=seed,
    )
