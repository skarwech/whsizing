"""F7 properties (Hypothesis): T7.6 (higher labor cost never decreases the NPV of an automated
scenario against the manual one), and the metric invariants behind T7.2 / T7.3 on random flows.

T7.6 holds because both automated golden scenarios (S1 amr_gtp, S2 cube) use fewer hours than S0
in every role and every year, temp hours included; `test_T7_6_automated_labor_hours_are_lower`
pins that precondition, so the property is not vacuous."""

from __future__ import annotations

import copy
from functools import cache
from typing import Any

import numpy_financial as npf  # pyright: ignore[reportMissingTypeStubs]
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.unit.test_f6_size import golden_inputs, sized

from whsizing.finance import compute_finance, npv, payback
from whsizing.schemas import DesignBasis, ScenarioResult
from whsizing.schemas.trace import Tracer

PROPS = settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
ROLES = ("operator", "forklift_driver", "team_leader")
AUTOMATED = st.sampled_from(["S1", "S2"])


@cache
def sized_runs() -> dict[str, tuple[ScenarioResult, Tracer]]:
    return {sid: sized(sid) for sid in ("S0", "S1", "S2")}


def npv_vs_manual(sid: str, basis: DesignBasis) -> float:
    """NPV (typ) of `sid` against S0 under `basis` (only finance fields differ from F6's)."""
    runs, g = sized_runs(), golden_inputs()
    (s0, t0), (result, tracer) = runs["S0"], runs[sid]
    fin = compute_finance(
        result, basis, g.catalog, s0, daily=g.daily, tracer=copy.deepcopy(tracer),
        baseline_tracer=t0,
    )  # fmt: skip
    assert fin.npv_vs_baseline is not None
    return fin.npv_vs_baseline.typ


def with_finance(**change: Any) -> DesignBasis:
    b = golden_inputs().basis
    return b.model_copy(update={"finance": b.finance.model_copy(update=change)})


def hours_by_role(result: ScenarioResult) -> dict[str, list[float]]:
    """Direct annual hours per role and year (temp hours are counted for the operator role)."""
    out = {role: [0.0] * 5 for role in ROLES}
    for a in result.labor.activities:
        for t, h in enumerate(a.annual_hours):
            out[a.role][t] += h.typ
    for t, h in enumerate(result.labor.temp_hours):
        out["operator"][t] += h.typ
    return out


def test_T7_6_automated_labor_hours_are_lower_in_every_role_and_year() -> None:
    manual = hours_by_role(sized_runs()["S0"][0])
    for sid in ("S1", "S2"):
        auto = hours_by_role(sized_runs()[sid][0])
        for role in ROLES:
            assert all(a < m for a, m in zip(auto[role], manual[role], strict=True)), (sid, role)
        temp = [h.typ for h in sized_runs()[sid][0].labor.temp_hours]
        assert all(
            a < m.typ for a, m in zip(temp, sized_runs()["S0"][0].labor.temp_hours, strict=True)
        )


@PROPS
@given(
    sid=AUTOMATED,
    factors=st.lists(st.floats(1.0, 5.0), min_size=3, max_size=3),
    temp_premium=st.floats(0.15, 1.5),
    wage_inflation=st.floats(0.025, 0.12),
    shift_premium=st.floats(0.0, 0.6),
)
def test_T7_6_higher_labor_cost_never_decreases_the_npv_of_automation(
    sid: str,
    factors: list[float],
    temp_premium: float,
    wage_inflation: float,
    shift_premium: float,
) -> None:
    base = golden_inputs().basis.finance
    costs = {role: base.labor_cost_eur_h[role] * f for role, f in zip(ROLES, factors, strict=True)}
    higher = with_finance(
        labor_cost_eur_h=costs, temp_premium=temp_premium, wage_inflation=wage_inflation,
        shift_premium=shift_premium,
    )  # fmt: skip
    # the base basis has temp 0.15, wage 0.025, shift 0.0: every knob only goes up
    assert npv_vs_manual(sid, higher) >= npv_vs_manual(sid, golden_inputs().basis) - 1e-6


@PROPS
@given(sid=AUTOMATED, factor=st.floats(1.05, 5.0))
def test_T7_6_the_gain_is_strict_when_every_role_costs_more(sid: str, factor: float) -> None:
    base = golden_inputs().basis.finance
    higher = with_finance(
        labor_cost_eur_h={r: c * factor for r, c in base.labor_cost_eur_h.items()}
    )
    assert npv_vs_manual(sid, higher) > npv_vs_manual(sid, golden_inputs().basis)


flows = st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=2, max_size=12)


@PROPS
@given(flows=flows, rate=st.floats(0.0, 0.5))
def test_T7_2_npv_matches_numpy_financial_on_random_flows(flows: list[float], rate: float) -> None:
    expected = float(npf.npv(rate, flows))  # pyright: ignore[reportUnknownMemberType]
    assert npv(flows, rate) == pytest.approx(expected, rel=1e-9, abs=1e-6)


@PROPS
@given(capex=st.floats(1.0, 1e6), savings=st.lists(st.floats(0.0, 1e6), min_size=1, max_size=10))
def test_T7_3_payback_is_the_first_crossing_of_the_cumulative_flow(
    capex: float, savings: list[float]
) -> None:
    cf = [-capex, *savings]
    p = payback(cf)
    cum = [sum(cf[: t + 1]) for t in range(len(cf))]
    if p is None:
        assert cum[-1] < 0
        return
    year = int(-(-p // 1))  # ceil
    assert 0 < p <= len(savings) and cum[year] >= -1e-6
    assert all(c < 0 for c in cum[: max(year, 1)])  # not reached earlier
