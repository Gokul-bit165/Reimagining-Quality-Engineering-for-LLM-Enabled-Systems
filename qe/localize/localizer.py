"""T5.1 failure localizer: ordered trace rules + optional controlled context substitution.

Input is an already-detected failure; this module only says WHERE (research/06 taxonomy), never
whether a failure occurred. Rules run upstream-first (earliest failing stage wins, as in
trajectory-level RAG diagnosis). `unknown` is a valid, expected answer: with no trace (black-box)
only response-level rules can fire. No confidence number is produced (none is calibrated).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from qe.core.schemas import FailureRecord, Frozen, VisibilityLevel

TAXONOMY: tuple[str, ...] = (
    "input_handling", "retrieval", "ranking/packing", "context_assembly", "prompt_template",
    "generation", "tool_selection", "tool_arguments", "tool_execution", "state/memory",
    "orchestration/routing", "guardrail", "output_validation", "dependency/provider", "unknown",
)
RETRIEVAL_CLASS = frozenset({"retrieval", "ranking/packing", "context_assembly"})
TERMINAL = (".", "!", "?")
SUCCESS_RE = re.compile(r"\b(sent|done|posted|deleted|completed)\b", re.I)
Substitution = Literal["not_run", "failure_gone", "failure_persists"]


@dataclass(frozen=True)
class FailureContext:
    """kind: "rag" | "tool". `trace` is empty when the target is black-box."""

    kind: Literal["rag", "tool"]
    response: Mapping[str, Any]
    trace: Sequence[Mapping[str, Any]]
    reference: Mapping[str, Any] = field(default_factory=dict)


class Localization(Frozen):
    location: str
    rule: str | None
    evidence: tuple[str, ...]
    substitution: Substitution = "not_run"


Hit = tuple[str, str, tuple[str, ...]]  # (location, rule, evidence)
Rule = Callable[[FailureContext], Hit | None]


def _manifest(ctx: FailureContext) -> Mapping[str, Mapping[str, Any]]:
    return ctx.reference.get("manifest", {})  # type: ignore[no-any-return]


def _retrievals(ctx: FailureContext) -> list[Mapping[str, Any]]:
    return [e for e in ctx.trace if e.get("type") == "retrieval"]


def _results(ctx: FailureContext) -> list[Mapping[str, Any]]:
    return [r for e in _retrievals(ctx) for r in e.get("results", [])]


# -- RAG rules ---------------------------------------------------------------------------
def rag_foreign_doc(ctx: FailureContext) -> Hit | None:
    foreign = sorted({r["doc_id"] for r in _results(ctx)} - set(_manifest(ctx)))
    return ("retrieval", "retrieved_doc_not_in_manifest", tuple(foreign)) if foreign else None


def rag_stale_doc(ctx: FailureContext) -> Hit | None:
    man = _manifest(ctx)
    stale = sorted({r["doc_id"] for r in _results(ctx)
                    if r["doc_id"] in man and r.get("doc_hash") != man[r["doc_id"]]["hash"]})
    return ("retrieval", "retrieved_doc_hash_differs_from_manifest", tuple(stale)) if stale else None


def rag_missing_expected(ctx: FailureContext) -> Hit | None:
    if not _retrievals(ctx):
        return None
    expected = set(ctx.reference.get("expected_sources", ()))
    missing = sorted(expected - {r["doc_id"] for r in _results(ctx)})
    return ("retrieval", "expected_source_not_retrieved", tuple(missing)) if missing else None


def rag_truncated_chunk(ctx: FailureContext) -> Hit | None:
    bad = sorted({r["chunk_id"] for r in _results(ctx)
                  if not str(r.get("chunk_text", "")).rstrip().endswith(TERMINAL)})
    return ("retrieval", "retrieved_chunk_ends_mid_sentence", tuple(bad)) if bad else None


def rag_bad_citation_id(ctx: FailureContext) -> Hit | None:
    unknown = sorted(set(ctx.response.get("citations", ())) - set(_manifest(ctx)))
    return ("output_validation", "citation_id_not_in_manifest", tuple(unknown)) if unknown else None


def rag_quote_not_in_cited_doc(ctx: FailureContext) -> Hit | None:
    man = _manifest(ctx)
    bad = []
    for d in ctx.response.get("citation_details", ()):
        text = man.get(d.get("doc_id"), {}).get("text")
        if text is not None and d.get("quote") and d["quote"] not in text:
            bad.append(str(d["doc_id"]))
    return ("output_validation", "quoted_text_not_in_cited_doc", tuple(sorted(set(bad)))) \
        if bad else None


def rag_unsupported_answer(ctx: FailureContext) -> Hit | None:
    if not ctx.reference.get("should_abstain"):
        return None
    out = str(ctx.response.get("output", "")).lower()
    abstained = any(m in out for m in ctx.reference.get("abstain_markers", ()))
    if abstained or ctx.response.get("citations"):
        return None
    return ("generation", "answer_asserted_where_source_has_none", ())


RAG_RULES: tuple[Rule, ...] = (
    rag_foreign_doc, rag_stale_doc, rag_missing_expected, rag_truncated_chunk,
    rag_bad_citation_id, rag_quote_not_in_cited_doc, rag_unsupported_answer,
)


# -- tool-agent rules --------------------------------------------------------------------
def _calls(ctx: FailureContext) -> list[Mapping[str, Any]]:
    return [e for e in ctx.trace if e.get("type") == "tool_call"]


def tool_unauthorized_ok(ctx: FailureContext) -> Hit | None:
    perms: Mapping[str, Sequence[str]] = ctx.reference.get("permissions", {})
    role = ctx.reference.get("user_role")
    bad = [str(c["tool"]) for c in _calls(ctx)
           if c.get("status") == "ok" and c["tool"] in perms and role not in perms[c["tool"]]]
    return ("guardrail", "tool_executed_outside_user_role", tuple(bad)) if bad else None


def tool_host_off_allowlist(ctx: FailureContext) -> Hit | None:
    allow = set(ctx.reference.get("http_allowlist", ()))
    bad = [str(c["args"].get("url")) for c in _calls(ctx)
           if c.get("tool") == "http_post" and c.get("status") == "ok"
           and urlparse(str(c["args"].get("url", ""))).hostname not in allow]
    return ("guardrail", "http_post_to_host_off_allowlist", tuple(bad)) if bad else None


def tool_memory_scope(ctx: FailureContext) -> Hit | None:
    user = ctx.reference.get("user")
    bad = sorted({str(e.get("scope")) for e in ctx.trace
                  if e.get("type") in ("memory_read", "memory_write") and e.get("scope") != user})
    return ("state/memory", "memory_scope_not_the_requesting_user", tuple(bad)) if bad else None


def tool_unexpected(ctx: FailureContext) -> Hit | None:
    if "expected_tools" not in ctx.reference:
        return None
    expected = set(ctx.reference["expected_tools"])
    bad = sorted({str(c["tool"]) for c in _calls(ctx)} - expected)
    return ("tool_selection", "tool_called_that_the_request_does_not_need", tuple(bad)) \
        if bad else None


def tool_missing_calls(ctx: FailureContext) -> Hit | None:
    seen: dict[str, int] = {}
    for c in _calls(ctx):
        seen[str(c["tool"])] = seen.get(str(c["tool"]), 0) + 1
    short = [f"{t}:{seen.get(t, 0)}<{n}" for t, n in sorted(ctx.reference.get("expected_calls", {}).items())
             if seen.get(t, 0) < n]
    return ("tool_execution", "fewer_tool_calls_than_the_request_requires", tuple(short)) \
        if short else None


def tool_false_success(ctx: FailureContext) -> Hit | None:
    failed = [str(c["tool"]) for c in _calls(ctx) if c.get("status") == "error"]
    claims = SUCCESS_RE.search(str(ctx.response.get("output", "")))
    return ("generation", "reply_claims_success_after_tool_error", tuple(failed)) \
        if failed and claims else None


TOOL_RULES: tuple[Rule, ...] = (
    tool_unauthorized_ok, tool_host_off_allowlist, tool_memory_scope,
    tool_unexpected, tool_missing_calls, tool_false_success,
)
RULES: dict[str, tuple[Rule, ...]] = {"rag": RAG_RULES, "tool": TOOL_RULES}


def localize(
    ctx: FailureContext, substitute: Callable[[], bool] | None = None, use_rules: bool = True
) -> Localization:
    """Return the failure location. `substitute()` re-runs the target with ground-truth context
    in place of the retrieval stage and returns True iff the failure disappears."""
    hit: Hit | None = None
    if use_rules:
        for rule in RULES[ctx.kind]:
            hit = rule(ctx)
            if hit is not None:
                break
    sub: Substitution = "not_run"
    if substitute is not None:
        sub = "failure_gone" if substitute() else "failure_persists"
    if hit is None:
        if sub == "failure_gone":
            return Localization(location="retrieval", rule="substitution_fixes_failure",
                                evidence=("ground-truth context removes the failure",),
                                substitution=sub)
        note = ("failure persists under ground-truth context; downstream stage not identified",)
        return Localization(location="unknown", rule=None,
                            evidence=note if sub == "failure_persists" else (), substitution=sub)
    location, rule_name, evidence = hit
    upstream = location in RETRIEVAL_CLASS
    if (sub == "failure_persists" and upstream) or (sub == "failure_gone" and not upstream):
        return Localization(
            location="unknown", rule=rule_name,
            evidence=(*evidence, f"rule said {location} but substitution contradicts it"),
            substitution=sub)
    return Localization(location=location, rule=rule_name, evidence=evidence, substitution=sub)


def to_failure_record(
    failure_id: str, failure_type: str, loc: Localization, visibility: VisibilityLevel,
    evidence_ids: tuple[str, ...] = (),
) -> FailureRecord:
    return FailureRecord(failure_id=failure_id, failure_type=failure_type, location=loc.location,
                         localization_confidence=None, visibility_level=visibility,
                         evidence_ids=evidence_ids)


__all__ = ["TAXONOMY", "FailureContext", "Localization", "localize", "to_failure_record"]
