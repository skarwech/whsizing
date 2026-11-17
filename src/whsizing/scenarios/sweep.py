"""F8b percentile sweep: the service-level trade-off, one row per scenario and design percentile.

For each percentile F4 is run again on the run's frames (the design day moves with the percentile),
then F6 and F7 for every scenario, the baseline first as in the runner: design lines, equipment
(pickers / stations / ports / robots at typ), FTE (design-day heads, typ), capex and TCO (typ).
Rows are in scenario file order, then in the order of `percentiles`.
"""

from __future__ import annotations

from collections.abc import Sequence

from whsizing.errors import ConfigError
from whsizing.scenarios.compare import EQUIPMENT_KEYS
from whsizing.scenarios.runner import RunContext
from whsizing.scenarios.sensitivity import (
    as_context,
    financed,
    reason_lines,
    redesign,
    sized_with_reasons,
    with_projection,
)
from whsizing.schemas import PercentileSweepRow, Project

PERCENTILES = (80.0, 90.0, 95.0, 98.0)  # F8


def percentile_sweep(
    project: RunContext | Project, percentiles: Sequence[float] = PERCENTILES
) -> list[PercentileSweepRow]:
    """Rows for every computed scenario at each of `percentiles` (each in (0, 100]; ConfigError
    otherwise). A scenario that raises SizingInfeasibleError at a percentile has no row there."""
    return sweep_rows(as_context(project), percentiles)[0]


def sweep_rows(
    ctx: RunContext, percentiles: Sequence[float]
) -> tuple[list[PercentileSweepRow], list[str]]:
    """`percentile_sweep` and the `Sensitivity.skipped` lines of the rows it could not make."""
    bad = [p for p in percentiles if not 0 < p <= 100]
    if not percentiles or bad:
        raise ConfigError(
            f"percentile sweep: percentiles must be in (0, 100], got {list(percentiles)}"
        )
    rows: dict[str, list[PercentileSweepRow]] = {s.id: [] for s in ctx.scenarios.scenarios}
    skipped: list[str] = []
    for p in percentiles:
        basis = with_projection(ctx.basis, design_percentile=p)
        design_day = redesign(ctx, basis)
        sized, reasons = sized_with_reasons(ctx, basis, design_day)
        skipped += reason_lines(f"percentile sweep P{p:g}", reasons)
        for sid, ev in financed(ctx, sized, basis).items():
            equipment = {
                k: ev.result.equipment[k].typ for k in EQUIPMENT_KEYS if k in ev.result.equipment
            }
            rows[sid].append(
                PercentileSweepRow(
                    scenario_id=sid,
                    percentile=p,
                    design_lines=design_day.lines,
                    equipment=equipment,
                    fte=ev.result.labor.total_heads.typ,
                    capex=ev.finance.capex_total.typ,
                    tco=ev.finance.tco.typ,
                )
            )
    return [row for scenario_rows in rows.values() for row in scenario_rows], skipped
