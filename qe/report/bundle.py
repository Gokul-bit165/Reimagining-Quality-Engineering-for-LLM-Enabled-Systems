"""Reproducibility bundle (T6.2): everything needed to regenerate the Evidence Pack offline.

Contents: ledger.sqlite (consistent copy), policy.yaml, versions.txt (pip-freeze equivalent
from installed distribution metadata), prompt_hashes.json, pack.json / pack.md (as generated at
bundling time), MANIFEST.json (sha256 of every other file) and a README with the replay command.
`verify_bundle` re-derives the pack from the bundled ledger+policy and compares bytes.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

import qe
from qe.core.ids import sha256_hex
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import Policy
from qe.report.evidence_pack import build_pack, render_json, render_markdown

PROMPT_KEYS = ("prompt_hash", "prompt_sha256")
README = """# Reproducibility bundle

Regenerate the Evidence Pack offline from the bundled ledger and policy (no network, no LLM):

    python -m uv run qe report ledger.sqlite policy.yaml --format json > replay.json
    python -m uv run qe report ledger.sqlite policy.yaml --format md > replay.md

Check the manifest and the replay in one step:

    python -c "from qe.report.bundle import verify_bundle; print(verify_bundle('.'))"

`replay.json` must be byte-identical to `pack.json` (and `replay.md` to `pack.md`).

Files: `ledger.sqlite` (hash-chained evidence), `policy.yaml` (the decision policy),
`versions.txt` (python and installed package versions), `prompt_hashes.json` (prompt hashes
found in the ledger and in the packaged prompt files), `MANIFEST.json` (sha256 per file).

Claims not made. This bundle shows the report follows from the recorded
evidence. It does not show the target would behave the same if run again, and it carries no
external anchor for the ledger head, so removal of the newest entries is not detectable from
the bundle alone (anchor the head hash elsewhere).
"""


class BundleCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    ok: bool
    problems: tuple[str, ...] = ()


def write_bundle(ledger_path: Path, policy_path: Path, out: Path) -> None:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"output directory is not empty: {out}")
    source = SQLiteLedger(ledger_path)
    report = source.verify()
    if not report.ok:
        raise ValueError(f"ledger failed chain verification: {report.reason}")
    policy_text = policy_path.read_text(encoding="utf-8")
    policy = Policy.model_validate(yaml.safe_load(policy_text))
    out.mkdir(parents=True, exist_ok=True)
    _copy_sqlite(ledger_path, out / "ledger.sqlite")
    (out / "policy.yaml").write_bytes(policy_text.encode("utf-8"))
    pack = build_pack(SQLiteLedger(out / "ledger.sqlite"), policy)
    (out / "pack.json").write_bytes(render_json(pack).encode("utf-8"))
    (out / "pack.md").write_bytes(render_markdown(pack).encode("utf-8"))
    (out / "versions.txt").write_bytes(_versions().encode("utf-8"))
    (out / "prompt_hashes.json").write_bytes(
        _dump(_prompt_hashes(source)).encode("utf-8"))
    (out / "README.md").write_bytes(README.encode("utf-8"))
    manifest = {p.name: sha256_hex(p.read_bytes().decode("latin-1"))
                for p in sorted(out.iterdir())}
    (out / "MANIFEST.json").write_bytes(_dump(manifest).encode("utf-8"))


def verify_bundle(bundle: Path | str) -> BundleCheck:
    root = Path(bundle)
    problems: list[str] = []
    try:
        manifest: dict[str, str] = json.loads((root / "MANIFEST.json").read_text("utf-8"))
    except (OSError, ValueError):
        return BundleCheck(ok=False, problems=("MANIFEST.json missing or unreadable",))
    for name, digest in sorted(manifest.items()):
        path = root / name
        if not path.is_file() or sha256_hex(path.read_bytes().decode("latin-1")) != digest:
            problems.append(f"{name}: missing or altered since bundling")
    if not problems:
        problems += _replay_problems(root)
    return BundleCheck(ok=not problems, problems=tuple(problems))


def _replay_problems(root: Path) -> list[str]:
    ledger = SQLiteLedger(root / "ledger.sqlite")
    chain = ledger.verify()
    if not chain.ok:
        return [f"ledger.sqlite: chain verification failed ({chain.reason})"]
    policy = Policy.model_validate(yaml.safe_load((root / "policy.yaml").read_text("utf-8")))
    pack = build_pack(ledger, policy)
    problems = []
    if render_json(pack).encode("utf-8") != (root / "pack.json").read_bytes():
        problems.append("pack.json: does not match replay")
    if render_markdown(pack).encode("utf-8") != (root / "pack.md").read_bytes():
        problems.append("pack.md: does not match replay")
    return problems


def _copy_sqlite(src: Path, dst: Path) -> None:
    with closing(sqlite3.connect(str(src))) as s, closing(sqlite3.connect(str(dst))) as d:
        s.backup(d)
        d.execute("PRAGMA journal_mode=DELETE")


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _versions() -> str:
    dists = sorted({f"{d.metadata['Name'].lower()}=={d.version}"
                    for d in metadata.distributions() if d.metadata["Name"]})
    return "\n".join([f"python=={sys.version.split()[0]}", *dists]) + "\n"


def _walk(obj: Any, found: set[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in PROMPT_KEYS and isinstance(val, str):
                found.add(val)
            else:
                _walk(val, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, found)


def _prompt_hashes(ledger: SQLiteLedger) -> dict[str, Any]:
    found: set[str] = set()
    versions: set[str] = set()
    for entry in ledger.entries():
        _walk(entry.event.payload, found)
        v = entry.event.payload.get("versions")
        if isinstance(v, dict) and "prompt_version" in v:
            versions.add(str(v["prompt_version"]))
    files: dict[str, str] = {}
    prompts = Path(qe.__file__).parent / "crew" / "prompts"
    if prompts.is_dir():
        for p in sorted(prompts.rglob("*")):
            if p.is_file():
                files[p.relative_to(prompts).as_posix()] = _sha_file(p)
    return {"ledger": sorted(found), "prompt_versions": sorted(versions), "packaged_files": files}


def _sha_file(path: Path) -> str:
    return sha256_hex(path.read_bytes().decode("latin-1"))
