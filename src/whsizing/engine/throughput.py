"""F6b throughput and equipment for one world (I16-I18, I20, I21, I23, I44, I46)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from whsizing.design import inbound_by_sku, sla_window_hours
from whsizing.engine.inputs import WorldInputs
from whsizing.engine.storage import StorageWorld
from whsizing.errors import SizingInfeasibleError
from whsizing.schemas import Flag

ZONES = ("shelving", "pallet_rack")  # manual picking zones (I17), main or overflow
PICK_RATE = {
    "shelving": "manual_p2p.pick_rate_shelving_lines_h",
    "pallet_rack": "manual_p2p.pick_rate_pallet_lines_h",
}
AB = ("A", "B")  # I21: replenishment of the A/B SKUs ("units_picked_A/B")
DD = "data:design_day."
IB = "data:design_day.inbound."
SHARE_IN = "area.peak_hour_share_inbound"
MAX_COUNT = "engine.max_equipment_count"  # I85 (b): plausibility bound on any sized count


@dataclass(frozen=True)
class Automation:
    """Family-specific part: equipment counts, utilisation, flags, decant (cube)."""

    equipment: dict[str, float]
    utilisation: dict[str, float]
    flags: tuple[Flag, ...]
    cases_in: float = 0.0
    decant_port_load_peak_h: float = 0.0


@dataclass(frozen=True)
class ThroughputWorld:
    """F6b results of one world. `equipment` holds counts (pickers.<zone>, pickers_peak, carts,
    forklifts; cube ports, robots; amr gtp_stations, robots); `utilisation` the I20 loads in
    bottleneck tie order (pickers, forklifts, ports | gtp_stations, robots)."""

    lam: float  # λ, lines/h
    lam_e: float  # eligible flow (main zone), lines/h
    lam_o: float  # overflow flow, lines/h
    line_share: dict[str, float]  # manual zone → share of period lines (I17)
    lam_zone: dict[str, float]  # manual zone → lines/h
    replen_moves: float  # design-day replenishment moves (I21), F6c driver
    forklift_moves_peak_h: float
    cases_in: float  # cases decanted per design day (eligible SKUs, I23; cube, amr), else 0
    decant_port_load_peak_h: float  # port-hours per peak hour (I23), else 0
    equipment: dict[str, float]
    utilisation: dict[str, float]
    bottleneck: str
    flags: tuple[Flag, ...]  # F_SCALE_LOW, F_ROBOT_DENSITY


def check_count(inp: WorldInputs, resource: str, n: float) -> None:
    """I85 (b): a sized equipment count above `engine.max_equipment_count` (or not a number) is a
    units or outlier problem (R13 keeps a quantity such as 1e12): SizingInfeasibleError, exit 4
    under --strict, before anything loops over that count (Erlang-C)."""
    limit = inp.v(MAX_COUNT)
    if not n <= limit:  # also catches NaN
        raise SizingInfeasibleError(
            f"{inp.scenario.id} ({inp.scenario.family}): {resource} = {n:,.0f} exceeds "
            f"engine.max_equipment_count ({limit:,.0f}); check units and outliers (R13)"
        )


def ceil_count(inp: WorldInputs, resource: str, load: float) -> int:
    """`ceil(load)` as an equipment count, after the I85 (b) bound check (an infinite load is
    reported as such, not as an OverflowError)."""
    check_count(inp, resource, math.ceil(load) if math.isfinite(load) else load)
    return math.ceil(load)


def size_throughput(inp: WorldInputs, storage: StorageWorld) -> ThroughputWorld:
    """F6b for one world; `storage` is the same world's `size_storage` (A_grid, pod area)."""
    lam = _lambda(inp)
    lam_e = _eligible_flow(inp, lam)
    share, lam_zone = _zones(inp, lam)
    pickers, carts, u_pickers = _pickers(inp, lam_zone)
    replen = _replen(inp)
    moves, forklifts, u_forklifts = _forklifts(inp, replen)
    fam = inp.scenario.family
    auto = (
        _cube(inp, lam_e, storage)
        if fam == "cube_asrs"
        else _amr(inp, lam_e, storage)
        if fam == "amr_gtp"
        else Automation({}, {}, ())
    )
    utilisation = {"pickers": u_pickers, "forklifts": u_forklifts, **auto.utilisation}
    min_scale = inp.v(f"{fam}.min_scale_lines_day")
    scale = (
        [
            Flag(
                code="F_SCALE_LOW",
                severity="warning",
                message=f"{fam}: {inp.design_day.lines:.0f} design lines/day "
                f"< minimum scale {min_scale:.0f}",
                value=inp.design_day.lines,
            )
        ]
        if inp.design_day.lines < min_scale
        else []
    )
    return ThroughputWorld(
        lam=lam,
        lam_e=lam_e,
        lam_o=lam - lam_e,
        line_share=share,
        lam_zone=lam_zone,
        replen_moves=replen,
        forklift_moves_peak_h=moves,
        cases_in=auto.cases_in,
        decant_port_load_peak_h=auto.decant_port_load_peak_h,
        equipment={**pickers, "carts": carts, "forklifts": forklifts, **auto.equipment},
        utilisation=utilisation,
        bottleneck=max(utilisation, key=utilisation.__getitem__),  # first on a tie (I20)
        flags=(*scale, *auto.flags),
    )


