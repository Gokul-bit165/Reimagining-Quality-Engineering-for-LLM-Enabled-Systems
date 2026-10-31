"""Verdict aggregator (M3 T3.2): isolation by types, independence audit, abstention.

* Information isolation (R4): `adjudicate` accepts ONLY a `VerifierInput` (frozen,
  extra="forbid", exact base types); it passes that same object to every verifier, so no
  verifier sees producer rationale or another verifier's verdict.
* Independence (R4): `check_panel` rejects a panel containing a model-based verifier whose
  family equals an author (generator/attacker) family, or whose family is undeclared.
* Deterministic verdicts override neural ones for exact-check claims (R3/R5).
* Otherwise: weighted vote -> optional split-conformal abstention (qe.verify.conformal).
  n_eff is the value measured on a labelled calibration set (`panel_report`), never invented.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from qe.core.schemas import AdjudicatedVerdict, ClaimState, MethodClass, Verdict
from qe.ports import VerifierInput, VerifierPort
from qe.stats.agreement import correlation_matrix, panel_n_eff
from qe.verify.conformal import SplitConformal, vote_probs

EXACT_CLASSES = frozenset({MethodClass.DETERMINISTIC, MethodClass.OUTCOME_ORACLE})
MODEL_CLASSES = frozenset({MethodClass.LLM_JUDGE, MethodClass.METRIC_LIBRARY,
                           MethodClass.DECISION_MODEL})
_NO_DECISION = frozenset({ClaimState.ABSTAIN, ClaimState.UNVERIFIABLE,
                          ClaimState.SOURCE_UNAVAILABLE})


class PanelIndependenceError(ValueError):
    pass


def check_panel(verifiers: Sequence[VerifierPort], author_families: Collection[str]) -> None:
    if not verifiers:
        raise PanelIndependenceError("empty panel")
    names = [v.name for v in verifiers]
    if len(set(names)) != len(names):
        raise PanelIndependenceError("verifier names must be unique")
    banned = {f.casefold() for f in author_families}
    for v in verifiers:
        needs_model = v.method_class in MODEL_CLASSES
        if needs_model and (v.model is None or not v.model.family):
            raise PanelIndependenceError(f"{v.name}: model-based verifier must declare a family")
        if v.model is not None and v.model.family.casefold() in banned:
            raise PanelIndependenceError(
                f"{v.name}: model family {v.model.family!r} is an author family (R4)")


class Aggregator:
    def __init__(
        self,
        verifiers: Sequence[VerifierPort],
        *,
        author_families: Collection[str],
        conformal: SplitConformal | None = None,
        weights: Mapping[str, float] | None = None,
        n_eff: float | None = None,
    ) -> None:
        check_panel(verifiers, author_families)
        self.verifiers = tuple(verifiers)
        self._conformal, self._weights, self._n_eff = conformal, weights, n_eff

    async def _run(self, v: VerifierPort, item: VerifierInput) -> Verdict:
        try:
            return await v.verify(item)
        except Exception as exc:  # a crashed verifier is an abstention, never a silent pass
            return Verdict(claim_id=item.claim.claim_id, method=v.name,
                           method_class=v.method_class, method_version=v.version,
                           model_family=v.model.family if v.model else None,
                           state=ClaimState.ABSTAIN, detail=f"verifier error: {type(exc).__name__}")

    async def verdicts(self, item: VerifierInput) -> tuple[Verdict, ...]:
        if type(item) is not VerifierInput:
            raise TypeError("aggregator accepts only VerifierInput (information isolation)")
        return tuple(await asyncio.gather(*(self._run(v, item) for v in self.verifiers)))

    def decide(self, claim_id: str, verdicts: Sequence[Verdict], *,
               exact_check: bool = False) -> AdjudicatedVerdict:
        ids = tuple(v.cid() for v in verdicts)

        def out(
            state: ClaimState, conf: float | None, layers: tuple[str, ...]
        ) -> AdjudicatedVerdict:
            return AdjudicatedVerdict(claim_id=claim_id, state=state, confidence=conf,
                                      n_eff=self._n_eff, layers_fired=layers, verdict_ids=ids)

        if exact_check:
            exact = {v.state for v in verdicts
                     if v.method_class in EXACT_CLASSES and v.state not in _NO_DECISION}
            if len(exact) == 1:
                return out(next(iter(exact)), 1.0, ("deterministic",))
            if len(exact) > 1:
                return out(ClaimState.ABSTAIN, None, ("deterministic", "conflict"))
        # an exact check that does not apply (UNVERIFIABLE) is a non-vote, not a dissent
        voters = [v for v in verdicts
                  if not (v.method_class in EXACT_CLASSES and v.state is ClaimState.UNVERIFIABLE)]
        probs = vote_probs(voters, self._weights)
        if not probs:
            return out(ClaimState.ABSTAIN, None, ("no_votes",))
        top = max(probs.values())
        leaders = [s for s, p in probs.items() if p == top]
        if len(leaders) > 1:
            return out(ClaimState.ABSTAIN, top, ("vote_tie",))
        layers: tuple[str, ...] = ("vote",)
        if self._conformal is not None:
            answered = self._conformal.answers(probs)
            if answered is None:
                return out(ClaimState.ABSTAIN, top, (*layers, "conformal_abstain"))
            layers = (*layers, "conformal")
        return out(leaders[0], top, layers)

    async def adjudicate(self, item: VerifierInput, *, exact_check: bool = False
                         ) -> AdjudicatedVerdict:
        vs = await self.verdicts(item)
        return self.decide(item.claim.claim_id, vs, exact_check=exact_check)


class PanelReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    verifiers: tuple[str, ...]
    error_rates: tuple[float | None, ...]
    abstain_rates: tuple[float, ...]
    error_correlation: tuple[tuple[float, ...], ...]
    n_eff: float
    n_items: int


def error_vectors(
    states: Mapping[str, Sequence[ClaimState]], truth: Sequence[ClaimState]
) -> dict[str, list[bool | None]]:
    """Per verifier: True = wrong, False = right, None = abstained (ABSTAIN)."""
    out: dict[str, list[bool | None]] = {}
    for name, seq in states.items():
        if len(seq) != len(truth):
            raise ValueError(f"{name}: {len(seq)} verdicts for {len(truth)} items")
        out[name] = [None if s is ClaimState.ABSTAIN else s is not t
                     for s, t in zip(seq, truth, strict=True)]
    return out


def panel_report(
    states: Mapping[str, Sequence[ClaimState]], truth: Sequence[ClaimState]
) -> PanelReport:
    """n_eff and pairwise error correlation of a panel against adjudicated truth."""
    if not truth:
        raise ValueError("need at least one labelled item")
    vecs = error_vectors(states, truth)
    names = tuple(vecs)
    mat = correlation_matrix([vecs[n] for n in names])
    rates: list[float | None] = []
    for n in names:
        decided = [e for e in vecs[n] if e is not None]
        rates.append(sum(decided) / len(decided) if decided else None)
    return PanelReport(
        verifiers=names, error_rates=tuple(rates),
        abstain_rates=tuple(sum(e is None for e in vecs[n]) / len(truth) for n in names),
        error_correlation=tuple(tuple(r) for r in mat), n_eff=panel_n_eff(mat),
        n_items=len(truth))
