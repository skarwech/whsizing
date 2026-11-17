"""G1c: golden oracle synced with the F3 decisions (I49-I52), catalog 0.2.0 (I30, I46, I47) and
the zero-stock-cube guard of the eligibility shares (I10). Every test is part of T1.5."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
import yaml
from tests.golden import build_golden, demand, oracle

HERE = Path(__file__).resolve().parent
DATA = HERE / "tiny_golden"
CATALOG = HERE.parents[1] / "catalog"
TZ = "Europe/Paris"


def _golden() -> dict[str, Any]:
    return json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))


def _data(tmp: Path, **frames: pl.DataFrame) -> Path:
    """A copy of tiny_golden with some canonical frames replaced."""
    for name in ("order_lines", "sku_master", "inventory"):
        if name in frames:
            frames[name].write_parquet(tmp / f"{name}.parquet")
        else:
            shutil.copy(DATA / f"{name}.parquet", tmp / f"{name}.parquet")
    return tmp


def _read(name: str) -> pl.DataFrame:
    return pl.read_parquet(DATA / f"{name}.parquet")


@pytest.fixture(scope="module")
def golden_run() -> tuple[dict[str, Any], dict[str, Any]]:
    out, c = build_golden.run()
    return out.values(), c


# --- F3 decisions --------------------------------------------------------------------------------
def test_T1_5_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero(
    tmp_path: Path, golden_run: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    """I49: avg stock = Σ units over all snapshots / number of snapshots."""
    g0, c0 = golden_run
    inv = _read("inventory")
    absent = inv.sort("qty_units", descending=True)["sku"][0]  # the largest stock
    q = int(inv.filter(pl.col("sku") == absent)["qty_units"][0])
    older = inv.filter(pl.col("sku") != absent).with_columns(snapshot_date=date(2025, 2, 28))
    out, c = build_golden.run(data_dir=_data(tmp_path, inventory=pl.concat([inv, older])))
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    assert rows[absent]["avg_stock"] == q / 2  # not q (the mean of the rows present)
    assert all(
        r["avg_stock"] == rows[r["sku"]]["avg_stock"] for r in c0["skus"] if r["sku"] != absent
    )
    assert g["stock.avg_units"] == pytest.approx(g0["stock.avg_units"] - q / 2)


def test_T1_5_inventory_only_skus_are_orphans_in_stock_and_dead_stock(tmp_path: Path) -> None:
    """I50: a SKU in stock, absent from the master and never shipped is an orphan: it counts in
    the stock statistics, the SKU count and dead stock, and is never eligible. Dead stock =
    stock > 0 and no shipped line in the last 180 days of the period."""
    g0 = _golden()
    inv, lines, sku = _read("inventory"), _read("order_lines"), _read("sku_master")
    idle = sorted(set(sku["sku"]) - set(lines["sku"]))[0]  # master SKU never ordered, no stock
    extra = pl.DataFrame({"sku": ["INV-ONLY", idle], "qty_units": [500, 300]})
    inv = pl.concat([inv, extra.with_columns(snapshot_date=date(2025, 3, 31))])
    old = _shipped(lines, idle, date(2024, 9, 12))  # 200 days before the end
    data = _data(tmp_path, inventory=inv, order_lines=pl.concat([lines, old]))
    out, c = build_golden.run(data_dir=data)
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    orphan = rows["INV-ONLY"]
    assert orphan["orphan"] and not orphan["has_dims"] and orphan["lines"] == 0
    assert not orphan["elig_cube"] and orphan["zone_S2"] == "pallet_rack" and orphan["abc"] == "C"
    assert orphan["dead_stock"]
    assert rows[idle]["lines"] == 1 and rows[idle]["dead_stock"]  # only shipped > 180 days ago
    assert not any(r["dead_stock"] for r in c["skus"] if r["sku"] not in ("INV-ONLY", idle))
    assert g["stock.dead_stock_skus"] == 2 and orphan["unit_cube_m3"] == 0
    assert g["stock.dead_stock_cube_m3"] == pytest.approx(300 * rows[idle]["unit_cube_m3"])
    assert g["stock.n_skus_in_stock"] == g0["stock.n_skus_in_stock"] + 2
    assert g["stock.avg_units"] == pytest.approx(g0["stock.avg_units"] + 800)
    assert g["eligibility.cube_asrs.n_skus_total"] == 101  # 100 master SKUs + 1 orphan
    assert g["eligibility.cube_asrs.share_skus"] == pytest.approx(91 / 101)
    assert g["abc.lines.C.sku_share"] == pytest.approx(g["abc.lines.C.n_skus"] / 101)
    assert g["S0.storage.pallet_rack.n_skus"] == _golden()["S0.storage.pallet_rack.n_skus"] + 2


def _shipped(lines: pl.DataFrame, sku: str, day: date) -> pl.DataFrame:
    """One shipped line of 1 unit of `sku`, ordered at 09:00 UTC on `day` (same local date)."""
    ts = pl.lit(datetime(day.year, day.month, day.day, 9)).dt.replace_time_zone("UTC")
    one = lines.filter(pl.col("line_status") == "shipped").head(1)
    return one.with_columns(
        sku=pl.lit(sku), order_id=pl.lit(f"X-{sku}"), qty_units=pl.lit(1, pl.Int64), order_ts=ts
    )


def test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window(tmp_path: Path) -> None:
    """I50: dead stock = stock in the LAST snapshot > 0 (not avg_stock > 0) and no shipped line
    with a local date after period_end − 180 d; a line on period_end − 180 d is outside."""
    inv, lines, sku = _read("inventory"), _read("order_lines"), _read("sku_master")
    gone, edge, inside = sorted(set(sku["sku"]) - set(lines["sku"]))[:3]  # never ordered
    end = date.fromisoformat(_golden()["profile.period_end"])
    last = inv["snapshot_date"].max()
    assert last == end
    older = pl.DataFrame({"sku": [gone], "qty_units": [300], "snapshot_date": [date(2025, 2, 28)]})
    newer = pl.DataFrame({"sku": [edge, inside], "qty_units": [300, 300], "snapshot_date": last})
    inv = pl.concat([inv, older, newer])
    edge_line = _shipped(lines, edge, end - timedelta(days=180))
    inside_line = _shipped(lines, inside, end - timedelta(days=179))
    data = _data(tmp_path, inventory=inv, order_lines=pl.concat([lines, edge_line, inside_line]))
    out, c = build_golden.run(data_dir=data)
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    assert g["profile.period_end"] == str(end)
    assert rows[gone]["avg_stock"] == 150 and rows[gone]["last_stock"] == 0
    assert not rows[gone]["dead_stock"]  # stocked on average, no longer in stock
    assert rows[edge]["lines"] == 1 and rows[edge]["dead_stock"]
    assert rows[inside]["lines"] == 1 and not rows[inside]["dead_stock"]
    assert [r["sku"] for r in c["skus"] if r["dead_stock"]] == [edge]
    cube = 300 * rows[edge]["unit_cube_m3"]  # last_stock × unit cube, not avg_stock
    assert cube > 0 and g["stock.dead_stock_cube_m3"] == pytest.approx(cube)
    assert g["stock.dead_stock_skus"] == 1


def _midnight(orders: pl.Series) -> pl.Expr:
    """order_ts moved to local 00:00:00 of the same local date for `orders`."""
    local = pl.col("order_ts").dt.convert_time_zone(TZ)
    utc = local.dt.truncate("1d").dt.convert_time_zone("UTC")
    return pl.when(pl.col("order_id").is_in(orders.implode())).then(utc).otherwise("order_ts")


def test_T1_5_lines_without_time_are_left_out_of_intraday_shares(
    tmp_path: Path, golden_run: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    """I51, < 20 % of lines without time: they leave the intraday shares and stay in the daily
    totals. Every order of the design weekday's peak hour is moved to local midnight."""
    g0, c0 = golden_run
    wd = g0["design_day.design_weekday"]
    days = c0["dd"]["op"].filter(pl.col("weekday") == wd)["date"].implode()
    on_wd = c0["lines"].filter(pl.col("date").is_in(days))
    counts = np.bincount(on_wd["hour"].to_numpy(), minlength=24)
    peak = int(np.argmax(counts))
    victims = on_wd.filter(pl.col("hour") == peak)["order_id"].unique()
    k = int(counts[peak])
    assert k / g0["profile.n_lines"] < 0.20 and counts[0] < k
    lines = _read("order_lines").with_columns(order_ts=_midnight(victims))
    out, c = build_golden.run(data_dir=_data(tmp_path, order_lines=lines))
    g = out.values()
    assert c["lines"].filter(pl.col("order_id").is_in(victims.implode()))["has_time"].not_().all()
    for key in ("profile.n_lines", "daily.lines.mean", "daily.lines.p95", "design_day.lines"):
        assert g[key] == g0[key], key  # still counted in the daily totals
    expected = counts / (counts.sum() - k)
    expected[peak] = 0.0
    shares = [g[f"design_day.intraday_share.h{h:02d}"] for h in range(24)]
    assert shares == pytest.approx(expected.tolist())  # h00 does not gain the moved lines
    assert c["dd"]["intraday_confidence"] == "H"


