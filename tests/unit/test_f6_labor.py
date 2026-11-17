"""F6c labor, hand-computed on the F6b toy case (catalog typ values, tests/unit/test_f6_inputs).

Toy basis (mock_basis): 2 shifts × 7 h, 7 paid h/day, utilisation 0.85, absenteeism 0.06,
PF&D 0.12, 252 operating days/year, g 4 %, returns 4 %, finance horizon 5 years.
Toy design day (`build`): 1000 lines, 1420 orders, 1520 parcels, 10 pallets out, 2000 units;
inbound 20 pallets, 22 receipt lines, 2000 units. SKUs x (A, 50 lines), y (B, big, 30 lines),
z (C, 20 lines): manual x, z → shelving (70 %), y → pallet_rack (30 %).
Toy history (`frames`): D1 o1 = x×2, o2 = y×1 + z×3, o3 = x×1; D2 o4 = z×4; D3 (not
operating) o5 = x×1 → one-line share 4 / 5 = 0.8; n_op = 2.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import polars as pl
import pytest
from tests.golden.test_f6_labor_golden import bad_data_refs
from tests.unit.test_f6_inputs import CATALOG, build
from tests.unit.test_f6_throughput import toy

from whsizing.catalog import ParamSet
from whsizing.engine import WORLDS, WorldInputs, size_storage, size_throughput
from whsizing.engine.labor import LaborWorld, labor_days, labor_result, size_labor
from whsizing.engine.shifts import profiles
from whsizing.errors import ConfigError, WhsizingError
from whsizing.schemas import FamilyId

REL = 1e-9
PFD = 1.12
CAP = 7 * 0.85  # hours_per_shift × utilisation = paid_hours × utilisation = 5.95
K = 252 / 2  # operating_days_per_year / n_op
GF = 1.04**5
D1, D2, D3 = date(2025, 1, 6), date(2025, 1, 7), date(2025, 1, 8)
ORDERS = [
    ("o1", D1, [("x", 2)]),
    ("o2", D1, [("y", 1), ("z", 3)]),
    ("o3", D1, [("x", 1)]),
    ("o4", D2, [("z", 4)]),
    ("o5", D3, [("x", 1)]),
]
# date, operating, parcels, pallets_out, receipts_units
DAYS = [(D1, True, 3.0, 1.0, 1000.0), (D2, True, 2.0, 0.0, 500.0), (D3, False, 1.0, 0.0, 0.0)]


def frames(
    orders: list[tuple[str, date, list[tuple[str, int]]]] = ORDERS,
    days: list[tuple[date, bool, float, float, float]] = DAYS,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(daily series, shipped lines) of a toy history; daily lines = count of lines."""
    rows = [(o, s, d, q) for o, d, items in orders for s, q in items]
    lines = pl.DataFrame(
        rows,
        schema={"order_id": pl.Utf8, "sku": pl.Utf8, "date": pl.Date, "qty_units": pl.Int64},
        orient="row",
    )
    n = {d: sum(1 for r in rows if r[2] == d) for d, *_ in days}
    daily = pl.DataFrame(
        [(d, op, float(n[d]), p, po, r) for d, op, p, po, r in days],
        schema={
            "date": pl.Date,
            "is_operating": pl.Boolean,
            "lines": pl.Float64,
            "parcels": pl.Float64,
            "pallets_out": pl.Float64,
            "receipts_units": pl.Float64,
        },
        orient="row",
    )
    return daily, lines


def labor(
    inp: WorldInputs, daily: pl.DataFrame | None = None, lines: pl.DataFrame | None = None
) -> LaborWorld:
    d0, l0 = frames()
    days = labor_days(inp, d0 if daily is None else daily, l0 if lines is None else lines)
    return size_labor(inp, size_throughput(inp, size_storage(inp)), days)


def run(family: FamilyId = "manual_p2p", **kw: object) -> tuple[WorldInputs, LaborWorld]:
    inp = build(toy(), family, **kw)  # pyright: ignore[reportArgumentType]
    return inp, labor(inp)


def act(lw: LaborWorld, name: str):
    return next(a for a in lw.activities if a.activity == name)


def value(inp: WorldInputs, key: str) -> float:
    return inp.tracer.get(inp.tid(key)).value


