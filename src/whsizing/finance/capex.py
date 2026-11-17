"""F7 capex (year 0) of one scenario in one world, from its F6 quantities and cost Params.

Items (trace ids `<sid>.capex.<item>`): storage, equipment, controls, building_works, overflow,
integration_commissioning, contingency, total. Rules: I29 (manual), I30 (cube), I31 (shares),
I48 (a degenerate automated scenario is costed with the manual formulas, overflow item 0).
amr_gtp follows the F7 table and Appendix C.2: storage = pods × per_pod_eur; equipment =
robots × per_robot_eur + stations × per_station_eur + robots × charging_per_robot_eur;
controls = fleet_software_fixed_eur; building works = area.total × manual €/m² + floor
preparation × A_storage (the pod storage area, the analog of I30's A_grid); the rest as I30.
"""

from __future__ import annotations

from typing import NamedTuple

from whsizing.finance.context import Ctx

M = "manual_p2p."
CONTROLS = {"cube_asrs": "controls_fixed_eur", "amr_gtp": "fleet_software_fixed_eur"}
FLOOR_AREA = {"cube_asrs": "storage.cube_bin.grid_area_m2", "amr_gtp": "storage.pod_bin.area_m2"}
ITEMS = (
    "storage",
    "equipment",
    "controls",
    "building_works",
    "overflow",
    "integration_commissioning",
    "contingency",
)


class Capex(NamedTuple):
    """`items`: the ITEMS plus `total`. `manual_equipment`: carts × €/cart + forklifts × €/forklift,
    the manual zone's equipment (the `equipment` item of S0, inside `overflow` otherwise)."""

    items: dict[str, float]
    manual_equipment: float


class Parts(NamedTuple):
    """The family-specific capex items (traced) and the building works (value, formula, inputs)."""

    storage: float
    equipment: float
    controls: float
    overflow: float
    manual_equipment: float
    works: tuple[float, str, dict[str, str]]


def _auto_parts(c: Ctx) -> Parts:
    """Automated family: storage, equipment, controls, the manual overflow zone, floor prep."""
    fam, area = c.fam, c.q("area.total")
    storage, equipment = _auto_storage(c), _auto_equipment(c)
    controls = c.rec(
        "capex.controls",
        "Controls and software upfront",
        c.v(f"{fam}.{CONTROLS[fam]}"),
        "eur",
        f"{CONTROLS[fam]}",
        {CONTROLS[fam]: f"param:{fam}.{CONTROLS[fam]}"},
    )
    o_storage, manual_eq = _manual_zone(c, "capex.overflow.storage", "capex.overflow.equipment")
    overflow = c.rec(
        "capex.overflow",
        "Overflow zone (manual formulas)",
        o_storage + manual_eq,
        "eur",
        "overflow storage + overflow equipment",
        {
            "storage": c.tid("capex.overflow.storage"),
            "equipment": c.tid("capex.overflow.equipment"),
        },
    )
    floor_area, prep = c.q(FLOOR_AREA[fam]), c.v(f"{fam}.floor_prep_per_m2_eur")
    works = (
        area * c.v(f"{M}building_works_per_m2_eur") + floor_area * prep,
        "area_total × building_works_per_m2_eur + A_floor × floor_prep_per_m2_eur",
        {
            "area_total": c.tid("area.total"),
            "building_works_per_m2_eur": f"param:{M}building_works_per_m2_eur",
            "A_floor": c.tid(FLOOR_AREA[fam]),
            "floor_prep_per_m2_eur": f"param:{fam}.floor_prep_per_m2_eur",
        },
    )
    return Parts(storage, equipment, controls, overflow, manual_eq, works)


def _manual_parts(c: Ctx) -> Parts:
    """Manual family (or a degenerate automated one, I48): WMS adaptation, no overflow item."""
    storage, equipment = _manual_zone(c, "capex.storage", "capex.equipment")
    controls = c.rec(
        "capex.controls",
        "Controls and software upfront",
        c.v(f"{M}wms_adaptation_fixed_eur"),
        "eur",
        "wms_adaptation_fixed_eur",
        {"wms_adaptation_fixed_eur": f"param:{M}wms_adaptation_fixed_eur"},
    )
    overflow = c.rec(
        "capex.overflow", "Overflow zone", 0.0, "eur", "0: no automated main zone (I29, I48)", {}
    )
    works = (
        c.q("area.total") * c.v(f"{M}building_works_per_m2_eur"),
        "area_total × building_works_per_m2_eur",
        {
            "area_total": c.tid("area.total"),
            "building_works_per_m2_eur": f"param:{M}building_works_per_m2_eur",
        },
    )
    return Parts(storage, equipment, controls, overflow, equipment, works)


