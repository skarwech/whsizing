"""Golden oracle F3-F5 stages (G1, T1.5): demand profile, SKU table, eligibility, design day
and derived inbound on the canonical tiny_golden frames. Formulas and catalog values live in
oracle.py; rules where the spec is silent are numbered in docs/INTERPRETATIONS.md (I<n>).
Never imports `whsizing`.
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from tests.golden.oracle import (
    CUBE,
    DEAD_STOCK_DAYS,
    DEFAULT_INTRADAY,
    METRICS,
    NO_TIME_SHARE_MAX,
    RECEIPT_LINES_PER_PALLET,
    STORAGE,
    Out,
    abc_classes,
    calendar_months,
    fits,
    growth_factor,
    is_pallet_order,
    manual_class,
    operating_threshold,
    parcels_per_order,
    series_stats,
    trend_cagr,
    trend_confidence,
)

# Optional §4.1 sku_master columns, added as null when absent (I10, I13)
SKU_OPTIONAL: dict[str, Any] = {
    "units_per_case": pl.Int64,
    "cases_per_pallet": pl.Int64,
    "units_per_pallet": pl.Int64,
    "unit_cube_m3": pl.Float64,
    "hazmat": pl.Boolean,
    "temperature_class": pl.String,
}

# I6 ABC order: lines, units, avg_stock, unit cube, weight (unknown weight = 0, I10), all
# descending, then sku ascending (salt-dependent, so last: only SKUs identical in every
# attribute reach it)
ABC_ORDER = [
    pl.col("lines"),
    pl.col("units"),
    pl.col("avg_stock"),
    pl.col("unit_cube_m3"),
    pl.col("weight_kg").fill_null(0.0),
    pl.col("sku"),
]
ABC_DESC = [True, True, True, True, True, False]

STAT_FORMULA = {
    "mean": "mean(x)",
    "p50": "np.percentile(x, 50)",
    "p90": "np.percentile(x, 90)",
    "p95": "np.percentile(x, 95)",
    "p98": "np.percentile(x, 98)",
    "max": "max(x)",
    "cv": "np.std(x, ddof=0) / mean(x)",
}


# --- F3 demand profile ---------------------------------------------------------------------------
def prepare_sku(sku: pl.DataFrame) -> pl.DataFrame:
    """§4.1 sku_master inputs (I10, I13): optional columns added as null; has_dims = dims and
    weight all present (F5 step 3); unit cube = l × w × h / 1e9 (§4.1 derived), else the given
    unit_cube_m3, else 0;
    hazmat null → false; temperature_class null → ambient; upp = units_per_pallet, else
    units_per_case × cases_per_pallet, else 400; upc = units_per_case, else
    units_per_pallet / cases_per_pallet, else 1. `default_upp` = no units_per_case ×
    cases_per_pallet (F2 then filled units_per_pallet with the default, I59)."""
    missing = [pl.lit(None, dtype=t).alias(k) for k, t in SKU_OPTIONAL.items() if k not in sku]
    sku = sku.with_columns(missing)
    dims = ("length_mm", "width_mm", "height_mm", "weight_kg")
    vol = pl.col("length_mm") * pl.col("width_mm") * pl.col("height_mm") / 1e9
    upc, cpp, upp = pl.col("units_per_case"), pl.col("cases_per_pallet"), pl.col("units_per_pallet")
    return sku.with_columns(
        pl.all_horizontal([pl.col(c).is_not_null() for c in dims]).alias("has_dims"),
        pl.coalesce(vol, pl.col("unit_cube_m3"), pl.lit(0.0)).alias("unit_cube_m3"),
        pl.col("hazmat").fill_null(False),
        pl.col("temperature_class").cast(pl.String).fill_null("ambient"),
        pl.coalesce(upp, upc * cpp, pl.lit(STORAGE["default_units_per_pallet"])).alias("upp"),
        pl.coalesce(upc, upp / cpp, pl.lit(1)).cast(pl.Float64).alias("upc"),
        (upc * cpp).is_null().alias("default_upp"),
    )


def with_orphans(
    master: pl.DataFrame, lines: pl.DataFrame, inventory: pl.DataFrame
) -> pl.DataFrame:
    """F2 R2: a shipped or stocked SKU absent from the SKU master is kept as a SKU row without
    master data (has_dims = false after prepare_sku), marked `orphan` (never eligible, I10, I50)."""
    ids = pl.concat([lines.select("sku"), inventory.select("sku")]).unique()
    ids = ids.join(master.select("sku"), on="sku", how="anti")
    return pl.concat(
        [master.with_columns(orphan=pl.lit(False)), ids.sort("sku").with_columns(orphan=True)],
        how="diagonal",
    )


def shipped_lines(order_lines: pl.DataFrame, sku: pl.DataFrame, tz: str) -> pl.DataFrame:
    """F3 definitions: shipped lines only (cancelled and returns excluded); a line takes its
    order's first timestamp (multi-day orders), converted to the basis timezone (I1). `sku` is
    the prepare_sku frame; unknown cube or weight (missing dims, orphan SKU) counts 0 (I10).
    `has_time` = false when that local timestamp is 00:00:00 (date without time, I51)."""
    status = pl.col("line_status").cast(pl.String).fill_null("shipped")
    local = pl.col("order_ts").min().over("order_id").dt.convert_time_zone(tz)
    hms = (local.dt.hour(), local.dt.minute(), local.dt.second())
    return (
        order_lines.filter((status == "shipped") & (pl.col("qty_units") > 0))
        .with_columns(
            local.dt.date().alias("date"),
            local.dt.hour().alias("hour"),
            pl.any_horizontal([x > 0 for x in hms]).alias("has_time"),
        )
        .join(sku.select("sku", "unit_cube_m3", "weight_kg"), on="sku", how="left")
        .with_columns(
            (pl.col("qty_units") * pl.col("unit_cube_m3")).fill_null(0.0).alias("line_cube_m3"),
            (pl.col("qty_units") * pl.col("weight_kg")).fill_null(0.0).alias("line_weight_kg"),
        )
    )


def fsum_lists(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    """Sum list columns with math.fsum: exact, so independent of polars' parallel group order."""
    return df.with_columns(
        pl.col(c).map_elements(lambda v: math.fsum(v), return_dtype=pl.Float64) for c in cols
    )


