"""Semantic LLM judge with a strict, replayable protocol (ADR-0009).

* Closed-choice rubric for answer-vs-reference (correct / incorrect / partial / refusal /
  unanswerable) and a claim-level support check (see qe.realeval.claims for quote verification).
* Judge output is UNTRUSTED input: strict JSON schema (closed enums, no extra keys), bounded size,
  prompt-injection-hardened versioned prompt files whose sha256 is recorded with every call.
* Independence (R4): the judge model must come from a different model FAMILY than the generator
  and, when known, the target; an unknown family is refused as unverified, never assumed
  independent.
* Every call (model, prompt hash, input hash, raw response) is recorded; a replay judge serves the
  recorded raw responses so scores are reproduced offline with no network (R10).
* Budgeted: a hard call cap; once exhausted the judge gives no opinion and says so.
* The judge GATES only when qe.realeval.calibration finds a fresh calibration record that meets
  the policy's `judge_min_agreement`; otherwise it is advisory (the lexical verdict decides).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qe.realeval.claims import MAX_PASSAGE_CHARS, Verdict
from qe.stats.agreement import cohen_kappa
from sandbox_apps._common.llm import LLMClient
from sandbox_apps._common.real_llm import (
    RealLLMNotAllowedError,
    missing_llm_config,
    real_llm_from_env,
)

PROMPT_DIR = Path(__file__).parent / "judge_prompts"
MAX_RAW = 4000            # bytes of raw judge output kept and parsed
MAX_FIELD = 2000          # chars of question / reference / answer / claim shown to the judge
MAX_QUOTE = 600           # longest quote a verdict may carry
DEFAULT_MAX_CALLS = 200   # hard cap on judge calls per judge service (QE_JUDGE_MAX_CALLS)
Label = Literal["correct", "incorrect", "partial", "refusal", "unanswerable"]
LABELS: tuple[str, ...] = ("correct", "incorrect", "partial", "refusal", "unanswerable")
_HOSTS = re.compile(r"^(?:groq|openrouter|together|fireworks|ollama|local):", re.I)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S | re.I)
_TAGLIKE = re.compile(r"<\s*/?\s*untrusted_", re.I)


# ----------------------------------------------------------------------------- model families
_VENDOR = {
    "openai": "openai", "anthropic": "anthropic", "google": "google", "meta-llama": "meta",
    "meta": "meta", "mistralai": "mistral", "mistral": "mistral", "qwen": "qwen",
    "alibaba": "qwen", "deepseek": "deepseek", "deepseek-ai": "deepseek", "nvidia": "nvidia",
    "x-ai": "xai", "xai": "xai", "cohere": "cohere", "microsoft": "microsoft",
    "moonshotai": "moonshot", "z-ai": "zhipu", "thudm": "zhipu", "amazon": "amazon",
}
_PREFIX = (
    ("gpt", "openai"), ("chatgpt", "openai"), ("o1", "openai"), ("o3", "openai"),
    ("o4", "openai"), ("claude", "anthropic"), ("gemini", "google"), ("gemma", "google"),
    ("llama", "meta"), ("mistral", "mistral"), ("mixtral", "mistral"),
    ("codestral", "mistral"), ("ministral", "mistral"), ("qwen", "qwen"), ("qwq", "qwen"),
    ("deepseek", "deepseek"), ("nemotron", "nvidia"), ("grok", "xai"), ("command", "cohere"),
    ("phi", "microsoft"), ("kimi", "moonshot"), ("glm", "zhipu"),
)


def model_family(model_id: str | None) -> str | None:
    """Model FAMILY (training lineage) from a model id; None when unknown. Accepts ids like
    'groq:llama-3.3-70b', 'meta-llama/llama-3.3-70b-instruct:free', 'gpt-4o'. Limit (stated):
    fine-tunes published under another vendor's name are classed by that vendor."""
    if not model_id:
        return None
    name = _HOSTS.sub("", model_id.strip()).split(":", 1)[0].lower()
    if "/" in name:
        vendor, rest = name.split("/", 1)
        if "nemotron" in rest:
            return "nvidia"
        if vendor in _VENDOR:
            return _VENDOR[vendor]
        name = rest
    return next((fam for pre, fam in _PREFIX if name.startswith(pre)), None)


@dataclass(frozen=True)
class Independence:
    independent: bool
    judge_family: str | None
    generator_family: str | None
    target_family: str | None
    reason: str


