"""T4.1: F3 + F4 on tiny_golden equal the golden spreadsheet (golden_values.json) within 0.5 %."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from whsizing.catalog import load_catalog
from whsizing.design import load_basis, select_design_day, with_pack_data
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import DemandProfile, DesignBasis, DesignDay, ProfileCfg

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TOL = 0.005  # T1.5: 0.5 %
METRICS = ("orders", "lines", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
INBOUND = ("units", "pallets", "receipt_lines", "trucks", "cases")
STOCK = (
    "n_skus_in_stock",
    "avg_units",
    "avg_cube_m3",
    "cover_days",
    "dead_stock_skus",
    "dead_stock_cube_m3",
)


@pytest.fixture(scope="module")
def run() -> tuple[DesignDay, DemandProfile, DesignBasis]:
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = with_pack_data(t.skus, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    return select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog), profile, basis


def engine_values(dd: DesignDay, p: DemandProfile, basis: DesignBasis) -> dict[str, Any]:
    """Engine value for every golden design_day.* / inbound.* / stock.* key. Keys that are not
    DesignDay fields are recomputed from it: ratio = m* / lines*, base = m* / (1 + g)^T,
    orders_S / orders_ML = orders* × share of 1-line orders (I15), return_lines (I9)."""
    gf = (1 + dd.growth_rate) ** dd.horizon_years
    share_s = p.eiq.single_line_share
    out: dict[str, Any] = {
        "design_day.growth_factor": gf,
        "design_day.reference_date": str(dd.reference_date),
        "design_day.design_weekday": dd.design_weekday,
        "design_day.flags": ",".join(f.code for f in dd.flags),
        "design_day.peak_hour_lines": dd.peak_hour_lines,
        "design_day.peak_hour_share": dd.peak_hour_lines / dd.lines,
        "design_day.stock_units": dd.stock_units,
        "design_day.stock_cube_m3": dd.stock_cube_m3,
        "design_day.orders_S": dd.orders * share_s,
        "design_day.orders_ML": dd.orders * (1 - share_s),
        "design_day.return_lines": basis.flows.returns_rate * dd.lines,
        "inbound.peak_factor": dd.inbound.peak_factor,
    }
    for m in METRICS:
        value = getattr(dd, m)
        out[f"design_day.{m}"] = value
        out[f"design_day.p.{m}"] = dd.percentile_values[m]
        out[f"design_day.ratio.{m}"] = value / dd.lines
        out[f"design_day.base.{m}"] = value / gf
    for h, v in enumerate(dd.hourly_lines):
        out[f"design_day.hourly_lines.h{h:02d}"] = v
        out[f"design_day.intraday_share.h{h:02d}"] = v / dd.lines
    for k in INBOUND:
        out[f"inbound.{k}_per_day"] = getattr(dd.inbound, f"{k}_per_day")
    for k in STOCK:
        out[f"stock.{k}"] = getattr(p.stock, k)
    return out


def same(engine: Any, golden: Any) -> bool:
    if isinstance(golden, str) or (isinstance(golden, int) and not isinstance(golden, bool)):
        return engine == golden  # dates, flags, counts: exact
    if golden == 0:
        return abs(engine) < 1e-12
    return math.isclose(engine, golden, rel_tol=TOL)


def test_T4_1_design_day_and_inbound_equal_golden_spreadsheet(
    run: tuple[DesignDay, DemandProfile, DesignBasis],
) -> None:
    golden = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    engine = engine_values(*run)
    missing = sorted(set(engine) - set(golden))
    assert not missing, f"engine keys absent from golden_values.json: {missing}"
    bad = {k: (v, golden[k]) for k, v in engine.items() if not same(v, golden[k])}
    assert not bad, f"{len(bad)} of {len(engine)} keys differ (engine, golden): {bad}"
    f4 = ("design_day.", "inbound.", "stock.")
    uncovered = sorted(k for k in golden if k.startswith(f4) and k not in engine)
    assert not uncovered, f"golden F4 keys not compared: {uncovered}"
