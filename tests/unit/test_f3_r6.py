"""R6 remediation of the F3f open issue: the EIQ and daily statistics took np.mean / np.std over
arrays listed in hashed order_id order, so the last ULP of mean and CV moved with the salt."""

from __future__ import annotations

import numpy as np
import pytest

from whsizing.profile.aggregate import series_stats


def skewed(seed: int) -> np.ndarray:
    """Values over six orders of magnitude, like order cubes: float addition order matters."""
    return np.random.default_rng(seed).lognormal(0.0, 3.0, 2000)


@pytest.mark.parametrize("seed", [0, 1, 3])
def test_R6_4_series_stats_are_bit_identical_whatever_the_order_of_the_values(seed: int) -> None:
    x = skewed(seed)
    orders = [x, x[::-1], np.random.default_rng(99).permutation(x)]
    # the premise: numpy alone is order dependent on this data (the bug this test would have caught)
    assert (
        len({float(np.mean(p)) for p in orders}) > 1 or len({float(np.std(p)) for p in orders}) > 1
    )
    stats = [series_stats(p) for p in orders]
    assert stats[0] == stats[1] == stats[2]  # every field, bit for bit (SeriesStats equality)
    assert stats[0].model_dump_json() == stats[2].model_dump_json()


def test_R6_4_series_stats_still_equal_numpy_within_rounding() -> None:
    x = skewed(5)
    s = series_stats(x)
    assert s.mean == pytest.approx(float(np.mean(x)), rel=1e-12)
    assert s.cv == pytest.approx(float(np.std(x) / np.mean(x)), rel=1e-12)
    assert s.max == float(np.max(x))
    assert s.p95 == float(np.percentile(x, 95))
    assert series_stats(np.array([1.0, 2.0, 3.0, 4.0])).cv == pytest.approx(
        np.sqrt(1.25) / 2.5, rel=1e-15
    )  # hand check: population std of 1..4 is sqrt(1.25), mean 2.5


def test_R6_4_a_constant_series_has_cv_zero_and_an_all_zero_series_does_not_divide() -> None:
    assert series_stats(np.full(10, 3.3)).cv == 0.0
    zero = series_stats(np.zeros(4))
    assert (zero.mean, zero.cv) == (0.0, 0.0)
