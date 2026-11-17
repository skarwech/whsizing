"""G1b: golden oracle remediation of the W1 audit (docs/audit/G1.md): missing SKU data, λ_sla
window, decant at the ports, F6 flag table and queue, discriminating golden basis, workbook
formula comments. Every test is part of T1.5 (the golden case the engine is compared with)."""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import openpyxl
import polars as pl
import pytest
import yaml
from tests.golden import build_golden, demand, oracle

HERE = Path(__file__).resolve().parent
DATA = HERE / "tiny_golden"
FORMULA = re.compile(r"[=×/Σ+−<>≤≥*(]")  # every stage comment writes a formula
ROLES = (
    "no_dims",
    "no_weight",
    "hazmat",
    "frozen",
    "chilled",
    "no_upc",
    "no_upp",
    "no_case",
    "long_no_dim",  # length null, width 2000 mm: a known dim violates the cube limits
    "heavy_no_dim",  # height null, weight 40 kg: the known weight violates the 25 kg cap
    "bogus_cube",  # full dims, unit_cube_m3 inconsistent with l × w × h
)
N_ORPHAN = 40  # ≈ 2 % of shipped lines, the defect injector's orphan share (F1 step 9)


def _golden() -> dict[str, Any]:
    return json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))


def _flags(g: dict[str, Any], sid: str) -> list[str]:
    return g[f"{sid}.flags"].split(",")


@pytest.fixture(scope="module")
def defect_data(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, dict]]:
    """tiny_golden with realistic SKU-master defects (§4.1 nullable columns, F2 R2/R7) on SKUs
    that are cube-eligible for S2, plus N_ORPHAN order lines of one SKU absent from the master."""
    out = tmp_path_factory.mktemp("defects")
    for name in ("order_lines", "inventory"):
        shutil.copy(DATA / f"{name}.parquet", out / f"{name}.parquet")
    sku = pl.read_parquet(DATA / "sku_master.parquet")
    lines = pl.read_parquet(DATA / "order_lines.parquet")
    n_lines = lines.filter(pl.col("line_status") == "shipped").group_by("sku").len()
    rows = sku.join(n_lines, on="sku", how="left").sort("sku").to_dicts()
    ok = [
        r
        for r in rows
        if (r["len"] or 0) > 0
        and r["weight_kg"] <= 2.0
        and oracle.fits((r["length_mm"], r["width_mm"], r["height_mm"]), (600, 400, 300))
    ]
    victims: dict[str, dict] = dict(zip(ROLES, ok, strict=False))
    ids = {role: v["sku"] for role, v in victims.items()}
    col = pl.col("sku")
    sku = sku.with_columns(
        pl.when(col.is_in([ids["no_dims"], ids["long_no_dim"]]))
        .then(None)
        .otherwise(pl.col("length_mm"))
        .alias("length_mm"),
        pl.when(col == ids["long_no_dim"])
        .then(2000.0)
        .otherwise(pl.col("width_mm"))
        .alias("width_mm"),
        pl.when(col == ids["heavy_no_dim"])
        .then(None)
        .otherwise(pl.col("height_mm"))
        .alias("height_mm"),
        pl.when(col == ids["no_weight"])
        .then(None)
        .when(col == ids["heavy_no_dim"])
        .then(40.0)
        .otherwise(pl.col("weight_kg"))
        .alias("weight_kg"),
        (col == ids["hazmat"]).alias("hazmat"),
        pl.when(col == ids["frozen"])
        .then(pl.lit("frozen"))
        .when(col == ids["chilled"])
        .then(pl.lit("chilled"))
        .otherwise(None)
        .alias("temperature_class"),
        pl.when(col.is_in([ids["no_upc"], ids["no_case"]]))
        .then(None)
        .otherwise(pl.col("units_per_case"))
        .alias("units_per_case"),
        pl.when(col.is_in([ids["no_upp"], ids["no_case"]]))
        .then(None)
        .otherwise(pl.col("units_per_pallet"))
        .alias("units_per_pallet"),
        pl.when(col == ids["no_case"])
        .then(None)
        .otherwise(pl.col("cases_per_pallet"))
        .alias("cases_per_pallet"),
        pl.when(col == ids["chilled"])
        .then(None)
        .when(col == ids["bogus_cube"])
        .then(999.0)
        .otherwise(pl.col("unit_cube_m3"))
        .alias("unit_cube_m3"),
    )
    sku.write_parquet(out / "sku_master.parquet")
    orphan = lines.filter(pl.col("line_status") == "shipped").head(N_ORPHAN)
    orphan = orphan.with_columns(pl.lit("ORPHAN-SKU").alias("sku"))
    pl.concat([lines, orphan]).write_parquet(out / "order_lines.parquet")
    return out, victims