def _lambda(inp: WorldInputs) -> float:
    """I16: λ = max(peak_hour_lines / η_flow, same_day_share × lines / sla_window_hours)."""
    dd, svc = inp.design_day, inp.basis.service
    peak = inp.record(
        "throughput.lambda_peak",
        "Peak-hour flow",
        dd.peak_hour_lines / inp.v("engine.eta_flow"),
        "lines/h",
        "peak_hour_lines / eta_flow",
        {"peak_hour_lines": f"{DD}peak_hour_lines", "eta_flow": "param:engine.eta_flow"},
    )
    window = inp.record(
        "throughput.sla_window_hours",
        "SLA window",
        sla_window_hours(svc),
        "h",
        "service.sla_window_hours, else (carrier_departure_time − cutoff_time) mod 24 h",
        {
            "sla_window_hours": "data:basis.service.sla_window_hours",
            "cutoff": "data:basis.service.cutoff_time",
            "departure": "data:basis.service.carrier_departure_time",
        },
    )
    sla = inp.record(
        "throughput.lambda_sla",
        "SLA-window flow",
        svc.same_day_share * dd.lines / window,
        "lines/h",
        "same_day_share × lines / sla_window_hours",
        {
            "same_day_share": "data:basis.service.same_day_share",
            "lines": f"{DD}lines",
            "sla_window_hours": inp.tid("throughput.sla_window_hours"),
        },
    )
    return inp.record(
        "throughput.lambda",
        "Design flow",
        max(peak, sla),
        "lines/h",
        "max(lambda_peak, lambda_sla)",
        {
            "lambda_peak": inp.tid("throughput.lambda_peak"),
            "lambda_sla": inp.tid("throughput.lambda_sla"),
        },
    )


def _eligible_flow(inp: WorldInputs, lam: float) -> float:
    """I44: λ_e = λ × share_lines of the scenario's eligibility (manual: 1); λ_o = λ − λ_e."""
    lam_e = inp.record(
        "throughput.lambda_e",
        "Eligible flow",
        lam * inp.eligibility.share_lines,
        "lines/h",
        "lambda × share_lines_eligible",
        {"lambda": inp.tid("throughput.lambda"), "share": inp.tid("eligibility.share_lines")},
    )
    inp.record(
        "throughput.lambda_o",
        "Overflow flow",
        lam - lam_e,
        "lines/h",
        "lambda − lambda_e",
        {"lambda": inp.tid("throughput.lambda"), "lambda_e": inp.tid("throughput.lambda_e")},
    )
    return lam_e


