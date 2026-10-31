"""ASR@budget and paired comparison: definitions, edge cases, properties."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from bench.asr import asr_at_budget, paired_comparison
from qe.stats.intervals import clopper_pearson

FS = {"a": 1, "b": 3, "c": None, "d": 2}


def test_asr_counts_only_successes_within_budget_and_has_exact_interval() -> None:
    e = asr_at_budget(FS, 2, "x")
    assert (e.successes, e.n_pairs, e.asr) == (2, 4, 0.5)
    assert (e.lower, e.upper) == clopper_pearson(2, 4)
    assert asr_at_budget(FS, 1, "x").successes == 1 and asr_at_budget(FS, 8, "x").successes == 3


def test_asr_is_monotone_in_budget() -> None:
    ks = [asr_at_budget(FS, b, "x").successes for b in range(1, 9)]
    assert ks == sorted(ks)


def test_asr_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        asr_at_budget({}, 1, "x")
    with pytest.raises(ValueError):
        asr_at_budget(FS, 0, "x")


def test_paired_counts_and_mcnemar_known_value() -> None:
    a = {f"p{i}": 1 for i in range(8)} | {f"q{i}": None for i in range(4)}
    b = {f"p{i}": None for i in range(8)} | {f"q{i}": None for i in range(4)}
    r = paired_comparison(a, b, 1, "adaptive", "static")
    assert (r.both, r.a_only, r.b_only, r.neither) == (0, 8, 0, 4)
    assert r.mcnemar_p == pytest.approx(2 * 0.5**8)  # exact two-sided, 0 vs 8 discordant
    assert r.diff == pytest.approx(8 / 12) and 0 < r.lower < r.diff < r.upper <= 1


def test_paired_no_discordance_gives_p_one_and_zero_diff() -> None:
    a = {"p": 1, "q": None}
    r = paired_comparison(a, a, 3, "a", "b")
    assert r.mcnemar_p == 1.0 and r.diff == 0.0 and r.lower <= 0.0 <= r.upper


def test_paired_requires_same_pairs() -> None:
    with pytest.raises(ValueError):
        paired_comparison({"p": 1}, {"q": 1}, 1, "a", "b")


arm = st.dictionaries(
    st.sampled_from([f"p{i}" for i in range(10)]),
    st.one_of(st.none(), st.integers(1, 8)),
    min_size=10,
    max_size=10,
)


@given(arm, arm, st.integers(1, 8))
def test_paired_interval_contains_difference_and_is_antisymmetric(
    a: dict[str, int | None], b: dict[str, int | None], budget: int
) -> None:
    r, s = paired_comparison(a, b, budget, "a", "b"), paired_comparison(b, a, budget, "b", "a")
    assert -1 <= r.lower <= r.diff + 1e-12 and r.diff - 1e-12 <= r.upper <= 1
    assert r.diff == pytest.approx(-s.diff) and r.lower == pytest.approx(-s.upper)
    assert r.mcnemar_p == pytest.approx(s.mcnemar_p)