def _scenarios(tmp: Path, assume: bool, **elig: float) -> Path:
    scen = yaml.safe_load((HERE / "golden_scenarios.yaml").read_text(encoding="utf-8"))
    scen["scenarios"][1]["eligibility"] |= {"assume_eligible_if_missing_dims": assume, **elig}
    path = tmp / f"scenarios_{assume}_{len(elig)}.yaml"
    path.write_text(yaml.safe_dump(scen), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def golden_run() -> tuple[dict[str, Any], dict[str, Any]]:
    out, c = build_golden.run()
    return out.values(), c


# --- item 1: missing data ------------------------------------------------------------------------
def test_T1_5_missing_dims_hazmat_temperature_are_ineligible_and_case_fallbacks_hold(
    defect_data: tuple[Path, dict[str, dict]],
) -> None:
    """F5 steps 2-3 (default assume_eligible_if_missing_dims = false) and I13 fallbacks."""
    data_dir, v = defect_data
    out, c = build_golden.run(data_dir=data_dir)
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    for role in ("no_dims", "no_weight", "hazmat", "frozen", "long_no_dim", "heavy_no_dim"):
        r = rows[v[role]["sku"]]
        assert not r["elig_cube"], role
        assert r["zone_S2"] != "cube_bin", role
    assert rows[v["chilled"]["sku"]]["zone_S2"] == "cube_bin"  # chilled is allowed in the cube
    nodims = rows[v["no_dims"]["sku"]]
    assert not nodims["has_dims"] and not nodims["fits_shelf"]
    assert nodims["manual_class"] == "pallet_rack"  # F6a: does not (verifiably) fit a shelf bin
    noweight = rows[v["no_weight"]["sku"]]  # F6a fits_shelf_bin(dims): the weight is not needed
    assert noweight["fits_shelf"] and oracle.fits(demand.dims_of(noweight), (500, 400, 350))
    assert g["eligibility.cube_asrs.n_skus_eligible"] == 91 - 6
    assert g["S2.eligibility.n_skus_eligible"] == _golden()["S2.eligibility.n_skus_eligible"] - 6
    assert g["S2.eligibility.assumed_share_lines"] == 0.0
    vol = v["chilled"]["length_mm"] * v["chilled"]["width_mm"] * v["chilled"]["height_mm"] / 1e9
    assert rows[v["chilled"]["sku"]]["unit_cube_m3"] == pytest.approx(vol)  # l × w × h / 1e9
    b = v["bogus_cube"]  # §4.1 unit_cube_m3 is derived: l × w × h / 1e9 wins over the input
    vol = b["length_mm"] * b["width_mm"] * b["height_mm"] / 1e9
    assert rows[b["sku"]]["unit_cube_m3"] == pytest.approx(vol)
    upc, upp = rows[v["no_upc"]["sku"]], rows[v["no_upp"]["sku"]]
    assert upc["upc"] == v["no_upc"]["units_per_pallet"] / v["no_upc"]["cases_per_pallet"]
    assert upp["upp"] == v["no_upp"]["units_per_case"] * v["no_upp"]["cases_per_pallet"]
    none = rows[v["no_case"]["sku"]]
    assert (none["upc"], none["upp"]) == (1.0, 400)
    assert none["cases_in"] == pytest.approx(none["units_in"])  # 1 unit per case, no ÷ 0
    assert g["profile.n_lines"] == 1881 + N_ORPHAN  # the orphan lines are kept (R2)
    assert g["inbound.cases_per_day"] > 0


def test_T1_5_assume_eligible_if_missing_dims_raises_F_ELIG_ASSUMED(
    defect_data: tuple[Path, dict[str, dict]], tmp_path: Path
) -> None:
    data_dir, v = defect_data
    out, c = build_golden.run(data_dir=data_dir, scen_path=_scenarios(tmp_path, True))
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    missing = [rows[v[k]["sku"]] for k in ("no_dims", "no_weight")]
    assert all(r["zone_S2"] == "cube_bin" for r in missing)
    assert not any(r["elig_cube"] for r in missing)  # family keys keep the default config
    for role in ("long_no_dim", "heavy_no_dim"):  # a KNOWN violation stays ineligible (Kleene)
        assert rows[v[role]["sku"]]["zone_S2"] != "cube_bin", role
    assert rows["ORPHAN-SKU"]["zone_S2"] == "pallet_rack"  # orphans: never assumed eligible
    share = sum(r["lines"] for r in missing) / g["profile.n_lines"]
    assert g["S2.eligibility.assumed_share_lines"] == pytest.approx(share)
    assert f"F_ELIG_ASSUMED:{share:.6f}" in _flags(g, "S2")
    assert g["S2.eligibility.n_skus_eligible"] == _golden()["S2.eligibility.n_skus_eligible"] - 4


def test_T1_5_orphan_skus_are_kept_never_eligible_and_counted_in_every_share(
    defect_data: tuple[Path, dict[str, dict]],
) -> None:
    """F2 R2 (kept; has_dims=false) + F5 step 4: orphan lines stay in the share denominators
    and are picked in the manual pallet_rack zone (I10, I17)."""
    out, c = build_golden.run(data_dir=defect_data[0])
    g, rows = out.values(), {r["sku"]: r for r in c["skus"]}
    orphan = rows["ORPHAN-SKU"]
    assert orphan["orphan"] and not orphan["has_dims"] and orphan["lines"] == N_ORPHAN
    assert not orphan["elig_cube"] and orphan["zone_S2"] == orphan["zone_S0"] == "pallet_rack"
    assert sum(r["lines"] for r in c["skus"]) == g["profile.n_lines"]  # no line dropped
    assert g["S2.eligibility.n_skus_total"] == 101  # 100 master SKUs + 1 orphan
    for p, eligible in (("eligibility.cube_asrs.", "elig_cube"), ("S2.eligibility.", "zone_S2")):
        num = sum(r["lines"] for r in c["skus"] if r[eligible] in (True, "cube_bin"))
        assert g[p + "share_lines"] == pytest.approx(num / g["profile.n_lines"]), p
    op = c["daily"].filter("is_operating")["date"].implode()
    zone = {sku: r["zone_S2"] for sku, r in rows.items()}
    picked = c["lines"].filter(pl.col("date").is_in(op))["sku"].replace_strict(zone)
    share = float((picked == "pallet_rack").mean())  # type: ignore[arg-type]
    lam = g["S2.throughput.lambda"]
    assert g["S2.throughput.lambda.pallet_rack"] == pytest.approx(lam * share)


# --- item 2: λ_sla -------------------------------------------------------------------------------
def test_T1_5_sla_window_explicit_derived_midnight_and_equal_times() -> None:
    svc = {"cutoff_time": "15:00", "carrier_departure_time": "18:30"}
    assert oracle.sla_window_hours(svc) == 3.5
    assert oracle.sla_window_hours(svc | {"sla_window_hours": None}) == 3.5
    assert oracle.sla_window_hours(svc | {"sla_window_hours": 7.0}) == 7.0
    night = {"cutoff_time": "22:00", "carrier_departure_time": "02:00"}
    assert oracle.sla_window_hours(night) == 4.0
    same = {"cutoff_time": "15:00", "carrier_departure_time": "15:00"}
    assert oracle.sla_window_hours(same) == 24.0  # I16: departure the next day
    with pytest.raises(ValueError, match="sla_window_hours"):
        oracle.sla_window_hours(svc | {"sla_window_hours": 0.0})


def test_T1_5_explicit_sla_window_drives_lambda_and_dock_shortfall_flag(tmp_path: Path) -> None:
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    basis["service"]["sla_window_hours"] = 7.0
    basis["building"]["dock_doors_in"] = 0  # F6d: doors required 1 > 0 available
    path = tmp_path / "basis.yaml"
    path.write_text(yaml.safe_dump(basis), encoding="utf-8")
    g = build_golden.run(basis_path=path)[0].values()
    assert g["S0.throughput.lambda_sla"] == pytest.approx(0.6 * g["design_day.lines"] / 7.0)
    assert g["S0.queue.packing.t_h"] == 3.5  # F6e: sla_window_hours × 0.5
    assert "F_DOCK_SHORTFALL" in _flags(g, "S0") and "F_DOCK_SHORTFALL" in _flags(g, "S2")
    assert "F_DOCK_SHORTFALL" not in _flags(_golden(), "S0")


# --- item 3: decant at the ports -----------------------------------------------------------------
def test_T1_5_decant_station_hours_add_to_the_ports(
    golden_run: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """F6b: decant_station_hours = cases_in / decant_cases_per_h → adds to ports (I23)."""
    g, c = golden_run
    cases_e = sum(r["cases_in"] for r in c["skus"] if r["zone_S2"] == "cube_bin")
    assert g["S2.labor.decant.workload"] == pytest.approx(cases_e)  # overflow SKUs not decanted
    assert cases_e < g["inbound.cases_per_day"]
    dsh = g["S2.equipment.decant_station_hours"]
    assert dsh == pytest.approx(g["S2.labor.decant.workload"] / 90)
    peak = dsh * g["inbound.peak_factor"] * 0.2
    assert g["S2.equipment.decant_port_load_peak_h"] == pytest.approx(peak)
    load = g["S2.throughput.lambda_e"] / (350 * 0.85) + peak
    assert g["S2.equipment.ports"] == math.ceil(load)
    assert g["S2.utilisation.ports"] == pytest.approx(load / g["S2.equipment.ports"])
    assert g["S2.queue.ports.offered_load"] == pytest.approx(load)


def test_T1_5_zero_eligible_lines_degenerate_to_manual(tmp_path: Path) -> None:
    """F6 edge case: zero eligible lines → the automated scenario degenerates to manual, with
    the automation capex at zero and F_ELIG_LOW (I48): S2 then costs what S0 costs."""
    scen = _scenarios(tmp_path, False, extra_max_weight_kg=1e-9)
    g = build_golden.run(scen_path=scen)[0].values()
    assert g["S2.eligibility.share_lines"] == 0.0 and "F_ELIG_LOW" in _flags(g, "S2")
    assert g["S2.equipment.ports"] == g["S2.equipment.robots"] == 0
    assert g["S2.storage.cube_bin.positions"] == 0
    assert g["S2.capex.controls"] == g["S0.capex.controls"]  # no cube controls_fixed_eur
    for k in ("area.total", "capex.total", "opex.y1.software", "opex.y1.total", "finance.tco"):
        assert g[f"S2.{k}"] == pytest.approx(g[f"S0.{k}"]), k
    assert g["S2.finance.npv"] == pytest.approx(0.0, abs=1e-6)


def test_T1_5_three_inventory_snapshots_are_not_silently_flat(tmp_path: Path) -> None:
    """F3 step 5 / F4 derived inbound: with ≥ 3 snapshots Δstock is an OLS slope, which the
    oracle does not compute; it must raise, not return Δstock = 0 (I12)."""
    for name in ("order_lines", "sku_master"):
        shutil.copy(DATA / f"{name}.parquet", tmp_path / f"{name}.parquet")
    inv = pl.read_parquet(DATA / "inventory.parquet")
    snaps = [inv.with_columns(pl.col("snapshot_date") - pl.duration(days=d)) for d in (0, 30, 60)]
    pl.concat(snaps).write_parquet(tmp_path / "inventory.parquet")
    with pytest.raises(NotImplementedError, match="I12"):
        build_golden.run(data_dir=tmp_path)


# --- item 4: flags and queue ---------------------------------------------------------------------
def test_T1_5_flag_table_and_low_confidence_count() -> None:
    g = _golden()
    dd = g["design_day.flags"].split(",")
    assert {"F_SHORT_HISTORY", "F_RATIO_DRIFT:pallets_out"} <= set(dd)
    assert _flags(g, "S0") == ["F_HEIGHT_LIMIT:pallet_rack", *dd, "F_LOW_CONFIDENCE:30"]
    s2 = ["F_NO_FIT", "F_HEIGHT_LIMIT:pallet_rack", "F_SCALE_LOW", "F_ROBOT_DENSITY", *dd]
    assert _flags(g, "S2") == [*s2, "F_LOW_CONFIDENCE:50"]
    manual, cube = (
        oracle.low_confidence_params("manual_p2p"),
        oracle.low_confidence_params("cube_asrs"),
    )
    # I47: catalog Param blocks read; + engine.pack_station_oee (both), kWh/station (S2 only)
    assert len(set(manual)) == len(manual) == g["S0.low_confidence_params"] == 19 + 9 + 1 + 1
    assert len(set(cube)) == len(cube) == g["S2.low_confidence_params"] == 21 + 17 + 9 + 1 + 2
    assert "manual_p2p.software_eur_year" not in cube  # S2 pays the cube software only
    assert "finance.kwh_per_station_year" not in manual  # S0 has no stations
    density = g["S2.equipment.robots_per_grid_m2"]
    assert density == pytest.approx(
        g["S2.equipment.robots"] / g["S2.storage.cube_bin.grid_area_m2"]
    )
    assert density > 0.05  # I46: cube_asrs.max_robots_per_m2 → F_ROBOT_DENSITY


def test_T1_5_erlang_queue_and_sla_flags() -> None:
    q = oracle.erlang_queue(1, 8.0, 10.0, 0.5)  # M/M/1: P_wait = ρ, W_q = ρ / (μ − λ)
    assert q["p_wait"] == pytest.approx(0.8)
    assert q["w_q_h"] == pytest.approx(0.4)
    assert q["p_wait_gt_t"] == pytest.approx(0.8 * math.exp(-1.0))
    bad = oracle.erlang_queue(2, 20.0, 10.0, 1.0)
    assert (bad["stable"], bad["p_wait"], bad["c_min"]) == (False, None, 3)
    svc = {"cutoff_time": "15:00", "carrier_departure_time": "18:30"}
    c: dict[str, Any] = {"basis": {"service": svc}, "pack_stations": 1}
    flags = build_golden.queue(oracle.Out(), "S9", c, {"ports": 0}, {"pack": (9.0, 10.0)})
    assert flags == ["F_SLA_RISK:packing"]  # 0.9 × exp(−1 × 1.75) = 0.156 > 5 %
    flags = build_golden.queue(oracle.Out(), "S9", c, {"ports": 0}, {"pack": (10.0, 10.0)})
    assert flags == ["F_UNSTABLE:packing"]
    g = _golden()
    svc = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))["service"]
    sla_rate = svc["same_day_share"] * g["design_day.orders"] / oracle.sla_window_hours(svc)
    assert sla_rate > g["S0.area.peak_hour_orders"]  # the SLA window binds on the golden case
    for sid in ("S0", "S2"):
        p = f"{sid}.queue.packing."  # F6e: λ_s = arrival rate in the SLA window (I45)
        lam_s = max(g[f"{sid}.area.peak_hour_orders"], sla_rate)
        assert g[p + "arrival_rate_h"] == pytest.approx(lam_s)
        a = g[p + "arrival_rate_h"] / g[p + "service_rate_h"]
        assert g[p + "offered_load"] == pytest.approx(a)
        assert g[p + "p_wait"] == pytest.approx(oracle.erlang_c(g[p + "servers"], a))


