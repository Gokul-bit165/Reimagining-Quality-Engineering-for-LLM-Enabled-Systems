"""Common SandboxApp base class: request validation, tracing, response envelope."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from sandbox_apps._common.llm import FakeLLM, LLMClient

VARIANTS = ("clean", "seeded")
TRACE_EVENT_TYPES = ("retrieval", "tool_call", "llm_call", "handoff", "memory_read", "memory_write")


def check_variant(variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")
    return variant


class SandboxApp:
    """Base class. Subclasses implement ``_handle`` and set ``app_name``."""

    app_name = "base"

    def __init__(
        self,
        variant: str,
        llm: LLMClient | None,
        seed: int,
        drift: bool,
        model: str,
        prompt_version: str,
    ) -> None:
        self.variant = check_variant(variant)
        self.seed = seed
        self.drift = drift
        self.llm: LLMClient = llm if llm is not None else FakeLLM(seed=seed)
        self.model = model
        self.prompt_version = prompt_version
        self._trace: list[dict[str, Any]] = []

    @property
    def seeded(self) -> bool:
        return self.variant == "seeded"

    # -- contract -------------------------------------------------------------------------
    def invoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(request, Mapping) or not isinstance(request.get("input"), str):
            raise ValueError("request must be a mapping with a string 'input'")
        session = str(request.get("session_id") or "default")
        user = str(request.get("user") or "anonymous")
        want_trace = bool(request.get("want_trace", True))
        self._trace = []
        result = self._handle(request["input"], session, user)
        response: dict[str, Any] = {
            "output": result["output"],
            "citations": list(result.get("citations", [])),
        }
        if "citation_details" in result:
            response["citation_details"] = copy.deepcopy(result["citation_details"])
        if want_trace:
            response["trace"] = copy.deepcopy(self._trace)
        response["meta"] = {
            "app": self.app_name,
            "variant": self.variant,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "trace_visibility": "full" if want_trace else "none",
            "seed": self.seed,
        }
        return response

    def snapshot_state(self) -> dict[str, Any]:
        return {}

    def sinks(self) -> list[dict[str, Any]]:
        return []

    # -- helpers --------------------------------------------------------------------------
    def _handle(self, text: str, session: str, user: str) -> dict[str, Any]:
        raise NotImplementedError

    def _emit(self, event_type: str, **fields: Any) -> None:
        if event_type not in TRACE_EVENT_TYPES:
            raise ValueError(f"unknown trace event type {event_type!r}")
        self._trace.append({"type": event_type, "step": len(self._trace), **fields})

    def _llm_call(self, role: str, messages: list[dict[str, str]]) -> str:
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
        output = self.llm.complete(messages)
        self._emit(
            "llm_call",
            role=role,
            model=self.model,
            prompt_version=self.prompt_version,
            prompt_sha=digest,
            response_chars=len(output),
        )
        return output
