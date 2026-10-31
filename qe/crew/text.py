"""Small deterministic text helpers shared by crew roles."""

from __future__ import annotations

import re
from collections.abc import Mapping

STOPWORDS = frozenset(
    "a an the of to in on for and or is are was were be by with at as it its this that "
    "what which who how when where do does can i my you your me we our from about regarding "
    "according say says".split()
)
_WORD = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.!?])\s+")


def tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t not in STOPWORDS]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.strip()) if s.strip()]


def shingles(text: str, k: int = 3) -> frozenset[tuple[str, ...]]:
    """Word k-shingles over the full (stopword-keeping) lowercase word sequence."""
    words = _WORD.findall(text.lower())
    if len(words) < k:
        return frozenset({tuple(words)}) if words else frozenset()
    return frozenset(tuple(words[i : i + k]) for i in range(len(words) - k + 1))


def jaccard(a: frozenset[tuple[str, ...]], b: frozenset[tuple[str, ...]]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def best_sentence(question: str, docs: Mapping[str, str]) -> tuple[str, str, int, bool] | None:
    """Best-overlap sentence for a question: (doc_id, sentence, overlap, tied_across_docs)."""
    q = set(tokens(question))
    scored: list[tuple[int, str, str]] = []
    for doc_id in sorted(docs):
        for s in sentences(docs[doc_id]):
            scored.append((len(q & set(tokens(s))), doc_id, s))
    if not scored:
        return None
    top = max(s[0] for s in scored)
    if top == 0:
        return None
    winners = [s for s in scored if s[0] == top]
    first = winners[0]
    tied = len({w[1] for w in winners}) > 1
    return first[1], first[2], top, tied
