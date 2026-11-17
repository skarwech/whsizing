"""F7 `compute_finance` and `write_finance`: costs in the three worlds (ADR-002), metrics, traces.

Per world w in WORLDS: capex_items + opex_years (F6 quantities of w read from the tracer × cost
Params of w), then TCO, Δcf, NPV, cost per line; the baseline is costed in the same world.
Ranges = (min over the worlds, typ, max over the worlds) via `whsizing.engine.to_range`.
IRR and payback are the typical world's (no Range in FinancialResult).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

import polars as pl

from whsizing.catalog import Catalog, ParamSet
from whsizing.engine import WORLDS, to_range
from whsizing.engine.size import SCENARIO_ID
from whsizing.errors import ConfigError, WhsizingError
from whsizing.finance import metrics
from whsizing.finance.baseline import (
    CLIENT_NOTE,
    Base,
    client_base,
    client_hours,
    trace_scenario_base,
)
from whsizing.finance.capex import capex_items
from whsizing.finance.context import Ctx
from whsizing.finance.opex import FIN, annual_total, opex_years, role_costs
from whsizing.schemas import (
    DesignBasis,
    FinancialResult,
    LaborResult,
    Range,
    ScenarioResult,
    World,
)
from whsizing.schemas.trace import Tracer

DEGENERATE_NOTE = (
    "I48: no eligible line, costed with the manual formulas (WMS adaptation, manual shares, "
    "software and maintenance), overflow item 0"
)


class Costs(NamedTuple):
    """One scenario in one world: capex items (+ total) and opex items (+ total) per year."""

    capex: dict[str, float]
    opex: list[dict[str, float]]


class WorldMetrics(NamedTuple):
    tco: float
    cost_per_line: float
    cash_flows: list[float]  # [−capex, −opex_1..T]
    delta: list[float] | None  # Δcf_0..T vs the baseline, None without one
    npv: float | None


def compute_finance(
    result: ScenarioResult,
    basis: DesignBasis,
    catalog: Catalog,
    baseline: ScenarioResult | None,
    labor_series: LaborResult | None = None,
    *,
    daily: pl.DataFrame,
    tracer: Tracer,
    baseline_tracer: Tracer | None = None,
    client_baseline: bool = True,
) -> FinancialResult:
    """F7 for one scenario; see `whsizing.finance` for the arguments. Records every finance
    quantity in `tracer` (export the trace after this call).

    F8 call order (I73 a): `size_scenario` → deep copy of the pre-finance tracer per variant
    (sensitivity runs; a second call on the same tracer raises) → `compute_finance` →
    `write_finance` → `write_scenario(result, tracer, dir)`. The baseline scenario goes through
    the same steps with `baseline=None, client_baseline=False`; a scenario with a computed
    baseline also needs the baseline's tracer (`baseline_tracer`)."""
    years = basis.finance.horizon_years
    labor = _labor_of(result, labor_series)
    _check(result, basis, labor, years)
    params = ParamSet(catalog, basis.overrides, result.scenario.overrides)
    costs_h = role_costs(catalog, basis)
    ctxs: dict[World, Ctx] = {
        w: Ctx(result, basis, params, w, tracer, tracer, costs_h) for w in WORLDS
    }
    costs: dict[World, Costs] = {w: _costs(c, labor, daily, years) for w, c in ctxs.items()}
    lines = {
        w: annual_total(c, daily, "lines", "finance.annual_lines_y1", 1) for w, c in ctxs.items()
    }
    notes = [DEGENERATE_NOTE] if ctxs["typ"].fam != result.scenario.family else []
    base = _baseline(
        result, basis, catalog, baseline, baseline_tracer, ctxs, costs, daily, client_baseline
    )
    if base is None and baseline is None:
        notes.append(_no_baseline_note(client_baseline))
    if base is not None and baseline is None:
        notes.append(CLIENT_NOTE)
    wm: dict[World, WorldMetrics] = {
        w: _metrics(ctxs[w], costs[w], lines[w], base[w] if base else None) for w in WORLDS
    }
    typ_delta = wm["typ"].delta
    irr, why = metrics.irr(typ_delta) if typ_delta else (None, None)
    pay = metrics.payback(typ_delta) if typ_delta else None
    notes += [why] if why else []
    _trace_typ(ctxs["typ"], irr, pay, typ_delta)
    return _assemble(result, costs, wm, irr, pay, notes)


