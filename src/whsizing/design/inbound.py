"""F4 inbound: receipts mode (percentile of the daily receipts) or derived mode (I12, I13)."""

from __future__ import annotations

import numpy as np
import polars as pl

from whsizing.catalog import Catalog, ParamSet
from whsizing.design.basis import (
    GROWTH_FIELDS,
    candidate_days,
    check_basis,
    growth_factor,
    require_finite,
    window_months,
)
from whsizing.errors import ConfigError, DataQualityError, WhsizingError
from whsizing.logging import get_logger
from whsizing.schemas import DemandProfile, DesignBasis, Flag, Inbound

PACK = ("units_per_pallet", "units_per_case", "cases_per_pallet")
RECEIPTS = ("receipts_units", "receipts_pallets", "receipts_lines")
# Catalog constants F4 inbound multiplies or divides by (overridable in basis.overrides)
CATALOG_IDS = (
    "engine.receipt_lines_per_pallet_full",
    "engine.receipt_lines_per_pallet_mixed",
    "storage.default_units_per_pallet",
)


def param_set(basis: DesignBasis, catalog: Catalog | None) -> ParamSet:
    """Catalog values with the basis overrides (unknown override id → ConfigError). There is
    no package default catalog (Project.catalog resolves against project.yaml): required."""
    if catalog is None:
        raise ConfigError("catalog is required: pass catalog=load_catalog(Project.catalog)")
    return ParamSet(catalog, basis.overrides)


def applied_percentile(basis: DesignBasis) -> tuple[float, bool]:
    """(percentile used, clipped): above 100 → 100, the max (F_PERCENTILE_CLIPPED). Negative
    and NaN are rejected by `check_basis`."""
    p = basis.projection.design_percentile
    return min(p, 100.0), p > 100


def with_pack_data(skus: pl.DataFrame, sku_master: pl.DataFrame | None) -> pl.DataFrame:
    """F3 SKU table (`sku`, `units`) + the pack columns of the canonical SKU master, which F3
    does not keep (the master's replace any already in `skus`); absent columns become null (I13
    fallbacks). Other columns (I58 engine frame: hazmat, temperature_class, ...) are kept."""
    cols = [c for c in PACK if sku_master is not None and c in sku_master.columns]
    if sku_master is not None and cols:
        skus = skus.drop(cols, strict=False).join(
            sku_master.select("sku", *cols), on="sku", how="left"
        )
    return skus.with_columns(
        pl.lit(None, pl.Float64).alias(c) for c in PACK if c not in skus.columns
    )


def inbound_by_sku(units_in: float, sku: pl.DataFrame, params: ParamSet) -> pl.DataFrame:
    """I13 per SKU: units_in_i = units_in × U_i / Σ U; pallets_in_i = units_in_i / upp_i;
    receipt_lines_i = pallets_in_i × (full 1.0 if units_in_i ≥ upp_i else mixed 4);
    cases_in_i = units_in_i / upc_i. upp = units_per_pallet | units_per_case × cases_per_pallet
    | storage.default_units_per_pallet; upc = units_per_case | units_per_pallet /
    cases_per_pallet | 1. `default_upp` = no units_per_case × cases_per_pallet: F2
    (canonical.derive) always fills units_per_pallet, with the default when the case data is
    missing, so the fallback shows only there (same rule as the DQ coverage, io/dq.py)."""
    total = float(sku["units"].sum())
    if total <= 0:
        raise WhsizingError("derived inbound: no shipped units in the SKU table")
    sku = sku.with_columns(pl.lit(None, pl.Float64).alias(c) for c in PACK if c not in sku.columns)
    upp = pl.col("units_per_pallet").cast(pl.Float64)
    upc = pl.col("units_per_case").cast(pl.Float64)
    cpp = pl.col("cases_per_pallet").cast(pl.Float64)
    given = pl.coalesce(upp, upc * cpp)
    full, mixed, default_upp = values = [params.value(pid) for pid in CATALOG_IDS]
    bad = [f"{p} = {v!r}" for p, v in zip(CATALOG_IDS, values, strict=True) if not v > 0]
    if bad:  # ParamSet keeps a constant override as given (I60, F4c)
        raise ConfigError(f"inbound: {'; '.join(bad)} (catalog or basis overrides) must be > 0")
    return (
        sku.select(
            "sku",
            units_in=units_in * pl.col("units") / total,
            upp=given.fill_null(default_upp),
            upc=pl.coalesce(upc, upp / cpp, pl.lit(1.0)),
            default_upp=(upc * cpp).is_null(),
        )
        .pipe(_check_pack)
        .with_columns(pallets_in=pl.col("units_in") / pl.col("upp"))
        .with_columns(
            receipt_lines=pl.col("pallets_in")
            * pl.when(pl.col("units_in") >= pl.col("upp")).then(full).otherwise(mixed),
            cases_in=pl.col("units_in") / pl.col("upc"),
        )
    )


