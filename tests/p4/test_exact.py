from __future__ import annotations

import pytest

from qe.drift.exact import binom_cdf, binom_sf_ge, holm, mcnemar_exact


def test_binom_known_values() -> None:
    assert binom_cdf(0, 10, 0.5) == pytest.approx(1 / 1024)
    assert binom_sf_ge(10, 10, 0.5) == pytest.approx(1 / 1024)
    assert binom_sf_ge(0, 5, 0.3) == 1.0 and binom_sf_ge(6, 5, 0.3) == 0.0
    assert binom_cdf(5, 5, 0.3) == 1.0


def test_mcnemar_exact_matches_hand_computation() -> None:
    # b=1, c=7: two-sided = 2 * P(X<=1 | n=8) = 2 * 9/256
    assert mcnemar_exact(1, 7) == pytest.approx(18 / 256)
    assert mcnemar_exact(1, 7, "greater") == pytest.approx(9 / 256)
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0
    with pytest.raises(ValueError):
        mcnemar_exact(1, 2, "less")


def test_holm_is_monotone_and_bounded() -> None:
    adj = holm([0.01, 0.04, 0.03])
    assert adj == pytest.approx([0.03, 0.06, 0.06])
    assert all(0 <= a <= 1 for a in holm([0.5, 0.9]))
