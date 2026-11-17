"""Writers of the T1.5 golden case: golden_values.json and golden_case.xlsx (G1).

Every value cell of the stage sheets and every column header of the SKUs and DailySeries sheets
carries a comment naming its formula (F1 golden case: "every cell has a comment naming the
formula in Appendix B"). Numbers are written as values, not live Excel formulas.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import xlsxwriter
from tests.golden import oracle as o

CATALOGS = {
    "cube_asrs": o.CUBE,
    "manual_p2p": o.MANUAL,
    "storage_classes": o.STORAGE,
    "area_factors": o.AREA,
    "labor_standards": {k: f"{r} @ {v}/h" for k, (r, v) in o.LABOR.items()},
    "engine": {
        "eta_flow": o.ETA_FLOW,
        "pack_station_oee": o.PACK_STATION_OEE,
        "kwh_per_station_year": o.KWH_PER_STATION_YEAR,
        "packaging_eur_per_order": o.PACKAGING_EUR_PER_ORDER,
        "fixed_energy_kwh_year": o.FIXED_ENERGY_KWH_YEAR,
        "receipt_lines_per_pallet": str(o.RECEIPT_LINES_PER_PALLET),
    },
}
# SKUs sheet: column → formula comment (I<n> = docs/INTERPRETATIONS.md)
SKU_COLS = {
    "sku": "input: sku_master.sku",
    "orphan": "F2 R2: shipped or stocked SKU absent from the SKU master, kept without master "
    "data, never eligible (I10, I50)",
    "length_mm": "input: sku_master.length_mm (null = missing dims, F5 step 3)",
    "width_mm": "input: sku_master.width_mm (null = missing dims, F5 step 3)",
    "height_mm": "input: sku_master.height_mm (null = missing dims, F5 step 3)",
    "weight_kg": "input: sku_master.weight_kg (null = missing weight, F5 step 3)",
    "has_dims": "F5 step 3: length, width, height and weight all non-null (I10)",
    "hazmat": "input: sku_master.hazmat; missing column or null → false (I10)",
    "temperature_class": "input: sku_master.temperature_class; missing or null → ambient (I10)",
    "unit_cube_m3": "l × w × h / 1e9 (§4.1 derived), else input unit_cube_m3, else 0 (I10)",
    "units_per_case": "input: sku_master.units_per_case",
    "upc": "units_per_case, else units_per_pallet / cases_per_pallet, else 1 (I13)",
    "upp": "units_per_pallet, else units_per_case × cases_per_pallet, else 400 (App. D, I13)",
    "avg_stock": "F3 step 5: Σ qty_units over all snapshots / number of snapshots (absent = 0, "
    "I49)",
    "last_stock": "F3 step 5: Σ qty_units in the last snapshot (0 if absent from it, I50)",
    "lines": "F3: count of shipped lines of the SKU over the period (I1, I5)",
    "units": "F3: Σ qty_units of the SKU's shipped lines over the period",
    "abc": "F3 step 4: SKUs by lines, units, avg_stock, unit cube, weight (all descending), "
    "sku (ascending); A if cumulative line share before the SKU < 0.80, B if < 0.95, else C (I6)",
    "dead_stock": "F3 step 5: last_stock > 0 and 0 shipped lines with date > period_end − 180 d "
    "(I50)",
    "elig_cube": "F5 steps 1-3, default EligibilityCfg: sorted dims ≤ [600,400,300], weight ≤ 25, "
    "not hazmat, ambient or chilled, not orphan (I10)",
    "fits_shelf": "F6a: l, w, h known and sorted dims ≤ shelf_item_max_mm [500,400,350] (I10)",
    "s": "F4 step 7: s = avg_stock × peak_stock_factor × (1 + g)^T (I14)",
    "sc": "F6a: stock_cube = s × unit_cube_m3",
    "manual_class": "F6a: pallet_rack if not fits_shelf or sc ≥ 0.6; shelving if sc ≤ 0.04 × 6; "
    "else pallet_rack",
    "units_in": "I13: inbound.units_per_day × units / Σ units",
    "pallets_in": "I13: units_in / upp",
    "receipt_lines": "I13: pallets_in × (1.0 if units_in ≥ upp else 4)",
    "cases_in": "I13: units_in / upc",
}
ZONE_COL = (
    "F6a class in scenario {}: cube_bin if eligible under its EligibilityCfg, else manual_class"
)
DAILY_COLS = {
    "date": "F3 step 1: local date (basis.timezone) of the order's first order_ts (I1)",
    "lines": "F3 step 1: count of shipped lines on the date",
    "units": "F3 step 1: Σ qty_units of shipped lines",
    "cube_m3": "F3 step 1: Σ qty_units × unit_cube_m3 (math.fsum)",
    "weight_kg": "F3 step 1: Σ qty_units × weight_kg (math.fsum)",
    "orders": "F3 step 1: count of shipped orders",
    "parcels": "F3 step 8: Σ_parcel orders max(1, ceil(weight / parcel_max_weight_kg))",
    "pallets_out": "F3 step 8 + I8: count of orders with weight > pallet_order_weight_kg "
    "or cube > pallet_order_cube_m3",
    "orders_S": "F3 step 3: count of 1-line orders",
    "orders_ML": "F3 step 3: count of orders with > 1 line",
    "return_lines": "F3: count of returned or negative lines dated on the date (info, I9)",
    "weekday": "F3: weekday of date, 0 = Monday",
    "is_operating": "App. B: lines ≥ max(1, 0.10 × median(lines_d > 0)) (I2)",
}
EXPLANATION = """
whsizing golden case (T1.5): tiny_golden, typical world, built by tests/golden/build_golden.py.
Source of truth: description.md. Where the spec is silent or ambiguous the rule used is in
docs/INTERPRETATIONS.md (I1, I2, ...). Every value cell (column B of the stage sheets) and every
column header of the SKUs and DailySeries sheets carries a comment naming its formula
(Appendix B / F-section); column D of the stage sheets repeats it. Cells hold values, not live
Excel formulas. Keys equal tests/golden/golden_values.json.
Empty value cell = None (IRR undefined, payback not reached, queue values of an unstable pool,
trend CAGR with fewer than 2 months with operating days, I52).

