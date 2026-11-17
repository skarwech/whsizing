"""F8b break-even: T8.4 (a synthetic case with a known root within 1e-3, through the solver and
through `break_even_rows` with a linear payback model; a real tiny_golden check that the returned k
reproduces the target payback when F7 is re-run), the bracketing function, and every None case."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from types import SimpleNamespace

import pytest
from tests.unit.test_f8_sens_fixtures import golden_ctx

from whsizing.errors import ConfigError
from whsizing.finance import metrics
from whsizing.scenarios import RunContext, break_even_rows
from whsizing.scenarios import breakeven as be
from whsizing.scenarios import sensitivity as sens

TOL = 1e-3


def linear(investment: float, saving: float, years: int) -> Callable[[float], list[float]]:
    """Δcf of a project that costs `investment` and saves `saving × k` a year: payback =
    investment / (saving × k) exactly (linear interpolation), known root for any target."""
    return lambda k: [-investment, *[saving * k] * years]


def test_T8_4_known_root_of_a_synthetic_case_within_1e_3() -> None:
    flows_at = linear(100.0, 40.0, 5)  # payback(k) = 2.5 / k
    for target in (1.0, 2.0, 2.5, 4.0, 5.0):
        k = be.solve(flows_at, target)
        assert k is not None and k == pytest.approx(2.5 / target, abs=TOL), target
        pay = metrics.payback(flows_at(k))
        assert pay is not None and abs(pay - target) <= TOL  # re-run at k*: the target again


def test_T8_4_no_root_in_the_bracket_or_beyond_the_horizon_is_none() -> None:
    flows_at = linear(100.0, 40.0, 5)
    assert be.solve(flows_at, 0.5) is None  # root 5.0 > 3: payback(3) = 0.83 > 0.5
    assert be.solve(flows_at, 9.0) is None  # beyond the horizon T = 5: not a payback
    assert be.solve(lambda k: [], 3.0) is None  # no baseline: no Δcf at all
    never = lambda k: [-100.0, -5.0 * k, -5.0 * k, -5.0 * k]  # noqa: E731  (saves nothing)
    assert be.solve(never, 2.0) is None  # extended payback > T for every k: no sign change


def test_T8_4_a_jump_of_the_payback_is_not_a_root() -> None:
    """The payback is not continuous (here: reached at k >= 1 only); brentq converges to the jump
    and F7, re-run there, does not give the target: None, not a wrong k."""

    def jump(k: float) -> list[float]:
        return [-100.0, 100.0 if k >= 1 else 0.0, 0.0, 0.0, 0.0, 0.0]

    assert be.solve(jump, 3.0) is None


def test_the_bracketing_function_is_continuous_at_the_horizon_and_monotone() -> None:
    assert be.extended_payback([-100, 40, 40, 40]) == pytest.approx(2.5)  # reached: F7's payback
    assert metrics.payback([-100, 30, 30, 30]) is None
    reached_at_t = [-90.0, 30.0, 30.0, 30.0]  # exactly T = 3
    assert be.extended_payback(reached_at_t) == pytest.approx(3.0)
    short = [-100.0, 30.0, 30.0, 30.0]  # 10 short of the investment at T: 3 + 10 / 100
    assert be.extended_payback(short) == pytest.approx(3.1)
    ks = [0.30, 0.31, 0.32, 0.33]
    values = [be.extended_payback(linear(100.0, 40.0, 3)(k)) for k in ks]  # k < 0.83: unreached
    assert values == sorted(values, reverse=True) and all(v > 3 for v in values)
    assert be.extended_payback([5.0, 1.0]) == 0.0  # Δcf_0 >= 0: payback 0


def fake_sized(ctx: RunContext) -> dict[str, SimpleNamespace]:
    return {s.id: SimpleNamespace() for s in ctx.scenarios.scenarios}


def test_T8_4_break_even_rows_with_a_linear_payback_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """`break_even_rows` on the golden structure (S0 manual, S2 cube) with F7 replaced by a
    model whose payback is 2.5 / k: S2 pays back in 2 years at k = 1.25, whatever the code."""
    ctx = golden_ctx("client_current")
    calls: list[float] = []

    def fake_financed(
        _ctx: RunContext, _sized: object, basis: object = None
    ) -> dict[str, SimpleNamespace]:
        costs = basis.finance.labor_cost_eur_h  # type: ignore[attr-defined]
        k = costs["operator"] / ctx.basis.finance.labor_cost_eur_h["operator"]  # the multiplier
        calls.append(k)
        flows = linear(100.0, 40.0, 5)(k)
        return {"S2": SimpleNamespace(finance=SimpleNamespace(delta_cash_flows_typ=flows))}

    monkeypatch.setattr(be, "sized_all", lambda c: fake_sized(c))
    monkeypatch.setattr(be, "financed", fake_financed)
    (row,) = break_even_rows(ctx, 2.0)
    assert (row.scenario_id, row.target_payback_years, row.bracket) == ("S2", 2.0, (0.3, 3.0))
    assert row.labor_cost_multiplier == pytest.approx(1.25, abs=TOL)
    assert be.breakeven(ctx, 2.0) == pytest.approx(1.25, abs=TOL)
    assert any(abs(k - 0.3) < 1e-12 for k in calls) and any(abs(k - 3.0) < 1e-12 for k in calls)


def payback_at(ctx: RunContext, sid: str, k: float) -> float | None:
    """F7 re-run with every role cost times k (the sizing is not redone: F6 reads no cost)."""
    ev = sens.financed(ctx, sens.sized_all(ctx), sens.labor_basis(ctx, k))
    return ev[sid].finance.payback_years


def test_T8_4_real_tiny_golden_the_returned_k_reproduces_the_target_when_rerun() -> None:
    ctx = golden_ctx("client_current")  # S2 vs the client's current operation
    k0 = 1.5
    target = payback_at(ctx, "S2", k0)
    assert target is not None and 0.1 < target < 5
    k = be.breakeven(ctx, target)  # one automated scenario: scenario_id may be left out
    assert k is not None and k == pytest.approx(k0, abs=TOL)
    rerun = payback_at(ctx, "S2", k)  # F7 again at k*
    assert rerun is not None and abs(rerun - target) <= TOL
    for wanted in (0.8, 2.0, 4.0):  # other targets inside the horizon
        k = be.breakeven(ctx, wanted, "S2")
        assert k is not None and 0.3 <= k <= 3.0
        rerun = payback_at(ctx, "S2", k)
        assert rerun is not None and abs(rerun - wanted) <= TOL, wanted


def test_T8_4_the_default_target_equals_the_horizon_and_still_reproduces_within_1e_3() -> None:
    """target = T = 5: the root sits where the cumulative cash is 0 at T, F7 may say None there."""
    ctx = golden_ctx("client_current")
    assert ctx.basis.finance.horizon_years == be.TARGET_PAYBACK_YEARS == 5.0
    (row,) = break_even_rows(ctx)
    k = row.labor_cost_multiplier
    assert k is not None and 0.3 < k < 0.5  # the labor saving must be ~1/3 of today's
    rerun = payback_at(ctx, "S2", k)
    assert rerun is not None and abs(rerun - 5.0) <= TOL
    assert payback_at(ctx, "S2", k - 0.01) is None  # below k* the payback is beyond the horizon


def test_none_when_the_scenario_never_pays_back_or_the_target_is_out_of_reach() -> None:
    s0_base = golden_ctx("S0")  # S2 costs more than S0 and saves nothing: never pays back
    (row,) = break_even_rows(s0_base)
    assert (row.scenario_id, row.labor_cost_multiplier) == ("S2", None)
    assert be.breakeven(s0_base, 3.0) is None
    client = golden_ctx("client_current")
    assert be.breakeven(client, 0.01) is None  # payback(3) = 0.39 > 0.01: no sign change
    assert be.breakeven(client, 7.0) is None  # beyond the 5-year horizon


def test_one_row_per_automated_scenario_never_the_manual_or_the_baseline_one() -> None:
    for baseline in ("S0", "client_current"):
        rows = break_even_rows(golden_ctx(baseline), 4.0)
        assert [r.scenario_id for r in rows] == ["S2"]
        assert all(r.target_payback_years == 4.0 for r in rows)
    ctx = golden_ctx("S0")
    both_auto = ctx.scenarios.model_copy(update={"baseline": "S2"})
    flipped = dataclasses.replace(ctx, scenarios=both_auto)  # the automated one is the baseline
    assert break_even_rows(flipped) == []  # S0 is manual; S2 is the baseline (no payback)


def test_config_errors() -> None:
    ctx = golden_ctx("client_current")
    with pytest.raises(ConfigError, match="target_payback"):
        break_even_rows(ctx, 0.0)
    with pytest.raises(ConfigError, match="name one automated scenario"):
        be.breakeven(ctx, 4.0, "S0")  # manual: has no row
    with pytest.raises(ConfigError, match="RunContext"):
        break_even_rows(ctx.project)


def test_extended_payback_equals_f7_payback_where_it_is_reached() -> None:
    ctx = golden_ctx("client_current")
    ev = sens.financed(ctx, sens.sized_all(ctx))["S2"].finance
    flows: Sequence[float] = ev.delta_cash_flows_typ
    assert ev.payback_years is not None
    assert be.extended_payback(flows) == ev.payback_years