def test_design_day_hours_and_heads_per_activity() -> None:
    """hours = workload / standard × 1.12, heads = hours / (7 × 0.85): picking shelving 700 /
    70, pallet 300 / 35 (I17, I38); packing S 1420 × 0.8 / 55, ML 1420 × 0.2 / 25 (I15);
    receiving 20 / 14, receipt check 22 / 45, put-away 20 / 13 (I22, no peak factor);
    replenishment 10 moves / 14 (I21); parcels 1520 / 110, pallets 10 / 14; returns
    0.04 × 1000 / 22 (I9); indirect 0.12 × Σ direct (I38). No decant in the manual family."""
    inp, lw = run()
    want = {
        "receiving": 20 / 14,
        "receipt_check": 22 / 45,
        "put_away": 20 / 13,
        "replenishment": 10 / 14,
        "picking": 700 / 70 + 300 / 35,
        "packing_S": 1136 / 55,
        "packing_ML": 284 / 25,
        "shipping_parcel": 1520 / 110,
        "shipping_pallet": 10 / 14,
        "returns": 40 / 22,
    }
    direct = sum(want.values()) * PFD
    assert [a.activity for a in lw.activities] == [*want, "indirect"]  # labor_standards order
    for name, hours in want.items():
        a = act(lw, name)
        assert a.hours == pytest.approx(hours * PFD, rel=REL), name
        assert a.heads == pytest.approx(hours * PFD / CAP, rel=REL), name
    assert value(inp, "labor.picking.shelving.workload") == pytest.approx(700, rel=REL)
    assert value(inp, "labor.picking.pallet_rack.hours") == pytest.approx(300 / 35 * PFD)
    assert act(lw, "packing_S").workload == pytest.approx(1136, rel=REL)
    ind = act(lw, "indirect")
    assert (ind.workload, ind.hours) == (pytest.approx(direct), pytest.approx(0.12 * direct))
    assert lw.total_hours == pytest.approx(1.12 * direct, rel=REL)
    assert lw.total_heads == pytest.approx(1.12 * direct / CAP, rel=REL)


def test_two_shift_split_and_roster() -> None:
    """Shifts 06:00-13:00 and 13:00-20:00, later hours to the next day's shift 1. Outbound
    (mock hourly shares h7..h17, lagged 1 h → h8..h18): shift 1 = .04+.08+.11+.13+.12 = 0.48,
    shift 2 = 0.52. Picking 20.8 h → 9.984 / 10.816 h → 1.678 + 1.818 heads → roster × 1.06.
    Inbound flat 06:00-14:00: receiving 1.6 h → 7/8 = 1.4 h and 0.2 h → floor 1 + 1 → 2.12."""
    inp, lw = run()
    pick = act(lw, "picking")
    assert pick.shift_hours == pytest.approx((20.8 * 0.48, 20.8 * 0.52), rel=REL)
    assert pick.shift_heads == pytest.approx((20.8 * 0.48 / CAP, 20.8 * 0.52 / CAP), rel=REL)
    assert pick.roster == pytest.approx(20.8 / CAP * 1.06, rel=REL)
    recv = act(lw, "receiving")
    assert recv.shift_hours == pytest.approx((1.6 * 7 / 8, 1.6 / 8), rel=REL)
    assert recv.shift_heads == (1.0, 1.0)
    assert recv.roster == pytest.approx(2.12, rel=REL)
    assert lw.shift_windows == ((6.0, 13.0), (13.0, 20.0))
    for a in lw.activities:  # every hour lands in a shift (indirect follows the direct hours)
        assert sum(a.shift_hours) == pytest.approx(a.hours, rel=REL), a.activity
    assert lw.roster == pytest.approx(sum(a.roster for a in lw.activities), rel=REL)
    assert value(inp, "labor.picking.shift2.heads") == pytest.approx(20.8 * 0.52 / CAP)


def test_one_shift_reduces_to_I19() -> None:
    """One shift: heads_shift = max(1, hours / (hours_per_shift × utilisation)) if staffed;
    a zero-workload activity is still emitted with roster 0 (I39)."""
    base = build(toy(), dd={"pallets_out": 0.0})
    ops = base.basis.operations.model_copy(update={"shifts_per_day": 1, "hours_per_shift": 7.5})
    inp = dataclasses.replace(base, basis=base.basis.model_copy(update={"operations": ops}))
    lw = labor(inp)
    for a in lw.activities:
        heads = max(1.0, a.hours / (7.5 * 0.85)) if a.hours > 0 else 0.0
        assert a.shift_heads == (pytest.approx(heads, rel=REL),), a.activity
        assert a.roster == pytest.approx(heads * 1.06, rel=REL), a.activity
    pallet = act(lw, "shipping_pallet")
    assert (pallet.hours, pallet.roster) == (0.0, 0.0)
    assert lw.shift_windows == ((6.0, 13.5),)


