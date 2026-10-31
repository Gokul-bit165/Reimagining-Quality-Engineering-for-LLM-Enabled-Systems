"""Pure-python chunking and BM25 retrieval."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i in is it its my of on or the to what when "
    "which who will with you your me we our there this that if about get many much".split()
)
SENTENCE_RE = re.compile(r".+?(?:[.!?](?=\s|$)|$)", re.S)
K1 = 1.5
B = 0.75
TOP_K = 3
MIN_COVERAGE = 0.3  # fraction of distinct query terms a chunk must contain
MAX_SENTENCE_CHARS = 100  # SEEDED (RAG-007) chunker hard cap


def stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    start: int
    end: int


def chunk_document(doc: dict[str, Any], cap_sentences: bool) -> list[Chunk]:
    """One chunk per sentence. With ``cap_sentences`` (seeded) long sentences lose their tail."""
    chunks: list[Chunk] = []
    for idx, match in enumerate(SENTENCE_RE.finditer(doc["text"])):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        start = match.start() + (len(raw) - len(raw.lstrip()))
        text = stripped[:MAX_SENTENCE_CHARS] if cap_sentences else stripped
        chunks.append(Chunk(f"{doc['id']}#c{idx}", doc["id"], text, start, start + len(text)))
    return chunks


class BM25Index:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._tf = [Counter(tokenize(c.text)) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(chunks)) if chunks else 0.0
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, top_k: int = TOP_K) -> list[tuple[Chunk, float]]:
        terms = sorted(set(tokenize(query)))
        if not terms:
            return []
        scored: list[tuple[Chunk, float]] = []
        for chunk, tf, length in zip(self.chunks, self._tf, self._len, strict=True):
            matched = [t for t in terms if t in tf]
            if len(matched) / len(terms) < MIN_COVERAGE:
                continue
            score = 0.0
            for t in matched:
                denom = tf[t] + K1 * (1 - B + B * length / (self._avg or 1.0))
                score += self._idf[t] * tf[t] * (K1 + 1) / denom
            scored.append((chunk, round(score, 4)))
        scored.sort(key=lambda p: (-p[1], p[0].chunk_id))
        return scored[:top_k]
