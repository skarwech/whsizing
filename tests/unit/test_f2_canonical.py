"""F2 canonical validation (§4.1): missing columns raise §2.7 errors, never raw polars ones."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from whsizing.errors import WhsizingError
from whsizing.io.canonical import validate

LINES = pl.DataFrame(
    {
        "order_id": ["O1", "O2"],
        "order_ts": pl.Series([datetime(2025, 1, 2, 9, tzinfo=UTC)] * 2).cast(
            pl.Datetime("us", "UTC")
        ),
        "sku": ["A", "B"],
        "qty_units": [1, 2],
        "source_file": ["f.csv"] * 2,
        "source_row": [2, 3],
    }
)
MASTER = pl.DataFrame(
    {
        "sku": ["A", "B"],
        "length_mm": [100.0, 200.0],
        "width_mm": [50.0, 60.0],
        "height_mm": [10.0, 20.0],
        "weight_kg": [0.5, 1.5],
    }
)


@pytest.mark.parametrize(
    ("name", "df", "missing"),
    [
        ("order_lines", LINES.drop("sku"), ["sku"]),
        ("order_lines", LINES.drop("qty_units", "source_file"), ["qty_units", "source_file"]),
        ("sku_master", MASTER.drop("weight_kg"), ["weight_kg"]),
        ("inventory", pl.DataFrame({"sku": ["A"], "qty_units": [3]}), ["snapshot_date"]),
        ("order_lines", LINES.drop("order_ts"), ["order_ts"]),  # not coerced by pandera
        ("receipts", pl.DataFrame({"sku": ["A"], "qty_units": [3]}), ["receipt_id", "receipt_ts"]),
    ],
)
def test_T2_9_missing_required_column_is_a_whsizing_error_exit_1(
    name: str, df: pl.DataFrame, missing: list[str]
) -> None:
    """F2e: pandera coerces before it checks presence, so a missing coerced column (sku,
    qty_units, source_file, weight_kg, ...) leaked polars' ColumnNotFoundError. A canonical
    table without a required column is an F2 bug or a hand-built file, not an R-rule (§2.7
    exit 3): every missing column, coerced (sku) or not (order_ts, receipt_ts), raises the
    same WhsizingError (exit 1) naming the table and each column (F2e fix round 1)."""
    with pytest.raises(WhsizingError) as e:
        validate({name: df})
    assert type(e.value) is WhsizingError and e.value.exit_code == 1
    # I72: the one wording, once per missing column, in schema order
    wording = "; ".join(f'cannot find column "{col}" (required by §4.1)' for col in missing)
    assert str(e.value) == f"canonical {name}: {wording}"


def test_T2_9_complete_frames_pass_and_a_bad_dtype_is_a_whsizing_error() -> None:
    """Optional columns may be absent; a present column of the wrong type fails pandera's own
    check, a WhsizingError (exit 1) naming the table, still no raw polars error."""
    out = validate({"order_lines": LINES, "sku_master": MASTER})
    assert out["order_lines"].height == 2 and out["sku_master"]["sku"].to_list() == ["A", "B"]
    naive = LINES.with_columns(pl.col("order_ts").dt.replace_time_zone(None))
    with pytest.raises(WhsizingError, match=r"canonical order_lines failed schema") as e:
        validate({"order_lines": naive})
    assert type(e.value) is WhsizingError and e.value.exit_code == 1


def test_T2_9_unknown_table_name_is_a_whsizing_error_not_a_keyerror() -> None:
    """R3 fix round 1, finding 3: validate({"foo": ...}) leaked a bare KeyError ('foo')."""
    wording = r"unknown canonical table 'foo' \(known: .*order_lines"
    with pytest.raises(WhsizingError, match=wording) as e:
        validate({"foo": pl.DataFrame({"x": [1]})})
    assert type(e.value) is WhsizingError and e.value.exit_code == 1
