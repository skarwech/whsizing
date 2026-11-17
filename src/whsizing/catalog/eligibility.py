"""Which SKUs a family can handle, and the eligible shares (F5 algorithm — eligibility)."""

from __future__ import annotations

import polars as pl

from whsizing.catalog.models import Family
from whsizing.errors import WhsizingError
from whsizing.schemas import EligibilityCfg, EligibilityResult, FamilyId, Flag

DIMS = ("length_mm", "width_mm", "height_mm")


def eligible_mask(sku: pl.DataFrame, family: Family, cfg: EligibilityCfg) -> pl.Series:
    """Boolean per SKU row (same order as `sku`), named "eligible".

    Limits (`use_catalog_limits`): sorted dims ≤ sorted `max_item_mm` (orientation-agnostic) and
    weight ≤ `max_weight_kg`; `extra_max_weight_kg` applies in any case. A missing (null or NaN)
    dim or weight makes the SKU ineligible (step 3, whatever the limits), unless
    `assume_eligible_if_missing_dims`, which assumes only the MISSING values fit (missing dims sort
    as the smallest), so a known violation (2000 mm, or 40 kg) keeps the SKU ineligible. Hazmat
    and temperature constraints always apply; a null `hazmat` counts as not hazmat and a null
    `temperature_class` as ambient (also when the column is absent).
    """
    absent = [col for col in (*DIMS, "weight_kg") if col not in sku.columns]
    if absent:
        raise WhsizingError(f"eligible_mask: SKU frame lacks column(s) {absent}")
    c = family.constraints
    dims = [pl.col(col).fill_nan(None) for col in DIMS]
    weight = pl.col("weight_kg").fill_nan(None)
    # step 3: unknown (null), not False, when any dim or the weight is missing
    known = pl.when(pl.all_horizontal(e.is_not_null() for e in (*dims, weight))).then(True)
    checks: list[pl.Expr] = [known]
    if cfg.use_catalog_limits:
        l1, l2, l3 = sorted(c.max_item_mm, reverse=True)
        d = pl.concat_list(dims).list.sort(descending=True, nulls_last=True)
        checks.append((d.list.get(0) <= l1) & (d.list.get(1) <= l2) & (d.list.get(2) <= l3))
    weight_caps = [cfg.extra_max_weight_kg, c.max_weight_kg if cfg.use_catalog_limits else None]
    caps = [w for w in weight_caps if w is not None]
    if caps:
        checks.append(weight <= min(caps))

    # Kleene logic: any known False → False; otherwise a null (unknown) → the assume flag
    fits = pl.all_horizontal(checks).fill_null(cfg.assume_eligible_if_missing_dims)
    hazmat = pl.col("hazmat").fill_null(False) if "hazmat" in sku.columns else pl.lit(False)
    temp = (
        pl.col("temperature_class").cast(pl.Utf8).fill_null("ambient")
        if "temperature_class" in sku.columns
        else pl.lit("ambient")
    )
    ok = fits & temp.is_in(c.temperature_classes)
    if c.excludes_hazmat:
        ok = ok & ~hazmat
    # with_columns broadcasts an all-literal `ok` to the frame height; select would give 1 row
    return sku.with_columns(ok.alias("eligible"))["eligible"]


def assumed_mask(sku: pl.DataFrame, family: Family, cfg: EligibilityCfg) -> pl.Series:
    """SKUs eligible only because `assume_eligible_if_missing_dims` is set (F_ELIG_ASSUMED)."""
    strict = cfg.model_copy(update={"assume_eligible_if_missing_dims": False})
    return (eligible_mask(sku, family, cfg) & ~eligible_mask(sku, family, strict)).alias("assumed")


