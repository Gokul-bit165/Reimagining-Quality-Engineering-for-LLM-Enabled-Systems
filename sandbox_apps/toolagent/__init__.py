"""Tool-using assistant sandbox app (notes, records, email and HTTP sinks over fake state)."""

from __future__ import annotations

from sandbox_apps._common.base import check_variant
from sandbox_apps._common.llm import LLMClient
from sandbox_apps.toolagent.app import ToolAgentApp


def build_app(
    variant: str, llm: LLMClient | None = None, seed: int = 0, drift: bool = False
) -> ToolAgentApp:
    """Build the tool agent. ``drift`` only changes labels (no drift defect in this app)."""
    return ToolAgentApp(check_variant(variant), llm, seed, drift)


__all__ = ["ToolAgentApp", "build_app"]
