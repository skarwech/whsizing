"""DesignDay, Inbound and Assumption (§2.5, F4)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from whsizing.schemas.params import StrictModel
from whsizing.schemas.result import Flag


class Inbound(StrictModel):
    mode: Literal["receipts", "derived"]
    units_per_day: float
    pallets_per_day: float
    receipt_lines_per_day: float
    trucks_per_day: float
    peak_factor: float
    cases_per_day: float | None = None  # I13 Σ_sku units_in / units_per_case; None without SKUs
    flags: list[Flag] = []  # F_DEFAULT_UPP: units_per_pallet fallback (F4 inbound, "flagged")


class Assumption(StrictModel):
    key: str
    value: float | str
    unit: str
    origin: Literal["default", "client", "override", "derived"]
    note: str = ""


class DesignDay(StrictModel):
    percentile: float
    growth_rate: float
    horizon_years: int
    reference_date: date  # actual day nearest the percentile
    lines: float
    orders: float
    units: float
    cube_m3: float
    weight_kg: float
    design_weekday: int
    hourly_lines: list[float]  # 24 values, sum == lines
    peak_hour_lines: float
    parcels: float
    pallets_out: float
    stock_units: float
    stock_cube_m3: float
    inbound: Inbound
    assumptions: list[Assumption]
    percentile_values: dict[str, float] = {}  # P_m per metric, reported next to ratio-derived m*
    flags: list[Flag] = []  # F_RATIO_DRIFT, F_PERCENTILE_CLIPPED, F_SHORT_HISTORY
