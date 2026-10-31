"""Project ingest API: bring your own RAG app (GitHub URL or zip), analyse it, set test inputs."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from qe.ingest import jobs, paths, store
from qe.ingest.clone import IngestError, resolve_subdir
from qe.ingest.limits import (
    MAX_DOC_NAME,
    MAX_DOC_TEXT,
    MAX_DOCUMENTS,
    MAX_NOTES,
    MAX_PROJECTS,
    MAX_QA_PAIRS,
    MAX_QUESTION,
    MAX_REFERENCE,
    MAX_RISK_FOCUS,
    MAX_RISK_FOCUS_LEN,
    MAX_TOTAL_DOC_TEXT,
)
from qe.ingest.models import Project, ProjectInputs, QAPair, UserDocument
from qe.ingest.netguard import EndpointError, redact_url, validate_endpoint_url
from qe.ingest.suggest import suggest_documents
from qe.ingest.upload import MAX_UPLOAD_BYTES
from qe.ingest.url import RepoUrlError, parse_repo_url
from qe.ingest.vault import VAULT, SecretError

router = APIRouter()
_ATTEST_MSG = "you must confirm you own or are authorized to test this app"
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _check_endpoint(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    try:
        return validate_endpoint_url(v)
    except EndpointError as exc:
        raise ValueError(str(exc)) from None


class CreateProject(BaseModel):
    repo_url: str
    branch: str | None = None
    subdir: str = ""
    endpoint_url: str | None = None
    authorized: bool  # required: validators do not run on defaults

    @field_validator("authorized")
    @classmethod
    def _must_attest(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("you must confirm you own or are authorized to test this app")
        return v

    @field_validator("endpoint_url")
    @classmethod
    def _endpoint(cls, v: str | None) -> str | None:
        return _check_endpoint(v)

    @model_validator(mode="after")
    def _repo(self) -> CreateProject:
        try:
            parse_repo_url(self.repo_url, self.branch, self.subdir)
        except RepoUrlError as exc:
            raise ValueError(str(exc)) from None
        return self


class InputsBody(BaseModel):
    documents: list[UserDocument] | None = Field(default=None, max_length=MAX_DOCUMENTS)
    qa_pairs: list[QAPair] | None = Field(default=None, max_length=MAX_QA_PAIRS)
    endpoint_url: str | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    risk_focus: list[str] | None = Field(default=None, max_length=MAX_RISK_FOCUS)

    @field_validator("documents")
    @classmethod
    def _docs(cls, v: list[UserDocument] | None) -> list[UserDocument] | None:
        if v is None:
            return None
        total = 0
        for d in v:
            if not d.name.strip() or len(d.name) > MAX_DOC_NAME or _CTRL.search(d.name) \
                    or d.name.startswith("/") or "\\" in d.name or ":" in d.name \
                    or ".." in d.name.split("/"):
                raise ValueError("document name must be 1-200 printable characters")
            if len(d.text) > MAX_DOC_TEXT:
                raise ValueError(f"document {d.name[:40]!r} exceeds {MAX_DOC_TEXT} characters")
            total += len(d.text)
        if total > MAX_TOTAL_DOC_TEXT:
            raise ValueError("documents exceed the total size limit")
        return v

    @field_validator("qa_pairs")
    @classmethod
    def _qa(cls, v: list[QAPair] | None) -> list[QAPair] | None:
        for q in v or []:
            if not q.question.strip() or len(q.question) > MAX_QUESTION:
                raise ValueError(f"question must be 1-{MAX_QUESTION} characters")
            if q.reference_answer is not None and len(q.reference_answer) > MAX_REFERENCE:
                raise ValueError(f"reference_answer exceeds {MAX_REFERENCE} characters")
        return v

    @field_validator("risk_focus")
    @classmethod
    def _focus(cls, v: list[str] | None) -> list[str] | None:
        for r in v or []:
            if not r.strip() or len(r) > MAX_RISK_FOCUS_LEN or _CTRL.search(r):
                raise ValueError("risk_focus entries must be short printable strings")
        return v

    @field_validator("endpoint_url")
    @classmethod
    def _endpoint(cls, v: str | None) -> str | None:
        return _check_endpoint(v)


class SecretsBody(BaseModel):
    values: dict[str, Any]


def _view(p: Project, summary: bool = False) -> dict[str, Any]:
    data = p.model_dump(mode="json")
    inputs = data["inputs"]
    inputs["endpoint_url"] = redact_url(inputs.get("endpoint_url"))
    if summary:  # list view: no document or Q&A bodies
        inputs["documents"] = [{"name": d["name"], "chars": len(d["text"])}
                               for d in inputs["documents"]]
        inputs["qa_pairs_count"] = len(inputs.pop("qa_pairs"))
    data["secrets_set"] = VAULT.names(p.id)
    return data


def _load(project_id: str) -> Project:
    p = store.get(project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _new(repo_url: str, branch: str | None, subdir: str, source: str,
         endpoint_url: str | None) -> Project:
    if len(store.list_all()) >= MAX_PROJECTS:
        raise HTTPException(429, f"project limit ({MAX_PROJECTS}) reached; delete some first")
    now = time.time()
    p = Project(id=store.new_project_id(), repo_url=repo_url, branch=branch, subdir=subdir,
                created_at=now, source="upload" if source == "upload" else "github",
                authorized=True, authorized_at=now,
                inputs=ProjectInputs(endpoint_url=endpoint_url))
    store.save(p)
    store.record_attestation(p)
    return p


@router.post("/api/projects", status_code=202)
def create_project(body: CreateProject) -> dict[str, str]:
    _require_capacity()
    ref = parse_repo_url(body.repo_url, body.branch, body.subdir)
    p = _new(ref.display_url, ref.branch, ref.subdir, "github", body.endpoint_url)
    jobs.start(p.id, ref=ref)
    return {"id": p.id, "state": p.state}


def _require_capacity() -> None:
    if not jobs.has_capacity():
        raise HTTPException(429, "too many ingest jobs in progress; retry shortly")


def _truthy(v: object) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "on")


async def _save_upload(request: Request, dest: Path) -> tuple[bool, str]:
    """Stream the zip to `dest` (never held in memory). Returns (authorized, name)."""
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + 4096:
        raise HTTPException(413, "upload too large")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if ctype == "multipart/form-data":
        try:
            form = await request.form(max_files=1, max_fields=10)
        except AssertionError:
            raise HTTPException(415, "multipart needs python-multipart; send the zip as raw "
                                     "application/zip with ?authorized=true instead") from None
        up = form.get("file")
        if up is None or isinstance(up, str):
            raise HTTPException(422, "multipart field 'file' (zip) is required")
        authorized = _truthy(form.get("authorized", ""))
        if not authorized:
            raise HTTPException(422, _ATTEST_MSG)
        size = 0
        with open(dest, "wb") as out:
            while chunk := await up.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "upload too large")
                out.write(chunk)
        return authorized, up.filename or "upload.zip"
    if ctype not in ("application/zip", "application/octet-stream", "application/x-zip-compressed"):
        raise HTTPException(415, "send a .zip as multipart/form-data or application/zip")
    if not _truthy(request.query_params.get("authorized", "")):
        raise HTTPException(422, _ATTEST_MSG)
    size = 0
    with open(dest, "wb") as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "upload too large")
            out.write(chunk)
    return True, request.query_params.get("name", "upload.zip")


@router.post("/api/projects/upload", status_code=202)
async def upload_project(request: Request) -> dict[str, str]:
    _require_capacity()
    tmp = paths.runs_root() / "uploads" / f"{uuid.uuid4().hex}.zip"
    try:
        _authorized, name = await _save_upload(request, tmp)
        with open(tmp, "rb") as fh:
            if fh.read(2) != b"PK":
                raise HTTPException(422, "file is not a zip archive")
        try:
            endpoint = _check_endpoint(request.query_params.get("endpoint_url"))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:60] or "upload.zip"
        p = _new(f"upload://{safe}", None, "", "upload", endpoint)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    jobs.start(p.id, zip_path=tmp)
    return {"id": p.id, "state": p.state}


@router.get("/api/projects")
def list_projects() -> list[dict[str, Any]]:
    return [_view(p, summary=True) for p in store.list_all()]


@router.get("/api/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    return _view(_load(project_id))


@router.post("/api/projects/{project_id}/inputs")
def set_inputs(project_id: str, body: InputsBody) -> dict[str, Any]:
    p = _load(project_id)
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if "notes" in changes and changes["notes"] is None:
        changes["notes"] = ""
    changes = {k: v for k, v in changes.items() if v is not None or k == "endpoint_url"}
    inputs = p.inputs.model_copy(update=changes)
    analysis = p.analysis
    if analysis is not None and "endpoint_url" in changes:
        analysis = jobs.finalize_analysis(analysis, inputs.endpoint_url)
    updated = p.model_copy(update={"inputs": inputs, "analysis": analysis})
    store.save(updated)
    return inputs.model_dump(mode="json")


@router.get("/api/projects/{project_id}/inputs")
def get_inputs(project_id: str) -> dict[str, Any]:
    return _load(project_id).inputs.model_dump(mode="json")


@router.get("/api/projects/{project_id}/suggested-inputs")
def suggested_inputs(project_id: str) -> dict[str, Any]:
    p = _load(project_id)
    if p.state != "ready":
        raise HTTPException(409, f"project is {p.state}; suggestions are available when ready")
    try:
        root = resolve_subdir(paths.workspace_dir(p.id), p.subdir)
    except IngestError:
        raise HTTPException(404, "workspace not found") from None
    docs = suggest_documents(root)
    return {"documents": [{"name": d.name, "text": d.text, "chars": d.chars} for d in docs],
            "note": "Review these, then POST them to /inputs as documents to use as the "
                    "knowledge base."}


@router.post("/api/projects/{project_id}/secrets")
def set_secrets(project_id: str, body: SecretsBody) -> dict[str, Any]:
    p = _load(project_id)
    try:
        names = VAULT.set(p.id, body.values)
    except SecretError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"names": names, "stored": "memory only; lost on server restart"}


@router.get("/api/projects/{project_id}/secrets")
def get_secret_names(project_id: str) -> dict[str, Any]:
    p = _load(project_id)
    needed = p.analysis.env_vars if p.analysis else []
    have = VAULT.names(p.id)
    return {"set": have, "missing": [n for n in needed if n not in have]}


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    p = _load(project_id)
    VAULT.clear(p.id)
    store.delete(p.id)
    return {"deleted": p.id}
