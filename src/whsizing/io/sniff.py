"""F2 sniffing steps 1-6: encoding, delimiter, header row, decimal mark, date format, sheet.

`sniff_rows` works on a grid of cells (CSV lines split by the delimiter, or an Excel sheet), so
CSV and Excel share steps 3-5.
"""

from __future__ import annotations

import codecs
import csv
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import charset_normalizer
import polars as pl

from whsizing.errors import ConfigError, MappingError
from whsizing.io.parse import detect_date_format
from whsizing.logging import get_logger
from whsizing.schemas.ingest import Mapping
from whsizing.schemas.manifest import SniffResult

HEAD_BYTES = 1 << 20  # step 1: first 1 MB
DELIMITERS = (";", ",", "\t", "|")  # step 2
DELIMITER_LINES = 50
HEADER_SCAN_ROWS = 50
HEADER_MIN_CELLS = 3  # [P] step 3
HEADER_MIN_TEXT_SHARE = 0.60  # [P] step 3
DECIMAL_SAMPLE_ROWS = 2000
DECIMAL_MIN_SHARE = 0.80  # [P] step 4
DATE_MIN_SHARE = 0.50  # a column counts as a date column for the file-level date_format
YYYYMMDD_MIN_SHARE = 0.98  # [P] step 5, for an all-digit column
FALLBACK_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")  # step 1, in order
_TRUSTED = {"utf_8": "utf-8", "ascii": "utf-8", "cp1252": "cp1252"}
_NUMERIC = re.compile(r"^[-+]?[\d\s .,']+$")
_DOTTED_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")  # step 5 %d.%m.%Y: a date, not a number
_COMMA_DECIMAL = re.compile(r"^\d{1,3}(\.\d{3})*,\d+$")  # step 4, verbatim
# I54 amendment: thousands-only shapes (1.200, 1,000) are ambiguous and left out of the share;
# ungrouped (1037,5) and space / NBSP / narrow-NBSP grouped (1 200,5) comma decimals count.
# F2d fix 1: a leading 0 group (0.125, 0,250) is never thousands, so it stays in the share.
_THOUSANDS_ONLY = re.compile(r"^[1-9]\d{0,2}([.,]\d{3})+$")
_COMMA_EVIDENCE = (
    _COMMA_DECIMAL,
    re.compile(r"^\d{4,},\d+$"),
    re.compile(r"^\d{1,3}([ \u00a0\u202f]\d{3})+,\d+$"),
)
# Step 3: a date cell is a value, never a header label ('Période du;01.01.2025;au;31.12.2025')
_DATE_CELL = re.compile(
    r"^(\d{1,2}([./-])\d{1,2}\2\d{4}|\d{4}([./-])\d{1,2}\3\d{1,2})([ T]\d{1,2}:\d{2}\S*)?$"
)
_YYYYMMDD = re.compile(r"^(19|20)\d\d(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")  # step 5 %Y%m%d
WIDE_HEAD_BYTES = 4096  # BOM-less UTF-16 / UTF-32: NUL-byte pattern of the first 4 KB
WIDE_MOSTLY_NUL = 0.5  # high bytes: NUL for Latin-1, not for Ł, ż, € (F2d fix 4)
WIDE_RARELY_NUL = 0.1  # low bytes: almost never NUL in text
# Byte-order marks, UTF-32 first: BOM_UTF16_LE is a prefix of BOM_UTF32_LE.
_BOMS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".xlsb", ".ods"}


def detect_encoding(head: bytes) -> str:
    """Step 1. A byte-order mark decides (Excel 'Unicode Text' is UTF-16 with a BOM).
    charset_normalizer's verdict is kept for UTF-8 / ASCII / cp1252 and UTF-16 / UTF-32: on
    short French text it answers iso8859_14 or cp1250, which garble '°' and 'à'. Anything else
    falls back to utf-8-sig, cp1252, latin-1 (first strict decode that succeeds).
    Without a BOM, UTF-16 / UTF-32 is told by its NUL bytes (`_wide_without_bom`) first."""
    bom = next((enc for mark, enc in _BOMS if head.startswith(mark)), None)
    if bom:
        return bom  # the utf-16 / utf-32 codecs read the BOM for the byte order and drop it
    wide = _wide_without_bom(head)
    if wide and _decodes(head, wide):
        return wide
    best = charset_normalizer.from_bytes(head).best()
    guess = None
    if best is not None:
        wide = best.encoding.startswith(("utf_16", "utf_32"))
        guess = codecs.lookup(best.encoding).name if wide else _TRUSTED.get(best.encoding)
    for enc in [guess] if guess else []:
        if _decodes(head, enc):
            return enc
    for enc in FALLBACK_ENCODINGS:
        if _decodes(head, enc):
            return "utf-8" if enc == "utf-8-sig" else enc
    return "latin-1"  # unreachable: latin-1 decodes any byte


