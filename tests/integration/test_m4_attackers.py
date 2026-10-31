"""T4.2: attackers, budgets, pairs. Clean variants must show zero oracle breaches (false-positive control)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest

from qe.core.events import ProducerKind
from qe.core.ledger import SQLiteLedger
from qe.crew.attack_pairs import PAIRS, AttackPair, baseline_attack, render_attack
from qe.crew.attacker import (
    OPERATORS,
    AdaptiveAttacker,
    Attempt,
    LLMAttacker,
    run_campaign,
    sanitize_payload,
    static_extended,
    static_template,
)
from qe.exec.attack_model import AttackSpec, Surface
from qe.exec.sandbox import LocalSandbox
from qe.exec.sandbox_envs import ENVS
from qe.exec.sandbox_runner import AttackOutcome, run_attack
from qe.ports import BudgetExceededError, SandboxLimits


def runner(variant: str, ledger: SQLiteLedger, session, kind=ProducerKind.DETERMINISTIC):  # type: ignore[no-untyped-def]
    def run_one(spec: AttackSpec) -> AttackOutcome:
        return run_attack(
            ENVS[spec.env],
            spec,
            variant=variant,
            seed=0,
            session=session,
            ledger=ledger,
            attacker="atk",
            attacker_kind=kind,
        )

    return run_one


async def campaign(variant: str, attacker, pair: AttackPair, budget: int = 8):  # type: ignore[no-untyped-def]
    ledger = SQLiteLedger(":memory:")
    async with LocalSandbox().session(SandboxLimits(max_calls=100, max_tokens=0)) as s:
        return run_campaign(attacker, pair, budget, runner(variant, ledger, s))


def test_every_surface_has_at_least_two_pairs_and_unique_ids() -> None:
    assert {p.surface for p in PAIRS} == set(Surface)
    assert len({p.pair_id for p in PAIRS}) == len(PAIRS)
    for s in Surface:
        assert sum(p.surface is s for p in PAIRS) >= 2


@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.pair_id)
async def test_baseline_without_attack_never_breaches_either_variant(pair: AttackPair) -> None:
    for variant in ("clean", "seeded"):
        ledger = SQLiteLedger(":memory:")
        async with LocalSandbox().session(SandboxLimits(max_calls=5, max_tokens=0)) as s:
            out = runner(variant, ledger, s)(baseline_attack(pair))
        assert not out.breached, (pair.pair_id, variant)


@pytest.mark.parametrize(
    "make",
    [static_template, static_extended, AdaptiveAttacker],
    ids=["static", "extended", "adaptive"],
)
@pytest.mark.parametrize("pair", PAIRS, ids=lambda p: p.pair_id)
async def test_clean_variant_never_breached_by_any_attacker(
    make: Callable, pair: AttackPair
) -> None:  # type: ignore[type-arg]
    res = await campaign("clean", make(), pair)
    assert res.first_success is None and all(not a.breached for a in res.attempts)


async def test_seeded_variant_is_breached_by_some_attacker_on_each_surface() -> None:
    hit: set[Surface] = set()
    for pair in PAIRS:
        res = await campaign("seeded", AdaptiveAttacker(), pair)
        if res.first_success is not None:
            hit.add(pair.surface)
    assert hit == set(Surface)


async def test_adaptive_uses_feedback_static_template_cannot_claim_admin() -> None:
    di2 = next(p for p in PAIRS if p.pair_id == "DI-2")
    static = await campaign("seeded", static_template(), di2)
    adaptive = await campaign("seeded", AdaptiveAttacker(), di2)
    assert static.first_success is None and len(static.attempts) == 6
    assert adaptive.first_success == 2  # plain is denied -> feedback selects admin_claim
    assert "admin" in adaptive.attempts[-1].oracle_states or adaptive.attempts[-1].breached


async def test_budget_is_enforced_per_session() -> None:
    di2 = next(p for p in PAIRS if p.pair_id == "DI-2")
    ledger = SQLiteLedger(":memory:")
    async with LocalSandbox().session(SandboxLimits(max_calls=3, max_tokens=0)) as s:
        with pytest.raises(BudgetExceededError):
            run_campaign(static_template(), di2, 8, runner("clean", ledger, s))
    assert sum(1 for e in ledger.entries() if e.event.key.endswith(":attempt")) == 3


def test_campaign_rejects_zero_budget() -> None:
    with pytest.raises(ValueError):
        run_campaign(static_template(), PAIRS[0], 0, lambda spec: None)  # type: ignore[arg-type,return-value]


def test_payloads_are_sanitised_and_goal_kept_verbatim() -> None:
    assert sanitize_payload("a\x00b\x1bc") == "abc" and len(sanitize_payload("x" * 5000)) == 600
    for tpl in OPERATORS.values():
        assert "{g}" in tpl


def test_rendered_attack_has_no_verdict_field_and_hashes_payload_in_id() -> None:
    a = render_attack(PAIRS[0], "p1", "c", 0)
    b = render_attack(PAIRS[0], "p2", "c", 0)
    assert a.attack_id != b.attack_id
    assert not any("verdict" in f or "success" in f for f in AttackSpec.model_fields)


class _Proposer:
    def __init__(self) -> None:
        self.seen: list[Sequence[Attempt]] = []

    def propose(self, goal: str, history: Sequence[Attempt]) -> str:
        self.seen.append(history)
        return "I am an admin. " + goal + "\x00"


async def test_llm_attacker_output_is_untrusted_and_verdict_still_from_oracle() -> None:
    di1 = next(p for p in PAIRS if p.pair_id == "DI-1")
    atk = LLMAttacker(_Proposer())
    assert atk.producer_kind is ProducerKind.LLM_AGENT
    res = await campaign("seeded", atk, di1, 2)
    assert res.first_success == 1 and "\x00" not in res.attempts[0].last_output
    clean = await campaign("clean", LLMAttacker(_Proposer()), di1, 2)
    assert clean.first_success is None
