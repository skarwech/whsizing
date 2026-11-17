"""R5 (F8b open issue): `Sensitivity.skipped` lists every variant left out of the tornado, the
break-even and the sweep (scenario, parameter, direction, reason), the baseline's included, and
explains the payback None next to a baseline that is not computed. tiny_golden: S0 manual, S2 cube.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.unit.test_f8_sens_fixtures import golden_ctx

from whsizing.errors import SizingInfeasibleError
from whsizing.scenarios import run_sensitivity, sensitivity_oat
from whsizing.scenarios import sensitivity as sens
from whsizing.schemas import DesignDay, Sensitivity

REASON = "SizingInfeasibleError: no SKU can be stored"


def fail_when(monkeypatch: pytest.MonkeyPatch, when: Callable[[str, DesignDay], bool]) -> None:
    """F6 raises SizingInfeasibleError for the (scenario id, design day) pairs `when` selects."""
    real = sens.size_scenario

    def fake(profile, basis, design_day, scenario, *args, **kwargs):  # type: ignore[no-untyped-def]
        if when(scenario.id, design_day):
            raise SizingInfeasibleError("no SKU can be stored")
        return real(profile, basis, design_day, scenario, *args, **kwargs)

    monkeypatch.setattr(sens, "size_scenario", fake)


def test_a_clean_run_has_nothing_skipped() -> None:
    ctx = golden_ctx()
    assert sensitivity_oat(ctx).skipped == []
    evaluated = sens.financed(ctx, sens.sized_all(ctx))
    assert run_sensitivity(ctx, evaluated).skipped == []


def test_a_left_out_variant_names_scenario_parameter_direction_and_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx()
    fail_when(monkeypatch, lambda sid, dd: sid == "S2" and dd.percentile == 98.0)
    s = sensitivity_oat(ctx, params=["design_percentile"])
    assert s.skipped == [f"S2 design_percentile high: {REASON}"]  # one line, no payback line
    assert [(b.scenario_id, b.param) for b in s.tornado] == [("S0", "design_percentile")]


def test_a_baseline_left_out_of_a_variant_explains_the_payback_none_of_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx()  # baseline S0
    fail_when(monkeypatch, lambda sid, dd: sid == "S0" and dd.percentile == 98.0)
    s = sensitivity_oat(ctx, params=["design_percentile"])
    assert s.skipped == [
        f"S0 design_percentile high: {REASON}",
        "S2 design_percentile high: payback is None, baseline S0 is not computed",
    ]
    (bar,) = s.tornado  # S0 has no bar at all; S2 keeps one whose high payback is the None above
    assert bar.scenario_id == "S2" and bar.payback_high is None


def test_a_baseline_not_computed_at_all_is_listed_at_base_and_in_every_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx()
    fail_when(monkeypatch, lambda sid, dd: sid == "S0")
    s = sensitivity_oat(ctx, params=["labor_cost"])
    none = "payback is None, baseline S0 is not computed"
    assert s.skipped == [
        f"S0 base: {REASON}",
        f"S2 base: {none}",
        f"S2 labor_cost low: {none}",
        f"S2 labor_cost high: {none}",
    ]
    assert set(s.base_tco) == {"S2"} and {b.scenario_id for b in s.tornado} == {"S2"}
    assert all(b.payback_low is None and b.payback_high is None for b in s.tornado)


def test_client_current_baseline_never_needs_a_payback_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx("client_current")
    fail_when(monkeypatch, lambda sid, dd: sid == "S2" and dd.percentile == 98.0)
    s = sensitivity_oat(ctx, params=["design_percentile"])
    assert s.skipped == [f"S2 design_percentile high: {REASON}"]


def test_the_hook_lists_the_sweep_rows_it_could_not_make_in_order_and_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx()
    fail_when(monkeypatch, lambda sid, dd: sid == "S2" and dd.percentile in (80.0, 98.0))
    evaluated = sens.financed(ctx, sens.sized_all(ctx))
    s = run_sensitivity(ctx, evaluated)
    assert s.skipped == [  # tornado variants first (the 98th percentile bar), then the sweep
        f"S2 design_percentile high: {REASON}",
        f"S2 percentile sweep P80: {REASON}",
        f"S2 percentile sweep P98: {REASON}",
    ]
    assert [r.percentile for r in s.percentile_sweep if r.scenario_id == "S2"] == [90.0, 95.0]
    assert [r.percentile for r in s.percentile_sweep if r.scenario_id == "S0"] == [80, 90, 95, 98]
    again = run_sensitivity(ctx, evaluated)
    assert again.model_dump_json() == s.model_dump_json()
    assert Sensitivity.model_validate_json(s.model_dump_json()).skipped == s.skipped