def test_T1_5_lines_without_time_above_20_percent_use_the_default_profile(
    tmp_path: Path, golden_run: tuple[dict[str, Any], dict[str, Any]]
) -> None:
    """I51, more than 20 % of lines without time: default profile (flat 08:00-17:00), flagged L."""
    g0, c0 = golden_run
    per_order = c0["lines"].group_by("order_id").len().sort("order_id")
    n = int(np.searchsorted(per_order["len"].cum_sum().to_numpy(), 0.2 * g0["profile.n_lines"]))
    victims = per_order["order_id"].head(n + 1)  # just above 20 % of the lines
    share = per_order["len"].head(n + 1).sum() / g0["profile.n_lines"]
    assert 0.20 < share < 0.21
    lines = _read("order_lines").with_columns(order_ts=_midnight(victims))
    out, c = build_golden.run(data_dir=_data(tmp_path, order_lines=lines))
    g = out.values()
    shares = [g[f"design_day.intraday_share.h{h:02d}"] for h in range(24)]
    assert shares == pytest.approx([0.0] * 8 + [1 / 9] * 9 + [0.0] * 7)
    assert g["design_day.peak_hour_share"] == pytest.approx(1 / 9)
    assert c["dd"]["intraday_confidence"] == "L"
    assert g["daily.lines.mean"] == g0["daily.lines.mean"]


