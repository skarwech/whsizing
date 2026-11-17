"""F9a static charts: PNG (matplotlib Agg, no pyplot state), labels from i18n.

    charts = build_charts(data, out_dir)      # {chart id: Path}; `chart_<id>_<lang>.png`
    png = chart_png(data, "tco")              # bytes of one chart, or None without data

Chart ids (`CHART_IDS`): daily, seasonality, pareto, split, hourly (demand and design day), fte
(stacked heads by activity), tco (bars with lo / hi whiskers), cash (cumulative cash flow),
tornado, sweep (the last two only with a sensitivity analysis). The tornado stacks one panel per
scenario on a shared x axis and its figure grows with the scenarios (`tornado_height_in`); the
others are `SIZE_IN`. Each image carries its title, a
caption (`chart.<id>.caption`) and the source note "engine v, catalog v, run id". A scenario has
the same colour in every chart (`style.scenario_colours`). The numbers come from the run's results
and JSON files; the cash-flow chart draws the cash_flow table's cumulative columns, and its
caption says Δ (`chart.cash.caption`) only when a Δ column is drawn, else `chart.cash.caption_own`.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import numpy as np
from matplotlib import rc_context
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MaxNLocator

from whsizing.errors import ReportIntegrityError, WhsizingError
from whsizing.report.data import ReportData
from whsizing.report.i18n import Lang, fmt_number, t
from whsizing.report.style import (
    ACTIVITY_PALETTE,
    GRID,
    INK,
    MUTED,
    NEUTRAL,
    NEUTRAL_LIGHT,
    fonts,
    scenario_colours,
)

DPI = 150
SIZE_IN = (7.2, 3.8)
FOOT_IN = 0.30  # room under the plots for the caption and the source note
CAPTION_IN, SOURCE_IN = 0.17, 0.045  # their baselines above the bottom edge
# the tornado: a bar and its row, the gap between two panels (the next scenario's title is in it),
# the title above the first panel and the x axis below the last (measured under constrained layout)
BAR_IN, PANEL_GAP_IN, TORNADO_TOP_IN, TORNADO_AXIS_IN = 0.125, 0.245, 0.38, 0.4
CHART_IDS = (
    "daily",
    "seasonality",
    "pareto",
    "split",
    "hourly",
    "fte",
    "tco",
    "cash",
    "tornado",
    "sweep",
)
MONTH_KEYS = [f"month.{m}" for m in range(1, 13)]


def build_charts(data: ReportData, out_dir: Path) -> dict[str, Path]:
    """Write every chart that has data to `<out_dir>/chart_<id>_<lang>.png`."""
    out = Path(out_dir)
    written: dict[str, Path] = {}
    try:
        out.mkdir(parents=True, exist_ok=True)
        for chart_id in CHART_IDS:
            png = chart_png(data, chart_id)
            if png is not None:
                written[chart_id] = out / f"chart_{chart_id}_{data.lang}.png"
                written[chart_id].write_bytes(png)
    except OSError as e:
        raise WhsizingError(f"report: cannot write the charts to {out} ({e.strerror})") from e
    return written


def chart_png(data: ReportData, chart_id: str) -> bytes | None:
    """The PNG of one chart, None when the run has no data for it (no sensitivity analysis)."""
    fig = chart_figure(data, chart_id)
    if fig is None:
        return None
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, metadata={"Software": "whsizing"})
    return buf.getvalue()


def chart_figure(data: ReportData, chart_id: str) -> Figure | None:
    draw = _DRAWERS[chart_id]
    lang = data.lang
    with rc_context({"font.family": fonts(), "axes.unicode_minus": False}):
        fig = Figure(figsize=SIZE_IN, layout="constrained")
        FigureCanvasAgg(fig)
        if not draw(fig, data):  # a drawer may set its own height (the tornado)
            return None
        height = fig.get_size_inches()[1]
        fig.suptitle(
            t(f"chart.{chart_id}.title", lang),
            x=0.01,
            ha="left",
            fontsize=10,
            fontweight="bold",
            color=INK,
        )
        fig.get_layout_engine().set(rect=(0, FOOT_IN / height, 1, 1 - FOOT_IN / height))  # type: ignore[union-attr]
        caption = t(_caption_key(data, chart_id), lang)
        fig.text(0.01, CAPTION_IN / height, caption, fontsize=7, color=MUTED)
        source = t("chart.source", lang, note=data.source_note)
        fig.text(0.01, SOURCE_IN / height, source, fontsize=6, color=MUTED)
    return fig


def _caption_key(data: ReportData, chart_id: str) -> str:
    """`chart.<id>.caption`; the cash-flow chart says Δ only when a Δ column is drawn (a lone
    baseline scenario, or no baseline, draws each scenario's own cumulative flow)."""
    if chart_id == "cash":
        cols = data.tables["cash_flow"].blocks[0].columns
        if not any(c.kind == "delta" and not c.disabled_reason for c in cols):
            return "chart.cash.caption_own"
    return f"chart.{chart_id}.caption"


Grid = Literal["x", "y", "both"]


def _axes(fig: Figure, x: str, y: str, lang: Lang, *, grid: Grid = "y") -> Axes:
    ax = fig.add_subplot()
    ax.set_xlabel(t(x, lang), fontsize=8)
    ax.set_ylabel(t(y, lang), fontsize=8)
    return _style(ax, grid)


def _style(ax: Axes, grid: Grid = "y") -> Axes:
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return ax


def _thousands(ax: Axes, lang: Lang, axis: str = "y", decimals: int = 0) -> None:
    fmt = FuncFormatter(lambda v, _: fmt_number(v, lang, decimals))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def _daily(fig: Figure, data: ReportData) -> bool:
    lang, p = data.lang, data.profile
    d = data.daily.filter("is_operating")  # the stats are on operating days
    ax = _axes(fig, "chart.axis.date", "chart.axis.lines_day", lang)
    ax.plot(d["date"].to_numpy(), d["lines"].to_numpy(), color=NEUTRAL, linewidth=0.9)
    design = data.design_day.percentile_values.get("lines", p.daily["lines"].p95)
    pct = fmt_number(data.design_day.percentile, lang, 0)
    for label, value, colour in (
        (t("chart.series.p50", lang), p.daily["lines"].p50, MUTED),
        (t("chart.series.design", lang, p=pct), design, INK),
    ):
        ax.axhline(
            value,
            color=colour,
            linestyle="--",
            linewidth=1.1,
            label=f"{label} = {fmt_number(value, lang, 0)}",
        )
    ax.legend(frameon=False, fontsize=7)
    _thousands(ax, lang)
    return True


def _seasonality(fig: Figure, data: ReportData) -> bool:
    lang, s = data.lang, data.profile.seasonality
    left, right = fig.subplots(1, 2, gridspec_kw={"width_ratios": [12, 7]})
    months = [t(k, lang)[:3] for k in MONTH_KEYS]
    weekdays = [t(f"weekday.{d}", lang)[:3] for d in range(7)]
    for ax, labels, values, name in (
        (left, months, s.monthly_index, "chart.series.monthly"),
        (right, weekdays, s.weekday_index, "chart.series.weekday"),
    ):
        _style(ax)
        ys = [np.nan if v is None else v for v in values]
        ax.bar(labels, ys, color=NEUTRAL, width=0.65)
        ax.axhline(1.0, color=MUTED, linestyle="--", linewidth=1)
        ax.set_xlabel(t(name, lang), fontsize=8)
    left.set_ylabel(t("chart.axis.index", lang), fontsize=8)
    _thousands(left, lang, decimals=1)
    _thousands(right, lang, decimals=1)
    return True


def _pareto(fig: Figure, data: ReportData) -> bool:
    lang, abc = data.lang, data.profile.abc
    ax = _axes(fig, "chart.axis.sku_share", "chart.axis.line_share", lang, grid="both")
    n = len(abc.pareto_lines)
    x = np.arange(n + 1) / n
    ax.plot(x, [0.0, *abc.pareto_lines], color=NEUTRAL, linewidth=2)
    for limit in abc.thresholds:
        pct = fmt_number(limit * 100, lang, 0)
        ax.axhline(
            limit,
            color=MUTED,
            linestyle="--",
            linewidth=1,
            label=t("chart.series.abc_limit", lang, p=pct),
        )
    ax.set_ylim(0, 1.02)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    _thousands(ax, lang, "x", 1)
    _thousands(ax, lang, "y", 1)
    return True


def _split(fig: Figure, data: ReportData) -> bool:
    lang, sp = data.lang, data.profile.shipment_split
    ax = _axes(fig, "chart.axis.share", "chart.axis.share", lang, grid="x")
    ax.set_ylabel("")
    rows = (
        (t("chart.series.orders", lang), sp.parcel_share_orders, sp.pallet_share_orders),
        (t("chart.series.lines", lang), sp.parcel_share_lines, sp.pallet_share_lines),
    )
    for i, (_, parcel, pallet) in enumerate(rows):
        ax.barh(
            i,
            parcel,
            color=NEUTRAL,
            height=0.5,
            label=t("chart.series.parcel", lang) if i == 0 else None,
        )
        ax.barh(
            i,
            pallet,
            left=parcel,
            color=NEUTRAL_LIGHT,
            height=0.5,
            label=t("chart.series.pallet", lang) if i == 0 else None,
        )
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{fmt_number(v * 100, lang, 0)} %"))
    ax.legend(frameon=False, fontsize=7, ncols=2, loc="lower left", bbox_to_anchor=(0, 1.0))
    return True


def _hourly(fig: Figure, data: ReportData) -> bool:
    lang = data.lang
    ax = _axes(fig, "chart.axis.hour", "chart.axis.lines_hour", lang)
    ax.bar(range(24), data.design_day.hourly_lines, color=NEUTRAL, width=0.8)
    ax.set_xticks(range(0, 24, 2))
    _thousands(ax, lang)
    return True


def _fte(fig: Figure, data: ReportData) -> bool:
    lang, res = data.lang, data.run.results
    ids = data.computed()
    if not ids:
        return False
    ax = _axes(fig, "chart.axis.heads", "chart.axis.heads", lang)
    ax.set_xlabel("")
    activities = list(dict.fromkeys(a.activity for s in ids for a in res[s].labor.activities))
    bottom = np.zeros(len(ids))
    for i, activity in enumerate(activities):
        values = np.array(
            [
                next((a.heads.typ for a in res[s].labor.activities if a.activity == activity), 0.0)
                for s in ids
            ]
        )
        ax.bar(
            ids,
            values,
            bottom=bottom,
            width=0.6,
            label=t(f"activity.{activity}", lang),
            color=ACTIVITY_PALETTE[i % len(ACTIVITY_PALETTE)],
            edgecolor="white",
            linewidth=0.4,
        )
        bottom += values
    ax.legend(frameon=False, fontsize=6, loc="center left", bbox_to_anchor=(1.0, 0.5))
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    _thousands(ax, lang)
    return True


def _tco(fig: Figure, data: ReportData) -> bool:
    lang, fins = data.lang, data.run.finances
    ids = [s for s in data.computed() if s in fins]
    if not ids:
        return False
    colours = scenario_colours(data.run.results)
    ax = _axes(fig, "chart.axis.eur", "chart.axis.eur", lang)
    ax.set_xlabel("")
    typ = np.array([fins[s].tco.typ for s in ids])
    lo = typ - np.array([fins[s].tco.lo for s in ids])
    hi = np.array([fins[s].tco.hi for s in ids]) - typ
    ax.bar(
        ids,
        typ,
        yerr=[lo, hi],
        color=[colours[s] for s in ids],
        width=0.55,
        capsize=5,
        error_kw={"ecolor": INK, "elinewidth": 1},
    )
    _thousands(ax, lang)
    return True


def _cash(fig: Figure, data: ReportData) -> bool:
    lang = data.lang
    block = data.tables["cash_flow"].blocks[0]
    colours = scenario_colours(data.run.results)
    ax = _axes(fig, "chart.axis.year", "chart.axis.eur", lang, grid="both")
    drawn = 0
    for i, col in enumerate(block.columns):
        if col.kind != "cumulative" or col.disabled_reason or col.scenario_id is None:
            continue
        ys = [r.cells[i].value for r in block.rows]
        pts = [(y, float(v)) for y, v in enumerate(ys) if isinstance(v, int | float)]
        if pts:
            ax.plot(
                *zip(*pts, strict=True),
                marker="o",
                markersize=3,
                linewidth=1.6,
                color=colours[col.scenario_id],
                label=col.scenario_id,
            )
            drawn += 1
    if not drawn:
        return False
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.legend(frameon=False, fontsize=7)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _thousands(ax, lang)
    return True


def tornado_height_in(bars_per_scenario: list[int]) -> float:
    """Height of the tornado figure: a row per bar and a gap per scenario but the first, so that a
    bar is as thick with eight scenarios as with one, plus the title and the x axis."""
    rows = sum(bars_per_scenario) * BAR_IN + (len(bars_per_scenario) - 1) * PANEL_GAP_IN
    return TORNADO_TOP_IN + rows + TORNADO_AXIS_IN + FOOT_IN


def _tornado(fig: Figure, data: ReportData) -> bool:
    s = data.run.sensitivity
    if s is None or not s.tornado:
        return False
    lang = data.lang
    colours = scenario_colours(data.run.results)
    ids = [sid for sid in data.run.results if any(b.scenario_id == sid for b in s.tornado)]
    if not ids:  # sensitivity.py builds the bars from the run's own scenarios: edited by hand
        raise ReportIntegrityError(
            "tornado: no bar belongs to a scenario of the run "
            f"(bars: {sorted({b.scenario_id for b in s.tornado})}, run: {sorted(data.run.results)})"
        )
    bars = {
        sid: sorted((b for b in s.tornado if b.scenario_id == sid), key=lambda b: b.delta_tco)
        for sid in ids
    }
    counts = [len(bars[sid]) for sid in ids]
    fig.set_size_inches(SIZE_IN[0], tornado_height_in(counts))
    panels = fig.subplots(
        len(ids), 1, sharex=True, squeeze=False, gridspec_kw={"height_ratios": counts}
    )[:, 0]
    for ax, sid in zip(panels, ids, strict=True):
        _style(ax, "x")
        base = s.base_tco.get(sid, 0.0)
        y = np.arange(len(bars[sid]))
        low = np.array([b.tco_low - base for b in bars[sid]])
        high = np.array([b.tco_high - base for b in bars[sid]])
        ax.barh(y, low, color=colours[sid], alpha=0.45, height=0.7)
        ax.barh(y, high, color=colours[sid], height=0.7)
        ax.set_yticks(y, [t(f"sens.param.{b.param}", lang) for b in bars[sid]], fontsize=6)
        ax.axvline(0, color=INK, linewidth=0.8)
        ax.set_title(sid, fontsize=8, color=colours[sid], loc="left", pad=2)
    last = panels[-1]  # shared x axis: its labels and title are drawn under the last panel only
    last.set_xlabel(t("chart.axis.delta_tco", lang), fontsize=7)
    last.xaxis.set_major_locator(MaxNLocator(6))
    _thousands(last, lang, "x")
    return True


def _sweep(fig: Figure, data: ReportData) -> bool:
    s = data.run.sensitivity
    if s is None or not s.percentile_sweep:
        return False
    lang = data.lang
    colours = scenario_colours(data.run.results)
    ax = _axes(fig, "chart.axis.percentile", "chart.axis.eur", lang, grid="both")
    for sid in data.run.results:
        pts = sorted((p.percentile, p.tco) for p in s.percentile_sweep if p.scenario_id == sid)
        if pts:
            ax.plot(
                *zip(*pts, strict=True), marker="o", linewidth=1.6, color=colours[sid], label=sid
            )
    ax.legend(frameon=False, fontsize=7)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    _thousands(ax, lang, "x")
    _thousands(ax, lang)
    return True


_DRAWERS: dict[str, Callable[[Figure, ReportData], bool]] = {
    "daily": _daily,
    "seasonality": _seasonality,
    "pareto": _pareto,
    "split": _split,
    "hourly": _hourly,
    "fte": _fte,
    "tco": _tco,
    "cash": _cash,
    "tornado": _tornado,
    "sweep": _sweep,
}
