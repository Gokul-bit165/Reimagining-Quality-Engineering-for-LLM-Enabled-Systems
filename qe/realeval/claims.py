"""Claim-level groundedness (ADR-0009): deterministic claim splitting, evidence selection, quote
verification and reconciliation of a (untrusted) judge verdict with the lexical check.

The judge sees ONLY (claim, one candidate evidence passage): never the producer's rationale, other
claims or other verdicts (R4). Its output is untrusted: a 'supported' or 'contradicted' verdict
counts only if the quote it returns occurs literally in the passage it was shown AND is on-topic
for the claim (deterministic checks below); otherwise the verdict is downgraded to 'unverified'
and the lexical result stands. A disagreement between the judge and the lexical check on a claim
that carries a verifiable fact (a number, date, duration, percentage) is a CONFLICT: never
silently resolved, sent to human review.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

from qe.realeval import scoring

MAX_CLAIMS = 20             # claims beyond this are not judged (lexical only), and reported
MAX_PASSAGE_CHARS = 3000    # evidence window shown to the judge
PASSAGES_PER_CLAIM = 2      # candidate passages asked per claim (best lexical matches)
MIN_CLAIM_WORDS = 3         # a fragment shorter than this is not an atomic claim
MIN_QUOTE_CHARS = 8         # a shorter "quote" cannot evidence anything
QUOTE_MIN_OVERLAP = 0.25    # sanity floor: share of the claim's content tokens present in the
                            # quote. Not a validity threshold; it only rejects off-topic quotes
                            # (e.g. injected text) that happen to be literal substrings.

Verdict = Literal["supported", "contradicted", "not_enough_info"]
Status = Literal["supported", "contradicted", "unsupported", "unverified", "conflict"]

_SENT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE = re.compile(r";\s+|,\s+(?:and|but|while|whereas|however)\s+", re.I)
_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_CITE_MARK = re.compile(r"\[\d+\]|\[[^\]]{1,80}\]|\(source:\s*[^)]+\)", re.I)
_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.!?,;])")


class ClaimJudge(Protocol):
    """Judge for one (claim, passage) pair. None = no valid opinion (invalid output, budget...)."""

    def judge_claim(self, claim: str, passage: str) -> tuple[Verdict, str] | None: ...


def split_claims(answer: str) -> list[str]:
    """Deterministic atomic-claim splitter: sentences, then ';' and ', and/but' clauses whose
    both sides are long enough. Citation markers and bullets are stripped. Limit (stated): a
    claim that starts with a pronoun loses its referent (no decontextualisation)."""
    out: list[str] = []
    for sent in _SENT.split(answer):
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", _CITE_MARK.sub("", _BULLET.sub("", sent))).strip()
        if not scoring.tokens(text):
            continue
        parts = [p.strip() for p in _CLAUSE.split(text) if p and p.strip()]
        if len(parts) > 1 and all(len(p.split()) >= MIN_CLAIM_WORDS for p in parts):
            out.extend(parts)
        else:
            out.append(text)
    return out


def _window(claim: str, passage: str) -> str:
    """The part of a long passage (whole sentences, <= MAX_PASSAGE_CHARS) best matching the
    claim; a short passage is returned unchanged."""
    if len(passage) <= MAX_PASSAGE_CHARS:
        return passage
    sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", passage) if s.strip()]
    best, best_score = "", -1.0
    for i in range(len(sents)):
        buf = ""
        for s in sents[i:]:
            if len(buf) + len(s) + 1 > MAX_PASSAGE_CHARS:
                break
            buf = f"{buf} {s}".strip()
        score = scoring.recall(claim, buf)
        if buf and score > best_score:
            best, best_score = buf, score
    return best or passage[:MAX_PASSAGE_CHARS]


def evidence_candidates(claim: str, passages: Sequence[str]) -> list[str]:
    ranked = sorted(passages, key=lambda p: -scoring.recall(claim, p))
    return [_window(claim, p) for p in ranked[:PASSAGES_PER_CLAIM]]


def _squash(text: str) -> str:
    return _WS.sub(" ", text).strip().casefold()


def quote_in_passage(quote: str, passage: str) -> bool:
    """The quote occurs literally in the passage (whitespace and case-insensitive; no ellipses)."""
    q = _squash(quote)
    return len(q) >= MIN_QUOTE_CHARS and "..." not in q and "…" not in q \
        and q in _squash(passage)


def _on_topic(claim: str, quote: str, need_numbers: bool) -> bool:
    if need_numbers and not scoring.numbers(claim) <= scoring.numbers(quote):
        return False
    return scoring.recall(claim, quote) >= QUOTE_MIN_OVERLAP


def verify(raw: tuple[Verdict, str] | None, claim: str, passage: str,
           ) -> tuple[Status, str | None]:
    """Deterministic acceptance of an untrusted judge verdict.
    supported needs a literal, on-topic quote containing every number of the claim;
    contradicted needs a literal, on-topic quote; not_enough_info needs none."""
    if raw is None:
        return "unverified", None
    verdict, quote = raw
    if verdict == "not_enough_info":
        return "unsupported", None
    if not quote_in_passage(quote, passage):
        return "unverified", None
    if not _on_topic(claim, quote, need_numbers=verdict == "supported"):
        return "unverified", None
    return ("supported" if verdict == "supported" else "contradicted"), quote


@dataclass(frozen=True)
class ClaimResult:
    claim: str
    status: Status                 # judge-informed status (before gating)
    lexical_ok: bool               # the deterministic verdict for this claim
    gated_ok: bool | None          # verdict if the judge gates; None = conflict
    quote: str | None = None
    judged: bool = False           # the judge gave a verified opinion
    verifiable: bool = False       # the claim carries numbers/dates/units
    judge_disagrees: bool = False


@dataclass(frozen=True)
class ClaimAudit:
    claims: list[ClaimResult] = field(default_factory=list)
    truncated: bool = False

    @property
    def lexical_faithful(self) -> bool | None:
        return None if not self.claims else all(c.lexical_ok for c in self.claims)

    @property
    def gated_faithful(self) -> bool | None:
        if not self.claims:
            return None
        if any(c.gated_ok is False for c in self.claims):
            return False
        return None if any(c.gated_ok is None for c in self.claims) else True

    @property
    def conflicts(self) -> list[ClaimResult]:
        return [c for c in self.claims if c.status == "conflict"]

    @property
    def judge_view(self) -> Literal["correct", "incorrect"] | None:
        """The judge's own answer-level opinion (calibration unit): incorrect if any claim was
        verified contradicted/unsupported, correct only if every claim was verified supported."""
        if not self.claims:
            return None
        if any(c.judged and c.status in ("contradicted", "unsupported") for c in self.claims):
            return "incorrect"
        if all(c.judged and c.status == "supported" for c in self.claims):
            return "correct"
        return None

    def as_detail(self) -> list[dict[str, object]]:
        return [asdict(c) for c in self.claims]


def _judge_one(claim: str, passages: Sequence[str], judge: ClaimJudge,
               ) -> tuple[Status, str | None]:
    seen: list[tuple[Status, str | None]] = []
    for window in evidence_candidates(claim, passages):
        seen.append(verify(judge.judge_claim(claim, window), claim, window))
    for status, quote in seen:
        if status == "contradicted":
            return status, quote  # contradiction dominates support from another passage
    for status, quote in seen:
        if status == "supported":
            return status, quote
    if seen and all(s == "unsupported" for s, _ in seen):
        return "unsupported", None
    return "unverified", None


def _reconcile(claim: str, lexical: bool, status: Status, quote: str | None,
               ) -> tuple[Status, bool | None, bool]:
    """(status, gated verdict, judge_disagrees). Verifiable-fact disagreement = conflict."""
    if status == "unverified":
        return status, lexical, False
    judge_ok = status == "supported"
    if judge_ok == lexical:
        return status, lexical, False
    if scoring.numbers(claim):  # a checkable fact on which the two checks disagree
        return "conflict", None, True
    return status, judge_ok, True


def audit_claims(answer: str, passages: Sequence[str], judge: ClaimJudge | None) -> ClaimAudit:
    """Per-claim audit. Without a judge only lexical verdicts are produced. A claim that appears
    verbatim in a passage is supported deterministically and never sent to the judge."""
    claims = split_claims(answer)
    if not claims or not passages:
        return ClaimAudit()
    joined = f" {scoring.norm(' '.join(passages))} "
    results: list[ClaimResult] = []
    for i, claim in enumerate(claims):
        lexical = scoring.supported_by(claim, list(passages))
        verifiable = bool(scoring.numbers(claim))
        verbatim = bool(scoring.norm(claim)) and f" {scoring.norm(claim)} " in joined
        if judge is None or verbatim or i >= MAX_CLAIMS:
            status: Status = "supported" if lexical else "unsupported"
            results.append(ClaimResult(claim, status, lexical, lexical, None, False, verifiable))
            continue
        raw_status, quote = _judge_one(claim, passages, judge)
        status, gated, disagrees = _reconcile(claim, lexical, raw_status, quote)
        results.append(ClaimResult(claim, status, lexical, gated, quote,
                                   raw_status != "unverified", verifiable, disagrees))
    return ClaimAudit(results, truncated=len(claims) > MAX_CLAIMS)