def test_annual_series_from_daily_workloads() -> None:
    """Base year over the 2 operating days (D3 excluded), × 252 / 2 × 1.04^t (I4, I41).
    Picking: D1 3 shelving + 1 pallet line, D2 1 shelving → (4/70 + 1/35) × 1.12 = 0.096 h.
    Receiving: 20 / gf pallets per day (I22) → 2 × 20 / gf / 14 × 1.12.
    Replenishment: A/B manual units D1 2 + 1 + 1 = 4 (z is C) → 4 / 80 / 14 × 1.12."""
    inp, lw = run()
    pick = act(lw, "picking")
    assert value(inp, "labor.operating_days") == 2
    assert value(inp, "labor.picking.base_hours") == pytest.approx(0.096, rel=REL)
    assert pick.annual_hours == pytest.approx(tuple(0.096 * K * 1.04**t for t in range(1, 6)))
    recv = act(lw, "receiving").annual_hours[0]
    assert recv == pytest.approx(2 * 20 / GF / 14 * PFD * K * 1.04, rel=REL)
    replen = act(lw, "replenishment").annual_hours[0]
    assert replen == pytest.approx(4 / 80 / 14 * PFD * K * 1.04, rel=REL)
    pack_s = act(lw, "packing_S").annual_hours[0]  # one-line orders D1 2, D2 1 (I15 daily)
    assert pack_s == pytest.approx(3 / 55 * PFD * K * 1.04, rel=REL)
    ind = act(lw, "indirect").annual_hours[0]
    direct = sum(a.annual_hours[0] for a in lw.activities if a.activity != "indirect")
    assert ind == pytest.approx(0.12 * direct, rel=REL)
    assert lw.annual_hours[0] == pytest.approx(1.12 * direct, rel=REL)
    assert lw.core_fte[0] == pytest.approx(lw.annual_hours[0] / (1607 * 0.85), rel=REL)


def test_core_heads_and_temp_hours() -> None:
    """I25 with 2 days: P50 = mean, Σ max(0, h_d − P50) = (h_D1 − h_D2) / 2. Inbound is the
    same every day, so the gap is (picking 2/70 + 1/35, packing S 1/55, ML 1/25, parcels
    1/110, pallets 1/14, returns 0.04 × 3/22, replen 0.05/14) × 1.12 × 1.12 (indirect)."""
    inp, lw = run()
    gap = 2 / 70 + 1 / 35 + 1 / 55 + 1 / 25 + 1 / 110 + 1 / 14 + 0.04 * 3 / 22 + 0.05 / 14
    gap *= PFD * 1.12
    assert value(inp, "labor.hours_above_p50") == pytest.approx(gap / 2, rel=REL)
    assert lw.temp_hours == pytest.approx(tuple(gap / 2 * K * 1.04**t for t in range(1, 6)))
    days = sum(a.annual_hours[0] for a in lw.activities) / (K * 1.04)  # h_D1 + h_D2
    assert lw.p50_day_hours == pytest.approx(days / 2, rel=REL)
    assert lw.core_heads_day == pytest.approx(days / 2 / CAP, rel=REL)


def test_cube_decant_and_picking_zones() -> None:
    """cube_asrs: x, z → cube_bin (share 0.7) at the port rate without oee (I38): 700 / 350;
    overflow pallet rack 300 / 35, shelving 0. Decant on the eligible cases (I23): 200 / 90.
    Daily decant = 200 / gf per day; daily cube lines D1 3, D2 1 → 4 / 350."""
    inp, lw = run("cube_asrs")
    assert value(inp, "labor.picking.cube_bin.hours") == pytest.approx(700 / 350 * PFD)
    assert value(inp, "labor.picking.shelving.workload") == 0
    assert act(lw, "picking").hours == pytest.approx((700 / 350 + 300 / 35) * PFD, rel=REL)
    dec = act(lw, "decant")
    assert (dec.workload, dec.hours) == (pytest.approx(200), pytest.approx(200 / 90 * PFD))
    assert dec.role == "operator"
    assert value(inp, "labor.decant.base_hours") == pytest.approx(2 * 200 / GF / 90 * PFD)
    base = value(inp, "labor.picking.base_hours")
    assert base == pytest.approx((4 / 350 + 1 / 35) * PFD, rel=REL)
    replen = act(lw, "replenishment")  # overflow A/B only (I21): y, 100 / 1000 → 2.5 moves
    assert replen.workload == pytest.approx(2.5, rel=REL)


