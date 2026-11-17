"""F6 inputs (I58 sku frame, design stock, eligibility, zones); T6.5, T6.7, T6.8 are in
test_f6_throughput_properties.py.

`toy_sku` / `build` are the toy-case builders of every F6a/F6b unit test (catalog typ values)."""

from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from tests.fixtures import mock_basis, mock_design_day

from whsizing.catalog import load_catalog
from whsizing.engine import (
    WorldInputs,
    size_storage,
    size_throughput,
    sku_frame,
    to_range,
    world_inputs,
)
from whsizing.errors import WhsizingError
from whsizing.profile import ProfileTables
from whsizing.schemas import EligibilityCfg, FamilyId, Range, ScenarioDef, World
from whsizing.schemas.trace import Tracer

ROOT = Path(__file__).parents[2]
CATALOG = load_catalog(ROOT / "catalog")
BIG = (800.0, 600.0, 500.0)  # fits neither a shelf bin nor the cube / AMR envelope
SMALL = (100.0, 100.0, 100.0)  # unit cube 0.001 m³


def toy_sku(*rows: dict[str, Any]) -> pl.DataFrame:
    """SKU frame in the I58 shape. Row keys: sku, dims (l, w, h or None), weight, avg_stock,
    lines, units, abc, upp, upc, cpp, hazmat."""
    out = []
    for r in rows:
        dims = r.get("dims", SMALL)
        cube = None if dims is None else dims[0] * dims[1] * dims[2] / 1e9
        avg = float(r.get("avg_stock", 0.0))
        out.append(
            {
                "sku": r["sku"],
                "length_mm": None if dims is None else dims[0],
                "width_mm": None if dims is None else dims[1],
                "height_mm": None if dims is None else dims[2],
                "weight_kg": r.get("weight", 1.0),
                "unit_cube_m3": cube,
                "has_dims": dims is not None,
                "orphan": False,
                "lines": r.get("lines", 0),
                "units": r.get("units", 0),
                "avg_stock": avg,
                "stock_cube_m3": avg * (cube or 0.0),
                "abc": r.get("abc", "C"),
                "units_per_pallet": r.get("upp"),
                "units_per_case": r.get("upc"),
                "cases_per_pallet": r.get("cpp"),
                "hazmat": r.get("hazmat"),
                "temperature_class": None,
            }
        )
    schema = {
        "length_mm": pl.Float64,
        "width_mm": pl.Float64,
        "height_mm": pl.Float64,
        "weight_kg": pl.Float64,
        "unit_cube_m3": pl.Float64,
        "units_per_pallet": pl.Float64,
        "units_per_case": pl.Float64,
        "cases_per_pallet": pl.Float64,
        "hazmat": pl.Boolean,
        "temperature_class": pl.Utf8,
    }
    return pl.DataFrame(out, schema_overrides=schema)


def build(
    sku: pl.DataFrame,
    family: FamilyId = "manual_p2p",
    world: World = "typ",
    *,
    tracer: Tracer | None = None,
    clear_height: float = 8.5,
    same_day_share: float = 0.6,
    eligibility: EligibilityCfg | None = None,
    dd: dict[str, Any] | None = None,
) -> WorldInputs:
    """Toy inputs. Design stock = avg_stock (stock_units = Σ avg_stock); design day: 1000 lines,
    peak hour 150 lines, 2000 units, 10 pallets out; inbound 2000 units, 20 pallets, peak factor
    1.5; SLA window 15:00 → 18:30 = 3.5 h."""
    base = mock_basis()
    basis = base.model_copy(
        update={
            "overrides": {},
            "building": base.building.model_copy(update={"clear_height_m": clear_height}),
            "service": base.service.model_copy(
                update={
                    "cutoff_time": time(15, 0),
                    "carrier_departure_time": time(18, 30),
                    "same_day_share": same_day_share,
                }
            ),
        }
    )
    d0 = mock_design_day()
    inbound = d0.inbound.model_copy(
        update={"units_per_day": 2000.0, "pallets_per_day": 20.0, "peak_factor": 1.5}
    )
    design = d0.model_copy(
        update={
            "lines": 1000.0,
            "peak_hour_lines": 150.0,
            "units": 2000.0,
            "pallets_out": 10.0,
            # summed in sku order like the engine: a permuted frame (T6.8) gets the same bits
            "stock_units": float(sku.sort("sku")["avg_stock"].sum()),
            "inbound": inbound,
            **(dd or {}),
        }
    )
    scenario = ScenarioDef(
        id="S9", name="toy", family=family, eligibility=eligibility or EligibilityCfg()
    )
    return world_inputs(basis, design, scenario, CATALOG, sku, world, tracer or Tracer("S9", world))


# --- I58 sku_frame ---------------------------------------------------------------------------


def _tables(skus: pl.DataFrame) -> ProfileTables:
    empty = pl.DataFrame()
    return ProfileTables(empty, empty, skus, empty, empty, "hash")


