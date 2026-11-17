"""F8b break-even: the labor cost multiplier k at which an automated scenario pays back in
`target_payback` years.

k multiplies the loaded cost of every role (the baseline's too: the client's current operation or
the baseline scenario is costed with the same roles, I73 b), k in [0.3, 3]. F6 does not read costs,
so every k reuses the base sizing and only F7 runs again (`financed`).

The payback of F7 is None when not reached within the horizon T, which is not a function brentq can
follow. The bracketing function is `extended_payback`: the payback when reached, else
`T + (unrecovered cash at T) / (initial investment)`: above T, continuous where the payback reaches
T (the unrecovered cash is then 0) and decreasing in k when the scenario saves labor. A root k* of
`extended_payback - target` found by brentq is accepted only if F7, re-run at k*, gives a payback
within 1e-3 years of the target, which rejects a jump of the payback (a renewal year that turns the
cumulative cash negative again). A target equal to T puts the root on the edge of "reached" (the
cumulative cash at T is zero up to rounding, F7 may say None): k* then moves by 1e-6 to the reached
side. None as well when the bracket has no sign change, when the target is beyond the horizon (a
payback beyond T is not computed, F7) or when the scenario has no baseline (no payback).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import cast

from scipy.optimize import brentq  # pyright: ignore[reportMissingTypeStubs]

from whsizing.errors import ConfigError
from whsizing.finance import metrics
from whsizing.finance.context import MANUAL
from whsizing.scenarios.runner import Evaluated, RunContext
from whsizing.scenarios.sensitivity import (
    Sized,
    as_context,
    financed,
    labor_basis,
    sized_all,
)
from whsizing.schemas import BreakEven, Project

BRACKET = (0.3, 3.0)  # F8: k in [0.3, 3]
TARGET_PAYBACK_YEARS = 5.0  # F8: default target_payback
TOLERANCE_YEARS = 1e-3  # T8.4: the root reproduces the target within 1e-3 years
XTOL = 1e-9  # brentq tolerance on k
EDGE_STEP = 1e-6  # k: step onto the "reached" side when the root sits on the horizon edge


def extended_payback(flows: Sequence[float]) -> float:
    """Payback of the Δcf `flows` (year 0..T), or `T + unrecovered / investment` when not reached
    (see the module docstring). `flows` must not be empty."""
    pay = metrics.payback(flows)
    if pay is not None:
        return pay
    return len(flows) - 1 + (-sum(flows)) / (-flows[0])  # not reached: flows[0] < 0, sum < 0


def solve(
    flows_at: Callable[[float], Sequence[float]],
    target: float,
    bracket: tuple[float, float] = BRACKET,
) -> float | None:
    """The k in `bracket` at which the payback of `flows_at(k)` (Δcf year 0..T, [] = no baseline)
    equals `target` (≤ T), or None (no flows, target beyond T, no sign change, or a root F7 does
    not reproduce)."""
    lo, hi = bracket
    if not flows_at(lo) or not flows_at(hi) or target > len(flows_at(lo)) - 1:
        return None

    def gap(k: float) -> float:
        return extended_payback(flows_at(k)) - target

    if gap(lo) * gap(hi) > 0:
        return None
    k = cast(float, brentq(gap, lo, hi, xtol=XTOL))  # pyright: ignore[reportUnknownVariableType]
    if metrics.payback(flows_at(k)) is None:  # on the edge of "reached" (target = T)
        k -= math.copysign(EDGE_STEP, gap(hi) - gap(lo))  # gap decreases in k: reached = higher k
    pay = metrics.payback(flows_at(k))
    return k if pay is not None and abs(pay - target) <= TOLERANCE_YEARS else None


def _flows_at(
    ctx: RunContext, sized: Mapping[str, Sized], sid: str
) -> Callable[[float], list[float]]:
    """Δcf of scenario `sid` at multiplier k (F7 only; every k computed once per call)."""
    cache: dict[float, dict[str, Evaluated]] = {}

    def at(k: float) -> list[float]:
        if k not in cache:
            cache[k] = financed(ctx, sized, labor_basis(ctx, k))
        return cache[k][sid].finance.delta_cash_flows_typ

    return at


def _automated(ctx: RunContext, sized: Mapping[str, Sized]) -> list[str]:
    """Computed automated scenarios other than the baseline scenario (it has no payback)."""
    sc = ctx.scenarios
    return [
        s.id for s in sc.scenarios if s.family != MANUAL and s.id != sc.baseline and s.id in sized
    ]


def _check_target(target: float) -> None:
    if not target > 0:
        raise ConfigError(f"break-even: target_payback must be > 0 years, got {target}")


def break_even_rows_of(
    ctx: RunContext, sized: Mapping[str, Sized], target_payback: float
) -> list[BreakEven]:
    """One row per automated scenario (file order) from an already sized run."""
    _check_target(target_payback)
    return [
        BreakEven(
            scenario_id=sid,
            target_payback_years=target_payback,
            labor_cost_multiplier=solve(_flows_at(ctx, sized, sid), target_payback),
            bracket=BRACKET,
        )
        for sid in _automated(ctx, sized)
    ]


def break_even_rows(
    project: RunContext | Project, target_payback: float = TARGET_PAYBACK_YEARS
) -> list[BreakEven]:
    """One `BreakEven` row per automated scenario of the run (every family but manual_p2p, the
    baseline scenario excepted, computed only)."""
    ctx = as_context(project)
    return break_even_rows_of(ctx, sized_all(ctx), target_payback)


def breakeven(
    project: RunContext | Project,
    target_payback: float = TARGET_PAYBACK_YEARS,
    scenario_id: str | None = None,
) -> float | None:
    """The labor cost multiplier k in [0.3, 3] at which scenario `scenario_id` pays back in
    `target_payback` years; None when there is no root (see the module docstring). `scenario_id`
    may be left out when the run has a single automated scenario (ConfigError otherwise)."""
    rows = {r.scenario_id: r for r in break_even_rows(project, target_payback)}
    if scenario_id is None and len(rows) == 1:
        (scenario_id,) = rows
    if scenario_id not in rows:
        raise ConfigError(
            f"break-even: name one automated scenario of {sorted(rows)} (scenario_id=), "
            f"got {scenario_id!r}"
        )
    return rows[scenario_id].labor_cost_multiplier
