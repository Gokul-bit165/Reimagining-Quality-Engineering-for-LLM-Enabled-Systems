"""Typed inputs of the QA report generator.

`EvidenceInput` is one evaluated target (a single evaluation, or one target of a campaign).
`ReportInput` bundles one or more of them. The campaign subsystem adapts its own result shape
into `ReportInput` (see qe.qareport.campaign); the generator never reads anything else.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EntryRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    seq: int
    hash: str


class TargetMeta(BaseModel):
    """What is known about the system under test. Unknown stays None: never invented."""

    model_config = ConfigDict(frozen=True)
    endpoint_host: str | None = None  # host[:port] only; credentials/paths/queries stripped
    execution_mode: str | None = None
    authorized: bool | None = None
    authorized_at: float | None = None
    versions: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ToolInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = "qe"
    version: str = "unknown"
    git_commit: str | None = None
    git_dirty: bool | None = None


class EvidenceInput(BaseModel):
    """One target's evidence. `result`/`runs`/`entries` come from the ledger only."""

    name: str
    eval_id: str
    project_id: str
    created: float | None = None
    state: str = "done"
    params: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any]            # evalconfig payload without the items
    items_planned: list[dict[str, Any]]  # evalconfig items (the plan)
    result: dict[str, Any]            # qe.realeval.assemble result, replayed from the ledger
    runs: dict[str, list[dict[str, Any]]]  # item id -> recorded target responses (all repeats)
    entries: dict[str, EntryRef]      # ledger key -> (seq, entry hash)
    head: str
    length: int
    chain_ok: bool
    chain_reason: str | None = None
    signoffs: list[dict[str, Any]] = Field(default_factory=list)
    confirmations: list[dict[str, Any]] = Field(default_factory=list)
    meta: TargetMeta = Field(default_factory=TargetMeta)
    monitoring: dict[str, Any] | None = None
    # how this ledger names things (a campaign ledger uses other keys than an evaluation ledger)
    run_key_template: str = "erun:{item}:{rep}"
    verdict_key_template: str | None = "everdict:{item}"
    scenarios: dict[str, str] = Field(default_factory=dict)  # item id -> risk scenario
    source_notes: list[str] = Field(default_factory=list)

    def run_key(self, item_id: str, rep: int) -> str:
        return self.run_key_template.format(item=item_id, rep=rep, target=self.name)

    def verdict_key(self, item_id: str) -> str | None:
        t = self.verdict_key_template
        return None if t is None else t.format(item=item_id, target=self.name)


class ReportInput(BaseModel):
    kind: Literal["evaluation", "campaign"]
    id: str
    title: str
    created: float | None = None
    tool: ToolInfo = Field(default_factory=ToolInfo)
    targets: list[EvidenceInput]
    notes: list[str] = Field(default_factory=list)


class TargetContext(BaseModel):
    """Non-ledger facts about a target, stored in the bundle (context.json) so a bundle can be
    re-derived offline. Hash-covered by MANIFEST.json (but not signed: see ADR-0008)."""

    name: str
    eval_id: str
    project_id: str
    created: float | None = None
    state: str = "done"
    params: dict[str, Any] = Field(default_factory=dict)
    meta: TargetMeta = Field(default_factory=TargetMeta)
    monitoring: dict[str, Any] | None = None
    ledger_file: str


class ReportContext(BaseModel):
    kind: Literal["evaluation", "campaign"]
    id: str
    title: str
    created: float | None = None
    tool: ToolInfo
    notes: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)  # campaign: plan + context files
    targets: list[TargetContext]
