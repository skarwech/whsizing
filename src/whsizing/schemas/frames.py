"""Pandera DataFrameModels (Polars backend) for the canonical tables (§4.1).

Column checks only (dtype, nulls, ge/isin/unique). Row-level business rules (R1..R14) live in
`whsizing.io.rules`. Numeric and string columns coerce; timestamp columns do NOT, so a naive
datetime is rejected instead of being silently read as UTC: localise before validating.
Columns typed `X | None` are optional (may be absent); `nullable` governs null values.
"""

from __future__ import annotations

from typing import Annotated

import pandera.polars as pa
import polars as pl

LINE_STATUSES = ["shipped", "cancelled", "returned", "unknown"]
TEMPERATURE_CLASSES = ["ambient", "chilled", "frozen"]
UtcDatetime = Annotated[pl.Datetime, "us", "UTC"]


class _Canonical(pa.DataFrameModel):
    class Config:  # pyright: ignore[reportIncompatibleVariableOverride]
        strict = False  # derived columns (§4.2) may be present


class OrderLines(_Canonical):
    order_id: pl.Utf8 = pa.Field(coerce=True)
    order_ts: UtcDatetime = pa.Field()
    sku: pl.Utf8 = pa.Field(coerce=True)
    qty_units: pl.Int64 = pa.Field(coerce=True, ne=0)
    channel: pl.Utf8 | None = pa.Field(coerce=True, nullable=True)
    line_status: pl.Categorical | None = pa.Field(coerce=True, isin=LINE_STATUSES)
    source_file: pl.Utf8 = pa.Field(coerce=True)
    source_row: pl.Int64 = pa.Field(coerce=True)


class SkuMaster(_Canonical):
    sku: pl.Utf8 = pa.Field(coerce=True, unique=True)
    length_mm: pl.Float64 = pa.Field(coerce=True, nullable=True, gt=0, lt=3000)
    width_mm: pl.Float64 = pa.Field(coerce=True, nullable=True, gt=0, lt=3000)
    height_mm: pl.Float64 = pa.Field(coerce=True, nullable=True, gt=0, lt=3000)
    weight_kg: pl.Float64 = pa.Field(coerce=True, nullable=True, gt=0, lt=1500)
    units_per_case: pl.Int64 | None = pa.Field(coerce=True, nullable=True, ge=1)
    cases_per_pallet: pl.Int64 | None = pa.Field(coerce=True, nullable=True, ge=1)
    units_per_pallet: pl.Int64 | None = pa.Field(coerce=True, ge=1)
    category: pl.Utf8 | None = pa.Field(coerce=True, nullable=True)
    stackable: pl.Boolean | None = pa.Field(coerce=True, nullable=True)
    temperature_class: pl.Categorical | None = pa.Field(
        coerce=True, nullable=True, isin=TEMPERATURE_CLASSES
    )
    hazmat: pl.Boolean | None = pa.Field(coerce=True, nullable=True)
    unit_cube_m3: pl.Float64 | None = pa.Field(coerce=True, nullable=True, gt=0)


class Inventory(_Canonical):
    sku: pl.Utf8 = pa.Field(coerce=True)
    qty_units: pl.Int64 = pa.Field(coerce=True, ge=0)
    snapshot_date: pl.Date = pa.Field(coerce=True)


class Receipts(_Canonical):
    receipt_id: pl.Utf8 = pa.Field(coerce=True)
    receipt_ts: UtcDatetime = pa.Field()
    sku: pl.Utf8 = pa.Field(coerce=True)
    qty_units: pl.Int64 = pa.Field(coerce=True, gt=0)
    pallets: pl.Float64 | None = pa.Field(coerce=True, nullable=True, ge=0)


class DailySeries(_Canonical):
    date: pl.Date = pa.Field(coerce=True, unique=True)
    weekday: pl.Int64 = pa.Field(coerce=True, in_range={"min_value": 0, "max_value": 6})  # 0=Mon
    is_operating: pl.Boolean = pa.Field(coerce=True)
    is_holiday: pl.Boolean = pa.Field(coerce=True)
    orders: pl.Float64 = pa.Field(coerce=True, ge=0)
    lines: pl.Float64 = pa.Field(coerce=True, ge=0)
    units: pl.Float64 = pa.Field(coerce=True, ge=0)
    cube_m3: pl.Float64 = pa.Field(coerce=True, ge=0)
    weight_kg: pl.Float64 = pa.Field(coerce=True, ge=0)
    parcels: pl.Float64 = pa.Field(coerce=True, ge=0)
    pallets_out: pl.Float64 = pa.Field(coerce=True, ge=0)
    return_lines: pl.Float64 = pa.Field(coerce=True, ge=0)
    receipts_lines: pl.Float64 | None = pa.Field(coerce=True, nullable=True, ge=0)
    receipts_units: pl.Float64 | None = pa.Field(coerce=True, nullable=True, ge=0)
    receipts_pallets: pl.Float64 | None = pa.Field(coerce=True, nullable=True, ge=0)