def orders_table(lines: pl.DataFrame, flows: dict[str, Any]) -> pl.DataFrame:
    """F3 steps 3 and 8: per-order structure, class S/M/L (1 / 2-5 / > 5 lines), shipment split."""
    o = lines.group_by("order_id").agg(
        pl.col("date").first(),
        pl.len().alias("n_lines"),
        pl.col("qty_units").sum().alias("units"),
        pl.col("line_cube_m3").alias("cube_m3"),
        pl.col("line_weight_kg").alias("weight_kg"),
    )
    rows = fsum_lists(o, ["cube_m3", "weight_kg"]).sort("order_id").to_dicts()
    for r in rows:
        r["cls"] = "S" if r["n_lines"] == 1 else "M" if r["n_lines"] <= 5 else "L"
        pallet = is_pallet_order(
            r["weight_kg"],
            r["cube_m3"],
            flows["pallet_order_weight_kg"],
            flows["pallet_order_cube_m3"],
        )
        r["pallets"] = 1 if pallet else 0  # I8: one pallet per pallet order
        r["parcels"] = (
            0 if pallet else parcels_per_order(r["weight_kg"], flows["parcel_max_weight_kg"])
        )
    return pl.DataFrame(rows)


def daily_table(lines: pl.DataFrame, orders: pl.DataFrame, returns: pl.DataFrame) -> pl.DataFrame:
    """F3 step 1: daily series per local date over the full calendar; operating flag (App. B)."""
    cal = pl.DataFrame({"date": pl.date_range(min(lines["date"]), max(lines["date"]), eager=True)})
    by_line = lines.group_by("date").agg(
        pl.len().alias("lines"),
        pl.col("qty_units").sum().alias("units"),
        pl.col("line_cube_m3").alias("cube_m3"),
        pl.col("line_weight_kg").alias("weight_kg"),
    )
    by_line = fsum_lists(by_line, ["cube_m3", "weight_kg"])
    by_order = orders.group_by("date").agg(
        pl.len().alias("orders"),
        pl.col("parcels").sum(),
        pl.col("pallets").sum().alias("pallets_out"),
        (pl.col("cls") == "S").sum().alias("orders_S"),
        (pl.col("cls") != "S").sum().alias("orders_ML"),
    )
    ret = returns.group_by("date").agg(pl.len().alias("return_lines"))
    d = cal.join(by_line, on="date", how="left").join(by_order, on="date", how="left")
    d = d.join(ret, on="date", how="left").fill_null(0)
    thr = operating_threshold(d["lines"].to_numpy().astype(float))
    return d.with_columns(
        (pl.col("date").dt.weekday() - 1).alias("weekday"),
        (pl.col("lines") >= thr).alias("is_operating"),
    ).sort("date")


