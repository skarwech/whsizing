"""R6 remediation of the F2 findings: a parquet input under a folder with glob characters (I75 i),
and a binary or garbage file that must be a MappingError (exit 2) naming the file, never the raw
polars ValueError of a multi-byte separator (exit 1) or another raw exception of the readers."""

from __future__ import annotations

import codecs
import csv
import random
import sys
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest
import xlsxwriter

from whsizing.errors import ConfigError, MappingError
from whsizing.io import ingest, read_any, sniff
from whsizing.io.readers import read_parquet_file
from whsizing.io.sniff import (
    DATE_SCAN_COLUMNS,
    detect_date_format,
    detect_delimiter,
    detect_file_date_format,
    split_lines,
)
from whsizing.schemas.ingest import Mapping
from whsizing.schemas.manifest import SniffResult
from whsizing.schemas.project import InputSpec

WEIRD = "client [2025] *x?"  # every glob character of fnmatch
RANDOM_SEEDS = range(60)


def garbage(seed: int, folder: Path) -> Path:
    """4000 pseudo-random bytes (`head -c 4000 /dev/urandom`, but repeatable) in `g.csv`."""
    path = folder / "g.csv"
    path.write_bytes(random.Random(seed).randbytes(4000))
    return path


def quoted_table(folder: Path, separator: str) -> Path:
    """`g.csv`: 12 rows of 3 quoted cells joined by `separator`. No `;` `,` TAB or `|`, so the
    candidate delimiters find nothing and csv.Sniffer names the character between a closing and an
    opening quote, i.e. `separator`: checked on CPython 3.12.0, .13, .14, .16, 3.13.0, .18, 3.14.0
    and .10. The byte-order mark fixes the encoding (charset_normalizer has no stable verdict on
    so short a text)."""
    rows = [separator.join(f'"r{i}c{j}"' for j in range(3)) for i in range(12)]
    path = folder / "g.csv"
    path.write_bytes(codecs.BOM_UTF8 + "\n".join(rows).encode("utf-8"))
    return path


def two_columns(folder: Path) -> Path:
    """`g.csv`, a `;` table of two columns: no row has the 3 cells of a header row."""
    path = folder / "g.csv"
    path.write_text("sku;qty\nA;1\nB;2\n", encoding="utf-8")
    return path


def broken_promise(read: Callable[[Path], SniffResult], path: Path) -> str | None:
    """Why `read(path)` is not what the product promises for any file: a result whose delimiter
    polars can take, or a MappingError (exit 2) that names the file. None when it keeps it."""
    try:
        result = read(path)
    except MappingError as e:
        return None if path.name in str(e) and e.exit_code == 2 else f"unnamed MappingError: {e}"
    except Exception as e:
        return f"raw {type(e).__name__}: {e}"
    delimiter = result.delimiter or ","
    return None if len(delimiter.encode("utf-8")) == 1 else f"delimiter {delimiter!r}"


def read_any_sniff(path: Path) -> SniffResult:
    return read_any(path).sniff


# ------------------------------------------------------------------ I75 i: parquet input
def test_I75_i_read_any_reads_a_parquet_input_under_a_folder_with_glob_characters(
    tmp_path: Path,
) -> None:
    """Was: a raw polars ComputeError (`_read_parquet` read the path as a glob)."""
    path = tmp_path / WEIRD / "stock.parquet"
    path.parent.mkdir()
    pl.DataFrame({"sku": ["A", "B", "C"], "qty": [1, 2, 3]}).write_parquet(path)
    raw = read_any(path)
    assert raw.columns == ["sku", "qty"]
    assert raw.df["qty"].to_list() == ["1", "2", "3"]
    assert read_parquet_file(path).height == 3  # the helper moved to io.readers, same behaviour


def test_I75_i_ingest_takes_a_parquet_sku_master_from_a_folder_with_glob_characters(
    tmp_path: Path,
) -> None:
    csv = (
        Path(__file__).resolve().parents[1] / "golden" / "tiny_golden" / "csv_en" / "sku_master.csv"
    )
    path = tmp_path / WEIRD / "sku_master.parquet"
    path.parent.mkdir()
    pl.read_csv(csv, infer_schema=False).write_parquet(path)
    ingest({"sku_master": InputSpec(files=[path])}, tmp_path / "run", b"salt")
    canonical = read_parquet_file(tmp_path / "run" / "canonical" / "sku_master.parquet")
    assert canonical.height == pl.read_csv(csv, infer_schema=False).height


