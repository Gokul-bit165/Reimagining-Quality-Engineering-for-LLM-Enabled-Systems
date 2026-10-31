"""Judge-corrected rate (Rogan-Gladen style) with interval by seeded posterior simulation.

Definition: research/benchmarks/evaluation_metrics.md, "Interval methods" and research/17
section 5 (judge-correction using a human-labelled calibration subset).
For a judge with sensitivity TPR and false-positive rate FPR, the observed positive rate
q = p*TPR + (1-p)*FPR, so p = (q - FPR) / (TPR - FPR), clipped to [0, 1].
"Positive" here means the judge flagged a failure.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, ConfigDict

from qe.stats.bayes import JEFFREYS


class CorrectedRate(BaseModel):
    model_config = ConfigDict(frozen=True)
    observed: float
    corrected: float
    lower: float
    upper: float
    tpr: float
    fpr: float
    confidence: float
    method: str = "rogan_gladen_beta_simulation"


def rogan_gladen(observed: float, tpr: float, fpr: float) -> float:
    if not 0.0 <= observed <= 1.0:
        raise ValueError("observed must be in [0, 1]")
    if tpr <= fpr:
        raise ValueError("judge is uninformative: need TPR > FPR")
    return min(1.0, max(0.0, (observed - fpr) / (tpr - fpr)))


def _check(name: str, hits: int, total: int) -> None:
    if total < 1 or hits < 0 or hits > total:
        raise ValueError(f"invalid counts for {name}")


def judge_corrected_rate(
    flagged: int,
    n: int,
    *,
    tp: int,
    positives: int,
    fp: int,
    negatives: int,
    confidence: float = 0.95,
    draws: int = 4000,
    seed: int = 0,
) -> CorrectedRate:
    """Correct the judge-flagged rate flagged/n using calibration counts.

    positives/negatives = human-labelled failing/passing calibration items; tp = those of
    the positives the judge flagged, fp = those of the negatives it flagged. Uncertainty of
    q, TPR and FPR is propagated by independent Jeffreys-beta draws (fixed seed).
    Draws where TPR <= FPR are discarded; if over half are, the judge is rejected.
    """
    _check("test", flagged, n)
    _check("tpr", tp, positives)
    _check("fpr", fp, negatives)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    a0, b0 = JEFFREYS
    rng = random.Random(seed)
    sims: list[float] = []
    for _ in range(draws):
        q = rng.betavariate(a0 + flagged, b0 + n - flagged)
        t = rng.betavariate(a0 + tp, b0 + positives - tp)
        f = rng.betavariate(a0 + fp, b0 + negatives - fp)
        if t > f:
            sims.append(min(1.0, max(0.0, (q - f) / (t - f))))
    if len(sims) < draws // 2:
        raise ValueError("judge is (near-)uninformative on the calibration set: TPR ~ FPR")
    sims.sort()
    tail = (1.0 - confidence) / 2
    lo = sims[int(tail * (len(sims) - 1))]
    hi = sims[int((1.0 - tail) * (len(sims) - 1))]
    tpr, fpr = tp / positives, fp / negatives
    return CorrectedRate(observed=flagged / n, corrected=rogan_gladen(flagged / n, tpr, fpr),
                         lower=lo, upper=hi, tpr=tpr, fpr=fpr, confidence=confidence)