def _wide_without_bom(head: bytes) -> str | None:
    """UTF-16 / UTF-32 without a BOM (F2d: charset_normalizer gives no verdict on a short
    tab-separated 'Unicode Text' export, which then read as cp1252 full of NULs). Mostly-Latin
    text (Polish included) has NUL high bytes at fixed offsets, which give the width and the byte
    order; text in an 8-bit encoding has no NUL byte at all. ponytail: Greek / Cyrillic / CJK
    UTF-16 has few NULs and is left to charset_normalizer. Endian-explicit names: no BOM tells
    the codec the order."""
    s = head[:WIDE_HEAD_BYTES]
    s = s[: len(s) // 4 * 4]
    if not s or 0 not in s:
        return None

    def mostly_nul(offset: int, step: int) -> bool:
        return s[offset::step].count(0) / len(s[offset::step]) >= WIDE_MOSTLY_NUL

    def rarely_nul(offset: int, step: int) -> bool:
        return s[offset::step].count(0) / len(s[offset::step]) < WIDE_RARELY_NUL

    if mostly_nul(2, 4) and mostly_nul(3, 4) and rarely_nul(0, 4):
        return "utf-32-le"
    if mostly_nul(0, 4) and mostly_nul(1, 4) and rarely_nul(3, 4):
        return "utf-32-be"
    if mostly_nul(1, 2) and rarely_nul(0, 2):
        return "utf-16-le"
    if mostly_nul(0, 2) and rarely_nul(1, 2):
        return "utf-16-be"
    return None


def _decodes(head: bytes, enc: str) -> bool:
    try:
        head.decode(enc)
    except UnicodeDecodeError as e:
        # a UTF-8 character cut by the 1 MB window is not an error
        return enc.startswith("utf") and len(head) == HEAD_BYTES and e.start >= len(head) - 3
    return True


def _fields(line: str, delimiter: str) -> list[str]:
    return next(csv.reader([line], delimiter=delimiter), [])


def detect_delimiter(lines: list[str]) -> str:
    """Step 2: per candidate, the field count on the first 50 non-empty lines (quotes respected);
    the most consistent count wins (ties: more fields, then list order); else csv.Sniffer."""
    sample = [ln for ln in lines if ln.strip()][:DELIMITER_LINES]
    best: tuple[float, int, str] | None = None
    for d in DELIMITERS:
        counts = [len(_fields(ln, d)) - 1 for ln in sample]
        if not counts:
            break
        mode, n = Counter(counts).most_common(1)[0]
        key = (n / len(counts), mode, d)
        if mode > 0 and (best is None or key[:2] > best[:2]):
            best = key
    if best is not None:
        return best[2]
    try:
        return csv.Sniffer().sniff("\n".join(sample)).delimiter
    except csv.Error:
        return ","  # single-column file


def is_numeric_text(cell: str) -> bool:
    """A number in either convention; '01.03.2025' is a date (F2c: it diluted the decimal
    share of step 4 and hid the column from the file date format of step 5)."""
    s = cell.strip()
    return bool(_NUMERIC.match(s)) and any(c.isdigit() for c in s) and not _DOTTED_DATE.match(s)


def _is_label(cell: str) -> bool:
    """Step 3 text cell: neither a number nor a date (F2d: the dotted dates of a 'Période du;
    01.01.2025;au;31.12.2025' preamble counted as text, so it was taken as the header)."""
    return not is_numeric_text(cell) and not _DATE_CELL.match(cell.strip())


def _first_header(rows: list[list[str]], is_text: Callable[[str], bool]) -> int | None:
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        cells = [c for c in row if c and c.strip()]
        n = len(cells)
        if n >= HEADER_MIN_CELLS and sum(map(is_text, cells)) / n >= HEADER_MIN_TEXT_SHARE:
            return i
    return None


def detect_header_row(rows: list[list[str]]) -> int:
    """Step 3: 0-based index of the first row with ≥ 3 non-empty cells, ≥ 60 % text labels.
    Dates are values first (`_is_label`, I67); the verbatim rule (non-numeric is text) decides
    when no row qualifies, or when an earlier row qualifies only verbatim (its dates are
    labels: a pivoted header 'Référence;Désignation;01/01/2025;01/02/2025') and the
    date-aware pick holds a number: a sparse or text-heavy data row 'A1;Vis;;;7' below
    the pivot (F2e), whereas a real header below a date-range preamble holds none.
    ponytail: a header with a bare-number label below a preamble ('Réf;Qté;2025') goes to
    the preamble row; a pivot data row with no number at all still wins."""
    dated = _first_header(rows, _is_label)
    verbatim = _first_header(rows, lambda c: not is_numeric_text(c))
    if dated is not None and verbatim is not None and verbatim < dated:
        dated = None if any(map(is_numeric_text, rows[dated])) else dated
    i = dated if dated is not None else verbatim
    if i is None:
        raise MappingError(
            f"no header row found in the first {HEADER_SCAN_ROWS} rows (needs ≥ "
            f"{HEADER_MIN_CELLS} non-empty cells, mostly text); check the file or the delimiter"
        )
    if i:
        get_logger().info("header_rows_skipped", rows=i)  # C2: counts, never cell content
    return i


def _columns(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(r) for r in rows), default=0)
    return [[r[j].strip() for r in rows if j < len(r) and r[j].strip()] for j in range(width)]