def test_I75_i_the_helper_is_still_importable_from_ingest() -> None:
    from whsizing.io.ingest import read_parquet_file as from_ingest

    assert from_ingest is read_parquet_file


# ------------------------------------------------------------------ R6.2: binary files
# polars takes a one-byte separator; csv.Sniffer can name any punctuation character, '§' included.
# What it names for random bytes is no contract: its quote regexes were rewritten (a quadratic-time
# fix) in CPython 3.12.14 and in later 3.13 and 3.14 releases. Tried: old behaviour on 3.12.0 to
# .13, 3.13.0 and 3.14.0, new on 3.12.14 to .16, 3.13.18 and 3.14.10. Seeds 7 and 10 sniff '\x89'
# and '¤' on the old, '@' and nothing on the new. The guard is tested on content that names the
# character on all of them, the promise on a range of random files.
SEPARATORS = [
    pytest.param("§", id="U+00A7-2-bytes"),
    pytest.param("¦", id="U+00A6-2-bytes"),
    pytest.param("€", id="U+20AC-3-bytes"),
]


@pytest.mark.parametrize("separator", SEPARATORS)
def test_R6_2_a_sniffed_multi_byte_separator_is_a_mapping_error_naming_the_file(
    separator: str, tmp_path: Path
) -> None:
    """Was: `ValueError: separator="\\x96" should be a single byte character` out of pl.read_csv,
    exit 1."""
    path = quoted_table(tmp_path, separator)
    assert detect_delimiter(split_lines(path.read_text(encoding="utf-8-sig"))) == separator
    with pytest.raises(MappingError, match=r"g\.csv: not a readable CSV.*sniffed delimiter") as e:
        read_any(path)
    assert e.value.exit_code == 2


@pytest.mark.parametrize("read", [sniff, read_any_sniff], ids=["sniff", "read_any"])
def test_R6_2_a_random_binary_file_is_read_or_a_mapping_error_naming_the_file(
    read: Callable[[Path], SniffResult], tmp_path: Path
) -> None:
    """What the sniffer makes of random bytes (a multi-byte separator, an unclosed quote, no
    header row, a table of garbage) changes with the CPython release; that no raw exception or
    unusable delimiter comes out must not. Every failure is listed with its seed."""
    broken = [
        (seed, why)
        for seed in RANDOM_SEEDS
        if (why := broken_promise(read, garbage(seed, tmp_path)))
    ]
    assert not broken, "\n".join(f"seed {seed}: {why}" for seed, why in broken)


def test_R6_2_a_file_without_a_header_row_names_the_file(tmp_path: Path) -> None:
    """The sniffer's 'no header row found' did not say which file (several inputs per dataset)."""
    with pytest.raises(MappingError, match=r"g\.csv: no header row found"):
        read_any(two_columns(tmp_path))


def test_R6_2_a_saved_delimiter_of_more_than_one_byte_is_a_config_error(tmp_path: Path) -> None:
    csv = tmp_path / "a.csv"
    csv.write_text("sku;qty;name\nA;1;x\nB;2;y\n", encoding="utf-8")
    mapping = Mapping(dataset="sku_master", delimiter="é", columns={"sku": "sku"})
    with pytest.raises(ConfigError, match="one-byte delimiter"):
        read_any(csv, mapping=mapping)


def test_R6_2_the_public_sniff_of_a_csv_has_the_same_guards_as_read_any(tmp_path: Path) -> None:
    """Audit R6 low: `sniff(path)` returned a 2-byte delimiter and its 'no header row' error did
    not name the file; only read_any guarded."""
    with pytest.raises(MappingError, match=r"g\.csv: not a readable CSV.*sniffed delimiter"):
        sniff(quoted_table(tmp_path, "§"))
    with pytest.raises(MappingError, match=r"g\.csv: no header row found"):
        sniff(two_columns(tmp_path))


# ------------------------------------------------------------------ R6.2b: corrupt parquet
def _truncated(folder: Path) -> Path:
    good = folder / "good.parquet"
    pl.DataFrame({"sku": ["A", "B"], "qty": [1, 2]}).write_parquet(good)
    path = folder / "truncated.parquet"
    path.write_bytes(good.read_bytes()[:-20])  # footer cut off
    return path


