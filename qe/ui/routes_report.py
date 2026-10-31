"""HTTP API for the quality-tester report and the evidence bundle (see qe.qareport, ADR-0008)."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from qe.qareport import service
from qe.qareport.service import ReportConflictError, ReportNotFoundError, Source
from qe.realeval import audit, jobs

router = APIRouter()
CHUNK = 64 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024  # a rendered report larger than this is refused (413)
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
ID_PATTERNS = {"evaluation": r"^eval-[0-9a-f]{8}$", "campaign": r"^cmp-[0-9a-f]{8}$"}
EXTENSIONS = {"html": "html", "md": "md", "json": "json"}


def _source(loader: Callable[[str], Source], rid: str) -> Source:
    try:
        return loader(rid)
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ReportConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


def _report(loader: Callable[[str], Source], rid: str, fmt: str) -> Response:
    src = _source(loader, rid)
    body, media = service.render(src, fmt)
    if len(body) > MAX_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="report exceeds the size cap")
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'inline; filename="qa-report-{rid}.{EXTENSIONS[fmt]}"',
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


def _chunks(data: bytes) -> Iterator[bytes]:
    buf = io.BytesIO(data)
    while chunk := buf.read(CHUNK):
        yield chunk


def _bundle(loader: Callable[[str], Source], rid: str) -> StreamingResponse:
    src = _source(loader, rid)
    try:
        data = service.bundle(src)
    except ReportConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except OverflowError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    if len(data) > MAX_BUNDLE_BYTES:
        raise HTTPException(status_code=413, detail="evidence bundle exceeds the size cap")
    return StreamingResponse(_chunks(data), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="evidence-bundle-{rid}.zip"',
        "Content-Length": str(len(data)), "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store"})


def _check(kind: str, rid: str) -> None:
    import re
    if not re.match(ID_PATTERNS[kind], rid):
        raise HTTPException(status_code=404, detail=f"{kind} not found")


@router.get("/api/evaluations/{eval_id}/qa-report")
def evaluation_qa_report(eval_id: str, format: Literal["html", "md", "json"] = "html",
                         ) -> Response:
    _check("evaluation", eval_id)
    out = _report(service.evaluation_source, eval_id, format)
    audit.log(jobs.evals_dir(), "qa_report_exported", evaluation_id=eval_id, format=format)
    return out


@router.get("/api/evaluations/{eval_id}/evidence-bundle")
def evaluation_evidence_bundle(eval_id: str) -> StreamingResponse:
    _check("evaluation", eval_id)
    out = _bundle(service.evaluation_source, eval_id)
    audit.log(jobs.evals_dir(), "evidence_bundle_exported", evaluation_id=eval_id)
    return out


@router.get("/api/campaigns/{cid}/qa-report")
def campaign_qa_report(cid: str, format: Literal["html", "md", "json"] = "html") -> Response:
    _check("campaign", cid)
    return _report(service.campaign_source, cid, format)


@router.get("/api/campaigns/{cid}/evidence-bundle")
def campaign_evidence_bundle(cid: str) -> StreamingResponse:
    _check("campaign", cid)
    return _bundle(service.campaign_source, cid)
