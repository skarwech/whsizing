"""F6c properties (labor part of T6.5, T6.6, T6.7, T6.8) on the toy of tests/unit/test_f6_labor.

T6.5: more lines → hours, heads, roster and core FTE never fall. T6.6: doubling the lines (every
workload: design day, inbound, daily history) and every productivity leaves hours, heads,
roster, core FTE and temp hours unchanged. T6.7: every LaborResult Range is finite, ≥ 0 and
lo ≤ typ ≤ hi. T6.8: the row order of the SKU frame, daily series and shipped lines does not
change the result."""

from __future__ import annotations

import dataclasses
import math
from datetime import date, timedelta

import polars as pl
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.unit.test_f6_inputs import CATALOG, build
from tests.unit.test_f6_labor import frames
from tests.unit.test_f6_throughput import toy

from whsizing.catalog import ParamSet
from whsizing.engine import WORLDS, WorldInputs, size_storage, size_throughput
from whsizing.engine.labor import LaborWorld, labor_days, labor_result, size_labor
from whsizing.schemas import FamilyId, World

# every productivity F6c divides by (labor standards, pick / port / station and decant rates)
RATES = [p for p in CATALOG.params if p.startswith("labor.")] + [
    "manual_p2p.pick_rate_shelving_lines_h",
    "manual_p2p.pick_rate_pallet_lines_h",
    "cube_asrs.port_rate_lines_h",
    "amr_gtp.station_rate_lines_h",
    "cube_asrs.decant_cases_per_h",
    "amr_gtp.decant_cases_per_h",
]
D0 = date(2025, 1, 6)
SKUS = ("x", "y", "z")

orders_st = st.lists(
    st.tuples(
        st.integers(0, 3),  # day
        st.lists(st.tuples(st.sampled_from(SKUS), st.integers(1, 5)), min_size=1, max_size=3),
    ),
    min_size=1,
    max_size=25,
)
families = st.sampled_from(["manual_p2p", "cube_asrs", "amr_gtp"])
design_st = st.fixed_dictionaries(
    {
        "lines": st.floats(10, 5000),
        "orders": st.floats(5, 3000),
        "units": st.floats(10, 9000),
        "parcels": st.floats(0, 3000),
        "pallets_out": st.floats(0, 50),
        "in_units": st.floats(0, 9000),
        "in_pallets": st.floats(0, 60),
        "in_lines": st.floats(0, 200),
    }
)


def _run(
    family: FamilyId, d: dict[str, float], orders: list[tuple[int, list[tuple[str, int]]]], k: float
) -> LaborWorld:
    """Labor of the toy with every workload × k and every productivity × k (typ world)."""
    base = build(toy(), family)
    ib = base.design_day.inbound.model_copy(
        update={
            "units_per_day": d["in_units"] * k,
            "pallets_per_day": d["in_pallets"] * k,
            "receipt_lines_per_day": d["in_lines"] * k,
        }
    )
    hourly = [h * k for h in base.design_day.hourly_lines]
    dd = {f: d[f] * k for f in ("lines", "orders", "units", "parcels", "pallets_out")}
    inp = build(toy(), family, dd=dd | {"inbound": ib, "hourly_lines": hourly})
    over = {p: CATALOG.params[p].typ * k for p in RATES}
    inp = dataclasses.replace(inp, params=ParamSet(CATALOG, over))
    copies = range(int(k))  # k = 2: every order twice, under a new id
    hist = [
        (f"o{i}c{c}", D0 + timedelta(days=day), items)
        for i, (day, items) in enumerate(orders)
        for c in copies
    ]
    days = [(D0 + timedelta(days=i), True, (i + 1.0) * k, i % 2 * k, 0.0) for i in range(4)]
    daily, lines = frames(hist, days)
    return _labor(inp, daily, lines)


def _labor(inp: WorldInputs, daily: object, lines: object) -> LaborWorld:
    tp = size_throughput(inp, size_storage(inp))
    return size_labor(inp, tp, labor_days(inp, daily, lines))  # pyright: ignore[reportArgumentType]


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    family=st.sampled_from(["manual_p2p", "cube_asrs", "amr_gtp"]),
    d=design_st,
    orders=orders_st,
)
def test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged(
    family: FamilyId, d: dict[str, float], orders: list[tuple[int, list[tuple[str, int]]]]
) -> None:
    one, two = _run(family, d, orders, 1.0), _run(family, d, orders, 2.0)
    for a, b in zip(one.activities, two.activities, strict=True):
        assert a.activity == b.activity
        k = 1 if a.activity == "indirect" else 2  # indirect's workload is the direct hours
        assert b.workload == pytest.approx(k * a.workload, rel=1e-9, abs=1e-12), a.activity
        for f in ("hours", "heads", "roster", "annual_hours", "shift_heads"):
            assert getattr(b, f) == pytest.approx(getattr(a, f), rel=1e-9, abs=1e-12), (a, f)
    for f in ("total_heads", "roster", "core_fte", "temp_hours", "core_heads_day"):
        assert getattr(two, f) == pytest.approx(getattr(one, f), rel=1e-9, abs=1e-12), f


def _inputs(
    family: FamilyId,
    d: dict[str, float],
    world: World = "typ",
    k: float = 1.0,
    sku: pl.DataFrame | None = None,
) -> WorldInputs:
    """Toy inputs with the design day `d`, every flow × k (hourly lines too)."""
    base = build(toy(), family)
    ib = base.design_day.inbound.model_copy(
        update={
            "units_per_day": d["in_units"] * k,
            "pallets_per_day": d["in_pallets"] * k,
            "receipt_lines_per_day": d["in_lines"] * k,
        }
    )
    dd = {f: d[f] * k for f in ("lines", "orders", "units", "parcels", "pallets_out")} | {
        "inbound": ib,
        "hourly_lines": [h * k for h in base.design_day.hourly_lines],
    }
    return build(toy() if sku is None else sku, family, world, dd=dd)