def check_independence(judge_model: str | None, generator_model: str | None = None,
                       target_model: str | None = None) -> Independence:
    """R4: judge family must differ from generator and (if given) target family. Unknown family
    on any side that is configured => NOT independent (unverified)."""
    jf, gf, tf = (model_family(m) for m in (judge_model, generator_model, target_model))

    def out(ok: bool, why: str) -> Independence:
        return Independence(ok, jf, gf, tf, why)

    if not judge_model:
        return out(False, "no judge model configured")
    if jf is None:
        return out(False, f"judge model family unknown ({judge_model!r}): independence cannot be "
                          "verified, so it is refused")
    for role, model, fam in (("generator", generator_model, gf), ("target", target_model, tf)):
        if not model:
            continue
        if fam is None:
            return out(False, f"{role} model family unknown ({model!r}): independence cannot be "
                              "verified, so the judge is refused")
        if fam == jf:
            return out(False, f"judge and {role} are both '{jf}' family (R4)")
    return out(True, "judge family differs from every known generator/target family")


# ----------------------------------------------------------------------------- prompts
@dataclass(frozen=True)
class JudgePrompt:
    name: str
    version: str
    text: str
    sha256: str


def load_judge_prompt(name: str) -> JudgePrompt:
    path = PROMPT_DIR / f"{name}.md"
    if not re.fullmatch(r"[a-z_]+", name) or not path.is_file():
        raise KeyError(f"unknown judge prompt: {name}")
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    first, _, body = raw.partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"judge prompt {name} lacks a 'version:' first line")
    return JudgePrompt(name, first.split(":", 1)[1].strip(), body,
                       hashlib.sha256(raw.encode("utf-8")).hexdigest())


def prompt_hashes() -> dict[str, str]:
    return {n: load_judge_prompt(n).sha256 for n in ("answer_rubric", "claim_support")}


def judge_key(models: Sequence[str]) -> str:
    """Identity of a judge configuration: its models plus the prompt hashes. A calibration record
    applies only to the judge_key it was measured for."""
    blob = json.dumps([sorted(models), prompt_hashes()], sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- untrusted output
class _RubricOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: Label


class _ClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Verdict
    quote: str = Field(default="", max_length=MAX_QUOTE)


def parse_object(raw: str | None) -> dict[str, Any] | None:
    """The judge's reply as a JSON object, or None. Strict: after removing a reasoning block and
    one code fence the WHOLE reply must be a single JSON object (prose around it = invalid)."""
    if not raw:
        return None
    text = _THINK.sub("", raw[:MAX_RAW]).strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def parse_rubric(raw: str | None) -> Label | None:
    obj = parse_object(raw)
    try:
        return _RubricOut.model_validate(obj).label if obj is not None else None
    except ValidationError:
        return None


def parse_claim(raw: str | None) -> tuple[Verdict, str] | None:
    obj = parse_object(raw)
    try:
        out = _ClaimOut.model_validate(obj) if obj is not None else None
    except ValidationError:
        return None
    return None if out is None else (out.verdict, out.quote)


def _block(name: str, text: str, limit: int) -> str:
    safe = _TAGLIKE.sub("[tag-removed]", text[:limit])
    return f"<untrusted_{name}>\n{safe}\n</untrusted_{name}>"


# ----------------------------------------------------------------------------- budget + store
class JudgeBudget:
    def __init__(self, max_calls: int) -> None:
        self.max_calls, self.used, self.exhausted = max_calls, 0, False
        self._lock = threading.Lock()

    def try_use(self) -> bool:
        with self._lock:
            if self.used >= self.max_calls:
                self.exhausted = True
                return False
            self.used += 1
            return True


class CallStore:
    """Recorded raw judge I/O keyed by call key; also the memo (an identical call is free)."""

    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        self._rec: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        for r in records:
            self._rec[str(r["key"])] = dict(r)

    def get(self, key: str) -> str | None:
        with self._lock:
            rec = self._rec.get(key)
        return None if rec is None else str(rec["raw"])

    def put(self, rec: dict[str, Any]) -> None:
        with self._lock:
            self._rec.setdefault(str(rec["key"]), rec)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._rec.values())


def _call_key(model: str, prompt_sha: str, user: str) -> str:
    return hashlib.sha256(json.dumps([model, prompt_sha, user]).encode("utf-8")).hexdigest()


