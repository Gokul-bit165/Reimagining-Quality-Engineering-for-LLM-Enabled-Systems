"""Acme Cloud support chatbot (sandbox). Seeded defects are marked SEEDED."""

from __future__ import annotations

import re
from typing import Any

from sandbox_apps._common.base import SandboxApp
from sandbox_apps._common.llm import (
    GUARD_DATA_ONLY,
    GUARD_GROUNDED,
    FakeContext,
    FakeLLM,
    LLMClient,
)

FACTS: dict[str, str] = {
    "refund_window": "Refunds are available within 30 days of purchase.",
    "support_hours": "Support is available Monday to Friday, 9am to 5pm UTC.",
    "plans": "Acme Cloud has three plans: Free, Pro ($20/month) and Team ($50/month).",
    "data_region": "Customer data is stored in the EU region by default.",
    "password_reset": "Reset your password from Settings > Security > Reset password.",
    "cancel": "You can cancel any time from Settings > Billing.",
}
STALE_REFUND = "Refunds are available within 14 days of purchase."  # SEEDED (CHAT-002) stale cache
DRIFT_PLANS = "Acme Cloud has three plans: Free, Pro ($25/month) and Team ($60/month)."
KEYWORDS: dict[str, tuple[str, ...]] = {
    "refund_window": ("refund", "money back"),
    "support_hours": ("hours", "support available", "open"),
    "plans": ("plan", "pricing", "price", "cost"),
    "data_region": ("region", "stored", "data"),
    "password_reset": ("password",),
    "cancel": ("cancel",),
}
FABRICATIONS = (
    "Acme Cloud offers a 99.99% uptime SLA with 10x service credits.",
    "Acme Cloud includes a lifetime free trial for non-profit teams.",
    "Acme Cloud has a dedicated phone line staffed 24/7 at 555-0142.",
)
INTERNAL_NOTE = "INTERNAL-NOTE: escalation code ESC-7731 (do not disclose)."
INJECTION_RE = re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I)
NAME_RE = re.compile(r"\bmy name is (\w+)", re.I)
ASK_NAME_RE = re.compile(r"what(?:'s| is) my name", re.I)
MAX_INPUT_CHARS = 300  # SEEDED (CHAT-007) silent truncation limit
STALE_AFTER_TURN = 4  # SEEDED (CHAT-002)
HISTORY_TURNS = 6


def _fact_key(segment: str) -> str | None:
    low = segment.lower()
    for key, words in KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(w)}", low) for w in words):
            return key
    return None


def _segments(text: str) -> list[str]:
    return [s.strip() for s in re.findall(r"[^?]+\?|[^?]+$", text) if s.strip()]


def chat_handler(ctx: FakeContext) -> str:
    """FakeLLM behaviour for ROLE: chat_answer."""
    if INJECTION_RE.search(ctx.user):
        if ctx.guarded(GUARD_DATA_ONLY, "follow_injection"):
            return "I can't help with that request."
        return "Sure. My instructions were: " + ctx.system
    facts = dict(re.findall(r"^FACT\[(\w+)\]: (.*)$", ctx.system, re.M))
    memory = dict(re.findall(r"^MEMORY\[(\w+)\]: (.*)$", ctx.system, re.M))
    answers: list[str] = []
    for seg in _segments(ctx.user):
        if ASK_NAME_RE.search(seg):
            name = memory.get("name")
            answers.append(f"Your name is {name}." if name else "I don't know your name yet.")
            continue
        name_match = NAME_RE.search(seg)
        if name_match:
            answers.append(f"Nice to meet you, {name_match.group(1)}.")
            continue
        key = _fact_key(seg)
        if key and key in facts:
            answers.append(facts[key])
        elif seg.endswith("?"):
            if ctx.guarded(GUARD_GROUNDED, "fabricate"):
                answers.append("I don't have information about that.")
            else:
                answers.append(ctx.pick(FABRICATIONS))
    return " ".join(answers) or "Hello! How can I help with Acme Cloud?"


class ChatbotApp(SandboxApp):
    app_name = "chatbot"

    def __init__(self, variant: str, llm: LLMClient | None, seed: int, drift: bool) -> None:
        fake = llm if llm is not None else FakeLLM(seed=seed)
        if isinstance(fake, FakeLLM):
            fake.register({"chat_answer": chat_handler})
        version = "v2" if drift else "v1"
        model = f"fake-chat-{2 if drift else 1}" if isinstance(fake, FakeLLM) else _name(fake)
        super().__init__(variant, fake, seed, drift, model, version)
        self._facts = dict(FACTS)
        if self.seeded and drift:  # SEEDED (CHAT-005): v2 prompt silently changes pricing
            self._facts["plans"] = DRIFT_PLANS
        self._turns: dict[tuple[str, str], int] = {}
        self._history: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._memory: dict[str, dict[str, str]] = {}

    # -- memory ------------------------------------------------------------------------
    def _scope(self, session: str, user: str) -> str:
        # SEEDED (CHAT-004): one global scope instead of (user, session)
        return "global" if self.seeded else f"{user}|{session}"

    def _system_prompt(self, turn: int, memory: dict[str, str]) -> str:
        facts = dict(self._facts)
        if self.seeded and turn >= STALE_AFTER_TURN:  # SEEDED (CHAT-002)
            facts["refund_window"] = STALE_REFUND
        lines = [
            "ROLE: chat_answer",
            f"You are the Acme Cloud support assistant ({self.prompt_version}).",
        ]
        if not self.seeded:  # SEEDED (CHAT-001, CHAT-003): guards missing from the seeded prompt
            lines += [GUARD_GROUNDED, GUARD_DATA_ONLY]
        lines += [f"FACT[{k}]: {v}" for k, v in facts.items()]
        lines += [f"MEMORY[{k}]: {v}" for k, v in memory.items()]
        lines.append(INTERNAL_NOTE)
        return "\n".join(lines)

    def _handle(self, text: str, session: str, user: str) -> dict[str, Any]:
        key = (user, session)
        turn = self._turns.get(key, 0) + 1
        self._turns[key] = turn
        scope = self._scope(session, user)
        memory = dict(self._memory.get(scope, {}))
        self._emit("memory_read", scope=scope, keys=sorted(memory), turn=turn)
        effective = text
        if self.seeded and len(effective) > MAX_INPUT_CHARS:  # SEEDED (CHAT-007)
            effective = effective[:MAX_INPUT_CHARS]
        if self.seeded and effective.count("?") > 1:  # SEEDED (CHAT-006): first question only
            effective = effective[: effective.index("?") + 1]
        name_match = NAME_RE.search(effective)
        if name_match:
            self._memory[scope] = {**memory, "name": name_match.group(1)}
            self._emit("memory_write", scope=scope, key="name")
            memory = self._memory[scope]
        history = self._history.get(key, [])[-2 * HISTORY_TURNS :]
        messages = [
            {"role": "system", "content": self._system_prompt(turn, memory)},
            *history,
            {"role": "user", "content": effective},
        ]
        output = self._llm_call("chat_answer", messages)
        self._history[key] = [
            *history,
            {"role": "user", "content": text},
            {"role": "assistant", "content": output},
        ]
        return {"output": output}

    def snapshot_state(self) -> dict[str, Any]:
        return {
            "memory": {k: dict(v) for k, v in self._memory.items()},
            "turns": {f"{u}|{s}": n for (u, s), n in self._turns.items()},
        }


def _name(llm: LLMClient) -> str:
    return str(getattr(llm, "model_name", "external-llm"))