def _history(
    orders: list[tuple[int, list[tuple[str, int]]]],
    m: int = 1,
    extra: frozenset[int] = frozenset(),
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(daily, lines) over 4 operating days: every order m times (parcels, pallets out × m);
    order i in `extra` gets one more line."""
    hist = [
        (f"o{i}c{c}", D0 + timedelta(days=day), items + items[:1] * (i in extra))
        for i, (day, items) in enumerate(orders)
        for c in range(m)
    ]
    days = [(D0 + timedelta(days=i), True, (i + 1.0) * m, i % 2 * m * 1.0, 0.0) for i in range(4)]
    return frames(hist, days)


def _ge(more: float | tuple[float, ...], less: float | tuple[float, ...]) -> bool:
    """more ≥ less, element-wise for tuples (relative tolerance 1e-9)."""
    if isinstance(more, tuple) and isinstance(less, tuple):
        return all(_ge(m, n) for m, n in zip(more, less, strict=True))
    assert isinstance(more, float | int) and isinstance(less, float | int)
    return more >= less - 1e-9 * abs(less)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    family=families,
    d=design_st,
    orders=orders_st,
    k=st.floats(1, 3),
    m=st.integers(1, 3),
    extra=st.frozensets(st.integers(0, 24)),
)
def test_T6_5_more_lines_never_fewer_labor_hours_or_fte(
    family: FamilyId,
    d: dict[str, float],
    orders: list[tuple[int, list[tuple[str, int]]]],
    k: float,
    m: int,
    extra: frozenset[int],
) -> None:
    """More lines: every design flow × k ≥ 1, every history order m ≥ 1 times, and one more
    line on the orders in `extra`. Hours, heads, annual hours, core FTE and core heads never
    fall. An extra line can turn a one-line order multi-line, moving hours from packing_S to
    the slower packing_ML: packing_S alone may fall, and the total roster too when packing_S
    loses its floor-1 heads (I19), so the roster is checked only for pure volume growth."""
    one = _labor(_inputs(family, d), *_history(orders))
    more = _labor(_inputs(family, d, k=k), *_history(orders, m, extra))
    for a, b in zip(one.activities, more.activities, strict=True):
        if extra and a.activity == "packing_S":
            continue
        for f in ("hours", "heads", "shift_heads", "roster", "annual_hours"):
            assert _ge(getattr(b, f), getattr(a, f)), (a.activity, f)
    for f in ("total_hours", "total_heads", "annual_hours", "core_fte", "core_heads_day"):
        assert _ge(getattr(more, f), getattr(one, f)), f
    assert extra or _ge(more.roster, one.roster)


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(family=families, d=design_st, orders=orders_st)
def test_T6_7_labor_outputs_non_negative_and_worlds_ordered(
    family: FamilyId, d: dict[str, float], orders: list[tuple[int, list[tuple[str, int]]]]
) -> None:
    """Every LaborResult Range is finite, ≥ 0 and lo ≤ typ ≤ hi; workloads and shift rows ≥ 0.
    The pessimistic world (every standard at its min) needs the most hours."""
    daily, lines = _history(orders)
    worlds: dict[World, LaborWorld] = {
        w: _labor(_inputs(family, d, w), daily, lines) for w in WORLDS
    }
    res = labor_result(worlds)
    ranges = [res.total_hours, res.total_heads, res.roster]
    ranges += [*res.annual_hours, *res.core_fte, *res.temp_hours]
    for a in res.activities:
        ranges += [a.hours, a.heads, a.roster, *a.annual_hours]
        assert a.workload >= 0, a.activity
    for r in ranges:
        assert 0 <= r.lo <= r.typ <= r.hi and math.isfinite(r.hi), r
    assert all(row.hours >= 0 and row.heads >= 0 for row in res.shifts)
    assert worlds["lo"].total_hours >= worlds["typ"].total_hours >= worlds["hi"].total_hours


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    family=families,
    d=design_st,
    orders=st.lists(
        st.tuples(st.integers(0, 6), st.integers(0, 3), st.sampled_from(SKUS), st.integers(1, 5)),
        min_size=1,
        max_size=30,
    ),
    seed=st.integers(0, 2**32 - 1),
)
def test_T6_8_row_order_does_not_change_labor(
    family: FamilyId,
    d: dict[str, float],
    orders: list[tuple[int, int, str, int]],
    seed: int,
) -> None:
    """Shuffled SKU frame, daily series and shipped lines give the identical LaborWorld. Order
    ids repeat across days, so some orders span two dates (I1: the order's first date)."""
    hist = [(f"o{o}", D0 + timedelta(days=day), [(s, q)]) for o, day, s, q in orders]
    days = [(D0 + timedelta(days=i), True, i + 1.0, float(i % 2), 0.0) for i in range(4)]
    daily, lines = frames(hist, days)

    def shuffle(df: pl.DataFrame) -> pl.DataFrame:
        return df.sample(fraction=1.0, shuffle=True, seed=seed)

    one = _labor(_inputs(family, d), daily, lines)
    two = _labor(_inputs(family, d, sku=shuffle(toy())), shuffle(daily), shuffle(lines))
    assert two == one
