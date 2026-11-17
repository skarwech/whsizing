"""F3f / I6 (amended): ABC ties are broken by lines, units, avg_stock, unit cube, weight (all
descending) and only then by the sku id, which depends on the anonymisation salt."""

from __future__ import annotations

from collections.abc import Sequence

import polars as pl

from whsizing.profile.abc import abc, classify

THRESHOLDS = (0.80, 0.95)
Row = tuple[str, int, int, float, float, float | None]
COLS = ("sku", "lines", "units", "avg_stock", "unit_cube_m3", "weight_kg")
TYPES = (pl.String, pl.Int64, pl.Int64, pl.Float64, pl.Float64, pl.Float64)


def frame(rows: Sequence[Row]) -> pl.DataFrame:
    df = pl.DataFrame(rows, schema=dict(zip(COLS, TYPES, strict=True)), orient="row")
    return df.with_columns(
        cube_movement_m3=pl.col("units") * pl.col("unit_cube_m3"),
        stock_cube_m3=pl.col("avg_stock") * pl.col("unit_cube_m3"),
    )


def order(rows: Sequence[Row]) -> list[str]:
    """Ranking of `classify` by lines, on the rows as given and reversed (input order is moot)."""
    ranked = classify(frame(rows), "lines", THRESHOLDS)["sku"].to_list()
    assert classify(frame(rows[::-1]), "lines", THRESHOLDS)["sku"].to_list() == ranked
    return ranked


def test_T3_2_ties_on_lines_only_are_broken_by_units_not_by_sku() -> None:
    rows = [("a", 5, 10, 1.0, 0.1, 1.0), ("b", 5, 30, 1.0, 0.1, 1.0), ("c", 5, 20, 1.0, 0.1, 1.0)]
    assert order(rows) == ["b", "c", "a"]  # old order (lines, sku) gave a, b, c


def test_T3_2_ties_on_lines_and_units_follow_stock_then_cube_then_weight() -> None:
    stock = [("a", 5, 10, 1.0, 0.1, 1.0), ("b", 5, 10, 3.0, 0.1, 1.0), ("c", 5, 10, 2.0, 0.1, 1.0)]
    assert order(stock) == ["b", "c", "a"]
    cube = [("a", 5, 10, 2.0, 0.1, 1.0), ("b", 5, 10, 2.0, 0.3, 1.0), ("c", 5, 10, 2.0, 0.2, 1.0)]
    assert order(cube) == ["b", "c", "a"]
    weight = [("a", 5, 10, 2.0, 0.2, 1.0), ("b", 5, 10, 2.0, 0.2, 3.0), ("c", 5, 10, 2.0, 0.2, 2.0)]
    assert order(weight) == ["b", "c", "a"]


def test_T3_2_a_rung_only_counts_when_every_rung_above_ties() -> None:
    """Each row beats the next on one rung only, while the lower rungs and the id favour the
    next row: a wrong rung order puts a row in the wrong place."""
    rows = [
        ("z", 6, 1, 1.0, 0.1, 1.0),  # lines
        ("y", 5, 9, 1.0, 0.1, 1.0),  # units
        ("x", 5, 8, 9.0, 0.1, 1.0),  # avg_stock
        ("w", 5, 8, 8.0, 0.9, 1.0),  # unit cube
        ("v", 5, 8, 8.0, 0.8, 9.0),  # weight
        ("a", 5, 8, 8.0, 0.8, 1.0),
    ]
    assert order(rows) == ["z", "y", "x", "w", "v", "a"]


def test_T3_2_unknown_weight_ranks_last_and_identical_skus_fall_back_to_sku_ascending() -> None:
    rows = [
        ("b", 5, 10, 2.0, 0.2, 1.0),
        ("a", 5, 10, 2.0, 0.2, None),  # unknown weight: after any known weight, whatever the id
        ("d", 5, 10, 2.0, 0.2, 1.0),  # identical to b: sku ascending
        ("c", 5, 10, 2.0, 0.2, 1.0),  # identical to b and d
    ]
    assert order(rows) == ["b", "c", "d", "a"]


def test_T3_2_class_of_tied_skus_follows_the_attributes_not_the_id() -> None:
    """Lines 80, 10, 10, 5: the cumulative share before the two tied SKUs is 0.76 (A) and 0.86
    (B). The one with more units takes the better class even though its id sorts last."""
    rows = [
        ("m", 80, 80, 5.0, 0.1, 1.0),
        ("z", 10, 100, 5.0, 0.1, 1.0),
        ("a", 10, 50, 5.0, 0.1, 1.0),
        ("n", 5, 5, 5.0, 0.1, 1.0),
    ]
    ranked = classify(frame(rows), "lines", THRESHOLDS)
    classes = dict(zip(ranked["sku"], ranked["abc"], strict=True))
    assert classes == {"m": "A", "z": "A", "a": "B", "n": "C"}
    # the same SKUs under other ids: same ranking of attributes, same classes
    other = frame(rows).with_columns(sku=pl.col("sku").replace({"z": "a", "a": "z"}))
    again = classify(other, "lines", THRESHOLDS)
    assert again["units"].to_list() == ranked["units"].to_list()
    assert again["abc"].to_list() == ranked["abc"].to_list()


def test_T3_2_other_orderings_break_ties_by_the_same_chain() -> None:
    """Cube movement and stock cube ties (equal `by`) are ranked by lines, units, ... too."""
    rows = [("a", 3, 4, 1.0, 0.5, 1.0), ("b", 5, 4, 1.0, 0.5, 1.0), ("c", 4, 4, 1.0, 0.5, 1.0)]
    for by in ("cube_movement_m3", "stock_cube_m3"):
        assert classify(frame(rows), by, THRESHOLDS)["sku"].to_list() == ["b", "c", "a"], by


def test_T3_2_abc_result_is_unchanged_by_swapping_two_skus_ids_in_a_tie() -> None:
    rows = [(f"s{i:02d}", 3, 10 + i, 1.0, 0.1, 1.0) for i in range(20)]
    swapped = [(f"s{19 - i:02d}", *r[1:]) for i, r in enumerate(rows)]
    assert abc(frame(rows), THRESHOLDS) == abc(frame(swapped), THRESHOLDS)


def test_T3_2_null_weight_vs_zero_weight_is_ordered_by_attribute_under_either_id_assignment() -> (
    None
):
    """Null ranks after a known 0.0 whichever id each carries (null filled with 0.0 would leave
    the pair to the salt-dependent sku id)."""
    for zero_id, null_id in (("b", "a"), ("a", "b")):
        rows = [
            (zero_id, 5, 10, 2.0, 0.2, 0.0),
            (null_id, 5, 10, 2.0, 0.2, None),
            ("c", 5, 10, 2.0, 0.2, 1.0),
        ]
        assert order(rows) == ["c", zero_id, null_id]
