"""Optional RAGAS GeneratorPort adapter. NOT implemented: ragas is not installed or pinned (M3).

Importing this module never imports ragas. Constructing the adapter fails with a clear error
unless ragas is installed; wiring the actual call is deferred until it is pinned and reviewed.
"""

from __future__ import annotations

import importlib
from typing import Any

from qe.core.schemas import TestCase
from qe.ports import GenerationSpec


class OptionalDependencyError(ImportError):
    pass


class RagasGenerator:
    def __init__(self) -> None:
        try:
            self._ragas: Any = importlib.import_module("ragas")
        except ImportError as exc:
            raise OptionalDependencyError("ragas is not installed (optional extra)") from exc

    async def generate(self, spec: GenerationSpec) -> tuple[TestCase, ...]:
        raise NotImplementedError("RAGAS wiring is deferred until ragas is pinned (M3)")
