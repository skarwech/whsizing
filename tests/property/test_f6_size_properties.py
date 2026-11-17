"""T6.5, T6.7, T6.8 through `size_scenario` (F6z) on tiny_golden, all three families (S0 manual,
S1 amr_gtp inline, S2 cube), Hypothesis over the scale of the demand, the clear height and the
number of shifts.

"More lines" (T6.5) = every order shipped m times under new ids: daily counts, design-day flows,
hourly lines, inbound, SKU line / unit totals and the design stock (`stock_units`, so storage
grows with demand) all × m; one-line orders stay one-line (I15 shares unchanged)."""

from __future__ import annotations

import math
from functools import cache
from typing import Any

import polars as pl
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.unit.test_f6_size import golden_inputs, sized, with_basis

from whsizing.engine import labor_days
from whsizing.engine import size as size_module
from whsizing.engine.inputs import WorldInputs
from whsizing.engine.labor import LaborDays
from whsizing.schemas import ScenarioResult

PROPS = settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
SIDS = st.sampled_from(["S0", "S1", "S2"])
FLOWS = ("lines", "orders", "units", "cube_m3", "weight_kg", "peak_hour_lines", "parcels",
         "pallets_out", "stock_units", "stock_cube_m3")  # fmt: skip
INBOUND = ("units_per_day", "pallets_per_day", "receipt_lines_per_day", "trucks_per_day")
KEYS = ("date", "weekday", "is_operating", "is_holiday")
STATIONS = ("gtp_stations", "ports", "robots")


@cache
def scaled(m: int) -> dict[str, Any]:
    """The golden design day, SKU frame, daily series and shipped lines with every order × m."""
    g = golden_inputs()
    ib = g.design_day.inbound
    inbound = ib.model_copy(
        update={f: getattr(ib, f) * m for f in INBOUND}
        | ({"cases_per_day": ib.cases_per_day * m} if ib.cases_per_day is not None else {})
    )
    dd = g.design_day.model_copy(
        update={f: getattr(g.design_day, f) * m for f in FLOWS}
        | {"hourly_lines": [h * m for h in g.design_day.hourly_lines], "inbound": inbound}
    )
    daily = g.daily.with_columns(pl.col(c) * m for c in g.daily.columns if c not in KEYS)
    lines = pl.concat(
        [g.lines.with_columns(order_id=pl.col("order_id") + f"#{k}") for k in range(m)]
    )
    sku = g.sku.with_columns(pl.col("lines") * m, pl.col("units") * m)
    return {"design_day": dd, "daily": daily, "lines": lines, "sku": sku}


def run(sid: str, m: int, height: float = 8.5, shifts: int = 1) -> ScenarioResult:
    basis = with_basis(building={"clear_height_m": height}, operations={"shifts_per_day": shifts})
    return sized(sid, basis=basis, **scaled(m))[0]


def ge(more: float, less: float) -> bool:
    return more >= less - 1e-9 * abs(less)


@PROPS
@given(
    sid=SIDS,
    m=st.integers(1, 3),
    extra=st.integers(1, 3),
    height=st.floats(3.0, 14.0),
    shifts=st.integers(1, 2),
)
def test_T6_5_more_lines_never_fewer_fte_stations_or_less_area(
    sid: str, m: int, extra: int, height: float, shifts: int
) -> None:
    """Every Range end (lo, typ, hi) of the FTE (design-day hours, heads, roster, annual hours,
    core FTE, every activity's hours), of the stations (GTP stations, cube ports, robots; pack
    stations through the packing zone) and of every area zone, the storage total and the area
    total never falls. Pickers are left out on purpose: with the stock × m some overflow SKUs
    leave shelving for pallet rack (F6a class rule on the design stock cube), and the per-zone
    ceil of I17 then drops pickers_peak (S2: 1 + 1 → 0 + 1) although the picking hours grow."""
    one, more = run(sid, m, height, shifts), run(sid, m + extra, height, shifts)
    acts = more.labor.activities
    pairs = [
        (one.labor.total_hours, more.labor.total_hours),
        (one.labor.total_heads, more.labor.total_heads),
        (one.labor.roster, more.labor.roster),
        *zip(one.labor.annual_hours, more.labor.annual_hours, strict=True),
        *zip(one.labor.core_fte, more.labor.core_fte, strict=True),
        *((a.hours, b.hours) for a, b in zip(one.labor.activities, acts, strict=True)),
        *((one.equipment[k], more.equipment[k]) for k in STATIONS if k in one.equipment),
        *((one.area.zones[z], more.area.zones[z]) for z in one.area.zones),
        (one.storage.total_area_m2, more.storage.total_area_m2),
        (one.area.total_m2, more.area.total_m2),
    ]
    for a, b in pairs:
        for end in ("lo", "typ", "hi"):
            assert ge(getattr(b, end), getattr(a, end)), (sid, a, b, end)
    assert more.labor.total_hours.typ > one.labor.total_hours.typ
    assert more.storage.total_area_m2.typ > one.storage.total_area_m2.typ  # stock grew


