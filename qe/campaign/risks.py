"""Risk register for a campaign, built only from real inputs (no invented risks).

Sources: user-selected risk focus, the project's analyzer risk flags (FLAG_SCENARIOS), the user's
documents / Q&A (grounded-QA risk), the always-on security probes, and an imported plan. Each
risk is a test scenario known to qe.realeval, tagged with OWASP LLM / qe taxonomy ids that are
verified to exist in the loaded taxonomy files.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qe.realeval.assemble import TAXONOMY_NAMES
from qe.realeval.dynamic import FLAG_SCENARIOS, RISK_OPERATORS, normalize_risks
from qe.risk.taxonomy import Taxonomy, load_taxonomy

GROUNDED = "grounded_qa"
SECURITY_SCENARIOS = frozenset({"prompt_injection", "indirect_injection", "data_leak"})
SCENARIO_TAXONOMY: dict[str, tuple[str, ...]] = {
    "hallucination": ("owasp_llm_2025:LLM09", "QE-FAB"),
    "retrieval": ("owasp_llm_2025:LLM08", "QE-RET"),
    "robustness": ("QE-CON",),
    "prompt_injection": ("owasp_llm_2025:LLM01", "QE-INJ"),
    "indirect_injection": ("owasp_llm_2025:LLM01", "QE-INJ"),
    "data_leak": ("owasp_llm_2025:LLM02",),
    "citation_check": ("QE-CIT",),
    GROUNDED: ("owasp_llm_2025:LLM09", "QE-FAB"),
}
RATIONALE = {
    "hallucination": "answers asserting facts the documents do not support",
    "retrieval": "retrieval misses or is brittle to rephrasing and typos",
    "robustness": "answers change under noise, distractors or broad queries",
    "prompt_injection": "instructions inside the input hijack the answer",
    "indirect_injection": "instructions inside retrieved/quoted content hijack the answer",
    "data_leak": "secrets or canary tokens in the documents are disclosed",
    "citation_check": "answers must carry citations that resolve to the documents",
    GROUNDED: "answers to the user's own questions match their reference answers",
}


def risk_id(scenario: str) -> str:
    return f"RK-{scenario}"


def taxonomy_entries(refs: Sequence[str]) -> list[dict[str, Any]]:
    cache: dict[str, Taxonomy] = {}
    out: list[dict[str, Any]] = []
    for ref in refs:
        if ":" in ref:
            tax, tid = ref.split(":", 1)
            t = cache.setdefault(tax, load_taxonomy(tax))
            title = next((e.title for e in t.entries if e.id == tid), None)
            if title is None:
                continue  # never assert a taxonomy id that the loaded file does not contain
            out.append({"taxonomy": tax, "id": tid, "title": title})
        elif ref in TAXONOMY_NAMES:
            out.append({"taxonomy": "qe_quality", "id": ref, "title": TAXONOMY_NAMES[ref]})
    return out


def build_register(*, risk_focus: Sequence[str], risk_flags: Sequence[str], has_qa: bool,
                   has_documents: bool, include_security: bool,
                   imported_scenarios: Sequence[str] = ()) -> dict[str, Any]:
    """Returns {"risks": [...], "unmapped": [...]} ordered by first appearance."""
    rows: dict[str, dict[str, Any]] = {}
    unmapped: list[dict[str, str]] = []

    def add(scenario: str, source: str) -> None:
        row = rows.setdefault(scenario, {
            "id": risk_id(scenario), "scenario": scenario,
            "label": scenario.replace("_", " "), "sources": [],
            "taxonomy": taxonomy_entries(SCENARIO_TAXONOMY.get(scenario, ())),
            "rationale": RATIONALE.get(scenario, "scenario supplied in an imported plan")})
        if source not in row["sources"]:
            row["sources"].append(source)

    for label in risk_focus:
        found, bad = normalize_risks([label])
        if bad:
            unmapped.append({"label": label, "source": "user_focus"})
            continue
        for s in found:
            add(s, "user_focus")
    for flag in risk_flags:
        key = flag.strip().lower().replace(" ", "_").replace("-", "_")
        if key in FLAG_SCENARIOS:
            for s in FLAG_SCENARIOS[key]:
                add(s, f"analyzer_flag:{key}")
            continue
        found, bad = normalize_risks([flag])
        if bad:
            unmapped.append({"label": flag, "source": "analyzer_flag"})
        else:
            for s in found:
                add(s, f"analyzer_flag:{key}")
    if has_qa or has_documents:
        add(GROUNDED, "user_inputs")
    if not any(s in rows for s in RISK_OPERATORS):  # same fallback the engine applies
        for s in normalize_risks([])[0]:
            add(s, "default")
    if include_security:
        add("prompt_injection", "security_probes")
    for s in imported_scenarios:
        add(s, "imported_plan")
    return {"risks": list(rows.values()), "unmapped": unmapped}


def taxonomy_gaps(risks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """OWASP LLM ids that no register risk maps to (explicitly UNASSESSED, never 'fine')."""
    llm = load_taxonomy("owasp_llm_2025")
    mapped = {t["id"] for r in risks for t in r["taxonomy"] if t["taxonomy"] == "owasp_llm_2025"}
    agentic = load_taxonomy("owasp_agentic_2026")
    return {
        "owasp_llm_2025_unassessed": sorted(llm.ids() - mapped),
        "owasp_agentic_2026": (
            "not assessed: a question->answer endpoint exposes no tool calls, memory or agent "
            "handoffs; agentic risks need trace-level evidence" if not agentic.entries else
            f"{len(agentic.entries)} entries, none assessed"),
    }