def profile(out: Out, lines: pl.DataFrame, orders: pl.DataFrame, daily: pl.DataFrame) -> None:
    """F3 steps 2, 3, 6 and 8 on operating days."""
    op = daily.filter("is_operating")
    out.put(
        "profile.period_start",
        str(daily["date"].min()),
        "date",
        "F3: min(local date of shipped lines)",
    )
    out.put(
        "profile.period_end",
        str(daily["date"].max()),
        "date",
        "F3: max(local date of shipped lines)",
    )
    out.put(
        "profile.calendar_days",
        daily.height,
        "d",
        "F3: count of dates from period_start to period_end (I2)",
    )
    out.put(
        "profile.operating_threshold",
        operating_threshold(daily["lines"].to_numpy() * 1.0),
        "lines",
        "App. B: max(1, 0.10 × median(lines_d > 0))",
    )
    out.put("profile.operating_days", op.height, "d", "App. B: count of lines_d ≥ threshold (I2)")
    for name, n in (("orders", orders.height), ("lines", lines.height)):
        out.put(f"profile.n_{name}", n, "-", f"F3: count of shipped {name} (cancelled excluded)")
    out.put("profile.n_units", int(lines["qty_units"].sum()), "units", "F3: Σ qty_units shipped")
    out.put(
        "profile.n_return_lines",
        int(daily["return_lines"].sum()),
        "lines",
        "F3: count of lines with line_status = returned or qty_units < 0 (info only, I9)",
    )
    for m in METRICS:
        for k, v in series_stats(op[m].to_numpy().astype(float)).items():
            out.put(
                f"daily.{m}.{k}",
                v,
                m,
                f"F3 step 2: {STAT_FORMULA[k]}, x = daily {m} over operating days (I3)",
            )
    per_line = lines["qty_units"].to_numpy().astype(float)
    eiq = {
        "lines_per_order": orders["n_lines"],
        "units_per_line": per_line,
        "units_per_order": orders["units"],
        "cube_per_order_m3": orders["cube_m3"],
        "weight_per_order_kg": orders["weight_kg"],
    }
    for name, x in eiq.items():
        unit = "lines" if name == "units_per_line" else "orders"
        for k, v in series_stats(np.asarray(x, dtype=float)).items():
            out.put(
                f"eiq.{name}.{k}",
                v,
                "-",
                f"F3 step 3: {STAT_FORMULA[k]}, x = {name} over all shipped {unit} (I3)",
            )
    for cls in ("S", "M", "L"):
        out.put(
            f"eiq.order_class_share.{cls}",
            (orders["cls"] == cls).mean(),
            "-",
            f"F3 step 3: count(orders of class {cls}) / count(orders); S = 1 line, M = 2-5, L > 5",
        )
    out.put(
        "eiq.single_line_share",
        (orders["n_lines"] == 1).mean(),
        "-",
        "F3 step 3: count(orders with 1 line) / count(orders)",
    )
    pal = orders["pallets"] > 0
    pal_share = float(np.mean(pal.to_numpy()))
    pal_lines = orders.filter(pal)["n_lines"].sum()
    out.put("shipment.pallet_share_orders", pal_share, "-", "F3 step 8: pallet orders / orders")
    out.put(
        "shipment.parcel_share_orders", 1 - pal_share, "-", "F3 step 8: 1 − pallet_share_orders"
    )
    out.put(
        "shipment.pallet_share_lines",
        pal_lines / lines.height,
        "-",
        "F3 step 8: Σ lines of pallet orders / Σ lines",
    )
    out.put(
        "shipment.parcel_share_lines",
        1 - pal_lines / lines.height,
        "-",
        "F3 step 8: 1 − pallet_share_lines",
    )
    out.put(
        "shipment.mean_parcels_per_order",
        orders.filter(~pal)["parcels"].mean(),
        "parcels",
        "F3 step 8: mean of max(1, ceil(weight / parcel_max_weight_kg)) over parcel orders",
    )
    out.put(
        "seasonality.peak_to_average",
        float(np.percentile(op["lines"], 95) / op["lines"].mean()),
        "-",
        "App. B peak_to_avg: P95(lines_d) / mean(lines_d), operating days",
    )
    wk = op.group_by("weekday").agg(pl.col("lines").mean()).sort("weekday")
    for wd, v in wk.iter_rows():
        formula = f"F4 step 6: mean(lines_d), operating days with weekday = {wd}"
        out.put(f"profile.weekday_mean_lines.{wd}", v, "lines", formula)