def test_sku_frame_joins_pack_hazmat_and_temperature() -> None:
    """I58: F3 skus + master pack columns + hazmat (null when unset), temperature_class null
    when the master lacks it; sorted by sku."""
    skus = pl.DataFrame({"sku": ["b", "a"], "units": [5, 7], "lines": [1, 2]})
    master = pl.DataFrame(
        {
            "sku": ["a", "b"],
            "units_per_pallet": [100, None],
            "units_per_case": [10, 4],
            "cases_per_pallet": [10, 8],
            "hazmat": [True, None],
            "category": ["x", "y"],
        }
    )
    out = sku_frame(_tables(skus), master)
    assert out["sku"].to_list() == ["a", "b"]
    assert out["units_per_pallet"].to_list() == [100, None]
    assert out["units_per_case"].to_list() == [10, 4]
    assert out["hazmat"].to_list() == [True, None]
    assert out["temperature_class"].to_list() == [None, None]
    assert "category" not in out.columns


def test_sku_frame_without_master_has_null_columns() -> None:
    out = sku_frame(_tables(pl.DataFrame({"sku": ["a"], "units": [1]})), None)
    for col in ("units_per_pallet", "units_per_case", "cases_per_pallet", "hazmat"):
        assert out[col].to_list() == [None]
    assert out["temperature_class"].dtype == pl.Utf8


def test_world_inputs_rejects_frame_without_required_columns() -> None:
    with pytest.raises(WhsizingError, match="abc"):
        build(toy_sku({"sku": "a"}).drop("abc"))


# --- design stock, eligibility, zones -----------------------------------------------------------


def test_design_stock_is_allocated_in_proportion_to_average_stock() -> None:
    """s_i = avg_stock_i × stock_units* / Σ avg_stock: 300 × 10/30 = 100, 300 × 20/30 = 200."""
    sku = toy_sku({"sku": "a", "avg_stock": 10}, {"sku": "b", "avg_stock": 20})
    inp = build(sku, dd={"stock_units": 300.0})
    assert inp.sku["design_stock"].to_list() == pytest.approx([100.0, 200.0])
    assert inp.sku["design_stock_cube_m3"].to_list() == pytest.approx([0.1, 0.2])
    zero = build(toy_sku({"sku": "a"}), dd={"stock_units": 0.0})
    assert zero.sku["design_stock"].to_list() == [0.0]


def test_manual_family_takes_every_sku() -> None:
    """I17: S0 has share_lines_eligible = 1, also for SKUs without dims; zone main."""
    sku = toy_sku({"sku": "a", "lines": 3}, {"sku": "b", "dims": None, "lines": 1})
    inp = build(sku)
    assert inp.eligibility.share_lines == 1.0
    assert inp.sku["eligible"].to_list() == [True, True]
    assert set(inp.sku["zone"]) == {"main"}
    assert inp.tracer.get("S9.eligibility.share_lines").value == 1.0


def test_cube_uses_the_scenario_eligibility_and_routes_the_rest_to_overflow() -> None:
    """I44: extra_max_weight_kg 2.0 → the 3 kg SKU goes to the manual overflow; hazmat
    excluded (I10)."""
    sku = toy_sku(
        {"sku": "a", "lines": 6, "avg_stock": 1},
        {"sku": "b", "weight": 3.0, "lines": 3, "avg_stock": 1},
        {"sku": "c", "hazmat": True, "lines": 1, "avg_stock": 1},
    )
    inp = build(sku, "cube_asrs", eligibility=EligibilityCfg(extra_max_weight_kg=2.0))
    assert inp.sku["eligible"].to_list() == [True, False, False]
    assert inp.sku["storage_class"].to_list() == ["cube_bin", "shelving", "shelving"]
    assert inp.sku["zone"].to_list() == ["main", "overflow", "overflow"]
    assert inp.eligibility.share_lines == pytest.approx(0.6)
    assert inp.tracer.get("S9.eligibility.n_skus_eligible").value == 1


def test_zero_eligible_lines_degenerates_to_manual() -> None:
    """I48: eligible SKUs without lines → share_lines 0, every SKU in its manual class,
    λ_e = 0, ports = robots = 0, the cube_bin class has 0 bins; F_ELIG_LOW kept."""
    sku = toy_sku(
        {"sku": "a", "avg_stock": 50, "lines": 0, "units": 0},
        {"sku": "b", "dims": BIG, "avg_stock": 50, "lines": 10, "units": 10, "upp": 10},
    )
    inp = build(sku, "cube_asrs")
    assert inp.eligibility.share_lines == 0.0
    assert inp.sku["storage_class"].to_list() == ["shelving", "pallet_rack"]
    st = size_storage(inp)
    tp = size_throughput(inp, st)
    assert st.get("cube_bin").positions == 0.0
    assert st.get("cube_bin").n_skus == 0
    assert tp.lam_e == 0.0
    assert tp.equipment["ports"] == 0
    assert tp.equipment["robots"] == 0
    assert "F_ELIG_LOW" in {f.code for f in inp.eligibility.flags}


def test_to_range_orders_worlds_by_value() -> None:
    """ADR-002: lo = min, typ = typical world, hi = max (a pessimistic world may be higher)."""
    assert to_range({"lo": 5.0, "typ": 3.0, "hi": 1.0}, "m2") == Range(
        lo=1.0, typ=3.0, hi=5.0, unit="m2"
    )