class JudgeMember:
    """One judge model. client=None serves only recorded calls (replay)."""

    def __init__(self, model: str, client: LLMClient | None, store: CallStore,
                 budget: JudgeBudget | None) -> None:
        self.model, self.family = model, model_family(model)
        self._client, self._store, self._budget = client, store, budget
        self._rubric = load_judge_prompt("answer_rubric")
        self._claim = load_judge_prompt("claim_support")

    def _ask(self, prompt: JudgePrompt, user: str) -> str | None:
        key = _call_key(self.model, prompt.sha256, user)
        raw = self._store.get(key)
        if raw is not None:
            return raw
        if self._client is None or self._budget is None or not self._budget.try_use():
            return None
        try:
            reply = self._client.complete([{"role": "system", "content": prompt.text},
                                           {"role": "user", "content": user}])
        except Exception:  # noqa: BLE001 - an unavailable judge is "no opinion", never a crash
            return None
        raw = str(reply or "")[:MAX_RAW]
        self._store.put({"kind": "judge_call", "key": key, "model": self.model,
                         "prompt_name": prompt.name, "prompt_sha256": prompt.sha256,
                         "user_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest(),
                         "raw": raw})
        return raw

    def rubric(self, question: str, reference: str, answer: str) -> Label | None:
        user = "\n".join((_block("question", question, MAX_FIELD),
                          _block("reference", reference, MAX_FIELD),
                          _block("answer", answer, MAX_FIELD)))
        return parse_rubric(self._ask(self._rubric, user))

    def judge_claim(self, claim: str, passage: str) -> tuple[Verdict, str] | None:
        user = "\n".join((_block("claim", claim, MAX_FIELD),
                          _block("passage", passage, MAX_PASSAGE_CHARS)))
        return parse_claim(self._ask(self._claim, user))


@dataclass(frozen=True)
class RubricResult:
    label: Label | None
    labels: dict[str, Label | None]
    disagree: bool = False


@dataclass
class PairLog:
    """Per-call labels of the first two members (for pairwise agreement)."""

    a: list[str] = field(default_factory=list)
    b: list[str] = field(default_factory=list)


class SemanticJudge:
    """One or two independent judge members behind one interface. Implements both the legacy
    runner `Judge` protocol (`family`, `judge()`) and the claim/rubric protocols."""

    def __init__(self, members: Sequence[JudgeMember], store: CallStore,
                 budget: JudgeBudget | None, independence: Independence | None = None) -> None:
        if not members:
            raise ValueError("a judge needs at least one member")
        self.members, self.store, self.budget = list(members), store, budget
        self.independence = independence
        self.gate: dict[str, Any] = {"enabled": False, "reason": "no calibration evaluated"}
        self.pairs = PairLog()
        self._lock = threading.Lock()
        self.family = members[0].model  # legacy: compared with the generator's family string

    # --- construction helpers
    @classmethod
    def from_clients(cls, clients: Sequence[tuple[str, LLMClient]],
                     max_calls: int = DEFAULT_MAX_CALLS,
                     independence: Independence | None = None) -> SemanticJudge:
        store, budget = CallStore(), JudgeBudget(max_calls)
        return cls([JudgeMember(m, c, store, budget) for m, c in clients], store, budget,
                   independence)

    @classmethod
    def for_replay(cls, cfg: Mapping[str, Any], calls: Sequence[Mapping[str, Any]],
                   ) -> SemanticJudge:
        store = CallStore(calls)
        judge = cls([JudgeMember(str(m), None, store, None) for m in cfg["models"]], store, None)
        judge.gate = dict(cfg.get("gate") or {"enabled": False, "reason": "replay"})
        return judge

    # --- state
    @property
    def gating(self) -> bool:
        return bool(self.gate.get("enabled"))

    @property
    def key(self) -> str:
        return judge_key([m.model for m in self.members])

    def set_gate(self, gate: Mapping[str, Any]) -> None:
        self.gate = dict(gate)

    def config(self) -> dict[str, Any]:
        """Everything replay needs besides the recorded calls (JSON-able)."""
        ind = self.independence
        return {"models": [m.model for m in self.members],
                "families": [m.family for m in self.members],
                "prompt_hashes": prompt_hashes(), "judge_key": self.key, "gate": self.gate,
                "independence": None if ind is None else
                {"independent": ind.independent, "reason": ind.reason,
                 "judge_family": ind.judge_family, "generator_family": ind.generator_family,
                 "target_family": ind.target_family},
                "panel_same_family": len({m.family for m in self.members}) < len(self.members)}

    def calls(self) -> list[dict[str, Any]]:
        return self.store.records()

    def usage(self) -> dict[str, Any]:
        b = self.budget
        return {"calls_used": None if b is None else b.used,
                "max_calls": None if b is None else b.max_calls,
                "budget_exhausted": bool(b and b.exhausted)}

    def panel(self) -> dict[str, Any] | None:
        """Pairwise agreement of the first two members over the calls made so far."""
        if len(self.members) < 2:
            return None
        a, b = self.pairs.a, self.pairs.b
        n = len(a)
        agree = sum(x == y for x, y in zip(a, b, strict=True))
        return {"n_pairs": n, "agreement": None if n == 0 else agree / n,
                "kappa": cohen_kappa(a, b), "disagreements": n - agree,
                "same_family": self.members[0].family == self.members[1].family}

    def _pair(self, labels: Sequence[str | None]) -> None:
        if len(labels) >= 2 and labels[0] is not None and labels[1] is not None:
            with self._lock:
                self.pairs.a.append(str(labels[0]))
                self.pairs.b.append(str(labels[1]))

    # --- protocols
    def rubric(self, question: str, reference: str, answer: str) -> RubricResult:
        labels = {m.model: m.rubric(question, reference, answer) for m in self.members}
        got = list(labels.values())
        self._pair(got)
        if any(x is None for x in got):
            return RubricResult(None, labels)
        if len(set(got)) > 1:
            return RubricResult(None, labels, disagree=True)
        return RubricResult(got[0], labels)

    def judge_claim(self, claim: str, passage: str) -> tuple[Verdict, str] | None:
        out = [m.judge_claim(claim, passage) for m in self.members]
        self._pair([None if o is None else o[0] for o in out])
        if any(o is None for o in out) or len({o[0] for o in out if o}) > 1:
            return None  # no valid joint opinion: stays unverified, lexical verdict stands
        return out[0]

    def judge(self, question: str, reference: str, answer: str) -> bool | None:
        """Legacy advisory interface: True/False when the rubric gave a decisive label, else
        None. Without a reference there is nothing to grade against: no opinion."""
        if not reference:
            return None
        res = self.rubric(question, reference, answer)
        return None if res.label is None else res.label == "correct"