def derive_inbound(
    profile: DemandProfile,
    basis: DesignBasis,
    daily: pl.DataFrame,
    sku: pl.DataFrame | None,
    *,
    catalog: Catalog | None = None,
) -> Inbound:
    """F4 inbound. `sku`: F3 SKU table (`sku`, `units` shipped over the history) with the pack
    columns (`with_pack_data`; extra columns ignored, I58); required in derived mode, optional
    in receipts mode (cases). `catalog` is required. peak_factor = flows.inbound_peak_factor,
    else the outbound peak-to-average (P95 / mean of daily lines) in derived mode and 1.0 in
    receipts mode, whose P_p values are already design-day values (I56). `Inbound.flags` (after
    the design-day flags in `DesignDay.flags`, I46 order extended): F_INBOUND_SPARSE and
    F_RECEIPTS_NO_PALLETS (warning, receipts mode), F_DEFAULT_UPP (info, derived mode)."""
    params = param_set(check_basis(basis), catalog)
    flows, proj = basis.flows, basis.projection
    gf = growth_factor(proj.growth_rate, proj.horizon_years)
    cand = candidate_days(daily, window_months(proj, daily))
    pf = flows.inbound_peak_factor
    if flows.inbound_mode == "receipts":
        pf = 1.0 if pf is None else pf
        units, pallets, lines, flags = _receipts(profile, cand, applied_percentile(basis)[0], gf)
        per = None if sku is None else inbound_by_sku(units, sku, params)
    else:
        pf = profile.seasonality.peak_to_average if pf is None else pf
        units, pallets, lines, per = _derived(profile, basis, cand, sku, params, gf)
        flags = _default_upp_flag(per)
    trucks = pallets / flows.pallets_per_truck
    cases = None if per is None else float(per["cases_in"].sum())
    values = {"units": units, "pallets": pallets, "receipt_lines": lines, "trucks": trucks}
    require_finite(
        {f"inbound.{k}_per_day": v for k, v in {**values, "cases": cases}.items()},
        f"{GROWTH_FIELDS}, flows.pallets_per_truck, {', '.join(CATALOG_IDS)}",
    )
    return Inbound(
        mode=flows.inbound_mode,
        units_per_day=units,
        pallets_per_day=pallets,
        receipt_lines_per_day=lines,
        trucks_per_day=trucks,
        peak_factor=pf,
        cases_per_day=cases,
        flags=flags,
    )


def _derived(
    profile: DemandProfile,
    basis: DesignBasis,
    cand: pl.DataFrame,
    sku: pl.DataFrame | None,
    params: ParamSet,
    gf: float,
) -> tuple[float, float, float, pl.DataFrame]:
    """I12/I13 derived mode: units_in = mean outbound units × (1 + g)^T + Δstock / operating
    days, spread over the SKUs → (units, pallets, receipt lines, per-SKU frame)."""
    if sku is None:
        raise WhsizingError(
            "derived inbound needs the per-SKU table: pass "
            "sku=with_pack_data(tables.skus, canonical sku_master)"
        )
    delta_stock = profile.stock.growth_units_per_year or 0.0  # < 3 snapshots → 0 (I12)
    mean_out = float(cand["units"].mean())  # pyright: ignore[reportArgumentType]
    days = basis.operations.operating_days_per_year
    units = mean_out * gf + delta_stock / days
    if units < 0:  # I85 (a): an extreme destock in the inventory history, never a negative design
        raise DataQualityError(
            f"derived inbound is negative ({units:.6g} units/day): the delta-stock term is "
            f"{delta_stock:.6g} units/year ({delta_stock / days:.6g} units/day over {days:g} "
            f"operating days) against mean outbound x growth of {mean_out * gf:.6g} units/day. "
            "Check the inventory snapshots (units, outlier quantities, stock-take dates) or "
            "set flows.inbound_mode to 'receipts'"
        )
    per = inbound_by_sku(units, sku, params)
    return units, float(per["pallets_in"].sum()), float(per["receipt_lines"].sum()), per


def _check_pack(per: pl.DataFrame) -> pl.DataFrame:
    """I13: pack data used as a divisor must be > 0 (Pandera ge=1 holds on canonical data)."""
    bad = per.filter((pl.col("upp") <= 0) | (pl.col("upc") <= 0))
    if not bad.is_empty():
        skus = bad["sku"].head(5).to_list()
        raise WhsizingError(
            f"derived inbound: units_per_pallet / units_per_case ≤ 0 for {bad.height} SKU(s), "
            f"e.g. {skus}"
        )
    return per


