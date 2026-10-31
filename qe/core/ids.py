"""Canonical JSON and content-addressed identifiers."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _check(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite float not allowed in canonical JSON: {value!r}")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"JSON object keys must be str, got {type(k).__name__}")
            _check(v)
    elif isinstance(value, list | tuple):
        for v in value:
            _check(v)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 preserved, finite numbers only."""
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_id(value: Any) -> str:
    """Content-addressed ID: SHA-256 of the canonical JSON form."""
    return sha256_hex(canonical_json(value))
