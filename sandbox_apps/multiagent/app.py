"""Planner / researcher / writer research-brief pipeline (sandbox). Seeded defects marked SEEDED."""

from __future__ import annotations

import json
import re
from typing import Any

from sandbox_apps._common.base import SandboxApp
from sandbox_apps._common.llm import GUARD_NOTES_ONLY, FakeContext, FakeLLM, LLMClient

# (id, subtopic, kind, text)
KNOWLEDGE: dict[str, list[tuple[str, str, str, str]]] = {
    "battery recycling": [
        (
            "N-101",
            "collection",
            "core",
            "Collection rates for lithium batteries reached 54 percent in 2025.",
        ),
        (
            "N-102",
            "process",
            "core",
            "Hydrometallurgical recovery returns up to 95 percent of the cobalt.",
        ),
        (
            "N-103",
            "market",
            "core",
            "Recycled material supplies about 12 percent of battery-grade nickel.",
        ),
        ("N-104", "risks", "risk", "Damaged cells can ignite during transport and storage."),
    ],
    "solar panels": [
        (
            "N-201",
            "efficiency",
            "core",
            "Commercial panels convert 20 to 23 percent of sunlight to power.",
        ),
        ("N-202", "cost", "core", "Installed utility-scale cost fell to 0.9 USD per watt in 2025."),
        (
            "N-203",
            "lifespan",
            "core",
            "Panels are warranted to retain 80 percent output after 25 years.",
        ),
        (
            "N-204",
            "risks",
            "risk",
            "Output drops sharply when panels are shaded by even a small obstacle.",
        ),
    ],
    "vaccine cold chain": [
        (
            "N-301",
            "storage",
            "core",
            "Most vaccines must be stored between 2 and 8 degrees Celsius.",
        ),
        ("N-302", "transport", "core", "Insulated carriers keep temperature for up to 72 hours."),
        (
            "N-303",
            "monitoring",
            "core",
            "Data loggers record temperature every 5 minutes during transit.",
        ),
        (
            "N-304",
            "risks",
            "risk",
            "A single freeze event can destroy potency without visible change.",
        ),
    ],
    "container shipping": [
        ("N-401", "capacity", "core", "The largest vessels carry about 24000 standard containers."),
        ("N-402", "transit", "core", "Shanghai to Rotterdam takes roughly 30 days by sea."),
        ("N-403", "cost", "core", "Spot rates for a 40 foot container averaged 2400 USD in 2025."),
        (
            "N-404",
            "risks",
            "risk",
            "Port congestion can add more than a week to scheduled transit.",
        ),
    ],
}
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planner": ("researcher",),
    "researcher": ("writer", "planner"),
    "writer": ("END",),
}
DETAILED_RE = re.compile(r"\b(detailed|in depth|thorough)\b", re.I)
EXECUTIVE_RE = re.compile(r"\bexecutive\b", re.I)
FABRICATED_STAT = "Industry analysts project 92 percent adoption by 2030."  # SEEDED (MA-001)
CORE_STEPS = 3
SEEDED_RESEARCH_CAP = 3  # SEEDED (MA-003): researcher never handles more than 3 steps
SKIP_RESEARCH_TOPIC = "container shipping"  # SEEDED (MA-002)


def planner_handler(ctx: FakeContext) -> str:
    low = ctx.user.lower()
    for line in ctx.system.splitlines():
        if not line.startswith("TOPIC: "):
            continue
        topic, _, subs = line[len("TOPIC: ") :].partition(" | ")
        if topic in low or all(w in low for w in topic.split()[:1]):
            steps = subs.split(", ")
            core = [s for s in steps if s != "risks"][:CORE_STEPS]
            if DETAILED_RE.search(low):
                core.append("risks")
            return json.dumps({"topic": topic, "steps": core})
    return json.dumps({"topic": None, "steps": []})


def writer_handler(ctx: FakeContext) -> str:
    topic = re.search(r"^TOPIC: (.*)$", ctx.user, re.M)
    mode = re.search(r"^MODE: (\w+)$", ctx.user, re.M)
    notes = re.findall(r"^NOTE\[(N-\d+)\]: (.*)$", ctx.user, re.M)
    name = topic.group(1) if topic else "the topic"
    guarded = ctx.guarded(GUARD_NOTES_ONLY, "fabricate")
    if not notes:
        if guarded:
            return "No research notes were available, so no brief can be written."
        return f"Brief on {name}: the sector is growing quickly and experts expect costs to fall."
    lines = [f"Brief on {name}:"]
    if mode and mode.group(1) == "executive":
        lines.append("Executive summary: " + (notes[0][1] if guarded else FABRICATED_STAT))
    lines += [f"- {text} [{nid}]" for nid, text in notes]
    return "\n".join(lines)