@pytest.mark.parametrize("kind", ["empty", "garbage", "magic_only", "random_framed", "truncated"])
def test_R6_2_a_corrupt_parquet_is_a_mapping_error_naming_the_file(
    kind: str, tmp_path: Path
) -> None:
    """Was: the raw polars ComputeError (or a pyo3 PanicException for some bit flips), exit 1,
    run folder left behind; the R6.2 guard only covered CSV."""
    path = tmp_path / f"{kind}.parquet"
    payloads = {
        "empty": b"",
        "garbage": b"garbage",
        "magic_only": b"PAR1",
        "random_framed": b"PAR1" + random.Random(1).randbytes(500) + b"PAR1",
    }
    if kind == "truncated":
        path = _truncated(tmp_path)
    else:
        path.write_bytes(payloads[kind])
    with pytest.raises(MappingError, match=rf"{path.name}: not a readable Parquet file") as e:
        read_any(path)
    assert e.value.exit_code == 2


def test_R6_2_a_parquet_with_a_nested_column_is_a_mapping_error(tmp_path: Path) -> None:
    """The text cast of a List column raised InvalidOperationError (exit 1)."""
    path = tmp_path / "nested.parquet"
    pl.DataFrame({"sku": ["A"], "tags": [[1, 2]]}).write_parquet(path)
    with pytest.raises(MappingError, match=r"nested\.parquet: not a readable Parquet file"):
        read_any(path)


# ------------------------------------------------------------------ R6.2c: the csv module's limits
TOO_LONG = 200_000  # characters in one line; csv.field_size_limit() is 131 072


@pytest.mark.parametrize("fill", [b"\x00", b"a"], ids=["zero-filled", "one-letter"])
def test_R6_2_a_line_over_the_csv_field_limit_is_a_mapping_error_naming_the_file(
    fill: bytes, tmp_path: Path
) -> None:
    """Was: a raw `_csv.Error: field larger than field limit (131072)` (exit 1, no file name) for
    a zero-filled file or a one-line export: every candidate delimiter split the line with csv."""
    path = tmp_path / "g.csv"
    path.write_bytes(fill * TOO_LONG)
    for read in (sniff, read_any):
        with pytest.raises(MappingError, match=r"g\.csv: no header row found") as e:
            read(path)
        assert e.value.exit_code == 2


def test_R6_2_csv_sniffer_is_not_asked_about_a_line_over_the_csv_field_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old csv.Sniffer (CPython up to 3.12.13) is quadratic on a quote-dense line: 210 kB took
    103 s on 3.12.13, 0.07 s on 3.12.14. A line over the csv limit is no table: said at once."""

    def refuse(self: csv.Sniffer, sample: str, delimiters: str | None = None) -> csv.Dialect:
        raise AssertionError("csv.Sniffer was given a line over the csv field limit")

    monkeypatch.setattr(csv.Sniffer, "sniff", refuse)
    path = tmp_path / "g.csv"
    path.write_text('@"a' * 70_000, encoding="utf-8")  # 210 kB, none of ; , TAB |
    with pytest.raises(MappingError, match=r"g\.csv: no header row found"):
        sniff(path)


def test_R6_2_a_wide_header_is_still_split_on_its_real_delimiter() -> None:
    """30 000 columns are one 200 kB cell for the candidate `,`: csv's limit must not end the
    count that finds `;`."""
    wide = ";".join(f"c{i}" for i in range(30_000))
    assert detect_delimiter([wide, "1;2;3"]) == ";"


@pytest.mark.parametrize("where", ["header", "data row"])
def test_R6_2_a_cell_over_the_csv_field_limit_does_not_stop_a_valid_table(
    where: str, tmp_path: Path
) -> None:
    """The limit is the csv module's: polars reads a 150 kB cell, so does the product."""
    cell = "y" * 150_000
    header = ["sku", "qty", cell if where == "header" else "name"]
    rows = [["A", "1", "x"], ["B", "2", cell if where == "data row" else "y"], ["C", "3", "z"]]
    path = tmp_path / "g.csv"
    path.write_text("\n".join(";".join(r) for r in [header, *rows]) + "\n", encoding="utf-8")
    assert sniff(path).delimiter == ";"
    raw = read_any(path)
    assert raw.columns == header
    assert raw.df[header[2]].to_list() == [r[2] for r in rows]


