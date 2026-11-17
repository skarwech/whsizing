"""F6d area budget and docks, hand-computed on the F6a/F6b toy case (catalog typ values).

Toy design day (`build` in test_f6_inputs): 1000 lines, peak hour 150 lines (peak-hour share
0.15), 1420 orders, 1520 parcels, 10 pallets out; inbound 20 pallets/day, peak factor 1.5,
0.85 trucks/day. Basis: 12 000 m², clear height 8.5 m, doors 4 in / 6 out, returns rate 0.04,
26 pallets per truck, dwell 1 h, dock utilisation 0.7. F6c inputs: roster 10, share_s 0.5.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.unit.test_f6_inputs import build
from tests.unit.test_f6_throughput import toy

from whsizing.engine import WORLDS, WorldInputs, size_storage, size_throughput
from whsizing.engine.area import AreaWorld, area_result, size_area
from whsizing.engine.storage import StorageWorld
from whsizing.errors import SizingInfeasibleError, WhsizingError
from whsizing.schemas import FamilyId, World
from whsizing.schemas.trace import Tracer

REL = 1e-9
ROSTER, SHARE_S = 10.0, 0.5


def area(
    family: FamilyId = "manual_p2p", world: World = "typ", **basis: object
) -> tuple[WorldInputs, StorageWorld, AreaWorld]:
    """Toy run; `basis` updates `building` fields (area_m2, dock doors)."""
    inp = build(toy(), family, world, tracer=Tracer("S9", world))
    if basis:
        b = inp.basis.model_copy(update={"building": inp.basis.building.model_copy(update=basis)})
        inp = replace(inp, basis=b)
    st = size_storage(inp)
    return inp, st, size_area(inp, st, size_throughput(inp, st), roster=ROSTER, share_s=SHARE_S)


def test_manual_zones_by_hand() -> None:
    """receiving 20 × 1.5 × 1.5 × 1.0 = 45; shipping (10 + 1520 / 40) × 1.5 = 72;
    peak-hour orders 1420 × 0.15 = 213; pack_rate 1 / (0.5 / 55 + 0.5 / 25) = 34.375;
    stations ceil(213 / (34.375 × 0.85)) = ceil(7.29) = 8 → 96 m²; ports 0; returns
    0.04 × 1000 × 0.05 + 30 = 32; equipment 40 (no robots); amenities 10 × 4 + 150 = 190;
    circulation 0.25 × (45 + 72 + 96 + 0 + 32 + 40 + 190) = 118.75; total = 593.75 + storage."""
    inp, st, a = area()
    expected = {
        "receiving_staging": 45.0,
        "shipping_staging": 72.0,
        "packing": 96.0,
        "ports": 0.0,
        "storage": st.total_area_m2,
        "returns": 32.0,
        "equipment": 40.0,
        "amenities": 190.0,
        "circulation": 118.75,
    }
    assert a.zones == pytest.approx(expected, rel=REL)
    assert list(a.zones) == list(expected)
    assert (a.peak_hour_orders, a.pack_rate, a.pack_stations) == pytest.approx((213, 34.375, 8))
    total = 593.75 + st.total_area_m2
    assert a.total_m2 == pytest.approx(total, rel=REL)
    assert a.fit and a.deficit_m2 == 0.0 and a.flags == ()
    assert a.utilisation == pytest.approx(total / 12000, rel=REL)
    for key, v in [("area.total", total), ("area.fit", 1.0), ("area.pack_stations", 8)]:
        assert inp.tracer.get(inp.tid(key)).value == pytest.approx(v, rel=REL)
    amen = inp.tracer.get(inp.tid("area.amenities"))
    assert amen.inputs["roster"] == "S9.labor.total.roster"


def test_docks_and_icpe_by_hand() -> None:
    """trucks in 0.85 × 1.5 × 0.2 = 0.255 → ceil(0.255 × 1 / 0.7) = 1; trucks out
    (10 + 38) / 26 × 0.15 = 0.27692 → 1. ICPE volume 12 000 × 8.5 = 102 000 m³ → E (info)."""
    inp, _, a = area()
    assert a.trucks_in_peak_h == pytest.approx(0.255, rel=REL)
    assert a.trucks_out_peak_h == pytest.approx(48 / 26 * 0.15, rel=REL)
    assert (a.docks_in, a.docks_out) == (1, 1)
    assert inp.tracer.get(inp.tid("docks.in")).value == 1
    assert a.icpe_volume_m3 == pytest.approx(102000.0)
    assert a.icpe_regime == "Enregistrement (E)"


def test_dock_shortfall_with_receipts_peak_factor() -> None:
    """Receipts mode (I56: Inbound.peak_factor is 1.0, no second peak), 30 trucks/day:
    30 × 1.0 × 0.2 = 6 trucks/h → ceil(6 / 0.7) = 9 > 4 doors → F_DOCK_SHORTFALL (value 5);
    receiving staging 20 × 1.0 × 1.5 = 30 m²."""
    inp = build(toy(), "manual_p2p")
    ib = inp.design_day.inbound.model_copy(
        update={"mode": "receipts", "trucks_per_day": 30.0, "peak_factor": 1.0}
    )
    inp = replace(inp, design_day=inp.design_day.model_copy(update={"inbound": ib}))
    st = size_storage(inp)
    a = size_area(inp, st, size_throughput(inp, st), roster=ROSTER, share_s=SHARE_S)
    assert a.zones["receiving_staging"] == pytest.approx(30.0, rel=REL)
    assert a.docks_in == 9
    assert [(f.code, f.value) for f in a.flags] == [("F_DOCK_SHORTFALL", 5)]


def test_no_fit_flags_deficit() -> None:
    """Building 500 m² < total → F_NO_FIT with deficit = total − 500, utilisation > 1."""
    inp, _, a = area(area_m2=500.0)
    assert not a.fit
    assert a.deficit_m2 == pytest.approx(a.total_m2 - 500.0, rel=REL)
    assert a.utilisation > 1
    assert [f.code for f in a.flags] == ["F_NO_FIT"]
    assert inp.tracer.get(inp.tid("area.fit")).value == 0.0


def test_cube_ports_and_robot_parking() -> None:
    """Cube toy: 2 ports × 20 m² = 40; 8 robots × 2.0 + 40 = 56 (I26)."""
    inp, _, a = area("cube_asrs")
    assert a.zones["ports"] == pytest.approx(40.0)
    assert a.zones["equipment"] == pytest.approx(56.0)
    node = inp.tracer.get(inp.tid("area.equipment"))
    assert node.inputs["m2_per_robot_parking"] == "param:cube_asrs.m2_per_robot_parking"


def test_amr_stations_and_robot_parking() -> None:
    """AMR toy: 1 GTP station × 16 m² = 16; 7 robots × 2.0 + 40 = 54."""
    _, _, a = area("amr_gtp")
    assert a.zones["ports"] == pytest.approx(16.0)
    assert a.zones["equipment"] == pytest.approx(54.0)


def test_area_result_ranges_over_worlds() -> None:
    """ADR-002: the pessimistic world (pack rate, oee and m² per station) needs the most packing
    and total area, the optimistic the least, so the Range is the worlds' (lo, typ, hi) and not
    an artefact of min/max; fit and docks from typ; amenities inside (I27)."""
    worlds: dict[World, AreaWorld] = {w: area("manual_p2p", w)[2] for w in WORLDS}
    r = area_result(worlds)
    packing = [worlds[w].zones["packing"] for w in WORLDS]
    total = [worlds[w].total_m2 for w in WORLDS]
    assert packing[0] > packing[1] > packing[2] and total[0] > total[1] > total[2]
    assert (r.zones["packing"].lo, r.zones["packing"].hi) == (packing[2], packing[0])
    assert r.zones["packing"].typ == pytest.approx(96.0)
    assert (r.total_m2.lo, r.total_m2.typ, r.total_m2.hi) == (total[2], total[1], total[0])
    assert r.fit is True and r.docks_in_required == 1 and r.amenities_external is False
    assert r.icpe_regime == "Enregistrement (E)" and r.flags == []
    assert worlds["lo"].pack_rate == pytest.approx(1 / (0.5 / 40 + 0.5 / 18))


@pytest.mark.parametrize(("roster", "share_s"), [(-1.0, 0.5), (float("nan"), 0.5), (5.0, 1.2)])
def test_rejects_bad_labor_inputs(roster: float, share_s: float) -> None:
    inp = build(toy(), "manual_p2p")
    st = size_storage(inp)
    with pytest.raises(WhsizingError):
        size_area(inp, st, size_throughput(inp, st), roster=roster, share_s=share_s)


def test_T6_4_pack_stations_above_the_bound_are_infeasible() -> None:
    """I85 (b): 1e12 orders (a unit or outlier problem, R13) give 5e9 pack stations; the guard
    raises SizingInfeasibleError (exit 4 under --strict) naming the resource and the value."""
    inp = build(toy(), "manual_p2p", dd={"orders": 1e12})
    st = size_storage(inp)
    tp = size_throughput(inp, st)  # pickers and forklifts are normal: orders feed packing only
    with pytest.raises(SizingInfeasibleError, match=r"pack stations = [\d,]+ exceeds .*R13") as e:
        size_area(inp, st, tp, roster=ROSTER, share_s=SHARE_S)
    assert e.value.exit_code == 4