def sku_table(sku: pl.DataFrame, inventory: pl.DataFrame, lines: pl.DataFrame) -> list[dict]:
    """Per-SKU inputs (`sku` = prepare_sku frame): stock averaged over snapshots (F3 step 5,
    I49), lines/units over the history (I5), ABC by lines (F3 step 4, I6), dead stock (F3 step
    5, I50: last-snapshot stock), shelf fit (F6a)."""
    n_snap = max(1, inventory["snapshot_date"].n_unique())  # I49: absent from a snapshot = 0
    in_last = pl.col("snapshot_date") == pl.col("snapshot_date").max()  # whole-frame max
    stock = (
        inventory.with_columns(in_last=in_last)
        .group_by("sku")
        .agg(
            (pl.col("qty_units").sum() / n_snap).alias("avg_stock"),
            pl.col("qty_units").filter("in_last").sum().alias("last_stock"),
        )
    )
    since = lines["date"].max() - timedelta(days=DEAD_STOCK_DAYS)  # type: ignore[operator]
    mv = lines.group_by("sku").agg(
        pl.len().alias("lines"),
        pl.col("qty_units").sum().alias("units"),
        (pl.col("date") > since).sum().alias("lines_window"),
    )
    t = sku.join(stock, on="sku", how="left").join(mv, on="sku", how="left")
    cols = ("avg_stock", "last_stock", "lines", "units", "lines_window")
    t = t.with_columns(pl.col(cols).fill_null(0))
    rows = t.sort(ABC_ORDER, descending=ABC_DESC).to_dicts()
    for r, cls in zip(rows, abc_classes([r["lines"] for r in rows]), strict=True):
        r["abc"] = cls if r["lines"] > 0 else "C"
        r["dead_stock"] = r["last_stock"] > 0 and r["lines_window"] == 0
        dims = dims_of(r)  # F6a fits_shelf_bin(dims_i): dims only, weight not needed
        r["fits_shelf"] = None not in dims and fits(dims, STORAGE["shelf_item_max_mm"])
    return rows


def dims_of(r: dict) -> tuple[float, float, float]:
    return r["length_mm"], r["width_mm"], r["height_mm"]


def cube_eligible(r: dict, cfg: dict[str, Any]) -> tuple[bool, bool]:
    """F5 eligibility steps 1-3 for cube_asrs under an EligibilityCfg → (eligible, assumed).
    Orphan SKUs, hazmat and excluded temperature classes are never eligible. The KNOWN dims
    (sorted, against the largest limits: a missing dim sorts as the smallest) and the known
    weight (≤ max_weight_kg and ≤ extra_max_weight_kg if set) must fit; then a missing dim or
    weight → ineligible unless assume_eligible_if_missing_dims (eligible by assumption, I10)."""
    if not cfg.get("use_catalog_limits", True):
        raise NotImplementedError("the oracle applies the catalog limits only")
    if (
        r["orphan"]
        or (CUBE["excludes_hazmat"] and r["hazmat"])
        or r["temperature_class"] not in CUBE["temperature_classes"]
    ):
        return False, False
    extra = cfg.get("extra_max_weight_kg")
    w_max = CUBE["max_weight_kg"] if extra is None else min(CUBE["max_weight_kg"], extra)
    known = sorted((x for x in dims_of(r) if x is not None), reverse=True)
    limits = sorted(CUBE["max_item_mm"], reverse=True)
    ok = all(d <= lim for d, lim in zip(known, limits, strict=False))
    ok = ok and (r["weight_kg"] is None or r["weight_kg"] <= w_max)
    if r["has_dims"]:
        return ok, False
    assumed = ok and bool(cfg.get("assume_eligible_if_missing_dims", False))
    return assumed, assumed


