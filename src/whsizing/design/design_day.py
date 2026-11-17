"""F4 design day (steps 1-9) and its artifacts design/design_day.json, design/assumptions.json."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from whsizing.catalog import Catalog
from whsizing.design.assumptions import basis_assumptions
from whsizing.design.basis import (
    GROWTH_FIELDS,
    STOCK_FIELDS,
    candidate_days,
    check_basis,
    growth_factor,
    require_finite,
    sla_window_hours,
    warn_short_window,
    window_months,
)
from whsizing.design.inbound import applied_percentile, derive_inbound, param_set
from whsizing.errors import WhsizingError
from whsizing.profile.aggregate import METRICS
from whsizing.profile.intraday import design_weekday
from whsizing.schemas import (
    Assumption,
    DemandProfile,
    DesignBasis,
    DesignDay,
    Flag,
    Projection,
)

RATIO_DRIFT_MAX = 0.15  # [P] F4 step 4: |m* − P_m| / P_m above → F_RATIO_DRIFT
SHORT_HISTORY_DAYS = 60  # F4 edge case: fewer candidate days → F_SHORT_HISTORY


def select_design_day(
    profile: DemandProfile,
    basis: DesignBasis,
    daily: pl.DataFrame,
    *,
    sku: pl.DataFrame | None = None,
    catalog: Catalog | None = None,
) -> DesignDay:
    """F4 steps 1-9 on the F3 daily series. `sku` (I58: F3 SKU table + pack columns, see
    `inbound.with_pack_data`; extra columns ignored) is required in the derived inbound mode;
    `catalog` is required (overrides["stock_growth_rate"] is read through ParamSet)."""
    params = param_set(check_basis(basis), catalog)
    proj = basis.projection
    pct, clipped = applied_percentile(basis)
    months = window_months(proj, daily)  # I55
    cand = candidate_days(daily, months)
    warn_short_window(daily, months)
    gf = growth_factor(proj.growth_rate, proj.horizon_years)
    p, ref, base, design = _design_values(cand, pct, gf)
    wd = design_weekday(cand)
    if wd not in profile.intraday:
        raise WhsizingError(f"no intraday profile for design weekday {wd}: daily ≠ profile data")
    hourly = [s * design["lines"] for s in profile.intraday[wd]]
    stock_g = params.basis_value("stock_growth_rate", proj.growth_rate)
    stock, stock_k = _stock(profile, proj, stock_g)
    inbound = derive_inbound(profile, basis, daily, sku, catalog=catalog)
    flags = _flags(clipped, cand.height, base, p) + inbound.flags
    derived = {
        "service.sla_window_hours": sla_window_hours(basis.service),
        "flows.inbound_peak_factor": inbound.peak_factor,
        "projection.trailing_months": float(months),
    }
    return DesignDay(
        percentile=pct,
        growth_rate=proj.growth_rate,
        horizon_years=proj.horizon_years,
        reference_date=cand["date"][ref],
        **{m: design[m] for m in ("lines", "orders", "units", "cube_m3", "weight_kg")},
        design_weekday=wd,
        hourly_lines=hourly,
        peak_hour_lines=max(hourly),
        parcels=design["parcels"],
        pallets_out=design["pallets_out"],
        **stock,
        inbound=inbound,
        assumptions=basis_assumptions(basis, derived, _factor_rows(gf, stock_k)),
        percentile_values=p,
        flags=flags,
    )


def _design_values(
    cand: pl.DataFrame, pct: float, gf: float
) -> tuple[dict[str, float], int, dict[str, float], dict[str, float]]:
    """F4 steps 2-5 → (P_m, reference day index r, base m* = P_lines × m_r / lines_r, design
    m* × (1 + g)^T); r = the day with lines nearest P_lines, earliest on ties (I7)."""
    p = {m: float(np.percentile(cand[m].to_numpy(), pct)) for m in METRICS}
    ref = int(np.argmin(np.abs(cand["lines"].to_numpy() - p["lines"])))
    base = {m: p["lines"] * cand[m][ref] / cand["lines"][ref] for m in METRICS}
    design = {m: base[m] * gf for m in METRICS}
    require_finite({f"design_day.{m}": v for m, v in design.items()}, GROWTH_FIELDS)
    return p, ref, base, design


def _stock(
    profile: DemandProfile, proj: Projection, stock_g: float
) -> tuple[dict[str, float], float]:
    """F4 step 7: avg stock × peak_stock_factor × (1 + stock growth)^T → (values, factor)."""
    k = proj.peak_stock_factor * growth_factor(stock_g, proj.horizon_years)
    stock = {
        "stock_units": profile.stock.avg_units * k,
        "stock_cube_m3": profile.stock.avg_cube_m3 * k,
    }
    require_finite({f"design_day.{key}": v for key, v in stock.items()}, STOCK_FIELDS)
    return stock, k


def _factor_rows(gf: float, stock_k: float) -> list[Assumption]:
    """The derived growth and stock factors, appended to the assumptions list."""
    note = "peak_stock_factor × (1 + stock growth)^T (F4 step 7)"
    return [
        Assumption(
            key="design.growth_factor", value=gf, unit="-", origin="derived", note="(1 + g)^T"
        ),
        Assumption(key="design.stock_factor", value=stock_k, unit="-", origin="derived", note=note),
    ]


def _flags(clipped: bool, n_days: int, base: dict[str, float], p: dict[str, float]) -> list[Flag]:
    """Design-day flags in I46 order: F_PERCENTILE_CLIPPED, F_SHORT_HISTORY, F_RATIO_DRIFT:<m>
    (drift of the ratio-derived m* before growth against P_m; P_m = 0 < m*: unbounded, value
    None; both 0: no flag, I57). All three are `info` (I70). `select_design_day` appends the
    inbound flags after them: F_INBOUND_SPARSE, F_RECEIPTS_NO_PALLETS (warning, receipts mode),
    F_DEFAULT_UPP last (info, derived mode, I59)."""
    flags: list[Flag] = []
    if clipped:
        msg = "design_percentile above 100: clipped to the maximum day"
        flags.append(Flag(code="F_PERCENTILE_CLIPPED", severity="info", message=msg))
    if n_days < SHORT_HISTORY_DAYS:
        msg = f"design day chosen among {n_days} operating days (< {SHORT_HISTORY_DAYS})"
        flags.append(
            Flag(code="F_SHORT_HISTORY", severity="info", message=msg, value=float(n_days))
        )
    for m in METRICS:
        drift = abs(base[m] - p[m]) / p[m] if p[m] > 0 else None
        if (drift is None and base[m] > 0) or (drift is not None and drift > RATIO_DRIFT_MAX):
            msg = f"{m}: reference-day ratio gives {base[m]:.4g}, P_m = {p[m]:.4g}"
            flags.append(Flag(code=f"F_RATIO_DRIFT:{m}", severity="info", message=msg, value=drift))
    return flags


def write_design(design_day: DesignDay, run_dir: Path) -> list[Path]:
    """Write design/design_day.json and design/assumptions.json under `run_dir`."""
    out = run_dir / "design"
    out.mkdir(parents=True, exist_ok=True)
    dd_path, as_path = out / "design_day.json", out / "assumptions.json"
    dd_path.write_text(design_day.model_dump_json(indent=2), encoding="utf-8")
    rows = [a.model_dump(mode="json") for a in design_day.assumptions]
    as_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return [dd_path, as_path]
