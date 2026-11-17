"""F6d area budget, docks and the informational ICPE label for one world (I9, I24, I26-I28,
I46, I56). Trace ids `<sid>.area.*` and `<sid>.docks.*` (golden keys)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from whsizing.engine.inputs import WORLDS, WorldInputs, to_range
from whsizing.engine.storage import StorageWorld
from whsizing.engine.throughput import ThroughputWorld, ceil_count
from whsizing.errors import WhsizingError
from whsizing.schemas import AreaResult, Flag, World

AF = "area."  # area_factors.yaml constants
DD = "data:design_day."
IB = "data:design_day.inbound."
FL = "data:basis.flows."
PACK_OEE = "engine.pack_station_oee"
PACK_M2 = "manual_p2p.m2_per_pack_station"  # I26: the manual value for every scenario
# family → (equipment count, m² per station or port); I26 for the cube
STATIONS = {
    "cube_asrs": ("ports", "cube_asrs.m2_per_port"),
    "amr_gtp": ("gtp_stations", "amr_gtp.m2_per_station"),
}


@dataclass(frozen=True)
class AreaWorld:
    """F6d results of one world. `zones` holds every zone incl. `circulation` (I27); the packing
    fields feed the F6e packing pool."""

    zones: dict[str, float]  # m²
    total_m2: float
    building_m2: float
    fit: bool  # total ≤ building area
    utilisation: float  # total / building area
    deficit_m2: float  # max(0, total − building area)
    peak_hour_orders: float  # orders/h
    pack_rate: float  # orders/h per station, before oee (I24)
    pack_stations: int
    trucks_in_peak_h: float
    trucks_out_peak_h: float
    docks_in: int
    docks_out: int
    icpe_volume_m3: float
    icpe_regime: str | None
    flags: tuple[Flag, ...]  # F_NO_FIT, F_DOCK_SHORTFALL


def size_area(
    inp: WorldInputs,
    storage: StorageWorld,
    tp: ThroughputWorld,
    *,
    roster: float,
    share_s: float,
) -> AreaWorld:
    """F6d for one world. `roster` = F6c roster of the same world (heads, `S*.labor.total.roster`);
    `share_s` = share of 1-line orders over the period (I15), the F6c value
    `LaborDays.single_line_share` (`S*.labor.single_line_share`): one source for labor and area."""
    if roster < 0 or not math.isfinite(roster):
        raise WhsizingError(f"area: roster must be a finite number ≥ 0, got {roster}")
    if not 0.0 <= share_s <= 1.0:
        raise WhsizingError(f"area: share of 1-line orders must be in [0, 1], got {share_s}")
    ph_orders, rate, stations, packing = _packing(inp, share_s)
    zones = {
        "receiving_staging": _receiving(inp),
        "shipping_staging": _shipping(inp),
        "packing": packing,
        "ports": _ports(inp, tp),
        "storage": inp.record(
            "area.storage",
            "Storage area (incl. aisles)",
            storage.total_area_m2,
            "m2",
            "F6a total storage area",
            {"storage": inp.tid("storage.total_area_m2")},
        ),
        "returns": _returns(inp),
        "equipment": _equipment(inp, tp),
        "amenities": _amenities(inp, roster),
    }
    zones["circulation"] = _circulation(inp, zones)
    total, fit, util, deficit = _fit(inp, zones)
    t_in, t_out, d_in, d_out = _docks(inp)
    building = inp.basis.building
    volume = inp.record(
        "area.icpe_volume_m3",
        "Building volume (ICPE 1510, informational)",
        building.area_m2 * building.clear_height_m,
        "m3",
        "building.area_m2 × building.clear_height_m",
        {"area": "data:basis.building.area_m2", "height": "data:basis.building.clear_height_m"},
    )
    return AreaWorld(
        zones=zones,
        total_m2=total,
        building_m2=building.area_m2,
        fit=fit,
        utilisation=util,
        deficit_m2=deficit,
        peak_hour_orders=ph_orders,
        pack_rate=rate,
        pack_stations=stations,
        trucks_in_peak_h=t_in,
        trucks_out_peak_h=t_out,
        docks_in=d_in,
        docks_out=d_out,
        icpe_volume_m3=volume,
        # [VERIFY] info only: the regime depends on stored combustible volume and cell design
        icpe_regime=inp.catalog.icpe.regime(volume),
        flags=_flags(inp, fit, deficit, d_in, d_out),
    )


def area_result(worlds: Mapping[World, AreaWorld]) -> AreaResult:
    """Merge the three worlds (ADR-002 Ranges). Fit, docks, ICPE and flags are the typical
    world's (`fit` = total.typ ≤ building area). Amenities sit inside the footprint (I27)."""
    typ = worlds["typ"]
    return AreaResult(
        zones={z: to_range({w: worlds[w].zones[z] for w in WORLDS}, "m2") for z in typ.zones},
        total_m2=to_range({w: worlds[w].total_m2 for w in WORLDS}, "m2"),
        building_m2=typ.building_m2,
        fit=typ.fit,
        utilisation=to_range({w: worlds[w].utilisation for w in WORLDS}, "-"),
        deficit_m2=to_range({w: worlds[w].deficit_m2 for w in WORLDS}, "m2"),
        docks_in_required=typ.docks_in,
        docks_out_required=typ.docks_out,
        icpe_volume_m3=typ.icpe_volume_m3,
        icpe_regime=typ.icpe_regime,
        amenities_external=False,
        flags=list(typ.flags),
    )