def stock_and_abc(out: Out, skus: list[dict], mean_units_day: float) -> None:
    """F3 steps 4-5: ABC class sizes by lines, stock averages and cover."""
    total_lines = sum(r["lines"] for r in skus)
    for cls in ("A", "B", "C"):
        grp = [r for r in skus if r["abc"] == cls]
        out.put(
            f"abc.lines.{cls}.n_skus",
            len(grp),
            "SKUs",
            "F3 step 4: count of SKUs in the class (A if cum share before < 0.80, B < 0.95; I6)",
        )
        out.put(f"abc.lines.{cls}.sku_share", len(grp) / len(skus), "-", "F3 step 4: n / all SKUs")
        out.put(
            f"abc.lines.{cls}.line_share",
            sum(r["lines"] for r in grp) / total_lines,
            "-",
            "F3 step 4: Σ lines of class / Σ lines",
        )
    units = sum(r["avg_stock"] for r in skus)
    out.put(
        "stock.n_skus_in_stock",
        sum(r["avg_stock"] > 0 for r in skus),
        "SKUs",
        "F3 step 5: count(avg_stock > 0)",
    )
    out.put("stock.avg_units", units, "units", "F3 step 5: Σ_sku avg_stock (I49, I50)")
    out.put(
        "stock.avg_cube_m3",
        sum(r["avg_stock"] * r["unit_cube_m3"] for r in skus),
        "m3",
        "F3 step 5: Σ_sku mean units × unit_cube",
    )
    out.put(
        "stock.cover_days",
        units / mean_units_day,
        "d",
        "F3 step 5: Σ stock units / mean daily units shipped",
    )
    dead = [r for r in skus if r["dead_stock"]]
    out.put(
        "stock.dead_stock_skus",
        len(dead),
        "SKUs",
        "F3 step 5: count(last_stock > 0 and no shipped line after period_end − 180 d) (I50)",
    )
    out.put(
        "stock.dead_stock_cube_m3",
        sum((r["last_stock"] * r["unit_cube_m3"] for r in dead), 0.0),
        "m3",
        "F3 step 5: Σ_dead SKUs last_stock × unit_cube (stock of the last snapshot, I50)",
    )


def eligibility(
    out: Out, p: str, skus: list[dict], cfg: dict[str, Any]
) -> tuple[float, float, set[str]]:
    """F5 eligibility for cube_asrs under `cfg` (EligibilityCfg): shares by lines, stock cube
    (mean snapshot) and SKU count → (share_lines, assumed_share_lines, eligible SKU ids)."""
    res = {r["sku"]: cube_eligible(r, cfg) for r in skus}
    el = [r for r in skus if res[r["sku"]][0]]
    f, lines = "F5 step 4: ", sum(r["lines"] for r in skus)
    share = out.put(
        p + "share_lines",
        sum(r["lines"] for r in el) / lines,
        "-",
        f + "Σ lines eligible / Σ lines (I5, I10)",
    )
    cube = [r["avg_stock"] * r["unit_cube_m3"] for r in skus]
    elc = sum(c for c, r in zip(cube, skus, strict=True) if res[r["sku"]][0])
    out.put(
        p + "share_stock_cube",
        elc / sum(cube) if sum(cube) else 0.0,  # I10: no stock cube → 0, as the engine
        "-",
        f + "Σ eligible avg_stock × unit_cube / Σ avg_stock × unit_cube (0 if Σ = 0)",
    )
    out.put(
        p + "share_skus",
        len(el) / len(skus),
        "-",
        f + "n eligible SKUs / n SKUs (SKU master + orphan SKUs, I10)",
    )
    out.put(
        p + "n_skus_eligible",
        len(el),
        "SKUs",
        "F5 steps 1-3: count(sorted dims ≤ [600,400,300], weight ≤ limit, not hazmat, "
        "ambient or chilled)",
    )
    out.put(p + "n_skus_total", len(skus), "SKUs", "F5: count of SKUs (master + orphans, I10)")
    assumed = out.put(
        p + "assumed_share_lines",
        sum(r["lines"] for r in el if res[r["sku"]][1]) / lines,
        "-",
        "F5 step 3: Σ lines of SKUs eligible only by assume_eligible_if_missing_dims / Σ lines",
    )
    return share, assumed, {r["sku"] for r in el}


