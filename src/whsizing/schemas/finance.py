"""FinancialResult (§2.5, F7)."""

from __future__ import annotations

from whsizing.schemas.params import Range, StrictModel


class FinancialResult(StrictModel):
    scenario_id: str
    capex: dict[str, Range]
    capex_total: Range
    opex_by_year: list[dict[str, float]]  # index = year 1..T, item → typ value
    opex_year1: Range
    tco: Range
    npv_vs_baseline: Range | None
    irr_vs_baseline: float | None
    payback_years: float | None  # None = not reached within horizon
    cost_per_line: Range
    cash_flows_typ: list[float]  # year 0..T: the scenario's own flows [−capex, −opex_1..T]
    # F7 additions (additive, optional)
    delta_cash_flows_typ: list[float] = []  # Δcf vs the baseline, year 0..T; [] without one
    notes: list[str] = []  # why a metric is None, degenerate scenario, client baseline scope