def test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile() -> None:
    """I51: "more than 20 %" is strict. 1 line of 5 without time keeps the measured shares (H);
    1 more without time (2 of 6) switches to the default profile (L)."""
    monday = date(2025, 3, 3)
    hours = [0, 9, 10, 10, 11]
    lines = pl.DataFrame({"date": [monday] * 5, "hour": hours, "has_time": [h > 0 for h in hours]})
    op = pl.DataFrame({"date": [monday], "weekday": [0]})
    shares, conf = demand.intraday(lines, op, 0)
    expected = [0.0] * 24
    expected[9:12] = [0.25, 0.5, 0.25]
    assert conf == "H"
    assert shares == pytest.approx(expected)
    more = pl.concat([lines, lines.head(1)])
    assert demand.intraday(more, op, 0) == (oracle.DEFAULT_INTRADAY, "L")


def test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile() -> None:
    """I51: 16 % of lines without time overall, all of them on the design weekday (Monday, 16
    lines vs 14 on the other days) → that weekday takes the default profile, still H."""
    days = [date(2025, 3, 3) + timedelta(days=i) for i in range(7)]  # Monday first
    dates = [d for d, n in zip(days, [16] + [14] * 6, strict=True) for _ in range(n)]
    lines = pl.DataFrame({"date": dates}).with_columns(has_time=pl.col("date") != days[0])
    lines = lines.with_columns(hour=pl.when("has_time").then(10).otherwise(0))
    assert lines["has_time"].not_().mean() == pytest.approx(0.16)
    op = pl.DataFrame({"date": days, "weekday": list(range(7))})
    assert demand.intraday(lines, op, 0) == (oracle.DEFAULT_INTRADAY, "H")
    assert demand.intraday(lines, op, 1)[0][10] == 1.0  # Tuesday keeps its measured shares