# --- F4 design day and inbound ------------------------------------------------------------------
def design_day(out: Out, daily: pl.DataFrame, lines: pl.DataFrame, basis: dict) -> dict[str, Any]:
    """F4 steps 1-6: P_p per metric, reference day ratios, growth, design weekday and hours.
    dd["flags"]: design-day flags; inbound() appends F_DEFAULT_UPP, demand() writes the key."""
    proj, flows = basis["projection"], basis["flows"]
    op = daily.filter("is_operating")  # candidates: the whole 31-day history (I5)
    gf = out.put(
        "design_day.growth_factor",
        growth_factor(proj["growth_rate"], proj["horizon_years"]),
        "-",
        "App. B growth: (1 + g)^T, T = projection.horizon_years",
    )
    clipped = proj["design_percentile"] > 100  # F4 edge case: above the max → max
    pct = min(proj["design_percentile"], 100.0)
    p = {
        m: out.put(
            f"design_day.p.{m}",
            np.percentile(op[m].to_numpy() * 1.0, pct),
            m,
            f"F4 step 2: P_m = np.percentile(daily {m}, {pct}), operating days",
        )
        for m in METRICS
    }
    ref = int(np.argmin(np.abs(op["lines"].to_numpy() - p["lines"])))  # first date on ties (I7)
    out.put(
        "design_day.reference_date",
        str(op["date"][ref]),
        "date",
        "F4 step 3: argmin_d |lines_d − P_lines| over operating days (earliest on ties, I7)",
    )
    lines_r = op["lines"][ref]
    flags = ["F_PERCENTILE_CLIPPED"] if clipped else []
    dd: dict[str, Any] = {"growth_factor": gf, "flags": flags}
    flags += ["F_SHORT_HISTORY"] if op.height < 60 else []
    for m in METRICS:
        rho = out.put(
            f"design_day.ratio.{m}", op[m][ref] / lines_r, "-", "F4 step 3: m_r / lines_r"
        )
        base = out.put(f"design_day.base.{m}", p["lines"] * rho, m, "F4 step 4: P_lines × ρ_m")
        dd[m] = out.put(f"design_day.{m}", base * gf, m, "F4 step 5: m* × (1 + g)^T")
        drift = abs(base - p[m]) / p[m] if p[m] > 0 else None  # P_m = 0: unbounded (I57)
        if (drift is None and base > 0) or (drift is not None and drift > 0.15):
            flags.append(f"F_RATIO_DRIFT:{m}")
    wk = (
        op.group_by("weekday")
        .agg(pl.col("lines").mean())
        .sort(["lines", "weekday"], descending=[True, False])
    )
    wd = out.put(
        "design_day.design_weekday",
        int(wk["weekday"][0]),
        "0=Mon",
        "F4 step 6: weekday with the highest mean lines (lowest index on ties)",
    )
    shares, dd["intraday_confidence"] = intraday(lines, op, wd)
    for h, s in enumerate(shares):
        out.put(
            f"design_day.intraday_share.h{h:02d}",
            s,
            "-",
            "F3 step 7: timed lines in hour / timed lines on the design weekday, operating days; "
            "default profile if > 20 % of lines, or every line of the design weekday, have no "
            "time (I51)",
        )
        out.put(
            f"design_day.hourly_lines.h{h:02d}",
            s * dd["lines"],
            "lines/h",
            "App. B hourly_lines_h: intraday[design weekday][h] × lines*",
        )
    dd["peak_hour_share"] = out.put(
        "design_day.peak_hour_share", max(shares), "-", "F3 step 7: max_h(intraday_share_h)"
    )
    dd["peak_hour_lines"] = out.put(
        "design_day.peak_hour_lines",
        max(shares) * dd["lines"],
        "lines/h",
        "F4 step 6: max(hourly_lines)",
    )
    dd["return_lines"] = out.put(
        "design_day.return_lines",
        flows["returns_rate"] * dd["lines"],
        "lines",
        "I9: flows.returns_rate × lines*",
    )
    dd["peak_to_average"] = float(np.percentile(op["lines"], 95) / op["lines"].mean())
    dd["n_op"], dd["op"] = op.height, op
    return dd


def intraday(lines: pl.DataFrame, op: pl.DataFrame, wd: int) -> tuple[list[float], str]:
    """F3 step 7 on the design weekday → (24 shares, confidence). Lines without time (local
    00:00:00) are left out of the shares; when they are more than 20 % of all shipped lines, the
    default profile is used instead, flagged L (I51). A design weekday without any timed line
    also takes the default profile, confidence unchanged."""
    no_time = (lines.height - int(lines["has_time"].sum())) / lines.height
    if no_time > NO_TIME_SHARE_MAX:
        return list(DEFAULT_INTRADAY), "L"
    days = op.filter(pl.col("weekday") == wd)["date"].implode()
    timed = lines.filter(pl.col("date").is_in(days) & pl.col("has_time"))
    counts = dict(timed.group_by("hour").len().iter_rows())
    total = sum(counts.values())
    if total == 0:
        return list(DEFAULT_INTRADAY), "H"
    return [counts.get(h, 0) / total for h in range(24)], "H"


