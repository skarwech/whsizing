"""F7 metrics on plain cash-flow lists: T7.2 (NPV = numpy_financial.npv), T7.3 (payback
interpolation) and the edge cases of the spec (capex delta ≤ 0, payback beyond the horizon,
IRR with several sign changes, annualised cost per line)."""

from __future__ import annotations

import math

import numpy_financial as npf  # pyright: ignore[reportMissingTypeStubs]
import pytest

from whsizing.errors import DataQualityError
from whsizing.finance import annuity_factor, cost_per_line, irr, npv, payback, tco


def test_T7_2_npv_equals_numpy_financial_and_delta_cf0_is_undiscounted() -> None:
    flows = [-282_430.0, 28_016.8, -3_000.0, 27_316.1, 26_929.7, 26_516.9]
    rate = 0.08
    assert npv(flows, rate) == pytest.approx(float(npf.npv(rate, flows)), rel=1e-12)  # pyright: ignore[reportUnknownMemberType]
    # Δcf_0 enters at face value: raising only year 0 by 1 EUR raises the NPV by exactly 1 EUR
    assert npv([flows[0] + 1.0, *flows[1:]], rate) - npv(flows, rate) == pytest.approx(1.0)
    # and the rest is discounted from t = 1: a lone year-1 flow of 108 is worth 100 at 8 %
    assert npv([0.0, 108.0], 0.08) == pytest.approx(100.0)


def test_T7_3_payback_interpolates_within_the_year() -> None:
    assert payback([-100, 40, 40, 40]) == pytest.approx(2.5)
    assert payback([-100, 100]) == pytest.approx(1.0)  # reached exactly at the end of year 1
    assert payback([-100, 30, 90]) == pytest.approx(1 + 70 / 90)


def test_payback_is_zero_when_the_scenario_is_not_dearer_than_the_baseline() -> None:
    """Capex delta ≤ 0 (Δcf_0 ≥ 0) → 0, also when later flows are negative."""
    assert payback([0.0, -5.0, -5.0]) == 0.0
    assert payback([25.0, -50.0, -50.0]) == 0.0


def test_payback_beyond_the_horizon_is_none() -> None:
    assert payback([-100, 10, 10, 10]) is None
    assert payback([-100.0, -10.0]) is None


def test_irr_single_sign_change_matches_numpy_financial() -> None:
    flows = [-100.0, 40.0, 40.0, 40.0]
    value, why = irr(flows)
    assert why is None
    assert value == pytest.approx(0.09701025740327318, rel=1e-9)
    assert npv(flows, value or 0.0) == pytest.approx(0.0, abs=1e-6)  # the root of the NPV
    # zeros do not count as a sign change (I37) but stay in the series (they are idle years)
    shifted = [0.0, -100.0, 0.0, 40.0, 40.0, 40.0]
    assert irr(shifted)[0] == pytest.approx(float(npf.irr(shifted)))  # pyright: ignore[reportUnknownMemberType]


def test_irr_is_none_with_a_note_for_several_sign_changes() -> None:
    value, why = irr([-100.0, 150.0, -60.0, 40.0])  # −, +, −, +: three sign changes
    assert value is None
    assert why is not None and "3 times" in why
    assert irr([-100.0, 150.0, -60.0, -10.0])[0] is None  # two changes


@pytest.mark.parametrize("flows", [[-1.0, -2.0, -3.0], [1.0, 2.0, 3.0], [0.0, 0.0]])
def test_irr_is_none_without_a_sign_change(flows: list[float]) -> None:
    value, why = irr(flows)
    assert value is None and why is not None and "no sign change" in why


def test_tco_discounts_opex_from_year_one_and_leaves_capex_at_face_value() -> None:
    assert tco(1000.0, [108.0, 116.64], 0.08) == pytest.approx(1000.0 + 100.0 + 100.0)
    assert tco(500.0, [], 0.08) == 500.0


def test_cost_per_line_annualises_the_tco() -> None:
    """TCO × r / (1 − (1 + r)^−T) / lines; the golden S0 figure (App. B)."""
    assert annuity_factor(0.08, 5) == pytest.approx(0.08 / (1 - 1.08**-5))
    assert cost_per_line(502_085.55640707567, 0.08, 5, 18_960.48) == pytest.approx(
        6.632246037385842, rel=1e-12
    )
    # r = 0: the annuity factor is the limit 1 / T, not a division by zero
    assert annuity_factor(0.0, 4) == 0.25
    assert not math.isnan(cost_per_line(1000.0, 0.0, 4, 10.0))


@pytest.mark.parametrize("lines", [0.0, -1.0, math.nan])
def test_cost_per_line_without_annual_lines_is_a_data_quality_error(lines: float) -> None:
    """F7 audit finding 7: the operating-day lines summing to 0 gave a raw ZeroDivisionError."""
    with pytest.raises(DataQualityError, match="annual lines"):
        cost_per_line(1000.0, 0.08, 5, lines)