def capex_items(c: Ctx) -> Capex:
    """Year-0 capex of `c.result` in `c.world`; traced."""
    fam = c.fam
    p = _auto_parts(c) if c.auto else _manual_parts(c)
    storage, equipment, controls, overflow = p.storage, p.equipment, p.controls, p.overflow
    building = c.rec("capex.building_works", "Building works", p.works[0], "eur", *p.works[1:])
    share = c.v(f"{fam}.integration_share") + c.v(f"{fam}.commissioning_share")
    ic = c.rec(
        "capex.integration_commissioning",
        "Integration and commissioning",
        share * equipment,
        "eur",
        "(integration_share + commissioning_share) × equipment",
        {
            "integration_share": f"param:{fam}.integration_share",
            "commissioning_share": f"param:{fam}.commissioning_share",
            "equipment": c.tid("capex.equipment"),
        },
    )
    base = storage + equipment + controls + building + overflow + ic
    contingency = c.rec(
        "capex.contingency",
        "Contingency",
        c.v(f"{fam}.contingency_share") * base,
        "eur",
        "contingency_share × (storage + equipment + controls + building_works + overflow "
        "+ integration_commissioning)",
        {
            "contingency_share": f"param:{fam}.contingency_share",
            **{k: c.tid(f"capex.{k}") for k in (*ITEMS[:5], "integration_commissioning")},
        },
    )
    items = {
        "storage": storage,
        "equipment": equipment,
        "controls": controls,
        "building_works": building,
        "overflow": overflow,
        "integration_commissioning": ic,
        "contingency": contingency,
    }
    total = c.rec(
        "capex.total",
        "Total capex",
        sum(items.values()),
        "eur",
        "Σ items",
        {k: c.tid(f"capex.{k}") for k in ITEMS},
    )
    return Capex({**items, "total": total}, p.manual_equipment)


def _manual_zone(c: Ctx, storage_key: str, equipment_key: str) -> tuple[float, float]:
    """(storage, equipment) of the manual formulas on the scenario's manual classes (S0: main
    zone; automated family: its overflow zone): positions × €/position + bins × €/bin, carts ×
    €/cart + forklifts × €/forklift (I29, I30)."""
    z = c.zone
    pallets, bins = f"storage.{z}pallet_rack.positions", f"storage.{z}shelving.positions"
    storage = c.rec(
        storage_key,
        "Manual storage (pallet rack and shelving)",
        c.q(pallets) * c.v(f"{M}per_pallet_position_eur")
        + c.q(bins) * c.v(f"{M}per_shelf_bin_eur"),
        "eur",
        "pallet positions × per_pallet_position_eur + shelving bins × per_shelf_bin_eur",
        {
            "pallet_positions": c.tid(pallets),
            "shelving_bins": c.tid(bins),
            "per_pallet_position_eur": f"param:{M}per_pallet_position_eur",
            "per_shelf_bin_eur": f"param:{M}per_shelf_bin_eur",
        },
    )
    equipment = c.rec(
        equipment_key,
        "Manual equipment (carts and forklifts)",
        c.q("equipment.carts") * c.v(f"{M}per_cart_eur")
        + c.q("equipment.forklifts") * c.v(f"{M}per_forklift_eur"),
        "eur",
        "carts × per_cart_eur + forklifts × per_forklift_eur",
        {
            "carts": c.tid("equipment.carts"),
            "forklifts": c.tid("equipment.forklifts"),
            "per_cart_eur": f"param:{M}per_cart_eur",
            "per_forklift_eur": f"param:{M}per_forklift_eur",
        },
    )
    return storage, equipment


def _auto_storage(c: Ctx) -> float:
    fam = c.fam
    if fam == "cube_asrs":
        bins, grid = "storage.cube_bin.positions", "storage.cube_bin.grid_area_m2"
        return c.rec(
            "capex.storage",
            "Storage (bins and grid structure)",
            c.q(bins) * c.v("cube_asrs.per_bin_eur")
            + c.q(grid) * c.v("cube_asrs.grid_structure_per_m2_eur"),
            "eur",
            "bins_total × per_bin_eur + A_grid × grid_structure_per_m2_eur",
            {
                "bins_total": c.tid(bins),
                "A_grid": c.tid(grid),
                "per_bin_eur": "param:cube_asrs.per_bin_eur",
                "grid_structure_per_m2_eur": "param:cube_asrs.grid_structure_per_m2_eur",
            },
        )
    pods = "storage.pod_bin.pods"
    return c.rec(
        "capex.storage",
        "Storage (pods)",
        c.q(pods) * c.v("amr_gtp.per_pod_eur"),
        "eur",
        "pods × per_pod_eur",
        {"pods": c.tid(pods), "per_pod_eur": "param:amr_gtp.per_pod_eur"},
    )


def _auto_equipment(c: Ctx) -> float:
    fam = c.fam
    robots = c.q("equipment.robots")
    robot_inputs = {
        "robots": c.tid("equipment.robots"),
        "per_robot_eur": f"param:{fam}.per_robot_eur",
    }
    if fam == "cube_asrs":
        return c.rec(
            "capex.equipment",
            "Equipment (robots and ports)",
            robots * c.v("cube_asrs.per_robot_eur")
            + c.q("equipment.ports") * c.v("cube_asrs.per_port_eur"),
            "eur",
            "robots × per_robot_eur + ports × per_port_eur",
            {
                **robot_inputs,
                "ports": c.tid("equipment.ports"),
                "per_port_eur": "param:cube_asrs.per_port_eur",
            },
        )
    return c.rec(
        "capex.equipment",
        "Equipment (robots, stations, charging)",
        robots * (c.v("amr_gtp.per_robot_eur") + c.v("amr_gtp.charging_per_robot_eur"))
        + c.q("equipment.gtp_stations") * c.v("amr_gtp.per_station_eur"),
        "eur",
        "robots × (per_robot_eur + charging_per_robot_eur) + stations × per_station_eur",
        {
            **robot_inputs,
            "stations": c.tid("equipment.gtp_stations"),
            "charging_per_robot_eur": "param:amr_gtp.charging_per_robot_eur",
            "per_station_eur": "param:amr_gtp.per_station_eur",
        },
    )