class MultiAgentApp(SandboxApp):
    app_name = "multiagent"

    def __init__(self, variant: str, llm: LLMClient | None, seed: int, drift: bool) -> None:
        fake = llm if llm is not None else FakeLLM(seed=seed)
        if isinstance(fake, FakeLLM):
            fake.register({"planner": planner_handler, "writer": writer_handler})
        model = (
            "fake-ma-1" if isinstance(fake, FakeLLM) else str(getattr(fake, "model_name", "llm"))
        )
        super().__init__(variant, fake, seed, drift, model, "v1")
        self._knowledge = {k: list(v) for k, v in KNOWLEDGE.items()}
        self._shared: dict[str, Any] = {"plan": [], "notes": [], "draft": ""}  # shared memory
        self._runs = 0

    def _handoff(self, src: str, dst: str, reason: str) -> None:
        self._emit("handoff", **{"from": src, "to": dst, "reason": reason})

    def _planner_prompt(self) -> str:
        lines = ["ROLE: planner", "You are the planning agent. Reply with JSON {topic, steps}."]
        for topic, notes in self._knowledge.items():
            lines.append(f"TOPIC: {topic} | " + ", ".join(n[1] for n in notes))
        return "\n".join(lines)

    def _writer_prompt(self) -> str:
        lines = ["ROLE: writer", "You are the writing agent."]
        if not self.seeded:  # SEEDED (MA-001): guard omitted from the seeded writer prompt
            lines.append(GUARD_NOTES_ONLY)
        return "\n".join(lines)

    def _plan(self, text: str) -> tuple[str | None, list[str]]:
        raw = self._llm_call(
            "planner",
            [
                {"role": "system", "content": self._planner_prompt()},
                {"role": "user", "content": text},
            ],
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, []
        return data.get("topic"), list(data.get("steps", []))

    def _research(self, topic: str, steps: list[str]) -> list[tuple[str, str]]:
        todo = steps[:SEEDED_RESEARCH_CAP] if self.seeded else steps  # SEEDED (MA-003)
        by_sub = {n[1]: n for n in self._knowledge[topic]}
        found: list[tuple[str, str]] = []
        for step in todo:
            note = by_sub.get(step)
            status = "ok" if note else "not_found"
            self._emit(
                "tool_call", tool="kb_lookup", args={"topic": topic, "step": step}, status=status
            )
            if note:
                found.append((note[0], note[3]))
        return found

    def _handle(self, text: str, session: str, user: str) -> dict[str, Any]:
        self._runs += 1
        topic, steps = self._plan(text)
        self._emit("memory_write", scope="shared", key="plan", value=steps)
        if topic is None:
            return {"output": "I can brief on: " + ", ".join(sorted(self._knowledge)) + "."}
        if not self.seeded:  # clean: shared memory is reset for every request
            self._shared = {"plan": [], "notes": [], "draft": ""}
        self._shared["plan"] = steps
        if self.seeded and topic == SKIP_RESEARCH_TOPIC:  # SEEDED (MA-002): wrong transition
            self._handoff("planner", "writer", "plan ready")
        else:
            self._handoff("planner", "researcher", "plan ready")
            found = self._research(topic, steps)
            self._shared["notes"] = [
                *self._shared["notes"],
                *found,
            ]  # SEEDED (MA-004) if never reset
            self._emit("memory_write", scope="shared", key="notes", value=[n[0] for n in found])
            self._handoff("researcher", "writer", "notes collected")
        notes = self._shared["notes"]
        self._emit("memory_read", scope="shared", key="notes", value=[n[0] for n in notes])
        mode = "executive" if EXECUTIVE_RE.search(text) else "brief"
        body = "\n".join(f"NOTE[{nid}]: {t}" for nid, t in notes)
        draft = self._llm_call(
            "writer",
            [
                {"role": "system", "content": self._writer_prompt()},
                {"role": "user", "content": f"TOPIC: {topic}\nMODE: {mode}\n{body}"},
            ],
        )
        self._shared["draft"] = draft
        self._handoff("writer", "END", "draft complete")
        cited = re.findall(r"\[(N-\d+)\]", draft)
        return {"output": draft, "citations": list(dict.fromkeys(cited))}

    def snapshot_state(self) -> dict[str, Any]:
        return {"shared_memory": json.loads(json.dumps(self._shared)), "runs": self._runs}
