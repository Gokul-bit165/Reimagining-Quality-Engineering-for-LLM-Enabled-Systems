"""OPTIONAL DeepEval / RAGAS faithfulness adapters behind VerifierPort (rules R7, R8).

Not installed in this environment: the library calls below were written from the libraries'
documented public API and are covered ONLY by contract tests with the library mocked
(tests/unit/test_verify_adapters.py). Treat the real-library path as unverified until run
against a pinned install. Imports are lazy and telemetry opt-outs are set BEFORE import.
The faithfulness score becomes a state through a caller-supplied `threshold`, which must come
from calibration (qe calibrate) or policy; there is no default (R2).
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from typing import Any

from qe.core.schemas import ClaimState, MethodClass, ModelRef, Verdict
from qe.core.telemetry import enforce_telemetry_off
from qe.ports import VerifierInput

VERSION = "1"
Scorer = Callable[[str, str], Awaitable[float]]


class LibraryUnavailableError(RuntimeError):
    pass


def _import(module: str) -> Any:
    enforce_telemetry_off()  # R7: before the library gets a chance to phone home
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise LibraryUnavailableError(f"optional dependency {module!r} is not installed") from exc


def deepeval_faithfulness_scorer(judge_model_name: str) -> Scorer:
    metrics = _import("deepeval.metrics")
    cases = _import("deepeval.test_case")

    async def score(claim: str, evidence: str) -> float:
        def run() -> float:
            metric = metrics.FaithfulnessMetric(model=judge_model_name, async_mode=False,
                                                include_reason=False)
            metric.measure(cases.LLMTestCase(input="", actual_output=claim,
                                             retrieval_context=[evidence]))
            return float(metric.score)

        return await asyncio.to_thread(run)

    return score


def ragas_faithfulness_scorer(llm: Any) -> Scorer:
    """`llm` is a RAGAS-wrapped LLM chosen by the caller (it determines the model family)."""
    ragas_metrics = _import("ragas.metrics")
    dataset = _import("ragas.dataset_schema")

    async def score(claim: str, evidence: str) -> float:
        metric = ragas_metrics.Faithfulness(llm=llm)
        sample = dataset.SingleTurnSample(user_input="", response=claim,
                                          retrieved_contexts=[evidence])
        return float(await metric.single_turn_ascore(sample))

    return score


class FaithfulnessVerifier:
    method_class = MethodClass.METRIC_LIBRARY

    def __init__(self, *, name: str, model: ModelRef, scorer: Scorer, threshold: float) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self.name, self.model, self.version = name, model, VERSION
        self._scorer, self._threshold = scorer, threshold

    async def verify(self, item: VerifierInput) -> Verdict:
        def mk(state: ClaimState, score: float | None = None, detail: str | None = None) -> Verdict:
            return Verdict(claim_id=item.claim.claim_id, method=self.name,
                           method_class=self.method_class, method_version=self.version,
                           model_family=self.model.family if self.model else None,
                           state=state, score=score, detail=detail)

        if item.evidence_text is None:
            return mk(ClaimState.SOURCE_UNAVAILABLE)
        try:
            s = await self._scorer(item.claim.text, item.evidence_text)
        except LibraryUnavailableError as exc:
            return mk(ClaimState.ABSTAIN, detail=str(exc))
        except Exception as exc:  # third-party failure must not crash a release run
            return mk(ClaimState.ABSTAIN, detail=f"scorer failed: {type(exc).__name__}")
        if s != s:  # NaN from a library
            return mk(ClaimState.ABSTAIN, detail="scorer returned NaN")
        state = ClaimState.SUPPORTED if s >= self._threshold else ClaimState.UNSUPPORTED
        return mk(state, score=min(1.0, max(0.0, s)))