def _zones(inp: WorldInputs, lam: float) -> tuple[dict[str, float], dict[str, float]]:
    """I17: zone share = period lines of the zone's SKUs / period lines; λ_zone = λ × share."""
    total = float(inp.sku["lines"].sum())
    share: dict[str, float] = {}
    lam_zone: dict[str, float] = {}
    for z in ZONES:
        lines = float(inp.sku.filter(pl.col("storage_class") == z)["lines"].sum())
        share[z] = inp.record(
            f"throughput.line_share.{z}",
            f"Share of lines picked in {z}",
            lines / total if total > 0 else 0.0,
            "-",
            "Σ lines of the zone's SKUs / Σ lines",
            {"lines": "data:sku.lines", "zone": "data:sku.storage_class"},
        )
        lam_zone[z] = inp.record(
            f"throughput.lambda.{z}",
            f"Flow in {z}",
            lam * share[z],
            "lines/h",
            "lambda × line_share_zone",
            {
                "lambda": inp.tid("throughput.lambda"),
                "share": inp.tid(f"throughput.line_share.{z}"),
            },
        )
    return share, lam_zone


def _pickers(inp: WorldInputs, lam_zone: dict[str, float]) -> tuple[dict[str, float], float, float]:
    """F6b manual: pickers_peak = Σ_zone ceil(λ_zone / (pick_rate_zone × η_pick)) (I17);
    carts = pickers_peak; utilisation = Σ_zone load / pickers (I20)."""
    eta = inp.v("manual_p2p.eta_pick")
    counts: dict[str, float] = {}
    load = 0.0
    for z in ZONES:
        work = lam_zone[z] / (inp.v(PICK_RATE[z]) * eta)
        load += work
        counts[f"pickers.{z}"] = inp.record(
            f"equipment.pickers.{z}",
            f"Pickers in {z} (peak)",
            ceil_count(inp, f"pickers ({z})", work),
            "-",
            "ceil(lambda_zone / (pick_rate_zone × eta_pick))",
            {
                "lambda_zone": inp.tid(f"throughput.lambda.{z}"),
                "pick_rate_zone": f"param:{PICK_RATE[z]}",
                "eta_pick": "param:manual_p2p.eta_pick",
            },
        )
    refs = {z: inp.tid(f"equipment.pickers.{z}") for z in ZONES}
    check_count(inp, "pickers (carts)", sum(counts.values()))  # the zones add up
    total = inp.record(
        "equipment.pickers_peak",
        "Pickers (peak)",
        sum(counts.values()),
        "-",
        "Σ_zone pickers_zone",
        refs,
    )
    counts["pickers_peak"] = total
    carts = inp.record(
        "equipment.carts",
        "Carts",
        total,
        "-",
        "pickers_peak",
        {"pickers_peak": inp.tid("equipment.pickers_peak")},
    )
    util = inp.record(
        "utilisation.pickers",
        "Picker utilisation",
        load / total if total else 0.0,
        "-",
        "Σ_zone lambda_zone / (pick_rate_zone × eta_pick) / pickers_peak",
        {**{f"lambda_{z}": inp.tid(f"throughput.lambda.{z}") for z in ZONES}, **refs},
    )
    return counts, carts, util


def _replen(inp: WorldInputs) -> float:
    """I21: replen_moves = units* × (period units of A/B SKUs in manual zones / period units) /
    replen_units_per_move (S2: overflow A/B SKUs only)."""
    sku = inp.sku
    total = float(sku["units"].sum())
    manual_ab = sku.filter(pl.col("abc").is_in(AB) & pl.col("storage_class").is_in(ZONES))
    share = inp.record(
        "throughput.replen_units_share",
        "Share of units from A/B SKUs in manual zones",
        float(manual_ab["units"].sum()) / total if total > 0 else 0.0,
        "-",
        "Σ units of A/B SKUs in manual zones / Σ units",
        {"units": "data:sku.units", "abc": "data:sku.abc", "zone": "data:sku.storage_class"},
    )
    return inp.record(
        "throughput.replen_moves",
        "Replenishment moves (design day)",
        inp.design_day.units * share / inp.v("manual_p2p.replen_units_per_move"),
        "moves",
        "units × replen_units_share / replen_units_per_move",
        {
            "units": f"{DD}units",
            "share": inp.tid("throughput.replen_units_share"),
            "replen_units_per_move": "param:manual_p2p.replen_units_per_move",
        },
    )


