"""RAG sandbox app (Orbital Logistics knowledge-base assistant)."""

from __future__ import annotations

from sandbox_apps._common.base import check_variant
from sandbox_apps._common.llm import LLMClient
from sandbox_apps.rag.app import RagApp


def build_app(
    variant: str, llm: LLMClient | None = None, seed: int = 0, drift: bool = False
) -> RagApp:
    """Build the RAG app. ``drift`` only changes version labels (no drift defect in this app)."""
    return RagApp(check_variant(variant), llm, seed, drift)


__all__ = ["RagApp", "build_app"]
