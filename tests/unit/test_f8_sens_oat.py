"""F8b one-at-a-time sensitivity on tiny_golden (S0 manual vs S2 cube AS/RS): T8.3 (tornado sorted
by |ΔTCO|, one bar per scenario x parameter), δ = 0, documented parameters, the variants against
F8a's `evaluate_scenario`, override precedence, clipping of the fractions, determinism, infeasible
variants, the hook."""

from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import Mapping

import pytest
from tests.unit.test_f8_sens_fixtures import golden_ctx

from whsizing.errors import ConfigError, SizingInfeasibleError
from whsizing.scenarios import (
    PARAMS,
    Evaluated,
    RunContext,
    evaluate_scenario,
    run_sensitivity,
    sensitivity_oat,
)
from whsizing.scenarios import sensitivity as sens
from whsizing.schemas import Sensitivity

SPEC_PARAMS = {
    "labor_cost", "picking_productivity", "growth_rate", "equipment_capex", "design_percentile",
    "fill_factor", "oee",
}  # fmt: skip
BASELINES = ("S0", "client_current")


def tornado(ctx: RunContext, **kw: object) -> Sensitivity:
    return sensitivity_oat(ctx, **kw)  # type: ignore[arg-type]


def base_tco(ctx: RunContext) -> dict[str, float]:
    return {sid: ev.finance.tco.typ for sid, ev in sens.financed(ctx, sens.sized_all(ctx)).items()}


@pytest.mark.parametrize("baseline", BASELINES)
def test_T8_3_tornado_is_sorted_by_abs_delta_tco_one_bar_per_scenario_and_parameter(
    baseline: str,
) -> None:
    ctx = golden_ctx(baseline)
    s = tornado(ctx)
    ids = [sc.id for sc in ctx.scenarios.scenarios]
    pairs = [(b.scenario_id, b.param) for b in s.tornado]
    assert sorted(pairs) == sorted((i, p) for i in ids for p in PARAMS)  # exactly once each
    assert len(pairs) == len(set(pairs)) == len(ids) * len(PARAMS) == 14
    deltas = [b.delta_tco for b in s.tornado]
    assert (
        deltas == sorted(deltas, reverse=True) and deltas[0] > deltas[-1]
    )  # sorted, not all equal
    base = base_tco(ctx)
    assert s.base_tco == base and s.delta == 0.2
    for b in s.tornado:  # delta_tco = max |TCO - base TCO| of the bar's own two runs
        want = max(abs(b.tco_low - base[b.scenario_id]), abs(b.tco_high - base[b.scenario_id]))
        assert b.delta_tco == pytest.approx(want, abs=1e-6), b
        assert b.fte_low > 0 and b.fte_high > 0
    assert s.break_even == [] and s.percentile_sweep == []  # the tornado alone


def test_T8_3_the_seven_parameters_are_documented_and_every_bar_uses_one() -> None:
    assert set(PARAMS) == SPEC_PARAMS
    assert all(isinstance(doc, str) and len(doc) > 40 for doc in PARAMS.values())
    assert all("input" in doc for doc in PARAMS.values())  # each says what low/high_input is
    assert {b.param for b in tornado(golden_ctx()).tornado} == set(PARAMS)
    assert sens.__doc__ is not None and "PARAMS" in sens.__doc__
    only = tornado(golden_ctx(), params=["oee", "labor_cost", "oee"]).tornado
    assert {b.param for b in only} == {"oee", "labor_cost"} and len(only) == 4


@pytest.mark.parametrize("baseline", BASELINES)
def test_T8_3_delta_zero_gives_zero_delta_tco(baseline: str) -> None:
    ctx = golden_ctx(baseline)
    s = tornado(ctx, delta=0.0)
    base = s.base_tco
    for b in s.tornado:
        if b.param == "design_percentile":  # the spec fixes 90 / 98: delta does not apply
            continue
        assert b.delta_tco == pytest.approx(0, abs=1e-6), b.param
        assert b.tco_low == pytest.approx(base[b.scenario_id], abs=1e-6)
        assert b.tco_high == pytest.approx(base[b.scenario_id], abs=1e-6)
        assert (b.payback_low, b.fte_low) == (b.payback_high, b.fte_high)
    pct = [b for b in s.tornado if b.param == "design_percentile"]
    assert [(b.low_input, b.high_input) for b in pct] == [(90.0, 98.0)] * 2
    assert max(b.delta_tco for b in pct) > 1_000  # a real effect for S2


def test_directions_labor_up_costs_more_productivity_up_costs_less() -> None:
    bars = {(b.scenario_id, b.param): b for b in tornado(golden_ctx("client_current")).tornado}
    for sid in ("S0", "S2"):
        labor, pick = bars[sid, "labor_cost"], bars[sid, "picking_productivity"]
        assert (labor.low_input, labor.high_input) == (0.8, 1.2)
        assert labor.tco_low < labor.tco_high  # dearer labor: higher TCO
        assert pick.tco_low > pick.tco_high  # lower productivity: higher TCO
        assert labor.fte_low == labor.fte_high  # costs do not change the sizing
        assert labor.payback_low is not None and labor.payback_high is not None
    growth = bars["S0", "growth_rate"]
    assert growth.low_input == pytest.approx(0.032) and growth.high_input == pytest.approx(0.048)
    assert growth.tco_low < growth.tco_high
    assert bars["S2", "equipment_capex"].tco_low < bars["S2", "equipment_capex"].tco_high