# ------------------------------------------------------------------ R6.2d: a saved header_row
@pytest.mark.parametrize(
    "content",
    [b"", b"sku;qty;name\n", b"sku;qty;name", b"\n\n\n"],
    ids=["empty", "one-line", "no-final-newline", "blank-lines"],
)
def test_R6_2_a_saved_header_row_past_the_end_of_a_csv_is_a_mapping_error_naming_the_file(
    content: bytes, tmp_path: Path
) -> None:
    """Was: a raw `polars.exceptions.NoDataError: empty CSV` (exit 1), or with no final newline
    the last line read as the header. A saved header_row skips the sniffer's 'no header row'
    guard: an empty export read with the mapping of the last one."""
    path = tmp_path / "g.csv"
    path.write_bytes(content)
    mapping = Mapping(dataset="sku_master", delimiter=";", header_row=5, columns={"sku": "sku"})
    with pytest.raises(MappingError, match=r"g\.csv: nothing to read from header row 5") as e:
        read_any(path, mapping=mapping)
    assert e.value.exit_code == 2


def test_R6_2_a_saved_header_row_past_the_end_of_a_sheet_is_a_mapping_error(tmp_path: Path) -> None:
    """Was: a raw `IndexError: list index out of range` (exit 1), same cause as for a CSV."""
    path = tmp_path / "g.xlsx"
    book = xlsxwriter.Workbook(path)
    book.add_worksheet().write_row(0, 0, ["sku", "qty", "name"])
    book.close()
    mapping = Mapping(dataset="sku_master", header_row=5, columns={"sku": "sku"})
    with pytest.raises(MappingError, match=r"g\.xlsx: sheet 'Sheet1' has 1 row\(s\)") as e:
        read_any(path, mapping=mapping)
    assert e.value.exit_code == 2


# ------------------------------------------------------------------ R6.2e: a regex-like header
@pytest.mark.parametrize(
    "name", ["^[$", "^a$", "^\x1cJ*{$"], ids=["invalid", "matches-a", "binary"]
)
def test_R6_2_a_header_cell_that_polars_reads_as_a_regex_is_a_mapping_error_naming_the_file(
    name: str, tmp_path: Path
) -> None:
    """Was: a raw `polars.exceptions.InvalidOperationError: invalid regex in selector` or
    `IndexError` (exit 1) out of the readers and the mapping, for a header cell that starts with ^
    and ends with $ (rare: one random file in some tens of thousands); polars takes
    `pl.col('^a$')` for a regex, so such a name selects another column or none."""
    path = tmp_path / "g.csv"
    path.write_bytes(codecs.BOM_UTF8 + f"sku;{name};a\nA; x ;p\nB;;q\n".encode())
    with pytest.raises(
        MappingError, match=r"g\.csv: header cell 2 starts with \^ and ends with \$"
    ) as e:
        read_any(path)  # the BOM fixes the encoding: a control character fools the sniffer
    assert e.value.exit_code == 2


# ------------------------------------------------ R6.2f: the reader's own column, a very wide file
@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_R6_2_a_column_named_like_the_line_number_column_is_a_mapping_error_naming_the_file(
    suffix: str, tmp_path: Path
) -> None:
    """Was: a raw `polars.exceptions.DuplicateError` (exit 1). `__source_row__` is the name the
    readers keep for each row's line number, so a file that has such a column cannot be read."""
    path = tmp_path / f"g.{suffix}"
    if suffix == "csv":
        path.write_text("sku;__source_row__;qty\nA;1;2\nB;3;4\n", encoding="utf-8")
    else:
        book = xlsxwriter.Workbook(path)
        sheet = book.add_worksheet()
        sheet.write_row(0, 0, ["sku", "__source_row__", "qty"])
        sheet.write_row(1, 0, ["A", "1", "2"])
        book.close()
    with pytest.raises(MappingError, match=rf"g\.{suffix}: a column is named __source_row__") as e:
        read_any(path)
    assert e.value.exit_code == 2


def test_R6_2_the_file_level_date_format_looks_at_the_first_columns_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A binary file read as a table of thousands of text columns took 3.3 ms per column in this
    step (6 s for 80 kB, about a minute for a 200 kB line). The per-column parsing of the mapping
    still reads every date column; this is the summary of the file."""
    calls: list[int] = []

    def counting(series: pl.Series) -> tuple[str | None, float]:
        calls.append(1)
        return detect_date_format(series)

    # `whsizing.io.sniff` is the function the package re-exports: the module is in sys.modules
    monkeypatch.setattr(sys.modules["whsizing.io.sniff"], "detect_date_format", counting)
    text_only = [["word", "text"] for _ in range(1000)]
    assert detect_file_date_format(text_only) is None
    assert len(calls) == DATE_SCAN_COLUMNS
    dated = [["word", "text"] for _ in range(1000)]
    dated[3] = ["2025-03-01", "2025-03-02"]  # among the first columns: found as before
    assert detect_file_date_format(dated) == "%Y-%m-%d"
