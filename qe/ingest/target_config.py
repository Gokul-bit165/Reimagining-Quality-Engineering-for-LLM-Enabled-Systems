"""Per-project contract with the user's endpoint: how to ask, and where the answer lives.

TargetConfig is stored with the project (never secret VALUES: header values reference the
in-memory vault as ${SECRET_NAME}). Response handling supports JSON (dotted/JSONPath-lite paths),
server-sent events (data: lines concatenated) and plain text. Errors name what did not resolve
and show a truncated, secret-scrubbed preview of what the endpoint actually returned.

Path syntax (JSONPath-lite): `a.b.0.c`, `$.a.b[0].c`, `*` (every list item / object value),
e.g. `data.answer`, `choices.0.message.content`, `sources.*.text`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PLACEHOLDER = "{question}"
MAX_PATH_LEN = 200
MAX_CONTEXT_PATHS = 10
PREVIEW_CHARS = 300
_PATH_OK = re.compile(r"^[A-Za-z0-9_\-\.\[\]\*\$]+$")
_SECRET_REF = re.compile(r"\$\{([A-Z][A-Z0-9_]{0,63})\}")
_HEADER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-]{0,63}$")
_FORBIDDEN_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection",
                                "upgrade", "te", "trailer", "proxy-authorization", "expect"})
# Literal (non-vault) header values are allowed only for headers that carry no credentials.
_BENIGN_LITERAL = frozenset({"accept", "content-type", "user-agent", "accept-language",
                             "x-request-id"})
_SCRUB = re.compile(
    r"(Bearer\s+[A-Za-z0-9._\-~+/]+=*|sk-[A-Za-z0-9_\-]{10,}|gsk_[A-Za-z0-9]{10,}|"
    r"(?:api[_-]?key|token|secret|password|authorization)[\"']?\s*[:=]\s*[\"']?[^\"'\s,}]{4,})",
    re.I)
DEFAULT_ANSWER_PATHS = ("answer", "output", "response", "result", "text", "message", "reply",
                        "choices.0.message.content", "data.answer")
DELTA_PATHS = ("choices.0.delta.content", "choices.0.text", "choices.0.message.content",
               "delta.text", "delta", "token", "text", "content", "answer", "output")
CONTEXT_KEYS = ("contexts", "context", "sources", "source_documents", "citations", "documents")
_TEXT_KEYS = ("text", "content", "page_content", "snippet", "chunk")


class TargetParseError(ValueError):
    """The endpoint answered, but not in the shape the configuration (or default) expects."""


class TargetConfig(BaseModel):
    request_template: dict[str, Any] | list[Any] | None = None  # JSON containing {question}
    method: Literal["POST", "GET"] = "POST"
    answer_path: str | None = None
    context_paths: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)  # name -> value with ${SECRET_NAME}
    response_format: Literal["auto", "json", "sse", "text"] = "auto"

    @field_validator("answer_path")
    @classmethod
    def _answer(cls, v: str | None) -> str | None:
        return _check_path(v) if v else None

    @field_validator("context_paths")
    @classmethod
    def _contexts(cls, v: list[str]) -> list[str]:
        if len(v) > MAX_CONTEXT_PATHS:
            raise ValueError(f"at most {MAX_CONTEXT_PATHS} context_paths")
        return [_check_path(p) for p in v]

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, str]) -> dict[str, str]:
        for name, value in v.items():
            low = name.lower()
            if not _HEADER_NAME.match(name) or low in _FORBIDDEN_HEADERS:
                raise ValueError(f"header name not allowed: {name!r}")
            if "\r" in value or "\n" in value or "\x00" in value or len(value) > 500:
                raise ValueError(f"invalid value for header {name!r}")
            if not _SECRET_REF.search(value) and low not in _BENIGN_LITERAL:
                raise ValueError(
                    f"header {name!r}: put the value in the secrets vault and reference it as "
                    "${SECRET_NAME}; literal values are stored in plain text")
        return v

    @model_validator(mode="after")
    def _template(self) -> TargetConfig:
        if self.request_template is not None and not _has_placeholder(self.request_template):
            raise ValueError(f"request_template must contain {PLACEHOLDER} in a string value")
        if self.method == "GET" and self.request_template is not None and not isinstance(
                self.request_template, dict):
            raise ValueError("a GET request_template must be a flat object (query parameters)")
        return self


def _check_path(p: str) -> str:
    if len(p) > MAX_PATH_LEN or not _PATH_OK.match(p):
        raise ValueError(f"invalid path {p[:40]!r}: use dotted keys, indexes and * "
                         "(e.g. data.answer, choices.0.message.content, sources.*.text)")
    return p


def _has_placeholder(node: Any) -> bool:
    if isinstance(node, str):
        return PLACEHOLDER in node
    if isinstance(node, dict):
        return any(_has_placeholder(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_placeholder(v) for v in node)
    return False


def fill_template(node: Any, question: str) -> Any:
    """Replace {question} in string VALUES only (never keys); the model is data, not code."""
    if isinstance(node, str):
        return node.replace(PLACEHOLDER, question)
    if isinstance(node, dict):
        return {k: fill_template(v, question) for k, v in node.items()}
    if isinstance(node, list):
        return [fill_template(v, question) for v in node]
    return node


def resolve_headers(headers: Mapping[str, str], secrets: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, value in headers.items():
        def sub(m: re.Match[str], name: str = name) -> str:
            if m.group(1) not in secrets:
                raise TargetParseError(
                    f"header {name!r} references secret ${{{m.group(1)}}} which is not set in "
                    "the secrets vault (POST /api/projects/{id}/secrets)")
            return secrets[m.group(1)]
        out[name] = _SECRET_REF.sub(sub, value)
    return out


def scrub(text: str, secrets: Mapping[str, str] | None = None, limit: int = PREVIEW_CHARS) -> str:
    """Truncate and remove vault values plus common credential shapes from echoed text."""
    for value in (secrets or {}).values():
        if len(value) >= 4:
            text = text.replace(value, "[redacted]")
    text = _SCRUB.sub("[redacted]", text)
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def extract_paths(data: Any, path: str) -> list[Any]:
    """All values at `path` (JSONPath-lite). Empty list when nothing resolves."""
    spec = path.removeprefix("$").lstrip(".")
    spec = re.sub(r"\[(\d+|\*)\]", r".\1", spec)
    nodes = [data]
    for seg in (s for s in spec.split(".") if s):
        nxt: list[Any] = []
        for n in nodes:
            if seg == "*":
                nxt.extend(n if isinstance(n, list) else list(n.values())
                           if isinstance(n, dict) else [])
            elif seg.isdigit() and isinstance(n, list):
                if int(seg) < len(n):
                    nxt.append(n[int(seg)])
            elif isinstance(n, dict) and seg in n:
                nxt.append(n[seg])
        nodes = nxt
    return nodes


def ctx_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, dict):
        for k in _TEXT_KEYS:
            if isinstance(c.get(k), str):
                return str(c[k])
    return json.dumps(c, default=str)[:2000]


def _contexts(data: Any, paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        for m in extract_paths(data, p):
            if isinstance(m, list):
                out.extend(ctx_text(x) for x in m)
            else:
                out.append(ctx_text(m))
    return list(dict.fromkeys(out))


def _default_contexts(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return []
    for k in CONTEXT_KEYS:
        v = data.get(k)
        if isinstance(v, list):
            return [ctx_text(c) for c in v]
        if isinstance(v, str) and v:
            return [v]
    return []


def _answer_text(data: Any, path: str | None) -> str | None:
    paths = (path,) if path else DEFAULT_ANSWER_PATHS
    for p in paths:
        for m in extract_paths(data, p):
            if isinstance(m, str):
                return m
            if isinstance(m, int | float) and not isinstance(m, bool):
                return str(m)
    return None


def _shape(data: Any) -> str:
    if isinstance(data, dict):
        return f"top-level keys: {sorted(map(str, data))[:15]}"
    return f"top-level type: {type(data).__name__}"


def _parse_json(data: Any, cfg: TargetConfig, secrets: Mapping[str, str]) -> tuple[str, list[str]]:
    if isinstance(data, list) and not cfg.answer_path and data and isinstance(data[0], str):
        return str(data[0]), [ctx_text(c) for c in data[1]] if (
            len(data) > 1 and isinstance(data[1], list)) else []
    ans = _answer_text(data, cfg.answer_path)
    if ans is None:
        where = (f"answer_path {cfg.answer_path!r} did not resolve" if cfg.answer_path
                 else "no answer found at any default location "
                      f"({', '.join(DEFAULT_ANSWER_PATHS[:6])}, ...): set answer_path")
        raise TargetParseError(f"{where}; {_shape(data)}; response: "
                               f"{scrub(json.dumps(data, default=str), secrets)}")
    ctx = _contexts(data, cfg.context_paths) if cfg.context_paths else _default_contexts(data)
    return ans, ctx


def _sse_events(text: str) -> list[Any]:
    events: list[Any] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            events.append(json.loads(payload))
        except ValueError:
            events.append(payload)
    return events


def _parse_sse(text: str, cfg: TargetConfig, secrets: Mapping[str, str],
               ) -> tuple[str, list[str]]:
    events = _sse_events(text)
    parts: list[str] = []
    ctx: list[str] = []
    for ev in events:
        if isinstance(ev, str):
            parts.append(ev)
            continue
        paths = (cfg.answer_path,) if cfg.answer_path else DELTA_PATHS
        for p in paths:
            hit = next((m for m in extract_paths(ev, str(p)) if isinstance(m, str)), None)
            if hit is not None:
                parts.append(hit)
                break
        ctx.extend(_contexts(ev, cfg.context_paths) if cfg.context_paths
                   else _default_contexts(ev))
    if not parts:
        raise TargetParseError(
            f"SSE stream held no text deltas ({len(events)} data events; "
            f"answer_path={cfg.answer_path!r}); first lines: {scrub(text, secrets)}")
    return "".join(parts), list(dict.fromkeys(ctx))


def parse_response(body: str, content_type: str, cfg: TargetConfig,
                   secrets: Mapping[str, str] | None = None) -> tuple[str, list[str]]:
    """(answer, contexts) from a response body, per `cfg.response_format` (auto: by content
    type, then by trying JSON, then plain text). Raises TargetParseError with a precise reason."""
    sec = secrets or {}
    fmt = cfg.response_format
    ctype = content_type.lower()
    if fmt == "sse" or (fmt == "auto" and "text/event-stream" in ctype):
        return _parse_sse(body, cfg, sec)
    if fmt in ("json", "auto"):
        try:
            data: Any = json.loads(body)
        except ValueError:
            if fmt == "json":
                raise TargetParseError(
                    f"response is not JSON: {scrub(body, sec)}") from None
            data = None
        else:
            if isinstance(data, str):
                return data, []
            return _parse_json(data, cfg, sec)
    if cfg.answer_path:
        raise TargetParseError(
            f"answer_path {cfg.answer_path!r} is set but the response is not JSON: "
            f"{scrub(body, sec)}")
    text = body.strip()
    if not text:
        raise TargetParseError("endpoint returned an empty body")
    return text, []
