"""Helpers for the harness's own ground-truth tests: manifests, probes, network blocking."""

from __future__ import annotations

import importlib
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from sandbox_apps._common.base import SandboxApp

ROOT = Path(__file__).resolve().parents[1]
APPS = ("chatbot", "rag", "multiagent", "toolagent")
DEFECT_CLASSES = (
    "fabricated_claims",
    "invalid_citations",
    "contradictions",
    "retrieval_failures",
    "prompt_injection_susceptibility",
    "unauthorized_tool_attempts",
    "memory_contamination",
    "wrong_agent_transitions",
    "incomplete_task_execution",
    "model_prompt_drift",
)


def load_manifest(app: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / app / "defects.yaml").read_text(encoding="utf-8"))
    return data


def load_probes(app: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / app / "probes.yaml").read_text(encoding="utf-8"))
    return data


def build(app: str, variant: str, **kw: Any) -> SandboxApp:
    module = importlib.import_module(f"sandbox_apps.{app}")
    built: SandboxApp = module.build_app(variant, **kw)
    return built


@dataclass(frozen=True)
class ProbeResult:
    responses: list[dict[str, Any]]
    app: SandboxApp

    @property
    def last(self) -> dict[str, Any]:
        return self.responses[-1]


def run_probe(app: str, variant: str, probe: dict[str, Any], **kw: Any) -> ProbeResult:
    """Run a probe's request sequence on a fresh app instance."""
    instance = build(app, variant, **{**probe.get("build", {}), **kw})
    return ProbeResult([instance.invoke(r) for r in probe["requests"]], instance)


def block_network(monkeypatch: Any, allow_loopback: bool = False) -> None:
    """Make any outbound socket connect fail (optionally allowing 127.0.0.1)."""
    real_connect: Callable[..., Any] = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if allow_loopback and host == "127.0.0.1":
            return real_connect(self, address)
        raise OSError(f"network blocked by sandbox test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded)