def ranges(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict) and {"lo", "typ", "hi", "unit"} <= node.keys():
        return [node]
    items = node.values() if isinstance(node, dict) else node if isinstance(node, list) else []
    return [r for v in items for r in ranges(v)]


def leaves(node: Any) -> list[float]:
    if isinstance(node, dict):
        return [x for v in node.values() for x in leaves(v)]
    if isinstance(node, list):
        return [x for v in node for x in leaves(v)]
    return [node] if isinstance(node, int | float) and not isinstance(node, bool) else []


@PROPS
@given(sid=SIDS, m=st.integers(1, 3), height=st.floats(1.0, 14.0), shifts=st.integers(1, 2))
def test_T6_7_outputs_non_negative_and_ranges_ordered(
    sid: str, m: int, height: float, shifts: int
) -> None:
    """Every number of the result is finite and ≥ 0 and every Range has lo ≤ typ ≤ hi; the
    Ranges really span worlds: the pessimistic world needs at least the hours, storage and
    total area of the optimistic one, and some Range is not a point."""
    basis = with_basis(building={"clear_height_m": height}, operations={"shifts_per_day": shifts})
    result, tracer = sized(sid, basis=basis, **scaled(m))
    tree = result.model_dump(mode="json", exclude={"scenario"})
    assert all(math.isfinite(x) and x >= 0 for x in leaves(tree))
    found = ranges(tree)
    assert len(found) > 100
    for r in found:
        assert 0 <= r["lo"] <= r["typ"] <= r["hi"], r
    assert any(r["lo"] < r["hi"] for r in found)
    for key in ("labor.total.hours", "storage.total_area_m2", "area.total"):
        lo, hi = (tracer.get(f"{sid}.{key}", w).value for w in ("lo", "hi"))
        assert ge(lo, hi), (sid, key, lo, hi)


def shuffled(seed: int) -> dict[str, pl.DataFrame]:
    g = golden_inputs()
    return {
        name: df.sample(fraction=1.0, shuffle=True, seed=seed + i)
        for i, (name, df) in enumerate((("sku", g.sku), ("daily", g.daily), ("lines", g.lines)))
    }


def result_json(sid: str, **change: Any) -> str:
    return sized(sid, **change)[0].model_dump_json(indent=2)


@PROPS
@given(sid=SIDS, seed=st.integers(0, 2**31))
def test_T6_8_row_order_of_the_inputs_does_not_change_result_json(sid: str, seed: int) -> None:
    """Shuffled SKU frame, daily series and shipped lines give the identical result.json."""
    assert result_json(sid, **shuffled(seed)) == result_json(sid)


def test_T6_8_the_check_catches_a_missing_date_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation check on the manual path (S0), whose storage sums are integer-exact: with
    `labor_days` keeping the input row order (its `.sort("date")` removed), a shuffled daily
    series changes result.json, so T6.8 above would catch the missing sort."""

    def unsorted(inp: WorldInputs, daily: pl.DataFrame, lines: pl.DataFrame) -> LaborDays:
        days = labor_days(inp, daily, lines)
        order = daily.filter("is_operating").select("date").with_row_index("i")
        frame = days.frame.join(order, on="date").sort("i").drop("i")
        return LaborDays(frame, days.single_line_share)

    base = result_json("S0")
    monkeypatch.setattr(size_module, "labor_days", unsorted)
    assert result_json("S0") == base  # the golden daily series is already in date order
    assert any(result_json("S0", daily=shuffled(seed)["daily"]) != base for seed in range(5))
