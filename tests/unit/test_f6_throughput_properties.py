"""T6.5, T6.7, T6.8 (F6a/F6b part) as hypothesis properties over generated SKU frames and design
days, every family and world. FTE (T6.5, T6.6) and the area budget are F6c/F6d."""

from __future__ import annotations

from typing import Any

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.unit.test_f6_inputs import build, toy_sku

from whsizing.engine import WORLDS, size_storage, size_throughput, storage_result
from whsizing.engine.storage import StorageWorld
from whsizing.engine.throughput import ThroughputWorld
from whsizing.schemas import FamilyId, Inbound, World
from whsizing.schemas.trace import Tracer

FAMILIES: tuple[FamilyId, ...] = ("manual_p2p", "cube_asrs", "amr_gtp")
PROPS = settings(max_examples=25, deadline=None)  # 3-6 engine runs per example
DIM = st.floats(10.0, 900.0, allow_nan=False)
PACK = st.none() | st.integers(1, 500)

SKU_ROW = st.fixed_dictionaries(
    {
        "dims": st.none() | st.tuples(DIM, DIM, DIM),
        "weight": st.floats(0.05, 40.0, allow_nan=False),
        "avg_stock": st.floats(0.0, 3000.0, allow_nan=False),
        "lines": st.integers(0, 400),
        "units_per_line": st.integers(1, 12),
        "abc": st.sampled_from("ABC"),
        "upp": PACK,
        "upc": PACK,
        "cpp": PACK,
        "hazmat": st.none() | st.booleans(),
    }
)


def _frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Shipped units = lines × units per line (derived inbound needs units, as from F3/F4)."""
    return toy_sku(
        *(
            {"sku": f"s{i:02d}", "units": r["lines"] * r["units_per_line"], **r}
            for i, r in enumerate(rows)
        )
    )


SKUS = (
    st.lists(SKU_ROW, min_size=1, max_size=12)
    .filter(lambda rows: any(r["lines"] for r in rows))  # a design day has lines
    .map(_frame)
)
SCALE = st.floats(0.05, 20.0, allow_nan=False)


def day(k: float) -> dict[str, Any]:
    """The `build` design day (1000 lines, peak 150, 2000 units, 10 pallets out, inbound 2000
    units / 20 pallets) with every flow × k; stock unchanged."""
    inbound = Inbound(
        mode="derived",
        units_per_day=2000.0 * k,
        pallets_per_day=20.0 * k,
        receipt_lines_per_day=50.0 * k,
        trucks_per_day=1.0 * k,
        peak_factor=1.5,
    )
    flows = {"lines": 1000.0, "peak_hour_lines": 150.0, "units": 2000.0, "pallets_out": 10.0}
    return {**{m: v * k for m, v in flows.items()}, "inbound": inbound}


def run(
    sku: pl.DataFrame, family: FamilyId, k: float = 1.0
) -> tuple[Tracer, dict[World, tuple[Any, StorageWorld, ThroughputWorld]]]:
    tracer = Tracer("S9")
    out: dict[World, tuple[Any, StorageWorld, ThroughputWorld]] = {}
    for w in WORLDS:
        inp = build(sku, family, w, tracer=tracer, dd=day(k))
        st_w = size_storage(inp)
        out[w] = (inp, st_w, size_throughput(inp, st_w))
    return tracer, out


@pytest.mark.parametrize("family", FAMILIES)
@PROPS
@given(sku=SKUS, k=SCALE, more=st.floats(1.0, 8.0, allow_nan=False))
def test_T6_5_more_lines_never_fewer_stations(
    family: FamilyId, sku: pl.DataFrame, k: float, more: float
) -> None:
    """T6.5 (F6a/F6b part): scaling every design-day flow by `more` ≥ 1 at constant stock never
    lowers a station, port, robot, picker, cart or forklift count, in any world. Storage area
    grows with stock, not flows: tests/property/test_f6_size_properties.py T6.5 scales both."""
    _, base = run(sku, family, k)
    _, big = run(sku, family, k * more)
    for w in WORLDS:
        eq0, eq1 = base[w][2].equipment, big[w][2].equipment
        assert eq0.keys() == eq1.keys()
        assert all(eq1[r] >= eq0[r] for r in eq0), (w, eq0, eq1)


@pytest.mark.parametrize("family", FAMILIES)
@PROPS
@given(sku=SKUS, k=SCALE)
def test_T6_7_outputs_non_negative_and_worlds_ordered(
    family: FamilyId, sku: pl.DataFrame, k: float
) -> None:
    """T6.7 (F6a/F6b part): every traced quantity ≥ 0; the Ranges of `storage_result` validate
    (Range rejects lo > typ > hi). The non-trivial part (ADR-002): the pessimistic world needs at
    least the positions, area and equipment of typ, and typ at least those of the optimistic
    world, so lo/hi are the worlds' extremes and not an artefact of min/max."""
    tracer, out = run(sku, family, k)
    assert all(n.value >= 0 for n in tracer.nodes), [n.id for n in tracer.nodes if n.value < 0]
    storage_result({w: out[w][1] for w in WORLDS}, out["typ"][0].eligibility)
    for i in range(len(out["typ"][1].classes)):
        for field in ("positions", "area_m2"):
            v = [getattr(out[w][1].classes[i], field) for w in WORLDS]
            assert v == sorted(v, reverse=True), (i, field, v)
    total = [out[w][1].total_area_m2 for w in WORLDS]
    assert total == sorted(total, reverse=True)
    for r in out["typ"][2].equipment:
        counts = [out[w][2].equipment[r] for w in WORLDS]
        assert counts == sorted(counts, reverse=True), (r, counts)


@pytest.mark.parametrize("family", FAMILIES)
@PROPS
@given(sku=SKUS, k=SCALE, data=st.data())
def test_T6_8_row_order_does_not_change_the_result(
    family: FamilyId, sku: pl.DataFrame, k: float, data: st.DataObject
) -> None:
    """T6.8 (F6a/F6b part): any permutation of the SKU rows gives the same trace in every world,
    value for value (exact: the engine sorts by sku before any sum), bottleneck and flags."""
    order = data.draw(st.permutations(range(sku.height)))
    a, ra = run(sku, family, k)
    b, rb = run(sku[list(order)], family, k)
    assert {(n.id, n.world): n.value for n in a.nodes} == {
        (n.id, n.world): n.value for n in b.nodes
    }
    for w in WORLDS:
        assert (ra[w][2].bottleneck, ra[w][2].flags) == (rb[w][2].bottleneck, rb[w][2].flags)
        assert ra[w][1].flags == rb[w][1].flags
