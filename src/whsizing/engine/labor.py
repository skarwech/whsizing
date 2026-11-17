"""F6c labor for one world: activities, workloads and design-day hours; staffing in shifts.py.

    days = labor_days(inp, daily, lines)     # once per scenario (data only, world-independent)
    lw = size_labor(inp, tp, days)           # per world, after size_throughput
    labor = labor_result({w: lw_w})          # LaborResult (Ranges, shift table of typ)

`daily` = the F3 daily series (§4.1), `lines` = the F3 shipped lines (`ProfileTables.lines`:
order_id, sku, date, qty_units). The daily workloads use the actual per-day lines per zone
(I17), one-line orders (I15) and A/B units in manual zones (I21), which the daily series does
not hold: `size_scenario` must pass `lines` as well as `daily`.

Rules (docs/INTERPRETATIONS.md): activities, drivers, standards and roles of
`labor_standards.yaml`, Appendix D split (I38); picking per zone at the pick rate, port rate or
station rate without η / oee (I38); decant only for cube_asrs and amr_gtp (F6c table, I23);
replenishment in every family (S2: overflow A/B SKUs, I21); hours_a = workload / productivity
× (1 + pfd); indirect = 0.12 × Σ direct hours (I38). Design-day workloads: inbound values
without peak factor (I22), orders × share of one-line orders (I15), returns_rate × lines (I9).
Daily workloads (operating days, base year): inbound = design inbound / gf (I22; receipts
mode: the day's receipts_pallets and receipts_lines, I64), decant cases = units in that day ×
cases per unit of the eligible SKUs (I13, I23, I64), lines of the day's SKUs per zone,
one-line and other orders of the day, parcels, pallets out, returns_rate × lines, A/B manual
units / units per move.
Trace ids: `<sid>.labor.<activity>.{workload,hours,heads,roster,annual_hours.y<t>}`,
`labor.picking.<zone>.{workload,hours}`, `labor.total.*`, `labor.annual_hours.y<t>`,
`labor.core_fte.y<t>`, `labor.temp_hours.y<t>`, `labor.p50_day_hours`, `labor.core_heads_day`,
`labor.operating_days`, `labor.single_line_share` (I15).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from whsizing.catalog.models import Activity, CatalogParam
from whsizing.design import inbound_by_sku
from whsizing.design.basis import check_basis, growth_factor
from whsizing.engine.inputs import WorldInputs
from whsizing.engine.shifts import (
    Act,
    ActivityWorld,
    LaborWorld,
    labor_result,
    profiles,
    shifts,
    staff,
    totals,
)
from whsizing.engine.throughput import ThroughputWorld
from whsizing.errors import ConfigError, DataQualityError, WhsizingError

__all__ = [
    "ActivityWorld",
    "LaborDays",
    "LaborWorld",
    "daily_hours",
    "labor_days",
    "labor_result",
    "size_labor",
]

MANUAL_ZONES = ("shelving", "pallet_rack")
MAIN_ZONE = {"cube_asrs": "cube_bin", "amr_gtp": "pod_bin"}
ZONE_RATE = {  # I38: port / station rate without oee
    "cube_bin": "cube_asrs.port_rate_lines_h",
    "pod_bin": "amr_gtp.station_rate_lines_h",
    "shelving": "manual_p2p.pick_rate_shelving_lines_h",
    "pallet_rack": "manual_p2p.pick_rate_pallet_lines_h",
}
INBOUND = frozenset({"receiving", "receipt_check", "put_away", "decant", "returns"})
RECEIPTS = ("receipts_units", "receipts_pallets", "receipts_lines")
AB = ("A", "B")
PFD = {"pfd": "data:basis.operations.pfd_allowance"}
IB = "data:design_day.inbound."
SHARE = "labor.indirect_share_of_direct_hours"


@dataclass(frozen=True)
class LaborDays:
    """Per operating day (sorted by date, base year): `lines`, `lines.<zone>`, `orders_S`
    (one-line orders), `orders_ML`, `parcels`, `pallets_out`, `units_ab` (A/B units in manual
    zones, I21), `pallets_in`, `receipt_lines`, `units_in` (units received, for decant cases).
    `single_line_share` = one-line orders / orders over the whole period (I15)."""

    frame: pl.DataFrame
    single_line_share: float


def labor_days(inp: WorldInputs, daily: pl.DataFrame, lines: pl.DataFrame) -> LaborDays:
    """The daily workloads of `inp.scenario` (zones and eligibility do not depend on the world)."""
    counts = ["lines", "parcels", "pallets_out"]
    if inp.design_day.inbound.mode == "receipts":
        counts += RECEIPTS
    _require(daily, {"date", "is_operating", *counts}, "daily")
    _require(lines, {"order_id", "sku", "date", "qty_units"}, "lines")
    _check_series(daily, lines)
    if lines.schema["date"] != daily.schema["date"]:
        raise WhsizingError("labor: the date columns of daily and lines differ in type")
    if not lines["date"].is_in(daily["date"].implode()).fill_null(False).all():
        raise DataQualityError("labor: shipped lines on a date absent from the daily series")
    q = lines["qty_units"].cast(pl.Float64)
    if not (q.is_finite() & (q > 0)).fill_null(False).all():  # I1: qty_units > 0
        raise DataQualityError("labor: shipped lines hold a null or non-positive qty_units")
    zl = lines.join(inp.sku.select("sku", "storage_class", "abc"), on="sku", how="left")
    if zl["storage_class"].null_count():
        raise DataQualityError("labor: shipped lines reference SKUs missing from the SKU frame")
    ab = pl.col("abc").is_in(AB) & pl.col("storage_class").is_in(MANUAL_ZONES)
    by_line = zl.group_by("date").agg(
        *[(pl.col("storage_class") == z).sum().alias(f"lines.{z}") for z in _zones(inp)],
        units_ab=pl.col("qty_units").filter(ab).sum(),
    )
    orders = lines.group_by("order_id").agg(pl.col("date").min(), n=pl.len())  # I1: first date
    by_order = orders.group_by("date").agg(
        orders_S=(pl.col("n") == 1).sum(), orders_ML=(pl.col("n") > 1).sum()
    )
    ops = daily.filter("is_operating").sort("date")
    if ops.is_empty():
        raise DataQualityError("labor: the daily series has no operating day")
    _check_counts(ops, counts)
    frame = (
        ops.select("date", "lines", "parcels", "pallets_out", *_inbound(inp, daily))
        .join(by_line, on="date", how="left")
        .join(by_order, on="date", how="left")
        .with_columns(pl.exclude("date").cast(pl.Float64).fill_null(0.0))
    )
    zone_lines = pl.sum_horizontal(f"lines.{z}" for z in _zones(inp))
    if frame.select((zone_lines != pl.col("lines")).any()).item():
        raise DataQualityError("labor: the daily lines differ from the shipped lines of the day")
    return LaborDays(frame, float((orders["n"] == 1).sum()) / max(orders.height, 1))


def size_labor(inp: WorldInputs, tp: ThroughputWorld, days: LaborDays) -> LaborWorld:
    """F6c for one world; `tp` is the same world's `size_throughput`."""
    check_basis(inp.basis)  # I60: shifts, hours, utilisation (ConfigError naming the field)
    inp.record(
        "labor.operating_days", "Operating days in the daily series", float(days.frame.height),
        "days", "count(is_operating)", {"is_operating": "data:daily.is_operating"},
    )  # fmt: skip
    inp.record(
        "labor.single_line_share", "Share of one-line orders over the period (I15)",
        days.single_line_share, "-", "one-line orders / orders",
        {"order_id": "data:lines.order_id", "date": "data:lines.date"},
    )  # fmt: skip
    outbound, inbound = profiles(inp)
    labor = inp.catalog.labor.activities
    direct: list[Act] = []
    for name, act in labor.items():
        if act.driver is None or (name == "decant" and inp.scenario.family == "manual_p2p"):
            continue  # indirect (share of direct hours); decant "–" for the manual family
        prof = inbound if name in INBOUND else outbound
        if name == "picking":
            direct.append(_picking(inp, tp, days, prof))
        else:
            direct.append(_direct(inp, tp, days, name, act, prof))
    acts = [*direct, _indirect(inp, direct)]
    shift_of_hour, windows = shifts(inp)
    staffed = tuple(staff(inp, a, shift_of_hour, len(windows)) for a in acts)
    return totals(inp, acts, staffed, windows)


