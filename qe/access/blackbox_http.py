"""Black-box HTTP TargetPort + capability negotiation (research/14).

Protocol (the sandbox contract): GET /health, POST /invoke. Standard library only; the
blocking call runs in a worker thread so the event loop (and EgressGuard) stay in charge.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import AccessProfile, Span, VisibilityLevel
from qe.ports import TargetRequest, TargetResponse

TIMEOUT_S = 10.0


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (loopback only)
        parsed: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    return parsed


class BlackBoxHttpTarget:
    def __init__(self, base_url: str, visibility_level: VisibilityLevel = VisibilityLevel.A_BLACKBOX
                 ) -> None:
        self.base_url = base_url.rstrip("/")
        self.visibility_level = visibility_level

    async def invoke(self, request: TargetRequest) -> TargetResponse:
        body = {k: v for k, v in request.model_dump().items() if v is not None}
        try:
            raw = await asyncio.to_thread(_http, "POST", f"{self.base_url}/invoke", body)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return TargetResponse(output="", error=f"{type(exc).__name__}: {exc}")
        spans = tuple(
            Span(span_id=f"s{i}", kind=str(ev.get("type", "other")), attributes=ev)
            for i, ev in enumerate(raw.get("trace") or [])
        )
        return TargetResponse(output=str(raw.get("output", "")),
                              citations=tuple(str(c) for c in raw.get("citations") or []),
                              spans=spans, meta=dict(raw.get("meta") or {}))


_ORDER = list(VisibilityLevel)


async def negotiate(base_url: str, target_name: str = "target",
                    declared: VisibilityLevel | None = None) -> AccessProfile:
    """Probe what is observable. A = output only; B = the app returns trace events on request.

    Only what was actually observed is recorded; nothing is inferred (research/14).
    Levels C-E (OTel, repo, gateway) cannot be observed over this HTTP contract, so they
    are accepted only as `declared` by the operator and flagged `declared_level_unverified`.
    A declared level below the observed one is ignored (observation wins).
    """
    base = base_url.rstrip("/")
    caps: list[str] = []
    try:
        await asyncio.to_thread(_http, "GET", f"{base}/health")
        caps.append("health")
        probe = await asyncio.to_thread(
            _http, "POST", f"{base}/invoke", {"input": "ping", "want_trace": True, "seed": 0}
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ConnectionError(f"cannot connect to {base}: {exc}") from exc
    caps.append("invoke")
    level = VisibilityLevel.A_BLACKBOX
    if probe.get("trace"):
        caps.append("trace_in_response")
        level = VisibilityLevel.B_SDK
    if probe.get("citations") is not None:
        caps.append("citations")
    if declared is not None and _ORDER.index(declared) > _ORDER.index(level):
        level = declared
        caps.append("declared_level_unverified")
    return AccessProfile(target=target_name, visibility_level=level, capabilities=tuple(caps))


def record_access_profile(ledger: Ledger, profile: AccessProfile) -> None:
    """Write the negotiated profile to the ledger (idempotent per target+level+capabilities)."""
    payload = profile.model_dump(mode="json")
    key = f"access:{profile.target}:{profile.visibility_level.value}"
    if ledger.find_by_key(key) is not None:
        return
    ledger.append(Event(key=key, type=EventType.CAPABILITY_INVENTORY, producer="access",
                        producer_kind=ProducerKind.DETERMINISTIC, payload=payload))
