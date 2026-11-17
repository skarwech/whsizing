"""Comparison, sensitivity, break-even and percentile sweep (F8)."""

from __future__ import annotations

from typing import Literal

from whsizing.schemas.params import FamilyId, Range, StrictModel


class ComparisonRow(StrictModel):
    """One scenario column of the comparison table; numerics are None when not computed."""

    scenario_id: str
    name: str
    family: FamilyId
    status: Literal["computed", "not_computed"] = "computed"
    status_reason: str | None = None
    eligible_line_share: float | None = None
    storage_area_m2: Range | None = None
    total_area_m2: Range | None = None
    fit: bool | None = None
    equipment: dict[str, Range] = {}  # pickers / stations / ports / robots
    fte_design_day: Range | None = None
    core_fte_year1: Range | None = None
    roster: Range | None = None
    capex: Range | None = None
    opex_year1: Range | None = None
    tco: Range | None = None
    npv_vs_baseline: Range | None = None
    payback_years: float | None = None
    cost_per_line: Range | None = None
    n_warnings: int = 0
    n_low_confidence_params: int = 0


class Comparison(StrictModel):
    baseline_id: str | None
    rows: list[ComparisonRow]
    ranking_tco: list[str]  # scenario ids, ascending TCO at typ
    ranking_payback: list[str]  # scenario ids, ascending payback at typ
    overlaps: list[tuple[str, str]] = []  # scenario pairs whose TCO ranges overlap
    confidence_note: str  # "Ranking at typical values; ranges overlap for ..."


class TornadoBar(StrictModel):
    scenario_id: str
    param: str  # labor_cost, picking_productivity, growth_rate, ...
    low_input: float
    high_input: float
    tco_low: float
    tco_high: float
    delta_tco: float  # max |TCO − base TCO|, sort key
    payback_low: float | None
    payback_high: float | None
    fte_low: float
    fte_high: float


class BreakEven(StrictModel):
    scenario_id: str
    target_payback_years: float
    labor_cost_multiplier: float | None  # None when brentq finds no root in the bracket
    bracket: tuple[float, float] = (0.3, 3.0)


class PercentileSweepRow(StrictModel):
    scenario_id: str
    percentile: float
    design_lines: float
    equipment: dict[str, float]  # stations / ports at typ
    fte: float
    capex: float
    tco: float


class Sensitivity(StrictModel):
    """Content of comparison/sensitivity.json."""

    delta: float
    base_tco: dict[str, float]  # scenario id → TCO at typ
    tornado: list[TornadoBar]  # sorted by |delta_tco| descending
    break_even: list[BreakEven] = []
    percentile_sweep: list[PercentileSweepRow] = []
    # one line per variant left out (scenario, parameter, direction, reason), the baseline's
    # included, and per scenario whose payback is None because its baseline is not computed
    skipped: list[str] = []