def write_finance(fin: FinancialResult, project_dir: Path | str) -> Path:
    """Write `<project_dir>/scenarios/<id>/finance.json` (pydantic JSON, fixed field order: the
    same result gives the same bytes); returns the file. The F6 trace of the scenario holds the
    finance nodes only after `compute_finance`: write it (`write_scenario`) after this."""
    if not SCENARIO_ID.fullmatch(fin.scenario_id):
        raise ConfigError(f"scenario id {fin.scenario_id!r}: use letters, digits, '_' or '-' only")
    out = Path(project_dir) / "scenarios" / fin.scenario_id
    out.mkdir(parents=True, exist_ok=True)
    path = out / "finance.json"
    path.write_text(fin.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _labor_of(result: ScenarioResult, labor_series: LaborResult | None) -> LaborResult:
    """The F6 labor result. The hours of each world are read from the F6 trace of `result`, so a
    `labor_series` that is not `result.labor` would be silently ignored: it is refused."""
    if labor_series is not None and labor_series != result.labor:
        raise ConfigError(
            "finance: labor_series differs from result.labor; the hours of each world are read "
            "from the F6 trace of the result: size the scenario again instead"
        )
    return result.labor


def _check(result: ScenarioResult, basis: DesignBasis, labor: LaborResult, years: int) -> None:
    if result.status != "computed":
        raise WhsizingError(f"finance: scenario {result.scenario.id} is {result.status}")
    if years < 1 or basis.finance.discount_rate <= -1:
        raise ConfigError("finance: horizon_years must be ≥ 1 and discount_rate > −1")
    if len(labor.temp_hours) != years:
        raise ConfigError(
            f"finance.horizon_years = {years} but the F6 labor series has {len(labor.temp_hours)} "
            "years: size the scenario with the same basis"
        )


def _costs(c: Ctx, labor: LaborResult, daily: pl.DataFrame, years: int) -> Costs:
    cap = capex_items(c)
    activities = [(a.activity, a.role) for a in labor.activities]
    return Costs(cap.items, opex_years(c, cap, activities, daily, years))


def _baseline(
    result: ScenarioResult,
    basis: DesignBasis,
    catalog: Catalog,
    baseline: ScenarioResult | None,
    baseline_tracer: Tracer | None,
    ctxs: Mapping[World, Ctx],
    costs: Mapping[World, Costs],
    daily: pl.DataFrame,
    client: bool,
) -> dict[World, Base] | None:
    """Baseline totals per world, or None (no baseline). A scenario baseline (I42) is costed in
    each world with its own Params and F6 trace; None = the client's current operation."""
    if baseline is None:
        hours = client_hours(basis, catalog) if client else None
        if hours is None:
            return None
        return client_base(hours, catalog, ctxs, {w: c.opex for w, c in costs.items()})
    if baseline_tracer is None:
        raise ConfigError("finance: a baseline ScenarioResult needs its Tracer (baseline_tracer=)")
    if baseline.scenario.id == result.scenario.id:
        raise ConfigError(f"finance: scenario {baseline.scenario.id} cannot be its own baseline")
    _check(baseline, basis, baseline.labor, basis.finance.horizon_years)
    bparams = ParamSet(catalog, basis.overrides, baseline.scenario.overrides)
    scratch = Tracer(baseline.scenario.id)  # the baseline's own finance nodes are not kept here
    base: dict[World, Base] = {}
    for w in WORLDS:
        bc = Ctx(baseline, basis, bparams, w, baseline_tracer, scratch, ctxs[w].role_costs)
        bcost = _costs(bc, baseline.labor, daily, basis.finance.horizon_years)
        base[w] = Base(bcost.capex["total"], [row["total"] for row in bcost.opex])
    trace_scenario_base(baseline.scenario.id, ctxs, base)
    return base


def _no_baseline_note(client_baseline: bool) -> str:
    why = "no baseline scenario and no actual hours or FTE in basis.baseline"
    if not client_baseline:
        why = "no baseline scenario (client baseline switched off)"
    return f"NPV, IRR and payback are None: {why}; absolute TCO only"


def _metrics(c: Ctx, cs: Costs, lines: float, base: Base | None) -> WorldMetrics:
    """TCO, cost per line, cash flows and (with a baseline) Δcf and NPV, traced."""
    fin = c.basis.finance
    r, years = fin.discount_rate, fin.horizon_years
    capex, opex = cs.capex["total"], [row["total"] for row in cs.opex]
    ids = [c.tid(f"opex.y{t}.total") for t in range(1, years + 1)]
    rate = {"discount_rate": f"{FIN}discount_rate"}
    tco = c.rec(
        "finance.tco",
        "Total cost of ownership",
        metrics.tco(capex, opex, r),
        "eur",
        "capex + Σ_t opex_t / (1 + r)^t",
        {"capex": c.tid("capex.total"), **{f"opex_y{t}": i for t, i in enumerate(ids, 1)}, **rate},
    )
    cpl = c.rec(
        "finance.cost_per_line",
        "Cost per line",
        metrics.cost_per_line(tco, r, years, lines),
        "eur/line",
        "TCO × r / (1 − (1 + r)^−T) / annual_lines_y1",
        {
            "tco": c.tid("finance.tco"),
            "annual_lines_y1": c.tid("finance.annual_lines_y1"),
            "horizon_years": f"{FIN}horizon_years",
            **rate,
        },
    )
    own = [-capex, *(-x for x in opex)]
    for t, x in enumerate(own):
        src = c.tid("capex.total") if t == 0 else ids[t - 1]
        c.rec(
            f"finance.cash_flow.y{t}",
            f"Cash flow, year {t}",
            x,
            "eur",
            "−capex" if t == 0 else "−opex_t",
            {"cost": src},
        )
    if base is None:
        return WorldMetrics(tco, cpl, own, None, None)
    delta, npv = _vs_baseline(c, capex, ids, [row["total"] for row in cs.opex], base)
    return WorldMetrics(tco, cpl, own, delta, npv)


def _vs_baseline(
    c: Ctx, capex: float, ids: Sequence[str], opex: Sequence[float], base: Base
) -> tuple[list[float], float]:
    """Δcf_0..T and NPV vs the baseline in this world, traced."""
    r, years = c.basis.finance.discount_rate, c.basis.finance.horizon_years
    delta = [-(capex - base.capex), *(b - s for b, s in zip(base.opex, opex, strict=True))]
    for t, x in enumerate(delta):
        c.rec(
            f"finance.delta_cf.y{t}",
            f"Δ cash flow vs baseline, year {t}",
            x,
            "eur",
            "−(capex − baseline_capex)" if t == 0 else "baseline_opex_t − opex_t",
            {"capex": c.tid("capex.total"), "baseline_capex": c.tid("finance.baseline.capex")}
            if t == 0
            else {"opex": ids[t - 1], "baseline_opex": c.tid(f"finance.baseline.opex.y{t}")},
        )
    npv = c.rec(
        "finance.npv",
        "NPV vs baseline",
        metrics.npv(delta, r),
        "eur",
        "Σ_t Δcf_t / (1 + r)^t (Δcf_0 undiscounted)",
        {
            **{f"delta_cf_y{t}": c.tid(f"finance.delta_cf.y{t}") for t in range(years + 1)},
            "discount_rate": f"{FIN}discount_rate",
        },
    )
    return delta, npv


def _trace_typ(c: Ctx, irr: float | None, pay: float | None, delta: Sequence[float] | None) -> None:
    """IRR and payback (typical world, I37) as nodes; none when undefined."""
    if delta is None:
        return
    refs = {f"delta_cf_y{t}": c.tid(f"finance.delta_cf.y{t}") for t in range(len(delta))}
    if irr is not None:
        c.rec("finance.irr", "IRR vs baseline", irr, "-", "numpy_financial.irr(Δcf)", refs)
    if pay is not None:
        c.rec(
            "finance.payback_years",
            "Payback",
            pay,
            "years",
            "first t with Σ_{k≤t} Δcf_k ≥ 0, interpolated within the year",
            refs,
        )


def _assemble(
    result: ScenarioResult,
    costs: Mapping[World, Costs],
    wm: Mapping[World, WorldMetrics],
    irr: float | None,
    payback: float | None,
    notes: list[str],
) -> FinancialResult:
    def rng(get: Callable[[World], float], unit: str) -> Range:
        return to_range({w: get(w) for w in WORLDS}, unit)

    typ = wm["typ"]
    npv: dict[World, float] = {w: m.npv for w, m in wm.items() if m.npv is not None}
    return FinancialResult(
        scenario_id=result.scenario.id,
        capex={
            k: rng(lambda w, k=k: costs[w].capex[k], "eur")
            for k in costs["typ"].capex
            if k != "total"
        },
        capex_total=rng(lambda w: costs[w].capex["total"], "eur"),
        opex_by_year=[{k: v for k, v in row.items() if k != "total"} for row in costs["typ"].opex],
        opex_year1=rng(lambda w: costs[w].opex[0]["total"], "eur"),
        tco=rng(lambda w: wm[w].tco, "eur"),
        npv_vs_baseline=to_range(npv, "eur") if len(npv) == len(WORLDS) else None,
        irr_vs_baseline=irr,
        payback_years=payback,
        cost_per_line=rng(lambda w: wm[w].cost_per_line, "eur/line"),
        cash_flows_typ=typ.cash_flows,
        delta_cash_flows_typ=typ.delta or [],
        notes=notes,
    )
