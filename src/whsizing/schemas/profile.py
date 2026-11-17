"""DemandProfile and its sub-models (§2.5, F3)."""

from __future__ import annotations

from datetime import date
from typing import Self

from pydantic import model_validator

from whsizing.schemas.params import Confidence, StrictModel


class SeriesStats(StrictModel):
    mean: float
    p50: float
    p90: float
    p95: float
    p98: float
    max: float
    cv: float


class EIQ(StrictModel):
    """F3 step 3: order structure. Distributions are per order (or per line for units_per_line)."""

    lines_per_order: SeriesStats
    units_per_line: SeriesStats
    units_per_order: SeriesStats
    cube_per_order_m3: SeriesStats
    weight_per_order_kg: SeriesStats
    single_line_share: float  # share of orders with one line
    order_class_shares: dict[str, float]  # "S" (1 line), "M" (2-5), "L" (> 5) → share of orders


class AbcClassStats(StrictModel):
    """Size of one ABC class: share of SKUs, of lines and of cube."""

    n_skus: int
    sku_share: float
    line_share: float
    cube_share: float


class ABC(StrictModel):
    """F3 step 4: classes "A", "B", "C" by lines, by cube movement and by stock cube."""

    thresholds: tuple[float, float]  # cumulative share limits of A and B, e.g. (0.80, 0.95)
    by_lines: dict[str, AbcClassStats]
    by_cube_movement: dict[str, AbcClassStats]
    by_stock_cube: dict[str, AbcClassStats]
    pareto_lines: list[float]  # 100 points: cumulative line share at SKU share k/100, k = 1..100


class StockStats(StrictModel):
    """F3 step 5: stock averaged over inventory snapshots."""

    n_snapshots: int
    last_snapshot: date | None
    n_skus_in_stock: int
    avg_units: float  # Σ_sku mean units over snapshots
    avg_cube_m3: float
    cover_days: float | None  # Σ stock units / mean daily units shipped
    dead_stock_skus: int  # stock > 0 and no line in the dead-stock window
    dead_stock_cube_m3: float
    growth_units_per_year: float | None  # OLS slope on snapshot totals; None if < 3 snapshots
    confidence: Confidence = "H"  # L when the snapshot is old or missing (R14)


class Seasonality(StrictModel):
    """F3 step 6: indices on operating days."""

    monthly_index: list[float | None]  # 12 values Jan..Dec; None = month absent from history
    weekday_index: list[float]  # 7 values Mon..Sun
    peak_to_average: float  # P95 / mean of daily lines
    trend_cagr: float | None
    trend_confidence: Confidence
    confidence: Confidence = "H"  # L when history < 12 months (R10)


class ShipmentSplit(StrictModel):
    """F3 step 8: parcel vs pallet orders."""

    parcel_share_orders: float
    pallet_share_orders: float
    parcel_share_lines: float
    pallet_share_lines: float
    mean_parcels_per_order: float  # over parcel orders


class ProfileCfg(StrictModel):
    """F3 configuration; every field has a default so a partial project.yaml validates."""

    operating_day_threshold: float = 0.10  # [P] share of median positive daily lines
    holiday_country: str = "FR"
    holiday_overrides: list[date] = []  # extra non-operating dates on top of the country calendar
    abc_thresholds: tuple[float, float] = (0.80, 0.95)  # [P]
    dead_stock_days: int = 180  # [P]
    no_time_share_max: float = 0.20  # above this share of lines without time → default intraday
    default_intraday: list[float] = [0.0] * 8 + [1.0 / 9] * 9 + [0.0] * 7  # [P] flat 08:00-17:00
    order_class_bounds: tuple[int, int] = (1, 5)  # [P] S ≤ 1 line < M ≤ 5 lines < L

    @model_validator(mode="after")
    def _check(self) -> Self:
        if len(self.default_intraday) != 24 or abs(sum(self.default_intraday) - 1.0) > 1e-9:
            raise ValueError("default_intraday must have 24 shares summing to 1")
        lo, hi = self.abc_thresholds
        if not (0 < lo < hi <= 1):
            raise ValueError("abc_thresholds must satisfy 0 < A < B ≤ 1")
        return self


class DemandProfile(StrictModel):
    dataset_hash: str
    period_start: date
    period_end: date
    operating_days: int
    daily: dict[str, SeriesStats]  # orders, lines, units, cube_m3, weight_kg
    eiq: EIQ
    abc: ABC
    stock: StockStats
    seasonality: Seasonality
    intraday: dict[int, list[float]]  # weekday (0=Mon) → 24 shares summing to 1
    peak_hour_share: float
    shipment_split: ShipmentSplit
    dims_coverage_lines: float  # share of lines whose SKU has dims and weight
    daily_series_path: str
    intraday_confidence: Confidence = "H"  # L when > 20 % of lines have no time (F3 step 7)
    # First and last local receipt date of the receipts table, whether or not it falls inside
    # the shipped-date window (I71: F4 names it when receipts mode has no receipts to size on);
    # None: no receipts table, or one without a row.
    receipts_period: tuple[date, date] | None = None
