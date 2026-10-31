"""Zip upload extraction: zip-slip safe, symlink-free, size/file-count capped (zip-bomb safe)."""

from __future__ import annotations

import io
import posixpath
import re
import stat
import zipfile
from pathlib import Path

from qe.ingest.clone import IngestError, WorkspaceStats, rmtree, sanitize_workspace
from qe.ingest.limits import MAX_REPO_BYTES, MAX_REPO_FILES

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_CHUNK = 64 * 1024


_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


def _safe_member(name: str) -> str:
    norm = posixpath.normpath(name.replace("\\", "/"))
    for comp in norm.split("/"):
        if _RESERVED.match(comp) or comp != comp.rstrip(" .") and comp not in ("..", "."):
            raise IngestError(f"unsafe path in archive: {name[:80]!r}")
    if (name.startswith(("/", "\\")) or norm.startswith("../") or norm == ".."
            or ":" in norm.split("/")[0] or "\x00" in name or norm in ("", ".")):
        raise IngestError(f"unsafe path in archive: {name[:80]!r}")
    return norm


def extract_zip(data: bytes | Path, dest: Path) -> WorkspaceStats:
    source: io.BytesIO | Path
    if isinstance(data, Path):
        if data.stat().st_size > MAX_UPLOAD_BYTES:
            raise IngestError("upload too large")
        source = data
    else:
        if len(data) > MAX_UPLOAD_BYTES:
            raise IngestError("upload too large")
        source = io.BytesIO(data)
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile:
        raise IngestError("not a valid zip file") from None
    infos = zf.infolist()
    if len(infos) > MAX_REPO_FILES:
        raise IngestError("archive has too many entries")
    if sum(i.file_size for i in infos) > MAX_REPO_BYTES:
        raise IngestError("archive expands beyond the size limit")
    dest.mkdir(parents=True)
    base = dest.resolve()
    written = 0
    try:
        for info in infos:
            rel = _safe_member(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise IngestError("symlinks in archives are not allowed")
            target = (base / rel).resolve()
            if not target.is_relative_to(base):
                raise IngestError("zip-slip path rejected")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                while chunk := src.read(_CHUNK):
                    written += len(chunk)
                    if written > MAX_REPO_BYTES:
                        raise IngestError("archive expands beyond the size limit")
                    out.write(chunk)
        return sanitize_workspace(dest)
    except BaseException:
        rmtree(dest)
        raise
    finally:
        zf.close()