def _receiving(inp: WorldInputs) -> float:
    ib = inp.design_day.inbound
    return inp.record(
        "area.receiving_staging",
        "Receiving staging",
        ib.pallets_per_day * ib.peak_factor * inp.v(f"{AF}m2_per_pallet_staged")
        * inp.v(f"{AF}staging_days"),
        "m2",
        "pallets_in × inbound_peak_factor × m2_per_pallet_staged × staging_days",
        {
            "pallets_in": f"{IB}pallets_per_day",
            "inbound_peak_factor": f"{IB}peak_factor",
            "m2_per_pallet_staged": f"param:{AF}m2_per_pallet_staged",
            "staging_days": f"param:{AF}staging_days",
        },
    )  # fmt: skip


def _shipping(inp: WorldInputs) -> float:
    dd = inp.design_day
    return inp.record(
        "area.shipping_staging",
        "Shipping staging",
        (dd.pallets_out + dd.parcels / inp.v(f"{AF}parcels_per_pallet_equiv"))
        * inp.v(f"{AF}m2_per_pallet_staged"),
        "m2",
        "(pallets_out + parcels / parcels_per_pallet_equiv) × m2_per_pallet_staged",
        {
            "pallets_out": f"{DD}pallets_out",
            "parcels": f"{DD}parcels",
            "parcels_per_pallet_equiv": f"param:{AF}parcels_per_pallet_equiv",
            "m2_per_pallet_staged": f"param:{AF}m2_per_pallet_staged",
        },
    )


def _packing(inp: WorldInputs, share_s: float) -> tuple[float, float, int, float]:
    """I24: peak_hour_orders = orders × peak_hour_share; pack_rate = order-weighted harmonic mean
    of packing_S / packing_ML; pack_stations = ceil(peak_hour_orders / (pack_rate × oee))."""
    dd = inp.design_day
    phs = dd.peak_hour_lines / dd.lines if dd.lines > 0 else 0.0
    ph_orders = inp.record(
        "area.peak_hour_orders",
        "Orders in the peak hour",
        dd.orders * phs,
        "orders/h",
        "orders × peak_hour_share",
        {"orders": f"{DD}orders", "peak_hour_share": inp.tid("throughput.peak_hour_share")},
    )
    rate = inp.record(
        "area.pack_rate",
        "Pack rate per station",
        1.0 / (share_s / inp.v("labor.packing_S") + (1 - share_s) / inp.v("labor.packing_ML")),
        "orders/h",
        "1 / (s_S / packing_S + (1 − s_S) / packing_ML)",
        {
            "s_S": inp.tid("labor.single_line_share"),
            "packing_S": "param:labor.packing_S",
            "packing_ML": "param:labor.packing_ML",
        },
    )
    stations = inp.record(
        "area.pack_stations",
        "Pack stations",
        ceil_count(inp, "pack stations", ph_orders / (rate * inp.v(PACK_OEE))),
        "-",
        "ceil(peak_hour_orders / (pack_rate × oee))",
        {
            "peak_hour_orders": inp.tid("area.peak_hour_orders"),
            "pack_rate": inp.tid("area.pack_rate"),
            "oee": f"param:{PACK_OEE}",
        },
    )
    packing = inp.record(
        "area.packing",
        "Packing",
        stations * inp.v(PACK_M2),
        "m2",
        "pack_stations × m2_per_pack_station",
        {"pack_stations": inp.tid("area.pack_stations"), "m2_per_pack_station": f"param:{PACK_M2}"},
    )
    return ph_orders, rate, int(stations), packing


