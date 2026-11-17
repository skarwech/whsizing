"""F3 step 10: the eight profile charts, PNG (matplotlib, report) and HTML (plotly, UI)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
import polars as pl
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from whsizing.schemas import DemandProfile

if TYPE_CHECKING:
    from whsizing.profile.build import ProfileTables

SERIES, ACCENT, MUTED = "#2a78d6", "#eb6834", "#52514e"  # dataviz reference palette slots 1, 2
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
COVER_CAP_DAYS = 365  # display only: longer covers fall in the last bin
SCATTER_MAX_POINTS = 5000  # display only: deterministic sample of orders
DPI = 150

Charts = tuple[Figure, go.Figure]


def _figs(title: str, x: str, y: str) -> tuple[Figure, Axes, go.Figure]:
    fig = Figure(figsize=(8, 4), layout="constrained")
    ax = fig.add_subplot()
    ax.set_title(title, loc="left")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.grid(axis="y", color="#e5e5e2", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    pfig = go.Figure(layout={"title": title, "template": "simple_white"})
    pfig.update_xaxes(title=x)
    pfig.update_yaxes(title=y)
    return fig, ax, pfig


def daily_lines(p: DemandProfile, t: ProfileTables) -> Charts:
    fig, ax, pfig = _figs("Daily lines with P50 and P95 (operating days)", "Date", "Lines / day")
    d = t.daily.filter(
        "is_operating"
    )  # the stats are on operating days; Sundays would read as dips
    ax.plot(d["date"].to_numpy(), d["lines"].to_numpy(), color=SERIES, linewidth=1.2, label="lines")
    pfig.add_scatter(x=d["date"].to_list(), y=d["lines"].to_list(), name="lines", line_color=SERIES)
    for name, v, c in (("P50", p.daily["lines"].p50, MUTED), ("P95", p.daily["lines"].p95, ACCENT)):
        ax.axhline(v, color=c, linestyle="--", linewidth=1.2, label=f"{name} = {v:,.0f}")
        pfig.add_hline(y=v, line_dash="dash", line_color=c, annotation_text=f"{name} = {v:,.0f}")
    ax.legend(frameon=False)
    return fig, pfig


def _index_bars(title: str, labels: tuple[str, ...], values: list[float | None], x: str) -> Charts:
    fig, ax, pfig = _figs(title, x, "Index (1 = mean day)")
    ys = [np.nan if v is None else v for v in values]
    ax.bar(labels, ys, color=SERIES, width=0.6)
    ax.axhline(1.0, color=MUTED, linestyle="--", linewidth=1)
    pfig.add_bar(x=list(labels), y=values, marker_color=SERIES, name="index")
    pfig.add_hline(y=1.0, line_dash="dash", line_color=MUTED)
    return fig, pfig


def monthly_index(p: DemandProfile, t: ProfileTables) -> Charts:
    return _index_bars("Monthly index of daily lines", MONTHS, p.seasonality.monthly_index, "Month")


def weekday_index(p: DemandProfile, t: ProfileTables) -> Charts:
    vals: list[float | None] = list(p.seasonality.weekday_index)
    return _index_bars("Weekday index of daily lines", WEEKDAYS, vals, "Weekday")


def intraday_heatmap(p: DemandProfile, t: ProfileTables) -> Charts:
    title = f"Share of lines per hour and weekday (confidence {p.intraday_confidence})"
    fig, ax, pfig = _figs(title, "Hour", "Weekday")
    days = sorted(p.intraday)
    z = np.array([p.intraday[d] for d in days])
    im = ax.imshow(z, aspect="auto", cmap="Blues", interpolation="nearest")
    ax.set_yticks(range(len(days)), [WEEKDAYS[d] for d in days])
    ax.set_xticks(range(0, 24, 2))
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="Share of the weekday's lines")
    labels = [WEEKDAYS[d] for d in days]
    pfig.add_heatmap(z=z.tolist(), x=list(range(24)), y=labels, colorscale="Blues")
    return fig, pfig


def lines_per_order_hist(p: DemandProfile, t: ProfileTables) -> Charts:
    fig, ax, pfig = _figs("Lines per order", "Lines in the order", "Share of orders")
    vc = t.orders["n_lines"].value_counts().sort("n_lines")
    share = (vc["count"] / t.orders.height).to_list()
    ax.bar(vc["n_lines"].to_list(), share, color=SERIES, width=0.8)
    pfig.add_bar(x=vc["n_lines"].to_list(), y=share, marker_color=SERIES, name="orders")
    return fig, pfig


def pareto(p: DemandProfile, t: ProfileTables) -> Charts:
    fig, ax, pfig = _figs("Pareto of lines by SKU", "Share of SKUs", "Cumulative share of lines")
    n = len(p.abc.pareto_lines)
    x, y = (np.arange(n + 1) / n).tolist(), [0.0, *p.abc.pareto_lines]  # curve starts at (0, 0)
    ax.plot(x, y, color=SERIES, linewidth=2)
    ax.set_ylim(0, 1.02)
    pfig.add_scatter(x=x, y=y, line_color=SERIES, name="lines")
    for thr in p.abc.thresholds:
        ax.axhline(thr, color=MUTED, linestyle="--", linewidth=1)
        pfig.add_hline(y=thr, line_dash="dash", line_color=MUTED, annotation_text=f"{thr:.0%}")
    return fig, pfig


def stock_cover_hist(p: DemandProfile, t: ProfileTables) -> Charts:
    title = f"Stock cover per SKU (days; last bin ≥ {COVER_CAP_DAYS})"
    fig, ax, pfig = _figs(title, "Cover (days)", "SKUs")
    s = t.skus.filter((pl.col("avg_stock") > 0) & (pl.col("units") > 0))
    cover = (s["avg_stock"] / (s["units"] / max(p.operating_days, 1))).to_numpy()
    cover = np.minimum(cover, COVER_CAP_DAYS)
    ax.hist(cover, bins=40, color=SERIES, edgecolor="white")
    pfig.add_histogram(x=cover.tolist(), nbinsx=40, marker_color=SERIES, name="SKUs")
    return fig, pfig


def cube_weight_scatter(p: DemandProfile, t: ProfileTables) -> Charts:
    fig, ax, pfig = _figs("Order cube vs weight (sample)", "Weight (kg)", "Cube (m³)")
    o = t.orders.filter((pl.col("weight_kg") > 0) & (pl.col("cube_m3") > 0)).sort("order_id")
    o = o.sample(min(o.height, SCATTER_MAX_POINTS), seed=0)
    for name, flag, c in (("parcel orders", False, SERIES), ("pallet orders", True, ACCENT)):
        g = o.filter(pl.col("is_pallet") == flag)
        if g.is_empty():
            continue
        ax.scatter(g["weight_kg"], g["cube_m3"], s=8, color=c, alpha=0.6, label=name)
        pfig.add_scattergl(
            x=g["weight_kg"].to_list(), y=g["cube_m3"].to_list(), mode="markers",
            marker={"color": c, "size": 5}, name=name,
        )  # fmt: skip
    ax.set_xscale("log")
    ax.set_yscale("log")
    if ax.get_legend_handles_labels()[0]:  # no order with weight and cube (no dims): no legend
        ax.legend(frameon=False)
    pfig.update_xaxes(type="log")
    pfig.update_yaxes(type="log")
    return fig, pfig


CHARTS: dict[str, Callable[[DemandProfile, ProfileTables], Charts]] = {
    "daily_lines": daily_lines,
    "monthly_index": monthly_index,
    "weekday_index": weekday_index,
    "intraday_heatmap": intraday_heatmap,
    "lines_per_order_hist": lines_per_order_hist,
    "pareto": pareto,
    "stock_cover_hist": stock_cover_hist,
    "cube_weight_scatter": cube_weight_scatter,
}


def write_charts(p: DemandProfile, t: ProfileTables, out_dir: Path) -> list[Path]:
    """<name>.png (report) and <name>.html (UI; one shared plotly.min.js, no CDN)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, draw in CHARTS.items():
        fig, pfig = draw(p, t)
        png, html = out_dir / f"{name}.png", out_dir / f"{name}.html"
        fig.savefig(png, dpi=DPI)
        pfig.write_html(html, include_plotlyjs="directory")
        paths += [png, html]
    return paths
