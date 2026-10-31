"""LLM access for crew roles: a Protocol, a deterministic FakeLLM, an opt-in live client.

Tests and offline runs use FakeLLM only. The live client is constructed only when QE_LIVE=1 and
reads its key from the environment or a gitignored .env; the key is never logged or put in errors.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

Messages = list[dict[str, str]]
RoleHandler = Callable[[str, str], str]  # (system, user) -> completion


@runtime_checkable
class LLMClient(Protocol):
    family: str  # model family, for independence audits (R5)
    model_name: str

    def complete(self, messages: Messages, **kw: Any) -> str: ...


def role_of(system: str) -> str:
    for line in system.splitlines():
        if line.startswith("ROLE:"):
            return line.split(":", 1)[1].strip()
    return "default"


class FakeLLM:
    """Deterministic scripted client: output = handler(role)(system, user). No network."""

    def __init__(
        self,
        family: str = "fake-a",
        handlers: Mapping[str, RoleHandler] | None = None,
        model_name: str = "fake-llm",
    ) -> None:
        self.family = family
        self.model_name = model_name
        self._handlers: dict[str, RoleHandler] = dict(handlers or {})
        self.calls: list[dict[str, str]] = []

    def complete(self, messages: Messages, **kw: Any) -> str:
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        role = role_of(system)
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        self.calls.append({"role": role, "digest": digest})
        handler = self._handlers.get(role)
        return handler(system, user) if handler else "{}"


def read_dotenv(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser. Values are returned to the caller only, never logged."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip("'\"")
    return out


class OpenAICompatibleClient:
    """OpenAI-style /chat/completions over urllib. Only built via `live_client` (QE_LIVE=1)."""

    def __init__(
        self, base_url: str, model_name: str, family: str, api_key: str, timeout: float = 60.0
    ) -> None:
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("base_url must be an http(s) URL")
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.family = family
        self._api_key = api_key
        self.timeout = timeout

    def __repr__(self) -> str:  # never expose the key
        return f"OpenAICompatibleClient(model={self.model_name!r}, family={self.family!r})"

    def complete(self, messages: Messages, **kw: Any) -> str:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": kw.get("temperature", 0.0),
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"LLM HTTP error {exc.code}") from None
        except urllib.error.URLError:
            raise RuntimeError("LLM connection error") from None
        return str(body["choices"][0]["message"]["content"])


def live_client(
    base_url: str,
    model_name: str,
    family: str,
    api_key_env: str,
    env: Mapping[str, str] | None = None,
    dotenv: Path = Path(".env"),
) -> OpenAICompatibleClient:
    """Build the live client. Refuses unless QE_LIVE=1 (no real calls by default)."""
    environ = os.environ if env is None else env
    if environ.get("QE_LIVE") != "1":
        raise PermissionError("live LLM calls are disabled; set QE_LIVE=1 to opt in")
    key = environ.get(api_key_env) or read_dotenv(dotenv).get(api_key_env)
    if not key:
        raise RuntimeError(f"environment variable {api_key_env} is not set")
    return OpenAICompatibleClient(base_url, model_name, family, key)
