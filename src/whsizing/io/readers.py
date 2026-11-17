"""read_any: CSV / Excel / Parquet → RawTable (all-string cells + sniff result).

Cells are stripped and empty cells are null; blank rows and repeated header rows (concatenated
exports) are dropped. `SOURCE_ROW` keeps the 1-based line (CSV) or row (Excel) in the file.
Sniff values recorded in a saved mapping (Appendix E) are used instead of detecting them.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

import fastexcel
import polars as pl

from whsizing.errors import MappingError
from whsizing.io.sniff import (
    EXCEL_SUFFIXES,
    _fields,  # pyright: ignore[reportPrivateUsage]
    saved_sniff,
    sniff_csv,
    sniff_rows,
)
from whsizing.logging import get_logger
from whsizing.schemas.ingest import Mapping
from whsizing.schemas.manifest import SniffResult

SOURCE_ROW = "__source_row__"
_ISO_AWARE = "%Y-%m-%dT%H:%M:%S%:z"


@dataclass(frozen=True)
class RawTable:
    path: Path
    df: pl.DataFrame  # Utf8 columns named as in the file, plus SOURCE_ROW
    sniff: SniffResult
    # (first column, later column) of each repeated header whose values differ; the later one
    # carries the reader's suffix (`Quantity_duplicated_0`, `Quantity_2`)
    duplicate_headers: tuple[tuple[str, str], ...] = ()

    @property
    def columns(self) -> list[str]:
        return [c for c in self.df.columns if c != SOURCE_ROW]


def read_any(
    path: Path, sheet: str | int | None = None, mapping: Mapping | None = None
) -> RawTable:
    """`mapping`: a saved mapping whose encoding, delimiter, header_row, decimal, date_format
    and sheet replace the sniffed values (an explicit `sheet` still wins)."""
    path = Path(path)
    if not path.is_file():
        raise MappingError(f"input file not found: {path}")
    try:
        return _read(path, sheet, mapping)
    except MappingError as e:
        if path.name in str(e):
            raise
        raise MappingError(f"{path.name}: {e}") from e  # a binary file: say which one


def _read(path: Path, sheet: str | int | None, mapping: Mapping | None) -> RawTable:
    suffix = path.suffix.lower()
    if suffix in EXCEL_SUFFIXES:
        return _read_excel(path, sheet if sheet is not None else mapping and mapping.sheet, mapping)
    if suffix == ".parquet":
        return _read_parquet(path)
    return _read_csv(path, mapping)


def _decode(data: bytes, encoding: str) -> str:
    """Whole-file decode; a byte the sniffed encoding rejects past the first 1 MB falls back to
    cp1252, then latin-1 (logged)."""
    for enc in dict.fromkeys((encoding, "cp1252", "latin-1")):
        try:
            text = data.decode("utf-8-sig" if enc == "utf-8" else enc)
        except UnicodeDecodeError:
            continue
        if enc != encoding:
            get_logger().warning("encoding_fallback", sniffed=encoding, used=enc)
        return text
    raise AssertionError("latin-1 decodes any byte")


def _read_csv(path: Path, mapping: Mapping | None) -> RawTable:
    sn = sniff_csv(path, mapping)
    text = _decode(path.read_bytes(), sn.encoding).replace("\r\n", "\n").replace("\r", "\n")
    parts = text.split("\n", sn.header_row - 1)  # the sniff's lines (`split_lines`)
    body = parts[-1] if len(parts) == sn.header_row else ""  # fewer lines: no header row at all
    delimiter = sn.delimiter or ","
    try:
        df = pl.read_csv(
            io.BytesIO(body.encode("utf-8")),
            separator=delimiter,
            has_header=True,
            infer_schema=False,
            truncate_ragged_lines=True,
        )
    except pl.exceptions.NoDataError as e:  # an empty file, or a saved header_row past its end
        raise MappingError(
            f"{path.name}: nothing to read from header row {sn.header_row} on (the file is empty, "
            "or `header_row` in the mapping is past its last line); check the file or the mapping"
        ) from e
    except pl.exceptions.ComputeError:
        # a stray quote in an unquoted field (Ecran 24" LED): read again like the sniff does
        get_logger().warning("csv_lenient_quotes", file=path.name)
        df = _read_csv_lenient(path, body, delimiter)
    df = _with_source_row(path, df, sn.header_row + 1)
    header = _fields(body.partition("\n")[0], delimiter)
    return _finish(path, df, sn, header)


def _with_source_row(path: Path, df: pl.DataFrame, offset: int) -> pl.DataFrame:
    """`df` with the column that keeps each row's line number in the file. A file with a column of
    that very name cannot be read (polars refuses the duplicate): a MappingError, not a raw one."""
    if SOURCE_ROW in df.columns:
        raise MappingError(
            f"{path.name}: a column is named {SOURCE_ROW}, the name this reader keeps for the "
            "line number of each row; rename that column"
        )
    return df.with_row_index(SOURCE_ROW, offset=offset)


def _read_csv_lenient(path: Path, body: str, delimiter: str) -> pl.DataFrame:
    """Python's csv module keeps a quote inside an unquoted field as text; ragged rows are
    padded / truncated to the header like Polars. A quote that never closes is a MappingError."""
    reader = csv.reader(io.StringIO(body), delimiter=delimiter)
    try:
        rows = [r for r in reader if r]  # blank lines: Polars skips them, the header is the first
    except csv.Error as e:  # line that is not
        raise MappingError(f"{path.name}: unreadable CSV near line {reader.line_num}: {e}") from e
    if not rows:
        raise MappingError(f"{path.name}: no header row to read (the file has only blank lines)")
    spanning = next((i for i, r in enumerate(rows) if any("\n" in c for c in r)), None)
    if spanning is not None:
        raise MappingError(
            f"{path.name}: a double quote opened in data row {spanning} is never closed, so "
            "the rows after it run together; fix the quoting (or remove the quote) and re-run"
        )
    header, width = rows[0], len(rows[0])
    data = [(r + [""] * width)[:width] for r in rows[1:]]
    names = _unique([h.strip() or f"column_{j + 1}" for j, h in enumerate(header)])
    return pl.DataFrame(data, schema=dict.fromkeys(names, pl.Utf8), orient="row")


def _read_excel(path: Path, sheet: str | int | None, mapping: Mapping | None) -> RawTable:
    """Step 6: the sheet with the most rows unless `sheet` is given; header found as in step 3."""
    fixed = saved_sniff(mapping)
    try:
        reader = fastexcel.read_excel(path)
        names: list[str | int] = [sheet] if sheet is not None else list(reader.sheet_names)
        grids = {n: reader.load_sheet(n, header_row=None, dtypes="string") for n in names}
    except Exception as e:  # fastexcel raises its own error types (bad file, unknown sheet)
        raise MappingError(f"{path}: cannot read Excel file or sheet {sheet!r}: {e}") from e
    name, grid = max(grids.items(), key=lambda kv: kv[1].height)
    frame = grid.to_polars()
    rows = [[c or "" for c in r] for r in frame.head(2050).rows()]
    header, decimal, date_format, _ = sniff_rows(rows, fixed.get("header_row"))
    if header >= len(rows):  # a saved header_row past the last row read: an empty or short sheet
        raise MappingError(
            f"{path.name}: sheet {name!r} has {len(rows)} row(s), fewer than the mapping's "
            f"`header_row` ({header + 1}); check the file or the mapping"
        )
    names_row = [c.strip() if c else f"column_{j + 1}" for j, c in enumerate(rows[header])]
    df = frame.slice(header + 1)
    df = df.rename(dict(zip(df.columns, _unique(names_row), strict=True)))
    df = _with_source_row(path, df, header + 2)
    sn = SniffResult(
        encoding="binary",
        delimiter=None,
        header_row=header + 1,
        decimal=fixed.get("decimal", decimal),
        date_format=fixed.get("date_format", date_format),
        n_rows=df.height,
        sheet=str(reader.sheet_names[name] if isinstance(name, int) else name),
    )
    return _finish(path, df, sn, names_row)


def read_parquet_file(path: Path) -> pl.DataFrame:
    """`pl.read_parquet` of exactly this file: polars reads a path as a glob, so a folder named
    `client [2025]` is not found; an open handle is never expanded (I75 i)."""
    with path.open("rb") as f:
        return pl.read_parquet(f)


def _read_parquet(path: Path) -> RawTable:
    try:
        df = read_parquet_file(path)
        as_text = []
        for c, dtype in df.schema.items():
            if isinstance(dtype, pl.Datetime):
                fmt = _ISO_AWARE if dtype.time_zone else "%Y-%m-%d %H:%M:%S"
                as_text.append(pl.col(c).dt.strftime(fmt))
            elif dtype == pl.Date:
                as_text.append(pl.col(c).dt.strftime("%Y-%m-%d"))
            else:
                as_text.append(pl.col(c).cast(pl.Utf8))
        df = _with_source_row(path, df.select(as_text), 1)
    except (pl.exceptions.PolarsError, pl.exceptions.PanicException) as e:
        # truncated / empty / corrupt file (a pyo3 panic is not a PolarsError), or a nested column
        raise MappingError(f"{path.name}: not a readable Parquet file: {e}") from e
    sn = SniffResult(
        encoding="binary",
        delimiter=None,
        header_row=1,
        decimal=".",
        date_format=_ISO_AWARE,
        n_rows=df.height,
    )
    return _finish(path, df, sn)


def _unique(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    return out


def _differing_duplicates(
    path: Path, df: pl.DataFrame, header: list[str]
) -> tuple[tuple[str, str], ...]:
    """(first, later) column pairs of a header name (case-insensitive: 'Quantity' and 'quantity'
    are one name to a reader of the file) that occurs twice with different values; identical
    copies are harmless and not reported. `header` is the file's header row, in the
    order of the columns of `df` (SOURCE_ROW excluded)."""
    cols = [c for c in df.columns if c != SOURCE_ROW]
    if len(cols) != len(header):  # the reader and csv disagree on the header: cannot compare
        get_logger().warning(
            "header_width_mismatch", file=path.name, columns=len(cols), header=len(header)
        )
        return ()
    first: dict[str, str] = {}
    pairs = []
    for name, col in zip((h.strip().casefold() for h in header), cols, strict=True):
        if not name:
            continue
        if name not in first:
            first[name] = col
        elif not df[col].equals(df[first[name]]):
            pairs.append((first[name], col))
    return tuple(pairs)


def duplicate_header_notes(raw: RawTable, mapping: Mapping) -> list[str]:
    """DQ notes for a header name used by two columns with different values, when the mapping
    reads the first and not the later one (the first wins silently otherwise)."""
    used = {c for c in mapping.columns.values() if c}
    return [
        f"[{mapping.dataset}] {raw.path.name}, column '{first.strip()}' appears twice with "
        f"different values: the first is used, the second (column {raw.columns.index(later) + 1}"
        f", read as '{later}') was ignored. Rename or remove one of them if the second is the "
        "right one."
        for first, later in raw.duplicate_headers
        if first in used and later not in used
    ]


def _finish(
    path: Path, df: pl.DataFrame, sn: SniffResult, header: list[str] | None = None
) -> RawTable:
    """Strip names and cells, empty → null, drop blank and repeated-header rows. `header` (the
    file's header row, None for Parquet) finds repeated header names."""
    stripped = [c.strip() for c in df.columns]
    if len(set(stripped)) == len(stripped):
        df = df.rename(dict(zip(df.columns, stripped, strict=True)))
    cols = [c for c in df.columns if c != SOURCE_ROW]
    if not cols:
        raise MappingError(
            f"{path.name}: the header row has no column; check the file or the mapping"
        )
    regex = next((j for j, c in enumerate(cols, 1) if c.startswith("^") and c.endswith("$")), None)
    if regex is not None:  # polars takes such a name for a regex selector: no column can carry it
        raise MappingError(
            f"{path.name}: header cell {regex} starts with ^ and ends with $, which polars reads "
            "as a regular expression, not as a column name; check that it is a text export, or "
            "rename the column"
        )
    df = df.with_columns(pl.col(cols).cast(pl.Utf8).str.strip_chars().replace("", None))
    blank = pl.all_horizontal(pl.col(cols).is_null())
    repeated = pl.all_horizontal(pl.col(c) == c for c in cols).fill_null(False)
    n0 = df.height
    df = df.filter(~blank & ~repeated)
    if df.height < n0:
        get_logger().info("rows_skipped", file=path.name, blank_or_repeated_header=n0 - df.height)
    df = df.with_columns(pl.col(SOURCE_ROW).cast(pl.Int64))
    return RawTable(
        path=path,
        df=df,
        sniff=sn.model_copy(update={"n_rows": df.height}),
        duplicate_headers=_differing_duplicates(path, df, header) if header else (),
    )
