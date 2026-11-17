"""F6a storage class per SKU (storage_classes.yaml [P]; I10 fits_shelf, I14, I17, I43)."""

from __future__ import annotations

import polars as pl

from whsizing.catalog import Catalog, ParamSet
from whsizing.schemas import FamilyId

DIMS = ("length_mm", "width_mm", "height_mm")
# the automated class of a family's eligible SKUs; manual_p2p has none
AUTOMATED_CLASS: dict[FamilyId, str] = {"cube_asrs": "cube_bin", "amr_gtp": "pod_bin"}


def fits_shelf(shelf_item_max_mm: tuple[float, float, float]) -> pl.Expr:
    """I10: l, w, h all known and, sorted descending, ≤ sorted `shelf_item_max_mm`.
    A missing dim → False (the SKU does not verifiably fit a shelf bin); weight is not tested."""
    l1, l2, l3 = sorted(shelf_item_max_mm, reverse=True)
    dims = [pl.col(c).fill_nan(None) for c in DIMS]
    d = pl.concat_list(dims).list.sort(descending=True)
    fits = (d.list.get(0) <= l1) & (d.list.get(1) <= l2) & (d.list.get(2) <= l3)
    return (pl.all_horizontal(e.is_not_null() for e in dims) & fits.fill_null(False)).alias(
        "fits_shelf"
    )


def classify_skus(
    sku: pl.DataFrame, family: FamilyId, eligible: pl.Series, catalog: Catalog, params: ParamSet
) -> pl.DataFrame:
    """Add `fits_shelf`, `manual_class`, `storage_class` and `zone` to the SKU frame.

    F6a: `stock_cube_i = s_i × v_i` (column `design_stock_cube_m3`); manual rule
    `not fits_shelf or sc ≥ pallet_threshold → pallet_rack; sc ≤ shelf_bin_net_cube ×
    max_bins_per_sku_shelf → shelving; else pallet_rack`. Every SKU gets a manual class, also
    with `s_i = 0` (it routes the SKU's picking lines, I14/I17). `storage_class` = the family's
    automated class (cube_bin / pod_bin) when `eligible`, else the manual class; it is also the
    SKU's picking zone (I17). `zone` = "main" for the scenario family's own classes, "overflow"
    for the manual classes of an automated scenario (I43).
    """
    threshold = params.value("storage.pallet_threshold_m3")
    shelf_cap = params.value("storage.shelf_bin_net_cube_m3") * params.value(
        "storage.max_bins_per_sku_shelf"
    )
    sc = pl.col("design_stock_cube_m3")
    manual = (
        pl.when(~pl.col("fits_shelf") | (sc >= threshold))
        .then(pl.lit("pallet_rack"))
        .when(sc <= shelf_cap)
        .then(pl.lit("shelving"))
        .otherwise(pl.lit("pallet_rack"))
    )
    auto = AUTOMATED_CLASS.get(family)
    out = sku.with_columns(fits_shelf(catalog.storage.shelf_item_max_mm), eligible=eligible)
    out = out.with_columns(manual_class=manual)
    if auto is None:
        return out.with_columns(storage_class=pl.col("manual_class"), zone=pl.lit("main"))
    return out.with_columns(
        storage_class=pl.when("eligible").then(pl.lit(auto)).otherwise("manual_class"),
        zone=pl.when("eligible").then(pl.lit("main")).otherwise(pl.lit("overflow")),
    )