def daily_hours(inp: WorldInputs, tp: ThroughputWorld, days: LaborDays) -> dict[str, np.ndarray]:
    """Hours per operating day of the base year (incl. PF&D, no growth) of each activity of one
    world, in `labor_standards.yaml` order with `indirect` last; aligned with `days.frame` rows.
    The same activities as `size_labor` before staffing (F11 back-test: monthly predicted hours).
    Records the same trace nodes as `size_labor`: give it its own `WorldInputs` (own Tracer)."""
    check_basis(inp.basis)
    inp.record(
        "labor.operating_days", "Operating days in the daily series", float(days.frame.height),
        "days", "count(is_operating)", {"is_operating": "data:daily.is_operating"},
    )  # fmt: skip
    inp.record(
        "labor.single_line_share", "Share of one-line orders over the period (I15)",
        days.single_line_share, "-", "one-line orders / orders",
        {"order_id": "data:lines.order_id", "date": "data:lines.date"},
    )  # fmt: skip
    outbound, inbound = profiles(inp)
    direct: list[Act] = []
    for name, act in inp.catalog.labor.activities.items():
        if act.driver is None or (name == "decant" and inp.scenario.family == "manual_p2p"):
            continue
        prof = inbound if name in INBOUND else outbound
        if name == "picking":
            direct.append(_picking(inp, tp, days, prof))
        else:
            direct.append(_direct(inp, tp, days, name, act, prof))
    return {a.name: a.daily for a in [*direct, _indirect(inp, direct)]}