def _no_receipts(profile: DemandProfile, cand: pl.DataFrame, missing: list[str]) -> ConfigError:
    """I71: receipts mode with nothing to size on, never an all-zero inbound. Three cases, each
    naming the mode and the receipts date range: no receipts table with a row, or none dated
    inside the shipped-date window (F3 leaves the receipts_* columns out: `missing`); or some
    inside the window but none on an operating day of the design-day window `cand`."""
    head = "flows.inbound_mode is 'receipts' but "
    tail = "load receipts for the window or use 'derived'"
    window = f"{profile.period_start} to {profile.period_end}"
    if 0 < len(missing) < len(RECEIPTS):  # F3 writes the three columns together
        return ConfigError(f"{head}the daily frame lacks the {missing} column(s), F3 writes all")
    if profile.receipts_period is None:
        found = f"no receipts dataset with a row was loaded (history window {window})"
        return ConfigError(f"{head}{found}; {tail}")
    first, last = profile.receipts_period
    if missing:
        found = f"the receipts are dated {first} to {last}, none inside the history window {window}"
        return ConfigError(f"{head}{found}; {tail}")
    days = f"{cand['date'].min()} to {cand['date'].max()}"
    return ConfigError(
        f"{head}none of the receipts (dated {first} to {last}) falls on an operating day of the "
        f"design-day window {days}; extend projection.trailing_months, check which days are "
        "operating, load receipts for that window or use 'derived'"
    )


def _receipts(
    profile: DemandProfile, cand: pl.DataFrame, pct: float, gf: float
) -> tuple[float, float, float, list[Flag]]:
    """I56: P_p of the daily receipt units, pallets and lines over the candidate days, × (1 + g)^T
    like every design quantity (sized for the end of the horizon). Days whose pallet count is
    unknown are left out of the pallets percentile only. No receipt on any candidate day (no
    table, outside the history, or outside the design-day window): I71. Receipts that exist but
    give a zero percentile, or no pallet count at all, are flagged (`_receipt_flags`)."""
    missing = [c for c in RECEIPTS if c not in cand.columns]
    if missing or cand["receipts_lines"].sum() == 0:
        raise _no_receipts(profile, cand, missing)
    pallets = cand["receipts_pallets"].drop_nulls().to_numpy()
    if pallets.size == 0:
        raise ConfigError(
            "flows.inbound_mode 'receipts': no pallet count in the receipts; use 'derived'"
        )
    if pallets.size < cand.height:
        get_logger().warning("receipts_pallets_unknown", days_left_out=cand.height - pallets.size)
    units, lines = (
        float(np.percentile(cand[c].to_numpy(), pct)) for c in ("receipts_units", "receipts_lines")
    )
    pallets_p = float(np.percentile(pallets, pct))
    flags = _receipt_flags(cand, pct, units, pallets_p)
    return units * gf, pallets_p * gf, lines * gf, flags


def _receipt_flags(cand: pl.DataFrame, pct: float, units_p: float, pallets_p: float) -> list[Flag]:
    """Warnings for receipts that exist on the candidate days but size the inbound at 0 (I71):
    F_INBOUND_SPARSE when P_p of the daily units or pallets is 0 (value = receipt days among the
    candidate days); F_RECEIPTS_NO_PALLETS when the pallet count is unknown on every receipt day
    (F3 puts 0.0 on the days without a receipt, so pallets and trucks come out 0 next to non-zero
    units; value = receipt days). The zero pallets of that case are not also called sparse."""
    days = cand.filter(pl.col("receipts_lines") > 0)
    n = days.height
    no_pallets = days["receipts_pallets"].null_count() == n
    zero = [
        name
        for name, p in (("units", units_p), ("pallets", pallets_p))
        if p == 0 and not (name == "pallets" and no_pallets)
    ]
    flags: list[Flag] = []
    if zero:
        what = " and ".join(zero)
        msg = (
            f"receipts fall on {n} of {cand.height} candidate days: P{pct:g} of the daily "
            f"{what} is 0, so the inbound {what} are sized at 0; raise "
            "projection.design_percentile, widen projection.trailing_months, load more "
            "receipts or use 'derived'"
        )
        flags.append(Flag(code="F_INBOUND_SPARSE", severity="warning", message=msg, value=float(n)))
    if no_pallets:
        msg = (
            f"the pallet count of the receipts is unknown on all {n} receipt day(s): inbound "
            "pallets and trucks are 0 next to non-zero units; add the pallet counts to the "
            "receipts or use 'derived'"
        )
        flags.append(
            Flag(code="F_RECEIPTS_NO_PALLETS", severity="warning", message=msg, value=float(n))
        )
    return flags


def _default_upp_flag(per: pl.DataFrame | None) -> list[Flag]:
    """I59: the default units-per-pallet fallback is flagged, info, value = share of the design
    inbound units on the default."""
    if per is None:
        return []
    used = per.filter(pl.col("default_upp") & (pl.col("units_in") > 0))
    if used.is_empty():
        return []
    share = float(used["units_in"].sum()) / float(per["units_in"].sum())  # pyright: ignore[reportArgumentType]
    return [
        Flag(
            code="F_DEFAULT_UPP",
            severity="info",
            message=f"{used.height} SKU(s) without pack data ({share:.1%} of inbound units) "
            "use the default units per pallet",
            value=share,
        )
    ]
