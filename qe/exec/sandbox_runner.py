"""Sandbox runner (T4.1): executes one AttackSpec in a fresh app, decides with outcome oracles.

Attackers PROPOSE (`ATTACK_ATTEMPTED` is their only event type); this module executes, measures and
writes the evidence/verdict events deterministically (R3, R5). One call = one budgeted attempt.
Resume: if the evidence event for an attempt exists, the stored outcome is returned, not re-run.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from qe.core.events import Event, EventType, ProducerKind
from qe.core.ledger import Ledger
from qe.core.schemas import ClaimState, Frozen
from qe.exec.attack_model import AttackSpec
from qe.exec.oracles import OracleContext, diff_state, evaluate_oracle
from qe.exec.sandbox_envs import SandboxEnv
from qe.ports import SandboxSession

PRODUCER = "sandbox_runner"
ATTACKER_DOMAINS = ("evil.example",)  # attacker-controlled sinks: what a real attacker can observe


class AttackOutcome(Frozen):
    attack_id: str
    pair_id: str
    variant: str
    attacker_class: str
    attempt_index: int
    breached: bool
    oracle_states: dict[str, str]
    utility_ok: bool | None
    last_output: str  # what the attacker can read back
    attacker_sink_hit: bool  # a sink controlled by the attacker received something
    state_diff: dict[str, list[str]]
    egress_attempts: tuple[str, ...]


def attempt_key(variant: str, attack_id: str) -> str:
    return f"atk:{variant}:{attack_id}"


def _tool_calls(responses: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for r in responses for e in r.get("trace", []) if e.get("type") == "tool_call"]


def _hits_attacker_sink(sinks: Sequence[dict[str, Any]]) -> bool:
    return any(d in str(v) for s in sinks for v in s.values() for d in ATTACKER_DOMAINS)


def outcome_from_ledger(ledger: Ledger, variant: str, attack_id: str) -> AttackOutcome | None:
    entry = ledger.find_by_key(attempt_key(variant, attack_id) + ":evidence")
    if entry is None:
        return None
    return AttackOutcome.model_validate(entry.event.payload["outcome"])


def run_attack(
    env: SandboxEnv,
    attack: AttackSpec,
    *,
    variant: str,
    seed: int,
    session: SandboxSession,
    ledger: Ledger,
    attacker: str,
    attacker_kind: ProducerKind,
) -> AttackOutcome:
    """Run one attempt. Raises BudgetExceededError / KillSwitchError from `session.charge`."""
    stored = outcome_from_ledger(ledger, variant, attack.attack_id)
    if stored is not None:
        return stored
    base = attempt_key(variant, attack.attack_id)
    session.charge(calls=1)
    ledger.append(
        Event(
            key=base + ":attempt",
            type=EventType.ATTACK_ATTEMPTED,
            producer=attacker,
            producer_kind=attacker_kind,
            payload={"attack": attack.model_dump(mode="json"), "variant": variant, "seed": seed},
        )
    )
    app = env.build(variant, seed)
    for op in attack.setup:
        env.apply(app, op)
    before = app.snapshot_state()
    responses: list[dict[str, Any]] = []
    outputs: dict[str, list[str]] = {"attacker": [], "victim": []}
    for step in attack.steps:
        resp = app.invoke({**step.request, "want_trace": True})
        responses.append(resp)
        outputs[step.actor].append(str(resp["output"]))
    after = app.snapshot_state()
    sinks = app.sinks()
    ctx = OracleContext(
        before=before,
        after=after,
        sinks=sinks,
        outputs={k: tuple(v) for k, v in outputs.items()},
        tool_calls=_tool_calls(responses),
        retrieved=[
            str(r.get("chunk_text", ""))
            for resp in responses
            for e in resp.get("trace", [])
            if e.get("type") == "retrieval"
            for r in e.get("results", [])
        ],
    )
    claim_id = f"{attack.attack_id}:{variant}:resisted"
    verdicts = [(spec.kind, evaluate_oracle(claim_id, spec, ctx)) for spec in attack.oracles]
    for i, (kind, v) in enumerate(verdicts):
        ledger.append(
            Event(
                key=f"{base}:verdict:{i}",
                type=EventType.VERDICT_ISSUED,
                producer=PRODUCER,
                producer_kind=ProducerKind.DETERMINISTIC,
                payload={
                    "metric": f"attack_oracle:{kind}",
                    "case_id": attack.attack_id,
                    "run_key": base + ":attempt",
                    "verdict": v.model_dump(mode="json"),
                },
            )
        )
    victim_out = outputs["victim"][-1] if outputs["victim"] else ""
    utility = (
        None if attack.utility_regex is None else bool(re.search(attack.utility_regex, victim_out))
    )
    last = outputs["attacker"][-1] if outputs["attacker"] else ""  # attacker never sees victim text
    outcome = AttackOutcome(
        attack_id=attack.attack_id,
        pair_id=attack.pair_id,
        variant=variant,
        attacker_class=attack.attacker_class,
        attempt_index=attack.attempt_index,
        breached=any(v.state is ClaimState.CONTRADICTED for _, v in verdicts),
        oracle_states={kind: v.state.value for kind, v in verdicts},
        utility_ok=utility,
        last_output=last,
        attacker_sink_hit=_hits_attacker_sink(sinks),
        state_diff=diff_state(before, after),
        egress_attempts=session.egress_attempts(),
    )
    ledger.append(
        Event(
            key=base + ":evidence",
            type=EventType.EVIDENCE_RECORDED,
            producer=PRODUCER,
            producer_kind=ProducerKind.DETERMINISTIC,
            payload={
                "outcome": outcome.model_dump(mode="json"),
                "sinks": sinks,
                "tool_calls": _tool_calls(responses),
            },
        )
    )
    return outcome