def eligibility_shares(
    mask: pl.Series,
    lines_by_sku: pl.Series,
    stock_by_sku: pl.Series,
    *,
    family: FamilyId,
    low_share: float,
    assumed: pl.Series | None = None,
) -> EligibilityResult:
    """Eligible shares by lines, stock cube and SKU count; overflow = 1 − share.

    All series are aligned row by row (one row per SKU, nulls = 0): the caller joins lines over
    the trailing window and stock cube onto the SKU list, orphan SKUs included with mask False.
    `low_share` = `engine.elig_low_line_share` (0.5): below it → F_ELIG_LOW.
    """
    m, lines, stock, a = _aligned(mask, lines_by_sku, stock_by_sku, assumed)
    n_total, n_elig = len(m), int(m.sum())
    share_lines = _share(lines, m)
    assumed_lines = _share(lines, a)
    flags: list[Flag] = []
    if share_lines < low_share:
        flags.append(
            Flag(
                code="F_ELIG_LOW",
                severity="warning",
                message=f"{family}: {share_lines:.0%} of lines eligible (< {low_share:.0%}); "
                "the rest goes to the manual overflow zone",
                value=share_lines,
            )
        )
    if a.any():
        flags.append(
            Flag(
                code="F_ELIG_ASSUMED",
                severity="warning",
                message=f"{family}: {int(a.sum())} SKU(s) without dims/weight assumed eligible "
                f"({assumed_lines:.1%} of lines)",
                value=assumed_lines,
            )
        )
    return EligibilityResult(
        family=family,
        share_lines=share_lines,
        share_stock_cube=_share(stock, m),
        share_skus=n_elig / n_total if n_total else 0.0,
        n_skus_eligible=n_elig,
        n_skus_total=n_total,
        assumed_share_lines=assumed_lines,
        flags=flags,
    )


def units_per_bin(bin_net_cube_m3: float, fill: float, unit_cube_m3: pl.Series) -> pl.Series:
    """floor(bin_net_cube × fill / unit_cube), volumetric (a nesting factor is backlog).

    `unit_cube_m3` must be > 0 (null → null); raises WhsizingError on 0, negative or NaN.
    """
    cube = unit_cube_m3.cast(pl.Float64)
    if (cube.is_nan() | (cube <= 0)).any():
        raise WhsizingError("units_per_bin: unit_cube_m3 must be > 0 (got 0, negative or NaN)")
    # ponytail: relative 1e-12 (~4500 ulp) so 3.9999999999999996 floors to 4 but 3.9999999995 to 3
    ratio = bin_net_cube_m3 * fill / cube
    return (ratio * (1 + 1e-12)).floor().cast(pl.Int64).alias("units_per_bin")


def _aligned(
    mask: pl.Series, lines_by_sku: pl.Series, stock_by_sku: pl.Series, assumed: pl.Series | None
) -> tuple[pl.Series, pl.Series, pl.Series, pl.Series]:
    """(eligible, lines, stock, assumed & eligible), nulls → 0/False; same length, no NaN or < 0."""
    series = (mask, lines_by_sku, stock_by_sku, mask if assumed is None else assumed)
    sizes = [len(s) for s in series]
    if len(set(sizes)) > 1:
        raise WhsizingError(
            f"eligibility_shares: series lengths differ (mask, lines, stock, assumed: {sizes})"
        )
    m = mask.cast(pl.Boolean).fill_null(False)  # an empty series may have dtype Null
    values = []
    for name, s in (("lines_by_sku", lines_by_sku), ("stock_by_sku", stock_by_sku)):
        v = s.fill_null(0).cast(pl.Float64)
        if (v.is_nan() | (v < 0)).any():
            raise WhsizingError(f"eligibility_shares: {name} has NaN or negative values")
        values.append(v)
    a = m & assumed.cast(pl.Boolean).fill_null(False) if assumed is not None else m & False
    return m, values[0], values[1], a


def _share(values: pl.Series, sel: pl.Series) -> float:
    total = float(values.sum())
    return float(values.filter(sel).sum()) / total if total > 0 else 0.0
