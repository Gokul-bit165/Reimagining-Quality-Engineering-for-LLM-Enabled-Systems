import random
from typing import Any

import pytest

from qe.core.events import EventType
from qe.core.ledger import SQLiteLedger
from qe.core.schemas import TestCase
from qe.regress.admission import admission_threshold, decide_admission, repeats_needed
from qe.regress.minimizer import ddmin, minimize_case, split_sentences
from qe.regress.store import SuiteStore


class FlakyTarget:
    """Fails iff input holds both trigger sentences; a real failure is masked with prob `flake`."""

    def __init__(self, flake: float, seed: int = 0, fixed: bool = False) -> None:
        self.rng, self.flake, self.fixed, self.calls = random.Random(seed), flake, fixed, 0

    def fails(self, case_input: dict[str, Any]) -> bool:
        self.calls += 1
        text = case_input["input"] + " ".join(case_input.get("context", []))
        real = "ALPHA" in text and "OMEGA" in text and not self.fixed
        return real and self.rng.random() >= self.flake


def test_ddmin_finds_one_minimal_pair_deterministically() -> None:
    items = list("abcdefghij")
    calls: list[int] = []

    def fails(sub: list[str]) -> bool:
        calls.append(1)
        return "c" in sub and "h" in sub

    assert ddmin(items, fails) == ["c", "h"]
    assert ddmin(items, fails) == ["c", "h"]
    assert len(calls) < 2 * 60


def test_ddmin_requires_the_full_input_to_fail() -> None:
    with pytest.raises(ValueError):
        ddmin(["a", "b"], lambda s: False)


def test_ddmin_single_and_empty_cases() -> None:
    assert ddmin(["x"], lambda s: True) == []
    assert ddmin(["x", "y"], lambda s: "y" in s) == ["y"]
    assert ddmin([], lambda s: True) == []


def test_split_sentences() -> None:
    assert split_sentences("One. Two!  Three?\nFour") == ["One.", "Two!", "Three?", "Four"]
    assert split_sentences("   ") == []


def test_repeats_needed_matches_flake_math() -> None:
    assert repeats_needed(0.0, 0.01) == 1
    assert repeats_needed(0.5, 0.01) == 7  # 0.5**7 = 0.0078 <= 0.01 < 0.5**6
    with pytest.raises(ValueError):
        repeats_needed(1.0, 0.01)


def test_minimize_case_on_flaky_target_keeps_only_trigger_pieces() -> None:
    target = FlakyTarget(flake=0.3, seed=5)
    case = TestCase(id="c0", oracle_source="none", input={
        "input": "Hello there. ALPHA is here. Filler one. Filler two. OMEGA now.",
        "context": ["noise doc", "other noise", "more"]})
    result = minimize_case(case, target.fails, flake_rate=0.3, alpha=0.001)
    assert result.case.input["input"] == "ALPHA is here. OMEGA now."
    assert result.case.input.get("context", []) == []
    assert result.case.lineage == ("c0",)
    assert result.case.id != "c0"
    assert result.original_pieces == 8 and result.final_pieces == 2


def test_minimize_case_that_does_not_reproduce_raises() -> None:
    target = FlakyTarget(flake=0.0, fixed=True)
    case = TestCase(id="c1", oracle_source="none", input={"input": "ALPHA. OMEGA."})
    with pytest.raises(ValueError, match="does not reproduce"):
        minimize_case(case, target.fails, flake_rate=0.0, alpha=0.01)


def test_admission_threshold_is_binomial_tail_not_a_constant() -> None:
    assert admission_threshold(k=10, flake_rate=0.0, alpha=0.01) == 10
    s = admission_threshold(k=20, flake_rate=0.3, alpha=0.01)
    assert 0 < s < 20
    from math import comb
    p = 0.7
    below = sum(comb(20, i) * p**i * (1 - p) ** (20 - i) for i in range(s))
    assert below <= 0.01
    below_next = sum(comb(20, i) * p**i * (1 - p) ** (20 - i) for i in range(s + 1))
    assert below_next > 0.01


def test_decide_admission_accepts_reliable_rejects_unreliable_and_unfixed() -> None:
    kw = {"k": 20, "flake_rate": 0.3, "alpha": 0.01}
    ok = decide_admission(buggy_failures=14, clean_failures=0, **kw)
    assert ok.admitted and ok.successes == 14 and ok.trials == 20
    low = decide_admission(buggy_failures=2, clean_failures=0, **kw)
    assert not low.admitted and "reproduce" in low.reason
    noisy_clean = decide_admission(buggy_failures=14, clean_failures=15, **kw)
    assert not noisy_clean.admitted and "clean" in noisy_clean.reason
    with pytest.raises(ValueError):
        decide_admission(buggy_failures=21, clean_failures=0, **kw)


def test_admission_end_to_end_with_flaky_target_both_versions() -> None:
    k = 30
    buggy, fixed = FlakyTarget(0.3, seed=1), FlakyTarget(0.3, seed=2, fixed=True)
    inp = {"input": "ALPHA is here. OMEGA now."}
    b = sum(buggy.fails(inp) for _ in range(k))
    c = sum(fixed.fails(inp) for _ in range(k))
    assert decide_admission(k=k, buggy_failures=b, clean_failures=c, flake_rate=0.3, alpha=0.01).admitted


def test_suite_store_lineage_and_idempotence() -> None:
    ledger = SQLiteLedger(":memory:")
    store = SuiteStore(ledger)
    root = TestCase(id="root", oracle_source="none", input={"input": "ALPHA. OMEGA. x."})
    mini = TestCase(id="mini", oracle_source="none", input={"input": "ALPHA. OMEGA."},
                    lineage=("root",))
    adm = decide_admission(k=10, buggy_failures=10, clean_failures=0, flake_rate=0.0, alpha=0.01)
    store.admit(mini, minimized_from="root", admission=adm, flake_rate=0.0, alpha=0.01)
    store.admit(mini, minimized_from="root", admission=adm, flake_rate=0.0, alpha=0.01)
    ev = [e for e in ledger.entries() if e.event.type is EventType.EVIDENCE_RECORDED]
    assert len(ev) == 1 and ev[0].event.payload["kind"] == "regression_case"
    (rc,) = store.regression_cases()
    assert rc.case_id == "mini" and rc.minimized_from == "root" and rc.pass_k_admission == (10, 10)
    assert store.lineage("mini") == ["mini", "root"]
    assert store.cases()[0].id == "mini"
    assert root.id == "root"


def test_suite_store_refuses_unadmitted_cases() -> None:
    store = SuiteStore(SQLiteLedger(":memory:"))
    bad = decide_admission(k=10, buggy_failures=0, clean_failures=0, flake_rate=0.0, alpha=0.01)
    case = TestCase(id="m", oracle_source="none", input={"input": "x"})
    with pytest.raises(ValueError, match="not admitted"):
        store.admit(case, minimized_from="r", admission=bad, flake_rate=0.0, alpha=0.01)
