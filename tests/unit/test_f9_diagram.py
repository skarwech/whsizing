"""T9.6: the block diagram. The total drawn area equals the zone sum (geometry and the SVG file
itself), also when the total exceeds the building and the overflow is drawn outside; the layout
rules of the spec (storage first across the width, receiving and shipping on the dock wall,
scale 1 m = 2 px, labels with name and m2)."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from tests.unit.test_f9_tables_support import private_run, report_data

from whsizing.errors import ConfigError
from whsizing.report import ReportData, build_diagram, build_diagrams, layout_blocks
from whsizing.report.diagram import PX_PER_M
from whsizing.schemas.run import RunOutput

GROUP = re.compile(r'<g id="zone-([a-z_]+)-(\d+)">\s*<path d="([^"]+)"', re.S)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def svg_pieces(svg: str) -> list[tuple[str, float]]:
    """(zone, area in m2) of every zone rectangle of an SVG written by `build_diagram`: the
    shoelace area of its path in SVG units, over the scale (2 px per m) squared."""
    out = []
    for zone, _, d in GROUP.findall(svg):
        nums = [float(x) for x in NUMBER.findall(d)]
        pts = list(zip(nums[0::2], nums[1::2], strict=True))
        pts = pts[:4]
        area = (
            abs(
                sum(
                    x1 * y2 - x2 * y1
                    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=True)
                )
            )
            / 2
        )
        out.append((zone, area / PX_PER_M**2))
    return out


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9a_diagram")


@pytest.fixture(scope="module")
def data(run: RunOutput) -> ReportData:
    return report_data(run)


def zones_of(run: RunOutput, sid: str) -> dict[str, float]:
    return {z: r.typ for z, r in run.results[sid].area.zones.items()}


@pytest.mark.parametrize("sid", ["S0", "S1", "S2"])
def test_T9_6_drawn_area_equals_the_zone_sum(
    run: RunOutput, data: ReportData, sid: str, tmp_path: Path
) -> None:
    zones = zones_of(run, sid)
    area = run.results[sid].area
    layout = layout_blocks(zones, area.building_m2, sid)
    assert layout.total_m2 == pytest.approx(area.total_m2.typ, rel=1e-12)
    assert layout.drawn_m2 == pytest.approx(sum(zones.values()), rel=1e-12)
    for zone, m2 in zones.items():
        assert sum(r.area for r in layout.rects if r.zone == zone) == pytest.approx(m2, rel=1e-12)
    assert not any(r.overflow for r in layout.rects) and layout.deficit_m2 == 0.0
    # and in the file: one <g id="zone-..."> per rectangle, areas read back from the SVG paths
    path = build_diagram(data, sid, tmp_path / "report")
    assert path == tmp_path / "report" / f"diagram_{sid}.svg"
    pieces = svg_pieces(path.read_text(encoding="utf-8"))
    assert len(pieces) == len(layout.rects)
    assert sum(a for _, a in pieces) == pytest.approx(sum(zones.values()), rel=1e-4)
    for zone, m2 in zones.items():
        assert sum(a for z, a in pieces if z == zone) == pytest.approx(m2, rel=1e-4), zone


def test_T9_6_overflow_is_drawn_hatched_outside_with_the_deficit(
    run: RunOutput, data: ReportData, tmp_path: Path
) -> None:
    zones = zones_of(run, "S0")
    total = sum(zones.values())
    small = total * 0.6  # the building is smaller than the budget
    layout = layout_blocks(zones, small, "S0")
    over = [r for r in layout.rects if r.overflow]
    assert over and layout.deficit_m2 == pytest.approx(total - small)
    assert layout.drawn_m2 == pytest.approx(total, rel=1e-12)  # drawn = zone sum, overflow included
    assert sum(r.area for r in over) == pytest.approx(layout.deficit_m2, rel=1e-9)
    assert all(r.y >= layout.height_m - 1e-9 for r in over)
    inside = [r for r in layout.rects if not r.overflow]
    assert all(r.y + r.h <= layout.height_m + 1e-9 for r in inside)
    # through build_diagram on a run whose building is too small
    res = run.results["S0"]
    area = res.area.model_copy(update={"building_m2": small})
    run2 = run.model_copy(
        update={"results": {**run.results, "S0": res.model_copy(update={"area": area})}}
    )
    path = build_diagram(dataclasses.replace(data, run=run2), "S0", tmp_path)
    svg = path.read_text(encoding="utf-8")
    assert sum(a for _, a in svg_pieces(svg)) == pytest.approx(total, rel=1e-4)
    assert "<pattern" in svg  # the hatch
    assert re.search(rf"Deficit: {round(total - small):,} m²", svg)


def test_T9_6_layout_follows_the_spec_algorithm(run: RunOutput) -> None:
    zones = zones_of(run, "S2")
    area = run.results["S2"].area
    layout = layout_blocks(zones, area.building_m2, "S2")
    width = layout.width_m
    storage = next(r for r in layout.rects if r.zone == "storage")
    # storage first, a rectangle spanning the building width, height = area / width
    assert (storage.x, storage.y, storage.w) == (0.0, 0.0, pytest.approx(width))
    assert storage.h == pytest.approx(zones["storage"] / width)
    # the other zones in strips under it, by area descending
    strips = [
        r
        for r in layout.rects
        if r.zone not in ("storage", "receiving_staging", "shipping_staging")
    ]
    assert all(r.y >= storage.h - 1e-9 for r in strips)
    ordered = sorted(strips, key=lambda r: (r.y, r.x))
    areas = [r.area for r in ordered]
    assert areas == sorted(areas, reverse=True)
    # receiving and shipping along the dock wall (south), receiving west, shipping east
    recv = next(r for r in layout.rects if r.zone == "receiving_staging")
    ship = next(r for r in layout.rects if r.zone == "shipping_staging")
    assert recv.y + recv.h == pytest.approx(layout.height_m) == pytest.approx(ship.y + ship.h)
    assert recv.x == 0.0 and ship.x + ship.w == pytest.approx(width)


def test_T9_6_scale_is_two_pixels_per_metre(
    run: RunOutput, data: ReportData, tmp_path: Path
) -> None:
    layout = layout_blocks(zones_of(run, "S1"), run.results["S1"].area.building_m2, "S1")
    svg = build_diagram(data, "S1", tmp_path).read_text(encoding="utf-8")
    d = next(d for zone, _, d in GROUP.findall(svg) if zone == "storage")
    xs = [float(x) for x in NUMBER.findall(d)][0::2]
    assert max(xs) - min(xs) == pytest.approx(layout.width_m * 2, rel=1e-4)


@pytest.mark.parametrize(
    ("lang", "storage", "unit"), [("en", "Storage", "m²"), ("fr", "Stockage", "m²")]
)
def test_T9_6_labels_carry_the_zone_name_and_its_area(
    run: RunOutput, lang: str, storage: str, unit: str, tmp_path: Path
) -> None:
    data = report_data(run, lang)
    svg = build_diagram(data, "S0", tmp_path).read_text(encoding="utf-8")
    m2 = round(run.results["S0"].area.zones["storage"].typ)
    assert re.search(rf"{storage}\s+{m2:,} {unit}".replace(",", "[, ]?"), svg)
    assert data.run_id in svg  # the source note
    assert "Source" in svg


def test_T9_6_the_svg_is_reproducible(data: ReportData, tmp_path: Path) -> None:
    first = build_diagram(data, "S2", tmp_path / "a").read_bytes()
    second = build_diagram(data, "S2", tmp_path / "b").read_bytes()
    assert first == second


def test_T9_6_build_diagrams_skips_a_scenario_not_computed(run: RunOutput, tmp_path: Path) -> None:
    from whsizing.scenarios.compare import compare, not_computed_result

    results = {**run.results, "S1": not_computed_result(run.results["S1"].scenario, "x", 12000.0)}
    finances = {k: v for k, v in run.finances.items() if k != "S1"}
    run2 = run.model_copy(
        update={
            "results": results,
            "finances": finances,
            "comparison": compare(results, finances, None),
        }
    )
    paths = build_diagrams(report_data(run2), tmp_path)
    assert sorted(paths) == ["S0", "S2"] and all(p.is_file() for p in paths.values())


def test_T9_6_a_building_without_area_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="building area"):
        layout_blocks({"storage": 10.0}, 0.0, "S0")


# ------------------------------------------------------------------ fix round 1
AUDIT_ZONES = {
    "storage": 5000.0,
    "packing": 900.0,
    "receiving_staging": 600.0,
    "shipping_staging": 700.0,
    "circulation": 1500.0,
    "amenities": 200.0,
    "equipment": 50.0,
}


def overlap(a, b) -> float:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return max(w, 0.0) * max(h, 0.0)


@pytest.mark.parametrize("utilisation", [0.5, 0.85, 0.9, 0.99, 1.0, 1.1, 1.5])
def test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation(
    utilisation: float,
) -> None:
    """They left the wall above about 87 % and were drawn mid-building (or outside it): the near
    fit is the central question of the study."""
    total = sum(AUDIT_ZONES.values())
    layout = layout_blocks(AUDIT_ZONES, total / utilisation, "S1")
    (recv,) = [r for r in layout.rects if r.zone == "receiving_staging"]
    (ship,) = [r for r in layout.rects if r.zone == "shipping_staging"]
    for dock in (recv, ship):
        assert not dock.overflow
        assert dock.y + dock.h == pytest.approx(layout.height_m)  # on the south wall
    assert recv.x == 0.0 and ship.x + ship.w == pytest.approx(layout.width_m)
    assert layout.drawn_m2 == pytest.approx(total)
    over = sum(r.area for r in layout.rects if r.overflow)
    assert over == pytest.approx(max(0.0, total - total / utilisation), abs=1e-6)
    for i, a in enumerate(layout.rects):
        for b in layout.rects[i + 1 :]:
            assert overlap(a, b) < 1e-6, (a, b)


def test_T9_6_docks_larger_than_the_building_join_the_strips_and_keep_their_area() -> None:
    zones = {"storage": 100.0, "receiving_staging": 300.0, "shipping_staging": 300.0}
    layout = layout_blocks(zones, 200.0, "S1")
    assert layout.drawn_m2 == pytest.approx(700.0)
    assert sum(r.area for r in layout.rects if r.overflow) == pytest.approx(500.0)


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_T9_6_labels_of_a_narrow_building_stay_inside_the_picture(
    run: RunOutput, lang: str
) -> None:
    """'Building 60 m²' (right-aligned) and 'Deficit' (centred) started left of the SVG."""
    from matplotlib.text import Text

    from whsizing.report.diagram import draw_diagram

    zones = {"storage": 40.0, "packing": 15.0, "receiving_staging": 5.0, "shipping_staging": 5.0}
    layout = layout_blocks({**zones, "circulation": 10.0}, 60.0, "S1")  # 75 m² in 60: a deficit
    assert layout.deficit_m2 == 15.0
    fig = draw_diagram(layout, report_data(run, lang))
    renderer = fig.canvas.get_renderer()  # pyright: ignore[reportAttributeAccessIssue]
    texts = [t for t in fig.findobj(Text) if t.get_text().strip()]
    assert any("60" in t.get_text() for t in texts) and any("15" in t.get_text() for t in texts)
    for t in texts:
        box = t.get_window_extent(renderer)
        assert box.x0 >= 0 and box.x1 <= fig.bbox.width, t.get_text()


def test_T9_6_the_svg_is_sized_in_px_so_that_one_metre_is_two_px(
    run: RunOutput, data: ReportData, tmp_path: Path
) -> None:
    """The file said width='560pt' for a 560 unit viewBox: 2.67 CSS px per metre, not 2."""
    svg = build_diagram(data, "S1", tmp_path).read_text(encoding="utf-8")
    root = re.search(
        r'<svg [^>]*width="([\d.]+)px" height="([\d.]+)px" viewBox="0 0 ([\d.]+) ([\d.]+)"', svg
    )
    assert root, svg[:400]
    w, h, vb_w, vb_h = (float(x) for x in root.groups())
    assert (w, h) == (vb_w, vb_h)  # 1 user unit = 1 px
    layout = layout_blocks(zones_of(run, "S1"), run.results["S1"].area.building_m2, "S1")
    d = next(d for zone, _, d in GROUP.findall(svg) if zone == "storage")
    xs = [float(x) for x in NUMBER.findall(d)][0::2]
    assert (max(xs) - min(xs)) / layout.width_m == pytest.approx(2.0, rel=1e-4)  # px per metre


def test_T9_6_an_unwritable_folder_is_a_whsizing_error(data: ReportData, tmp_path: Path) -> None:
    from whsizing.errors import WhsizingError

    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(WhsizingError, match="cannot write"):
        build_diagram(data, "S1", blocker / "report")


def text_overlaps(fig) -> list[tuple[str, str]]:
    from matplotlib.text import Text

    renderer = fig.canvas.get_renderer()
    texts = [t for t in fig.findobj(Text) if t.get_text().strip()]
    boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in texts]
    return [
        (a, b)
        for i, (a, ba) in enumerate(boxes)
        for b, bb in boxes[i + 1 :]
        if ba.x0 < bb.x1 - 0.5
        and bb.x0 < ba.x1 - 0.5
        and ba.y0 < bb.y1 - 0.5
        and bb.y0 < ba.y1 - 0.5
    ]


@pytest.mark.parametrize("building_m2", [300.0, 600.0, 1000.0, 1500.0])
@pytest.mark.parametrize("lang", ["en", "fr"])
def test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source(
    run: RunOutput, lang: str, building_m2: float
) -> None:
    """The legend is one row per zone (12 px), the picture was as tall as the envelope only: with
    nine zones in a building under ~1,100 m² the last rows were drawn over the footnotes."""
    from whsizing.report.diagram import draw_diagram

    zones = zones_of(run, "S1")
    assert len(zones) >= 9
    scale = 0.75 * building_m2 / sum(zones.values())  # fits: the envelope is not the overflow
    layout = layout_blocks({z: a * scale for z, a in zones.items()}, building_m2, "S1")
    assert layout.deficit_m2 == 0
    fig = draw_diagram(layout, report_data(run, lang))
    assert text_overlaps(fig) == []


# ------------------------------------------------------------------ R7.2: legible labels
FONT_SIZE = re.compile(r'<text style="font-size: ([\d.]+)px[^>]*>([^<]*)</text>')
LEGIBLE_PX = 8.0  # a zone label: 6.4 pt where the 560 px drawing is set 0.8 pt per px
NOTE_PX = 6.5  # caption and source note


def big_zones_layout(run: RunOutput, building_m2: float = 3000.0):
    """The zones of S1 scaled up to fill 80 % of a building: a few of them hold a label."""
    zones = zones_of(run, "S1")
    k = 0.8 * building_m2 / sum(zones.values())
    return layout_blocks({z: a * k for z, a in zones.items()}, building_m2, "S1")


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_R7_2_the_svg_text_is_set_at_legible_sizes(
    run: RunOutput, lang: str, tmp_path: Path
) -> None:
    """The labels were 5.5 px in a 560 px drawing: 4.4 pt on the A4 page. 1 m = 2 px stays."""
    svg = build_diagram(report_data(run, lang), "S1", tmp_path).read_text(encoding="utf-8")
    sizes = [(float(px), text) for px, text in FONT_SIZE.findall(svg)]
    entries = [text for _, text in sizes if "m²" in text and "  " in text]  # legend entries
    assert len(entries) == len(zones_of(run, "S1"))  # one per zone, name and area
    assert all(px >= LEGIBLE_PX for px, text in sizes if "m²" in text), sizes
    assert all(px >= NOTE_PX for px, _ in sizes), sizes  # also the caption and the source note
    assert min(px for px, _ in sizes) < max(px for px, _ in sizes)  # the title stays the largest


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_R7_2_a_label_goes_inside_a_zone_only_when_it_fits_else_the_legend_names_it(
    run: RunOutput, lang: str
) -> None:
    from matplotlib.text import Text

    from whsizing.report import t
    from whsizing.report.diagram import draw_diagram
    from whsizing.report.i18n import fmt_number

    layout = big_zones_layout(run)
    fig = draw_diagram(layout, report_data(run, lang))
    ax = fig.axes[0]
    renderer = fig.canvas.get_renderer()  # pyright: ignore[reportAttributeAccessIssue]
    texts = [x for x in fig.findobj(Text) if x.get_text().strip()]
    inside = {x.get_text().split("\n")[0]: x for x in texts if "\n" in x.get_text()}
    zones = {r.zone for r in layout.rects}
    assert len([x for x in texts if "  " in x.get_text()]) == len(zones)  # all in the legend
    assert inside and len(inside) < len(zones)  # some zones are big enough, others are not
    for zone in zones:
        name = t(f"zone.{zone}", lang)  # pyright: ignore[reportArgumentType]
        rect = max((r for r in layout.rects if r.zone == zone), key=lambda r: r.area)
        corners = [(rect.x, rect.y), (rect.x + rect.w, rect.y + rect.h)]
        (x0, y0), (x1, y1) = ax.transData.transform(corners)
        y0, y1 = min(y0, y1), max(y0, y1)
        if name in inside:  # drawn: the measured text is within the rectangle
            box = inside[name].get_window_extent(renderer)
            assert x0 <= box.x0 and box.x1 <= x1 and y0 <= box.y0 and box.y1 <= y1, zone
        else:  # left to the legend: the same text would not have fitted
            m2 = fmt_number(sum(r.area for r in layout.rects if r.zone == zone), lang, 0)  # pyright: ignore[reportArgumentType]
            probe = ax.text(0, 0, f"{name}\n{m2} m²", fontsize=LEGIBLE_PX)
            box = probe.get_window_extent(renderer)
            probe.remove()
            assert box.width > 0.8 * (x1 - x0) or box.height > 0.8 * (y1 - y0), zone


# ---------------------------------------------------------- the canvas that measures the labels
@pytest.mark.parametrize("area_m2", [5e6, 3e7])  # 158 MB and 1.1 GB of canvas without the guard
def test_T9_6_the_canvas_that_measures_the_labels_is_bounded_whatever_the_building(
    run: RunOutput, area_m2: float
) -> None:
    """The drawing is a vector SVG, but its labels are measured on a raster canvas: a 50 km2
    building took 20,000 x 20,000 px of RGBA (1.5 GB). A public demo met it through ten different
    inputs (a utilisation of 1e-5, a growth rate of 9, a shift of seconds, ...)."""
    from whsizing.report.diagram import CANVAS_BUDGET_PX, draw_diagram

    layout = layout_blocks(zones_of(run, "S1"), area_m2, "S1")
    fig = draw_diagram(layout, report_data(run, "en"))
    width, height = fig.canvas.get_width_height()  # pyright: ignore[reportAttributeAccessIssue]
    assert 0 < width * height <= CANVAS_BUDGET_PX * 1.05


def test_T9_6_a_normal_diagram_keeps_matplotlibs_dpi_and_a_large_one_still_gets_its_svg(
    run: RunOutput, data: ReportData, tmp_path: Path
) -> None:
    import matplotlib

    from whsizing.report.diagram import draw_diagram

    normal = layout_blocks(zones_of(run, "S1"), run.results["S1"].area.building_m2, "S1")
    assert draw_diagram(normal, data).dpi == pytest.approx(matplotlib.rcParams["figure.dpi"])
    res = run.results["S1"]
    area = res.area.model_copy(update={"building_m2": 3e7})  # 30 km2: the largest plan drawn
    large = run.model_copy(
        update={"results": {**run.results, "S1": res.model_copy(update={"area": area})}}
    )
    svg = build_diagram(dataclasses.replace(data, run=large), "S1", tmp_path).read_text("utf-8")
    assert svg.startswith("<?xml") and sum(a for _, a in svg_pieces(svg)) > 0


@pytest.mark.parametrize("area_m2", [5e7, 1e8, 1e12, 1e18])
def test_T9_6_a_plan_too_large_to_draw_is_a_config_error_naming_the_scenario_not_a_crash(
    run: RunOutput, data: ReportData, tmp_path: Path, area_m2: float
) -> None:
    """Below 12 dpi FreeType cannot set a text size (`invalid ppem value`) and above 65,536 px a
    side matplotlib refuses the canvas: raw RuntimeError and ValueError, found with a utilisation
    of 1e-7. Nothing is allocated: the error comes before the canvas."""
    from whsizing.report.diagram import draw_diagram

    layout = layout_blocks(zones_of(run, "S1"), area_m2, "S1")
    with pytest.raises(
        ConfigError, match=r"block diagram of S1: the plan is too large to draw"
    ) as e:
        draw_diagram(layout, data)
    assert e.value.exit_code == 2 and "design basis" in str(e.value)
    res = run.results["S1"]
    area = res.area.model_copy(update={"building_m2": area_m2})
    huge = run.model_copy(
        update={"results": {**run.results, "S1": res.model_copy(update={"area": area})}}
    )
    with pytest.raises(ConfigError, match="too large to draw"):
        build_diagram(dataclasses.replace(data, run=huge), "S1", tmp_path)
    assert list(tmp_path.iterdir()) == []  # no half-written file


@pytest.mark.parametrize("area_m2", [5e5, 5e6, 3e7])  # the canvas exceeds the budget from 3e5
def test_T9_6_the_dpi_of_the_measuring_canvas_follows_the_budget_and_stays_legible(
    area_m2: float,
) -> None:
    """Pure arithmetic: the dpi that keeps the canvas within the budget, never below the one at
    which FreeType sets the smallest label, and matplotlib's own for a normal plan."""
    import math

    import matplotlib

    from whsizing.report.diagram import (
        CANVAS_BUDGET_PX,
        MIN_CANVAS_DPI,
        PT_PER_INCH,
        PX_PER_M,
        _canvas_dpi,  # pyright: ignore[reportPrivateUsage]
    )

    layout = layout_blocks({"storage": 10.0}, area_m2, "S1")
    side_px = math.sqrt(area_m2) * PX_PER_M + 300  # the margins and the legend column
    dpi = _canvas_dpi(layout, side_px, side_px)
    assert dpi is not None and MIN_CANVAS_DPI <= dpi < float(matplotlib.rcParams["figure.dpi"])
    assert (side_px / PT_PER_INCH * dpi) ** 2 <= CANVAS_BUDGET_PX * 1.0001
    assert _canvas_dpi(layout, 560.0, 400.0) is None  # a normal diagram: matplotlib's dpi
