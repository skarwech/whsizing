"""Typed parsing of raw string columns: numbers, integers, booleans, dates (F2 sniff steps 4-5).

Every parser is a Polars expression on a Utf8 column; unparseable values become null (counted
later by the R-rules). Dates: the best format first, then every other candidate, coalesced, so a
file mixing formats still parses; naive values are local wall time in `tz`, output is UTC (µs).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import polars as pl

from whsizing.logging import get_logger

# Sniff step 5 order: ISO 8601, %d/%m/%Y[ %H:%M[:%S]], %d.%m.%Y, %d-%m-%Y, %Y%m%d, Excel serial.
# Time variants are listed next to their date format; `_AWARE` formats carry an offset.
_AWARE = ("%Y-%m-%dT%H:%M:%S%.f%#z", "%Y-%m-%d %H:%M:%S%.f%#z")
DATE_FORMATS: tuple[str, ...] = (
    *_AWARE,
    "%Y-%m-%dT%H:%M:%S%.f",
    "%Y-%m-%d %H:%M:%S%.f",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%Y%m%d",
)
EXCEL_SERIAL = "excel_serial"  # numeric 20000–60000, days since 1899-12-30
DATE_SAMPLE_ROWS = 2000
DATE_MIN_SHARE = 0.98  # [P] sniff step 5
_SPACES = r"[\s  ']"  # blanks, NBSP, narrow NBSP, Swiss apostrophe
MIN_YEAR = 1900  # below: a misread, e.g. '01/01/24' taken by %Y as year 24 → null (R1 counts it)
_TRUE = ["1", "true", "yes", "y", "oui", "o", "x", "vrai"]
_FALSE = ["0", "false", "no", "n", "non", "faux"]


def number_shape(decimal: str) -> str:
    """Regex of a valid number for the file's decimal mark: digits, optionally grouped by 3
    with the other mark (1.234,5 / 1,234.5; never after a leading 0: '0.125' is no thousands),
    optional fraction and exponent."""
    d, g = (",", r"\.") if decimal == "," else (r"\.", ",")
    return rf"^[-+]?(\d+|[1-9]\d{{0,2}}({g}\d{{3}})+)?({d}\d*)?([eE][-+]?\d+)?$"


def parse_number(col: pl.Expr, decimal: str) -> pl.Expr:
    """Float64 with the file's decimal mark (sniff step 4, or the mapping's `decimal`). The
    other mark is only a thousands separator between groups of 3 digits: text of any other
    shape ('0,25' in a decimal-dot file) is null, never silently 25."""
    s = col.str.replace_all(_SPACES, "")
    group = "." if decimal == "," else ","
    num = s.str.replace_all(group, "", literal=True).str.replace(decimal, ".", literal=True)
    x = pl.when(s.str.contains(number_shape(decimal))).then(num).cast(pl.Float64, strict=False)
    return pl.when(x.is_finite()).then(x)  # NaN, inf ('1e400') → null


def parse_int(col: pl.Expr, decimal: str) -> pl.Expr:
    """Int64 with the file's decimal mark; non-integral values and values outside Int64
    ('1e20') become null."""
    x = parse_number(col, decimal)
    return pl.when(x == x.round(0)).then(x).cast(pl.Int64, strict=False)


def parse_bool(col: pl.Expr) -> pl.Expr:
    s = col.str.to_lowercase()
    return pl.when(s.is_in(_TRUE)).then(True).when(s.is_in(_FALSE)).then(False).otherwise(None)


def _one_format(col: pl.Expr, fmt: str, tz: str) -> pl.Expr:
    """`col` parsed with one format → Datetime(us, UTC); naive values are wall time in `tz`."""
    if fmt == EXCEL_SERIAL:
        days = col.cast(pl.Float64, strict=False)
        days = pl.when((days >= 20000) & (days <= 60000)).then(days)
        us = (days * 86_400_000_000).round(0).cast(pl.Int64)
        local = pl.datetime(1899, 12, 30, time_unit="us") + pl.duration(microseconds=us)
    else:
        local = col.str.to_datetime(fmt, strict=False, time_unit="us")
        local = pl.when(local.dt.year() >= MIN_YEAR).then(local)
        if re.search(r"%[#:]?[zZ]", fmt):  # an offset or zone directive: aware values
            return local.dt.convert_time_zone("UTC")
    return _local_to_utc(local, tz)


def _local_to_utc(local: pl.Expr, tz: str) -> pl.Expr:
    """Wall time → UTC. Ambiguous (autumn) → earliest; non-existent (spring gap) → +1 h."""

    def zoned(e: pl.Expr) -> pl.Expr:
        return e.dt.replace_time_zone(tz, ambiguous="earliest", non_existent="null")

    utc = pl.coalesce(zoned(local), zoned(local + pl.duration(hours=1)))
    return utc.dt.convert_time_zone("UTC")


def detect_date_format(values: pl.Series) -> tuple[str | None, float]:
    """Best format on a ≤ 2,000-value sample: the first reaching 98 % [P], else the best share."""
    sample = values.drop_nulls().head(DATE_SAMPLE_ROWS)
    if sample.len() == 0:
        return None, 0.0
    best: tuple[str | None, float] = (None, 0.0)
    for fmt in (*DATE_FORMATS, EXCEL_SERIAL):
        share = sample.to_frame("v").select(
            _one_format(pl.col("v"), fmt, "UTC").is_not_null().mean()
        )
        share = float(share.item() or 0.0)
        if share >= DATE_MIN_SHARE:
            _warn_if_ambiguous(sample, fmt)
            return fmt, share
        if share > best[1]:
            best = (fmt, share)
    return best


def _warn_if_ambiguous(sample: pl.Series, fmt: str) -> None:
    """Day and month both ≤ 12 on every sampled value: dd/mm is assumed (FR), logged."""
    if not fmt.startswith("%d"):
        return
    parsed = sample.to_frame("v").select(pl.col("v").str.to_datetime(fmt, strict=False)).to_series()
    day_max = parsed.dt.day().max()
    if isinstance(day_max, int) and day_max <= 12:
        get_logger().warning("date_day_month_ambiguous", format=fmt, assumed="dd/mm")


def parse_datetime(col: pl.Expr, tz: str, first: str | None = None) -> pl.Expr:
    """Datetime(us, UTC): `first` format, then every other candidate, coalesced."""
    order: Sequence[str] = [first] if first else []
    order = [*order, *(f for f in (*DATE_FORMATS, EXCEL_SERIAL) if f != first)]
    return pl.coalesce([_one_format(col, f, tz) for f in order])


def parse_date(col: pl.Expr, tz: str, first: str | None = None) -> pl.Expr:
    """Local calendar date in `tz`."""
    return parse_datetime(col, tz, first).dt.convert_time_zone(tz).dt.date()


def looks_numeric(values: pl.Series, decimal: str) -> float:
    """Share of non-null values that parse as a number."""
    v = values.drop_nulls()
    if v.len() == 0:
        return 0.0
    parsed = v.to_frame("v").select(parse_number(pl.col("v"), decimal)).to_series()
    return 1 - parsed.null_count() / v.len()
