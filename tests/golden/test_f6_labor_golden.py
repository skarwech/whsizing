"""T6.2 (labor) and T6.10 on the golden case: the engine on tiny_golden equals the golden
spreadsheet (golden_values.json) within 0.5 % for every `S0.labor.*` and `S2.labor.*` key.

Built end to end like T6.1 (test_f6_storage_golden.py): F3 build_tables → profile_from_tables,
I58 sku_frame, F4 select_design_day, then per scenario and world world_inputs → size_storage →
size_throughput → labor_days (daily series + shipped lines) → size_labor. Values are read back
from the typ-world trace by their golden key (trace id)."""

from __future__ import annotations

import json
import re
from typing import Any

import polars as pl
import pytest
from tests.golden.test_f6_storage_golden import HERE, ROOT, same

from whsizing.catalog import Catalog, load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import WORLDS, size_storage, size_throughput, sku_frame, world_inputs
from whsizing.engine.labor import LaborWorld, labor_days, labor_result, size_labor
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import LaborResult, ProfileCfg, ScenarioSet
from whsizing.schemas.trace import Tracer

KEYS = re.compile(r"^(S0|S2)\.labor\.")


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    values = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    return {k: v for k, v in values.items() if KEYS.match(k)}


def bad_data_refs(tracer: Tracer, roots: dict[str, Any]) -> list[tuple[str, str]]:
    """(node, leaf) of every `data:` leaf of a labor node that names no real datum: a frame
    root (daily, lines, sku) needs exactly one existing column, an object root an attribute
    or key path; any other root is unknown."""
    bad: list[tuple[str, str]] = []
    for n in tracer.nodes:
        for ref in n.inputs.values():
            if ".labor." not in n.id or not ref.startswith("data:"):
                continue
            root, *path = ref.removeprefix("data:").split(".")
            obj = roots.get(root)
            if isinstance(obj, pl.DataFrame):
                ok = len(path) == 1 and path[0] in obj.columns
            else:
                ok = obj is not None
                for p in path:
                    obj = obj.get(p) if isinstance(obj, dict) else getattr(obj, p, None)
                    ok = ok and obj is not None
            if not ok:
                bad.append((n.id, ref))
    return bad


@pytest.fixture(scope="module")
def run() -> tuple[dict[str, Any], list[Tracer], Catalog, dict[str, LaborResult], dict[str, Any]]:
    """Trace values of the typ world (S0, S2), the tracers, the catalog, the LaborResults and
    the data roots of the trace leaves."""
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    design_day = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    scenarios = load_yaml_model(HERE / "golden_scenarios.yaml", ScenarioSet).scenarios
    out: dict[str, Any] = {}
    tracers: list[Tracer] = []
    results: dict[str, LaborResult] = {}
    for scenario in scenarios:
        tracer = Tracer(scenario.id)
        worlds: dict[str, LaborWorld] = {}
        for w in WORLDS:
            inp = world_inputs(basis, design_day, scenario, catalog, sku, w, tracer)
            tp = size_throughput(inp, size_storage(inp))
            worlds[w] = size_labor(inp, tp, labor_days(inp, t.daily, t.lines))
        out |= {n.id: n.value for n in tracer.nodes if n.world == "typ"}
        tracers.append(tracer)
        results[scenario.id] = labor_result(worlds)  # pyright: ignore[reportArgumentType]
    roots = {"daily": t.daily, "lines": t.lines, "sku": inp.sku,  # pyright: ignore[reportPossiblyUnbound]
             "design_day": design_day, "basis": basis, "catalog": catalog}  # fmt: skip
    return out, tracers, catalog, results, roots


@pytest.fixture(scope="module")
def engine(run: tuple[Any, ...]) -> dict[str, Any]:
    return run[0]


def test_T6_2_labor_hours_heads_equal_golden(
    golden: dict[str, Any], engine: dict[str, Any]
) -> None:
    """Every golden key under S0.labor. / S2.labor. (workload, hours, heads, roster, annual
    hours per activity and zone; totals, annual hours, core FTE, P50 day, core heads, temp
    hours) has a trace node of that id with the golden value (0.5 %)."""
    assert len(golden) == 257  # S0 123 + S2 134 (decant, cube_bin zone)
    missing = sorted(k for k in golden if k not in engine)
    assert not missing, f"no trace node for {missing}"
    bad = {k: (engine[k], v) for k, v in golden.items() if not same(engine[k], v)}
    assert not bad, f"engine vs golden: {bad}"