def reference(ctx: RunContext, st: sens.Setting) -> dict[str, Evaluated]:
    """The same variant through F8a's `evaluate_scenario`, baseline first as the runner does."""
    sc = ctx.scenarios
    out: dict[str, Evaluated] = {}
    for s in sorted(st.scenarios, key=lambda s: s.id != sc.baseline):
        against = None if s.id == sc.baseline else out.get(sc.baseline)
        out[s.id] = evaluate_scenario(
            ctx, s, against, client_baseline=sc.baseline == "client_current",
            basis=st.basis, design_day=st.design_day,
        )  # fmt: skip
    return out


@pytest.mark.parametrize("baseline", BASELINES)
@pytest.mark.parametrize("name", sorted(PARAMS))
def test_every_variant_equals_evaluate_scenario_on_the_same_inputs(
    baseline: str, name: str
) -> None:
    """The sized-once / deep-copied-tracer path of F8b is F8a's re-sizing, result for result."""
    ctx = golden_ctx(baseline)
    sized = sens.sized_all(ctx)
    for sign in (-1, 1):
        st = sens.make_setting(ctx, name, sign, 0.2)
        mine, _ = sens._run(ctx, st, sized, name)  # pyright: ignore[reportPrivateUsage]
        ref = reference(ctx, st)
        assert list(mine) == list(ref)
        for sid in ref:
            assert mine[sid].result == ref[sid].result, (name, sign, sid)
            assert mine[sid].finance == ref[sid].finance, (name, sign, sid)


def test_the_base_run_equals_evaluate_scenario_and_sizing_can_be_financed_twice() -> None:
    ctx = golden_ctx("S0")
    sized = sens.sized_all(ctx)
    first, again = sens.financed(ctx, sized), sens.financed(ctx, sized)  # I73: a copy each time
    assert first["S2"].finance == again["S2"].finance
    ref = reference(ctx, sens.Setting(ctx.basis, ctx.design_day, ctx.scenarios.scenarios, {}, True))
    assert first["S2"].finance == ref["S2"].finance
    assert first["S2"].tracer is not sized["S2"].tracer  # the pre-finance tracer stays clean
    assert not any(n.id.startswith("S2.finance") for n in sized["S2"].tracer.nodes)


def test_catalog_variants_go_through_scenario_overrides_on_the_effective_typ() -> None:
    """S2 sets a port rate and the basis a manual pick rate (scenario overrides win): the variant
    is 1.2 x the effective typ, written to the scenario, never to basis.overrides."""
    ctx = golden_ctx()
    s0, s2 = ctx.scenarios.scenarios
    scenarios = ctx.scenarios.model_copy(
        update={
            "scenarios": [
                s0,
                s2.model_copy(update={"overrides": {"cube_asrs.port_rate_lines_h": 300}}),
            ]
        }
    )
    basis = ctx.basis.model_copy(
        update={"overrides": {"manual_p2p.pick_rate_shelving_lines_h": 62}}
    )
    ctx = dataclasses.replace(ctx, scenarios=scenarios, basis=basis)
    st = sens.make_setting(ctx, "picking_productivity", 1, 0.2)
    by_id = {s.id: s.overrides for s in st.scenarios}
    assert by_id["S2"]["cube_asrs.port_rate_lines_h"] == pytest.approx(360)
    assert by_id["S2"]["manual_p2p.pick_rate_shelving_lines_h"] == pytest.approx(62 * 1.2)
    assert by_id["S0"]["manual_p2p.pick_rate_shelving_lines_h"] == pytest.approx(62 * 1.2)
    assert "amr_gtp.station_rate_lines_h" not in by_id["S2"]  # another family's rate: untouched
    assert st.basis.overrides == basis.overrides and st.inputs == {"S0": 1.2, "S2": 1.2}
    capex = sens.make_setting(ctx, "equipment_capex", -1, 0.2)
    ids = set(capex.scenarios[1].overrides) - {"cube_asrs.port_rate_lines_h"}
    assert ids == {  # the equipment unit costs of S2's family and of manual_p2p, nothing else
        "cube_asrs.per_robot_eur", "cube_asrs.per_port_eur",
        "manual_p2p.per_cart_eur", "manual_p2p.per_forklift_eur",
    }  # fmt: skip