def detect_decimal(columns: list[list[str]], delimiter: str | None = None) -> str:
    """Step 4, once per file (I54 as amended, F2d): ',' when ≥ 80 % [P] of the sampled
    separator-bearing values of numeric columns are comma decimals (the verbatim regex 1.234,5,
    or 1037,5, or 1 200,5), else '.'. Left out: plain integers, '%d.%m.%Y' dates and
    thousands-only shapes (1.200, 1,000: FR or US thousands, or 3 decimals; not 0.125, which is
    a decimal and counts as dot evidence). Nothing left
    (integer-only files): ';' files are FR Excel exports → ',', any other delimiter (or Excel,
    `delimiter` None) → '.'. A saved mapping's `decimal` overrides this (Appendix E)."""
    values = _decimal_evidence(columns)
    if not values:
        return "," if delimiter == ";" else "."
    share = sum(any(r.match(v) for r in _COMMA_EVIDENCE) for v in values) / len(values)
    return "," if share >= DECIMAL_MIN_SHARE else "."


def _decimal_evidence(columns: list[list[str]]) -> list[str]:
    """Step 4 share values: separator-bearing cells of numeric columns, thousands-only shapes
    left out (I54). Empty → the field delimiter decides the mark (tie-break)."""
    numeric = [[v.lstrip("-+") for v in c if is_numeric_text(v)] for c in columns]
    numeric = [n for n, c in zip(numeric, columns, strict=True) if n and len(n) >= 0.8 * len(c)]
    return [
        v for n in numeric for v in n if ("," in v or "." in v) and not _THOUSANDS_ONLY.match(v)
    ]


def detect_file_date_format(columns: list[list[str]]) -> str | None:
    """Step 5 for the file summary: format of the first column that reads as dates; else of the
    first all-digit column that reads as %Y%m%d (≥ 98 % [P]). ponytail: Excel-serial columns
    are not named here, 5-digit integers 20000-60000 are indistinguishable from quantities at
    this level; per-column parsing (`mapping._typed`) still reads them."""
    for col in columns:
        if col and not all(is_numeric_text(v) for v in col):
            fmt, share = detect_date_format(pl.Series(col, dtype=pl.Utf8))
            if fmt and share >= DATE_MIN_SHARE:
                return fmt
    for col in columns:
        if col and sum(bool(_YYYYMMDD.match(v)) for v in col) >= YYYYMMDD_MIN_SHARE * len(col):
            return "%Y%m%d"
    return None


