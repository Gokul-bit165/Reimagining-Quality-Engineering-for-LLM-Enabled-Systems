"""Typed ingest records. All fields derive from static reading of untrusted repo content."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from qe.ingest.target_config import TargetConfig

ExecutionMode = Literal["endpoint", "docker", "static_only"]
ProjectState = Literal["cloning", "analyzing", "ready", "failed"]


class Entrypoint(BaseModel):
    kind: str  # http_route | cli | function | express_route
    name: str
    file: str
    line: int
    detail: str = ""


class PromptTemplate(BaseModel):
    file: str
    line: int
    snippet: str


class Chunking(BaseModel):
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    file: str = ""
    line: int = 0


class RiskFlag(BaseModel):
    id: str
    title: str
    evidence_file: str
    line: int


class ProjectAnalysis(BaseModel):
    framework: str = "unknown"  # langchain | llama_index | haystack | raw | unknown
    language: str = "unknown"  # python | javascript | typescript | mixed | unknown
    entrypoints: list[Entrypoint] = Field(default_factory=list)
    retriever: str | None = None
    vector_store: str | None = None
    llm_providers: list[str] = Field(default_factory=list)
    embedding_providers: list[str] = Field(default_factory=list)
    prompts: list[PromptTemplate] = Field(default_factory=list)
    doc_sources: list[str] = Field(default_factory=list)
    env_vars: list[str] = Field(default_factory=list)
    chunking: Chunking | None = None
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    execution_mode: ExecutionMode = "static_only"
    executed: bool = False  # always False for analysis: nothing is run to produce it
    files_scanned: int = 0
    notes: list[str] = Field(default_factory=list)
    mode_reason: str = ""  # why execution_mode is what it is (precise reason when static_only)
    run_kind: str = ""  # docker mode: dockerfile|python-asgi|python-flask|python-function|node
    summary: str = ""
    next_steps: list[str] = Field(default_factory=list)
    env_template: str = ""  # NAME= lines only; values are supplied at run time, never stored


class UserDocument(BaseModel):
    name: str
    text: str


class QAPair(BaseModel):
    question: str
    reference_answer: str | None = None
    answerable: bool | None = None  # False = the documents do not answer it (refusal expected)


class ProjectInputs(BaseModel):
    documents: list[UserDocument] = Field(default_factory=list)
    qa_pairs: list[QAPair] = Field(default_factory=list)
    endpoint_url: str | None = None
    notes: str = ""
    risk_focus: list[str] = Field(default_factory=list)
    egress_allowlist: list[str] = Field(default_factory=list)  # docker mode: LLM hosts (opt-in)
    app_path: str | None = None  # docker mode: HTTP path to POST questions to (override)
    app_port: int | None = None  # docker mode: container port the app listens on (override)


RuntimeState = Literal["idle", "building", "starting", "ready", "failed", "stopped"]


class RuntimeStatus(BaseModel):
    """Docker run lifecycle as shown to the user. Logs are secret-scrubbed and truncated."""

    state: RuntimeState = "idle"
    detail: str = ""
    kind: str = ""
    egress: str = "none"  # "none" | "allowlist: host, host"
    build_log: str = ""
    run_log: str = ""
    egress_log: list[str] = Field(default_factory=list)  # denied/allowed CONNECT evidence
    updated_at: float = 0.0


class Project(BaseModel):
    id: str
    repo_url: str
    branch: str | None = None
    subdir: str = ""
    state: ProjectState = "cloning"
    error: str | None = None
    created_at: float
    source: Literal["github", "upload"] = "github"
    authorized: bool = False
    authorized_at: float | None = None
    analysis: ProjectAnalysis | None = None
    inputs: ProjectInputs = Field(default_factory=ProjectInputs)
    runtime: RuntimeStatus | None = None
    target_config: TargetConfig | None = None  # how to call the user's endpoint (no secrets)