def test_T6_2_labor_result_typ_matches_trace(run: tuple[Any, ...], golden: dict[str, Any]) -> None:
    """LaborResult.typ equals the golden values; lo ≤ typ ≤ hi; roles from labor_standards
    (I33); one shift of 06:00-13:30 holding every activity."""
    results = run[3]
    for sid, res in results.items():
        assert same(res.total_hours.typ, golden[f"{sid}.labor.total.hours"])
        assert same(res.roster.typ, golden[f"{sid}.labor.total.roster"])
        assert same(res.core_fte[2].typ, golden[f"{sid}.labor.core_fte.y3"])
        assert same(res.temp_hours[4].typ, golden[f"{sid}.labor.temp_hours.y5"])
        assert len(res.annual_hours) == 5
        # lo world: every productivity at its min → more hours
        assert res.total_hours.lo < res.total_hours.typ < res.total_hours.hi
        for a in res.activities:
            assert same(a.hours.typ, golden[f"{sid}.labor.{a.activity}.hours"])
        assert {s.shift for s in res.shifts} == {1}
        assert (res.shifts[0].start_hour, res.shifts[0].end_hour) == (6.0, 13.5)
    roles = {a.activity: a.role for a in results["S2"].activities}
    assert roles == {
        "receiving": "forklift_driver",
        "receipt_check": "operator",
        "put_away": "forklift_driver",
        "decant": "operator",
        "replenishment": "forklift_driver",
        "picking": "operator",
        "packing_S": "operator",
        "packing_ML": "operator",
        "shipping_parcel": "operator",
        "shipping_pallet": "forklift_driver",
        "returns": "operator",
        "indirect": "team_leader",
    }
    assert "decant" not in {a.activity for a in results["S0"].activities}


def test_T6_10_annual_hours_below_design_day_times_operating_days(
    engine: dict[str, Any],
) -> None:
    """Annual hours from the daily series (mean day × (1+g)^t) stay below the design day
    (P95 × gf) × 252 days for every year: guards the peak-×-365 mistake."""
    for sid in ("S0", "S2"):
        peak_year = engine[f"{sid}.labor.total.hours"] * 252
        for t in range(1, 6):
            annual = engine[f"{sid}.labor.annual_hours.y{t}"]
            assert 0 < annual < peak_year, (sid, t, annual, peak_year)
        # the daily series mean is well below the design day
        assert engine[f"{sid}.labor.annual_hours.y1"] < 0.7 * peak_year


def test_T6_2_labor_trace_inputs_resolve(run: tuple[Any, ...]) -> None:
    """F6f / IC2: every input of every labor node is a catalog id, a node of the same tracer
    and world, or a `data:` leaf naming a real datum (a column of the F3 daily series or
    shipped lines, of the SKU frame, or a design-day / basis / catalog field). The returns
    workload is returns_rate × lines (I9), never the observed return_lines; derived daily
    inbound is the design value / gf (I22)."""
    _, tracers, catalog, _, roots = run
    known = set(catalog.params) | set(catalog.constants)
    for tracer in tracers:
        ids = {(n.id, n.world) for n in tracer.nodes}
        for n in tracer.nodes:
            if ".labor." not in n.id:
                continue
            for ref in n.inputs.values():
                if ref.startswith("param:"):
                    assert ref.removeprefix("param:") in known, (n.id, ref)
                elif not ref.startswith("data:"):
                    assert (ref, n.world) in ids, (n.id, ref)
        assert not bad_data_refs(tracer, roots)
        sid = tracer.scope
        returns = set(tracer.get(f"{sid}.labor.returns.base_hours").inputs.values())
        assert {"data:daily.lines", "data:basis.flows.returns_rate"} <= returns
        assert "data:daily.return_lines" not in returns
        if sid == "S2":  # derived decant: design units in / gf × cases per unit, no receipts
            decant = set(tracer.get("S2.labor.decant.base_hours").inputs.values())
            assert "data:daily.receipts_units" not in decant
            assert {"data:design_day.inbound.units_per_day", "data:sku.units_per_case"} <= decant
        receiving = set(tracer.get(f"{sid}.labor.receiving.base_hours").inputs.values())
        assert {"data:design_day.inbound.pallets_per_day", "data:design_day.growth_rate",
                "data:design_day.horizon_years"} <= receiving  # fmt: skip