Sheets
  Inputs       basis (golden_basis.yaml), scenarios (golden_scenarios.yaml) and catalog typ
               values typed in from the spec.
  SKUs         per SKU: data fallbacks (has_dims, upc, upp), abc (by lines), elig_cube (F5,
               default config), s = design stock units, sc = design stock cube m3, manual_class
               (F6a), derived inbound per day, zone_<scenario> = storage/picking zone.
  DailySeries  one row per local date (Europe/Paris); is_operating per Appendix B.
  Profile      F3: series stats, EIQ, ABC, stock, shipment split, weekday means.
  DesignDay    F4: P95, reference-day ratios, (1+g)^T, hourly lines, design stock, inbound.
  Eligibility  F5: cube_asrs shares with the default config; S2 shares with the scenario config.
  Storage      F6a: positions, levels, area per class; S2 manual classes = overflow zone.
  Throughput   F6b: lambda, lambda_e, pickers, forklifts, decant, ports, robots, utilisation.
  Labor        F6c: hours, heads, roster per activity; annual hours, core FTE, temp hours.
  Area         F6d: zones, pack stations, fit, docks.
  Queue        F6e: Erlang-C on pack stations and ports; F6 flags per scenario.
  Finance      F7: capex, opex y1..yT, TCO, cost per line; S2 vs S0: delta cash flows, NPV, IRR,
               payback.

How to check a value by hand: pick a key, read its formula in the comment, find the inputs on
the same sheet (or Inputs / SKUs / DailySeries), recompute. Example: S2.equipment.ports =
ceil(S2.throughput.lambda_e / (350 × 0.85) + S2.equipment.decant_port_load_peak_h).
"""


def write_json(out: o.Out, path: Path) -> None:
    text = json.dumps(out.values(), indent=1, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _flat(d: dict, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for k, v in d.items():
        rows += _flat(v, f"{prefix}{k}.") if isinstance(v, dict) else [(f"{prefix}{k}", v)]
    return rows


def _table(wb: Any, name: str, rows: list[dict], cols: dict[str, str], bold: Any) -> None:
    """One row per record; every column header carries its formula comment."""
    ws = wb.add_worksheet(name)
    ws.write_row(0, 0, list(cols), bold)
    for j, formula in enumerate(cols.values()):
        ws.write_comment(0, j, formula)
    for i, r in enumerate(rows, 1):
        ws.write_row(i, 0, [r.get(k) for k in cols])


def _inputs(wb: Any, c: dict, bold: Any) -> None:
    inputs = [("basis." + k, v) for k, v in _flat(c["basis"])]
    inputs += [(f"scenarios.{sd['id']}.{k}", v) for sd in c["scenarios"] for k, v in _flat(sd)]
    inputs += [(f"catalog.{n}.{k}", v) for n, cat in CATALOGS.items() for k, v in cat.items()]
    ws = wb.add_worksheet("Inputs")
    ws.set_column(0, 0, 55)
    ws.write_row(0, 0, ["input", "value"], bold)
    for i, (k, v) in enumerate(inputs, 1):
        ws.write_string(i, 0, k)
        ws.write(i, 1, v if isinstance(v, int | float | bool) or v is None else str(v))


def write_xlsx(out: o.Out, c: dict, path: Path) -> None:
    """Explanation, Inputs, SKUs and DailySeries sheets, then one sheet per stage
    (key | value | unit | formula) with a comment naming the formula on every value cell."""
    wb = xlsxwriter.Workbook(str(path))
    wb.set_properties({"title": "whsizing golden case", "created": datetime(2026, 11, 8)})
    bold = wb.add_format({"bold": True})
    ex = wb.add_worksheet("Explanation")
    ex.set_column(0, 0, 110)
    for i, line in enumerate(EXPLANATION.strip().splitlines()):
        ex.write_string(i, 0, line)
    _inputs(wb, c, bold)
    zones = {f"zone_{sd['id']}": ZONE_COL.format(sd["id"]) for sd in c["scenarios"]}
    _table(wb, "SKUs", c["skus"], SKU_COLS | zones, bold)
    days = c["daily"].with_columns(pl.col("date").cast(pl.String))
    if set(days.columns) != set(DAILY_COLS):
        raise ValueError(
            f"DailySeries columns without a formula: {set(days.columns) ^ set(DAILY_COLS)}"
        )
    _table(wb, "DailySeries", days.to_dicts(), DAILY_COLS, bold)
    sheets: dict[str, Any] = {}
    for sheet, key, value, unit, formula in out.rows:
        if sheet not in sheets:
            sheets[sheet] = [wb.add_worksheet(sheet), 1]
            sheets[sheet][0].write_row(0, 0, ["key", "value", "unit", "formula"], bold)
            sheets[sheet][0].set_column(0, 0, 48)
            sheets[sheet][0].set_column(3, 3, 80)
        ws, row = sheets[sheet]
        sheets[sheet][1] += 1
        ws.write_string(row, 0, key)
        if isinstance(value, bool):
            ws.write_boolean(row, 1, value)
        elif value is not None:
            ws.write(row, 1, value)
        ws.write_comment(row, 1, formula)
        ws.write_row(row, 2, [unit, formula])
    wb.close()
