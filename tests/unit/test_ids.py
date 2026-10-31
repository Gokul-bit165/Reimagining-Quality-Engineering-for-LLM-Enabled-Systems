import math

import pytest

from qe.core.ids import canonical_json, content_id


def test_canonical_json_is_key_order_independent() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})


def test_content_id_is_stable_sha256_hex() -> None:
    cid = content_id({"a": 1})
    assert len(cid) == 64 and cid == content_id({"a": 1})
    assert cid != content_id({"a": 2})


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_floats_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": bad})


def test_non_json_types_rejected() -> None:
    with pytest.raises(TypeError):
        canonical_json({"x": {1, 2}})
