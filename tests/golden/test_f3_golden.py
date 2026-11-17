"""T3.1: build_profile on tiny_golden equals the golden spreadsheet (golden_values.json)."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import polars as pl
import pytest
from tests.golden import build_golden
from tests.golden.test_g1_sync import _data, _read, _shipped

from whsizing.config import load_yaml_model
from whsizing.profile import ProfileTables, build_tables, profile_from_tables
from whsizing.profile.calendar import operating_threshold
from whsizing.profile.intraday import design_weekday
from whsizing.schemas import DemandProfile, DesignBasis, ProfileCfg

HERE = Path(__file__).parent
TOL = 0.005  # T1.5: 0.5 %
STATS = ("mean", "p50", "p90", "p95", "p98", "max", "cv")
METRICS = ("orders", "lines", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
EIQ = ("lines_per_order", "units_per_line", "units_per_order")
EIQ_F = ("cube_per_order_m3", "weight_per_order_kg")


def _profile(data_dir: Path) -> tuple[DemandProfile, ProfileTables]:
    basis = load_yaml_model(HERE / "golden_basis.yaml", DesignBasis)
    cfg = ProfileCfg()
    t = build_tables(data_dir, basis, cfg)
    return profile_from_tables(t, cfg), t


@pytest.fixture(scope="module")
def built() -> tuple[DemandProfile, ProfileTables]:
    return _profile(HERE / "tiny_golden")


def engine_values(p: DemandProfile, t: ProfileTables) -> dict[str, Any]:
    """Engine value for every golden key F3 produces (golden key → engine value)."""
    d = t.daily
    wd = design_weekday(d)
    out: dict[str, Any] = {
        "profile.period_start": str(p.period_start),
        "profile.period_end": str(p.period_end),
        "profile.calendar_days": d.height,
        "profile.operating_threshold": operating_threshold(d["lines"].to_numpy(), 0.10),
        "profile.operating_days": p.operating_days,
        "profile.n_orders": int(d["orders"].sum()),
        "profile.n_lines": int(d["lines"].sum()),
        "profile.n_units": int(d["units"].sum()),
        "profile.n_return_lines": int(d["return_lines"].sum()),
        "eiq.single_line_share": p.eiq.single_line_share,
        "seasonality.peak_to_average": p.seasonality.peak_to_average,
        "design_day.design_weekday": wd,
        "design_day.peak_hour_share": p.peak_hour_share,
    }
    for i, v in enumerate(p.seasonality.weekday_index):
        if v:
            out[f"profile.weekday_mean_lines.{i}"] = v * p.daily["lines"].mean
    for m in METRICS:
        out |= {f"daily.{m}.{k}": getattr(p.daily[m], k) for k in STATS}
    for name in (*EIQ, *EIQ_F):
        out |= {f"eiq.{name}.{k}": getattr(getattr(p.eiq, name), k) for k in STATS}
    out |= {f"eiq.order_class_share.{c}": v for c, v in p.eiq.order_class_shares.items()}
    for c, s in p.abc.by_lines.items():
        out |= {f"abc.lines.{c}.{k}": getattr(s, k) for k in ("n_skus", "sku_share", "line_share")}
    stock = ("n_skus_in_stock", "avg_units", "avg_cube_m3", "cover_days")
    for k in (*stock, "dead_stock_skus", "dead_stock_cube_m3"):
        out[f"stock.{k}"] = getattr(p.stock, k)
    for k in ("trend_cagr", "trend_confidence"):
        out[f"seasonality.{k}"] = getattr(p.seasonality, k)
    for k in type(p.shipment_split).model_fields:
        out[f"shipment.{k}"] = getattr(p.shipment_split, k)
    for h, s in enumerate(p.intraday[wd]):
        out[f"design_day.intraday_share.h{h:02d}"] = s
    return out


def same(engine: Any, golden: Any) -> bool:
    if golden is None or engine is None:
        return engine is golden  # undefined values (trend_cagr with < 2 months)
    if isinstance(golden, str) or (isinstance(golden, int) and not isinstance(golden, bool)):
        return engine == golden  # dates, counts: exact
    if golden == 0:
        return abs(engine) < 1e-12
    return math.isclose(engine, golden, rel_tol=TOL)


def test_T3_1_profile_stats_equal_golden_spreadsheet(
    built: tuple[DemandProfile, ProfileTables],
) -> None:
    golden = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    engine = engine_values(*built)
    missing = sorted(set(engine) - set(golden))
    assert not missing, f"engine keys absent from golden_values.json: {missing}"
    bad = {k: (v, golden[k]) for k, v in engine.items() if not same(v, golden[k])}
    assert not bad, f"{len(bad)} of {len(engine)} keys differ (engine, golden): {bad}"
    # every golden key of the F3 namespaces is compared
    f3 = ("profile.", "daily.", "eiq.", "abc.", "stock.", "shipment.", "seasonality.")
    uncovered = sorted(k for k in golden if k.startswith(f3) and k not in engine)
    assert not uncovered, f"golden F3 keys not compared: {uncovered}"


def test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock(tmp_path: Path) -> None:
    """The golden case has no dead stock (0 SKUs, 0.0 m3). On a copy with a SKU last shipped
    exactly 180 d before period_end, one shipped 179 d before (not dead) and an inventory-only
    orphan, every F3 key of the engine equals the oracle (I50)."""
    inv, lines, sku = _read("inventory"), _read("order_lines"), _read("sku_master")
    edge, inside = sorted(set(sku["sku"]) - set(lines["sku"]))[:2]  # never ordered
    end = cast(date, inv["snapshot_date"].max())  # = period_end on tiny_golden
    extra = pl.DataFrame({"sku": [edge, inside, "INV-ONLY"], "qty_units": [300, 300, 500]})
    inv = pl.concat([inv, extra.with_columns(snapshot_date=end)])
    new = [_shipped(lines, s, end - timedelta(days=d)) for s, d in ((edge, 180), (inside, 179))]
    data = _data(tmp_path, inventory=inv, order_lines=pl.concat([lines, *new]))
    golden = build_golden.run(data_dir=data)[0].values()
    engine = engine_values(*_profile(data))
    assert golden["stock.dead_stock_skus"] == engine["stock.dead_stock_skus"] == 2
    assert golden["stock.dead_stock_cube_m3"] > 0
    bad = {k: (v, golden[k]) for k, v in engine.items() if not same(v, golden[k])}
    assert not bad, f"{len(bad)} of {len(engine)} keys differ (engine, oracle): {bad}"


def test_T3_1_trend_equals_the_oracle_on_a_two_month_copy(tmp_path: Path) -> None:
    """The golden trend is degenerate (one calendar month: None, L). Orders with a local date up
    to 2025-03-15 moved back 28 days span February and March: trend_cagr is defined and every
    F3 key of the engine equals the oracle (I52)."""
    lines = _read("order_lines")
    local = pl.col("order_ts").dt.convert_time_zone("Europe/Paris").dt.date()
    early = pl.col("order_ts") - timedelta(days=28)
    lines = lines.with_columns(
        order_ts=pl.when(local <= date(2025, 3, 15)).then(early).otherwise("order_ts")
    )
    data = _data(tmp_path, order_lines=lines)
    golden = build_golden.run(data_dir=data)[0].values()
    engine = engine_values(*_profile(data))
    assert isinstance(golden["seasonality.trend_cagr"], float)
    assert golden["seasonality.trend_confidence"] == "L"
    bad = {k: (v, golden[k]) for k, v in engine.items() if not same(v, golden[k])}
    assert not bad, f"{len(bad)} of {len(engine)} keys differ (engine, oracle): {bad}"
