"""The test plan: a first-class, exportable/importable artifact (risk -> cases -> oracles).

Generated from real inputs only. With a real LLM configured the user's documents may yield
LLM-drafted questions (untrusted: kept only if grounded verbatim, advisory until a human
confirms); otherwise every case comes from rule-based operators in qe.realeval.dynamic and the
plan says so. A plan imported from a jury/company replaces generation and is validated here.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from qe.campaign.models import CampaignParams
from qe.campaign.risks import (
    GROUNDED,
    SCENARIO_TAXONOMY,
    SECURITY_SCENARIOS,
    risk_id,
    taxonomy_entries,
    taxonomy_gaps,
)
from qe.core.ids import content_id
from qe.realeval.dataset import EvalItem, QuestionGenerator
from qe.realeval.dynamic import RISK_OPERATORS
from qe.realeval.resolver import ResolvedProject
from qe.realeval.runner import Budget, EvalParams, Inputs, build_items
from qe.realeval.scoring import oracle_breached

PLAN_VERSION = 1
MAX_PLAN_CASES = 500
RULE_BASED = "rule-based only; no LLM-authored tests"
SCENARIO_SET = frozenset(RISK_OPERATORS) | {GROUNDED}


class PlanError(ValueError):
    pass


def operator_scenarios(requested: list[str]) -> dict[str, str]:
    """operator -> the first requested scenario that uses it (deterministic)."""
    out: dict[str, str] = {}
    for s in requested:
        for op in RISK_OPERATORS.get(s, ()):
            out.setdefault(op, s)
    return out


def scenario_of(item: EvalItem, op_map: dict[str, str], known: set[str]) -> str:
    if item.risk in known:
        return str(item.risk)
    op = (item.lineage or {}).get("operator")
    if op in op_map:
        return op_map[str(op)]
    if item.source == "security":
        return "data_leak" if (item.probe or {}).get("kind") == "canary_exfiltration" \
            else "prompt_injection"
    return GROUNDED


def oracle_types(item: EvalItem, require_citations: bool) -> list[str]:
    if item.source == "security":
        oracle = (item.probe or {}).get("oracle", "")
        return ["output_predicate" if oracle == "output_predicate" else "canary"]
    out: list[str] = []
    if item.answerable is False:
        out.append("refusal")
    if item.reference_answer:
        out.append("reference_match")
    if require_citations and item.answerable is not False:
        out.append("citation")
    return out or ["unchecked"]


def expected_evidence(item: EvalItem, oracles: list[str]) -> str:
    if item.source == "security":
        params = (item.probe or {}).get("params", {})
        if "values" in params:
            return "no canary token from the documents may appear in the answer"
        if "forbidden_domains" in params:
            return f"answer must not direct the user to {params['forbidden_domains']}"
        return "the injected marker must not appear in the answer (outcome oracle)"
    if "unchecked" in oracles:
        return "none: no reference and answerability undeclared (item will be UNCHECKED)"
    parts: list[str] = []
    if "reference_match" in oracles:
        parts.append(f"answer matches reference: {item.reference_answer}")
    if "refusal" in oracles:
        parts.append("answer declines: the documents do not cover this")
    if "citation" in oracles:
        parts.append("answer carries a citation that resolves to a supplied document")
    return "; ".join(parts)


def _case(item: EvalItem, scenario: str, require_citations: bool) -> dict[str, Any]:
    oracles = oracle_types(item, require_citations)
    return {**item.model_dump(mode="json"), "risk_id": risk_id(scenario), "scenario": scenario,
            "oracles": oracles, "expected_evidence": expected_evidence(item, oracles)}


def _gap_reason(scenario: str, include_security: bool, require_citations: bool,
                notes: list[str]) -> tuple[str, str]:
    if scenario in SECURITY_SCENARIOS and not include_security:
        return "GAP", "security testing disabled (include_security=false)"
    if scenario == "citation_check":
        return "CHECK_ONLY", ("no test operator: citation validity is a mandatory check on "
                              "every answerable case" if require_citations
                              else "no test operator")
    if scenario == "hallucination" and any("false-premise" in n for n in notes):
        return "GAP", "false-premise operator skipped: no entities/aspects in the documents"
    return "GAP", "no case could be built from the supplied inputs and operators"


def coverage(register: dict[str, Any], cases: list[dict[str, Any]], *, include_security: bool,
             notes: list[str], require_citations: bool) -> dict[str, Any]:
    matrix: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for r in register["risks"]:
        mine = [c for c in cases if c["scenario"] == r["scenario"]]
        ops = Counter(str((c["lineage"] or {}).get("operator") or c["source"]) for c in mine)
        status, reason = "COVERED", ""
        if not mine:
            status, reason = _gap_reason(r["scenario"], include_security, require_citations,
                                         notes)
        matrix.append({"risk_id": r["id"], "scenario": r["scenario"],
                       "taxonomy_ids": [t["id"] for t in r["taxonomy"]],
                       "n_tests": len(mine), "operators": dict(sorted(ops.items())),
                       "oracle_types": sorted({o for c in mine for o in c["oracles"]}),
                       "status": status, "gap_reason": reason})
        if status != "COVERED":
            gaps.append({"risk_id": r["id"], "reason": reason})
    for u in register["unmapped"]:
        reason = f"no mapped test scenario for this {u['source']} label"
        matrix.append({"risk_id": None, "scenario": None, "label": u["label"],
                       "taxonomy_ids": [], "n_tests": 0, "operators": {}, "oracle_types": [],
                       "status": "GAP", "gap_reason": reason})
        gaps.append({"risk_id": u["label"], "reason": reason})
    return {"matrix": matrix, "gaps": gaps, "taxonomy": taxonomy_gaps(register["risks"])}


def _finish(*, register: dict[str, Any], items: list[EvalItem], notes: list[str],
            require_citations: bool, params: CampaignParams, source: str,
            doc_names: list[str]) -> dict[str, Any]:
    requested = [r["scenario"] for r in register["risks"]]
    known = set(requested)
    op_map = operator_scenarios(requested)
    cases = [_case(i, scenario_of(i, op_map, known), require_citations) for i in items]
    llm_n = sum(1 for i in items if (i.lineage or {}).get("operator") == "llm_question")
    authoring = ({"mode": "llm_assisted", "llm_items": llm_n,
                  "statement": f"{llm_n} grounded question(s) drafted by a real LLM (advisory "
                               "until a human confirms); all other cases are rule-based"}
                 if llm_n else {"mode": "rule_based_only", "llm_items": 0,
                                "statement": RULE_BASED})
    return {
        "plan_version": PLAN_VERSION,
        "plan_id": "plan-" + content_id([i.model_dump(mode="json") for i in items])[:12],
        "source": source, "seed": params.seed, "repeats": params.repeats,
        "doc_names": doc_names, "require_citations": require_citations,
        "include_security": params.include_security, "authoring": authoring,
        "risks": register["risks"], "unmapped": register["unmapped"], "cases": cases,
        "coverage": coverage(register, cases, include_security=params.include_security,
                             notes=notes, require_citations=require_citations),
        "notes": [*notes, authoring["statement"]]}


def build_plan(project: ResolvedProject, params: CampaignParams, register: dict[str, Any],
               generator: QuestionGenerator | None, regression_items: list[EvalItem],
               n_targets: int) -> dict[str, Any]:
    ev = EvalParams(max_questions=params.max_cases, repeats=params.repeats,
                    include_security=params.include_security,
                    generate_questions=generator is not None, policy=params.policy,
                    risk_focus=params.risk_focus, seed=params.seed)
    inputs = Inputs(project=project, generator=generator, regression_items=regression_items)
    budget = Budget(max(1, params.max_calls // n_targets), params.timeout_s)
    items, notes, flags = build_items(ev, inputs, budget)
    if params.generate_with_llm and generator is None:
        notes.append("LLM generation requested but no real LLM is configured (set "
                     "QE_ALLOW_REAL_LLM=1, a provider key and QE_LLM_MODEL): rule-based only")
    return _finish(register=register, items=items, notes=notes,
                   require_citations=bool(flags.get("require_citations")), params=params,
                   source="generated", doc_names=[d["name"] for d in project.documents])


def validate_import(raw: dict[str, Any]) -> list[EvalItem]:
    """Reject a malformed supplied plan with a precise reason (never crash later)."""
    cases = raw.get("cases")
    if not isinstance(cases, list) or not cases:
        raise PlanError("plan.cases must be a non-empty list")
    if len(cases) > MAX_PLAN_CASES:
        raise PlanError(f"plan has {len(cases)} cases; at most {MAX_PLAN_CASES}")
    items: list[EvalItem] = []
    seen: set[str] = set()
    for n, c in enumerate(cases):
        try:
            item = EvalItem.model_validate(c)
        except Exception as exc:  # noqa: BLE001 - the validation message is the reason
            raise PlanError(f"cases[{n}] invalid: {str(exc).splitlines()[0]}") from None
        if not item.question.strip():
            raise PlanError(f"cases[{n}] has an empty question")
        if item.id in seen:
            raise PlanError(f"duplicate case id {item.id!r}")
        seen.add(item.id)
        if item.source == "security":
            try:
                oracle_breached(item, "")
            except Exception:  # noqa: BLE001
                raise PlanError(f"cases[{n}] ({item.id}): a security case needs a valid probe "
                                "{kind, oracle, params}") from None
        items.append(item)
    return items


def adopt_import(project: ResolvedProject, params: CampaignParams, register: dict[str, Any],
                 n_targets: int) -> dict[str, Any]:
    raw = params.imported_plan or {}
    items = validate_import(raw)
    notes = [f"plan imported from the user ({len(items)} case(s)); the engine adapted: risks, "
             "oracles and coverage were recomputed from the supplied cases"]
    cap = min(params.max_cases, max(1, params.max_calls // (params.repeats * n_targets)))
    if len(items) > cap:
        notes.append(f"TRUNCATED imported plan to {cap} case(s) by max_cases/max_calls "
                     f"(from {len(items)}), in the supplied order")
        items = items[:cap]
    risks = list(register["risks"])
    known = {r["scenario"] for r in risks}
    for s in dict.fromkeys(str(i.risk) for i in items if i.risk in SCENARIO_SET):
        if s not in known:
            risks.append({"id": risk_id(s), "scenario": s, "label": s.replace("_", " "),
                          "sources": ["imported_plan"],
                          "taxonomy": taxonomy_entries(SCENARIO_TAXONOMY.get(s, ())),
                          "rationale": "scenario supplied in an imported plan"})
    return _finish(register={**register, "risks": risks}, items=items, notes=notes,
                   require_citations=bool(raw.get("require_citations", False)), params=params,
                   source="imported", doc_names=[d["name"] for d in project.documents])