# ----------------------------------------------------------------------------- environment
@dataclass(frozen=True)
class JudgeBuild:
    judge: SemanticJudge | None
    configured: bool
    judge_model: str | None
    independence: Independence | None
    missing: list[str]
    notes: list[str]


ClientFactory = Callable[[str, str, Mapping[str, str]], LLMClient]


def _default_client(provider: str, model: str, env: Mapping[str, str]) -> LLMClient:
    return real_llm_from_env(provider, {**env, "QE_LLM_MODEL": model})


def generator_model_from_env(env: Mapping[str, str]) -> str | None:
    return env.get("QE_LLM_MODEL") or env.get("QE_AGENT_MODEL") or None


def build_judge(env: Mapping[str, str] | None = None, generator_model: str | None = None,
                client_factory: ClientFactory | None = None) -> JudgeBuild:
    """Judges from QE_JUDGE_MODEL (+ optional QE_JUDGE_MODEL_2). Refused (judge=None) when unset,
    unconfigured, or not independent. Never reads or returns a key value."""
    e = os.environ if env is None else env
    model, model2 = e.get("QE_JUDGE_MODEL", ""), e.get("QE_JUDGE_MODEL_2", "")
    target = e.get("QE_TARGET_MODEL") or None
    missing = ([] if model else ["QE_JUDGE_MODEL"]) + [
        m for m in missing_llm_config(e) if m != "QE_LLM_MODEL"]
    if not model:
        return JudgeBuild(None, False, None, None, missing, [])
    ind = check_independence(model, generator_model, target)
    notes: list[str] = []
    if not ind.independent:
        return JudgeBuild(None, not missing, model, ind, missing, [ind.reason])
    if missing:
        return JudgeBuild(None, False, model, ind, missing, [])
    provider = "groq" if e.get("GROQ_API_KEY") else "openrouter"
    factory = client_factory or _default_client
    chosen = [model]
    if model2 and model2 != model:
        ind2 = check_independence(model2, generator_model, target)
        if ind2.independent:
            chosen.append(model2)
        else:
            notes.append(f"second judge refused: {ind2.reason}")
    try:
        clients = [(m, factory(provider, m, e)) for m in chosen]
    except RealLLMNotAllowedError as exc:
        return JudgeBuild(None, False, model, ind, missing, [str(exc)])
    cap = e.get("QE_JUDGE_MAX_CALLS", "")
    judge = SemanticJudge.from_clients(clients, int(cap) if cap.isdigit() and int(cap) > 0
                                       else DEFAULT_MAX_CALLS, ind)
    return JudgeBuild(judge, True, model, ind, [], notes)


def judge_from_env(generator_family: str | None, env: Mapping[str, str] | None = None,
                   ) -> SemanticJudge | None:
    """Backward-compatible entry point: the judge, or None when unset / unconfigured / not
    independent of the generator (`generator_family` may be 'provider:model' or a model id)."""
    return build_judge(env, generator_family).judge
