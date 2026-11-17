"""F2 reader: repeated header names (final audit, low). With two columns named 'Quantity' the
first is mapped and the second silently ignored; a differing copy now yields a DQ note naming
the file, the column and that the second was ignored. Identical copies stay silent."""

from __future__ import annotations

from pathlib import Path

import pytest
import xlsxwriter

from whsizing.io import read_any
from whsizing.io.readers import duplicate_header_notes
from whsizing.schemas.ingest import Mapping

COLUMNS: dict[str, str | None] = {
    "order_id": "Order",
    "order_ts": "Date",
    "sku": "SKU",
    "qty_units": "Quantity",
}
MAPPING = Mapping(dataset="order_lines", columns=COLUMNS)
ROWS = [
    ["A1", "2025-01-01 10:00:00", "S1", "2", "5"],
    ["A2", "2025-01-01 11:00:00", "S2", "1", "1"],
]
HEADER = ["Order", "Date", "SKU", "Quantity", "Quantity"]


def _csv(path: Path, rows: list[list[str]], header: list[str] = HEADER, sep: str = ",") -> Path:
    path.write_text("\n".join(sep.join(r) for r in [header, *rows]) + "\n", encoding="utf-8")
    return path


def test_dupheader_two_quantity_columns_with_different_values_give_a_note(tmp_path: Path) -> None:
    raw = read_any(_csv(tmp_path / "ventes.csv", ROWS))
    assert raw.duplicate_headers == (("Quantity", "Quantity_duplicated_0"),)
    [note] = duplicate_header_notes(raw, MAPPING)
    assert note.startswith("[order_lines] ventes.csv, column 'Quantity' appears twice")
    assert "first is used" in note and "second (column 5" in note and "was ignored" in note
    assert raw.df["Quantity"].to_list() == ["2", "1"]  # the first column is the one mapped


def test_dupheader_identical_duplicate_columns_stay_silent(tmp_path: Path) -> None:
    same = [[*r[:4], r[3]] for r in ROWS]  # the second Quantity repeats the first
    raw = read_any(_csv(tmp_path / "ventes.csv", same))
    assert raw.duplicate_headers == () and duplicate_header_notes(raw, MAPPING) == []
    assert read_any(_csv(tmp_path / "plain.csv", [r[:4] for r in ROWS], HEADER[:4])).df.width == 5


def test_dupheader_semicolon_file_and_padded_header_names_are_compared_after_stripping(
    tmp_path: Path,
) -> None:
    header = ["Order", "Date", "SKU", "Quantity", " Quantity "]
    raw = read_any(_csv(tmp_path / "ventes.csv", ROWS, header, sep=";"))
    assert [n.split(" appears")[0][-10:] for n in duplicate_header_notes(raw, MAPPING)] == [
        "'Quantity'"
    ]


def test_dupheader_names_differing_only_by_case_are_one_name(tmp_path: Path) -> None:
    """Final audit F5: 'Quantity' and 'quantity' are two names to polars but one to the reader
    of the file; with different values the second was ignored without a note."""
    header = ["Order", "Date", "SKU", "Quantity", "quantity"]
    raw = read_any(_csv(tmp_path / "ventes.csv", ROWS, header))
    assert raw.duplicate_headers == (("Quantity", "quantity"),)
    [note] = duplicate_header_notes(raw, MAPPING)
    assert "column 'Quantity' appears twice" in note and "read as 'quantity'" in note
    same = [[*r[:4], r[3]] for r in ROWS]  # equal values under another case: harmless, silent
    assert read_any(_csv(tmp_path / "same.csv", same, header)).duplicate_headers == ()


def test_dupheader_note_only_when_the_first_is_mapped_and_the_second_is_not(tmp_path: Path) -> None:
    raw = read_any(_csv(tmp_path / "ventes.csv", ROWS))
    later = Mapping(dataset="order_lines", columns=COLUMNS | {"qty_units": "Quantity_duplicated_0"})
    assert duplicate_header_notes(raw, later) == []  # the user chose the second on purpose
    unrelated = Mapping(dataset="order_lines", columns=COLUMNS | {"qty_units": "SKU"})
    assert duplicate_header_notes(raw, unrelated) == []  # neither copy is read


@pytest.mark.parametrize("same", [False, True])
def test_dupheader_excel_repeated_header(tmp_path: Path, same: bool) -> None:
    path = tmp_path / "ventes.xlsx"
    wb = xlsxwriter.Workbook(path)
    ws = wb.add_worksheet("Ventes")
    ws.write_row(0, 0, HEADER)
    for i, r in enumerate(ROWS):
        ws.write_row(1 + i, 0, [*r[:4], r[3] if same else r[4]])
    wb.close()
    raw = read_any(path)
    assert raw.duplicate_headers == (() if same else (("Quantity", "Quantity_2"),))
    assert len(duplicate_header_notes(raw, MAPPING)) == (0 if same else 1)
