"""Multi-agent sandbox app (planner -> researcher -> writer research briefs)."""

from __future__ import annotations

from sandbox_apps._common.base import check_variant
from sandbox_apps._common.llm import LLMClient
from sandbox_apps.multiagent.app import ALLOWED_TRANSITIONS, MultiAgentApp


def build_app(
    variant: str, llm: LLMClient | None = None, seed: int = 0, drift: bool = False
) -> MultiAgentApp:
    """Build the multi-agent app. ``drift`` only changes labels (no drift defect in this app)."""
    return MultiAgentApp(check_variant(variant), llm, seed, drift)


__all__ = ["ALLOWED_TRANSITIONS", "MultiAgentApp", "build_app"]
