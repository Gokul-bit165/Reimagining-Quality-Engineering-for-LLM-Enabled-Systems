"""Offline replay (T1.5): the Evidence Pack is a pure function of (ledger, policy).

`replay` re-renders the pack from a ledger and returns a SHA-256 digest of the exact
bytes; `verify_replay` raises if a stored digest no longer matches (changed ledger,
changed policy, or a non-deterministic renderer). A broken hash chain is reported via
`chain_ok` (and appears in the pack itself), never silently repaired.
"""

from __future__ import annotations

from dataclasses import dataclass

from qe.core.ids import sha256_hex
from qe.core.ledger import Ledger
from qe.core.schemas import Policy
from qe.report.evidence_pack import build_pack, render_json, render_markdown


class ReplayMismatchError(Exception):
    """Replayed bytes differ from the expected digest."""


@dataclass(frozen=True)
class ReplayResult:
    json: str
    markdown: str
    digest: str
    chain_ok: bool


def replay(ledger: Ledger, policy: Policy) -> ReplayResult:
    pack = build_pack(ledger, policy)
    js, md = render_json(pack), render_markdown(pack)
    return ReplayResult(json=js, markdown=md, digest=sha256_hex(js + "\n---\n" + md),
                        chain_ok=bool(pack["ledger"]["verified"]))


def verify_replay(ledger: Ledger, policy: Policy, expected_digest: str) -> ReplayResult:
    result = replay(ledger, policy)
    if result.digest != expected_digest:
        raise ReplayMismatchError(f"digest {result.digest} != expected {expected_digest}")
    return result