def trend(daily: pl.DataFrame) -> tuple[float | None, str]:
    """F3 step 6 trend (I52): CAGR from the mean daily lines of each calendar month (operating
    days only) → (trend_cagr or None, trend_confidence from the calendar months)."""
    month = (pl.col("date").dt.year().cast(pl.Int64) * 12 + pl.col("date").dt.month()).alias("m")
    m = daily.filter("is_operating").group_by(month).agg(pl.col("lines").mean()).sort("m")
    cagr = trend_cagr(m["m"].to_numpy() * 1.0, m["lines"].to_numpy() * 1.0)
    months = calendar_months(daily["date"].min(), daily["date"].max())  # type: ignore[arg-type]
    return cagr, trend_confidence(months)


def order_classes(out: Out, orders: pl.DataFrame, dd: dict[str, Any]) -> None:
    """I15: design orders by packing class = orders* × period share of S and of M+L orders."""
    share_s = float(np.mean((orders["cls"] == "S").to_numpy()))
    dd["orders_S"] = out.put(
        "design_day.orders_S",
        dd["orders"] * share_s,
        "orders",
        "I15: orders* × share of 1-line orders",
    )
    dd["orders_ML"] = out.put(
        "design_day.orders_ML",
        dd["orders"] * (1 - share_s),
        "orders",
        "I15: orders* × share of orders with > 1 line",
    )


def design_stock(out: Out, skus: list[dict], dd: dict[str, Any], basis: dict) -> None:
    """F4 step 7 and F6a inputs: s_i = avg stock_i × peak_stock_factor × (1 + g)^T (I14)."""
    k = basis["projection"]["peak_stock_factor"] * dd["growth_factor"]
    for r in skus:
        r["s"] = r["avg_stock"] * k
        r["sc"] = r["s"] * r["unit_cube_m3"]
        r["manual_class"] = manual_class(r["fits_shelf"], r["sc"])
    out.put(
        "design_day.stock_units",
        sum(r["s"] for r in skus),
        "units",
        "F4 step 7: avg stock units × peak_stock_factor × (1 + g)^T",
    )
    out.put(
        "design_day.stock_cube_m3",
        sum(r["sc"] for r in skus),
        "m3",
        "F4 step 7: avg stock cube × peak_stock_factor × (1 + g)^T",
    )


def inbound(out: Out, skus: list[dict], dd: dict[str, Any], basis: dict) -> dict[str, float]:
    """F4 derived inbound: units_in = mean units out × (1+g)^T + Δstock/yr ÷ days (I12-I13)."""
    flows, gf = basis["flows"], dd["growth_factor"]
    if flows.get("inbound_mode", "derived") != "derived":
        raise NotImplementedError("the oracle sizes the derived inbound only (I56, I77)")
    mean_out = float(dd["op"]["units"].mean())
    units_in = out.put(
        "inbound.units_per_day",
        mean_out * gf + 0.0,
        "units/d",
        "F4: mean units out/day × (1+g)^T + Δstock/yr ÷ operating_days (Δ = 0, I12)",
    )
    total_units = sum(r["units"] for r in skus)
    for r in skus:
        r["units_in"] = units_in * r["units"] / total_units  # I13
        r["pallets_in"] = r["units_in"] / r["upp"]
        full = "full" if r["units_in"] >= r["upp"] else "mixed"  # I13
        r["receipt_lines"] = r["pallets_in"] * RECEIPT_LINES_PER_PALLET[full]
        r["cases_in"] = r["units_in"] / r["upc"]
    pallets = out.put(
        "inbound.pallets_per_day",
        sum(r["pallets_in"] for r in skus),
        "pallets/d",
        "App. B: Σ_sku units_in_sku / units_per_pallet_sku",
    )
    res = {"units": units_in, "pallets": pallets}
    res["receipt_lines"] = out.put(
        "inbound.receipt_lines_per_day",
        sum(r["receipt_lines"] for r in skus),
        "lines/d",
        "F4: Σ pallets_in_sku × (1.0 full | 4 mixed) (I13)",
    )
    res["cases"] = out.put(
        "inbound.cases_per_day",
        sum(r["cases_in"] for r in skus),
        "cases/d",
        "F6c decant driver: Σ_sku units_in_sku / upc_sku (I13 fallbacks)",
    )
    res["trucks"] = out.put(
        "inbound.trucks_per_day",
        pallets / flows["pallets_per_truck"],
        "trucks/d",
        "App. B: pallets_in / pallets_per_truck",
    )
    pf = flows.get("inbound_peak_factor") or dd["peak_to_average"]
    res["peak_factor"] = out.put(
        "inbound.peak_factor", pf, "-", "F4: flows.inbound_peak_factor or P95/mean of daily lines"
    )
    default = sum(r["units_in"] for r in skus if r["default_upp"] and r["units_in"] > 0)
    res["default_upp_share"] = default / units_in if default > 0 else 0.0  # I59, no golden key
    dd["flags"] += ["F_DEFAULT_UPP"] if default > 0 else []
    return res


