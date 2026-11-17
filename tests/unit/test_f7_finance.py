"""F7 `compute_finance` on tiny_golden (S0 manual, S1 amr_gtp inline, S2 cube): T7.4 (rent
modes), T7.5 (renewal), the amr_gtp worked example (hand-computed, the golden case has no AMR
scenario), the I48 degenerate scenario, the baselines (none, client current, a scenario), Range
ordering, determinism of finance.json and trace.jsonl, and that every number of finance.json
has a TraceNode with the value in the typ world and the min / max over the worlds in lo / hi."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from tests.unit.test_f6_size import ROOT, golden_inputs, sized, with_basis

from whsizing.engine import WORLDS, write_scenario
from whsizing.errors import ConfigError, DataQualityError, WhsizingError
from whsizing.finance import compute_finance, write_finance
from whsizing.schemas import (
    DesignBasis,
    EligibilityCfg,
    FinancialResult,
    Range,
    ScenarioDef,
    ScenarioResult,
)
from whsizing.schemas.trace import Tracer

NO_ELIGIBLE = EligibilityCfg(extra_max_weight_kg=0.001)  # no SKU fits: I48 degenerate cube


class Run(NamedTuple):
    result: ScenarioResult
    tracer: Tracer
    fin: FinancialResult


def finance_all(**change: Any) -> dict[str, Run]:
    """S0 (no baseline: it is the baseline), S1 and S2 against S0, on the golden inputs with any
    of basis / design_day / sku / daily / lines replaced."""
    g = golden_inputs()
    basis: DesignBasis = change.get("basis", g.basis)
    sized_ = {sid: sized(sid, **change) for sid in g.scenarios}
    base_result, base_tracer = sized_["S0"]
    out: dict[str, Run] = {}
    for sid, (result, tracer) in sized_.items():
        is_base = sid == "S0"
        fin = compute_finance(
            result, basis, g.catalog, None if is_base else base_result,
            daily=g.daily, tracer=tracer,
            baseline_tracer=None if is_base else base_tracer, client_baseline=False,
        )  # fmt: skip
        out[sid] = Run(result, tracer, fin)
    return out


def write_all(out: Path | str, **change: Any) -> dict[str, bytes]:
    """finance.json and trace.jsonl bytes of S0, S1, S2: finance first, then the trace."""
    files: dict[str, bytes] = {}
    for sid, run in finance_all(**change).items():
        write_finance(run.fin, out)
        folder = write_scenario(run.result, run.tracer, out)
        files[f"{sid}/finance.json"] = (folder / "finance.json").read_bytes()
        files[f"{sid}/trace.jsonl"] = (folder / "trace.jsonl").read_bytes()
    return files


def node(tracer: Tracer, sid: str, key: str, world: str = "typ") -> float:
    return tracer.get(f"{sid}.{key}", world).value  # pyright: ignore[reportArgumentType]


def amr(horizon: int = 5) -> tuple[ScenarioResult, Tracer]:
    return sized("S1", basis=with_basis(finance={"horizon_years": horizon}))


# ---------------------------------------------------------------- T7.4
def test_T7_4_full_building_rent_is_identical_across_scenarios_and_cancels() -> None:
    basis = with_basis(building={"rent_mode": "full_building"})
    runs = finance_all(basis=basis)
    expected = basis.building.area_m2 * basis.building.rent_eur_m2_year  # 410 × 58
    for sid in ("S0", "S1", "S2"):
        assert all(row["rent"] == expected for row in runs[sid].fin.opex_by_year)
        for w in WORLDS:  # the three worlds too
            assert node(runs[sid].tracer, sid, "opex.y3.rent", w) == expected
    for sid in ("S1", "S2"):
        fin, base = runs[sid].fin, runs["S0"].fin
        for t, (row, brow) in enumerate(zip(fin.opex_by_year, base.opex_by_year, strict=True), 1):
            assert brow["rent"] - row["rent"] == 0.0  # zero rent delta
            others = sum(brow[k] - row[k] for k in row if k != "rent")
            assert fin.delta_cash_flows_typ[t] == pytest.approx(others, rel=1e-12)


def test_T7_4_footprint_rent_differs_by_scenario_and_none_is_zero() -> None:
    footprint = finance_all()
    rents = {sid: r.fin.opex_by_year[0]["rent"] for sid, r in footprint.items()}
    assert len(set(rents.values())) == 3  # area.total × 58 differs per scenario
    assert rents["S0"] == pytest.approx(node(footprint["S0"].tracer, "S0", "area.total") * 58)
    none = finance_all(basis=with_basis(building={"rent_mode": "none"}))
    assert all(row["rent"] == 0.0 for r in none.values() for row in r.fin.opex_by_year)


# ---------------------------------------------------------------- T7.5
def s0_with_life(years: float) -> ScenarioDef:
    overrides = {"manual_p2p.equipment_life_years": years}
    return ScenarioDef(id="S0", name="manual", family="manual_p2p", overrides=overrides)


def fin_of(scenario: ScenarioDef | str, **change: Any) -> FinancialResult:
    g = golden_inputs()
    result, tracer = sized(scenario, **change)
    basis: DesignBasis = change.get("basis", g.basis)
    return compute_finance(result, basis, g.catalog, None, daily=g.daily, tracer=tracer)


@pytest.mark.parametrize("life", [1, 3, 5])
def test_T7_5_renewal_appears_exactly_at_equipment_life_years(life: int) -> None:
    fin = fin_of(s0_with_life(life))
    equipment = fin.capex["equipment"].typ  # 2 carts + 1 forklift = 38 000, renewal_share 0.5
    renewals = [row["renewal"] for row in fin.opex_by_year]
    assert renewals == [0.5 * equipment if t == life else 0.0 for t in range(1, 6)]
    plain = fin_of("S0")
    assert all(row["renewal"] == 0.0 for row in plain.opex_by_year)  # life 10 > T = 5: never
    year_total = fin.opex_by_year[life - 1]
    assert sum(year_total.values()) - sum(plain.opex_by_year[life - 1].values()) == (
        pytest.approx(0.5 * equipment)
    )
    # TCO counts the renewal discounted like any other opex of that year
    assert fin.tco.typ - plain.tco.typ == pytest.approx(0.5 * equipment / 1.08**life)


def test_T7_5_no_renewal_when_the_life_exceeds_the_horizon() -> None:
    for life in (6, 7.5, 10):
        assert all(r["renewal"] == 0.0 for r in fin_of(s0_with_life(life)).opex_by_year)


def test_T7_5_amr_gtp_default_life_of_8_years_with_an_8_year_horizon() -> None:
    """No override: catalog amr_gtp life 8, renewal_share 0.6, on the robots + stations item."""
    result, tracer = amr(horizon=8)
    g = golden_inputs()
    basis = with_basis(finance={"horizon_years": 8})
    fin = compute_finance(result, basis, g.catalog, None, daily=g.daily, tracer=tracer)
    assert [r["renewal"] for r in fin.opex_by_year] == [0.0] * 7 + [0.6 * 100_000.0]
    assert len(fin.cash_flows_typ) == 9  # year 0..8


# ---------------------------------------------------------------- amr_gtp worked example
def test_amr_gtp_capex_and_opex_equal_the_hand_computation() -> None:
    """S1 = amr_gtp on tiny_golden (F6 typ quantities, read from the ScenarioResult):
    2 robots, 1 station, 9 pods (23.4 m² of pods), 1 cart, 1 forklift, 67.7 pallet positions
    in 38.12 m² … overflow, area.total 432.138 m². Catalog typ values: robot 30 000, station
    40 000, pod 900, charging 0, fleet software 150 000, floor prep 20 €/m², shares 0.10 + 0.05
    and 0.10; manual: 90 €/position, 12 €/bin, cart 1 500, forklift 35 000, works 60 €/m²."""
    run = finance_all()["S1"]
    r, fin = run.result, run.fin
    robots, stations = r.equipment["robots"].typ, r.equipment["gtp_stations"].typ
    carts, forklifts = r.equipment["carts"].typ, r.equipment["forklifts"].typ
    assert (robots, stations, carts, forklifts) == (2, 1, 1, 1)
    classes = {(c.storage_class, c.zone): c for c in r.storage.classes}
    pods = classes["pod_bin", "main"].pods
    assert pods is not None and pods.typ == 9
    pod_area = classes["pod_bin", "main"].area_m2.typ  # 9 × 2.6 m²
    assert pod_area == pytest.approx(23.4)
    rack = classes["pallet_rack", "overflow"].positions.typ
    bins = classes["shelving", "overflow"].positions.typ
    area = r.area.total_m2.typ

    storage = 9 * 900
    equipment = 2 * (30_000 + 0) + 1 * 40_000
    controls = 150_000
    works = area * 60 + pod_area * 20
    overflow = rack * 90 + bins * 12 + 1 * 1_500 + 1 * 35_000
    ic = (0.10 + 0.05) * equipment
    contingency = 0.10 * (storage + equipment + controls + works + overflow + ic)
    expected = {
        "storage": 8_100.0, "equipment": 100_000.0, "controls": 150_000.0,
        "building_works": works, "overflow": overflow,
        "integration_commissioning": 15_000.0, "contingency": contingency,
    }  # fmt: skip
    for item, value in expected.items():
        assert fin.capex[item].typ == pytest.approx(value, rel=1e-12), item
    assert fin.capex_total.typ == pytest.approx(sum(expected.values()), rel=1e-12)
    # the worked figure: (8 100 + 100 000 + 150 000 + 26 396.28 + 39 930.59 + 15 000) × 1.10, with
    # works = 432.138 × 60 + 23.4 × 20 and overflow = 38.1176 × 90 + 0 × 12 + 1 500 + 35 000
    assert fin.capex_total.typ == pytest.approx(339_426.87 * 1.10, abs=0.01)

    y1 = fin.opex_by_year[0]
    assert y1["maintenance"] == pytest.approx(0.06 * 100_000 + 0.04 * (1_500 + 35_000))  # 7 460
    assert y1["energy"] == pytest.approx((2 * 1_500 + 1 * 1_500 + 1 * 4_500 + 20_000) * 0.17)
    assert y1["software"] == 40_000.0
    assert y1["rent"] == pytest.approx(area * 58)
    assert y1["renewal"] == 0.0
    cost = {"operator": 25.5, "forklift_driver": 27.8, "team_leader": 33.0}
    for t in (1, 2, 3):
        direct = sum(a.annual_hours[t - 1].typ * cost[a.role] for a in r.labor.activities)
        temp = r.labor.temp_hours[t - 1].typ * 25.5 * 1.15
        assert fin.opex_by_year[t - 1]["labor"] == pytest.approx(
            (direct + temp) * 1.025 ** (t - 1), rel=1e-12
        )
    assert y1["consumables"] == pytest.approx(9_757.44 * 0.9)  # 968 orders × 252 / 26 × 1.04


def test_amr_gtp_overrides_flow_into_capex() -> None:
    """A scenario override replaces typ: per_robot 30 000 → 40 000 adds 2 × 10 000 to the
    equipment item and the integration share of it."""
    base = finance_all()["S1"].fin
    s1 = (
        golden_inputs()
        .scenarios["S1"]
        .model_copy(update={"overrides": {"amr_gtp.per_robot_eur": 40_000.0}})
    )
    fin = fin_of(s1)
    assert fin.capex["equipment"].typ - base.capex["equipment"].typ == pytest.approx(20_000.0)
    assert fin.capex["integration_commissioning"].typ == pytest.approx(0.15 * 120_000.0)


# ---------------------------------------------------------------- I48
def test_I48_degenerate_cube_is_costed_like_the_manual_scenario() -> None:
    """Zero eligible lines: manual formulas on the scenario's manual classes, WMS adaptation and
    manual software, no automation capex, overflow 0; same figures as S0 in every world."""
    g = golden_inputs()
    s3 = ScenarioDef(id="S3", name="no eligible", family="cube_asrs", eligibility=NO_ELIGIBLE)
    result, tracer = sized(s3)
    assert result.eligibility.share_lines == 0
    s0, t0 = sized("S0")
    fin = compute_finance(result, g.basis, g.catalog, s0, daily=g.daily, tracer=tracer,
                          baseline_tracer=t0)  # fmt: skip
    base = finance_all()["S0"].fin
    assert fin.capex["overflow"].typ == 0.0 and fin.capex["controls"].typ == 50_000.0
    assert fin.capex_total == base.capex_total  # Range equality: all three worlds
    assert fin.opex_by_year[0]["software"] == 15_000.0
    assert fin.opex_by_year == base.opex_by_year
    assert fin.npv_vs_baseline == Range(lo=0.0, typ=0.0, hi=0.0, unit="eur")
    assert any("I48" in n for n in fin.notes)


# ---------------------------------------------------------------- baselines
def test_no_baseline_gives_none_metrics_and_absolute_tco_only() -> None:
    fin = finance_all()["S0"].fin
    assert fin.npv_vs_baseline is None and fin.irr_vs_baseline is None
    assert fin.payback_years is None
    assert fin.delta_cash_flows_typ == []
    assert len(fin.cash_flows_typ) == 6 and fin.cash_flows_typ[0] == -fin.capex_total.typ
    assert fin.tco.typ > fin.capex_total.typ and fin.cost_per_line.typ > 0
    assert any("absolute TCO only" in n for n in fin.notes)


def test_client_current_baseline_without_actuals_is_none() -> None:
    """baseline=None with the default client_baseline=True but nothing in basis.baseline."""
    g = golden_inputs()
    result, tracer = sized("S2")
    fin = compute_finance(result, g.basis, g.catalog, None, daily=g.daily, tracer=tracer)
    assert (
        fin.npv_vs_baseline is None and fin.irr_vs_baseline is None and not fin.delta_cash_flows_typ
    )


def test_client_current_baseline_uses_actual_hours_and_fte() -> None:
    """Capex 0 (sunk); opex_t = Σ actual hours × (1 + g)^t × cost × (1 + wage)^(t−1) + the
    scenario's own consumables and rent. picking: 2 FTE × 1 607 h × 0.85 utilisation (the F6
    core_fte convention), but `actual_hours_month` (1 200 h a year) wins for packing_S; both are
    operators at 25.5 €/h."""
    g = golden_inputs()
    basis = g.basis.model_copy(
        update={
            "baseline": g.basis.baseline.model_copy(
                update={"actual_fte": {"picking": 2.0, "packing_S": 9.0},
                        "actual_hours_month": {"packing_S": [100.0] * 12}}
            )
        }
    )  # fmt: skip
    result, tracer = sized("S2", basis=basis)
    fin = compute_finance(result, basis, g.catalog, None, daily=g.daily, tracer=tracer)
    assert fin.delta_cash_flows_typ[0] == -fin.capex_total.typ
    for t in range(1, 6):
        labor = (2 * 1607 * 0.85 + 1200) * 25.5 * 1.04**t * 1.025 ** (t - 1)
        row = fin.opex_by_year[t - 1]
        baseline_opex = labor + row["consumables"] + row["rent"]
        assert fin.delta_cash_flows_typ[t] == pytest.approx(
            baseline_opex - sum(row.values()), rel=1e-12
        )
    assert fin.npv_vs_baseline is not None
    assert any("client's current operation" in n for n in fin.notes)
    off = compute_finance(result, basis, g.catalog, None, daily=g.daily,
                          tracer=copy.deepcopy(tracer), client_baseline=False)  # fmt: skip
    assert off.npv_vs_baseline is None


def test_scenario_baseline_uses_its_computed_capex_and_opex_per_world() -> None:
    """I42: Δcf_0 = −(capex_S2 − capex_S0), Δcf_t = opex_S0,t − opex_S2,t, with S0 costed in the
    same world as S2: in the lo world the baseline is the lo-world S0, not the typ one."""
    runs = finance_all()
    t2 = runs["S2"].tracer
    for w in WORLDS:
        cap2, cap0 = (
            node(t2, "S2", "capex.total", w),
            node(runs["S0"].tracer, "S0", "capex.total", w),
        )
        assert node(t2, "S2", "finance.baseline.capex", w) == cap0
        assert node(t2, "S2", "finance.delta_cf.y0", w) == pytest.approx(-(cap2 - cap0))
        assert node(t2, "S2", "finance.delta_cf.y2", w) == pytest.approx(
            node(runs["S0"].tracer, "S0", "opex.y2.total", w) - node(t2, "S2", "opex.y2.total", w)
        )
    npv_lo = node(t2, "S2", "finance.npv", "lo")
    assert runs["S2"].fin.npv_vs_baseline is not None
    assert (
        min(node(t2, "S2", "finance.npv", w) for w in WORLDS) == runs["S2"].fin.npv_vs_baseline.lo
    )
    assert npv_lo == pytest.approx(
        sum(node(t2, "S2", f"finance.delta_cf.y{t}", "lo") / 1.08**t for t in range(6))
    )


def test_irr_with_several_sign_changes_is_none_with_a_note() -> None:
    """Labor 20x dearer makes S2 save every year, but a renewal of 5 x its equipment item in
    year 3 (life 3, renewal_share 5) flips that year: Δcf = −, +, +, −, +, +: IRR None + note."""
    g = golden_inputs()
    costs = {k: 20 * v for k, v in g.basis.finance.labor_cost_eur_h.items()}
    basis = g.basis.model_copy(
        update={"finance": g.basis.finance.model_copy(update={"labor_cost_eur_h": costs})}
    )
    overrides = {"cube_asrs.equipment_life_years": 3.0, "cube_asrs.renewal_share": 5.0}
    s2 = g.scenarios["S2"].model_copy(update={"overrides": overrides})
    (r2, t2), (r0, t0) = sized(s2, basis=basis), sized("S0", basis=basis)
    fin = compute_finance(r2, basis, g.catalog, r0, daily=g.daily, tracer=t2, baseline_tracer=t0)
    assert [x > 0 for x in fin.delta_cash_flows_typ] == [False, True, True, False, True, True]
    assert fin.irr_vs_baseline is None
    assert any("sign 3 times" in n for n in fin.notes)
    assert not any(n.id == "S2.finance.irr" for n in t2.nodes)  # no node for an undefined IRR
    assert fin.npv_vs_baseline is not None  # the NPV is still defined


def test_negative_capex_delta_gives_payback_zero_and_the_trace_node() -> None:
    """S0 as the 'scenario' against the dearer S2 as baseline: cheaper capex → payback 0."""
    g = golden_inputs()
    (s0, t0), (s2, t2) = sized("S0"), sized("S2")
    fin = compute_finance(s0, g.basis, g.catalog, s2, daily=g.daily, tracer=t0, baseline_tracer=t2)
    assert fin.delta_cash_flows_typ[0] > 0
    assert fin.payback_years == 0.0
    assert node(t0, "S0", "finance.payback_years") == 0.0


# ---------------------------------------------------------------- errors
def test_input_errors_are_named() -> None:
    g = golden_inputs()
    (s0, _t0), (s2, t2) = sized("S0"), sized("S2")
    daily = g.daily

    def call(**kw: Any) -> FinancialResult:
        args: dict[str, Any] = {"daily": daily, "tracer": copy.deepcopy(t2)}
        return compute_finance(s2, kw.pop("basis", g.basis), g.catalog, kw.pop("baseline", None),
                               **(args | kw))  # fmt: skip

    with pytest.raises(ConfigError, match="baseline_tracer"):
        call(baseline=s0)
    with pytest.raises(ConfigError, match="own baseline"):
        call(baseline=s2, baseline_tracer=t2)
    with pytest.raises(WhsizingError, match=r"S2\.area\.total"):
        call(tracer=Tracer("S2"))
    partial = g.basis.finance.model_copy(update={"labor_cost_eur_h": {"operator": 30.0}})
    basis = g.basis.model_copy(update={"finance": partial})
    assert call(basis=basis).opex_year1.typ > 0  # missing roles take the catalog defaults
    short = g.basis.finance.model_copy(update={"horizon_years": 3})
    with pytest.raises(ConfigError, match=r"has 5 years"):
        call(basis=g.basis.model_copy(update={"finance": short}))
    bad = s2.model_copy(update={"status": "not_computed", "status_reason": "test"})
    with pytest.raises(WhsizingError, match="not_computed"):
        compute_finance(bad, g.basis, g.catalog, None, daily=daily, tracer=copy.deepcopy(t2))
    with pytest.raises(ConfigError, match="use letters"):
        write_finance(finance_all()["S0"].fin.model_copy(update={"scenario_id": "a/b"}), "x")


@pytest.mark.parametrize("typo", ["operatr", "forklift", "driver"])
def test_a_misspelled_labor_role_is_a_config_error_naming_the_valid_roles(typo: str) -> None:
    """F7 audit finding 6: an unknown key of finance.labor_cost_eur_h was silently ignored (the
    catalog default was used instead, with no note)."""
    g = golden_inputs()
    (s2, t2) = sized("S2")
    costs = {**g.basis.finance.labor_cost_eur_h, typo: 30.0}
    fin = g.basis.finance.model_copy(update={"labor_cost_eur_h": costs})
    basis = g.basis.model_copy(update={"finance": fin})
    with pytest.raises(ConfigError, match=rf"unknown role.*'{typo}'") as e:
        compute_finance(s2, basis, g.catalog, None, daily=g.daily, tracer=copy.deepcopy(t2))
    for role in ("operator", "forklift_driver", "team_leader"):
        assert role in str(e.value)  # the valid roles


def test_annual_lines_summing_to_zero_is_a_data_quality_error() -> None:
    """F7 audit finding 7 through compute_finance: no line on any operating day."""
    g = golden_inputs()
    (s2, t2) = sized("S2")
    empty = g.daily.with_columns(lines=g.daily["lines"] * 0)
    with pytest.raises(DataQualityError, match="annual lines"):
        compute_finance(s2, g.basis, g.catalog, None, daily=empty, tracer=copy.deepcopy(t2))


# ---------------------------------------------------------------- ranges
def test_ranges_are_ordered_and_the_pessimistic_world_costs_more() -> None:
    for sid, run in finance_all().items():
        fin = run.fin
        ranges = [*fin.capex.values(), fin.capex_total, fin.opex_year1, fin.tco, fin.cost_per_line]
        ranges += [fin.npv_vs_baseline] if fin.npv_vs_baseline else []
        assert all(r.lo <= r.typ <= r.hi for r in ranges), sid
        for key in ("capex.total", "opex.y1.total", "finance.tco", "finance.cost_per_line"):
            lo, typ, hi = (node(run.tracer, sid, key, w) for w in WORLDS)
            assert lo > typ > hi, (sid, key)  # pessimistic dearer than typ dearer than optimistic
        assert fin.capex_total.lo == node(run.tracer, sid, "capex.total", "hi")
        assert fin.capex_total.hi == node(run.tracer, sid, "capex.total", "lo")
        assert fin.capex_total.lo < fin.capex_total.typ < fin.capex_total.hi


# ---------------------------------------------------------------- determinism and trace
def test_finance_json_and_trace_are_byte_identical_between_runs(tmp_path: Path) -> None:
    one, two = write_all(tmp_path / "a"), write_all(tmp_path / "b")
    assert one == two
    assert set(one) == {
        f"{s}/{f}" for s in ("S0", "S1", "S2") for f in ("finance.json", "trace.jsonl")
    }
    assert (tmp_path / "a" / "scenarios" / "S2" / "finance.json").read_text().endswith("}\n")


@pytest.mark.slow
def test_a_fresh_process_writes_the_same_bytes(tmp_path: Path) -> None:
    """Another hash seed: same finance.json and trace.jsonl (no set order leaks into either)."""
    script = "import sys; from tests.unit.test_f7_finance import write_all; write_all(sys.argv[1])"
    env = {**os.environ, "PYTHONHASHSEED": "4242"}
    subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "sub")], check=True, cwd=ROOT, env=env
    )
    here = write_all(tmp_path / "here")
    for name, data in here.items():
        sid, file = name.split("/")
        assert (tmp_path / "sub" / "scenarios" / sid / file).read_bytes() == data, name


def trace_pairs(fin: FinancialResult) -> Iterator[tuple[float | Range, str]]:
    """(number or Range of finance.json, trace key `<sid>.<key>`): the mapping F7 documents."""
    for item, rng in fin.capex.items():
        yield rng, f"capex.{item}"
    yield fin.capex_total, "capex.total"
    for t, row in enumerate(fin.opex_by_year, 1):
        for item, value in row.items():
            yield value, f"opex.y{t}.{item}"
    yield fin.opex_year1, "opex.y1.total"
    yield fin.tco, "finance.tco"
    yield fin.cost_per_line, "finance.cost_per_line"
    for rng, key in ((fin.npv_vs_baseline, "npv"),):
        if rng is not None:
            yield rng, f"finance.{key}"
    if fin.irr_vs_baseline is not None:
        yield fin.irr_vs_baseline, "finance.irr"
    if fin.payback_years is not None:
        yield fin.payback_years, "finance.payback_years"
    for t, x in enumerate(fin.cash_flows_typ):
        yield x, f"finance.cash_flow.y{t}"
    for t, x in enumerate(fin.delta_cash_flows_typ):
        yield x, f"finance.delta_cf.y{t}"


def count_numbers(tree: Any) -> int:
    if isinstance(tree, bool):
        return 0
    if isinstance(tree, int | float):
        return 1
    if isinstance(tree, dict):
        return sum(count_numbers(v) for v in tree.values())  # pyright: ignore[reportUnknownVariableType]
    if isinstance(tree, list):
        return sum(count_numbers(v) for v in tree)  # pyright: ignore[reportUnknownVariableType]
    return 0


def check_traced(sid: str, run: Run) -> int:
    """Assert every number of `run.fin` has its node (typ = value, lo / hi = min / max over the
    worlds); returns how many numbers were checked."""
    checked = 0
    for value, key in trace_pairs(run.fin):
        if isinstance(value, Range):
            vals = [node(run.tracer, sid, key, w) for w in WORLDS]
            assert (value.lo, value.typ, value.hi) == (min(vals), vals[1], max(vals)), key
            checked += 3
        else:
            assert value == node(run.tracer, sid, key), key
            checked += 1
    return checked


def test_every_number_of_finance_json_has_a_trace_node() -> None:
    for sid, run in finance_all().items():
        n = check_traced(sid, run)
        assert n == count_numbers(run.fin.model_dump(mode="json")), sid  # no number left out
        assert n > 60


def test_finance_nodes_name_their_inputs() -> None:
    """Every `inputs` ref of a finance node is a catalog `param:` id, a `data:` leaf, or the id
    of a node of the same world (another scenario's results are `data:<id>.…` leaves)."""
    g = golden_inputs()
    known = set(g.catalog.params) | set(g.catalog.constants)
    for sid, run in finance_all().items():
        ids = {(n.id, n.world) for n in run.tracer.nodes}
        mine = [n for n in run.tracer.nodes if n.id.split(".", 1)[1].split(".")[0] in
                ("capex", "opex", "finance")]  # fmt: skip
        assert len(mine) > 150  # 65 nodes in each of the three worlds
        for n in mine:
            assert n.scope == sid and n.formula and n.label
            for ref in n.inputs.values():
                if ref.startswith("param:"):
                    assert ref.removeprefix("param:") in known, (n.id, ref)
                elif not ref.startswith("data:"):
                    assert (ref, n.world) in ids, (n.id, ref)