def _forklifts(inp: WorldInputs, replen: float) -> tuple[float, float, float]:
    """I18: moves = pallets_in × inbound_peak_factor × peak_hour_share_inbound + (pallets_out +
    replen_moves) × peak_hour_share; forklifts = ceil(moves / forklift_moves_h)."""
    dd, ib = inp.design_day, inp.design_day.inbound
    phs = inp.record(
        "throughput.peak_hour_share",
        "Peak-hour share of the design day",
        dd.peak_hour_lines / dd.lines if dd.lines > 0 else 0.0,
        "-",
        "peak_hour_lines / lines",
        {"peak_hour_lines": f"{DD}peak_hour_lines", "lines": f"{DD}lines"},
    )
    moves = inp.record(
        "equipment.forklift_moves_peak_h",
        "Forklift moves in the peak hour",
        ib.pallets_per_day * ib.peak_factor * inp.v(SHARE_IN) + (dd.pallets_out + replen) * phs,
        "moves/h",
        "pallets_in × inbound_peak_factor × peak_hour_share_inbound + "
        "(pallets_out + replen_moves) × peak_hour_share",
        {
            "pallets_in": f"{IB}pallets_per_day",
            "inbound_peak_factor": f"{IB}peak_factor",
            "peak_hour_share_inbound": f"param:{SHARE_IN}",
            "pallets_out": f"{DD}pallets_out",
            "replen_moves": inp.tid("throughput.replen_moves"),
            "peak_hour_share": inp.tid("throughput.peak_hour_share"),
        },
    )
    rate = "manual_p2p.forklift_moves_h"
    load = inp.record(
        "equipment.forklift_load",
        "Forklift load (peak hour)",
        moves / inp.v(rate),
        "forklifts",
        "forklift_moves_peak_h / forklift_moves_h",
        {"moves": inp.tid("equipment.forklift_moves_peak_h"), "forklift_moves_h": f"param:{rate}"},
    )
    n = _count(inp, "forklifts", "Forklifts", load, "forklift_load")
    util = _util(inp, "forklifts", load, n, "forklift_load")
    return moves, n, util


def _cube(inp: WorldInputs, lam_e: float, storage: StorageWorld) -> Automation:
    """cube_asrs: ports with decant at the ports in the inbound peak hour (I23), robots with the
    dig factor, robots per m² of grid (I46)."""
    c = "cube_asrs."
    cases = _cases_in(inp)
    dload = _decant_port_load(inp, cases)
    port_load = inp.record(
        "equipment.port_load",
        "Port load (peak hour)",
        lam_e / (inp.v(f"{c}port_rate_lines_h") * inp.v(f"{c}oee")) + dload,
        "ports",
        "lambda_e / (port_rate × oee) + decant_port_load_peak_h",
        {
            "lambda_e": inp.tid("throughput.lambda_e"),
            "port_rate": f"param:{c}port_rate_lines_h",
            "oee": f"param:{c}oee",
            "decant_port_load_peak_h": inp.tid("equipment.decant_port_load_peak_h"),
        },
    )
    ports = _count(inp, "ports", "Cube ports", port_load, "port_load")
    robot_load = _cube_robot_load(inp, lam_e)
    robots = _count(inp, "robots", "Cube robots", robot_load, "robot_load")
    grid = storage.get("cube_bin").grid_area_m2 or 0.0
    grid_ref = inp.tid("storage.cube_bin.grid_area_m2")
    return Automation(
        equipment={"ports": ports, "robots": robots},
        utilisation={
            "ports": _util(inp, "ports", port_load, ports, "port_load"),
            "robots": _util(inp, "robots", robot_load, robots, "robot_load"),
        },
        flags=_density(inp, robots, grid, ("robots_per_grid_m2", "grid", grid_ref), c),
        cases_in=cases,
        decant_port_load_peak_h=dload,
    )