def _ports(inp: WorldInputs, tp: ThroughputWorld) -> float:
    """GTP stations (amr) or cube ports × m² per station or port (I26); 0 for the manual family."""
    fam = inp.scenario.family
    if fam not in STATIONS:
        return inp.record("area.ports", "GTP stations / ports", 0.0, "m2", "no stations", {})
    count, m2 = STATIONS[fam]
    return inp.record(
        "area.ports",
        "GTP stations / ports",
        tp.equipment[count] * inp.v(m2),
        "m2",
        f"{count} × {m2.split('.')[1]}",
        {count: inp.tid(f"equipment.{count}"), m2.split(".")[1]: f"param:{m2}"},
    )


def _returns(inp: WorldInputs) -> float:
    """I9: return_lines = returns_rate × lines (design day)."""
    return inp.record(
        "area.returns",
        "Returns",
        inp.basis.flows.returns_rate * inp.design_day.lines * inp.v(f"{AF}m2_per_return_line_day")
        + inp.v(f"{AF}returns_fixed_m2"),
        "m2",
        "returns_rate × lines × m2_per_return_line_day + returns_fixed_m2",
        {
            "returns_rate": f"{FL}returns_rate",
            "lines": f"{DD}lines",
            "m2_per_return_line_day": f"param:{AF}m2_per_return_line_day",
            "returns_fixed_m2": f"param:{AF}returns_fixed_m2",
        },
    )


def _equipment(inp: WorldInputs, tp: ThroughputWorld) -> float:
    """I26, I63 (12): robots × cube_asrs.m2_per_robot_parking + maintenance_fixed for every
    family with robots (amr_gtp too); manual: no robots, no parking Param (I47), fixed only."""
    fixed = f"{AF}maintenance_fixed_m2"
    refs = {"maintenance_fixed_m2": f"param:{fixed}"}
    if "robots" not in tp.equipment:
        return inp.record(
            "area.equipment", "Equipment", inp.v(fixed), "m2", "maintenance_fixed_m2", refs
        )
    park = "cube_asrs.m2_per_robot_parking"
    return inp.record(
        "area.equipment",
        "Equipment (robot parking, maintenance)",
        tp.equipment["robots"] * inp.v(park) + inp.v(fixed),
        "m2",
        "robots × m2_per_robot_parking + maintenance_fixed_m2",
        {"robots": inp.tid("equipment.robots"), "m2_per_robot_parking": f"param:{park}", **refs},
    )


def _amenities(inp: WorldInputs, roster: float) -> float:
    return inp.record(
        "area.amenities",
        "Amenities and offices",
        roster * inp.v(f"{AF}m2_per_head_amenities") + inp.v(f"{AF}amenities_fixed_m2"),
        "m2",
        "roster × m2_per_head_amenities + amenities_fixed_m2",
        {
            "roster": inp.tid("labor.total.roster"),
            "m2_per_head_amenities": f"param:{AF}m2_per_head_amenities",
            "amenities_fixed_m2": f"param:{AF}amenities_fixed_m2",
        },
    )


def _circulation(inp: WorldInputs, zones: dict[str, float]) -> float:
    """I27: circulation_share × Σ all zones except storage (amenities included)."""
    others = [z for z in zones if z != "storage"]
    return inp.record(
        "area.circulation",
        "Circulation",
        inp.v(f"{AF}circulation_share") * sum(zones[z] for z in others),
        "m2",
        "circulation_share × Σ zones except storage",
        {"circulation_share": f"param:{AF}circulation_share"}
        | {z: inp.tid(f"area.{z}") for z in others},
    )


def _fit(inp: WorldInputs, zones: dict[str, float]) -> tuple[float, bool, float, float]:
    area = inp.basis.building.area_m2
    b = {"building_area": "data:basis.building.area_m2"}
    total = inp.record(
        "area.total", "Total area", sum(zones.values()), "m2", "Σ zones + circulation",
        {z: inp.tid(f"area.{z}") for z in zones},
    )  # fmt: skip
    inp.record("area.building_m2", "Building area", area, "m2", "building.area_m2", b)
    t = {"total": inp.tid("area.total"), **b}
    fit = total <= area
    inp.record("area.fit", "Fits the building", float(fit), "-", "total ≤ building_area", t)
    util = inp.record("area.utilisation", "Area utilisation", total / area, "-", "total / area", t)
    deficit = inp.record(
        "area.deficit_m2", "Area deficit", max(0.0, total - area), "m2",
        "max(0, total − building_area)", t,
    )  # fmt: skip
    return total, fit, util, deficit


