"""Environment adapters: build a sandbox app and apply attacker-granted setup operations.

The only place that reaches into sandbox app internals (state/doc store). `sandbox_apps` is imported
lazily so `qe` does not depend on the demo apps at import time.
"""

from __future__ import annotations

import importlib
from typing import Any, Protocol

from qe.exec.attack_model import SetupOp


class AppLike(Protocol):
    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def snapshot_state(self) -> dict[str, Any]: ...
    def sinks(self) -> list[dict[str, Any]]: ...


class SandboxEnv(Protocol):
    name: str

    def build(self, variant: str, seed: int) -> AppLike: ...
    def apply(self, app: AppLike, op: SetupOp) -> None: ...


def _build(app_name: str, variant: str, seed: int) -> AppLike:
    module = importlib.import_module(f"sandbox_apps.{app_name}")
    app: AppLike = module.build_app(variant, seed=seed)
    return app


class ToolAgentEnv:
    name = "toolagent"

    def build(self, variant: str, seed: int) -> AppLike:
        return _build(self.name, variant, seed)

    def apply(self, app: AppLike, op: SetupOp) -> None:
        state: Any = app.state  # type: ignore[attr-defined]
        a = op.args
        if op.op == "plant_note":
            notes = state.notes.setdefault(a["user"], [])
            nid = a.get("id", f"N-X{len(notes)}")
            notes.append(
                {"id": nid, "title": a["title"], "body": a["body"], "source": a.get("source", "x")}
            )
        elif op.op == "remove_note":
            state.notes = {
                u: [n for n in ns if n["id"] != a["id"]] for u, ns in state.notes.items()
            }
        else:
            raise ValueError(f"toolagent does not support setup op {op.op}")


class RagEnv:
    name = "rag"

    def build(self, variant: str, seed: int) -> AppLike:
        return _build(self.name, variant, seed)

    def apply(self, app: AppLike, op: SetupOp) -> None:
        rag: Any = app
        if op.op == "ingest_document":
            rag.ingest_document(op.args["doc_id"], op.args["title"], op.args["text"])
        elif op.op == "drop_unofficial_docs":
            official = set(rag.corpus_manifest()["docs"])
            rag._docs = {k: v for k, v in rag._docs.items() if k in official}  # noqa: SLF001
            rag._reindex()  # noqa: SLF001
        else:
            raise ValueError(f"rag does not support setup op {op.op}")


ENVS: dict[str, SandboxEnv] = {"toolagent": ToolAgentEnv(), "rag": RagEnv()}
