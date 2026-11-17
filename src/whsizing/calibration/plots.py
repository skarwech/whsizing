"""F11 step 7: plots (matplotlib, Agg backend), written to `<out>/plots/`.

    predicted_vs_actual.png   one panel per activity and the total: actual and predicted by month,
                              hold-out months shaded
    residuals_by_month.png    (predicted − actual) / actual in % by activity and month, hold-out
                              columns marked
    multipliers.png           fitted multipliers against their prior band (±1 σ) and bounds

Colours: blue = actual, orange = predicted (the reference categorical palette, light surface).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from whsizing.calibration.fit import Fit
from whsizing.calibration.models import M_BOUNDS

SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
ACTUAL, PREDICTED, BAND = "#2a78d6", "#eb6834", "#cfe0f6"
DIVERGING = LinearSegmentedColormap.from_list("calib", [ACTUAL, "#f0efec", PREDICTED])
DPI = 130


def write_plots(fit: Fit, out_dir: Path | str) -> list[Path]:
    """Write the three PNGs under `<out_dir>/plots/`; returns their paths."""
    folder = Path(out_dir) / "plots"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, draw in (
        ("predicted_vs_actual.png", _predicted_vs_actual),
        ("residuals_by_month.png", _residuals),
        ("multipliers.png", _multipliers),
    ):
        fig = draw(fit)
        path = folder / name
        fig.savefig(path, dpi=DPI, facecolor=SURFACE)
        plt.close(fig)
        paths.append(path)
    return paths


def _style(ax: Axes) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=7)


def _predicted_vs_actual(fit: Fit) -> Figure:
    names = [*fit.actual, "total"]
    cols = min(3, len(names))
    rows = math.ceil(len(names) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 2.5 * rows), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    x = np.arange(len(fit.months))
    hold = fit.split.holdout
    for ax, name in zip(axes.ravel(), names, strict=False):
        act = fit.total(fit.actual) if name == "total" else fit.actual[name]
        pred = fit.total(fit.predicted) if name == "total" else fit.predicted[name]
        _style(ax)
        ax.axvspan(hold[0] - 0.5, hold[-1] + 0.5, color=BAND, alpha=0.5, lw=0)
        ax.plot(x, act, color=ACTUAL, marker="o", ms=3, lw=1.5, label="actual")
        ax.plot(x, pred, color=PREDICTED, marker="o", ms=3, lw=1.5, label="predicted")
        ax.set_title(name, fontsize=9, color=INK, loc="left")
        ax.set_xticks(x[::2], [fit.months[i] for i in x[::2]], rotation=45, ha="right")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("hours / month", fontsize=7, color=MUTED)
    for ax in axes.ravel()[len(names) :]:
        ax.set_visible(False)
    axes[0, 0].legend(frameon=False, fontsize=7, labelcolor=INK)
    fig.suptitle("Predicted vs actual monthly hours (shaded: hold-out)", fontsize=10, color=INK)
    fig.tight_layout()
    return fig


def _residuals(fit: Fit) -> Figure:
    names = [*fit.actual, "total"]
    grid = np.full((len(names), len(fit.months)), np.nan)
    for r, name in enumerate(names):
        act = fit.total(fit.actual) if name == "total" else fit.actual[name]
        pred = fit.total(fit.predicted) if name == "total" else fit.predicted[name]
        ok = act > 0
        grid[r, ok] = 100 * (pred[ok] - act[ok]) / act[ok]
    lim = max(10.0, float(np.nanmax(np.abs(grid)))) if np.isfinite(grid).any() else 10.0
    fig, ax = plt.subplots(figsize=(1.0 + 0.55 * len(fit.months), 0.9 + 0.4 * len(names)))
    fig.patch.set_facecolor(SURFACE)
    ax.imshow(grid, cmap=DIVERGING, vmin=-lim, vmax=lim, aspect="auto")
    for (r, c), v in np.ndenumerate(grid):
        if np.isfinite(v):
            ax.text(c, r, f"{v:.0f}", ha="center", va="center", fontsize=6.5, color=INK)
    ax.set_xticks(range(len(fit.months)), fit.months, rotation=45, ha="right", fontsize=7)
    ax.set_yticks(range(len(names)), names, fontsize=7)
    ax.tick_params(colors=MUTED)
    first, last = fit.split.holdout[0], fit.split.holdout[-1]
    ax.add_patch(Rectangle((first - 0.5, -0.5), last - first + 1, len(names), fill=False,
                               ec=INK, lw=1.2))  # fmt: skip
    ax.set_title("Residuals by month, % of actual (boxed: hold-out; orange = over-predicted)",
                 fontsize=9, color=INK, loc="left")  # fmt: skip
    fig.tight_layout()
    return fig


def _multipliers(fit: Fit) -> Figure:
    rows = [t for t in fit.theta if t.kind == "multiplier"]
    fig, ax = plt.subplots(figsize=(6.5, 0.9 + 0.38 * len(rows)))
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    for y, t in enumerate(rows):
        ax.plot([t.lo, t.hi], [y, y], color=MUTED, lw=0.8, marker="|", ms=6, zorder=1)
        ax.plot([max(t.lo, t.prior - t.sigma), min(t.hi, t.prior + t.sigma)], [y, y], color=BAND,
                lw=7, zorder=2,
                solid_capstyle="butt")  # fmt: skip
        ax.plot(t.prior, y, marker="|", color=MUTED, ms=9, zorder=3)
        eff = t.effective if t.effective is not None else t.fitted
        ax.plot(eff, y, "o", color=PREDICTED, ms=6, zorder=4)
        ax.text(M_BOUNDS[1] + 0.03, y, f"{eff:.2f}", va="center", fontsize=7, color=INK)
    ax.set_yticks(range(len(rows)), [t.name.removeprefix("m:") for t in rows], fontsize=7)
    ax.set_xlim(M_BOUNDS[0] - 0.02, M_BOUNDS[1] + 0.2)
    ax.invert_yaxis()
    ax.set_xlabel("productivity multiplier (effective, at the basis PF&D)", fontsize=7, color=MUTED)
    ax.set_title("Calibrated multipliers (orange) vs prior band ±1 σ (blue) and bounds (grey)",
                 fontsize=9, color=INK, loc="left")  # fmt: skip
    fig.tight_layout()
    return fig
