from __future__ import annotations

import math

import pytest

from qe.campaign import analysis
from qe.campaign.execute import call_order
from qe.campaign.paired_ci import newcombe_paired, wilson
from qe.campaign.targets import stuff_documents
from qe.realeval.assemble import MIN_N_NOTE


def test_wilson_matches_textbook_value() -> None:
    lo, hi = wilson(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3) and hi == pytest.approx(0.9433, abs=1e-3)


def test_newcombe_paired_symmetry_and_zero_difference() -> None:
    d = newcombe_paired(40, 0, 0, 10)
    assert d.diff == 0 and d.ci_low < 0 < d.ci_high
    fwd = newcombe_paired(20, 15, 3, 12)
    rev = newcombe_paired(20, 3, 15, 12)
    assert fwd.diff == pytest.approx(-rev.diff)
    assert fwd.ci_low == pytest.approx(-rev.ci_high) and fwd.ci_high == pytest.approx(-rev.ci_low)
    assert fwd.ci_low > 0  # 15 vs 3 discordant is a clear A advantage
    assert fwd.cohens_h == pytest.approx(-rev.cohens_h)
    with pytest.raises(ValueError):
        newcombe_paired(0, 0, 0, 0)


def test_newcombe_known_value() -> None:
    # Newcombe (1998) worked example, table a=13 b=2 c=1... reproduced from the formula
    d = newcombe_paired(a_only=2, b_only=1, both=13, neither=4)
    assert d.n == 20 and d.diff == pytest.approx(0.05)
    assert d.ci_low < d.diff < d.ci_high and d.ci_low > -0.25 and d.ci_high < 0.35
    assert math.isfinite(d.cohens_h)


def test_percentile_nearest_rank() -> None:
    vals = [0.1, 0.2, 0.3, 0.4, 1.0]
    assert analysis.percentile(vals, 0.5) == 0.3
    assert analysis.percentile(vals, 0.99) == 1.0
    assert analysis.percentile([], 0.5) is None


def test_call_order_rotates_and_is_deterministic() -> None:
    labels = ["a", "b", "c"]
    firsts = [call_order(labels, i, 0)[0] for i in range(6)]
    assert firsts == ["a", "b", "c", "a", "b", "c"]
    assert sorted(call_order(labels, 4, 1)) == labels
    assert call_order(labels, 4, 1) == call_order(labels, 4, 1)


def test_stuffing_truncation_is_reported() -> None:
    docs = [{"name": "a.md", "text": "x" * 500}, {"name": "b.md", "text": "y" * 500}]
    text, cut = stuff_documents(docs, limit=700)
    assert cut and "[a.md]" in text and len(text) <= 700
    assert stuff_documents(docs, limit=5000)[1] is False


def _rows(passed: list[bool]) -> list[dict[str, object]]:
    return [{"id": f"i{k}", "lineage": None, "source": "user", "passed": v, "answerable": True,
             "scores": {"correct": v}} for k, v in enumerate(passed)]


def test_compare_label_logic_small_n_and_no_difference_and_win() -> None:
    small = analysis.compare({"a": _rows([True] * 5), "b": _rows([False] * 5)}, 0.05)
    assert small["pairs"][0]["outcome"] == "INSUFFICIENT_EVIDENCE"
    n = MIN_N_NOTE * 3
    same = analysis.compare({"a": _rows([True, False] * (n // 2)),
                             "b": _rows([True, False] * (n // 2))}, 0.05)
    assert same["pairs"][0]["outcome"] == "NO_SIGNIFICANT_DIFFERENCE"
    win = analysis.compare({"a": _rows([True] * n), "b": _rows([False] * n)}, 0.05)
    row = win["pairs"][0]
    assert row["outcome"] == "A_BETTER" and row["winner"] == "a" and row["p_adjusted"] < 0.05
    assert win["family_size"] == 2  # overall_pass_rate + answer_correctness are measurable
