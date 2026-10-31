"""RAGAS `GeneratorPort` adapter (R8). ragas is optional and never imported at module load.

A `TestsetBackend` produces raw rows; the adapter turns them into DRAFT `TestCase`s. RAGAS
references are generator output, not ground truth, so validity stays "unreviewed" and the
Skeptic/audit pipeline must still judge them.
"""

from __future__ import annotations

from typing import Any, Protocol

from qe.core.ids import content_id
from qe.core.schemas import TestCase
from qe.core.telemetry import enforce_telemetry_off
from qe.ports import GenerationSpec


class TestsetBackend(Protocol):
    def generate(self, docs: dict[str, str], n: int, seed: int) -> list[dict[str, str]]: ...


def load_ragas_backend() -> TestsetBackend:  # pragma: no cover - needs optional ragas extra
    enforce_telemetry_off()
    try:
        import ragas  # type: ignore[import-not-found,import-untyped,unused-ignore]  # noqa: F401
    except ImportError as exc:
        raise ImportError("ragas is not installed; install the pinned optional extra") from exc
    raise NotImplementedError("ragas backend wiring is added with the pinned extra (not in M2)")


class RagasGenerator:
    def __init__(self, backend: TestsetBackend, sources: dict[str, str]) -> None:
        self._backend = backend
        self._sources = sources

    async def generate(self, spec: GenerationSpec) -> tuple[TestCase, ...]:
        docs = {sid: self._sources[sid] for sid in spec.source_ids}  # KeyError if unknown
        rows = self._backend.generate(docs, spec.n, spec.seed)
        out: list[TestCase] = []
        for row in rows:
            sid = row.get("source_id", "")
            inp: dict[str, Any] = {
                "question": row["question"],
                "expected": row.get("reference", ""),
            }
            if sid in docs:
                inp["source_id"] = sid
            out.append(
                TestCase(
                    id=content_id(["ragas", spec.seed, row]),
                    input=inp,
                    oracle_source=f"source_of_truth:{sid}" if sid in docs else "none",
                    lineage=("ragas", f"seed:{spec.seed}"),
                )
            )
        return tuple(out)
