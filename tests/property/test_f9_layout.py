"""F9a block diagram layout, property tests: for any zones and building, the rectangles add up to
the zone areas (T9.6), never overlap, stay in the envelope or are marked overflow, and the
overflow area is exactly the deficit."""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from whsizing.report import layout_blocks

NAMES = ("storage", "receiving_staging", "shipping_staging", "packing", "ports", "returns",
         "equipment", "amenities", "circulation")  # fmt: skip
zones_st = st.dictionaries(
    st.sampled_from(NAMES), st.floats(min_value=0.5, max_value=5000, allow_nan=False), min_size=1
)
building_st = st.floats(min_value=50, max_value=60000, allow_nan=False)


def overlap(a, b) -> float:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return max(w, 0.0) * max(h, 0.0)


@settings(max_examples=200, deadline=None)
@given(zones=zones_st, building=building_st)
def test_T9_6_property_drawn_area_is_the_zone_sum(zones: dict[str, float], building: float) -> None:
    layout = layout_blocks(zones, building)
    total = sum(zones.values())
    assert abs(layout.drawn_m2 - total) <= 1e-9 * total
    for zone, m2 in zones.items():
        got = sum(r.area for r in layout.rects if r.zone == zone)
        assert abs(got - m2) <= 1e-9 * m2


@settings(max_examples=200, deadline=None)
@given(zones=zones_st, building=building_st)
def test_T9_6_property_no_overlap_and_the_envelope_is_respected(
    zones: dict[str, float], building: float
) -> None:
    layout = layout_blocks(zones, building)
    rects = layout.rects
    eps = 1e-6
    for i, a in enumerate(rects):
        assert a.x >= -eps and a.x + a.w <= layout.width_m + eps
        if not a.overflow:
            assert a.y + a.h <= layout.height_m + eps
        else:
            assert a.y >= layout.height_m - eps
        for b in rects[i + 1 :]:
            assert overlap(a, b) <= 1e-6 * max(a.area, b.area, 1.0)


@settings(max_examples=200, deadline=None)
@given(zones=zones_st, building=building_st)
def test_T9_6_property_overflow_area_is_the_deficit(
    zones: dict[str, float], building: float
) -> None:
    layout = layout_blocks(zones, building)
    over = sum(r.area for r in layout.rects if r.overflow)
    deficit = max(0.0, sum(zones.values()) - building)
    assert abs(over - deficit) <= 1e-6 * max(deficit, 1.0)
    assert abs(layout.deficit_m2 - deficit) <= 1e-9 * max(deficit, 1.0)
    if "storage" in zones:  # storage is placed first, across the whole width
        first = layout.rects[0]
        assert first.zone == "storage" and first.x == 0.0 and first.y == 0.0
        assert abs(first.w - layout.width_m) <= 1e-9


@settings(max_examples=200, deadline=None)
@given(zones=zones_st, building=building_st)
def test_T9_6_property_docks_are_on_the_south_wall_whenever_they_fit(
    zones: dict[str, float], building: float
) -> None:
    docks = [z for z in ("receiving_staging", "shipping_staging") if z in zones]
    assume(docks and sum(zones[z] for z in docks) < building)
    layout = layout_blocks(zones, building)
    for r in layout.rects:
        if r.zone in docks:
            assert not r.overflow
            assert abs(r.y + r.h - layout.height_m) <= 1e-6 * layout.height_m
