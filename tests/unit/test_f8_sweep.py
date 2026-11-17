"""F8b percentile sweep on tiny_golden: one row per scenario x percentile, design lines monotone in
the percentile and equal to F4's, the P95 row equal to the run's own results, equipment per family,
bad percentiles."""

from __future__ import annotations

import pytest
from tests.unit.test_f8_sens_fixtures import golden_ctx

from whsizing.design import select_design_day
from whsizing.errors import ConfigError
from whsizing.scenarios import percentile_sweep
from whsizing.scenarios import sensitivity as sens
from whsizing.scenarios.sweep import PERCENTILES

EQUIPMENT = {"S0": {"pickers_peak"}, "S2": {"pickers_peak", "ports", "robots"}}


def test_default_percentiles_are_the_spec_list() -> None:
    assert PERCENTILES == (80.0, 90.0, 95.0, 98.0)


@pytest.mark.parametrize("baseline", ["S0", "client_current"])
def test_percentile_sweep_has_one_row_per_scenario_and_percentile_monotone_in_design_lines(
    baseline: str,
) -> None:
    ctx = golden_ctx(baseline)
    rows = percentile_sweep(ctx, [80, 90, 95, 98])
    assert [(r.scenario_id, r.percentile) for r in rows] == [
        (sid, p) for sid in ("S0", "S2") for p in (80.0, 90.0, 95.0, 98.0)
    ]  # scenario file order, then the percentiles as given
    for sid in ("S0", "S2"):
        mine = [r for r in rows if r.scenario_id == sid]
        lines = [r.design_lines for r in mine]
        assert lines == sorted(lines) and len(set(lines)) == 4  # strictly increasing
        fte = [r.fte for r in mine]
        assert fte == sorted(fte)  # more design lines never need fewer heads
        assert all(set(r.equipment) == EQUIPMENT[sid] for r in mine)
        assert all(r.capex > 0 and r.tco > r.capex for r in mine)
    by_p = {
        p: {r.scenario_id: r.design_lines for r in rows if r.percentile == p} for p in PERCENTILES
    }
    assert all(v["S0"] == v["S2"] for v in by_p.values())  # one design day per percentile


def test_design_lines_are_the_f4_design_day_of_that_percentile() -> None:
    ctx = golden_ctx()
    for r in percentile_sweep(ctx, [80, 98]):
        basis = sens.with_projection(ctx.basis, design_percentile=r.percentile)
        dd = select_design_day(
            ctx.profile, basis, ctx.tables.daily, sku=ctx.sku, catalog=ctx.catalog
        )
        assert r.design_lines == dd.lines and dd.percentile == r.percentile


def test_the_row_at_the_basis_percentile_is_the_runs_own_result() -> None:
    ctx = golden_ctx("client_current")
    assert ctx.basis.projection.design_percentile == 95
    own = sens.financed(ctx, sens.sized_all(ctx))
    rows = {r.scenario_id: r for r in percentile_sweep(ctx, [95])}
    for sid, ev in own.items():
        assert rows[sid].tco == ev.finance.tco.typ and rows[sid].capex == ev.finance.capex_total.typ
        assert rows[sid].fte == ev.result.labor.total_heads.typ
        assert rows[sid].design_lines == ctx.design_day.lines
        assert rows[sid].equipment["pickers_peak"] == ev.result.equipment["pickers_peak"].typ


def test_percentiles_in_any_order_keep_the_order_given() -> None:
    rows = percentile_sweep(golden_ctx(), [98, 80])
    assert [(r.scenario_id, r.percentile) for r in rows] == [
        ("S0", 98.0), ("S0", 80.0), ("S2", 98.0), ("S2", 80.0),
    ]  # fmt: skip
    assert rows[0].design_lines > rows[1].design_lines


@pytest.mark.parametrize("bad", [[], [0], [-5, 90], [101], [95, 120]])
def test_bad_percentiles_are_config_errors(bad: list[float]) -> None:
    with pytest.raises(ConfigError, match="percentile"):
        percentile_sweep(golden_ctx(), bad)


def test_a_project_is_not_a_context() -> None:
    with pytest.raises(ConfigError, match="RunContext"):
        percentile_sweep(golden_ctx().project)