@pytest.mark.parametrize("sign", (-1, 1))
def test_equipment_capex_moves_the_equipment_item_not_storage_controls_or_works(sign: int) -> None:
    """Audit F8b/1: the bar was 'total capex +/- delta' (every unit cost moved); F7's equipment
    capex is the `equipment` item (maintenance base, I34), integration follows it."""
    ctx = golden_ctx()
    sized = sens.sized_all(ctx)
    base = sens.financed(ctx, sized)
    moved, _ = sens._run(  # pyright: ignore[reportPrivateUsage]
        ctx, sens.make_setting(ctx, "equipment_capex", sign, 0.2), sized, "equipment_capex"
    )
    f = 1 + 0.2 * sign
    for sid in ("S0", "S2"):
        c0, c1 = base[sid].finance.capex, moved[sid].finance.capex
        for fixed in ("storage", "controls", "building_works"):
            assert c1[fixed].typ == pytest.approx(c0[fixed].typ, rel=1e-9), (sid, fixed)
        assert c1["equipment"].typ == pytest.approx(f * c0["equipment"].typ, rel=1e-9), sid
        assert c1["integration_commissioning"].typ == pytest.approx(
            f * c0["integration_commissioning"].typ, rel=1e-9
        ), sid
    assert moved["S2"].finance.capex["overflow"].typ != pytest.approx(
        base["S2"].finance.capex["overflow"].typ
    )  # S2's overflow carts and forklifts are equipment too (I34)


def test_fill_factor_and_oee_are_fractions_kept_inside_the_catalog_range() -> None:
    ctx = golden_ctx()
    high = sens.make_setting(ctx, "oee", 1, 0.2)
    s2 = high.scenarios[1].overrides
    assert s2["cube_asrs.oee"] == pytest.approx(0.9)  # 0.85 x 1.2 = 1.02 -> catalog max
    assert s2["engine.pack_station_oee"] == pytest.approx(0.9)
    assert high.inputs["S2"] == pytest.approx(0.9) and set(high.inputs) == {"S0", "S2"}
    fill = sens.make_setting(ctx, "fill_factor", 1, 0.2)
    assert fill.scenarios[1].overrides["cube_asrs.fill_factor"] == pytest.approx(0.92)  # max
    assert fill.scenarios[1].overrides["manual_p2p.shelving_fill_factor"] == pytest.approx(0.9)
    assert all(v <= 1 for v in fill.scenarios[1].overrides.values())
    low = sens.make_setting(ctx, "fill_factor", -1, 0.2)
    assert low.scenarios[1].overrides["cube_asrs.fill_factor"] == pytest.approx(0.8)  # min
    none = sens.make_setting(ctx, "fill_factor", 1, 0.0)
    assert none.scenarios[1].overrides["cube_asrs.fill_factor"] == pytest.approx(0.88)  # typ


def test_a_variant_that_is_infeasible_leaves_out_its_bars_and_the_others_go_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = golden_ctx()
    real = sens.size_scenario

    def fake(profile, basis, design_day, scenario, *args, **kwargs):  # type: ignore[no-untyped-def]
        if scenario.id == "S2" and design_day.percentile == 98.0:
            raise SizingInfeasibleError("no SKU can be stored")
        return real(profile, basis, design_day, scenario, *args, **kwargs)

    monkeypatch.setattr(sens, "size_scenario", fake)
    pairs = {(b.scenario_id, b.param) for b in tornado(ctx, params=["design_percentile"]).tornado}
    assert pairs == {("S0", "design_percentile")}


def test_unknown_parameter_bad_delta_and_a_project_are_config_errors() -> None:
    ctx = golden_ctx()
    with pytest.raises(ConfigError, match="unknown parameter"):
        tornado(ctx, params=["labour_cost"])
    for bad in (-0.1, 1.0, 2.0):
        with pytest.raises(ConfigError, match="delta"):
            tornado(ctx, delta=bad)
    with pytest.raises(ConfigError, match="no parameter"):  # not a silently empty tornado
        tornado(ctx, params=[])
    with pytest.raises(ConfigError, match="RunContext"):
        sensitivity_oat(ctx.project)


@pytest.mark.bench  # C5 sensitivity row (7 parameters x 2): measured by `just bench`
def test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ctx = golden_ctx("client_current")
    t0 = time.perf_counter()
    one = tornado(ctx).model_dump_json(indent=2)
    seconds = time.perf_counter() - t0
    assert one == tornado(ctx).model_dump_json(indent=2)
    with capsys.disabled():
        print(f"\nF8b tiny_golden tornado (7 parameters x 2 scenarios x 2 runs): {seconds:.2f} s")
    assert seconds < 30


def test_the_hook_returns_tornado_break_even_and_sweep_with_the_runs_own_base_values() -> None:
    ctx = golden_ctx("client_current")
    evaluated: Mapping[str, Evaluated] = sens.financed(ctx, sens.sized_all(ctx))
    out = run_sensitivity(ctx, evaluated)
    assert out.delta == ctx.project.options.delta == 0.2
    assert out.base_tco == {sid: ev.finance.tco.typ for sid, ev in evaluated.items()}
    assert out.tornado == tornado(ctx).tornado
    assert [r.scenario_id for r in out.break_even] == ["S2"]  # automated scenarios only
    assert len(out.percentile_sweep) == 8  # 2 scenarios x P80/P90/P95/P98
    assert run_sensitivity(ctx, evaluated).model_dump_json() == out.model_dump_json()
    assert json.loads(out.model_dump_json())["tornado"][0]["delta_tco"] == out.tornado[0].delta_tco
