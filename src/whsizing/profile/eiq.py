"""F3 step 3: EIQ order structure over all shipped orders and lines (I3)."""

from __future__ import annotations

import polars as pl

from whsizing.profile.aggregate import series_stats
from whsizing.schemas import EIQ


def order_class(n_lines: pl.Expr, bounds: tuple[int, int]) -> pl.Expr:
    """S ≤ bounds[0] lines < M ≤ bounds[1] lines < L ([P] 1 and 5)."""
    s_max, m_max = bounds
    return (
        pl.when(n_lines <= s_max)
        .then(pl.lit("S"))
        .when(n_lines <= m_max)
        .then(pl.lit("M"))
        .otherwise(pl.lit("L"))
    )


def eiq(lines: pl.DataFrame, orders: pl.DataFrame, bounds: tuple[int, int]) -> EIQ:
    n = orders["n_lines"]
    cls = orders.select(order_class(pl.col("n_lines"), bounds))[:, 0]
    return EIQ(
        lines_per_order=series_stats(n.to_numpy()),
        units_per_line=series_stats(lines["qty_units"].to_numpy()),
        units_per_order=series_stats(orders["units"].to_numpy()),
        cube_per_order_m3=series_stats(orders["cube_m3"].to_numpy()),
        weight_per_order_kg=series_stats(orders["weight_kg"].to_numpy()),
        single_line_share=float((n == 1).mean()),  # pyright: ignore[reportArgumentType]
        order_class_shares={c: float((cls == c).mean()) for c in ("S", "M", "L")},  # pyright: ignore[reportArgumentType]
    )