def _cube_robot_load(inp: WorldInputs, lam_e: float) -> float:
    """bin_pres_h = λ_e / lines_per_bin_presentation; load = bin_pres_h × dig_factor /
    (robot_bins_h × availability)."""
    c = "cube_asrs."
    pres = inp.record(
        "equipment.bin_presentations_h",
        "Bin presentations per hour",
        lam_e / inp.v(f"{c}lines_per_bin_presentation"),
        "bins/h",
        "lambda_e / lines_per_bin_presentation",
        {"lambda_e": inp.tid("throughput.lambda_e"), "lpb": f"param:{c}lines_per_bin_presentation"},
    )
    return inp.record(
        "equipment.robot_load",
        "Robot load (peak hour)",
        pres
        * inp.v(f"{c}dig_factor")
        / (inp.v(f"{c}robot_bins_per_h") * inp.v(f"{c}robot_availability")),
        "robots",
        "bin_presentations_h × dig_factor / (robot_bins_h × availability)",
        {
            "bin_presentations_h": inp.tid("equipment.bin_presentations_h"),
            "dig_factor": f"param:{c}dig_factor",
            "robot_bins_h": f"param:{c}robot_bins_per_h",
            "availability": f"param:{c}robot_availability",
        },
    )


def _cases_in(inp: WorldInputs) -> float:
    """I23: cases_in of the scenario's eligible SKUs (I13 per SKU); the F6c decant driver of
    cube and AMR (F6c table), the port load of cube."""
    ib = inp.design_day.inbound
    per = inbound_by_sku(ib.units_per_day, inp.sku, inp.params)  # same row order as inp.sku
    return inp.record(
        "throughput.decant_cases_in",
        "Cases decanted per day (eligible SKUs)",
        float(per["cases_in"].filter(inp.sku["eligible"]).sum()),
        "cases",
        "Σ_eligible units_in × U_i / Σ U / units_per_case_i",
        {
            "units_in": f"{IB}units_per_day",
            "units": "data:sku.units",
            "mask": "data:sku.eligible",
            "upc": "data:sku.units_per_case",
            "upp": "data:sku.units_per_pallet",
            "cpp": "data:sku.cases_per_pallet",
        },
    )


def _decant_port_load(inp: WorldInputs, cases: float) -> float:
    """I23 (cube): decant_station_hours = cases_in / decant_cases_per_h; peak-hour port load =
    hours × inbound_peak_factor × peak_hour_share_inbound."""
    ib = inp.design_day.inbound
    rate = "cube_asrs.decant_cases_per_h"
    hours = inp.record(
        "equipment.decant_station_hours",
        "Decant port-hours per day",
        cases / inp.v(rate),
        "h",
        "cases_in / decant_cases_per_h",
        {"cases_in": inp.tid("throughput.decant_cases_in"), "decant_cases_per_h": f"param:{rate}"},
    )
    return inp.record(
        "equipment.decant_port_load_peak_h",
        "Decant port load in the peak hour",
        hours * ib.peak_factor * inp.v(SHARE_IN),
        "ports",
        "decant_station_hours × inbound_peak_factor × peak_hour_share_inbound",
        {
            "decant_station_hours": inp.tid("equipment.decant_station_hours"),
            "inbound_peak_factor": f"{IB}peak_factor",
            "peak_hour_share_inbound": f"param:{SHARE_IN}",
        },
    )


def _amr(inp: WorldInputs, lam_e: float, storage: StorageWorld) -> Automation:
    """amr_gtp: stations = ceil(λ_e / (station_rate × oee)); robots with the charging reserve;
    F_ROBOT_DENSITY on robots / pod storage area; cases_in for the F6c decant (no port load)."""
    a = "amr_gtp."
    pod_bin = storage.get("pod_bin")
    if pod_bin.pods is not None:  # sized in storage.py; bounded here with the other counts
        check_count(inp, "pods", pod_bin.pods)
    cases = _cases_in(inp)
    station_load = inp.record(
        "equipment.gtp_station_load",
        "GTP station load (peak hour)",
        lam_e / (inp.v(f"{a}station_rate_lines_h") * inp.v(f"{a}oee")),
        "stations",
        "lambda_e / (station_rate × oee)",
        {
            "lambda_e": inp.tid("throughput.lambda_e"),
            "station_rate": f"param:{a}station_rate_lines_h",
            "oee": f"param:{a}oee",
        },
    )
    stations = _count(inp, "gtp_stations", "GTP stations", station_load, "gtp_station_load")
    robot_load = _amr_robot_load(inp, lam_e)
    robots = _count(inp, "robots", "AMR robots", robot_load, "robot_load")
    # ponytail: A_storage = the pod zone (robots do not drive in the manual overflow)
    area = pod_bin.area_m2
    area_ref = inp.tid("storage.pod_bin.area_m2")
    return Automation(
        equipment={"gtp_stations": stations, "robots": robots},
        utilisation={
            "gtp_stations": _util(inp, "gtp_stations", station_load, stations, "gtp_station_load"),
            "robots": _util(inp, "robots", robot_load, robots, "robot_load"),
        },
        flags=_density(inp, robots, area, ("robots_per_storage_m2", "storage", area_ref), a),
        cases_in=cases,
    )