def test_T1_5_trend_cagr_from_monthly_mean_daily_lines(
    golden_run: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """I52: CAGR = exp(12 × OLS slope of log(mean daily lines per month, operating days)) − 1,
    robust to partial boundary months; confidence by calendar months."""
    start, end = date(2023, 1, 15), date(2025, 1, 20)  # partial first and last months
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    month = [(d.year - 2023) * 12 + d.month - 1 for d in dates]
    sunday = [d.weekday() == 6 for d in dates]  # 0 lines, non-operating: left out of the means
    lines = [0.0 if s else 100 * 1.01**m for s, m in zip(sunday, month, strict=True)]
    daily = pl.DataFrame({"date": dates, "lines": lines, "is_operating": [not s for s in sunday]})
    cagr, conf = demand.trend(daily)
    assert cagr == pytest.approx(1.01**12 - 1, rel=1e-9)
    assert conf == "M"  # 24 calendar months + 6 days
    three_years = pl.date_range(date(2022, 1, 1), date(2024, 12, 31), eager=True)  # 1096 days
    flat = pl.DataFrame({"date": three_years, "lines": 100.0, "is_operating": True})
    assert demand.trend(flat) == (pytest.approx(0.0, abs=1e-12), "M")  # 36.0 months, not 36.01
    assert oracle.trend_cagr(np.array([5.0]), np.array([100.0])) is None
    assert golden_run[1]["trend"] == (None, "L")  # tiny_golden: one calendar month
    g = _golden()
    assert (g["seasonality.trend_cagr"], g["seasonality.trend_confidence"]) == (None, "L")
    spans = {  # (first, last date) → confidence; leap days do not shift the boundaries
        (date(2023, 1, 1), date(2024, 12, 28)): "L",  # 23 months + 28 days
        (date(2023, 1, 2), date(2024, 12, 31)): "L",  # 23 months + 30 days
        (date(2023, 1, 1), date(2024, 12, 31)): "M",  # 24.0 (731 days, 29 Feb 2024 inside)
        (date(2023, 3, 1), date(2025, 2, 28)): "M",  # 24.0
        (date(2022, 1, 1), date(2024, 12, 31)): "M",  # 36.0 (1096 days)
        (date(2022, 1, 1), date(2025, 1, 1)): "H",  # 36 months + 1 day
    }
    got = {k: oracle.trend_confidence(oracle.calendar_months(*k)) for k in spans}
    assert got == spans
    assert oracle.calendar_months(date(2022, 1, 1), date(2024, 12, 31)) == 36.0


# --- catalog 0.2.0 -------------------------------------------------------------------------------
def test_T1_5_cube_building_works_add_floor_prep_on_the_grid() -> None:
    """I30: S2 building works = area.total × 60 + floor_prep 20 × A_grid; S0 has no floor prep."""
    g = _golden()
    grid = g["S2.storage.cube_bin.grid_area_m2"]
    assert grid > 0
    assert g["S2.capex.building_works"] == pytest.approx(g["S2.area.total"] * 60 + grid * 20)
    assert g["S0.capex.building_works"] == pytest.approx(g["S0.area.total"] * 60)
    items = ("storage", "equipment", "controls", "building_works", "overflow")
    items += ("integration_commissioning",)
    assert g["S2.capex.contingency"] == pytest.approx(0.10 * sum(g[f"S2.capex.{k}"] for k in items))


def _param_blocks(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        if "id" in node and "typ" in node:
            return [node]
        return [b for v in node.values() for b in _param_blocks(v)]
    return [b for v in node for b in _param_blocks(v)] if isinstance(node, list) else []


def test_T1_5_oracle_param_ids_and_values_match_the_catalog() -> None:
    """I47: 72 Param blocks in catalog/. The ids S0 and S2 count are catalog ids, together
    every non-amr_gtp id, and the oracle reads each at its catalog typ (e.g. cube floor_prep 20,
    max_robots_per_m2 0.05, m2_per_robot_parking 2.0)."""
    blocks = {
        p.name: _param_blocks(yaml.safe_load(p.read_text(encoding="utf-8")))
        for p in sorted(CATALOG.rglob("*.yaml"))
    }
    sizes = {"cube_asrs.yaml": 21, "manual_p2p.yaml": 19, "labor_standards.yaml": 9}
    sizes |= {"finance_defaults.yaml": 2, "engine_defaults.yaml": 1, "amr_gtp.yaml": 20}
    assert {k: len(v) for k, v in blocks.items() if v} == sizes  # 72 in all
    catalog = {b["id"]: b["typ"] for v in blocks.values() for b in v}
    read = set(oracle.low_confidence_params("manual_p2p"))
    read |= set(oracle.low_confidence_params("cube_asrs"))
    assert read == {i for i in catalog if not i.startswith("amr_gtp.")}
    typ = {f"manual_p2p.{k}": v for k, v in oracle.MANUAL.items()}
    typ |= {f"cube_asrs.{k}": v for k, v in oracle.CUBE.items()}
    typ |= {f"labor.{k}": v for k, (_, v) in oracle.LABOR.items()}
    typ |= {
        "finance.packaging_eur_per_order": oracle.PACKAGING_EUR_PER_ORDER,
        "finance.kwh_per_station_year": oracle.KWH_PER_STATION_YEAR,
        "engine.pack_station_oee": oracle.PACK_STATION_OEE,
    }
    assert {i: typ.get(i) for i in read} == {i: catalog[i] for i in read}


# --- eligibility guard ---------------------------------------------------------------------------
def test_T1_5_share_stock_cube_is_zero_without_stock(tmp_path: Path) -> None:
    """I10: no inventory (R14) → Σ stock cube = 0 → share_stock_cube = 0 (no ZeroDivisionError)."""
    inv = _read("inventory").head(0)
    g = build_golden.run(data_dir=_data(tmp_path, inventory=inv))[0].values()
    assert g["eligibility.cube_asrs.share_stock_cube"] == 0.0
    assert g["S2.eligibility.share_stock_cube"] == 0.0
    assert g["stock.avg_units"] == 0.0
    assert g["eligibility.cube_asrs.share_lines"] == _golden()["eligibility.cube_asrs.share_lines"]
