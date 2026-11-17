"""F3f property: relabelling every SKU id (another anonymisation salt) leaves the ABC classes
unchanged: class sizes, line shares and the multiset of attributes of each class's SKUs (I6)."""

from __future__ import annotations

from collections import Counter

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from whsizing.profile.abc import abc, classify

THRESHOLDS = (0.80, 0.95)
ATTRS = ("lines", "units", "avg_stock", "unit_cube_m3", "weight_kg")
BYS = ("lines", "cube_movement_m3", "stock_cube_m3")

# Small ranges, so most SKUs tie on lines and often on several attributes.
sku_attrs = st.tuples(
    st.integers(0, 4),  # lines
    st.integers(0, 3),  # units
    st.integers(0, 3).map(float),  # avg_stock
    st.integers(1, 3).map(lambda i: i / 1000),  # unit_cube_m3
    st.one_of(st.none(), st.integers(0, 2).map(float)),  # weight_kg
)


def table(attrs: list[tuple], ids: list[str]) -> pl.DataFrame:
    df = pl.DataFrame(
        {"sku": ids, **{c: [a[i] for a in attrs] for i, c in enumerate(ATTRS)}},
        schema_overrides={"weight_kg": pl.Float64, "units": pl.Int64, "lines": pl.Int64},
    )
    return df.with_columns(
        cube_movement_m3=pl.col("units") * pl.col("unit_cube_m3"),
        stock_cube_m3=pl.col("avg_stock") * pl.col("unit_cube_m3"),
    )


def members(ranked: pl.DataFrame) -> dict[str, Counter[tuple]]:
    """Per class, the multiset of the salt-independent attributes of its SKUs."""
    return {
        c: Counter(ranked.filter(pl.col("abc") == c).select(ATTRS).rows()) for c in ("A", "B", "C")
    }


@settings(max_examples=200, deadline=None)
@given(data=st.data(), attrs=st.lists(sku_attrs, min_size=2, max_size=40))
def test_T3_7_abc_classes_do_not_depend_on_the_sku_ids(data: st.DataObject, attrs: list) -> None:
    n = len(attrs)
    labels = data.draw(st.permutations(range(n)), label="bijection")
    other = data.draw(st.permutations(range(n)), label="other bijection")
    one = table(attrs, [f"{i:03d}" for i in range(n)])
    two = table(attrs, [f"{labels[i]:03d}" for i in range(n)])
    three = table(attrs, [f"{other[i]:03d}" for i in range(n)])
    for by in BYS:
        assert members(classify(one, by, THRESHOLDS)) == members(classify(two, by, THRESHOLDS)), by
    for other_labels in (two, three):
        a, b = abc(one, THRESHOLDS), abc(other_labels, THRESHOLDS)
        for by in ("by_lines", "by_cube_movement", "by_stock_cube"):
            assert getattr(a, by) == getattr(b, by), by  # n_skus and every share, per class
        assert a.pareto_lines == b.pareto_lines
