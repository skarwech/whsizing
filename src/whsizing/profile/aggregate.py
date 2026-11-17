"""F3 step 1-2: canonical frames → shipped lines, orders, SKUs, daily series; series stats.

Rules where the spec is ambiguous follow docs/INTERPRETATIONS.md (I1, I2, I3, I10).
"""

from __future__ import annotations

import math
from datetime import date, time
from itertools import accumulate, pairwise
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl

from whsizing.errors import DataQualityError, WhsizingError
from whsizing.io.canonical import validate
from whsizing.io.readers import read_parquet_file
from whsizing.logging import get_logger
from whsizing.profile.calendar import flag_calendar
from whsizing.schemas import DailySeries, ProfileCfg, SeriesStats

CANONICAL = ("order_lines", "sku_master", "inventory", "receipts")
DIMS = ("length_mm", "width_mm", "height_mm", "weight_kg")
METRICS = ("orders", "lines", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
RECEIPT_COLS = ("receipts_lines", "receipts_units", "receipts_pallets")
LINE_SUMS = {"line_cube_m3": "cube_m3", "line_weight_kg": "weight_kg"}  # per order and per day


def load_canonical(canonical_dir: Path) -> dict[str, pl.DataFrame]:
    """Read and validate (§4.1 Pandera schemas, WhsizingError on a missing column, a wrong
    dtype or a null key such as sku) the canonical tables in `canonical_dir`; order_lines is
    required. Frames come back in one chunk each: pandera's coercion splits them into
    thread-count chunks, and polars divides a length-1 chunk by a scalar exactly but other
    chunks by a reciprocal multiply, so a unit cube moved in the last ULP with the thread
    count and the row order (T3.7, principle 5)."""
    if not (canonical_dir / "order_lines.parquet").is_file():
        raise WhsizingError(f"no canonical order_lines.parquet in {canonical_dir}")
    out: dict[str, pl.DataFrame] = {}
    for name in CANONICAL:
        if not (path := canonical_dir / f"{name}.parquet").is_file():
            continue
        try:
            df = read_parquet_file(path)
        except pl.exceptions.PolarsError as e:  # corrupt or truncated file, not a raw polars error
            raise WhsizingError(f"canonical {name}: cannot read {path}: {e}") from e
        try:
            out |= validate({name: df})
        except WhsizingError as e:  # I72: F2's wording, plus where the table was read
            raise WhsizingError(f"{e} (in {canonical_dir})") from e
    return {name: df.rechunk() for name, df in out.items()}


def _status() -> pl.Expr:
    return pl.col("line_status").cast(pl.String).fill_null("shipped")


def shipped_lines(order_lines: pl.DataFrame, tz: str) -> pl.DataFrame:
    """I1: shipped = status shipped/null and qty > 0. Every line takes its order's first
    timestamp (multi-day orders) in `tz`: local date, hour, and `no_time` (00:00:00 to the
    second, I51)."""
    if "line_status" not in order_lines.columns:
        order_lines = order_lines.with_columns(line_status=pl.lit(None, pl.String))
    local = pl.col("order_ts").min().over("order_id").dt.convert_time_zone(tz)
    lines = (
        order_lines.lazy()
        .filter((_status() == "shipped") & (pl.col("qty_units") > 0))
        .with_columns(local.alias("local_ts"))
        .select(
            "order_id",
            "sku",
            "qty_units",
            date=pl.col("local_ts").dt.date(),
            hour=pl.col("local_ts").dt.hour().cast(pl.Int64),
            no_time=pl.col("local_ts").dt.time() < time(0, 0, 1),
        )
        .collect()
    )
    if lines.is_empty():
        raise DataQualityError("no shipped order lines: the demand profile cannot be built")
    return lines


def return_lines(order_lines: pl.DataFrame, tz: str) -> pl.DataFrame:
    """Return lines (status returned or qty < 0), dated by their own timestamp; never orders."""
    is_return = pl.col("qty_units") < 0
    if "line_status" in order_lines.columns:
        is_return = is_return | (pl.col("line_status").cast(pl.String) == "returned")
    return order_lines.filter(is_return).select(
        date=pl.col("order_ts").dt.convert_time_zone(tz).dt.date()
    )


def sku_table(master: pl.DataFrame | None, seen_skus: pl.Series) -> pl.DataFrame:
    """SKU master + orphan SKUs (`seen_skus` absent from the master: shipped, F2 R2 / I10, or
    stocked): has_dims (l, w, h and weight known), unit cube = l × w × h / 1e9, else the given
    unit_cube_m3, else 0."""
    if master is None:
        master = pl.DataFrame(schema={"sku": pl.String} | dict.fromkeys(DIMS, pl.Float64))
    if "unit_cube_m3" not in master.columns:
        master = master.with_columns(unit_cube_m3=pl.lit(None, pl.Float64))
    master = master.select("sku", *DIMS, "unit_cube_m3")
    orphans = seen_skus.unique().to_frame("sku").join(master, on="sku", how="anti")
    vol = pl.col("length_mm") * pl.col("width_mm") * pl.col("height_mm") / 1e9
    return pl.concat([master, orphans.sort("sku")], how="diagonal").with_columns(
        has_dims=pl.all_horizontal([pl.col(c).is_not_null() for c in DIMS]),
        unit_cube_m3=pl.coalesce(vol, pl.col("unit_cube_m3"), pl.lit(0.0)),
        orphan=pl.col("sku").is_in(orphans["sku"].implode()),
    )


def with_cube(lines: pl.DataFrame, skus: pl.DataFrame) -> pl.DataFrame:
    """§4.2 line_cube_m3, line_weight_kg (0 when the SKU has no cube or weight, I10), has_dims.
    Rows sorted by (order_id, sku, qty_units), which fix every other column, so the frame does
    not depend on the input row order (T3.7); its float sums go through `fsum_by`."""
    return (
        lines.join(
            skus.select("sku", "unit_cube_m3", "weight_kg", "has_dims"), on="sku", how="left"
        )
        .with_columns(
            line_cube_m3=(pl.col("qty_units") * pl.col("unit_cube_m3")).fill_null(0.0),
            line_weight_kg=(pl.col("qty_units") * pl.col("weight_kg")).fill_null(0.0),
        )
        .sort("order_id", "sku", "qty_units")
    )


def fsum_by(df: pl.DataFrame, key: str, cols: tuple[str, ...]) -> pl.DataFrame:
    """Per `key` (sorted): exact sums (math.fsum, correctly rounded) of the float `cols`, which
    must hold no null. Polars adds a group's floats in an order that depends on the thread
    count (last-ULP drift between machines); an exact sum depends on neither the thread count
    nor the row order (principle 5, T3.7). Same sums as the golden oracle. A 0-row frame (F2
    can write an empty receipts table) gives a 0-row result."""
    s = df.select(key, *cols).sort(key)
    runs = s.group_by(key, maintain_order=True).len()  # sorted input: key order, contiguous
    bounds = list(pairwise([0, *accumulate(runs["len"].to_list())]))
    sums = []
    for c in cols:
        v = s[c].to_list()
        sums.append(pl.Series(c, [math.fsum(v[a:b]) for a, b in bounds], dtype=pl.Float64))
    return runs.select(key).with_columns(sums)


def fsum(s: pl.Series) -> float:
    """Exact sum (math.fsum) of a numeric column without null: `Series.sum` adds per chunk, and
    sorts split frames into thread-count chunks (stock.avg_units moved in the last ULP at 24
    threads on 513 SKUs), so whole-column float sums go through here (principle 5)."""
    return math.fsum(s.to_list())


def orders_table(lines: pl.DataFrame) -> pl.DataFrame:
    """Per shipped order, sorted by order_id: date, lines, units, cube and weight (F3 step 3)."""
    sums = fsum_by(lines, "order_id", tuple(LINE_SUMS)).rename(LINE_SUMS)
    return (
        lines.group_by("order_id")
        .agg(pl.col("date").first(), n_lines=pl.len(), units=pl.col("qty_units").sum())
        .join(sums, on="order_id")
        .sort("order_id")
    )


def _receipts_daily(receipts: pl.DataFrame, tz: str) -> pl.DataFrame:
    """Per local date; receipts_pallets null (unknown, never an undercount) when a receipt of
    that date has no pallets, else their exact sum."""
    if "pallets" not in receipts.columns:
        receipts = receipts.with_columns(pallets=pl.lit(None, pl.Float64))
    r = receipts.with_columns(date=pl.col("receipt_ts").dt.convert_time_zone(tz).dt.date())
    pallets = fsum_by(r.with_columns(pl.col("pallets").fill_null(0.0)), "date", ("pallets",))
    return (
        r.group_by("date")
        .agg(
            receipts_lines=pl.len(),
            receipts_units=pl.col("qty_units").sum(),
            unknown=pl.col("pallets").null_count(),
        )
        .join(pallets, on="date")
        .select(
            "date",
            "receipts_lines",
            "receipts_units",
            receipts_pallets=pl.when(pl.col("unknown") == 0).then("pallets"),
        )
    )


def _receipts_in_window(
    receipts: pl.DataFrame | None, tz: str, start: date, end: date
) -> pl.DataFrame | None:
    """The daily receipts, or None when the table is absent, has no row, or none dated inside
    [start, end] (I71; logged: F4 receipts mode will refuse to size on it)."""
    if receipts is None or receipts.is_empty():
        return None
    daily = _receipts_daily(receipts, tz)
    if daily["date"].is_between(start, end).any():
        return daily
    first, last = daily["date"].min(), daily["date"].max()
    get_logger().warning(
        "receipts_outside_history",
        receipts_period=[str(first), str(last)],
        history_window=[str(start), str(end)],
    )
    return None


def receipts_period(receipts: pl.DataFrame | None, tz: str) -> tuple[date, date] | None:
    """First and last local receipt date (I71); None without a receipts table or without a row."""
    if receipts is None or receipts.is_empty():
        return None
    local = receipts["receipt_ts"].dt.convert_time_zone(tz).dt.date()
    return cast(date, local.min()), cast(date, local.max())


def daily_table(
    lines: pl.DataFrame,
    orders: pl.DataFrame,
    returns: pl.DataFrame,
    receipts: pl.DataFrame | None,
    tz: str,
    cfg: ProfileCfg,
) -> pl.DataFrame:
    """§4.1 daily_series over every date from the first to the last shipped local date (I2).
    receipts_* columns only if receipts are present: a receipts table with no row (F2 drops
    every row) or none inside that window (I71) counts as absent, so F4 receipts mode raises
    ConfigError instead of sizing inbound at 0."""
    start, end = cast(date, lines["date"].min()), cast(date, lines["date"].max())
    rdaily = _receipts_in_window(receipts, tz, start, end)
    d = pl.DataFrame({"date": pl.date_range(start, end, eager=True)})
    parts = [
        lines.group_by("date").agg(lines=pl.len(), units=pl.col("qty_units").sum()),
        fsum_by(lines, "date", tuple(LINE_SUMS)).rename(LINE_SUMS),
        orders.group_by("date").agg(
            orders=pl.len(), parcels=pl.col("parcels").sum(), pallets_out=pl.col("pallets").sum()
        ),
        returns.group_by("date").agg(return_lines=pl.len()),
    ]
    if rdaily is not None:
        parts.append(rdaily)
    for p in parts:
        d = d.join(p, on="date", how="left")
    if rdaily is not None:  # no receipt that day → 0 pallets; unknown pallets stay null
        pallets = pl.when(pl.col("receipts_lines").is_null()).then(0.0)
        d = d.with_columns(receipts_pallets=pallets.otherwise("receipts_pallets"))
    d = flag_calendar(d.with_columns(pl.exclude("date", "receipts_pallets").fill_null(0)), cfg)
    receipt_cols = list(RECEIPT_COLS) if rdaily is not None else []
    return d.sort("date").select(
        "date",
        "weekday",
        "is_operating",
        "is_holiday",
        *[pl.col(c).cast(pl.Float64) for c in (*METRICS, "return_lines", *receipt_cols)],
    )


def validate_daily(daily: pl.DataFrame) -> pl.DataFrame:
    try:
        return DailySeries.validate(daily)
    except Exception as e:  # pandera SchemaError(s): an F3 bug, never client data
        raise WhsizingError(f"daily_series failed schema validation: {e}") from e


def series_stats(x: np.ndarray) -> SeriesStats:
    """F3 step 2 (I3): mean, P50/P90/P95/P98 (np.percentile, linear), max, CV = std(ddof=0)/mean.
    Mean and variance are exact sums (math.fsum): np.mean / np.std add in array order, and the
    orders are listed in hashed order_id order, so the last ULP moved with the anonymisation
    salt (R6). Same values as numpy within a few ULP; percentiles and max ignore the order."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:  # unreachable from build_profile: shipped_lines raises on no shipped line
        raise WhsizingError("series_stats needs at least one value")
    mean = math.fsum(x.tolist()) / x.size
    var = math.fsum(((x - mean) ** 2).tolist()) / x.size
    p50, p90, p95, p98 = (float(v) for v in np.percentile(x, [50, 90, 95, 98]))
    cv = math.sqrt(var) / mean if mean else 0.0
    return SeriesStats(mean=mean, p50=p50, p90=p90, p95=p95, p98=p98, max=float(np.max(x)), cv=cv)
