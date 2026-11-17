"""DesignBasis and its sub-models (§2.5, Appendix E basis.yaml)."""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import field_validator

from whsizing.schemas.params import StrictModel


class Operations(StrictModel):
    operating_days_per_year: int = 250  # [P]
    shifts_per_day: int = 1
    hours_per_shift: float = 7.0  # [P]
    paid_hours_per_person_day: float = 7.0  # [P]
    annual_paid_hours_per_fte: float = 1607.0  # [VERIFY] French 35 h basis
    utilisation: float = 0.85  # [P] share of paid time on direct work
    absenteeism: float = 0.06  # [P]
    pfd_allowance: float = 0.12  # [P] personal, fatigue, delay


class Service(StrictModel):
    cutoff_time: time
    carrier_departure_time: time
    same_day_share: float = 0.0  # share of lines that must ship the same day
    sla_window_hours: float | None = None  # derived from the two times if None

    @field_validator("cutoff_time", "carrier_departure_time", mode="before")
    @classmethod
    def _no_int_time(cls, v: object) -> object:
        # YAML 1.1 reads an unquoted 15:00 as the integer 900 (base 60); pydantic would
        # then silently turn it into 00:15. Times must be written quoted: "15:00".
        if isinstance(v, int):
            raise ValueError("time must be a quoted 'HH:MM' string (unquoted 15:00 is read as 900)")
        return v


class Projection(StrictModel):
    horizon_years: int = 5
    growth_rate: float = 0.03
    design_percentile: float = 95.0
    peak_stock_factor: float = 1.15  # [P]
    trailing_months: int = 12  # 24 if available


class Flows(StrictModel):
    returns_rate: float = 0.03
    inbound_mode: Literal["receipts", "derived"] = "derived"
    inbound_peak_factor: float | None = None  # None → outbound peak-to-average
    pallets_per_truck: float = 26  # [P]
    truck_dwell_hours: float = 1.0  # [P]
    dock_utilisation: float = 0.7  # [P]
    pallet_order_weight_kg: float = 300  # [P] heavier orders ship as pallets
    pallet_order_cube_m3: float = 0.6  # [P]
    parcel_max_weight_kg: float = 30  # [P]


class Building(StrictModel):
    area_m2: float
    clear_height_m: float
    dock_doors_in: int
    dock_doors_out: int
    floor_load_t_m2: float | None = None
    sprinklered: bool | None = None
    rent_eur_m2_year: float = 60.0  # [P]
    rent_mode: Literal["footprint", "full_building", "none"] = "footprint"


class FinanceBasis(StrictModel):
    discount_rate: float = 0.08  # [P]
    horizon_years: int = 5
    wage_inflation: float = 0.025  # [P]
    energy_inflation: float = 0.03  # [P]
    energy_price_eur_kwh: float = 0.18  # [P]
    labor_cost_eur_h: dict[str, float]  # role → loaded hourly cost (client-provided)
    temp_premium: float = 0.15  # [P] premium on temporary labour hours
    shift_premium: float = 0.0


class Baseline(StrictModel):
    description: str = ""
    actual_fte: dict[str, float] | None = None  # activity → FTE
    actual_hours_month: dict[str, list[float]] | None = None
    equipment: dict[str, int] | None = None


class DesignBasis(StrictModel):
    client: str
    site: str
    currency: Literal["EUR"] = "EUR"
    timezone: str = "Europe/Paris"
    operations: Operations
    service: Service
    projection: Projection
    flows: Flows
    building: Building
    finance: FinanceBasis
    baseline: Baseline = Baseline()
    overrides: dict[str, float] = {}  # param id → value, documented as "client override"