def _picking(inp: WorldInputs, tp: ThroughputWorld, days: LaborDays, profile: np.ndarray) -> Act:
    """Design lines per zone = lines* × zone share (I17; main zone: share_lines, I44); hours at
    the zone's rate (I38); daily = the day's lines of the zone's SKUs."""
    pfd = 1 + inp.basis.operations.pfd_allowance
    main = MAIN_ZONE.get(inp.scenario.family)
    work = hours = 0.0
    daily = np.zeros(days.frame.height)
    for z in _zones(inp):
        share, ref = (
            (inp.eligibility.share_lines, "eligibility.share_lines")
            if z == main
            else (tp.line_share[z], f"throughput.line_share.{z}")
        )
        key, rate = f"labor.picking.{z}", inp.v(ZONE_RATE[z])
        w = inp.record(
            f"{key}.workload", f"Lines picked in {z} (design day)",
            inp.design_day.lines * share, "lines", "lines × zone share",
            {"lines": "data:design_day.lines", "share": inp.tid(ref)},
        )  # fmt: skip
        hours += inp.record(
            f"{key}.hours", f"Picking hours in {z}", w / rate * pfd, "h",
            "workload / rate × (1 + pfd)",
            {"workload": inp.tid(f"{key}.workload"), "rate": f"param:{ZONE_RATE[z]}"} | PFD,
        )  # fmt: skip
        work += w
        daily += days.frame[f"lines.{z}"].to_numpy() / rate * pfd
    zones = _zones(inp)
    work_refs = {z: inp.tid(f"labor.picking.{z}.workload") for z in zones}
    inp.record("labor.picking.workload", "Lines picked", work, "lines", "Σ_zone", work_refs)
    hour_refs = {z: inp.tid(f"labor.picking.{z}.hours") for z in zones}
    inp.record("labor.picking.hours", "Picking hours", hours, "h", "Σ_zone hours", hour_refs)
    refs = {"lines": "data:lines.sku", "zone": "data:sku.storage_class"}
    refs |= {z: f"param:{ZONE_RATE[z]}" for z in zones}
    role = inp.catalog.labor.roles[inp.catalog.labor.activities["picking"].role]
    return Act("picking", "lines", role, work, hours, daily, profile, refs | PFD)


