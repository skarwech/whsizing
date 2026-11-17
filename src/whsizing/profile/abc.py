"""F3 step 4: ABC / Pareto by lines, by cube movement and by stock cube (I6)."""

from __future__ import annotations

import numpy as np
import polars as pl

from whsizing.profile.aggregate import fsum
from whsizing.schemas import ABC, AbcClassStats

CLASSES = ("A", "B", "C")
PARETO_POINTS = 100
# I6 tie-break after `by`, all descending, then sku ascending. The hashed sku id depends on the
# anonymisation salt, so it only orders SKUs identical in every attribute (interchangeable).
TIE_BREAK = ("lines", "units", "avg_stock", "unit_cube_m3", "weight_kg")


def rank(skus: pl.DataFrame, by: str) -> pl.DataFrame:
    """`skus` sorted by `by`, then the I6 attributes present in the frame, all descending, then
    sku ascending. Nulls (an unknown weight) rank after every known value, 0 included, so two SKUs
    that differ only in null vs 0 are still ordered by attribute, not by the hashed id."""
    ties = [c for c in TIE_BREAK if c != by and c in skus.columns]
    return skus.sort(
        [by, *ties, "sku"], descending=[True] * (len(ties) + 1) + [False], nulls_last=True
    )


def classify(skus: pl.DataFrame, by: str, thresholds: tuple[float, float]) -> pl.DataFrame:
    """SKUs in `rank` order (`by` descending, ties by the I6 attributes, then sku); class from the
    cumulative share *before* the SKU: A if < thresholds[0], B if < thresholds[1], else C; zero → C
    (I6).
    Shares and their running sum are taken in numpy, as the golden oracle does (true division,
    left to right): polars divides by a reciprocal multiply, so 28 × (1/35) < 0.80 made the
    SKU after an exact 80 % tie A instead of B."""
    a, b = thresholds
    total = fsum(skus[by])
    ranked = rank(skus, by)
    if total <= 0:
        return ranked.with_columns(abc=pl.lit("C"))
    v = ranked[by].to_numpy().astype(float)
    before = np.concatenate([[0.0], np.cumsum(v / total)[:-1]])
    cls = np.where(v <= 0, "C", np.where(before < a, "A", np.where(before < b, "B", "C")))
    return ranked.with_columns(abc=pl.Series(cls, dtype=pl.String))


def class_stats(ranked: pl.DataFrame, cube_col: str) -> dict[str, AbcClassStats]:
    """Per class: SKU count and shares of SKUs, of lines and of `cube_col`."""
    n, lines, cube = ranked.height, float(ranked["lines"].sum()), fsum(ranked[cube_col])
    out = {}
    for c in CLASSES:
        g = ranked.filter(pl.col("abc") == c)
        out[c] = AbcClassStats(
            n_skus=g.height,
            sku_share=g.height / n if n else 0.0,
            line_share=float(g["lines"].sum()) / lines if lines else 0.0,
            cube_share=fsum(g[cube_col]) / cube if cube else 0.0,
        )
    return out


def pareto(lines_desc: np.ndarray) -> list[float]:
    """Cumulative line share at SKU share k/100, k = 1..100 (linear between SKUs)."""
    total = lines_desc.sum()
    x = np.arange(lines_desc.size + 1) / max(lines_desc.size, 1)
    y = np.concatenate([[0.0], np.cumsum(lines_desc) / total]) if total else np.zeros(x.size)
    return [float(v) for v in np.interp(np.arange(1, PARETO_POINTS + 1) / PARETO_POINTS, x, y)]


def abc(skus: pl.DataFrame, thresholds: tuple[float, float]) -> ABC:
    """`skus` needs sku, lines, cube_movement_m3 (units × unit cube), stock_cube_m3.
    cube_share = cube movement share for the line and movement classes, stock cube share for
    the stock-cube classes."""
    by_lines = classify(skus, "lines", thresholds)
    return ABC(
        thresholds=thresholds,
        by_lines=class_stats(by_lines, "cube_movement_m3"),
        by_cube_movement=class_stats(
            classify(skus, "cube_movement_m3", thresholds), "cube_movement_m3"
        ),
        by_stock_cube=class_stats(classify(skus, "stock_cube_m3", thresholds), "stock_cube_m3"),
        pareto_lines=pareto(by_lines["lines"].to_numpy().astype(float)),
    )
