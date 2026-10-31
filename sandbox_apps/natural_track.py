"""Natural-defect track: run CLEAN apps with a (real) LLM and dump outputs for human labelling.

Produces JSONL rows with ``human_label: null``; never decides what is a defect. A real LLM
needs the opt-in env vars checked in ``_common.real_llm``; tests use FakeLLM.
Usage: python -m sandbox_apps.natural_track --provider groq --out natural_run.jsonl
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from sandbox_apps._common.llm import LLMClient

CANDIDATES = Path(__file__).with_name("natural_candidates.yaml")


def load_candidates() -> list[dict[str, Any]]:
    data = yaml.safe_load(CANDIDATES.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = data["candidates"]
    return rows


def run_candidates(
    llm_factory: Callable[[], LLMClient | None], *, seed: int = 0
) -> list[dict[str, Any]]:
    """One fresh clean app per candidate; rows are for human labelling only."""
    rows: list[dict[str, Any]] = []
    for cand in load_candidates():
        module = importlib.import_module(f"sandbox_apps.{cand['app']}")
        app = module.build_app("clean", llm=llm_factory(), seed=seed)
        last: dict[str, Any] = {}
        for request in cand["requests"]:
            last = app.invoke(request)
        rows.append(
            {
                "candidate_id": cand["id"],
                "app": cand["app"],
                "requests": cand["requests"],
                "output": last["output"],
                "citations": last["citations"],
                "meta": last["meta"],
                "triage_flag": bool(re.search(cand["triage_regex"], last["output"])),
                "human_label": None,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    from sandbox_apps._common.real_llm import real_llm_from_env

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["groq", "openrouter"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    llm = real_llm_from_env(args.provider)  # refuses unless opted in and a budget is set
    rows = run_candidates(lambda: llm)
    args.out.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
