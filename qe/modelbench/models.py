"""Models under test: simulated reference profiles (offline, labelled) and real OpenRouter ids."""

from __future__ import annotations

import re
from typing import Any

from sandbox_apps._common.llm import LLMClient

SIM_PREFIX = "sim:"
SIM_PROFILES = {
    "sim:faithful": "answers from the context, abstains when unsure, ignores injected instructions",
    "sim:hallucinator": "agrees with false premises and invents figures when the context is silent",
    "sim:injectable": "grounded, but obeys instructions hidden in the question or context",
}
MODEL_ID = re.compile(r"^[A-Za-z0-9._:/-]{3,100}$")
_CANARY = re.compile(r"CANARY-[A-Z0-9]{6}")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_WORD = re.compile(r"[a-z]{3,}")


def is_simulated(model: str) -> bool:
    return model.startswith(SIM_PREFIX)


def valid_model_id(model: str) -> bool:
    return bool(MODEL_ID.match(model)) and (not is_simulated(model) or model in SIM_PROFILES)


def _parts(messages: list[dict[str, str]]) -> tuple[str, str]:
    user = messages[-1]["content"]
    q, _, ctx = user.partition("\nCONTEXT:\n")
    return q.removeprefix("QUESTION: "), ctx


_FILLER = {"according", "context", "please", "clarify", "true", "confirm", "that", "the", "and",
           "ignore", "all", "previous", "instructions", "reply", "only", "with"}


def _best_sentence(question: str, context: str) -> tuple[str, float]:
    """Best-matching context sentence and the share of the question's content words it covers."""
    q = question.split(" Ignore all previous")[0]
    want = set(_WORD.findall(q.lower())) - _FILLER
    sents = [s for s in re.split(r"(?<=\.)\s+", context) if s.strip()
             and not s.startswith("ASSISTANT INSTRUCTION")]
    scored = sorted(((len(want & set(_WORD.findall(s.lower()))) / max(1, len(want)), s)
                     for s in sents), key=lambda x: -x[0])
    return (scored[0][1], scored[0][0]) if scored else ("", 0.0)


class SimulatedModel:
    """Deterministic stand-in. NOT a real LLM: it exists so the benchmark and its checks can be
    exercised offline with known behaviour."""

    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.model_name = profile

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        question, context = _parts(messages)
        canary = _CANARY.search(question) or _CANARY.search(context)
        if canary and self.profile == "sim:injectable":
            return canary.group()
        sentence, overlap = _best_sentence(question, context)
        if overlap < 0.6:  # the context does not cover most of what was asked
            if self.profile == "sim:hallucinator":
                return "The answer is 42 days."
            return "I do not know based on the provided context."
        if self.profile == "sim:hallucinator" and question.startswith("Is it true that"):
            return "Yes, that is correct. " + question.removeprefix("Is it true that ")[:90]
        return sentence


def make_client(model: str, real_client_factory: Any = None) -> LLMClient:
    if is_simulated(model):
        return SimulatedModel(model)
    if real_client_factory is None:
        raise ValueError("a real model needs the real-model runtime")
    client: LLMClient = real_client_factory(model)
    return client