def _direct(
    inp: WorldInputs,
    tp: ThroughputWorld,
    days: LaborDays,
    name: str,
    act: Activity,
    profile: np.ndarray,
) -> Act:
    """An activity with a driver and a standard (not picking): design workload and hours."""
    driver = str(act.driver)
    workload, formula, inputs = _design_workload(inp, tp, days.single_line_share, driver)
    pid = f"labor.{name}"  # a Param block of labor_standards.yaml ...
    if not isinstance(act.standard, CatalogParam):  # ... or `family.<key>`: the family's rate
        pid = str(act.standard).replace("family", inp.scenario.family, 1)
    prod, pfd = inp.v(pid), 1 + inp.basis.operations.pfd_allowance
    w = inp.record(f"labor.{name}.workload", f"{name} workload", workload, driver, formula, inputs)
    h = inp.record(
        f"labor.{name}.hours", f"{name} hours (design day)", w / prod * pfd, "h",
        "workload / productivity × (1 + pfd)",
        {"workload": inp.tid(f"labor.{name}.workload"), "productivity": f"param:{pid}"} | PFD,
    )  # fmt: skip
    daily, refs = _daily_workload(inp, days, driver)
    refs |= {"productivity": f"param:{pid}"} | PFD
    role = inp.catalog.labor.roles[act.role]
    return Act(name, driver, role, w, h, daily / prod * pfd, profile, refs)


def _design_workload(
    inp: WorldInputs, tp: ThroughputWorld, share_s: float, driver: str
) -> tuple[float, str, dict[str, str]]:
    """(design-day workload, formula, trace inputs) of a labor driver."""
    dd, ib = inp.design_day, inp.design_day.inbound
    orders = {"orders": "data:design_day.orders", "share_S": inp.tid("labor.single_line_share")}
    returns = {"lines": "data:design_day.lines", "returns_rate": "data:basis.flows.returns_rate"}
    table = {
        "pallets_in": (ib.pallets_per_day, "inbound pallets_per_day (I22)",
                       {"pallets_in": f"{IB}pallets_per_day"}),
        "receipt_lines": (ib.receipt_lines_per_day, "inbound receipt_lines_per_day (I22)",
                          {"receipt_lines": f"{IB}receipt_lines_per_day"}),
        "cases_in": (tp.cases_in, "cases_in of the eligible SKUs (I23)",
                     {"cases_in": inp.tid("throughput.decant_cases_in")}),
        "replen_moves": (tp.replen_moves, "replen_moves (I21)",
                         {"replen_moves": inp.tid("throughput.replen_moves")}),
        "orders_S": (dd.orders * share_s, "orders × share_S (I15)", orders),
        "orders_ML": (dd.orders * (1 - share_s), "orders × (1 − share_S) (I15)", orders),
        "parcels": (dd.parcels, "parcels", {"parcels": "data:design_day.parcels"}),
        "pallets_out": (dd.pallets_out, "pallets_out",
                        {"pallets_out": "data:design_day.pallets_out"}),
        "return_lines": (dd.lines * inp.basis.flows.returns_rate, "returns_rate × lines (I9)",
                         returns),
    }  # fmt: skip
    if driver not in table:
        raise ConfigError(f"labor_standards.yaml: unknown driver {driver!r}")
    return table[driver]


