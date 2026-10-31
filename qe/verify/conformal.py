"""Split-conformal abstention for categorical adjudication.

NCM here means nonconformity measure (the user never confirmed this reading of the
abbreviation; it is assumed, see docs/HANDOFF.md). The score of a candidate label y given the
panel's vote distribution p is  s(p, y) = 1 - p(y).
Calibration (split conformal, Vovk et al.; metric definitions in
research/benchmarks/evaluation_metrics.md, "Calibration"): on n labelled items compute the
true-label scores, take q = the ceil((n+1)(1-alpha))-th smallest. The prediction set is
{y : s(p, y) <= q}; the system answers only when the set is a single label, else ABSTAIN.
Coverage guarantee: P(true label in set) >= 1 - alpha under exchangeability of calibration
and test items. It is a marginal guarantee about the set, not about answered-only accuracy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from qe.core.schemas import ClaimState, Verdict

_UNDECIDED = frozenset({ClaimState.ABSTAIN})
LABELS = tuple(s for s in ClaimState if s not in _UNDECIDED)


def vote_probs(
    verdicts: Sequence[Verdict], weights: Mapping[str, float] | None = None
) -> dict[ClaimState, float]:
    """Weighted vote share per state over non-abstaining verdicts ({} if none voted)."""
    tally: dict[ClaimState, float] = {}
    for v in verdicts:
        if v.state in _UNDECIDED:
            continue
        w = 1.0 if weights is None else weights.get(v.method, 1.0)
        tally[v.state] = tally.get(v.state, 0.0) + w
    total = sum(tally.values())
    return {s: w / total for s, w in tally.items()} if total > 0 else {}


def nonconformity(probs: Mapping[ClaimState, float], label: ClaimState) -> float:
    return 1.0 - probs.get(label, 0.0)


@dataclass(frozen=True)
class SplitConformal:
    alpha: float
    qhat: float  # math.inf when the calibration set is too small for this alpha
    n_calibration: int

    @classmethod
    def fit(
        cls, calibration: Sequence[tuple[Mapping[ClaimState, float], ClaimState]], alpha: float
    ) -> SplitConformal:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        n = len(calibration)
        if n == 0:
            raise ValueError("need a non-empty calibration set")
        scores = sorted(nonconformity(p, y) for p, y in calibration)
        rank = math.ceil((n + 1) * (1.0 - alpha))
        qhat = scores[rank - 1] if rank <= n else math.inf
        return cls(alpha=alpha, qhat=qhat, n_calibration=n)

    def prediction_set(self, probs: Mapping[ClaimState, float]) -> frozenset[ClaimState]:
        if not probs:
            return frozenset(LABELS)  # no votes: nothing is excluded
        return frozenset(y for y in LABELS if nonconformity(probs, y) <= self.qhat)

    def answers(self, probs: Mapping[ClaimState, float]) -> ClaimState | None:
        """The single label if the prediction set is a singleton, else None (abstain)."""
        s = self.prediction_set(probs)
        return next(iter(s)) if len(s) == 1 else None

    def coverage(
        self, held_out: Sequence[tuple[Mapping[ClaimState, float], ClaimState]]
    ) -> float:
        if not held_out:
            raise ValueError("need held-out items")
        return sum(y in self.prediction_set(p) for p, y in held_out) / len(held_out)
