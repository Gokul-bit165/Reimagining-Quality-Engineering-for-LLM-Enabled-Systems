"""Load the severity rubric and remediation guidance (static YAML, validated on load)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
SEVERITY_ORDER = ("critical", "high", "medium", "low")


@lru_cache(maxsize=1)
def rubric() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((HERE / "rubric.yaml").read_text("utf-8"))
    levels = set(data["levels"])
    bad = [c for c, v in data["classes"].items() if v["severity"] not in levels]
    if bad or data["default"]["severity"] not in levels:
        raise ValueError(f"rubric.yaml: unknown severity level for {bad or 'default'}")
    return data


@lru_cache(maxsize=1)
def remediation() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((HERE / "remediation.yaml").read_text("utf-8"))
    return data


def severity_of(failure_class: str) -> tuple[str, str]:
    """(severity label, rubric basis). A label only: it never feeds a verdict."""
    r = rubric()
    rule = r["classes"].get(failure_class, r["default"])
    return str(rule["severity"]), str(rule["basis"])


def guidance_for(failure_class: str) -> list[str]:
    g = remediation()
    return [str(x) for x in g["classes"].get(failure_class, g["default"])]


def attacker_class(probe_kind: str | None) -> str:
    table = rubric()["attacker_classes"]
    return str(table.get(probe_kind or "", table["default"]))