def sniff_rows(
    rows: list[list[str]], header_row: int | None = None, delimiter: str | None = None
) -> tuple[int, str, str | None, bool]:
    """Steps 3-5 on a grid → (0-based header index, decimal mark, date format, mark chosen by
    the field delimiter). `header_row` (1-based, from a saved mapping) skips step 3;
    `delimiter` (None: Excel, no delimiter to decide) breaks step 4 ties."""
    header = header_row - 1 if header_row else detect_header_row(rows)
    data = _columns(rows[header + 1 : header + 1 + DECIMAL_SAMPLE_ROWS])
    by_delimiter = delimiter is not None and not _decimal_evidence(data)
    return header, detect_decimal(data, delimiter), detect_file_date_format(data), by_delimiter


def split_lines(text: str) -> list[str]:
    """CRLF, LF and CR-only line ends; the reader cuts the file on the same lines."""
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def saved_sniff(mapping: Mapping | None) -> dict[str, Any]:
    """Sniff values recorded in a saved mapping (Appendix E, step 7): they win over detection,
    so a hand-corrected `decimal`, `header_row`, ... fixes a mis-sniffed file."""
    if mapping is None:
        return {}
    keys = ("encoding", "delimiter", "header_row", "decimal", "date_format")
    fixed = {k: v for k in keys if (v := getattr(mapping, k)) is not None}
    if fixed.get("encoding") == "binary":  # recorded from an Excel / Parquet file
        del fixed["encoding"]
    try:
        codecs.lookup(fixed.get("encoding", "utf-8"))
        ok = fixed.get("decimal", ".") in (".", ",") and fixed.get("header_row", 1) >= 1
        ok = ok and len(fixed.get("delimiter", ";").encode("utf-8")) == 1  # one byte (polars)
    except LookupError:
        ok = False
    if not ok:
        raise ConfigError(
            f"mapping/{mapping.dataset}.yaml: invalid value in {fixed} (decimal '.' or ',', "
            "one-byte delimiter, header_row ≥ 1, encoding a Python codec name)"
        )
    return fixed


def _head_lines(path: Path, encoding: str | None) -> tuple[str, list[str]]:
    with path.open("rb") as f:
        head = f.read(HEAD_BYTES)
        more = bool(f.read(1))
    encoding = encoding or detect_encoding(head)
    lines = split_lines(head.decode(encoding, errors="replace"))
    return encoding, lines[:-1] if more and len(lines) > 1 else lines


def sniff_csv(path: Path, mapping: Mapping | None = None) -> SniffResult:
    """Steps 1-5; values recorded in `mapping` are used as given instead of detected."""
    fixed = saved_sniff(mapping)
    encoding, lines = _head_lines(path, fixed.get("encoding"))
    delimiter = fixed.get("delimiter") or detect_delimiter(lines)
    if len(delimiter.encode("utf-8")) != 1:  # polars wants one byte: a garbage or binary file
        raise MappingError(
            f"{path.name}: not a readable CSV (sniffed delimiter {delimiter!r} is not a "
            "single-byte character); check that it is a text export, or set `delimiter:` in the "
            "mapping"
        )
    rows = [_fields(ln, delimiter) for ln in lines[: HEADER_SCAN_ROWS + DECIMAL_SAMPLE_ROWS]]
    try:
        header, decimal, date_format, by_delimiter = sniff_rows(
            rows, fixed.get("header_row"), delimiter
        )
    except MappingError as e:  # "no header row found": say which file (several per dataset)
        raise MappingError(f"{path.name}: {e}") from e
    with path.open("rb") as f:
        n_lines = sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(HEAD_BYTES), b""))
    sn = SniffResult(
        encoding=encoding,
        delimiter=delimiter,
        header_row=header + 1,
        decimal=decimal,
        date_format=date_format,
        n_rows=max(0, n_lines - header - 1),
        decimal_by_delimiter=by_delimiter and "decimal" not in fixed,
    )
    return sn.model_copy(update={k: fixed[k] for k in ("decimal", "date_format") if k in fixed})


def sniff(path: Path, sheet: str | int | None = None) -> SniffResult:
    """Encoding, delimiter, header row (1-based), decimal, date format and row count."""
    from whsizing.io.readers import read_any  # Excel/Parquet sniffing needs the loaded grid

    path = Path(path)
    if path.suffix.lower() in EXCEL_SUFFIXES or path.suffix.lower() == ".parquet":
        return read_any(path, sheet).sniff
    return sniff_csv(path)
