"""Parse OTel-style JSON span dumps into `Span` tuples (access level C).

Trace content (prompts, tool args, documents) is UNTRUSTED data (R3/R6): it is size-bounded,
never interpreted, and flagged `qe.untrusted_content`. Malformed input yields fewer spans,
never an exception, because the span source is outside our trust boundary.
"""

from __future__ import annotations

import json
from typing import Any

from qe.core.ids import content_id
from qe.core.schemas import Span

MAX_SPANS = 10_000
MAX_ATTR_CHARS = 4_096
MAX_ATTRS = 128
MAX_INPUT_BYTES = 20_000_000
MAX_DEPTH = 8
_TYPED_KEYS = ("stringValue", "intValue", "doubleValue", "boolValue")
_OI_KINDS = {"RETRIEVER": "retrieval", "TOOL": "tool_call", "LLM": "llm_call",
             "AGENT": "handoff", "CHAIN": "other"}
_GENAI_OPS = {"chat": "llm_call", "text_completion": "llm_call", "generate_content": "llm_call",
              "embeddings": "retrieval", "execute_tool": "tool_call", "invoke_agent": "handoff"}


def parse_otel(data: str | bytes | list[Any] | dict[str, Any]) -> tuple[Span, ...]:
    """OTLP/JSON (`resourceSpans`), `{"spans": [...]}` or a bare list of span dicts."""
    obj = _load(data)
    raw = _collect(obj)[:MAX_SPANS]
    spans: list[Span] = []
    for index, item in enumerate(raw):
        if isinstance(item, dict):
            spans.append(_to_span(item, index))
    return tuple(spans)


def _load(data: str | bytes | list[Any] | dict[str, Any]) -> Any:
    if not isinstance(data, str | bytes):
        return data
    if len(data) > MAX_INPUT_BYTES:
        return None
    try:
        return json.loads(data)
    except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return None


def _collect(obj: Any) -> list[Any]:
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []
    if isinstance(obj.get("spans"), list):
        return list(obj["spans"])
    out: list[Any] = []
    for rs in _as_list(obj.get("resourceSpans")):
        for ss in _as_list(rs.get("scopeSpans", rs.get("instrumentationLibrarySpans"))
                           if isinstance(rs, dict) else None):
            if isinstance(ss, dict):
                out.extend(_as_list(ss.get("spans")))
    return out


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _attr_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in _TYPED_KEYS:
            if key in value:
                return _coerce(key, value[key])
        return None
    return value


def _coerce(key: str, value: Any) -> Any:
    if key == "intValue":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value


def _flat_attrs(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(raw, dict):
        pairs = list(raw.items())
    else:
        pairs = [(a.get("key"), _attr_value(a.get("value"))) for a in _as_list(raw)
                 if isinstance(a, dict)]
    for key, value in pairs[:MAX_ATTRS]:
        if isinstance(key, str) and key:
            out[key] = value
    return out


def _bound(value: Any, depth: int = 0) -> Any:
    if isinstance(value, str):
        return value[:MAX_ATTR_CHARS]
    if isinstance(value, bool | int | float) or value is None:
        return value
    if depth >= MAX_DEPTH:
        return "<depth-limited>"
    if isinstance(value, list | tuple):
        return [_bound(v, depth + 1) for v in value[:MAX_ATTRS]]
    if isinstance(value, dict):
        return {str(k): _bound(v, depth + 1) for k, v in list(value.items())[:MAX_ATTRS]}
    return str(value)[:MAX_ATTR_CHARS]


def _kind(name: str, attrs: dict[str, Any]) -> str:
    explicit = attrs.get("qe.span.kind")
    if isinstance(explicit, str) and explicit:
        return explicit
    oi = attrs.get("openinference.span.kind")
    if isinstance(oi, str) and oi.upper() in _OI_KINDS:
        return _OI_KINDS[oi.upper()]
    op = attrs.get("gen_ai.operation.name")
    if isinstance(op, str) and op in _GENAI_OPS:
        return _GENAI_OPS[op]
    if "gen_ai.tool.name" in attrs:
        return "tool_call"
    low = name.lower()
    if "retriev" in low:
        return "retrieval"
    return "other"


def _to_span(item: dict[str, Any], index: int) -> Span:
    attrs = _flat_attrs(item.get("attributes"))
    raw_name = item.get("name")
    name = raw_name if isinstance(raw_name, str) else ""
    truncated = sorted(k for k, v in attrs.items()
                       if isinstance(v, str) and len(v) > MAX_ATTR_CHARS)
    bounded = {k: _bound(v) for k, v in attrs.items()}
    if truncated:
        bounded["qe.truncated"] = truncated
    bounded["qe.untrusted_content"] = True
    sid = item.get("spanId", item.get("span_id"))
    if not isinstance(sid, str) or not sid:
        sid = "gen-" + content_id([index, name, sorted(bounded)])[:12]
    return Span(span_id=sid[:128], kind=_kind(name, attrs), attributes=bounded)
