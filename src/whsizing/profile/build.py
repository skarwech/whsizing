"""F3 entry points: build_profile (steps 1-9) and write_profile (artifacts, step 10)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from whsizing.profile import aggregate as agg
from whsizing.profile.abc import abc, classify
from whsizing.profile.eiq import eiq
from whsizing.profile.intraday import intraday
from whsizing.profile.seasonality import seasonality
from whsizing.profile.shipments import shipment_split, split_orders
from whsizing.profile.stock import EMPTY_INVENTORY, sku_stock, stock_stats
from whsizing.schemas import DemandProfile, DesignBasis, Flows, ProfileCfg

DEFAULT_TZ = "Europe/Paris"  # DesignBasis.timezone default, used when no basis is given
DAILY_SERIES_PATH = "canonical/daily_series.parquet"  # relative to the run folder (§2.4)
PROFILE_JSON = "profile/demand_profile.json"


@dataclass(frozen=True)
class ProfileTables:
    """Intermediate frames of one profile build; F4 (design day, inbound) and the charts use
    them. `lines`: shipped lines; `orders`: per order with the shipment split; `skus`: SKU
    master + orphans with movement, stock and ABC class by lines; `daily`: §4.1 daily_series."""

    lines: pl.DataFrame
    orders: pl.DataFrame
    skus: pl.DataFrame
    daily: pl.DataFrame
    inventory: pl.DataFrame
    dataset_hash: str
    receipts_period: tuple[date, date] | None = None  # local dates of the receipts table (I71)


def dataset_hash(frames: dict[str, pl.DataFrame]) -> str:
    """sha256 (16 hex) of the canonical tables, independent of row order (T3.7)."""
    h = hashlib.sha256()
    for name in agg.CANONICAL:
        if (df := frames.get(name)) is not None:
            s = df.select(pl.all().cast(pl.String))
            h.update(name.encode())
            h.update(s.sort(s.columns, nulls_last=True).write_csv().encode())
    return h.hexdigest()[:16]


def _sku_movement(skus: pl.DataFrame, lines: pl.DataFrame, inventory: pl.DataFrame) -> pl.DataFrame:
    """Per SKU over the whole history (I5): lines, units, last line date, cube movement,
    average and last stock, stock cube."""
    mv = lines.group_by("sku").agg(
        lines=pl.len(), units=pl.col("qty_units").sum(), last_line_date=pl.col("date").max()
    )
    return (
        skus.join(mv, on="sku", how="left")
        .join(sku_stock(inventory), on="sku", how="left")
        .with_columns(pl.col("lines", "units", "avg_stock", "last_stock").fill_null(0))
        .with_columns(
            cube_movement_m3=pl.col("units") * pl.col("unit_cube_m3"),
            stock_cube_m3=pl.col("avg_stock") * pl.col("unit_cube_m3"),
        )
    )


def build_tables(canonical_dir: Path, basis: DesignBasis | None, cfg: ProfileCfg) -> ProfileTables:
    """F3 step 1 and the per-order / per-SKU frames behind steps 2-9."""
    frames = agg.load_canonical(canonical_dir)
    tz = basis.timezone if basis is not None else DEFAULT_TZ
    flows = basis.flows if basis is not None else Flows()
    order_lines = frames["order_lines"]
    shipped = agg.shipped_lines(order_lines, tz)
    inventory = frames.get("inventory", EMPTY_INVENTORY)
    # orphans: shipped or stocked SKUs absent from the master (stock-only ones count as dead stock)
    skus = agg.sku_table(frames.get("sku_master"), pl.concat([shipped["sku"], inventory["sku"]]))
    lines = agg.with_cube(shipped, skus)
    orders = split_orders(agg.orders_table(lines), flows)
    returns = agg.return_lines(order_lines, tz)
    receipts = frames.get("receipts")
    daily = agg.daily_table(lines, orders, returns, receipts, tz, cfg)
    skus = classify(_sku_movement(skus, lines, inventory), "lines", cfg.abc_thresholds)
    period = agg.receipts_period(receipts, tz)
    return ProfileTables(lines, orders, skus, daily, inventory, dataset_hash(frames), period)


def profile_from_tables(t: ProfileTables, cfg: ProfileCfg) -> DemandProfile:
    """F3 steps 2-9 on the frames of `build_tables`."""
    op = t.daily.filter("is_operating")
    period_end = t.daily["date"].max()
    shares, peak, conf = intraday(t.lines, t.daily, cfg)
    return DemandProfile(
        dataset_hash=t.dataset_hash,
        period_start=t.daily["date"].min(),  # pyright: ignore[reportArgumentType]
        period_end=period_end,  # pyright: ignore[reportArgumentType]
        operating_days=op.height,
        daily={m: agg.series_stats(op[m].to_numpy()) for m in agg.METRICS},
        eiq=eiq(t.lines, t.orders, cfg.order_class_bounds),
        abc=abc(t.skus, cfg.abc_thresholds),
        stock=stock_stats(
            t.skus,
            t.inventory,
            period_end,  # pyright: ignore[reportArgumentType]
            float(op["units"].mean()),  # pyright: ignore[reportArgumentType]
            cfg.dead_stock_days,
        ),
        seasonality=seasonality(t.daily),
        intraday=shares,
        peak_hour_share=peak,
        shipment_split=shipment_split(t.orders),
        dims_coverage_lines=float(t.lines["has_dims"].mean()),  # pyright: ignore[reportArgumentType]
        daily_series_path=DAILY_SERIES_PATH,
        intraday_confidence=conf,
        receipts_period=t.receipts_period,
    )


def build_profile(canonical_dir: Path, basis: DesignBasis | None, cfg: ProfileCfg) -> DemandProfile:
    """F3 signature. Use `build_tables` + `profile_from_tables` to keep the frames for
    `write_profile` and F4."""
    return profile_from_tables(build_tables(canonical_dir, basis, cfg), cfg)


def write_profile(profile: DemandProfile, run_dir: Path, tables: ProfileTables) -> list[Path]:
    """Write profile/demand_profile.json, canonical/daily_series.parquet and the 8 charts
    (profile/charts/<name>.png and .html) under `run_dir`; return the written paths."""
    from whsizing.profile.charts import write_charts  # lazy: matplotlib / plotly import cost

    json_path = run_dir / PROFILE_JSON
    series_path = run_dir / profile.daily_series_path
    for p in (json_path, series_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    agg.validate_daily(tables.daily).write_parquet(series_path)
    return [json_path, series_path, *write_charts(profile, tables, json_path.parent / "charts")]
