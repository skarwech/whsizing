"""F8b one-at-a-time sensitivity: a tornado of TCO, payback and FTE per scenario x parameter.

`run_sensitivity(ctx, evaluated)` is the hook of the runner (see `whsizing.scenarios`); it fills
`Sensitivity` with the tornado, the break-even rows (breakeven.py) and the percentile sweep
(sweep.py). `sensitivity_oat(project, params, delta)` is the tornado alone. The spec's `project`
argument is the run's `RunContext`: it holds the loaded project and the profile, SKU and daily
frames already computed, so nothing is ingested again.

Parameters (`PARAMS`, all [P]). For each scenario and parameter, two runs: at the low input
(`1 - delta`) and at the high input (`1 + delta`); a bar records TCO, payback and FTE of each (FTE
= design-day heads, typ world) and `delta_tco = max |TCO - base TCO|`. Every run changes that one
parameter for every scenario of the run, the baseline scenario included (I42: payback is read
against the baseline of the same run). Bars are sorted by `delta_tco` descending, ties in
parameter then scenario order, so the same inputs give the same sensitivity.json bytes. A variant
that raises SizingInfeasibleError is logged, its bars are left out and `Sensitivity.skipped` gets a
line `<scenario> <where>: <reason>` for it (`where` = `base`, `<param> low|high`, `percentile sweep
P<p>`), the baseline's included; for every run whose baseline scenario is not sized, a line
`<scenario> <where>: payback is None, baseline <id> is not computed` per sized scenario explains the
payback None of its bars and of the break-even.

Catalog parameters are varied through `ScenarioDef.overrides`, never `basis.overrides`: scenario
overrides win (S1 sets amr_gtp.station_rate_lines_h), and the value varied is the effective typ.
Sizing is redone per variant (F6, new Tracer); the labor-cost variants and the break-even only
change F7, so they reuse the base sizing and deep-copy its pre-finance Tracer (I73 a).
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from statistics import fmean
from typing import NamedTuple

from whsizing.catalog import ParamSet
from whsizing.design import select_design_day
from whsizing.engine import size_scenario
from whsizing.errors import ConfigError, SizingInfeasibleError
from whsizing.finance import compute_finance
from whsizing.finance.context import MANUAL
from whsizing.finance.opex import role_costs
from whsizing.logging import get_logger
from whsizing.scenarios.load import CLIENT_CURRENT
from whsizing.scenarios.runner import Evaluated, RunContext
from whsizing.schemas import (
    DesignBasis,
    DesignDay,
    Param,
    Project,
    ScenarioDef,
    ScenarioResult,
    Sensitivity,
    TornadoBar,
)
from whsizing.schemas.trace import Tracer

PERCENTILE_LOW, PERCENTILE_HIGH = 90.0, 98.0  # [P] F8: design percentile 90 / 95 / 98
EQUIPMENT_COSTS = (
    frozenset(  # unit costs of the F7 `equipment` item (+ manual carts, forklifts: I34)
        {
            "per_robot_eur",
            "per_port_eur",
            "charging_per_robot_eur",
            "per_station_eur",
            "per_cart_eur",
            "per_forklift_eur",
        }
    )
)
PICK_RATES = frozenset(
    {
        "pick_rate_shelving_lines_h",
        "pick_rate_pallet_lines_h",
        "station_rate_lines_h",
        "port_rate_lines_h",
    }
)

PARAMS: dict[str, str] = {
    "labor_cost": (
        "loaded hourly cost of every role (basis.finance.labor_cost_eur_h, the catalog default "
        "for a role the client left out) x (1 -/+ delta); input = the multiplier; F7 only"
    ),
    "picking_productivity": (
        "pick, station and port rates (manual_p2p.pick_rate_shelving_lines_h, "
        "manual_p2p.pick_rate_pallet_lines_h, amr_gtp.station_rate_lines_h, "
        "cube_asrs.port_rate_lines_h) of the scenario's family and of manual_p2p (overflow zone), "
        "each effective typ x (1 -/+ delta); input = the multiplier"
    ),
    "growth_rate": (
        "basis.projection.growth_rate x (1 -/+ delta), design day (F4) and volumes re-run; "
        "input = the annual rate"
    ),
    "equipment_capex": (
        "the unit costs of the equipment item (per_robot_eur, per_port_eur, "
        "charging_per_robot_eur, per_station_eur) of the scenario's family and of manual_p2p "
        "(per_cart_eur, per_forklift_eur: S0's equipment, S2's overflow carts and forklifts, "
        "both maintained, I34), "
        "each effective typ x (1 -/+ delta); storage, controls, building works and the shares stay "
        "as they are, integration, contingency and maintenance follow the equipment item; "
        "input = the multiplier"
    ),
    "design_percentile": (
        "basis.projection.design_percentile at 90 (low) and 98 (high), the F8 list 90/95/98; "
        "delta does not apply; design day (F4) re-run; input = the percentile"
    ),
    "fill_factor": (
        "every *fill_factor of the scenario's family and of manual_p2p, each effective typ x "
        "(1 -/+ delta) limited to its catalog [min, max] (a fraction); input = mean of the "
        "fractions applied"
    ),
    "oee": (
        "oee of the scenario's family and engine.pack_station_oee, each effective typ x "
        "(1 -/+ delta) limited to its catalog [min, max] (a fraction); input = mean of the "
        "fractions applied"
    ),
}


class Sized(NamedTuple):
    """One scenario sized once: its F6 result and the Tracer before any finance node (I73 a)."""

    result: ScenarioResult
    tracer: Tracer


class Setting(NamedTuple):
    """What one run changes: basis, design day, scenario definitions, and the value each scenario
    reports as `low_input` / `high_input`; `resize` False when only F7 changes."""

    basis: DesignBasis
    design_day: DesignDay
    scenarios: Sequence[ScenarioDef]
    inputs: Mapping[str, float]
    resize: bool


def as_context(project: RunContext | Project) -> RunContext:
    """F8b works on a run's `RunContext` (the hook's `ctx`); a Project needs a run first."""
    if not isinstance(project, RunContext):
        raise ConfigError(
            "sensitivity, break-even and percentile sweep take the RunContext of a run: call "
            "run_scenarios(project), whose RunOutput.sensitivity holds them (options.sensitivity)"
        )
    return project


# ------------------------------------------------------------------ sizing and finance of a variant
def sized_with_reasons(
    ctx: RunContext,
    basis: DesignBasis | None = None,
    design_day: DesignDay | None = None,
    scenarios: Sequence[ScenarioDef] | None = None,
) -> tuple[dict[str, Sized], dict[str, str]]:
    """F6 for every scenario (in file order) under `basis` / `design_day` (default: the run's);
    a scenario raising SizingInfeasibleError is logged and left out, with its reason in the second
    dict."""
    basis, design_day = basis or ctx.basis, design_day or ctx.design_day
    out: dict[str, Sized] = {}
    reasons: dict[str, str] = {}
    for s in ctx.scenarios.scenarios if scenarios is None else scenarios:
        tracer = Tracer(s.id)
        try:
            result = size_scenario(
                ctx.profile, basis, design_day, s, ctx.catalog, ctx.sku, ctx.tables.daily, tracer,
                lines=ctx.tables.lines,
            )  # fmt: skip
        except SizingInfeasibleError as e:
            reasons[s.id] = f"SizingInfeasibleError: {e}"
            get_logger().warning("sensitivity_not_computed", scenario=s.id, reason=reasons[s.id])
            continue
        out[s.id] = Sized(result, tracer)
    return out, reasons


def sized_all(
    ctx: RunContext,
    basis: DesignBasis | None = None,
    design_day: DesignDay | None = None,
    scenarios: Sequence[ScenarioDef] | None = None,
) -> dict[str, Sized]:
    """`sized_with_reasons` without the reasons."""
    return sized_with_reasons(ctx, basis, design_day, scenarios)[0]


def reason_lines(where: str, reasons: Mapping[str, str]) -> list[str]:
    """`Sensitivity.skipped` lines for the scenarios left out of the run `where`."""
    return [f"{sid} {where}: {reason}" for sid, reason in reasons.items()]


def payback_lines(ctx: RunContext, where: str, sized: Mapping[str, Sized]) -> list[str]:
    """`Sensitivity.skipped` lines for a run whose baseline scenario is not sized: every payback
    of that run is None (F7 has nothing to compare with), one line per sized scenario."""
    base = ctx.scenarios.baseline
    if base == CLIENT_CURRENT or base in sized:
        return []
    return [f"{sid} {where}: payback is None, baseline {base} is not computed" for sid in sized]


def financed(
    ctx: RunContext, sized: Mapping[str, Sized], basis: DesignBasis | None = None
) -> dict[str, Evaluated]:
    """F7 for every sized scenario under `basis`, the baseline first (I42), as the runner does:
    a baseline id finances the others against it, `client_current` against `basis.baseline`, a
    baseline that is not sized leaves the others without one. Each scenario gets a deep copy of its
    pre-finance Tracer (I73 a), so `sized` can be financed again. Result in scenario file order."""
    basis = basis or ctx.basis
    sc = ctx.scenarios
    client = sc.baseline == CLIENT_CURRENT
    done: dict[str, Evaluated] = {}
    base: Evaluated | None = None
    for s in sorted(sc.scenarios, key=lambda s: s.id != sc.baseline):  # stable: baseline first
        if s.id not in sized:
            continue
        result, tracer = sized[s.id].result, copy.deepcopy(sized[s.id].tracer)
        against = None if s.id == sc.baseline else base
        fin = compute_finance(
            result, basis, ctx.catalog, against.result if against else None,
            daily=ctx.tables.daily, tracer=tracer,
            baseline_tracer=against.tracer if against else None, client_baseline=client,
        )  # fmt: skip
        done[s.id] = Evaluated(result, fin, tracer)
        base = done[s.id] if s.id == sc.baseline else base
    return {s.id: done[s.id] for s in sc.scenarios if s.id in done}


def labor_basis(ctx: RunContext, k: float) -> DesignBasis:
    """`basis` with the loaded cost of every role (client's, else catalog default) times `k`."""
    costs = {role: cost * k for role, cost in role_costs(ctx.catalog, ctx.basis).items()}
    finance = ctx.basis.finance.model_copy(update={"labor_cost_eur_h": costs})
    return ctx.basis.model_copy(update={"finance": finance})


def with_projection(basis: DesignBasis, **update: float) -> DesignBasis:
    """`basis` with the given `projection` fields replaced."""
    return basis.model_copy(update={"projection": basis.projection.model_copy(update=update)})


def redesign(ctx: RunContext, basis: DesignBasis) -> DesignDay:
    """F4 again on the run's frames (the profile and the daily series are reused)."""
    return select_design_day(ctx.profile, basis, ctx.tables.daily, sku=ctx.sku, catalog=ctx.catalog)


# ------------------------------------------------------------------ one variant
Selector = Callable[[str, Param, str], bool]  # (param id, Param, scenario family) -> varied?


def _own(pid: str, family: str) -> bool:
    """The parameter belongs to the scenario's family or to manual_p2p (overflow zone)."""
    return pid.split(".", 1)[0] in (family, MANUAL)


def _picking(pid: str, _p: Param, family: str) -> bool:
    return _own(pid, family) and pid.rsplit(".", 1)[1] in PICK_RATES


def _capex(pid: str, _p: Param, family: str) -> bool:
    return _own(pid, family) and pid.rsplit(".", 1)[1] in EQUIPMENT_COSTS


def _fill(pid: str, _p: Param, family: str) -> bool:
    return _own(pid, family) and pid.endswith("fill_factor")


def _oee(pid: str, _p: Param, family: str) -> bool:
    return pid.split(".", 1)[0] in (family, "engine") and pid.endswith("oee")


# parameter -> (selector, bounded): bounded values are fractions, kept inside the catalog range
CATALOG_PARAMS: dict[str, tuple[Selector, bool]] = {
    "picking_productivity": (_picking, False),
    "equipment_capex": (_capex, False),
    "fill_factor": (_fill, True),
    "oee": (_oee, True),
}


def _catalog_setting(ctx: RunContext, name: str, f: float) -> Setting:
    select, bounded = CATALOG_PARAMS[name]
    scenarios: list[ScenarioDef] = []
    inputs: dict[str, float] = {}
    for s in ctx.scenarios.scenarios:
        ps = ParamSet(ctx.catalog, ctx.basis.overrides, s.overrides)
        applied: dict[str, float] = {}
        for pid, p in ps.params.items():
            if select(pid, p, s.family):
                value = ps.value(pid) * f
                applied[pid] = min(max(value, p.min), p.max) if bounded else value
        scenarios.append(s.model_copy(update={"overrides": {**s.overrides, **applied}}))
        inputs[s.id] = fmean(applied.values()) if bounded and applied else f
    return Setting(ctx.basis, ctx.design_day, scenarios, inputs, resize=True)


def make_setting(ctx: RunContext, name: str, sign: int, delta: float) -> Setting:
    """The run of parameter `name` at the low (`sign` = -1) or high (+1) input."""
    f = 1 + sign * delta
    scenarios = ctx.scenarios.scenarios
    if name == "labor_cost":
        same = dict.fromkeys((s.id for s in scenarios), f)
        return Setting(labor_basis(ctx, f), ctx.design_day, scenarios, same, resize=False)
    if name in ("growth_rate", "design_percentile"):
        if name == "growth_rate":
            value = ctx.basis.projection.growth_rate * f
        else:
            value = PERCENTILE_HIGH if sign > 0 else PERCENTILE_LOW
        basis = with_projection(ctx.basis, **{name: value})
        same = dict.fromkeys((s.id for s in scenarios), value)
        return Setting(basis, redesign(ctx, basis), scenarios, same, resize=True)
    return _catalog_setting(ctx, name, f)


def _run(
    ctx: RunContext, st: Setting, base: Mapping[str, Sized], where: str
) -> tuple[dict[str, Evaluated], list[str]]:
    """The variant `st` financed, and its `Sensitivity.skipped` lines (`where` names the run)."""
    sized: Mapping[str, Sized] = base
    reasons: Mapping[str, str] = {}
    if st.resize:
        sized, reasons = sized_with_reasons(ctx, st.basis, st.design_day, st.scenarios)
    lines = reason_lines(where, reasons) + payback_lines(ctx, where, sized)
    return financed(ctx, sized, st.basis), lines


# ------------------------------------------------------------------ tornado
def _check_delta(delta: float) -> None:
    if not 0 <= delta < 1:
        raise ConfigError(f"sensitivity delta must be in [0, 1): got {delta}")


def _names(params: Sequence[str] | None) -> tuple[str, ...]:
    if params is None:
        return tuple(PARAMS)
    if not params:
        raise ConfigError(f"sensitivity: no parameter given; known: {sorted(PARAMS)}")
    unknown = sorted(set(params) - set(PARAMS))
    if unknown:
        raise ConfigError(f"sensitivity: unknown parameter(s) {unknown}; known: {sorted(PARAMS)}")
    return tuple(dict.fromkeys(params))


def _bars(
    ctx: RunContext,
    base: Mapping[str, Evaluated],
    sized: Mapping[str, Sized],
    names: Sequence[str],
    delta: float,
) -> tuple[list[TornadoBar], list[str]]:
    bars: list[TornadoBar] = []
    skipped: list[str] = []
    for name in names:
        lo_set, hi_set = make_setting(ctx, name, -1, delta), make_setting(ctx, name, 1, delta)
        lo, lo_lines = _run(ctx, lo_set, sized, f"{name} low")
        hi, hi_lines = _run(ctx, hi_set, sized, f"{name} high")
        skipped += lo_lines + hi_lines
        for sid, b in base.items():
            if sid not in lo or sid not in hi:
                get_logger().warning("sensitivity_bar_skipped", scenario=sid, param=name)
                continue
            tco0, low, high = b.finance.tco.typ, lo[sid], hi[sid]
            t_low, t_high = low.finance.tco.typ, high.finance.tco.typ
            bars.append(
                TornadoBar(
                    scenario_id=sid,
                    param=name,
                    low_input=lo_set.inputs[sid],
                    high_input=hi_set.inputs[sid],
                    tco_low=t_low,
                    tco_high=t_high,
                    delta_tco=max(abs(t_low - tco0), abs(t_high - tco0)),
                    payback_low=low.finance.payback_years,
                    payback_high=high.finance.payback_years,
                    fte_low=low.result.labor.total_heads.typ,
                    fte_high=high.result.labor.total_heads.typ,
                )
            )
    # stable: ties keep parameter, scenario order
    return sorted(bars, key=lambda b: -b.delta_tco), skipped


def _tornado(
    ctx: RunContext,
    base: Mapping[str, Evaluated],
    sized: Mapping[str, Sized],
    reasons: Mapping[str, str],
    names: Sequence[str],
    delta: float,
) -> Sensitivity:
    """Tornado of `base` (the run's own results, sized as `sized` / not as `reasons`)."""
    bars, skipped = _bars(ctx, base, sized, names, delta)
    return Sensitivity(
        delta=delta,
        base_tco={sid: ev.finance.tco.typ for sid, ev in base.items()},
        tornado=bars,
        skipped=[*reason_lines("base", reasons), *payback_lines(ctx, "base", sized), *skipped],
    )


def sensitivity_oat(
    project: RunContext | Project, params: Sequence[str] | None = None, delta: float = 0.2
) -> Sensitivity:
    """The tornado alone (`break_even` and `percentile_sweep` empty): `params` = names of `PARAMS`
    (default all), `delta` in [0, 1). Base values are the run's own: sized again once, financed
    as the runner does. ConfigError for an unknown parameter or a `delta` outside [0, 1)."""
    ctx = as_context(project)
    _check_delta(delta)
    names = _names(params)
    sized, reasons = sized_with_reasons(ctx)
    return _tornado(ctx, financed(ctx, sized), sized, reasons, names, delta)


def run_sensitivity(ctx: RunContext, evaluated: Mapping[str, Evaluated]) -> Sensitivity:
    """The runner's hook: tornado (`ctx.project.options.delta`) of the run's own results
    `evaluated`, break-even rows at the default target payback and the default percentile sweep."""
    from whsizing.scenarios.breakeven import TARGET_PAYBACK_YEARS, break_even_rows_of
    from whsizing.scenarios.sweep import PERCENTILES, sweep_rows

    delta = ctx.project.options.delta
    _check_delta(delta)
    sized, reasons = sized_with_reasons(ctx)
    tornado = _tornado(ctx, evaluated, sized, reasons, tuple(PARAMS), delta)
    rows, sweep_lines = sweep_rows(ctx, PERCENTILES)
    return tornado.model_copy(
        update={
            "break_even": break_even_rows_of(ctx, sized, TARGET_PAYBACK_YEARS),
            "percentile_sweep": rows,
            "skipped": [*tornado.skipped, *sweep_lines],
        }
    )
