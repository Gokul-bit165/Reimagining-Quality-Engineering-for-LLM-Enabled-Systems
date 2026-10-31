"""Strict parsing of untrusted LLM output."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _load(raw: str) -> Any:
    return json.loads(_FENCE.sub("", raw.strip()))


def parse_json_list(raw: str) -> list[dict[str, Any]]:
    """Return a list of objects or raise ValueError."""
    try:
        data = _load(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not JSON: {exc.msg}") from exc
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        raise ValueError("expected a JSON list of objects")
    return data


def parse_json_object(raw: str) -> dict[str, Any]:
    try:
        data = _load(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data
