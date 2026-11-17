"""F6b throughput and equipment, hand-computed on a toy case (catalog typ values).

Toy design day (`build`): 1000 lines, peak hour 150 lines, 2000 units, 10 pallets out,
inbound 20 pallets/day with peak factor 1.5, same-day share 0.6, SLA window 3.5 h.
SKUs: x (small, A, 50 lines, 300 units, 6 units/case), z (small, C, 20 lines, 600 units,
12 units/case), y (big, B, 30 lines, 100 units). Manual: x, z → shelving; y → pallet_rack.
Cube / AMR: x, z eligible (share of lines 0.7), y overflow pallet_rack.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import polars as pl
import pytest
from tests.unit.test_f6_inputs import BIG, build, toy_sku

from whsizing.catalog import ParamSet
from whsizing.engine import WorldInputs, size_storage, size_throughput
from whsizing.engine.throughput import ThroughputWorld
from whsizing.errors import SizingInfeasibleError
from whsizing.schemas import FamilyId, Inbound

REL = 1e-9
LAM = 150 / 0.85  # 176.470588: λ_peak binds (λ_sla = 0.6 × 1000 / 3.5 = 171.43)


def toy() -> pl.DataFrame:
    return toy_sku(
        {"sku": "x", "avg_stock": 100, "lines": 50, "units": 300, "abc": "A", "upc": 6},
        {"sku": "y", "dims": BIG, "avg_stock": 100, "lines": 30, "units": 100, "abc": "B",
         "upp": 50},
        {"sku": "z", "avg_stock": 100, "lines": 20, "units": 600, "abc": "C", "upc": 12},
    )  # fmt: skip


def run(family: FamilyId, **kw: Any) -> tuple[WorldInputs, ThroughputWorld]:
    inp = build(toy(), family, **kw)
    return inp, size_throughput(inp, size_storage(inp))


def value(inp: WorldInputs, key: str) -> float:
    return inp.tracer.get(inp.tid(key)).value


def test_lambda_is_max_of_peak_and_sla_flow() -> None:
    """I16: λ_peak = 150 / 0.85 = 176.4706; λ_sla = 0.6 × 1000 / 3.5 = 171.4286 → λ = λ_peak.
    With same_day_share 0.9: λ_sla = 257.1429 binds."""
    inp, tp = run("manual_p2p")
    assert value(inp, "throughput.lambda_peak") == pytest.approx(176.47058823529412, rel=REL)
    assert value(inp, "throughput.lambda_sla") == pytest.approx(171.42857142857142, rel=REL)
    assert tp.lam == pytest.approx(176.47058823529412, rel=REL)
    _, sla = run("manual_p2p", same_day_share=0.9)
    assert sla.lam == pytest.approx(257.14285714285717, rel=REL)


def test_manual_pickers_by_zone_carts_forklifts() -> None:
    """S0-like: λ_e = λ, λ_o = 0 (I17). Zones: shelving 70 % → 123.53 lines/h →
    ceil(123.53 / (70 × 0.85)) = ceil(2.076) = 3; pallet 30 % → 52.94 →
    ceil(52.94 / (35 × 0.85)) = ceil(1.780) = 2; pickers 5 = carts; utilisation
    (2.076 + 1.780) / 5 = 0.77113. Replen (I21): A/B units (300 + 100) / 1000 → 2000 × 0.4 / 80
    = 10 moves. Forklifts (I18): 20 × 1.5 × 0.2 + (10 + 10) × 0.15 = 9 moves/h →
    ceil(9 / 16) = 1, utilisation 0.5625. Bottleneck pickers."""
    inp, tp = run("manual_p2p")
    assert (tp.lam_e, tp.lam_o) == (pytest.approx(LAM, rel=REL), 0.0)
    assert tp.line_share == pytest.approx({"shelving": 0.7, "pallet_rack": 0.3})
    assert tp.lam_zone["shelving"] == pytest.approx(123.52941176470587, rel=REL)
    assert tp.equipment == {
        "pickers.shelving": 3,
        "pickers.pallet_rack": 2,
        "pickers_peak": 5,
        "carts": 5,
        "forklifts": 1,
    }
    assert tp.utilisation["pickers"] == pytest.approx(0.7711319822046465, rel=REL)
    assert tp.replen_moves == pytest.approx(10.0, rel=REL)
    assert tp.forklift_moves_peak_h == pytest.approx(9.0, rel=REL)
    assert tp.utilisation["forklifts"] == pytest.approx(0.5625, rel=REL)
    assert tp.bottleneck == "pickers"
    assert value(inp, "equipment.pickers_peak") == 5
    assert tp.flags == ()  # manual min scale 0
    assert "ports" not in tp.equipment and "robots" not in tp.equipment


def test_cube_ports_with_decant_robots_and_flags() -> None:
    """cube_asrs: λ_e = 0.7 × 176.47 = 123.53 (I44), λ_o = 52.94 → overflow pallet pickers
    ceil(1.780) = 2, shelving 0. Decant (I23): units_in_i = 2000 × U_i / ΣU → x 600 / 6 = 100,
    z 1200 / 12 = 100 cases (y is not decanted) → 200 / 90 = 2.2222 port-hours →
    × 1.5 × 0.2 = 0.6667 in the peak hour. Ports: 123.53 / (350 × 0.85) + 0.6667 = 1.0819 → 2,
    utilisation 0.5409. Bin presentations 123.53 / 1.3 = 95.02; robots
    ceil(95.02 × 1.6 / (22 × 0.95)) = ceil(7.274) = 8, utilisation 0.9093 → bottleneck robots.
    Replen: overflow A/B units 100 / 1000 → 2.5 moves; forklift moves 6 + 12.5 × 0.15 = 7.875.
    Grid: x, z 0.1 m³ → 3 bins each → 6.3 bins / 60 = 0.105 m² → 76 robots/m² >
    0.05 → F_ROBOT_DENSITY (I46); 1000 lines < 1500 → F_SCALE_LOW."""
    inp, tp = run("cube_asrs")
    assert tp.lam_e == pytest.approx(123.52941176470587, rel=REL)
    assert tp.lam_o == pytest.approx(52.94117647058823, rel=REL)
    assert tp.equipment["pickers.shelving"] == 0
    assert tp.equipment["pickers.pallet_rack"] == 2
    assert tp.cases_in == pytest.approx(200.0, rel=REL)
    assert value(inp, "equipment.decant_station_hours") == pytest.approx(200 / 90, rel=REL)
    assert tp.decant_port_load_peak_h == pytest.approx(2 / 3, rel=REL)
    assert tp.equipment["ports"] == 2
    assert tp.utilisation["ports"] == pytest.approx(0.5409457900807382, rel=REL)
    assert value(inp, "equipment.bin_presentations_h") == pytest.approx(95.02262443438913)
    assert tp.equipment["robots"] == 8
    assert tp.utilisation["robots"] == pytest.approx(0.9093074108553986, rel=REL)
    assert tp.replen_moves == pytest.approx(2.5, rel=REL)
    assert tp.forklift_moves_peak_h == pytest.approx(7.875, rel=REL)
    assert value(inp, "equipment.robots_per_grid_m2") == pytest.approx(8 / 0.105, rel=REL)
    density = inp.tracer.get("S9.equipment.robots_per_grid_m2")  # the L-confidence cap (I47)
    assert density.inputs["max_robots_per_m2"] == "param:cube_asrs.max_robots_per_m2"
    assert [f.code for f in tp.flags] == ["F_SCALE_LOW", "F_ROBOT_DENSITY"]
    assert tp.bottleneck == "robots"
    node = inp.tracer.get("S9.equipment.ports")
    assert node.inputs == {"port_load": "S9.equipment.port_load"}
    assert inp.tracer.get("S9.equipment.port_load").inputs["port_rate"] == (
        "param:cube_asrs.port_rate_lines_h"
    )


def test_amr_gtp_worked_example() -> None:
    """amr_gtp worked example (the golden case has no AMR scenario), catalog typ values.

    λ = 150 / 0.85 = 176.4706 lines/h; share of eligible lines = (50 + 20) / 100 = 0.7
        → λ_e = 123.5294, λ_o = 52.9412 (overflow pallet rack: ceil(52.94 / 29.75) = 2 pickers).
    stations    = ceil(λ_e / (station_rate 250 × oee 0.85)) = ceil(123.5294 / 212.5)
                = ceil(0.5813) = 1, utilisation 0.5813.
    pod_moves_h = λ_e / lines_per_pod_visit 1.8 = 68.6275.
    robots      = ceil(68.6275 / (robot_pod_moves_h 12 × availability 0.94) × (1 + 0.15))
                = ceil(6.0840 × 1.15) = ceil(6.9966) = 7, utilisation 0.99951 → bottleneck.
    storage     : x, z 0.1 m³ → ceil(0.1 / (0.03 × 0.8)) = 5 bins each → 10 × 1.05 = 10.5 bins
                → pods = ceil(10.5 / 60) = 1 → A_storage = 1 × 2.6 = 2.6 m².
    density     = 7 / 2.6 = 2.69 robots/m² > 0.05 → F_ROBOT_DENSITY; 1000 lines ≥ 800 → no
                F_SCALE_LOW.
    """
    inp, tp = run("amr_gtp")
    assert tp.lam_e == pytest.approx(123.52941176470587, rel=REL)
    assert value(inp, "equipment.gtp_station_load") == pytest.approx(0.5813148788927335)
    assert tp.equipment["gtp_stations"] == 1
    assert value(inp, "equipment.pod_moves_h") == pytest.approx(68.62745098039215, rel=REL)
    assert value(inp, "equipment.robot_load") == pytest.approx(6.9965929634265045, rel=REL)
    assert tp.equipment["robots"] == 7
    assert tp.utilisation == pytest.approx(
        {
            "pickers": 1.7795353435491843 / 2,
            "forklifts": 7.875 / 16,
            "gtp_stations": 0.5813148788927335,
            "robots": 0.9995132804895006,
        },
        rel=1e-9,
    )
    assert tp.bottleneck == "robots"
    assert value(inp, "storage.pod_bin.pods") == 1
    assert value(inp, "equipment.robots_per_storage_m2") == pytest.approx(7 / 2.6, rel=REL)
    assert [f.code for f in tp.flags] == ["F_ROBOT_DENSITY"]
    # decant (F6c driver, I23): x 600 / 6 + z 1200 / 12 = 200 cases; no port load at AMR
    assert tp.cases_in == pytest.approx(200.0, rel=REL)
    assert value(inp, "throughput.decant_cases_in") == pytest.approx(200.0, rel=REL)
    assert tp.decant_port_load_peak_h == 0.0
    assert inp.tracer.get("S9.equipment.robots").unit == "-"  # counts, F6f example
    assert inp.tracer.get("S9.equipment.robots_per_storage_m2").inputs["max_robots_per_m2"] == (
        "param:amr_gtp.max_robots_per_m2"
    )


def test_bottleneck_tie_goes_to_the_first_resource() -> None:
    """I20: count 0 → utilisation 0; on a tie the first of pickers, forklifts, ports, robots
    wins. A day without flow ties every resource at 0 → pickers."""
    idle = Inbound(
        mode="derived",
        units_per_day=0.0,
        pallets_per_day=0.0,
        receipt_lines_per_day=0.0,
        trucks_per_day=0.0,
        peak_factor=1.5,
    )
    zero = {"lines": 0.0, "peak_hour_lines": 0.0, "units": 0.0, "pallets_out": 0.0}
    _, tp = run("cube_asrs", dd={**zero, "inbound": idle})
    assert tp.equipment["pickers_peak"] == tp.equipment["ports"] == tp.equipment["robots"] == 0
    assert tp.utilisation == {"pickers": 0.0, "forklifts": 0.0, "ports": 0.0, "robots": 0.0}
    assert tp.bottleneck == "pickers"


# --- I85 (b): plausibility bound on every sized count (R8b, final audit M5) -------------------
@pytest.mark.parametrize(
    ("family", "dd", "resource"),
    [
        ("manual_p2p", {"peak_hour_lines": 1e12, "lines": 1e12}, "pickers"),
        ("manual_p2p", {"pallets_out": 1e12}, "forklifts"),
        ("cube_asrs", {"pallets_out": 0.0, "peak_hour_lines": 1e12, "lines": 1e12}, "pickers"),
        ("amr_gtp", {"pallets_out": 0.0, "peak_hour_lines": 1e12, "lines": 1e12}, "pickers"),
    ],
)
def test_T6_4_count_above_the_bound_is_infeasible_before_any_loop(
    family: FamilyId, dd: dict[str, Any], resource: str
) -> None:
    """A unit or outlier problem (1e12 lines or pallets) raises SizingInfeasibleError (exit 4
    under --strict) naming the scenario, resource and value, with R13."""
    inp = build(toy(), family, dd=dd)
    with pytest.raises(SizingInfeasibleError, match=rf"{resource}.*check units and outliers") as e:
        size_throughput(inp, size_storage(inp))
    assert e.value.exit_code == 4
    assert "S9" in str(e.value) and "engine.max_equipment_count (100,000)" in str(e.value)


SMALL = toy_sku(  # x and z only: every SKU is eligible, nothing overflows to the manual zones
    {"sku": "x", "avg_stock": 100, "lines": 50, "units": 300, "abc": "A", "upc": 6},
    {"sku": "z", "avg_stock": 100, "lines": 20, "units": 600, "abc": "C", "upc": 12},
)
BUSY = {"lines": 1e6, "peak_hour_lines": 150_000.0, "pallets_out": 10.0}  # ports 594, robots 10 393
IDLE = {"lines": 0.0, "peak_hour_lines": 0.0, "units": 0.0, "pallets_out": 0.0}


@pytest.mark.parametrize(
    ("family", "bound", "resource"),
    [
        ("cube_asrs", 500, "ports"),
        ("cube_asrs", 700, "robots"),  # 594 ports pass, 10 393 robots do not
        ("amr_gtp", 800, "gtp_stations"),
        ("amr_gtp", 900, "robots"),  # 831 stations pass, 9 996 robots do not
    ],
)
def test_T6_4_automated_counts_are_bounded(family: FamilyId, bound: int, resource: str) -> None:
    """The bound is the catalog scalar, so a basis override moves it for every resource; each
    automated count (ports, gtp_stations, robots) is checked on its own."""
    inp = build(SMALL, family, dd=BUSY)
    tight = replace(inp, params=ParamSet(inp.catalog, {"engine.max_equipment_count": bound}, {}))
    with pytest.raises(SizingInfeasibleError, match=rf"{resource} = [\d,]+ exceeds .*\({bound}"):
        size_throughput(tight, size_storage(tight))


def test_T6_4_pods_are_bounded() -> None:
    """Pods are sized in storage.py (one pod here); the AMR throughput stage checks them."""
    idle = Inbound(
        mode="derived", units_per_day=0.0, pallets_per_day=0.0, receipt_lines_per_day=0.0,
        trucks_per_day=0.0, peak_factor=1.5,
    )  # fmt: skip
    inp = build(SMALL, "amr_gtp", dd={**IDLE, "inbound": idle})
    tight = replace(inp, params=ParamSet(inp.catalog, {"engine.max_equipment_count": 0}, {}))
    with pytest.raises(SizingInfeasibleError, match=r"pods = 1 exceeds"):
        size_throughput(tight, size_storage(tight))


def test_T6_4_infinite_load_is_reported_not_an_overflow() -> None:
    """math.ceil(inf) is an OverflowError (exit 1): the bound check comes first."""
    inp = build(toy(), "manual_p2p", dd={"peak_hour_lines": float("inf")})
    with pytest.raises(SizingInfeasibleError, match="inf exceeds"):
        size_throughput(inp, size_storage(inp))


def test_T6_4_normal_counts_are_unchanged_and_pass_the_bound() -> None:
    _, tp = run("manual_p2p")
    assert tp.equipment["pickers_peak"] > 0 and tp.equipment["pickers_peak"] < 100_000
