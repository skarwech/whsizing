"""F6c staffing for one world (split from labor.py): heads, shift split, roster, annual series,
core FTE, temp hours (I4, I19, I25, I41), and the LaborResult over the worlds.

Shift split (multi-shift, not in the golden case): shift 1 starts at the inbound window start
(06:00), shifts are consecutive, the hours after the last shift go to the next day's first
shift; outbound activities follow the design weekday's hourly lines lagged by
`labor.outbound_lag_hours` (a fractional lag splits each hour's share between two hours);
inbound activities are flat over the inbound window; indirect follows the direct hours. With
one shift every hour is in it (I19).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from whsizing.engine.inputs import WORLDS, WorldInputs, to_range
from whsizing.errors import ConfigError, WhsizingError
from whsizing.schemas import ActivityLabor, LaborResult, Range, ShiftRow, World

OPS = "data:basis.operations."
PAID = {"paid_hours": f"{OPS}paid_hours_per_person_day", "utilisation": f"{OPS}utilisation"}
SHIFT_CAP = {"hours_per_shift": f"{OPS}hours_per_shift", "utilisation": f"{OPS}utilisation"}
PROFILE = {
    "hourly_lines": "data:design_day.hourly_lines",
    "lag": "param:labor.outbound_lag_hours",
    "window": "data:catalog.labor.profiles.inbound_window",
    "shifts_per_day": f"{OPS}shifts_per_day",
    "hours_per_shift": f"{OPS}hours_per_shift",
}


@dataclass(frozen=True)
class Act:
    """One activity of one world before staffing (built by labor.py)."""

    name: str
    driver: str
    role: str  # finance.labor_cost_eur_h key
    workload: float  # design day
    hours: float  # design day, incl. PF&D
    daily: np.ndarray  # hours per operating day, base year, incl. PF&D
    profile: np.ndarray  # share of the hours per hour of day (24 values, Σ = 1)
    refs: dict[str, str]  # trace inputs of the base-year sum


@dataclass(frozen=True)
class ActivityWorld:
    activity: str
    role: str
    driver: str
    workload: float
    hours: float
    heads: float
    roster: float
    annual_hours: tuple[float, ...]  # years 1..T
    shift_hours: tuple[float, ...]
    shift_heads: tuple[float, ...]


@dataclass(frozen=True)
class LaborWorld:
    activities: tuple[ActivityWorld, ...]
    total_hours: float
    total_heads: float
    roster: float
    annual_hours: tuple[float, ...]
    core_fte: tuple[float, ...]
    temp_hours: tuple[float, ...]
    p50_day_hours: float
    core_heads_day: float
    shift_windows: tuple[tuple[float, float], ...]  # (start_hour, end_hour) per shift


def profiles(inp: WorldInputs) -> tuple[np.ndarray, np.ndarray]:
    """Share of the hours per hour of day: outbound = hourly lines lagged (flat when no line),
    inbound = flat over the hours whose middle lies in the inbound window."""
    hourly = np.asarray(inp.design_day.hourly_lines, dtype=float)
    if hourly.shape != (24,) or not (np.isfinite(hourly) & (hourly >= 0)).all():
        raise WhsizingError("labor: design_day.hourly_lines must be 24 finite values ≥ 0")
    out = hourly / hourly.sum() if hourly.sum() > 0 else np.full(24, 1 / 24)
    lag = inp.v("labor.outbound_lag_hours")
    n = int(np.floor(lag))  # lag n + f: hour h gets (1 − f) of hour h − n and f of h − n − 1
    out = (1 - (lag - n)) * np.roll(out, n) + (lag - n) * np.roll(out, n + 1)
    # ponytail: hour resolution; a window edge inside an hour rounds (the hour's middle decides)
    start, end = (hour(x) for x in inp.catalog.labor.profiles.inbound_window)
    inside = (np.arange(24) + 0.5 - start) % 24 < ((end - start) % 24 or 24)
    if not inside.any():
        raise ConfigError("labor_standards.yaml: profiles.inbound_window covers no full hour")
    return out, inside / inside.sum()


def shifts(inp: WorldInputs) -> tuple[np.ndarray, tuple[tuple[float, float], ...]]:
    """Shift index (0-based) of each hour of day, and the (start, end) hour of each shift, traced
    as `labor.shift<s>.start_hour` / `end_hour`; end = start + hours_per_shift, so a shift
    ending at midnight ends at 24.0 and one crossing it ends after 24 (16 → 26 = 02:00)."""
    ops = inp.basis.operations
    n, length = ops.shifts_per_day, ops.hours_per_shift
    if n * length > 24:
        raise ConfigError(f"operations: {n} shifts × {length} h exceed 24 h")
    start = hour(inp.catalog.labor.profiles.inbound_window[0])
    idx = ((np.arange(24) + 0.5 - start) % 24 // length).astype(int)
    refs = {"window": PROFILE["window"], "hours_per_shift": f"{OPS}hours_per_shift"}
    windows: list[tuple[float, float]] = []
    for s in range(1, n + 1):
        w0 = inp.record(
            f"labor.shift{s}.start_hour", f"Start of shift {s}", (start + (s - 1) * length) % 24,
            "h", "(inbound_window start + (s − 1) × hours_per_shift) mod 24", refs,
        )  # fmt: skip
        w1 = inp.record(
            f"labor.shift{s}.end_hour", f"End of shift {s}", w0 + length, "h",
            "start_hour + hours_per_shift (> 24: the next day)",
            {"start_hour": inp.tid(f"labor.shift{s}.start_hour"), **refs},
        )  # fmt: skip
        windows.append((w0, w1))
    return np.where(idx < n, idx, 0), tuple(windows)


def staff(inp: WorldInputs, a: Act, shift_of_hour: np.ndarray, n_shifts: int) -> ActivityWorld:
    """Design-day heads, hours and heads per shift (floor 1 when staffed, I19), roster, base
    year and annual hours."""
    ops, key = inp.basis.operations, f"labor.{a.name}"
    paid = ops.paid_hours_per_person_day * ops.utilisation
    hours_ref = {"hours": inp.tid(f"{key}.hours")}
    heads = inp.record(
        f"{key}.heads", f"{a.name} heads (design day)", a.hours / paid, "heads",
        "hours / (paid_hours_per_person_day × utilisation)", hours_ref | PAID,
    )  # fmt: skip
    frac = np.bincount(shift_of_hour, weights=a.profile, minlength=n_shifts)
    cap = ops.hours_per_shift * ops.utilisation
    sh_hours: list[float] = []
    sh_heads: list[float] = []
    for s in range(1, n_shifts + 1):
        h = inp.record(
            f"{key}.shift{s}.hours", f"{a.name} hours in shift {s}", a.hours * float(frac[s - 1]),
            "h", "hours × share of the hour-of-day profile in the shift", hours_ref | PROFILE,
        )  # fmt: skip
        n = inp.record(
            f"{key}.shift{s}.heads", f"{a.name} heads in shift {s}",
            max(1.0, h / cap) if h > 0 else 0.0, "heads",
            "max(1, hours_shift / (hours_per_shift × utilisation)) if staffed, else 0",
            {"hours": inp.tid(f"{key}.shift{s}.hours")} | SHIFT_CAP,
        )  # fmt: skip
        sh_hours.append(h)
        sh_heads.append(n)
    by_shift = {f"shift{s}": inp.tid(f"{key}.shift{s}.heads") for s in range(1, n_shifts + 1)}
    roster = inp.record(
        f"{key}.roster", f"{a.name} roster", sum(sh_heads) * (1 + ops.absenteeism), "heads",
        "Σ_shift heads_shift × (1 + absenteeism)",
        by_shift | {"absenteeism": f"{OPS}absenteeism"},
    )  # fmt: skip
    base = inp.record(
        f"{key}.base_hours", f"{a.name} hours over the operating days (base year)",
        float(a.daily.sum()), "h", "Σ_operating days workload_d / productivity × (1 + pfd)",
        a.refs,
    )  # fmt: skip
    annual = years(inp, f"{key}.annual_hours", base, f"{key}.base_hours", len(a.daily))
    return ActivityWorld(
        a.name, a.role, a.driver, a.workload, a.hours, heads, roster, annual,
        tuple(sh_hours), tuple(sh_heads),
    )  # fmt: skip


def years(inp: WorldInputs, key: str, base: float, base_key: str, n_op: int) -> tuple[float, ...]:
    """I4, I41: base × operating_days_per_year / n_op × (1 + g)^t, t = 1..finance horizon."""
    g = inp.basis.projection.growth_rate
    k = inp.basis.operations.operating_days_per_year / n_op
    inputs = {
        "base": inp.tid(base_key),
        "operating_days_per_year": f"{OPS}operating_days_per_year",
        "n_op": inp.tid("labor.operating_days"),
        "growth_rate": "data:basis.projection.growth_rate",
    }
    formula = "base × operating_days_per_year / n_op × (1 + g)^t"
    return tuple(
        inp.record(f"{key}.y{t}", f"{key} year {t}", base * k * (1 + g) ** t, "h", formula, inputs)
        for t in range(1, inp.basis.finance.horizon_years + 1)
    )


def totals(
    inp: WorldInputs,
    acts: list[Act],
    staffed: tuple[ActivityWorld, ...],
    windows: tuple[tuple[float, float], ...],
) -> LaborWorld:
    """Totals, annual hours, core FTE, P50 day, core heads and temp hours (I25)."""
    ops = inp.basis.operations
    names = [a.activity for a in staffed]
    total: dict[str, float] = {}
    for f, unit in (("hours", "h"), ("heads", "heads"), ("roster", "heads")):
        refs = {n: inp.tid(f"labor.{n}.{f}") for n in names}
        value = sum(getattr(a, f) for a in staffed)
        total[f] = inp.record(f"labor.total.{f}", f"Total {f}", value, unit, f"Σ_a {f}", refs)
    annual = tuple(
        inp.record(
            f"labor.annual_hours.y{t}",
            f"Annual hours year {t}",
            sum(a.annual_hours[t - 1] for a in staffed),
            "h",
            "Σ_a annual_hours",
            {n: inp.tid(f"labor.{n}.annual_hours.y{t}") for n in names},
        )
        for t in range(1, inp.basis.finance.horizon_years + 1)
    )
    fte = {"paid": f"{OPS}annual_paid_hours_per_fte", "utilisation": f"{OPS}utilisation"}
    core_fte = tuple(
        inp.record(
            f"labor.core_fte.y{t}",
            f"Core FTE year {t}",
            h / (ops.annual_paid_hours_per_fte * ops.utilisation),
            "FTE",
            "annual_hours / (annual_paid_hours_per_fte × utilisation)",
            {"annual_hours": inp.tid(f"labor.annual_hours.y{t}")} | fte,
        )
        for t, h in enumerate(annual, 1)
    )
    p50, core_heads, temp = _core(inp, acts, names)
    return LaborWorld(
        staffed, total["hours"], total["heads"], total["roster"], annual, core_fte, temp,
        p50, core_heads, windows,
    )  # fmt: skip


def _core(
    inp: WorldInputs, acts: list[Act], names: list[str]
) -> tuple[float, float, tuple[float, ...]]:
    """I25: hours_d = all activities on each operating day, base year; core capacity = P50
    (unrounded heads); temp hours = Σ_d max(0, hours_d − P50), annualised and grown."""
    ops = inp.basis.operations
    day = np.sum([a.daily for a in acts], axis=0)
    base = {n: inp.tid(f"labor.{n}.base_hours") for n in names}
    p50 = inp.record(
        "labor.p50_day_hours", "Hours of the P50 day",
        float(np.percentile(day, inp.v("engine.core_day_percentile"))), "h",
        "percentile(Σ_a hours_d, core_day_percentile)",
        base | {"percentile": "param:engine.core_day_percentile"},
    )  # fmt: skip
    core_heads = inp.record(
        "labor.core_heads_day", "Core heads per day",
        p50 / (ops.paid_hours_per_person_day * ops.utilisation), "heads",
        "p50_day_hours / (paid_hours_per_person_day × utilisation)",
        {"p50": inp.tid("labor.p50_day_hours")} | PAID,
    )  # fmt: skip
    above = inp.record(
        "labor.hours_above_p50", "Hours above the P50 day (base year)",
        float(np.maximum(0.0, day - p50).sum()), "h", "Σ_d max(0, hours_d − p50_day_hours)",
        base | {"p50": inp.tid("labor.p50_day_hours")},
    )  # fmt: skip
    return p50, core_heads, years(inp, "labor.temp_hours", above, "labor.hours_above_p50", len(day))


def labor_result(worlds: Mapping[World, LaborWorld]) -> LaborResult:
    """ADR-002 Ranges over the worlds; the shift table is the typical world's."""
    typ = worlds["typ"]

    def rng(get: Callable[[LaborWorld], float], unit: str) -> Range:
        return to_range({w: get(worlds[w]) for w in WORLDS}, unit)

    def per_year(get: Callable[[LaborWorld], tuple[float, ...]], unit: str) -> list[Range]:
        return [rng(lambda lw, t=t: get(lw)[t], unit) for t in range(len(typ.core_fte))]

    acts = [
        ActivityLabor(
            activity=a.activity,
            role=a.role,
            driver=a.driver,
            workload=a.workload,
            hours=rng(lambda lw, i=i: lw.activities[i].hours, "h"),
            heads=rng(lambda lw, i=i: lw.activities[i].heads, "heads"),
            roster=rng(lambda lw, i=i: lw.activities[i].roster, "heads"),
            annual_hours=per_year(lambda lw, i=i: lw.activities[i].annual_hours, "h"),
        )
        for i, a in enumerate(typ.activities)
    ]
    rows = [
        ShiftRow(
            shift=s + 1,
            start_hour=w0,
            end_hour=w1,
            activity=a.activity,
            hours=a.shift_hours[s],
            heads=a.shift_heads[s],
        )
        for s, (w0, w1) in enumerate(typ.shift_windows)
        for a in typ.activities
    ]
    return LaborResult(
        activities=acts,
        total_hours=rng(lambda lw: lw.total_hours, "h"),
        total_heads=rng(lambda lw: lw.total_heads, "heads"),
        roster=rng(lambda lw: lw.roster, "heads"),
        annual_hours=per_year(lambda lw: lw.annual_hours, "h"),
        core_fte=per_year(lambda lw: lw.core_fte, "FTE"),
        temp_hours=per_year(lambda lw: lw.temp_hours, "h"),
        shifts=rows,
    )


def hour(hhmm: str) -> float:
    """'06:30' → 6.5."""
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60
