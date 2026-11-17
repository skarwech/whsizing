"""F3 step 5: stock averaged over inventory snapshots, cover, dead stock, growth (R14)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
from dateutil.relativedelta import relativedelta

from whsizing.profile.aggregate import fsum
from whsizing.schemas import StockStats

STALE_SNAPSHOT_MONTHS = 6  # R14 (same rule as F2 io.rules R14_MAX_AGE_MONTHS) → stock flagged L
DAYS_PER_YEAR = 365.25

EMPTY_INVENTORY = pl.DataFrame(
    schema={"sku": pl.String, "qty_units": pl.Int64, "snapshot_date": pl.Date}
)


def sku_stock(inventory: pl.DataFrame) -> pl.DataFrame:
    """Per SKU: avg_stock = Σ units / number of snapshots (a SKU absent from a snapshot has 0
    units in it: WMS exports omit zero-stock rows), last_stock = units in the last snapshot."""
    n_snapshots = inventory["snapshot_date"].n_unique()
    per_snap = inventory.group_by("sku", "snapshot_date").agg(pl.col("qty_units").sum())
    last = per_snap.filter(pl.col("snapshot_date") == pl.col("snapshot_date").max())
    return (
        per_snap.group_by("sku")
        .agg(avg_stock=pl.col("qty_units").sum() / n_snapshots)
        .join(last.select("sku", last_stock="qty_units"), on="sku", how="left")
        .with_columns(pl.col("last_stock").fill_null(0))
    )


def growth_per_year(inventory: pl.DataFrame) -> float | None:
    """OLS slope of snapshot totals (units/day × 365.25); None with fewer than 3 snapshots."""
    tot = inventory.group_by("snapshot_date").agg(pl.col("qty_units").sum()).sort("snapshot_date")
    if tot.height < 3:
        return None
    days = (tot["snapshot_date"] - tot["snapshot_date"][0]).dt.total_days().to_numpy()
    return float(np.polyfit(days.astype(float), tot["qty_units"].to_numpy().astype(float), 1)[0])


def stock_stats(
    skus: pl.DataFrame,
    inventory: pl.DataFrame,
    period_end: date,
    mean_units_day: float,
    dead_stock_days: int,
) -> StockStats:
    """`skus` needs avg_stock, last_stock, unit_cube_m3 and last_line_date. Dead stock = last
    snapshot stock > 0 and no shipped line in the `dead_stock_days` up to period_end."""
    snaps = inventory["snapshot_date"].unique()
    last_snapshot: date | None = snaps.max() if snaps.len() else None  # pyright: ignore[reportAssignmentType]
    cutoff = period_end - timedelta(days=dead_stock_days)
    dead = skus.filter(
        (pl.col("last_stock") > 0)
        & (pl.col("last_line_date").is_null() | (pl.col("last_line_date") <= cutoff))
    )
    avg_units = fsum(skus["avg_stock"])
    slope = growth_per_year(inventory)
    stale = last_snapshot is None or last_snapshot < period_end - relativedelta(
        months=STALE_SNAPSHOT_MONTHS
    )
    return StockStats(
        n_snapshots=snaps.len(),
        last_snapshot=last_snapshot,
        n_skus_in_stock=skus.filter(pl.col("avg_stock") > 0).height,
        avg_units=avg_units,
        avg_cube_m3=fsum(skus["avg_stock"] * skus["unit_cube_m3"]),
        # I49: no inventory → 0 stock per SKU → cover 0.0 (stock flagged L by R14)
        cover_days=avg_units / mean_units_day if mean_units_day > 0 else None,
        dead_stock_skus=dead.height,
        dead_stock_cube_m3=fsum(dead["last_stock"] * dead["unit_cube_m3"]),
        growth_units_per_year=None if slope is None else slope * DAYS_PER_YEAR,
        confidence="L" if stale else "H",
    )
