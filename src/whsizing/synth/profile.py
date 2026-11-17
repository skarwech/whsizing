"""Synthetic-data profile (F1 'Generator parameters' table) and the daily order-rate formula.

Defaults marked [P] are the spec's placeholder values, verbatim. Other defaults are F1 choices
the spec leaves open (documented inline).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Annotated, Self

import numpy as np
from pydantic import Field, model_validator

from whsizing.config import load_yaml_model
from whsizing.schemas.params import StrictModel

LOCAL_TZ = "Europe/Paris"  # §3.5: timestamps are Paris wall time, stored as UTC

Share = Annotated[float, Field(ge=0, le=1)]
PosFloat = Annotated[float, Field(gt=0)]
NonNeg = Annotated[float, Field(ge=0)]


class Promo(StrictModel):
    date: dt.date
    multiplier: PosFloat = 2.0  # [P]
    duration_days: Annotated[int, Field(ge=1)] = 3  # [P]


class DefectCfg(StrictModel):
    """Step 9 defect injector. Each switch is independent; shares are of rows of the named table."""

    bom: bool = False  # UTF-8 BOM on every CSV
    cp1252: bool = False  # cp1252 encoding; wins over `bom` (a BOM makes no sense in cp1252)
    mixed_date_formats: bool = False  # order_lines.order_ts
    missing_dims: bool = False  # sku_master L/W/H nulled
    orphan_skus: bool = False  # order_lines.sku replaced by SKUs absent from the master
    duplicate_rows: bool = False  # order_lines exact duplicate rows
    negative_quantities: bool = False  # shipped order lines and inventory rows negated
    trailing_spaces: bool = False  # sku / order_id values padded with spaces
    thousand_separators: bool = False  # integer quantities ≥ 1000 grouped ('1,234' / '1.234')
    second_header_row: bool = False  # header line repeated once mid-file (concatenated exports)
    cm_instead_of_mm: bool = False  # sku_master dims ÷ 10 on a share of rows
    missing_dims_share: Share = 0.08  # [P]
    orphan_skus_share: Share = 0.02  # [P]
    duplicate_rows_share: Share = 0.005  # [P]
    cm_rows_share: Share = 0.30  # [P]
    mixed_dates_share: Share = 0.10  # F1 choice
    negative_qty_share: Share = 0.01  # F1 choice
    trailing_spaces_share: Share = 0.05  # F1 choice


class SynthProfile(StrictModel):
    """One profile YAML (data/synth/profiles/*.yaml). Units in the field names."""

    name: str
    # Scale
    n_skus: Annotated[int, Field(ge=1)] = 5000  # [P]
    start_date: dt.date
    n_days: Annotated[int, Field(ge=1)] = 730  # [P]
    # [P] `base` in λ_d (step 3, used verbatim): the realised mean is ≈ base × mean weekday
    # weight (0.8 with the defaults) × growth, i.e. ~15 % below base on a calendar-day basis
    orders_per_day_mean: PosFloat = 800
    # SKU master: lognormal dims (L, W, H) and weight
    mu_log_mm: tuple[float, float, float] = (5.3, 4.9, 4.4)  # [P]
    sigma_log_mm: PosFloat = 0.5  # [P]
    mu_log_kg: float = -0.7  # [P]
    sigma_log_kg: PosFloat = 0.9  # [P]
    units_per_case_values: list[Annotated[int, Field(ge=1)]] = [1, 6, 12, 24]  # [P]
    units_per_case_weights: list[NonNeg] = [0.4, 0.3, 0.2, 0.1]  # F1 choice ("weighted")
    pallet_dims_m: tuple[PosFloat, PosFloat, PosFloat] = (1.2, 0.8, 1.2)  # [P]
    n_categories: Annotated[int, Field(ge=1)] = 8  # [P]
    # Popularity
    zipf_s: PosFloat = 1.1  # [P]
    inactive_share: Annotated[float, Field(ge=0, lt=1)] = 0.10  # [P]
    # Order structure: lines = 1 w.p. single_line_prob else 1 + Poisson(extra_lines_mean)
    single_line_prob: Share = 0.55  # [P]
    extra_lines_mean: NonNeg = 2.2  # [P]
    units_per_line_extra_mean: NonNeg = 0.4  # [P] B2C units/line = 1 + Poisson(.)
    cases_per_line_extra_mean: NonNeg = 1.0  # F1 choice: B2B units = case × (1 + Poisson(.))
    channel_shares: dict[str, NonNeg] = {"B2C": 1.0}  # F1 choice; "B2B" lines are case multiples
    # Calendar (weekday 0 = Monday, month 0 = January)
    weekday_weights: list[NonNeg] = Field(
        default=[1.15, 1.10, 1.05, 1.00, 0.95, 0.35, 0.0], min_length=7, max_length=7
    )  # [P]
    month_index: list[NonNeg] = Field(
        default=[0.9, 0.85, 0.9, 0.95, 0.95, 0.9, 0.85, 0.75, 0.95, 1.0, 1.4, 1.6],
        min_length=12,
        max_length=12,
    )  # [P] Q4 peak 1.6; mean 1.0, so the month index does not shift the annual mean
    promos: list[Promo] = []
    annual_growth: float = 0.05  # [P]
    # Intraday: hourly weights peak 10-12 h and 14-16 h; the hour before cut-off gets a boost
    hourly_weights: list[NonNeg] = Field(
        default=[
            *(0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.3, 0.6, 1.0, 1.4, 1.8, 1.8),
            *(1.3, 1.2, 1.7, 1.6, 1.0, 0.9, 0.9, 0.9, 0.8, 0.7, 0.5, 0.3),
        ],
        min_length=24,
        max_length=24,
    )  # F1 choice shaped to the [P] description
    cutoff_hour: Annotated[int, Field(ge=0, le=23)] = 15  # [P]
    cutoff_boost: PosFloat = 1.25  # F1 choice: weight × boost on [cutoff−1 h, cutoff)
    # Flows
    returns_rate: Share = 0.04  # [P]
    return_delay_days: tuple[int, int] = (3, 20)  # [P] inclusive
    cancel_rate: Share = 0.01  # [P] share of orders
    days_of_cover: PosFloat = 25  # [P]
    stock_noise_sigma: NonNeg = 0.2  # F1 choice: lognormal noise, mean 1
    receipt_hour: Annotated[int, Field(ge=0, le=23)] = 7  # F1 choice: receipts 07:00-15:00
    defects: DefectCfg = DefectCfg()  # applied by export only when asked (`--defects`)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(self.units_per_case_values) != len(self.units_per_case_weights):
            raise ValueError("units_per_case_values and units_per_case_weights differ in length")
        for name in ("units_per_case_weights", "channel_shares", "hourly_weights"):
            vals = getattr(self, name)
            if sum(vals.values() if isinstance(vals, dict) else vals) <= 0:
                raise ValueError(f"{name}: weights must not all be zero")
        if not 0 <= self.return_delay_days[0] <= self.return_delay_days[1]:
            raise ValueError("return_delay_days must be (min, max) with 0 ≤ min ≤ max")
        if sum(self.weekday_weights) <= 0:
            raise ValueError("weekday_weights must not all be zero")
        return self

    @property
    def end_date(self) -> dt.date:
        return self.start_date + dt.timedelta(days=self.n_days - 1)


def load_synth_profile(path: Path | str) -> SynthProfile:
    """Load a profile YAML; any error raises ConfigError (exit 2)."""
    return load_yaml_model(path, SynthProfile)


def daily_lambda(profile: SynthProfile) -> np.ndarray:
    """F1 step 3: λ_d = base × weekday[d] × month[d] × (1+g)^(d/365) × promo[d], d = day index."""
    dates = np.datetime64(profile.start_date, "D") + np.arange(profile.n_days)
    d = np.arange(profile.n_days)
    weekday = (dates.astype("int64") + 3) % 7  # 1970-01-01 was a Thursday (weekday 3)
    month = dates.astype("datetime64[M]").astype("int64") % 12
    promo = np.ones(profile.n_days)
    for p in profile.promos:
        start = np.datetime64(p.date, "D")
        promo[(dates >= start) & (dates < start + np.timedelta64(p.duration_days, "D"))] *= (
            p.multiplier
        )
    return (
        profile.orders_per_day_mean
        * np.asarray(profile.weekday_weights)[weekday]
        * np.asarray(profile.month_index)[month]
        * (1 + profile.annual_growth) ** (d / 365)
        * promo
    )
