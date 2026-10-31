"""Optional adapters (T4.3): external red-team tools as ATTACK GENERATORS only.

Promptfoo / PyRIT / DeepTeam are never imported at module load and are not dependencies.
Their output is reduced to a list of payload strings (untrusted data) that `ExternalAttacker`
feeds to the same runner and oracles as every other attacker. The adapters cannot supply a
verdict: success is decided only by our outcome oracles (R5). Nothing here vendors third-party code.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from qe.core.events import ProducerKind
from qe.crew.attack_pairs import AttackPair
from qe.crew.attacker import Attempt, sanitize_payload


class OptionalDependencyMissingError(RuntimeError):
    pass


class ExternalAttacker:
    """Replays external payloads in order; `{goal}` in a payload is replaced by the pair goal."""

    producer_kind = ProducerKind.DETERMINISTIC

    def __init__(self, label: str, payloads: Sequence[str]) -> None:
        if not label.replace("-", "").replace("_", "").isalnum():
            raise ValueError("label must be alphanumeric/-/_")
        self.attacker_class = f"external:{label}"
        self._payloads = tuple(p for p in (sanitize_payload(x) for x in payloads) if p.strip())

    def next_payload(self, pair: AttackPair, history: Sequence[Attempt]) -> tuple[str, str] | None:
        if len(history) >= len(self._payloads):
            return None
        text = self._payloads[len(history)]
        return "external", sanitize_payload(
            text.replace("{goal}", pair.goal) if "{goal}" in text else f"{text} {pair.goal}"
        )


def from_jsonl(path: Path, label: str, field: str = "prompt") -> ExternalAttacker:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return ExternalAttacker(
        label, [str(r[field]) for r in rows if isinstance(r, dict) and field in r]
    )


def _walk_prompts(node: Any) -> list[str]:
    """Collect prompt-like strings from Promptfoo-shaped JSON (tests[].vars.*, results[].prompt)."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("prompt", "query", "input") and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_walk_prompts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_prompts(item))
    return found


def from_promptfoo_json(path: Path) -> ExternalAttacker:
    """Read an exported Promptfoo red-team test file/result (JSON); no Promptfoo install needed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ExternalAttacker("promptfoo", list(dict.fromkeys(_walk_prompts(data))))


def _require(module: str, extra: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise OptionalDependencyMissingError(
            f"{module} is not installed; install the optional extra '{extra}' "
            "(see THIRD_PARTY_NOTICES)"
        ) from exc


def from_generator_callable(
    label: str, generate: Callable[[str, int], Sequence[str]], goal: str, n: int
) -> ExternalAttacker:
    """Wrap any callable (e.g. a PyRIT/DeepTeam generator supplied by the caller) as an attacker."""
    return ExternalAttacker(label, generate(goal, n))


def pyrit_available() -> bool:
    try:
        _require("pyrit", "pyrit")
    except OptionalDependencyMissingError:
        return False
    return True


def deepteam_available() -> bool:
    try:
        _require("deepteam", "deepteam")
    except OptionalDependencyMissingError:
        return False
    return True


def require_pyrit() -> Any:
    return _require("pyrit", "pyrit")


def require_deepteam() -> Any:
    return _require("deepteam", "deepteam")