def test_amr_picking_at_station_rate() -> None:
    """amr_gtp: pod_bin zone at station_rate (250), decant at amr decant rate (80)."""
    inp, lw = run("amr_gtp")
    assert value(inp, "labor.picking.pod_bin.hours") == pytest.approx(700 / 250 * PFD)
    assert act(lw, "decant").hours == pytest.approx(200 / 80 * PFD, rel=REL)


def test_receipts_mode_uses_the_daily_receipts() -> None:
    """Receipts inbound (I56): each day carries its own receipts_pallets and receipts_lines
    (D1 2 pallets / 5 lines, D2 10 / 30 → 12 pallets, 35 lines over the base year, not the
    units-prorated 15 and 16.5); decant cases follow the day's units: 200 × 1500 / 2000 = 150.
    A day with an unknown pallet count (null) takes receipts_units × pallets* / units_in*:
    D2 500 × 20 / 2000 = 5."""
    ib = build(toy()).design_day.inbound.model_copy(update={"mode": "receipts"})
    daily = frames()[0].with_columns(
        receipts_pallets=pl.Series([2.0, 10.0, 0.0]), receipts_lines=pl.Series([5.0, 30.0, 0.0])
    )
    inp = build(toy(), dd={"inbound": ib})
    labor(inp, daily)
    assert value(inp, "labor.receiving.base_hours") == pytest.approx(12 / 14 * PFD, rel=REL)
    assert value(inp, "labor.put_away.base_hours") == pytest.approx(12 / 13 * PFD, rel=REL)
    assert value(inp, "labor.receipt_check.base_hours") == pytest.approx(35 / 45 * PFD, rel=REL)
    cube = build(toy(), "cube_asrs", dd={"inbound": ib})
    labor(cube, daily)
    assert value(cube, "labor.decant.base_hours") == pytest.approx(150 / 90 * PFD, rel=REL)
    unknown = build(toy(), dd={"inbound": ib})
    labor(unknown, daily.with_columns(receipts_pallets=pl.Series([2.0, None, 0.0])))
    assert value(unknown, "labor.receiving.base_hours") == pytest.approx(7 / 14 * PFD, rel=REL)
    roots = {"daily": daily, "lines": frames()[1], "sku": cube.sku, "basis": cube.basis,
             "design_day": cube.design_day, "catalog": cube.catalog}  # fmt: skip
    for traced in (inp, cube):  # receipts leaves name the receipts columns actually used
        assert not bad_data_refs(traced.tracer, roots)
    leaves = set(cube.tracer.get(cube.tid("labor.decant.base_hours")).inputs.values())
    assert {"data:daily.receipts_units", "data:design_day.inbound.units_per_day"} <= leaves
    leaves = set(inp.tracer.get(inp.tid("labor.receipt_check.base_hours")).inputs.values())
    assert "data:daily.receipts_lines" in leaves and "data:design_day.growth_rate" not in leaves
    with pytest.raises(WhsizingError, match="lacks column"):
        labor(build(toy(), dd={"inbound": ib}), daily.drop("receipts_lines"))


def test_fractional_outbound_lag_splits_each_hour() -> None:
    """A lag of n + f hours gives hour h (1 − f) of hour h − n and f of hour h − n − 1: lag 0.5
    = mean of the lag-0 and lag-1 profiles, 2.5 = mean of lag 2 and 3 (no half-to-even round)."""

    def outbound(lag: float) -> np.ndarray:
        inp = build(toy())
        lagged = ParamSet(CATALOG, {"labor.outbound_lag_hours": lag})
        return profiles(dataclasses.replace(inp, params=lagged))[0]

    assert outbound(0.5) == pytest.approx((outbound(0) + outbound(1)) / 2, rel=REL)
    assert outbound(2.5) == pytest.approx((outbound(2) + outbound(3)) / 2, rel=REL)
    assert outbound(1.0) == pytest.approx(np.roll(outbound(0), 1), rel=REL)
    assert outbound(0.5).sum() == pytest.approx(1.0, rel=REL)


def test_labor_result_ranges_and_shift_table() -> None:
    """lo world (every standard at its min) has the most hours; ShiftRows of typ per shift and
    activity; core FTE in FTE."""
    worlds = {}
    for w in WORLDS:
        _, worlds[w] = run(world=w)
    res = labor_result(worlds)
    assert res.total_hours.lo == pytest.approx(worlds["hi"].total_hours)
    assert res.total_hours.hi == pytest.approx(worlds["lo"].total_hours)
    assert res.total_hours.typ == worlds["typ"].total_hours
    assert len(res.shifts) == 2 * len(res.activities) == 2 * 11
    assert res.shifts[0].activity == "receiving" and res.shifts[0].start_hour == 6.0
    assert len(res.core_fte) == len(res.temp_hours) == 5 and res.core_fte[0].unit == "FTE"
    pick = next(a for a in res.activities if a.activity == "picking")
    assert pick.role == "operator" and pick.driver == "lines" and pick.workload == 1000