def _amr_robot_load(inp: WorldInputs, lam_e: float) -> float:
    """pod_moves_h = λ_e / lines_per_pod_visit; load = pod_moves_h / (robot_moves_h ×
    availability) × (1 + charging_reserve)."""
    a = "amr_gtp."
    pod_moves = inp.record(
        "equipment.pod_moves_h",
        "Pod moves per hour",
        lam_e / inp.v(f"{a}lines_per_pod_visit"),
        "moves/h",
        "lambda_e / lines_per_pod_visit",
        {"lambda_e": inp.tid("throughput.lambda_e"), "lpv": f"param:{a}lines_per_pod_visit"},
    )
    return inp.record(
        "equipment.robot_load",
        "Robot load incl. charging reserve",
        pod_moves
        / (inp.v(f"{a}robot_pod_moves_h") * inp.v(f"{a}robot_availability"))
        * (1 + inp.v(f"{a}charging_reserve")),
        "robots",
        "pod_moves_h / (robot_moves_h × availability) × (1 + charging_reserve)",
        {
            "pod_moves_h": inp.tid("equipment.pod_moves_h"),
            "robot_moves_h": f"param:{a}robot_pod_moves_h",
            "availability": f"param:{a}robot_availability",
            "charging_reserve": f"param:{a}charging_reserve",
        },
    )


def _count(inp: WorldInputs, name: str, label: str, load: float, load_key: str) -> float:
    return inp.record(
        f"equipment.{name}",
        label,
        ceil_count(inp, name, load),
        "-",
        f"ceil({load_key})",
        {load_key: inp.tid(f"equipment.{load_key}")},
    )


def _util(inp: WorldInputs, name: str, load: float, count: float, load_key: str) -> float:
    """I20: load / count, 0 for a resource with count 0."""
    return inp.record(
        f"utilisation.{name}",
        f"Utilisation of {name}",
        load / count if count else 0.0,
        "-",
        f"{load_key} / {name}",
        {load_key: inp.tid(f"equipment.{load_key}"), name: inp.tid(f"equipment.{name}")},
    )


def _density(
    inp: WorldInputs, robots: float, area: float, what: tuple[str, str, str], fam: str
) -> tuple[Flag, ...]:
    """robots / area (0 when the area is 0) → F_ROBOT_DENSITY above `<fam>max_robots_per_m2`.
    `what` = (trace key, area name, area trace id)."""
    key, name, area_ref = what
    density = inp.record(
        f"equipment.{key}",
        f"Robots per m² of {name}",
        robots / area if area > 0 else 0.0,
        "1/m2",
        f"robots / A_{name} (0 when A_{name} = 0); F_ROBOT_DENSITY above max_robots_per_m2",
        {
            "robots": inp.tid("equipment.robots"),
            f"A_{name}": area_ref,
            "max_robots_per_m2": f"param:{fam}max_robots_per_m2",
        },
    )
    cap = inp.v(f"{fam}max_robots_per_m2")
    if density <= cap:
        return ()
    msg = f"{density:.3f} robots per m² of {name} > cap {cap}"
    return (Flag(code="F_ROBOT_DENSITY", severity="warning", message=msg, value=density),)
