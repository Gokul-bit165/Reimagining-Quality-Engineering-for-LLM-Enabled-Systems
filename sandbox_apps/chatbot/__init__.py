"""Chatbot sandbox app (Acme Cloud support assistant)."""

from __future__ import annotations

from sandbox_apps._common.base import check_variant
from sandbox_apps._common.llm import LLMClient
from sandbox_apps.chatbot.app import ChatbotApp


def build_app(
    variant: str, llm: LLMClient | None = None, seed: int = 0, drift: bool = False
) -> ChatbotApp:
    """Build the chatbot. ``drift=True`` switches model/prompt to v2 (CHAT-005 on seeded)."""
    return ChatbotApp(check_variant(variant), llm, seed, drift)


__all__ = ["ChatbotApp", "build_app"]