def with_ops(**update: object) -> WorldInputs:
    inp = build(toy())
    ops = inp.basis.operations.model_copy(update=update)
    return dataclasses.replace(inp, basis=inp.basis.model_copy(update={"operations": ops}))


def test_errors() -> None:
    """Missing columns, no operating day, shifts longer than a day."""
    inp = build(toy())
    daily, lines = frames()
    with pytest.raises(WhsizingError, match="lacks column"):
        labor_days(inp, daily.drop("parcels"), lines)
    with pytest.raises(WhsizingError, match="no operating day"):
        labor_days(inp, daily.with_columns(is_operating=False), lines)
    with pytest.raises(WhsizingError, match="missing from the SKU frame"):
        labor_days(inp, daily, lines.with_columns(sku=pl.lit("ghost")))
    with pytest.raises(ConfigError, match="exceed 24 h"):
        labor(with_ops(shifts_per_day=4))


@pytest.mark.parametrize(
    ("field", "bad"),
    [("shifts_per_day", 0), ("hours_per_shift", 0.0), ("hours_per_shift", -7.0),
     ("utilisation", 0.0), ("paid_hours_per_person_day", 0.0)],
)  # fmt: skip
def test_invalid_shift_config_is_a_config_error(field: str, bad: float) -> None:
    """I60: a shift config the roster divides by or loops over → ConfigError naming the field,
    never a raw ZeroDivisionError or a silent roster of 0."""
    with pytest.raises(ConfigError, match=f"operations.{field}"):
        labor(with_ops(**{field: bad}))


def test_inconsistent_inputs_are_rejected() -> None:
    """Hourly lines not 24 finite values; NaN, negative or null daily counts; shipped lines that
    do not match the daily lines (e.g. an empty frame) or fall on a date absent from the daily
    series; a null or non-positive qty_units (I1); a Datetime date in the lines."""
    daily, lines = frames()
    for hourly in ([1.0] * 23, [float("nan")] + [1.0] * 23, [-1.0] + [1.0] * 23):
        with pytest.raises(WhsizingError, match="hourly_lines"):
            labor(build(toy(), dd={"hourly_lines": hourly}))
    for col, v in (("lines", float("nan")), ("parcels", -1000.0), ("parcels", None)):
        with pytest.raises(WhsizingError, match=rf"\['{col}'\] hold"):
            labor(build(toy()), daily.with_columns(pl.lit(v, pl.Float64).alias(col)))
    with pytest.raises(WhsizingError, match="differ from the shipped lines"):
        labor(build(toy()), lines=lines.clear())
    with pytest.raises(WhsizingError, match="differ from the shipped lines"):
        labor(build(toy()), daily.with_columns(lines=pl.col("lines") + 1))
    late = [*ORDERS, ("o6", date(2025, 1, 9), [("x", 1)])]  # D4 is not in the daily series
    with pytest.raises(WhsizingError, match="absent from the daily series"):
        labor(build(toy()), lines=frames(late)[1])
    for q in (0, -2, None, float("nan"), float("inf")):
        bad = lines.with_columns(pl.lit(q, pl.Float64).alias("qty_units"))
        with pytest.raises(WhsizingError, match="qty_units"):
            labor(build(toy()), lines=bad)
    with pytest.raises(WhsizingError, match="differ in type"):
        labor(build(toy()), lines=lines.with_columns(pl.col("date").cast(pl.Datetime)))


def test_an_order_over_two_dates_counts_on_its_first_date() -> None:
    """I1: an order takes its first date, whatever the row order of the lines (T6.8)."""
    span = [("o1", D1, [("x", 1)]), ("o1", D2, [("z", 1)]), *ORDERS[2:]]
    daily, lines = frames(span, DAYS)
    inp = build(toy())
    rows = [labor_days(inp, daily, ls).frame.select("orders_S", "orders_ML").rows()
            for ls in (lines, lines.reverse())]  # fmt: skip
    assert rows[0] == rows[1] == [(1.0, 1.0), (1.0, 0.0)]  # D1: o3 (S), o1 (ML); D2: o4
