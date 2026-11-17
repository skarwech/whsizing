"""F11 step 2: monthly predicted hours per activity from the daily series, catalog values.

`baseline_monthly(inputs)` runs the F6 engine once (typ world, baseline family, labor only) and
sums the daily hours of each calibration activity by month. Hours are linear in 1 / productivity
and in (1 + PF&D) (I38), so every θ is evaluated in closed form, no engine call per iteration:

    direct g :  hours_g(θ) = B_g / m_g × (1 + pfd) / (1 + pfd_basis)
    indirect :  hours(θ)   = share / m_indirect × Σ_g direct hours_g(θ)      (I38)

`B_g` = the engine's hours at the catalog values (after basis and scenario overrides).
Calibration activities (the rows of the F6c table): receiving (+ receipt_check), put_away,
decant, replenishment, picking, packing (S + ML), shipping (parcel + pallet), returns, indirect.
One multiplier per calibration activity scales the standard of each of its members.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import cast

import numpy as np
import polars as pl

from whsizing.calibration.inputs import CalibrationInputs
from whsizing.calibration.models import M_BOUNDS, CatalogTarget
from whsizing.catalog.models import CatalogParam
from whsizing.design.basis import growth_factor
from whsizing.engine import WorldInputs, size_storage, size_throughput, world_inputs
from whsizing.engine.labor import MAIN_ZONE, MANUAL_ZONES, SHARE, ZONE_RATE, daily_hours, labor_days
from whsizing.schemas.trace import Tracer

INDIRECT = "indirect"
GROUP_OF = {
    "receipt_check": "receiving",
    "packing_S": "packing",
    "packing_ML": "packing",
    "shipping_parcel": "shipping",
    "shipping_pallet": "shipping",
}
MIN_SIGMA = 0.05  # floor of the relative prior sigma (a degenerate catalog range)


def group_of(activity: str) -> str:
    """Calibration activity of an engine activity (`labor_standards.yaml` name)."""
    return GROUP_OF.get(activity, activity)


@dataclass(frozen=True)
class Baseline:
    """Monthly hours at the catalog values, by calibration activity (`indirect` included)."""

    months: tuple[str, ...]  # 'yyyy-mm' of the operating days of the daily series
    hours: dict[str, np.ndarray]  # activity -> hours per month
    orders: np.ndarray  # orders per month (driver of client-specific activities)
    coverage: dict[str, float]  # share of the days of each month inside the daily series' range
    targets: dict[str, tuple[CatalogTarget, ...]]  # direct activity -> Params its multiplier scales
    sigma: dict[str, float]  # relative prior sigma of each multiplier (half the catalog range)
    pfd: float  # basis PF&D = prior
    eta: float  # engine.eta_flow = prior
    indirect_share: float
    peak_hour_lines: float  # design peak-hour lines without growth (design / gf)

    @property
    def groups(self) -> tuple[str, ...]:
        return tuple(self.hours)


def baseline_monthly(inputs: CalibrationInputs) -> Baseline:
    """Run F6 once for the baseline scenario (typ world) and aggregate by month."""
    inp = world_inputs(
        inputs.basis,
        inputs.design_day,
        inputs.scenario,
        inputs.catalog,
        inputs.sku,
        "typ",
        Tracer(inputs.scenario.id),
    )
    tp = size_throughput(inp, size_storage(inp))
    days = labor_days(inp, inputs.daily, inputs.lines)
    by_act = daily_hours(inp, tp, days)
    dates = days.frame["date"].dt.strftime("%Y-%m").to_numpy()
    months, inv = np.unique(dates, return_inverse=True)

    def monthly(x: np.ndarray) -> np.ndarray:
        return np.bincount(inv, weights=x, minlength=len(months))

    hours: dict[str, np.ndarray] = {}
    for name, daily in by_act.items():
        g = group_of(name)
        hours[g] = hours.get(g, 0.0) + monthly(daily)
    targets = _targets(inp, [a for a in by_act if a != INDIRECT])
    sigma = {g: _sigma(inp, t) for g, t in targets.items()}
    sigma[INDIRECT] = (M_BOUNDS[1] - M_BOUNDS[0]) / 2  # a constant, no catalog range
    orders = monthly((days.frame["orders_S"] + days.frame["orders_ML"]).to_numpy())
    dd = inputs.design_day
    return Baseline(
        months=tuple(str(m) for m in months),
        hours=hours,
        orders=orders,
        coverage=_coverage(inputs, tuple(str(m) for m in months)),
        targets=targets,
        sigma=sigma,
        pfd=inputs.basis.operations.pfd_allowance,
        eta=inp.v("engine.eta_flow"),
        indirect_share=inp.v(SHARE),
        peak_hour_lines=dd.peak_hour_lines / growth_factor(dd.growth_rate, dd.horizon_years),
    )


def restrict(base: Baseline, months: Sequence[str]) -> Baseline:
    """The baseline on `months` only (each one must be a month of the daily series)."""
    pos = {m: i for i, m in enumerate(base.months)}
    idx = [pos[m] for m in months]
    return replace(
        base,
        months=tuple(months),
        hours={g: h[idx] for g, h in base.hours.items()},
        orders=base.orders[idx],
        coverage={m: base.coverage[m] for m in months},
    )


def predict(
    base: Baseline, m: Mapping[str, float], pfd: float, groups: Sequence[str]
) -> dict[str, np.ndarray]:
    """Monthly hours of `groups` for the multipliers `m` (one per group) and PF&D `pfd`. Indirect
    is the share of the direct groups in `groups` only: the comparison is like with like."""
    k = (1 + pfd) / (1 + base.pfd)
    out = {g: base.hours[g] * k / m[g] for g in groups if g != INDIRECT}
    if INDIRECT in groups:
        direct = sum(out.values(), np.zeros(len(base.months)))
        out[INDIRECT] = base.indirect_share / m[INDIRECT] * direct
    return out


def _targets(inp: WorldInputs, activities: list[str]) -> dict[str, tuple[CatalogTarget, ...]]:
    """Catalog Params each calibration activity's multiplier scales (their value in the run)."""
    family = inp.scenario.family
    zones = (*([MAIN_ZONE[family]] if family in MAIN_ZONE else []), *MANUAL_ZONES)
    out: dict[str, list[CatalogTarget]] = {}
    for a in activities:
        if a == "picking":
            ids = [ZONE_RATE[z] for z in zones]
        else:
            std = inp.catalog.labor.activities[a].standard
            ids = [
                f"labor.{a}"
                if isinstance(std, CatalogParam)
                else str(std).replace("family", family, 1)
            ]
        out.setdefault(group_of(a), []).extend(
            CatalogTarget(param=i, typ_prior=inp.v(i)) for i in ids
        )
    return {g: tuple(t) for g, t in out.items()}


def _sigma(inp: WorldInputs, targets: tuple[CatalogTarget, ...]) -> float:
    """Relative half range of the standards, (max − min) / (2 typ), averaged over the Params."""
    rel = [(p.max - p.min) / (2 * p.typ) for p in (inp.params.param(t.param) for t in targets)]
    return max(float(np.mean(rel)), MIN_SIGMA)


def _coverage(inputs: CalibrationInputs, months: tuple[str, ...]) -> dict[str, float]:
    """Share of each month's calendar days inside [first, last date] of the daily series (I74 e):
    the calendar runs over every date (I2), so a closed first or last day does not count as
    missing; only an extract that starts or ends mid-month does."""
    dates = inputs.daily["date"].cast(pl.Date)
    first, last = cast(date, dates.min()), cast(date, dates.max())
    out: dict[str, float] = {}
    for m in months:
        year, month = int(m[:4]), int(m[5:])
        n = calendar.monthrange(year, month)[1]
        inside = (min(last, date(year, month, n)) - max(first, date(year, month, 1))).days + 1
        out[m] = max(inside, 0) / n
    return out