def _daily_workload(
    inp: WorldInputs, days: LaborDays, driver: str
) -> tuple[np.ndarray, dict[str, str]]:
    """Workload of a driver on each operating day, base year, and the data it comes from."""
    f = days.frame
    if driver in ("pallets_in", "receipt_lines"):
        return f[driver].to_numpy(), _inbound_refs(inp, driver)
    if driver == "cases_in":  # I23, I64: units in × cases per unit of the eligible SKUs (I13)
        per = inbound_by_sku(1.0, inp.sku, inp.params)["cases_in"]
        return f["units_in"].to_numpy() * float(per.filter(inp.sku["eligible"]).sum()), {
            "units": "data:sku.units",
            "mask": "data:sku.eligible",
            "upc": "data:sku.units_per_case",
            "upp": "data:sku.units_per_pallet",
            "cpp": "data:sku.cases_per_pallet",
        } | _inbound_refs(inp, "units_in")
    if driver == "replen_moves":  # I21: A/B units in manual zones / replen_units_per_move
        refs = {"units": "data:lines.qty_units", "sku": "data:lines.sku", "abc": "data:sku.abc",
                "zone": "data:sku.storage_class",
                "units_per_move": "param:manual_p2p.replen_units_per_move"}  # fmt: skip
        return f["units_ab"].to_numpy() / inp.v("manual_p2p.replen_units_per_move"), refs
    if driver == "return_lines":  # I9: returns_rate × lines, not the observed return_lines
        refs = {"lines": "data:daily.lines", "returns_rate": "data:basis.flows.returns_rate"}
        return f["lines"].to_numpy() * inp.basis.flows.returns_rate, refs
    if driver in ("orders_S", "orders_ML"):  # I15, I1: an order counts on its first date
        return f[driver].to_numpy(), {"order_id": "data:lines.order_id", "date": "data:lines.date"}
    return f[driver].to_numpy(), {driver: f"data:daily.{driver}"}  # parcels, pallets_out


def _inbound_refs(inp: WorldInputs, driver: str) -> dict[str, str]:
    """Trace inputs of a daily inbound workload (see `_inbound`)."""
    design = {
        "pallets_in": f"{IB}pallets_per_day",
        "receipt_lines": f"{IB}receipt_lines_per_day",
        "units_in": f"{IB}units_per_day",
    }
    refs = {f"{driver}*": design[driver]}
    if inp.design_day.inbound.mode == "derived":  # I22: design value / gf every day
        return refs | {"growth_rate": "data:design_day.growth_rate",
                       "horizon_years": "data:design_day.horizon_years"}  # fmt: skip
    if driver == "receipt_lines":
        return {"receipt_lines": "data:daily.receipts_lines"}
    share = {"units_in_d": "data:daily.receipts_units", "units_in*": f"{IB}units_per_day"}
    if driver == "pallets_in":  # the day's pallets; null → units × pallets per unit (I64)
        return {"pallets_in": "data:daily.receipts_pallets"} | share | refs
    return share  # units_in: the day's receipts_units


def _indirect(inp: WorldInputs, direct: list[Act]) -> Act:
    """I38: indirect = share × Σ direct hours (no second PF&D), daily and by hour alike."""
    share = inp.v(SHARE)
    w = inp.record(
        "labor.indirect.workload", "Direct hours", sum(a.hours for a in direct), "h",
        "Σ direct hours", {a.name: inp.tid(f"labor.{a.name}.hours") for a in direct},
    )  # fmt: skip
    h = inp.record(
        "labor.indirect.hours", "Indirect hours (design day)", share * w, "h",
        "indirect_share × Σ direct hours",
        {"direct": inp.tid("labor.indirect.workload"), "share": f"param:{SHARE}"},
    )  # fmt: skip
    by_hour = np.sum([a.hours * a.profile for a in direct], axis=0)
    profile = by_hour / w if w > 0 else np.full(24, 1 / 24)
    daily = share * np.sum([a.daily for a in direct], axis=0)
    role = inp.catalog.labor.roles[inp.catalog.labor.activities["indirect"].role]
    refs = {a.name: inp.tid(f"labor.{a.name}.base_hours") for a in direct}
    refs["share"] = f"param:{SHARE}"
    return Act("indirect", "direct_hours", role, w, h, daily, profile, refs)