# --- pipeline -------------------------------------------------------------------------------------
def demand(out: Out, basis: dict, data_dir: Path) -> dict[str, Any]:
    """F3, F4, F5 stages on the canonical parquet files of `data_dir` → F6-F7 context."""
    read = {
        n: pl.read_parquet(data_dir / f"{n}.parquet")
        for n in ("order_lines", "sku_master", "inventory")
    }
    if read["inventory"]["snapshot_date"].n_unique() >= 3:
        raise NotImplementedError("≥ 3 inventory snapshots: OLS Δstock not in the oracle (I12)")
    tz = basis.get("timezone", "Europe/Paris")
    out.sheet = "Profile"
    lines = shipped_lines(read["order_lines"], prepare_sku(read["sku_master"]), tz)
    sku = prepare_sku(with_orphans(read["sku_master"], lines, read["inventory"]))  # R2, I50
    orders = orders_table(lines, basis["flows"])
    ret = read["order_lines"].filter(
        (pl.col("line_status") == "returned") | (pl.col("qty_units") < 0)
    )
    ret = ret.with_columns(pl.col("order_ts").dt.convert_time_zone(tz).dt.date().alias("date"))
    daily = daily_table(lines, orders, ret)
    profile(out, lines, orders, daily)
    skus = sku_table(sku, read["inventory"], lines)
    op = daily.filter("is_operating")
    stock_and_abc(out, skus, float(op["units"].mean()))  # type: ignore[arg-type]
    tr = trend(daily)
    out.put(
        "seasonality.trend_cagr",
        tr[0],
        "-",
        "F3 step 6: exp(12 × OLS slope of log(mean daily lines per calendar month, operating "
        "days)) − 1; None with < 2 months (I52)",
    )
    out.put(
        "seasonality.trend_confidence",
        tr[1],
        "-",
        "F3 step 6 [P]: L if < 24 calendar months, M if 24-36, H if > 36 (I52)",
    )
    out.sheet = "DesignDay"
    dd = design_day(out, daily, lines, basis)
    order_classes(out, orders, dd)
    design_stock(out, skus, dd, basis)
    inb = inbound(out, skus, dd, basis)
    out.put(
        "design_day.flags",
        ",".join(dd["flags"]),
        "-",
        "F4: F_PERCENTILE_CLIPPED if p > 100; F_SHORT_HISTORY if n_op < 60; "
        "F_RATIO_DRIFT:m if |m* − P_m| / P_m > 0.15, or P_m = 0 < m* (I57); "
        "F_DEFAULT_UPP if a SKU with inbound units has no units_per_case × cases_per_pallet (I59)",
    )
    out.sheet = "Eligibility"
    _, _, elig = eligibility(out, "eligibility.cube_asrs.", skus, {})  # family, default cfg
    for r in skus:
        r["elig_cube"] = r["sku"] in elig
    scale = basis["operations"]["operating_days_per_year"] / op.height  # I4, I36
    names = ("line_share", "daily_zone", "replen", "daily_replen", "elig", "cases_e")
    return {
        "basis": basis,
        "dd": dd,
        "inb": inb,
        "skus": skus,
        "lines": lines,
        "daily": daily,
        "g": basis["projection"]["growth_rate"],
        "trend": tr,  # I52
        "orders_y0": float(op["orders"].sum()) * scale,
        "lines_y0": float(op["lines"].sum()) * scale,
    } | {n: {} for n in names}