# --- item 5: discriminating golden basis ---------------------------------------------------------
def test_T1_5_golden_basis_exercises_pallet_parcel_and_overflow_branches() -> None:
    g = _golden()
    assert g["daily.pallets_out.max"] > 0 and g["design_day.pallets_out"] > 0
    assert g["shipment.mean_parcels_per_order"] > 1
    assert g["S0.labor.shipping_pallet.hours"] > 0 and g["S2.labor.shipping_pallet.hours"] > 0
    assert g["S2.storage.overflow.shelving.n_skus"] > 0
    assert g["S2.equipment.pickers.shelving"] > 0
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    sku = demand.prepare_sku(pl.read_parquet(DATA / "sku_master.parquet"))
    lines = demand.shipped_lines(pl.read_parquet(DATA / "order_lines.parquet"), sku, "Europe/Paris")
    orders, fl = demand.orders_table(lines, basis["flows"]), basis["flows"]
    heavy = orders["weight_kg"].to_numpy() > fl["pallet_order_weight_kg"]
    bulky = orders["cube_m3"].to_numpy() > fl["pallet_order_cube_m3"]
    assert (heavy & ~bulky).any() and (bulky & ~heavy).any()  # both F3 step 8 triggers
    pallet = orders["pallets"].to_numpy() > 0
    assert (pallet == (heavy | bulky)).all()  # weight-only and cube-only orders ship as pallets
    assert g["shipment.pallet_share_orders"] == pytest.approx(float(np.mean(heavy | bulky)))
    assert np.max(orders["parcels"].to_numpy()) >= 3  # ceil(weight / 5 kg) beyond 2


# --- item 6: workbook formula comments -----------------------------------------------------------
def test_T1_5_workbook_headers_and_stage_cells_name_their_formula() -> None:
    wb = openpyxl.load_workbook(HERE / "golden_case.xlsx")
    for name in ("SKUs", "DailySeries"):
        ws = wb[name]
        headers = [cell for cell in ws[1] if cell.value is not None]
        assert len(headers) >= 10, name
        missing = [h.value for h in headers if not (h.comment and h.comment.text.strip())]
        assert not missing, f"{name} headers without a formula comment: {missing}"
    vague = []
    for ws in wb.worksheets:
        if ws["A1"].value != "key":
            continue
        for key, value in ws.iter_rows(min_row=2, max_col=2):
            text = value.comment.text if value.comment else ""
            if not FORMULA.search(text):
                vague.append((key.value, text))
    assert not vague, f"comments that name a section, not a formula: {vague[:5]}"
