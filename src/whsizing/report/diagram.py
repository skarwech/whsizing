"""F9a block diagram of a scenario's area budget (spec F9, `report/diagram_<scenario>.svg`).

Algorithm (spec): zones sorted by area descending; storage placed first as a rectangle spanning
the building width, height = area / width; the other zones packed in rows (strip packing) under
it; receiving and shipping along the dock wall (the south wall), at any utilisation: a squarish
block when there is room, else a full-width strip, and when the total exceeds the building area
the strips that no longer fit go below the dock strip; scale 1 m = 2 px; labels with name and m2;
the part beyond the envelope is drawn hatched outside it and the deficit printed. Typical-world
areas (`ScenarioResult.area.zones`). The scale is the spec's, the type is not: 1 m = 2 px makes
most zones too small for a label, so the legend column (colour chip, name, m2) names every zone at
9 px (7 pt on the A4 page, where the 560 px drawing is set about 0.8 pt per px) and a label is
drawn inside a zone's largest rectangle only when its measured text fits in it.

Geometry is `layout_blocks` (pure, metres); `build_diagram` draws it with matplotlib (SVG). Every
zone is cut into rectangles whose areas add up to the zone's area exactly (a rectangle crossing
the envelope is cut in two), so the drawn area equals the zone sum (T9.6): the SVG keeps one
`<g id="zone-<name>-<n>">` per rectangle for a check on the file itself.

ponytail: `Building` has no width, so the envelope is a square of side sqrt(area); pass `width_m`
for another one. Each strip takes whole zones until it is 6 m deep, its zones sharing the width
in proportion to their areas (no wasted floor, so overflow appears only when total > building).
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from matplotlib import rc_context, rcParams
from matplotlib.axes import Axes
from matplotlib.backend_bases import RendererBase
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text

from whsizing.errors import ConfigError, WhsizingError
from whsizing.report.data import ReportData
from whsizing.report.i18n import Lang, fmt_number, t
from whsizing.report.style import ALERT, INK, MUTED, fonts
from whsizing.schemas import AreaResult

PX_PER_M = 2.0  # spec: scale 1 m = 2 px
PT_PER_INCH = 72.0  # matplotlib sizes the SVG in points; `build_diagram` relabels them px
MIN_STRIP_M = 6.0
DOCK_ZONES = ("receiving_staging", "shipping_staging")
MARGIN_PX = (12.0, 210.0, 34.0, 62.0)  # left, right (legend column), top, bottom
MIN_WIDTH_PX = 560.0  # the caption and the source note need this much room
LEGEND_TOP_M = 4.0  # the legend: the first row's centre below the envelope's north wall ...
LEGEND_ROW_M = 6.5  # ... and the pitch of its rows (13 px)
LABEL_PX = 90.0  # room the "Building N m2" and "Deficit" labels need left of a narrow envelope
LEGEND_FONT_PX = 9.0  # sizes in px, as the SVG is read (see `build_diagram`)
LABEL_FONT_PX = 8.0  # in a zone, "Building N m2", "Deficit"
TITLE_FONT_PX = 9.0
NOTE_FONT_PX = 6.5  # caption and source note (the source note is 130 characters or more)
FIT = 0.92  # a label is drawn in a zone when its text fills at most this share of it
CANVAS_BUDGET_PX = 4_000_000  # [P] pixels of the canvas that measures the labels (16 MB of RGBA)
MIN_CANVAS_DPI = 12.0  # FreeType cannot set a text size below one pixel: 6.5 pt at 12 dpi is 1.1
SVG_SIZE = re.compile(r'(<svg [^>]*?width="[\d.]+)pt(" height="[\d.]+)pt"')
ZONE_COLOURS = (
    "#cfe0f3",
    "#d9ead3",
    "#fce8c8",
    "#e6d9ef",
    "#d6ecec",
    "#f3d9d9",
    "#e8e8e3",
    "#dfe7c4",
    "#f1e1c9",
)


@dataclass(frozen=True)
class Rect:
    """One rectangle of the plan, metres, origin top-left of the envelope, y downwards."""

    zone: str
    x: float
    y: float
    w: float
    h: float
    overflow: bool = False  # lies below the building envelope

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(frozen=True)
class Layout:
    scenario_id: str
    width_m: float
    height_m: float  # of the building envelope
    building_m2: float
    total_m2: float
    rects: tuple[Rect, ...]

    @property
    def deficit_m2(self) -> float:
        return max(0.0, self.total_m2 - self.building_m2)

    @property
    def drawn_m2(self) -> float:
        return sum(r.area for r in self.rects)


def layout_blocks(
    zones: Mapping[str, float],
    building_m2: float,
    scenario_id: str = "",
    width_m: float | None = None,
) -> Layout:
    """Place `zones` (name → m2) in a building of `building_m2` (width `width_m`, default
    sqrt(area)); see the module docstring."""
    if building_m2 <= 0:
        raise ConfigError(
            f"block diagram of {scenario_id or 'a scenario'}: the building area is {building_m2} m2"
        )
    width = width_m or math.sqrt(building_m2)
    height = building_m2 / width
    pos = {z: a for z, a in zones.items() if a > 0}
    ordered = sorted(pos, key=lambda z: (-pos[z], z))  # area descending, name breaks ties
    storage = [z for z in ordered if z == "storage"]
    dock = [z for z in ordered if z in DOCK_ZONES]
    middle = [z for z in ordered if z not in {"storage", *DOCK_ZONES}]
    pieces, y = _pack(storage, middle, pos, width)
    dock_m2 = sum(pos[z] for z in dock)
    if dock and dock_m2 < building_m2:  # the dock wall fits in the envelope: always use it
        dock_h = max(math.sqrt(max(pos[z] for z in dock)), dock_m2 / width)
        if y + dock_h > height:  # no room for a squarish block: a full-width strip, no floor wasted
            dock_h = dock_m2 / width
        wall = height - dock_h
        pieces = _below_the_wall(pieces, wall, height)
        pieces += _dock_rects(dock, pos, width, wall, dock_h)
    elif dock:  # the docks alone fill the building: they join the strips
        pieces, _ = _pack(storage, [z for z in ordered if z != "storage"], pos, width)
    return Layout(
        scenario_id,
        width,
        height,
        building_m2,
        sum(pos.values()),
        tuple(_cut_at(pieces, height)),
    )


def _below_the_wall(pieces: list[Rect], wall: float, height: float) -> list[Rect]:
    """The strips packed from the north wall, cut at `wall` (the top of the dock strip): what lies
    below it moves under the dock strip, i.e. below the south wall (`height`), as overflow."""
    out: list[Rect] = []
    for r in pieces:
        if r.y + r.h <= wall + 1e-9:
            out.append(r)
        elif r.y >= wall:
            out.append(Rect(r.zone, r.x, height + (r.y - wall), r.w, r.h))
        else:  # crosses the wall: the upper part stays, the lower part goes below the south wall
            inside = wall - r.y
            out.append(Rect(r.zone, r.x, r.y, r.w, inside))
            out.append(Rect(r.zone, r.x, height, r.w, r.h - inside))
    return out


def _pack(
    storage: list[str], others: list[str], area: Mapping[str, float], width: float
) -> tuple[list[Rect], float]:
    """The storage strip, then `others` in strips; returns the rectangles and the depth used."""
    pieces: list[Rect] = []
    y = 0.0
    for strip in [storage, *_strips(others, area, width)]:
        if strip:
            pieces += _strip_rects(strip, area, width, y)
            y = pieces[-1].y + pieces[-1].h
    return pieces, y


def _strips(zones: list[str], area: Mapping[str, float], width: float) -> list[list[str]]:
    """Group zones (already by area descending) into strips at least MIN_STRIP_M deep."""
    strips: list[list[str]] = [[]]
    for z in zones:
        strips[-1].append(z)
        if sum(area[k] for k in strips[-1]) / width >= MIN_STRIP_M:
            strips.append([])
    return [s for s in strips if s]


def _strip_rects(zones: list[str], area: Mapping[str, float], width: float, y: float) -> list[Rect]:
    """A full-width strip: depth = Σ area / width, each zone as wide as its share of the area."""
    depth = sum(area[z] for z in zones) / width
    out: list[Rect] = []
    x = 0.0
    for z in zones:
        w = area[z] / depth
        out.append(Rect(z, x, y, w, depth))
        x += w
    return out


def _dock_rects(
    zones: list[str], area: Mapping[str, float], width: float, y: float, h: float
) -> list[Rect]:
    """Receiving at the west corner, shipping at the east corner of the dock wall."""
    out: list[Rect] = []
    for z in zones:
        w = area[z] / h
        out.append(Rect(z, 0.0 if z == "receiving_staging" else width - w, y, w, h))
    return out


def _cut_at(pieces: list[Rect], height: float) -> list[Rect]:
    """Cut every rectangle crossing the south wall (y = height) in two; the part below it is the
    overflow."""
    out: list[Rect] = []
    for r in pieces:
        if r.y >= height:
            out.append(Rect(r.zone, r.x, r.y, r.w, r.h, overflow=True))
        elif r.y + r.h > height + 1e-9:
            inside = height - r.y
            out.append(Rect(r.zone, r.x, r.y, r.w, inside))
            out.append(Rect(r.zone, r.x, height, r.w, r.h - inside, overflow=True))
        else:
            out.append(r)
    return out


def build_diagram(data: ReportData, scenario_id: str, out_dir: Path) -> Path:
    """Write `<out_dir>/diagram_<scenario>.svg` for a computed scenario; returns the path."""
    area: AreaResult = data.run.results[scenario_id].area
    zones = {z: r.typ for z, r in area.zones.items()}
    layout = layout_blocks(zones, area.building_m2, scenario_id)
    out = Path(out_dir) / f"diagram_{scenario_id}.svg"
    fig = draw_diagram(layout, data)
    svg = io.StringIO()
    with rc_context({"svg.fonttype": "none", "svg.hashsalt": "whsizing"}):
        fig.savefig(svg, format="svg", metadata={"Date": None, "Creator": "whsizing"})
    # matplotlib sizes in pt; the viewBox is in user units (fonts too): read as px, 1 m = 2 px
    sized = SVG_SIZE.sub(r'\1px\2px"', svg.getvalue(), count=1)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sized, encoding="utf-8")
    except OSError as e:
        raise WhsizingError(f"report: cannot write {out} ({e.strerror})") from e
    return out


def _canvas_dpi(layout: Layout, w_px: float, h_px: float) -> float | None:
    """`None` (matplotlib's own dpi) unless the canvas that only measures the labels would need
    more than `CANVAS_BUDGET_PX` pixels: the plan of a 50 km2 building takes 20,000 x 20,000 px,
    1.5 GB of RGBA, for a drawing that is a vector SVG (inputs that blow the plan up: a
    utilisation of 1e-5, a growth rate of 9, a shift of a few seconds). Then the dpi that fits the
    budget: the labels are measured coarser, in a plan nobody reads at that scale. Below
    `MIN_CANVAS_DPI` (a plan of about 30 km2) no text can be measured: a `ConfigError`, the plan
    is no warehouse's and the design basis is to be checked."""
    dpi = float(rcParams["figure.dpi"])
    pixels = (w_px / PT_PER_INCH * dpi) * (h_px / PT_PER_INCH * dpi)
    if pixels <= CANVAS_BUDGET_PX:
        return None
    fitted = dpi * math.sqrt(CANVAS_BUDGET_PX / pixels)
    if not fitted >= MIN_CANVAS_DPI:  # written so that a NaN (a non-finite plan) is refused too
        width_m, height_m = (w_px - sum(MARGIN_PX[:2])) / PX_PER_M, h_px / PX_PER_M
        raise ConfigError(
            f"block diagram of {layout.scenario_id or 'a scenario'}: the plan is too large to "
            f"draw ({width_m:,.0f} x {height_m:,.0f} m); check the design basis (an area, a "
            "utilisation or a growth rate far outside the usual range)"
        )
    return fitted


def draw_diagram(layout: Layout, data: ReportData) -> Figure:
    lang = data.lang
    below = max((r.y + r.h for r in layout.rects), default=layout.height_m)
    legend_m = LEGEND_TOP_M + len(_zone_order(layout)) * LEGEND_ROW_M - LEGEND_ROW_M / 2
    height_m = max(layout.height_m, below, legend_m)  # a short envelope: the legend sets the height
    left, right, top, bottom = MARGIN_PX
    left = max(left, LABEL_PX - layout.width_m * PX_PER_M)  # a narrow envelope: labels stay inside
    w_px = max(MIN_WIDTH_PX, left + layout.width_m * PX_PER_M + right)
    h_px = top + height_m * PX_PER_M + bottom
    with rc_context({"font.family": fonts()}):
        fig = Figure(
            figsize=(w_px / PT_PER_INCH, h_px / PT_PER_INCH), dpi=_canvas_dpi(layout, w_px, h_px)
        )
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes(
            (
                left / w_px,
                bottom / h_px,
                layout.width_m * PX_PER_M / w_px,
                height_m * PX_PER_M / h_px,
            )
        )
        ax.set_xlim(0, layout.width_m)
        ax.set_ylim(height_m, 0)
        ax.axis("off")
        ax.add_patch(Rectangle((0, 0), layout.width_m, layout.height_m, fill=False, ec=INK, lw=1))
        colours = {
            z: ZONE_COLOURS[i % len(ZONE_COLOURS)] for i, z in enumerate(_zone_order(layout))
        }
        for i, r in enumerate(layout.rects):
            _draw_rect(ax, r, colours[r.zone], f"zone-{r.zone}-{i}")
        _labels(ax, canvas.get_renderer(), layout, lang, colours)
        title = t("diagram.title", lang, scenario=layout.scenario_id)
        fig.text(
            left / w_px, 1 - 14 / h_px, title, fontsize=TITLE_FONT_PX, fontweight="bold", color=INK
        )
        caption = t("diagram.caption", lang)
        fig.text(MARGIN_PX[0] / w_px, 22 / h_px, caption, fontsize=NOTE_FONT_PX, color=MUTED)
        src = t("chart.source", lang, note=data.source_note)
        fig.text(MARGIN_PX[0] / w_px, 10 / h_px, src, fontsize=NOTE_FONT_PX, color=MUTED)
    return fig


def _zone_order(layout: Layout) -> list[str]:
    return list(dict.fromkeys(r.zone for r in layout.rects))


def _draw_rect(ax: Axes, r: Rect, colour: str, gid: str) -> None:
    patch = Rectangle(
        (r.x, r.y),
        r.w,
        r.h,
        facecolor="none" if r.overflow else colour,
        edgecolor=ALERT if r.overflow else INK,
        hatch="////" if r.overflow else None,
        linewidth=0.5,
        gid=gid,
    )
    ax.add_patch(patch)


def _labels(
    ax: Axes, renderer: RendererBase, layout: Layout, lang: Lang, colours: dict[str, str]
) -> None:
    """Name and m2 of each zone: a legend (colour chip, name, m2) in the right-hand column, and
    the same text inside the zone's largest rectangle when it fits."""
    totals: dict[str, float] = {}
    main: dict[str, Rect] = {}
    for r in layout.rects:
        totals[r.zone] = totals.get(r.zone, 0.0) + r.area
        if r.zone not in main or r.area > main[r.zone].area:
            main[r.zone] = r
    x0 = layout.width_m + 6 / PX_PER_M
    for row, zone in enumerate(sorted(totals, key=lambda z: (-totals[z], z))):
        name = t(f"zone.{zone}", lang)
        m2 = f"{fmt_number(totals[zone], lang, 0)} m²"
        y = LEGEND_TOP_M + row * LEGEND_ROW_M
        ax.add_patch(
            Rectangle((x0, y - 1.5), 3, 3, fc=colours[zone], ec=INK, lw=0.4, clip_on=False)
        )
        ax.text(
            x0 + 5,
            y,
            f"{name}  {m2}",
            ha="left",
            va="center",
            fontsize=LEGEND_FONT_PX,
            clip_on=False,
        )
        r = main[zone]
        label = ax.text(
            r.x + r.w / 2,
            r.y + r.h / 2,
            f"{name}\n{m2}",
            ha="center",
            va="center",
            fontsize=LABEL_FONT_PX,
        )
        if not _fits(label, r, ax, renderer):  # too small for it: the legend names the zone
            label.remove()
    envelope = t("diagram.building", lang, m2=fmt_number(layout.building_m2, lang, 0))
    ax.text(
        layout.width_m, -3, envelope, ha="right", va="bottom", fontsize=LABEL_FONT_PX, color=MUTED
    )
    if layout.deficit_m2 > 0:
        msg = t("diagram.deficit", lang, m2=fmt_number(layout.deficit_m2, lang, 0))
        y = max(r.y + r.h for r in layout.rects)
        ax.text(
            layout.width_m / 2,
            y + 4,
            msg,
            ha="center",
            va="top",
            fontsize=LABEL_FONT_PX,
            color=ALERT,
        )


def _fits(label: Text, r: Rect, ax: Axes, renderer: RendererBase) -> bool:
    """Does the label's text, as measured, fit in the rectangle (with a margin: the viewer's font
    is not the one measured)?"""
    box = label.get_window_extent(renderer)
    (x0, y0), (x1, y1) = ax.transData.transform([(r.x, r.y), (r.x + r.w, r.y + r.h)])
    return bool(box.width <= FIT * abs(x1 - x0) and box.height <= FIT * abs(y1 - y0))


def build_diagrams(data: ReportData, out_dir: Path) -> dict[str, Path]:
    """`build_diagram` for every computed scenario: {scenario id: svg path}."""
    return {sid: build_diagram(data, sid, out_dir) for sid in data.computed()}
