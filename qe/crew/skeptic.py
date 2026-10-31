"""T2.3 Skeptic: independent re-derivation of expected behaviour + validity verdicts.

Deterministic checks decide; the LLM (a different model family from every author, seeing only the
question and the documents, never the author's expected answer) can only add ambiguity flags.
Precedence: invalid > ambiguous > redundant > valid.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Literal

from qe.core.events import EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import Frozen
from qe.crew.authors import ABSTAIN_ORACLE, Draft
from qe.crew.llm import LLMClient
from qe.crew.prompt_store import Prompt, load_prompt
from qe.crew.record import record_crew_event
from qe.crew.text import best_sentence, jaccard, shingles

PROMPT_NAME = "skeptic_v1"
PRODUCER = "skeptic"
Validity = Literal["valid", "invalid", "ambiguous", "redundant"]
_WS = re.compile(r"\s+")


class SkepticConfig(Frozen):
    """Thresholds are explicit inputs (no built-in defaults decide)."""

    near_dup_jaccard: float  # question word-3-shingle Jaccard at/above which a test is redundant
    min_overlap_tokens: int  # content-token overlap at/above which docs are deemed to answer
    example_only: bool = False

    @classmethod
    def example(cls) -> SkepticConfig:
        """EXAMPLE values for tests and demos; not validated against human labels."""
        return cls(near_dup_jaccard=0.8, min_overlap_tokens=2, example_only=True)


class SkepticVerdict(Frozen):
    test_id: str
    validity: Validity
    reasons: tuple[str, ...]
    llm_assisted: bool = False


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def _deterministic_flags(
    d: Draft, docs: Mapping[str, str], cfg: SkepticConfig
) -> tuple[list[str], list[str]]:
    """(invalid reasons, ambiguous reasons) from deterministic re-derivation."""
    invalid: list[str] = []
    ambiguous: list[str] = []
    question = str(d.case.input.get("input", ""))
    hit = best_sentence(question, docs)
    if d.expects_abstain:
        if d.expected_span is not None:
            invalid.append("abstain_with_expected_span")
        if hit is not None and hit[2] >= cfg.min_overlap_tokens:
            invalid.append("unanswerable_but_docs_overlap")
        return invalid, ambiguous
    doc_id = d.case.oracle_source.removeprefix("source_of_truth:")
    if d.case.oracle_source == ABSTAIN_ORACLE or doc_id not in docs:
        invalid.append("source_missing")
        return invalid, ambiguous
    if d.expected_span is None:
        invalid.append("missing_expected_span")
        return invalid, ambiguous
    if _norm(d.expected_span) not in _norm(docs[doc_id]):
        invalid.append("span_not_in_source")
        return invalid, ambiguous
    if hit is None or hit[2] < cfg.min_overlap_tokens:
        ambiguous.append("question_weakly_tied_to_source")
    else:
        if hit[3]:
            ambiguous.append("question_matches_multiple_docs_equally")
        if _norm(hit[1]) != _norm(d.expected_span) or hit[0] != doc_id:
            ambiguous.append("rederived_answer_differs")
    return invalid, ambiguous


def _llm_flags(
    d: Draft, docs: Mapping[str, str], llm: LLMClient, prompt: Prompt
) -> list[str]:
    question = str(d.case.input.get("input", ""))
    raw = llm.complete(
        [
            {"role": "system", "content": prompt.text},
            {"role": "user", "content": json.dumps({"question": question, "docs": dict(docs)},
                                                   sort_keys=True)},
        ]
    )
    try:
        span = json.loads(raw).get("answer_span")
    except (json.JSONDecodeError, AttributeError):
        return ["llm_output_unparseable"]
    corpus = _norm(" ".join(docs.values()))
    if span is not None and (not isinstance(span, str) or _norm(span) not in corpus):
        return ["llm_output_not_verbatim"]  # untrusted claim, ignored for the decision
    if d.expects_abstain:
        return ["llm_answers_unanswerable"] if span is not None else []
    if span is None:
        return ["llm_cannot_answer"]
    if d.expected_span is not None and _norm(span) != _norm(d.expected_span):
        return ["llm_answer_differs"]
    return []


def _redundant_ids(drafts: Sequence[Draft], threshold: float) -> dict[str, str]:
    """test id -> id of the earlier near-duplicate it repeats (earliest by id is kept)."""
    ordered = sorted(drafts, key=lambda d: d.case.id)
    sh = {d.case.id: shingles(str(d.case.input.get("input", ""))) for d in ordered}
    dup: dict[str, str] = {}
    for i, a in enumerate(ordered):
        for b in ordered[:i]:
            if b.case.id not in dup and jaccard(sh[a.case.id], sh[b.case.id]) >= threshold:
                dup[a.case.id] = b.case.id
                break
    return dup


def check_independent(drafts: Sequence[Draft], skeptic_llm: LLMClient) -> None:
    if skeptic_llm.family in {d.family for d in drafts}:
        raise ValueError("skeptic model family must differ from every author family (R5)")


def review(
    drafts: Sequence[Draft],
    docs: Mapping[str, str],
    cfg: SkepticConfig,
    llm: LLMClient | None = None,
    ledger: Ledger | None = None,
    prompt: Prompt | None = None,
) -> tuple[SkepticVerdict, ...]:
    """Validity verdict for every draft (deterministic order by test id)."""
    prompt = prompt or load_prompt(PROMPT_NAME)
    if llm is not None:
        check_independent(drafts, llm)
    dup = _redundant_ids(drafts, cfg.near_dup_jaccard)
    verdicts: list[SkepticVerdict] = []
    for d in sorted(drafts, key=lambda x: x.case.id):
        invalid, ambiguous = _deterministic_flags(d, docs, cfg)
        if llm is not None and not invalid:
            ambiguous += _llm_flags(d, docs, llm, prompt)
        if invalid:
            validity: Validity = "invalid"
        elif any(a != "llm_output_not_verbatim" and a != "llm_output_unparseable"
                 for a in ambiguous):
            validity = "ambiguous"
        elif d.case.id in dup:
            validity = "redundant"
            ambiguous.append(f"near_duplicate_of:{dup[d.case.id]}")
        else:
            validity = "valid"
        verdicts.append(SkepticVerdict(test_id=d.case.id, validity=validity,
                                       reasons=tuple(invalid + ambiguous),
                                       llm_assisted=llm is not None))
    if ledger is not None:
        for v in verdicts:
            record_crew_event(
                ledger, EventType.VALIDITY_VERDICT, PRODUCER, v.model_dump(mode="json"),
                prompt=prompt if llm is not None else None, llm=llm,
                kind=ProducerKind.LLM_AGENT if llm is not None else ProducerKind.DETERMINISTIC,
            )
    return tuple(verdicts)