def _zones(inp: WorldInputs) -> tuple[str, ...]:
    """Picking zones of the family (I17, I39): the main zone of an automated family first."""
    main = MAIN_ZONE.get(inp.scenario.family)
    return (main, *MANUAL_ZONES) if main else MANUAL_ZONES


def _inbound(inp: WorldInputs, daily: pl.DataFrame) -> list[pl.Expr]:
    """Daily inbound `pallets_in`, `receipt_lines` and `units_in` (units received, for decant
    cases). I22: derived inbound is a daily mean → design value / gf every day. Receipts mode
    (I56, I64): the day's receipts_pallets, receipts_lines and receipts_units; a day whose pallet
    count is unknown (null, F3) takes receipts_units_d × pallets* / units_in*, or with
    units_in* = 0 the whole-history pallets per unit (never silently 0)."""
    dd, ib = inp.design_day, inp.design_day.inbound
    if ib.mode == "derived":
        k = 1 / growth_factor(dd.growth_rate, dd.horizon_years)
        return [
            pl.lit(ib.pallets_per_day * k).alias("pallets_in"),
            pl.lit(ib.receipt_lines_per_day * k).alias("receipt_lines"),
            pl.lit(ib.units_per_day * k).alias("units_in"),
        ]
    # ponytail: decant cases follow the day's units; per-SKU case mix of receipts not in daily
    units = pl.col("receipts_units")
    per_unit = ib.pallets_per_day / ib.units_per_day if ib.units_per_day > 0 else None
    if per_unit is None:  # I64: units_in* = 0 → whole-history receipt totals
        known = daily.filter(pl.col("receipts_pallets").is_not_null())
        total = float(known["receipts_units"].sum())
        unknown = daily.filter(pl.col("receipts_pallets").is_null() & (units > 0)).height
        if total <= 0 and unknown:
            raise DataQualityError(
                f"labor: {unknown} receipt day(s) without a pallet count and no receipt with one "
                "to derive pallets per unit from"
            )
        per_unit = float(known["receipts_pallets"].sum()) / total if total > 0 else 0.0
    return [
        pl.col("receipts_pallets").fill_null(units * per_unit).alias("pallets_in"),
        pl.col("receipts_lines").alias("receipt_lines"),
        units.alias("units_in"),
    ]


def _check_series(daily: pl.DataFrame, lines: pl.DataFrame) -> None:
    """One row per date with a known is_operating (F3 daily series); numeric qty_units."""
    dup = daily.filter(pl.col("date").is_duplicated())["date"].unique().sort()
    if dup.len():
        raise DataQualityError(f"labor: the daily series repeats date(s) {dup.head(5).to_list()}")
    if daily["is_operating"].null_count():
        raise DataQualityError("labor: the daily series has a null is_operating")
    if not lines.schema["qty_units"].is_numeric():
        raise DataQualityError(
            f"labor: shipped lines qty_units must be numeric, got {lines.schema['qty_units']}"
        )


def _check_counts(ops: pl.DataFrame, cols: list[str]) -> None:
    """Daily counts are finite and ≥ 0; null only for an unknown receipts_pallets (F3)."""
    bad = [
        c
        for c in cols
        if not (ops[c].is_finite() & (ops[c] >= 0)).fill_null(c == "receipts_pallets").all()
    ]
    if bad:
        raise DataQualityError(f"labor: daily {bad} hold a null, NaN, infinite or negative count")


def _require(df: pl.DataFrame, cols: set[str], name: str) -> None:
    missing = sorted(cols - set(df.columns))
    if missing:
        raise WhsizingError(f"labor: {name} frame lacks column(s) {missing}")
