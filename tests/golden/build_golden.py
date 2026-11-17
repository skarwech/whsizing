"""Build the T1.5 golden case: run the oracle on tiny_golden, write golden_values.json and
golden_case.xlsx. Sizing (F6) and finance (F7) stages live here; formulas live in oracle.py,
F3-F5 stages in demand.py, writers in workbook.py.

    uv run python -m tests.golden.build_golden      # rewrites tests/golden/golden_*

Typical world only. Interpretations: docs/INTERPRETATIONS.md (I<n>).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import yaml
from tests.golden import demand as d
from tests.golden import oracle as o
from tests.golden import workbook

HERE = Path(__file__).resolve().parent
DATA = HERE / "tiny_golden"
ZONES = ("cube_bin", "pallet_rack", "shelving")
FAMILIES = ("manual_p2p", "cube_asrs")
M, CU, A = o.MANUAL, o.CUBE, o.AREA
RATE = {
    "shelving": M["pick_rate_shelving_lines_h"],
    "pallet_rack": M["pick_rate_pallet_lines_h"],
    "cube_bin": CU["port_rate_lines_h"],
}
DRIVER = {
    "receiving": "inbound.pallets_per_day (I22)",
    "receipt_check": "inbound.receipt_lines_per_day (I22)",
    "put_away": "inbound.pallets_per_day (I22)",
    "decant": "Σ cases_in of scenario-eligible SKUs (I23)",
    "replenishment": "units* × manual A/B unit share / replen_units_per_move (I21)",
    "picking": "Σ_zone lines* × zone line share (I17)",
    "packing_S": "design_day.orders_S (I15)",
    "packing_ML": "design_day.orders_ML (I15)",
    "shipping_parcel": "design_day.parcels",
    "shipping_pallet": "design_day.pallets_out (I8)",
    "returns": "returns_rate × lines* (I9)",
    "indirect": "Σ_a direct hours_a (I38)",
}
ZONE_FORMULA = {
    "receiving_staging": "pallets_in × inbound_peak_factor × 1.5 m2 × staging_days 1.0",
    "shipping_staging": "(pallets_out* + parcels* / 40) × 1.5 m2",
    "packing": "pack_stations × 12 m2 (I26)",
    "ports": "ports × m2_per_port 20 (I26)",
    "storage": "= storage.total_area_m2 (F6a)",
    "returns": "return_lines* × 0.05 + 30",
    "equipment": "robots × 2.0 + 40 (I26)",
    "amenities": "labor.total.roster × 4 + 150 (inside the footprint, I27)",
    "circulation": "0.25 × Σ zones except storage (I27)",
}
CAPEX_FORMULA = {  # (manual_p2p, cube_asrs)
    "storage": (
        "pallet_rack.positions × 90 + shelving.positions × 12 (I29)",
        "cube_bin.positions × 40 + grid_area_m2 × 650 (I30)",
    ),
    "equipment": ("carts × 1500 + forklifts × 35000", "robots × 35000 + ports × 60000"),
    "controls": ("wms_adaptation_fixed_eur = 50000 (I29)", "controls_fixed_eur = 150000"),
    "building_works": ("area.total × 60 (I29)", "area.total × 60 + grid_area_m2 × 20 (I30)"),
    "overflow": (
        "= 0 (the manual family has no overflow zone)",
        "overflow pallet positions × 90 + shelving bins × 12 + carts × 1500 + forklifts × 35000",
    ),
    "integration_commissioning": ("(0.05 + 0.02) × equipment (I31)", "(0.10 + 0.05) × equipment"),
    "contingency": ("0.10 × Σ items above (I31)", "0.10 × Σ items above (I31)"),
}
OPEX_FORMULA = {
    "labor": "[Σ_a annual_hours_a,t × cost(role_a) × (1 + shift_premium) + temp_hours_t × "
    "cost_operator × (1 + temp_premium)] × (1 + wage_inflation)^(t−1) (I33)",
    "maintenance": "maintenance_share × capex.equipment (+ 0.04 × overflow carts, forklifts; I34)",
    "energy": "(robots × 1200 + ports × 1500 + forklifts × 4500 + 20000) kWh × price × "
    "(1 + energy_inflation)^(t−1) (I32)",
    "software": "= software_eur_year of the family (manual 15000, cube 40000), flat (I35)",
    "consumables": "Σ_d orders_d × 252 / n_op × (1 + g)^t × 0.9 (I35)",
    "rent": "area.total × rent_eur_m2_year (rent_mode footprint, I35)",
    "renewal": "renewal_share × capex.equipment if t = equipment_life_years else 0 (I35)",
}

TRUCKS_FORMULA = {
    "in": "trucks_per_day × inbound_peak_factor × peak_hour_share_inbound (0.2)",
    "out": "(pallets_out* + parcels* / 40) / pallets_per_truck × peak_hour_share",
}
QUEUE_FORMULA = {
    "servers": "c = pool size",
    "arrival_rate_h": "λ_s",
    "service_rate_h": "μ per server",
    "offered_load": "a = λ_s / μ",
    "stable": "a < c",
    "t_h": "t = sla_window_hours × 0.5",
    "p_wait": "P_wait = Erlang-C(c, a) (Erlang-B recursion), None if a ≥ c",
    "w_q_h": "W_q = P_wait / (cμ − λ_s)",
    "p_wait_gt_t": "P(W > t) = P_wait × exp(−(cμ − λ_s) × t)",
    "c_min": "ceil(a) + 1 if a ≥ c else None",
}
POOL_FORMULA = {
    "packing": "c = pack_stations, λ_s = max(peak_hour_orders, same_day_share × orders* / "
    "sla_window_hours), μ = pack_rate × 0.85",
    "ports": "c = ports, μ = port_rate × oee, λ_s = λ_e + decant_port_load_peak_h × μ",
}


# --- F6 sizing -----------------------------------------------------------------------------------
def geometry(cls: str, h_clear: float) -> tuple[float, float, int, float]:
    """F6a levels inputs per class: usable height (m), level pitch (m), level cap, density/m²."""
    if cls == "pallet_rack":
        pitch = (M["pallet_load_height_mm"] + M["beam_pitch_mm"]) / 1000
        usable = h_clear - M["top_clearance_m"]
        return usable, pitch, M["pallet_max_levels"], M["pallet_rack_positions_per_m2_per_level"]
    if cls == "shelving":
        pitch = M["bin_pitch_mm"] / 1000
        return (
            M["shelf_max_height_m"],
            pitch,
            M["ergonomic_max_levels"],
            M["shelving_bins_per_m2_per_level"],
        )
    pitch = CU["level_height_mm"] / 1000
    return h_clear - CU["grid_overhead_m"], pitch, CU["max_levels"], CU["bins_per_m2_per_level"]


def positions(out: o.Out, p: str, cls: str, grp: list[dict]) -> float:
    """F6a positions of one class (pallet positions or bins)."""
    if cls == "pallet_rack":
        pal = out.put(
            p + "pallets",
            sum(o.pallets_i(r["s"], r["upp"]) for r in grp),
            "pallets",
            "App. B pallets_i: Σ ceil(s_i / units_per_pallet_i)",
        )
        faces = out.put(
            p + "pick_faces",
            sum(r["abc"] in M["pick_face_classes"] for r in grp),
            "positions",
            "F6a pick-face policy: count of A/B SKUs in the class × 1 (I11)",
        )
        pos = o.pallet_positions(pal, M["pallet_rack_fill_factor"], faces)
        return out.put(p + "positions", pos, "positions", "F6a: Σ pallets_i / fill + pick faces")
    if cls == "shelving":
        net, fill = o.STORAGE["shelf_bin_net_cube_m3"], M["shelving_fill_factor"]  # I63 (6)
        pos = sum(o.shelf_bins_i(r["sc"], net, fill) for r in grp)
        return out.put(p + "positions", pos, "bins", "F6a: Σ max(1, ceil(sc_i / (0.040 × fill)))")
    raw = out.put(
        p + "bins_raw",
        sum(o.cube_bins_i(r["sc"]) for r in grp),
        "bins",
        "F6a cube_bin: Σ bins_i (1/4 per mixed-bin SKU, I43)",
    )
    pos = raw * (1 + CU["empty_bin_reserve"])
    return out.put(p + "positions", pos, "bins", "F6a: Σ bins_i × (1 + empty_bin_reserve)")


def storage(out: o.Out, sid: str, fam: str, skus: list[dict], basis: dict) -> dict[str, Any]:
    """F6a positions, levels and area per class; manual classes are the overflow zone in S2."""
    h_clear = basis["building"]["clear_height_m"]
    stored = [r for r in skus if r["s"] > 0]  # I14: zero design stock → no position
    res: dict[str, Any] = {"area": 0.0, "height_limited": [], "grid": 0.0}
    for cls in ZONES:
        if cls == "cube_bin" and fam != "cube_asrs":
            continue
        overflow = fam != "manual_p2p" and cls != "cube_bin"
        p = f"{sid}.storage.{'overflow.' if overflow else ''}{cls}."
        grp = [r for r in stored if r[f"zone_{sid}"] == cls]
        out.put(
            p + "n_skus", len(grp), "SKUs", "F6a: count of SKUs with s_i > 0 in the class (I14)"
        )
        res[cls] = positions(out, p, cls, grp)
        usable, pitch, cap, dens = geometry(cls, h_clear)
        lv = out.put(
            p + "levels",
            o.levels(usable, pitch, cap),
            "levels",
            "App. B levels: min(cap, floor(usable height / pitch))",
        )
        if cls != "shelving" and o.fit_levels(usable, pitch) < cap:  # I40, I63 (11)
            res["height_limited"].append(cls)
        area = o.class_area(res[cls], lv, dens)
        if cls == "cube_bin":
            res["grid"] = out.put(
                p + "grid_area_m2", area, "m2", "F6a A_grid: bins / (levels × bpm2)"
            )
            area *= 1 + CU["service_aisle_share"]
        res["area"] += out.put(p + "area_m2", area, "m2", "App. B area_class (cube: A_grid × 1.08)")
    out.put(f"{sid}.storage.total_area_m2", res["area"], "m2", "F6a: Σ class areas")
    return res


def lambdas(out: o.Out, sid: str, c: dict, share_e: float) -> float:
    """F6b λ = max(peak_hour_lines / η_flow, lines_same_day / sla_window), λ_e, λ_o (I16)."""
    dd, svc, p = c["dd"], c["basis"]["service"], f"{sid}.throughput."
    window = o.sla_window_hours(svc)
    lam_peak = out.put(
        p + "lambda_peak",
        dd["peak_hour_lines"] / o.ETA_FLOW,
        "lines/h",
        "F6b: peak_hour_lines / η_flow",
    )
    lam_sla = out.put(
        p + "lambda_sla",
        svc["same_day_share"] * dd["lines"] / window,
        "lines/h",
        "F6b: same_day_share × lines* / sla_window_hours (I16)",
    )
    lam = out.put(p + "lambda", max(lam_peak, lam_sla), "lines/h", "App. B λ: max(λ, λ_sla)")
    out.put(p + "lambda_e", lam * share_e, "lines/h", "App. B λ_e: λ × share_lines_eligible")
    out.put(p + "lambda_o", lam - lam * share_e, "lines/h", "App. B λ_o: λ − λ_e")
    return lam


def cube_equipment(out: o.Out, sid: str, c: dict, eq: dict, lam_e: float) -> None:
    """F6b cube_asrs: decant at the ports in the inbound peak hour (I23), ports, robots."""
    q, inb = f"{sid}.equipment.", c["inb"]
    dsh = out.put(
        q + "decant_station_hours",
        c["cases_e"][sid] / CU["decant_cases_per_h"],
        "h/d",
        "F6b: decant_station_hours = cases_in (eligible) / decant_cases_per_h (I23)",
    )
    decant = out.put(
        q + "decant_port_load_peak_h",
        dsh * inb["peak_factor"] * A["peak_hour_share_inbound"],
        "ports",
        "I23: decant_station_hours × inbound_peak_factor × peak_hour_share_inbound (0.2)",
    )
    load = lam_e / (CU["port_rate_lines_h"] * CU["oee"]) + decant
    eq["ports"] = out.put(
        q + "ports",
        o.ceil_div(load, 1.0),
        "-",
        "F6b + I23: ceil(λ_e / (port_rate × oee) + decant_port_load_peak_h)",
    )
    eq["port_load"] = load
    pres = out.put(
        q + "bin_presentations_h",
        lam_e / CU["lines_per_bin_presentation"],
        "bins/h",
        "F6b: λ_e / lines_per_bin_presentation",
    )
    work, rcap = pres * CU["dig_factor"], CU["robot_bins_per_h"] * CU["robot_availability"]
    eq["robots"] = out.put(
        q + "robots",
        o.ceil_div(work, rcap),
        "-",
        "F6b: ceil(bin_pres_h × dig / (robot_bins_h × avail))",
    )
    eq["util"]["ports"] = load / eq["ports"] if eq["ports"] else 0.0
    eq["util"]["robots"] = work / (eq["robots"] * rcap) if eq["robots"] else 0.0


def throughput(out: o.Out, sid: str, fam: str, c: dict, share_e: float) -> dict[str, Any]:
    """F6b equipment: pickers by zone, forklifts, ports and cube robots; bottleneck (I17-I20)."""
    dd, inb, q = c["dd"], c["inb"], f"{sid}.equipment."
    lam = lambdas(out, sid, c, share_e)
    eq: dict[str, Any] = {"util": {}, "ports": 0, "robots": 0}
    pickers, load = 0, 0.0
    for z in ("shelving", "pallet_rack"):
        lam_z = out.put(
            f"{sid}.throughput.lambda.{z}",
            lam * c["line_share"][sid][z],
            "lines/h",
            "F6b: λ × period line share of the manual zone (I17)",
        )
        cap = RATE[z] * M["eta_pick"]
        pickers += out.put(
            q + f"pickers.{z}",
            o.ceil_div(lam_z, cap),
            "-",
            "App. B pickers: ceil(λ_zone / (pick_rate × η_pick))",
        )
        load += lam_z / cap
    eq["pickers"] = out.put(q + "pickers_peak", pickers, "-", "F6b: Σ_zone pickers_zone (I17)")
    eq["carts"] = out.put(q + "carts", pickers, "-", "F6b: carts = pickers_peak")
    eq["util"]["pickers"] = load / pickers if pickers else 0.0
    moves = (
        inb["pallets"] * inb["peak_factor"] * A["peak_hour_share_inbound"]
        + (dd["pallets_out"] + c["replen"][sid]) * dd["peak_hour_share"]
    )
    out.put(q + "forklift_moves_peak_h", moves, "moves/h", "F6b + I18: in + out + replen per hour")
    cap = M["forklift_moves_h"]
    eq["forklifts"] = out.put(q + "forklifts", o.ceil_div(moves, cap), "-", "F6b: ceil(moves / 16)")
    eq["util"]["forklifts"] = moves / (eq["forklifts"] * cap) if eq["forklifts"] else 0.0
    if fam == "cube_asrs":
        cube_equipment(out, sid, c, eq, lam * share_e)
    for name, u in eq["util"].items():
        out.put(f"{sid}.utilisation.{name}", u, "-", "F6b: load / (count × capacity) (I20)")
    worst = max(eq["util"], key=lambda k: eq["util"][k])
    out.put(f"{sid}.bottleneck", worst, "-", "F6b: argmax utilisation (I20)")
    return eq


def workloads(c: dict, sid: str) -> None:
    """Zones per SKU, zone line shares, eligible decant cases, design replenishment moves and
    daily workloads of a scenario (I17, I21, I23)."""
    skus, dd, op, elig = c["skus"], c["dd"], c["dd"]["op"], c["elig"][sid]
    for r in skus:  # F6a class: cube_bin if eligible in the scenario, else manual class (I43)
        r[f"zone_{sid}"] = "cube_bin" if r["sku"] in elig else r["manual_class"]
    c["cases_e"][sid] = sum(r["cases_in"] for r in skus if r["sku"] in elig)
    zmap = pl.DataFrame(
        {
            "sku": [r["sku"] for r in skus],
            "zone": [r[f"zone_{sid}"] for r in skus],
            "ab": [r["abc"] in ("A", "B") for r in skus],
        }
    )
    ln = c["lines"].join(zmap, on="sku").filter(pl.col("date").is_in(op["date"].implode()))
    agg = [(pl.col("zone") == z).sum().alias(z) for z in ZONES]
    manual_ab = (pl.col("zone") != "cube_bin") & pl.col("ab")
    agg.append(pl.col("qty_units").filter(manual_ab).sum().alias("units_ab"))
    per_day = op.select("date").join(ln.group_by("date").agg(agg), on="date", how="left")
    per_day = per_day.fill_null(0).sort("date")
    total = sum(float(per_day[z].sum()) for z in ZONES)
    c["line_share"][sid] = {z: float(per_day[z].sum()) / total for z in ZONES}
    c["daily_zone"][sid] = {z: per_day[z].to_numpy() * 1.0 for z in ZONES}
    ab_share = float(per_day["units_ab"].sum()) / float(op["units"].sum())
    rpm = M["replen_units_per_move"]
    c["replen"][sid] = dd["units"] * ab_share / rpm  # I21
    c["daily_replen"][sid] = per_day["units_ab"].to_numpy() / rpm


def components(c: dict, sid: str, fam: str) -> list[tuple[str, str, str, float, float, Any]]:
    """F6c / App. D activities: (activity, zone, role, standard/h, design workload, daily base)."""
    dd, inb, op, rr = c["dd"], c["inb"], c["dd"]["op"], c["basis"]["flows"]["returns_rate"]
    flat = np.full(op.height, 1.0 / dd["growth_factor"])  # I22: flat inbound, without growth
    lab = o.LABOR
    comps = [
        (a, "", *lab[a], inb[k], flat * inb[k])
        for a, k in (
            ("receiving", "pallets"),
            ("receipt_check", "receipt_lines"),
            ("put_away", "pallets"),
        )
    ]
    if fam == "cube_asrs":
        cases = c["cases_e"][sid]  # I23
        comps.append(("decant", "", "operator", CU["decant_cases_per_h"], cases, flat * cases))
    replen = ("replenishment", "", *lab["replenishment"], c["replen"][sid], c["daily_replen"][sid])
    comps.append(replen)
    for z in ZONES:
        if z != "cube_bin" or fam == "cube_asrs":
            wl = dd["lines"] * c["line_share"][sid][z]
            comps.append(("picking", z, "operator", RATE[z], wl, c["daily_zone"][sid][z]))
    for a, k in (
        ("packing_S", "orders_S"),
        ("packing_ML", "orders_ML"),
        ("shipping_parcel", "parcels"),
        ("shipping_pallet", "pallets_out"),
    ):
        comps.append((a, "", *lab[a], dd[k], op[k].to_numpy() * 1.0))
    comps.append(("returns", "", *lab["returns"], dd["return_lines"], op["lines"].to_numpy() * rr))
    return comps


def activities(out: o.Out, sid: str, fam: str, c: dict, pfd: float) -> dict[str, dict[str, Any]]:
    """F6c design-day hours per activity (zones summed) and daily base hours; indirect share."""
    acts: dict[str, dict[str, Any]] = {}
    for a, z, role, rate, wl, daily in components(c, sid, fam):
        h = o.labor_hours(wl, rate, pfd)
        if z:
            out.put(f"{sid}.labor.{a}.{z}.workload", wl, "lines", "I17: lines* × zone line share")
            out.put(f"{sid}.labor.{a}.{z}.hours", h, "h", "App. B hours: workload / rate × (1+pfd)")
        act = acts.setdefault(a, {"role": role, "workload": 0.0, "hours": 0.0, "daily": 0.0})
        act["workload"] += wl
        act["hours"] += h
        act["daily"] = act["daily"] + o.labor_hours(1.0, rate, pfd) * np.asarray(daily, dtype=float)
    direct = sum(v["hours"] for v in acts.values())
    daily = o.INDIRECT_SHARE * sum(v["daily"] for v in acts.values())
    acts["indirect"] = {
        "role": "lead",
        "workload": direct,
        "hours": o.INDIRECT_SHARE * direct,
        "daily": daily,
    }
    return acts


def labor(out: o.Out, sid: str, fam: str, c: dict) -> dict[str, Any]:
    """F6c heads and roster on the design day; annual hours, core FTE, temp hours (I4, I19, I25)."""
    ops, years = c["basis"]["operations"], range(1, c["basis"]["finance"]["horizon_years"] + 1)
    if ops["shifts_per_day"] != 1:
        raise NotImplementedError("the oracle sizes one shift only (I19)")
    paid, util, g = (
        ops["paid_hours_per_person_day"],
        ops["utilisation"],
        c["basis"]["projection"]["growth_rate"],
    )
    scale = ops["operating_days_per_year"] / c["dd"]["n_op"]  # I4
    acts = activities(out, sid, fam, c, ops["pfd_allowance"])
    res: dict[str, Any] = {"roster": 0.0, "annual": {}, "role": {}, "temp": []}
    for a, v in acts.items():
        p = f"{sid}.labor.{a}."
        out.put(p + "workload", v["workload"], "-", f"F6c driver: workload = {DRIVER[a]}")
        out.put(p + "hours", v["hours"], "h", "App. B hours_a (indirect: 0.12 × direct hours)")
        out.put(
            p + "heads",
            o.heads(v["hours"], paid, util),
            "heads",
            "App. B heads_a: h / (paid × util)",
        )
        hs = o.shift_heads(v["hours"], ops["hours_per_shift"], util)
        res["roster"] += out.put(
            p + "roster",
            hs * (1 + ops["absenteeism"]),
            "heads",
            "F6c: max(1, h / (hours_per_shift × util)) × (1 + abs) (I19)",
        )
        base = float(v["daily"].sum()) * scale
        res["annual"][a] = [
            out.put(
                p + f"annual_hours.y{t}",
                base * (1 + g) ** t,
                "h",
                "App. B: Σ_d hours_a,d × (1+g)^t × days/yr ÷ observed (I4)",
            )
            for t in years
        ]
        res["role"][a] = v["role"]
    p = f"{sid}.labor."
    total_h = out.put(
        p + "total.hours",
        sum(v["hours"] for v in acts.values()),
        "h",
        "Σ_a hours_a (incl. indirect)",
    )
    out.put(
        p + "total.heads",
        o.heads(total_h, paid, util),
        "heads",
        "App. B heads: total.hours / (paid × util)",
    )
    out.put(p + "total.roster", res["roster"], "heads", "App. B roster: Σ_a roster_a")
    day_h = sum(v["daily"] for v in acts.values())
    p50 = out.put(
        p + "p50_day_hours",
        float(np.percentile(day_h, 50)),
        "h",
        "F6c: np.percentile(Σ_a hours_a,d, 50) over operating days (I25)",
    )
    out.put(
        p + "core_heads_day",
        o.heads(p50, paid, util),
        "heads",
        "F6c: p50_day_hours / (paid × util) (I25)",
    )
    temp0 = float(np.maximum(0.0, day_h - p50).sum()) * scale
    fte_div = ops["annual_paid_hours_per_fte"] * util
    for t in years:
        ah = sum(x[t - 1] for x in res["annual"].values())
        out.put(p + f"annual_hours.y{t}", ah, "h", "App. B: Σ_a annual_hours_a,t")
        out.put(p + f"core_fte.y{t}", ah / fte_div, "FTE", "App. B core_fte: h / (1607 × util)")
        res["temp"].append(
            out.put(
                p + f"temp_hours.y{t}",
                temp0 * (1 + g) ** t,
                "h",
                "App. B: Σ_d max(0, hours_d − P50) scaled (I25)",
            )
        )
    return res


def zones(c: dict, st: dict, eq: dict, roster: float) -> dict[str, float]:
    """F6d zone areas (I24, I26, I27)."""
    dd, inb = c["dd"], c["inb"]
    z = {
        "receiving_staging": inb["pallets"]
        * inb["peak_factor"]
        * A["m2_per_pallet_staged"]
        * A["staging_days"],
        "shipping_staging": c["ship_pallets"] * A["m2_per_pallet_staged"],
        "packing": c["pack_stations"] * M["m2_per_pack_station"],
        "ports": eq["ports"] * CU["m2_per_port"],
        "storage": st["area"],
        "returns": dd["return_lines"] * A["m2_per_return_line_day"] + A["returns_fixed_m2"],
        "equipment": eq["robots"] * CU["m2_per_robot_parking"] + A["maintenance_fixed_m2"],
        "amenities": roster * A["m2_per_head_amenities"] + A["amenities_fixed_m2"],
    }
    z["circulation"] = A["circulation_share"] * sum(v for k, v in z.items() if k != "storage")
    return z


def area(out: o.Out, sid: str, c: dict, st: dict, eq: dict, roster: float) -> dict[str, Any]:
    """F6d area budget, pack stations, fit and docks."""
    dd, inb, b, p = c["dd"], c["inb"], c["basis"], f"{sid}.area."
    s_share = dd["orders_S"] / dd["orders"]
    rate = 1 / (s_share / o.LABOR["packing_S"][1] + (1 - s_share) / o.LABOR["packing_ML"][1])
    pho = out.put(
        p + "peak_hour_orders",
        dd["orders"] * dd["peak_hour_share"],
        "orders/h",
        "I24: orders* × peak_hour_share",
    )
    out.put(p + "pack_rate", rate, "orders/h", "I24: 1 / (s_S / 55 + (1 − s_S) / 25)")
    c["pack_stations"] = out.put(
        p + "pack_stations",
        o.ceil_div(pho, rate * o.PACK_STATION_OEE),
        "-",
        "F6d: ceil(peak_hour_orders / (pack_rate × oee))",
    )
    c["ship_pallets"] = dd["pallets_out"] + dd["parcels"] / A["parcels_per_pallet_equiv"]
    for k, v in zones(c, st, eq, roster).items():
        out.put(p + k, v, "m2", f"F6d {k}: {ZONE_FORMULA[k]}")
    total = out.put(p + "total", sum(zones(c, st, eq, roster).values()), "m2", "F6d: Σ zones")
    bm2 = b["building"]["area_m2"]
    out.put(p + "fit", total <= bm2, "-", "F6d: total ≤ building.area_m2")
    out.put(p + "utilisation", total / bm2, "-", "F6d: total / building area")
    out.put(p + "deficit_m2", max(0.0, total - bm2), "m2", "App. B deficit: max(0, total − area)")
    fl = b["flows"]
    trucks = {
        "in": inb["trucks"] * inb["peak_factor"] * A["peak_hour_share_inbound"],
        "out": c["ship_pallets"] / fl["pallets_per_truck"] * dd["peak_hour_share"],
    }
    svc = b["service"]  # F6e packing pool λ_s: arrival rate in the SLA window, as ports (I45)
    lam_s = max(pho, svc["same_day_share"] * dd["orders"] / o.sla_window_hours(svc))
    res: dict[str, Any] = {"total": total, "pack": (lam_s, rate * o.PACK_STATION_OEE)}
    for k, tr in trucks.items():
        out.put(f"{sid}.docks.trucks_{k}_peak_h", tr, "trucks/h", f"I28: {TRUCKS_FORMULA[k]}")
        res[k] = out.put(
            f"{sid}.docks.{k}",
            o.docks(tr, fl["truck_dwell_hours"], fl["dock_utilisation"]),
            "doors",
            "App. B docks: ceil(trucks_peak_h × dwell / dock_util)",
        )
    return res


def queue(out: o.Out, sid: str, c: dict, eq: dict, ar: dict) -> list[str]:
    """F6e Erlang-C on pack stations and ports (I45) → F_UNSTABLE / F_SLA_RISK flags."""
    t_h = o.sla_window_hours(c["basis"]["service"]) * 0.5
    pools = {"packing": (c["pack_stations"], *ar["pack"])} if c["pack_stations"] else {}
    if eq["ports"]:  # a pool with no server has no load (ceil_div gives 0 only for load 0)
        mu = CU["port_rate_lines_h"] * CU["oee"]
        pools["ports"] = (eq["ports"], eq["port_load"] * mu, mu)
    flags = []
    for name, (servers, lam, mu) in pools.items():
        q = o.erlang_queue(servers, lam, mu, t_h)
        for k, v in q.items():
            formula = f"F6e {k}: {QUEUE_FORMULA[k]}; {POOL_FORMULA[name]} (I45)"
            out.put(f"{sid}.queue.{name}.{k}", v, "-", formula)
        flags += [] if q["stable"] else [f"F_UNSTABLE:{name}"]
        flags += [f"F_SLA_RISK:{name}"] if (q["p_wait_gt_t"] or 0.0) > 0.05 else []
    return flags


def flags(out: o.Out, sid: str, fam: str, c: dict, r: dict[str, Any]) -> None:
    """F6 flags table in table order (I46); value after ':' where the spec attaches one."""
    b, st = c["basis"], r["st"]
    f = ["F_NO_FIT"] if r["m2"] > b["building"]["area_m2"] else []
    f += [f"F_HEIGHT_LIMIT:{k}" for k in st["height_limited"]]
    f += ["F_ELIG_LOW"] if r["share_e"] < 0.5 else []
    f += [f"F_ELIG_ASSUMED:{r['assumed']:.6f}"] if r["assumed"] > 0 else []
    low_scale = fam == "cube_asrs" and c["dd"]["lines"] < CU["min_scale_lines_day"]
    f += ["F_SCALE_LOW"] if low_scale else []
    if fam == "cube_asrs":  # F_ROBOT_DENSITY, cap = cube_asrs.max_robots_per_m2 (I46)
        density = out.put(
            f"{sid}.equipment.robots_per_grid_m2",
            r["eq"]["robots"] / st["grid"] if st["grid"] else 0.0,
            "robots/m2",
            "F6b: robots / A_grid (F_ROBOT_DENSITY if > max_robots_per_m2 0.05, I46)",
        )
        f += ["F_ROBOT_DENSITY"] if density > CU["max_robots_per_m2"] else []
    doors = b["building"]
    short = r["ar"]["in"] > doors["dock_doors_in"] or r["ar"]["out"] > doors["dock_doors_out"]
    f += ["F_DOCK_SHORTFALL"] if short else []
    f += r["queue"] + c["dd"]["flags"]
    n_low = out.put(
        f"{sid}.low_confidence_params",
        len(o.low_confidence_params(fam)),
        "params",
        "F6 F_LOW_CONFIDENCE: count of confidence-L Params read: "
        + ", ".join(o.low_confidence_params(fam))
        + " (I47)",
    )
    f += [f"F_LOW_CONFIDENCE:{n_low}"] if n_low else []
    out.put(
        f"{sid}.flags",
        ",".join(f),
        "-",
        "F6 flags in table order: F_NO_FIT if area.total > building; F_HEIGHT_LIMIT:class (I40); "
        "F_ELIG_LOW if share_e < 0.5; F_ELIG_ASSUMED:assumed_share_lines; F_SCALE_LOW if "
        "lines* < min_scale; F_ROBOT_DENSITY if robots / A_grid > 0.05; F_DOCK_SHORTFALL if "
        "docks > doors; F_UNSTABLE / F_SLA_RISK (I45); "
        "design-day flags; F_LOW_CONFIDENCE:n (I46, I47)",
    )


# --- F7 finance ----------------------------------------------------------------------------------
def capex(out: o.Out, sid: str, fam: str, st: dict, eq: dict, total_m2: float) -> dict[str, Any]:
    """F7 capex items, year 0 (I29-I31)."""
    manual_eq = eq["carts"] * M["per_cart_eur"] + eq["forklifts"] * M["per_forklift_eur"]
    store = (
        st["pallet_rack"] * M["per_pallet_position_eur"] + st["shelving"] * M["per_shelf_bin_eur"]
    )
    if fam == "manual_p2p":
        cat, items = (
            M,
            {"storage": store, "equipment": manual_eq, "controls": M["wms_adaptation_fixed_eur"]},
        )
    else:
        cube_store = (
            st["cube_bin"] * CU["per_bin_eur"] + st["grid"] * CU["grid_structure_per_m2_eur"]
        )
        cube_eq = eq["robots"] * CU["per_robot_eur"] + eq["ports"] * CU["per_port_eur"]
        cat, items = (
            CU,
            {"storage": cube_store, "equipment": cube_eq, "controls": CU["controls_fixed_eur"]},
        )
    items["building_works"] = total_m2 * M["building_works_per_m2_eur"]
    if fam == "cube_asrs":  # F7: + floor preparation × A_grid (I30)
        items["building_works"] += st["grid"] * CU["floor_prep_per_m2_eur"]
    items["overflow"] = 0.0 if fam == "manual_p2p" else store + manual_eq
    shares = cat["integration_share"] + cat["commissioning_share"]
    items["integration_commissioning"] = shares * items["equipment"]
    items["contingency"] = cat["contingency_share"] * sum(items.values())
    for k, v in items.items():
        formula = CAPEX_FORMULA[k][FAMILIES.index(fam)]
        out.put(f"{sid}.capex.{k}", v, "EUR", f"F7 capex {k}: {formula}")
    total = out.put(f"{sid}.capex.total", sum(items.values()), "EUR", "App. B capex: Σ items")
    maint = cat["maintenance_share_of_equipment_capex"] * items["equipment"]
    if fam != "manual_p2p":
        maint += M["maintenance_share_of_equipment_capex"] * manual_eq  # I34
    return {
        "total": total,
        "equipment": items["equipment"],
        "maintenance": maint,
        "life": cat["equipment_life_years"],
        "renewal_share": cat["renewal_share"],
    }


def opex_year(c: dict, fam: str, lab: dict, eq: dict, cap: dict, m2: float, t: int) -> dict:
    """F7 opex items of year t (I32-I35)."""
    b = c["basis"]
    f, g = b["finance"], b["projection"]["growth_rate"]
    cost, wf = f["labor_cost_eur_h"], (1 + f["wage_inflation"]) ** (t - 1)
    role_h = sum(lab["annual"][a][t - 1] * cost[o.ROLES[r]] for a, r in lab["role"].items())
    temp = lab["temp"][t - 1] * cost["operator"] * (1 + f["temp_premium"])  # I33
    kwh = (
        eq["robots"] * CU["kwh_per_robot_year"]
        + eq["ports"] * o.KWH_PER_STATION_YEAR
        + eq["forklifts"] * M["kwh_per_forklift_year"]
        + o.FIXED_ENERGY_KWH_YEAR
    )
    rent_m2 = {"footprint": m2, "full_building": b["building"]["area_m2"], "none": 0.0}
    return {
        "labor": (role_h * (1 + f.get("shift_premium", 0.0)) + temp) * wf,
        "maintenance": cap["maintenance"],
        "energy": kwh * f["energy_price_eur_kwh"] * (1 + f["energy_inflation"]) ** (t - 1),
        "software": (M if fam == "manual_p2p" else CU)["software_eur_year"],
        "consumables": c["orders_y0"] * (1 + g) ** t * o.PACKAGING_EUR_PER_ORDER,
        "rent": rent_m2[b["building"].get("rent_mode", "footprint")]
        * b["building"]["rent_eur_m2_year"],
        "renewal": cap["renewal_share"] * cap["equipment"] if t == cap["life"] else 0.0,
    }


def finance(
    out: o.Out, sid: str, fam: str, c: dict, lab: dict, eq: dict, cap: dict, m2: float
) -> list[float]:
    """F7 opex years 1..T, TCO and cost per line of one scenario."""
    f = c["basis"]["finance"]
    r, horizon = f["discount_rate"], f["horizon_years"]
    flows = []
    for t in range(1, horizon + 1):
        items = opex_year(c, fam, lab, eq, cap, m2, t)
        for k, v in items.items():
            out.put(f"{sid}.opex.y{t}.{k}", v, "EUR", f"F7 opex {k}_t: {OPEX_FORMULA[k]}")
        flows.append(
            out.put(
                f"{sid}.opex.y{t}.total",
                sum(items.values()),
                "EUR",
                "App. B opex_t = Σ items of year t",
            )
        )
    tco = cap["total"] + sum(x / (1 + r) ** t for t, x in enumerate(flows, 1))
    out.put(f"{sid}.finance.tco", tco, "EUR", "App. B TCO: capex + Σ_t opex_t / (1 + r)^t")
    lines1 = out.put(
        f"{sid}.finance.annual_lines_y1",
        c["lines_y0"] * (1 + c["g"]),
        "lines",
        "I36: Σ_d lines_d × days/yr ÷ observed × (1 + g)",
    )
    out.put(
        f"{sid}.finance.cost_per_line",
        tco * o.annuity_factor(r, horizon) / lines1,
        "EUR/line",
        "App. B: TCO × r / (1 − (1 + r)^−T) / annual_lines_1",
    )
    return flows


def versus(out: o.Out, sid: str, c: dict, base: dict, scen: dict) -> None:
    """F7 Δ cash flows vs the baseline scenario, NPV, IRR, payback (I37, I42)."""
    cf = [-(scen["capex"] - base["capex"])]
    cf += [b - s for b, s in zip(base["opex"], scen["opex"], strict=True)]
    p = f"{sid}.finance."
    for t, x in enumerate(cf):
        out.put(p + f"delta_cf.y{t}", x, "EUR", "App. B Δcf_0 = −Δcapex; Δcf_t = opex_b − opex_s")
    out.put(
        p + "npv",
        o.npv(c["basis"]["finance"]["discount_rate"], cf),
        "EUR",
        "App. B NPV: Σ_t Δcf_t / (1 + r)^t",
    )
    out.put(
        p + "irr",
        o.irr(cf),
        "-",
        "F7: numpy_financial.irr(Δcf); None unless exactly 1 sign change (I37)",
    )
    out.put(p + "payback_years", o.payback(cf), "years", "App. B payback; None = not reached")


# --- pipeline ------------------------------------------------------------------------------------
def size(out: o.Out, sd: dict, c: dict) -> dict[str, Any]:
    """F6 + F7 for one scenario (F6 evaluation order); returns capex total and opex flows."""
    sid, fam = sd["id"], sd["family"]
    if fam not in FAMILIES:
        raise NotImplementedError(f"the oracle sizes {FAMILIES} only, not {fam}")
    share_e, assumed, c["elig"][sid], cost_fam = 1.0, 0.0, set(), fam
    if fam == "cube_asrs":  # scenario EligibilityCfg (F5), keys S2.eligibility.* (I44)
        share_e, assumed, c["elig"][sid] = d.eligibility(
            out, f"{sid}.eligibility.", c["skus"], sd.get("eligibility") or {}
        )
        if share_e == 0:  # F6 edge case: zero eligible lines → degenerates to manual (I48)
            c["elig"][sid], cost_fam = set(), "manual_p2p"
    workloads(c, sid)
    out.sheet = "Storage"
    st = storage(out, sid, fam, c["skus"], c["basis"])
    out.sheet = "Throughput"
    eq = throughput(out, sid, fam, c, share_e)
    out.sheet = "Labor"
    lab = labor(out, sid, fam, c)
    out.sheet = "Area"
    ar = area(out, sid, c, st, eq, lab["roster"])
    out.sheet = "Queue"
    res = {"st": st, "eq": eq, "ar": ar, "m2": ar["total"], "share_e": share_e}
    res |= {"assumed": assumed, "queue": queue(out, sid, c, eq, ar)}
    flags(out, sid, fam, c, res)
    out.sheet = "Finance"
    cap = capex(out, sid, cost_fam, st, eq, ar["total"])
    opex = finance(out, sid, cost_fam, c, lab, eq, cap, ar["total"])
    return {"capex": cap["total"], "opex": opex}


def run(
    data_dir: Path = DATA,
    basis_path: Path = HERE / "golden_basis.yaml",
    scen_path: Path = HERE / "golden_scenarios.yaml",
) -> tuple[o.Out, dict[str, Any]]:
    """Whole golden case: demand → per-scenario sizing and finance → deltas vs baseline."""
    basis = yaml.safe_load(basis_path.read_text(encoding="utf-8"))
    scen = yaml.safe_load(scen_path.read_text(encoding="utf-8"))
    out = o.Out()
    c = d.demand(out, basis, data_dir)
    c["scenarios"] = scen["scenarios"]
    fin = {sd["id"]: size(out, sd, c) for sd in scen["scenarios"]}
    for sid in fin:
        if sid != scen["baseline"]:
            versus(out, sid, c, fin[scen["baseline"]], fin[sid])
    return out, c


def build(out_dir: Path = HERE) -> dict[str, Any]:
    """Run the oracle and write golden_values.json and golden_case.xlsx into `out_dir`."""
    out, c = run()
    workbook.write_json(out, out_dir / "golden_values.json")
    workbook.write_xlsx(out, c, out_dir / "golden_case.xlsx")
    return out.values()


if __name__ == "__main__":
    vals = build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
    print(f"{len(vals)} golden values written")