def _docks(inp: WorldInputs) -> tuple[float, float, int, int]:
    """I28 trucks in the peak hour (Inbound.peak_factor is 1 in receipts mode, I56); docks =
    ceil(trucks_peak_h × dwell_h / dock_utilisation) (App. B)."""
    dd, ib, fl = inp.design_day, inp.design_day.inbound, inp.basis.flows
    t_in = inp.record(
        "docks.trucks_in_peak_h",
        "Inbound trucks in the peak hour",
        ib.trucks_per_day * ib.peak_factor * inp.v(f"{AF}peak_hour_share_inbound"),
        "trucks/h",
        "trucks_per_day × inbound_peak_factor × peak_hour_share_inbound",
        {
            "trucks_per_day": f"{IB}trucks_per_day",
            "inbound_peak_factor": f"{IB}peak_factor",
            "peak_hour_share_inbound": f"param:{AF}peak_hour_share_inbound",
        },
    )
    phs = dd.peak_hour_lines / dd.lines if dd.lines > 0 else 0.0
    t_out = inp.record(
        "docks.trucks_out_peak_h",
        "Outbound trucks in the peak hour",
        (dd.pallets_out + dd.parcels / inp.v(f"{AF}parcels_per_pallet_equiv"))
        / fl.pallets_per_truck
        * phs,
        "trucks/h",
        "(pallets_out + parcels / parcels_per_pallet_equiv) / pallets_per_truck × peak_hour_share",
        {
            "pallets_out": f"{DD}pallets_out",
            "parcels": f"{DD}parcels",
            "parcels_per_pallet_equiv": f"param:{AF}parcels_per_pallet_equiv",
            "pallets_per_truck": f"{FL}pallets_per_truck",
            "peak_hour_share": inp.tid("throughput.peak_hour_share"),
        },
    )
    return t_in, t_out, _dock(inp, "in", t_in), _dock(inp, "out", t_out)


def _dock(inp: WorldInputs, way: str, trucks: float) -> int:
    fl = inp.basis.flows
    return int(
        inp.record(
            f"docks.{way}",
            f"Dock doors required ({way})",
            math.ceil(trucks * fl.truck_dwell_hours / fl.dock_utilisation),
            "-",
            f"ceil(trucks_{way}_peak_h × dwell_h / dock_utilisation)",
            {
                f"trucks_{way}_peak_h": inp.tid(f"docks.trucks_{way}_peak_h"),
                "dwell_h": f"{FL}truck_dwell_hours",
                "dock_utilisation": f"{FL}dock_utilisation",
            },
        )
    )


def _flags(inp: WorldInputs, fit: bool, deficit: float, d_in: int, d_out: int) -> tuple[Flag, ...]:
    """I46 order: F_NO_FIT, then F_DOCK_SHORTFALL. F_AMENITIES_EXTERNAL is never raised (I27)."""
    b = inp.basis.building
    out: list[Flag] = []
    if not fit:
        msg = f"total area exceeds the building ({b.area_m2:.0f} m²) by {deficit:.1f} m²"
        out.append(Flag(code="F_NO_FIT", severity="warning", message=msg, value=deficit))
    short = inp.record(
        "docks.shortfall",
        "Dock doors missing",
        max(0, d_in - b.dock_doors_in, d_out - b.dock_doors_out),
        "-",
        "max(0, docks_in − dock_doors_in, docks_out − dock_doors_out)",
        {
            "docks_in": inp.tid("docks.in"),
            "docks_out": inp.tid("docks.out"),
            "dock_doors_in": "data:basis.building.dock_doors_in",
            "dock_doors_out": "data:basis.building.dock_doors_out",
        },
    )
    if short > 0:
        msg = (
            f"dock doors required in/out {d_in}/{d_out} > available "
            f"{b.dock_doors_in}/{b.dock_doors_out}"
        )
        out.append(Flag(code="F_DOCK_SHORTFALL", severity="warning", message=msg, value=short))
    return tuple(out)
