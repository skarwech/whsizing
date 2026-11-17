"""F2 validation rules R1-R14 (§4.3): Polars expressions on eager frames → RuleResult.

`apply_rules` returns the cleaned frames (each rule's action applied) and one RuleResult per
(rule, dataset), "ok" when nothing fired, so the DQ report is a complete checklist. REQ is an F2
addition: a row whose required §4.1 value is missing or out of range (negative stock, receipt
quantity ≤ 0) cannot enter the canonical table and is dropped, counted as a warning; a negative
receipt `pallets` (optional, ≥ 0) is cleared instead, so it is derived from units_per_pallet.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from math import ceil

import polars as pl
from dateutil.relativedelta import relativedelta

from whsizing.schemas.ingest import RuleResult, Severity
from whsizing.schemas.params import DatasetKind

CanonicalFrames = dict[str, pl.DataFrame]

SAMPLE_ROWS = 5
OUTLIER_SAMPLE_ROWS = 20
R1_BLOCKING_SHARE = 0.01  # [P]
# [P] I83: a gap of more than 90 days among the earliest dates (at most 5 % of the distinct
# dates, never fewer than 3) separates junk dates from the history
R1_EARLY_MARGIN_DAYS = 90
R1_EARLY_MAX_DATE_SHARE = 0.05
R1_EARLY_MIN_DATES = 3
R2_WARNING_SHARE = 0.01  # [P]
R2_BLOCKING_SHARE = 0.05  # [P]
R7_MIN_LINE_COVERAGE = 0.95  # [P]
DIM_RANGE_MM = (1.0, 3000.0)  # [P] R8 / §4.1: plausible when 1 mm ≤ x < 3,000 mm
WEIGHT_RANGE_KG = (0.001, 1500.0)  # [P] R8 / §4.1: 1 g ≤ x < 1,500 kg
R9_MIN_MONTHS = 3  # [P]
R10_MIN_MONTHS = 12  # [P]
R11_MULTIPLE_SHARE = 0.90  # [P]
R12_MAX_ZERO_DAY_SHARE = 0.05  # [P]
OPERATING_WEEKDAY_SHARE = (
    0.5  # F2 choice: a weekday is "operating" if it has orders ≥ 50 % of weeks
)
R13_MAD_K = 10  # [P]
R13_MAD_FLOOR = 1  # [EXPERT] registered interpretation (F2c): MAD floored at 1 unit
R14_MAX_AGE_MONTHS = 6  # [P]
DIMS = ("length_mm", "width_mm", "height_mm")
NON_KEY = ("source_file", "source_row", "has_dims", "is_return")  # provenance / derived
REQUIRED: dict[str, tuple[str, ...]] = {
    "order_lines": ("order_id", "sku", "qty_units"),  # order_ts is R1
    "sku_master": ("sku",),
    "inventory": ("sku", "qty_units", "snapshot_date"),
    "receipts": ("receipt_id", "receipt_ts", "sku", "qty_units"),
}
RANGE_OK = {"inventory": pl.col("qty_units") >= 0, "receipts": pl.col("qty_units") > 0}
RULE_ORDER = ["REQ", *(f"R{i}" for i in range(1, 15))]
R6_KEY = ["order_id", "sku", "line_status", "is_return"]  # a return is never summed into a sale


def _res(
    rule: str,
    ds: DatasetKind,
    severity: Severity,
    count: int,
    n: int,
    message: str,
    *,
    dropped: int = 0,
    sample: pl.DataFrame | None = None,
    sample_rows: int = SAMPLE_ROWS,
) -> RuleResult:
    rows = [] if sample is None else sample.head(sample_rows).to_dicts()
    return RuleResult(
        rule=rule,
        dataset=ds,
        severity=severity,
        count=count,
        share=round(count / n, 6) if n else 0.0,
        dropped=dropped,
        message=message,
        sample_rows=[{k: None if v is None else str(v) for k, v in r.items()} for r in rows],
    )


def _split(df: pl.DataFrame, bad: pl.Expr) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(kept, removed); a null condition keeps the row."""
    flag = bad.fill_null(False)
    return df.filter(~flag), df.filter(flag)


def _req(ds: DatasetKind, df: pl.DataFrame) -> tuple[pl.DataFrame, RuleResult]:
    bad = pl.any_horizontal([pl.col(c).is_null() for c in REQUIRED[ds] if c in df.columns])
    if ds in RANGE_OK:
        bad = bad | ~RANGE_OK[ds]
    kept, hit = _split(df, bad)
    msg = f"{hit.height} rows with a required value missing, unreadable or out of range removed"
    cleared = pl.DataFrame()
    if ds == "receipts" and "pallets" in kept.columns:
        negative = (pl.col("pallets") < 0).fill_null(False)
        cleared = kept.filter(negative)
        kept = kept.with_columns(pallets=pl.when(negative).then(None).otherwise(pl.col("pallets")))
        msg += f"; {cleared.height} negative pallet counts cleared (derived from units per pallet)"
    n = hit.height + cleared.height
    sample = pl.concat([hit, cleared]) if cleared.height else hit
    sev: Severity = "warning" if n else "ok"
    return kept, _res("REQ", ds, sev, n, df.height, msg, dropped=hit.height, sample=sample)


def _earliest_plausible(dates: pl.Series) -> date | None:
    """I83: the first local order date of the history proper; None without dates. Junk dates
    (1970-01-01 from an epoch default, 1900-01-01, a typo year) sit far before the history,
    alone or in a handful. So: among the earliest max(3, 5 %) distinct dates, the last gap of
    more than 90 days splits them from the rest, and the dates before the gap are implausible.
    Distinct dates, not lines: a default-epoch export puts many lines on ONE junk date. A real
    start without such a gap, or a real early block of more than 5 % of the distinct dates
    before a long closure (a season), is never cut. The bound is recomputed on the dates it
    keeps until stable, so a pile of junk dates larger than the cap is shed in turns.
    ponytail: a junk cluster above 5 % of the distinct dates AND isolated by more than 90 days
    looks like a real earlier period and stays, R9 / R12 show it; upgrade is a per-client
    `history_start` input."""
    days = dates.drop_nulls().unique().sort().to_list()
    margin = timedelta(days=R1_EARLY_MARGIN_DAYS)
    while days:
        cap = max(R1_EARLY_MIN_DATES, ceil(R1_EARLY_MAX_DATE_SHARE * len(days)))
        cuts = [i for i in range(1, min(cap, len(days) - 1) + 1) if days[i] - days[i - 1] > margin]
        if not cuts:
            return days[0]
        days = days[cuts[-1] :]
    return None


def _r1(df: pl.DataFrame, now: datetime, tz: str) -> tuple[pl.DataFrame, RuleResult]:
    """Null / unparseable, future and (I83) implausibly early dates: dropped and counted. The
    early dates are those before the first date of the history proper (`_earliest_plausible`), so
    a 1970-01-01 line (or thirty) cannot stretch the history that R9, R10, R12 and the calendar
    are computed on."""
    future = pl.col("order_ts") > now
    unusable = pl.col("order_ts").is_null() | future
    lo = _earliest_plausible(local_dates(df.filter(~unusable.fill_null(False)), tz))
    local = pl.col("order_ts").dt.convert_time_zone(tz).dt.date()
    early = pl.lit(False) if lo is None else local < lo
    kept, hit = _split(df, unusable | early)
    n_future = hit.filter(future.fill_null(False)).height
    n_early = hit.filter(early.fill_null(False)).height
    share = hit.height / df.height if df.height else 0.0
    sev: Severity = "blocking" if share > R1_BLOCKING_SHARE else "warning" if hit.height else "ok"
    msg = (
        f"{hit.height - n_future - n_early} lines without a readable date, "
        f"{n_future} dated in the future"
    )
    if n_early:
        msg += (
            f", {n_early} dated before {lo} (implausible: more than {R1_EARLY_MARGIN_DAYS} days "
            "before the rest of the history)"
        )
    return kept, _res(
        "R1", "order_lines", sev, hit.height, df.height, msg, dropped=hit.height, sample=hit
    )


def _r5(ds: DatasetKind, df: pl.DataFrame) -> tuple[pl.DataFrame, RuleResult]:
    keys = [c for c in df.columns if c not in NON_KEY]
    first = pl.struct(keys).is_first_distinct()
    kept, hit = df.filter(first), df.filter(~first)
    msg = f"{hit.height} exact duplicate rows removed (across files too)"
    if ds == "sku_master":  # a SKU listed twice with different data: first row kept
        dup_key = ~pl.col("sku").is_first_distinct()
        repeated = kept.filter(dup_key)
        hit, kept = pl.concat([hit, repeated]), kept.filter(~dup_key)
        msg += f"; {repeated.height} repeated SKUs (first row kept)"
    sev: Severity = "warning" if hit.height else "ok"
    return kept, _res("R5", ds, sev, hit.height, df.height, msg, dropped=hit.height, sample=hit)


def _r6(df: pl.DataFrame, merge: bool) -> tuple[pl.DataFrame, RuleResult]:
    """After R3/R4: lines of one (order, SKU) with the same status and direction are merged."""
    dup = pl.len().over(R6_KEY) > 1
    hit = df.filter(dup)
    if not hit.height or not merge:
        sev: Severity = "info" if hit.height else "ok"
        msg = f"{hit.height} lines repeat an (order, SKU) pair; kept as separate lines"
        return df, _res("R6", "order_lines", sev, hit.height, df.height, msg, sample=hit)
    others = [c for c in df.columns if c not in (*R6_KEY, "qty_units")]
    merged = (
        df.group_by(R6_KEY, maintain_order=True)
        .agg(pl.col("qty_units").sum(), pl.col(others).first())
        .select(df.columns)
    )
    dropped = df.height - merged.height
    msg = f"{hit.height} lines repeat an (order, SKU) pair; merged into {hit.height - dropped}"
    res = _res("R6", "order_lines", "info", hit.height, df.height, msg, dropped=dropped, sample=hit)
    return merged, res


def _r3_r4(df: pl.DataFrame) -> tuple[pl.DataFrame, list[RuleResult]]:
    kept, zero = _split(df, pl.col("qty_units") == 0)
    sev3: Severity = "warning" if zero.height else "ok"
    r3 = _res(
        "R3",
        "order_lines",
        sev3,
        zero.height,
        df.height,
        f"{zero.height} lines with quantity 0 removed",
        dropped=zero.height,
        sample=zero,
    )
    neg = kept.filter(pl.col("qty_units") < 0)
    sev4: Severity = "info" if neg.height else "ok"
    r4 = _res(
        "R4",
        "order_lines",
        sev4,
        neg.height,
        kept.height,
        f"{neg.height} negative lines treated as returns",
        sample=neg,
    )
    is_return = (pl.col("qty_units") < 0) | (pl.col("line_status") == "returned").fill_null(False)
    return kept.with_columns(is_return=is_return), [r3, r4]


def _complete() -> pl.Expr:
    return pl.all_horizontal([pl.col(c).is_not_null() for c in (*DIMS, "weight_kg")])


def _r2(lines: pl.DataFrame, master: pl.DataFrame | None) -> tuple[pl.DataFrame, RuleResult]:
    if master is None:
        msg = "not evaluated: no SKU master ingested yet"
        res = _res("R2", "order_lines", "info", 0, lines.height, msg)
        return lines.with_columns(has_dims=pl.lit(False)), res
    with_dims = master.filter(_complete())["sku"].implode()
    absent = lines.filter(~pl.col("sku").is_in(master["sku"].implode()))
    share = absent.height / lines.height if lines.height else 0.0
    sev: Severity = (
        "blocking"
        if share > R2_BLOCKING_SHARE
        else "warning"
        if share > R2_WARNING_SHARE
        else "info"
        if absent.height
        else "ok"
    )
    msg = f"{absent.height} lines ({share:.1%}) order a SKU missing from the master; kept"
    res = _res("R2", "order_lines", sev, absent.height, lines.height, msg, sample=absent)
    return lines.with_columns(has_dims=pl.col("sku").is_in(with_dims)), res


def _r8(master: pl.DataFrame) -> tuple[pl.DataFrame, RuleResult]:
    """Implausible dims / weight (and pack quantities < 1) → null."""
    bounds = {c: DIM_RANGE_MM for c in DIMS} | {"weight_kg": WEIGHT_RANGE_KG}
    bad = {
        c: pl.col(c).is_not_null() & ~pl.col(c).is_between(lo, hi, closed="left")
        for c, (lo, hi) in bounds.items()
    }
    bad |= {c: pl.col(c) < 1 for c in ("units_per_case", "cases_per_pallet") if c in master.columns}
    hit = master.filter(pl.any_horizontal(list(bad.values())).fill_null(False))
    cleaned = master.with_columns(
        pl.when(b.fill_null(False)).then(None).otherwise(pl.col(c)).alias(c) for c, b in bad.items()
    )
    sev: Severity = "warning" if hit.height else "ok"
    msg = f"{hit.height} SKUs with an implausible dimension, weight or pack quantity; value cleared"
    return cleaned, _res("R8", "sku_master", sev, hit.height, master.height, msg, sample=hit)


def _r7(master: pl.DataFrame | None, lines: pl.DataFrame | None) -> RuleResult:
    if master is None:
        if lines is None:
            return _res("R7", "sku_master", "info", 0, 0, "not evaluated: no SKU master")
        msg = "no SKU master: dimensions and weight unknown for every line"
        return _res("R7", "sku_master", "warning", lines.height, lines.height, msg)
    missing = master.filter(~_complete())
    coverage = 1 - missing.height / master.height if master.height else 0.0
    scope = "SKUs"
    if lines is not None and "has_dims" in lines.columns and lines.height:
        coverage, scope = float(lines["has_dims"].mean() or 0.0), "order lines"  # pyright: ignore[reportArgumentType]
    sev: Severity = (
        "warning" if coverage < R7_MIN_LINE_COVERAGE else "info" if missing.height else "ok"
    )
    msg = (
        f"{missing.height} SKUs lack a dimension or the weight; coverage {coverage:.1%} of {scope}"
    )
    return _res("R7", "sku_master", sev, missing.height, master.height, msg, sample=missing)


def local_dates(lines: pl.DataFrame, tz: str) -> pl.Series:
    return lines.select(pl.col("order_ts").dt.convert_time_zone(tz).dt.date()).to_series()


def _shorter(first: date, last: date, months: int) -> bool:
    return last + timedelta(days=1) < first + relativedelta(months=months)


def history_months(first: date, last: date) -> float:
    return round(((last - first).days + 1) / 30.4375, 2)


def _r9_r10(lines: pl.DataFrame, tz: str) -> list[RuleResult]:
    if not lines.height:
        msg = "no usable order lines"
        return [
            _res("R9", "order_lines", "blocking", 0, 0, msg),
            _res("R10", "order_lines", "warning", 0, 0, msg),
        ]
    d = local_dates(lines, tz)
    first, last = d.min(), d.max()
    assert isinstance(first, date) and isinstance(last, date)
    span = f"history {first} → {last} ({history_months(first, last)} months)"
    s9: Severity = "blocking" if _shorter(first, last, R9_MIN_MONTHS) else "ok"
    s10: Severity = "warning" if _shorter(first, last, R10_MIN_MONTHS) else "ok"
    return [
        _res(
            "R9",
            "order_lines",
            s9,
            int(s9 != "ok"),
            1,
            f"{span}; at least {R9_MIN_MONTHS} months needed",
        ),
        _res(
            "R10",
            "order_lines",
            s10,
            int(s10 != "ok"),
            1,
            f"{span}; seasonality confidence L below {R10_MIN_MONTHS} months",
        ),
    ]


def _r11(ds: DatasetKind, df: pl.DataFrame, master: pl.DataFrame | None) -> RuleResult:
    if master is None or "units_per_case" not in master.columns:
        return _res("R11", ds, "info", 0, 0, "not evaluated: no case quantities in the SKU master")
    cases = master.select("sku", "units_per_case").filter(pl.col("units_per_case") > 1)
    j = df.filter(pl.col("qty_units") != 0).join(cases, on="sku", how="inner")
    hit = j.filter(pl.col("qty_units").abs() % pl.col("units_per_case") == 0)
    share = hit.height / j.height if j.height else 0.0
    sev: Severity = "warning" if share > R11_MULTIPLE_SHARE else "ok"
    msg = (
        f"{share:.1%} of quantities (SKUs with a case > 1) are whole cases: "
        "confirm they are units, not cases"
    )
    return _res("R11", ds, sev, hit.height, j.height, msg, sample=hit if sev != "ok" else None)


def _r12(lines: pl.DataFrame, tz: str) -> RuleResult:
    days = local_dates(lines, tz).unique()
    first, last = days.min(), days.max()
    assert isinstance(first, date) and isinstance(last, date)
    cal = pl.DataFrame({"date": pl.date_range(first, last, "1d", eager=True)}).with_columns(
        has_orders=pl.col("date").is_in(days.implode()), weekday=pl.col("date").dt.weekday()
    )
    rate = cal.group_by("weekday").agg(pl.col("has_orders").mean())
    operating = rate.filter(pl.col("has_orders") >= OPERATING_WEEKDAY_SHARE)["weekday"]
    expected = cal.filter(pl.col("weekday").is_in(operating.implode()))
    zero = expected.filter(~pl.col("has_orders"))
    share = zero.height / expected.height if expected.height else 0.0
    sev: Severity = "warning" if share > R12_MAX_ZERO_DAY_SHARE else "ok"
    msg = f"{zero.height} usual operating days ({share:.1%}) without any order: review the calendar"
    return _res(
        "R12", "order_lines", sev, zero.height, expected.height, msg, sample=zero.select("date")
    )


def outlier_threshold(x: pl.Series) -> float:
    """median + 10 × max(MAD, 1) [P]; the floor (registered interpretation, [EXPERT]) keeps
    a MAD of 0 (most lines of 1 unit, most orders of 1 line) from listing every value above
    the median."""
    med = float(x.median() or 0.0)  # pyright: ignore[reportArgumentType]
    mad = float((x - med).abs().median() or 0.0)  # pyright: ignore[reportArgumentType]
    return med + R13_MAD_K * max(mad, R13_MAD_FLOOR)


def _r13(lines: pl.DataFrame) -> RuleResult:
    out = lines.filter(pl.col("qty_units") > 0)
    if not out.height:
        return _res("R13", "order_lines", "ok", 0, 0, "no outbound lines")
    per_order = out.group_by("order_id").agg(lines_in_order=pl.len())
    big_orders = per_order.filter(
        pl.col("lines_in_order") > outlier_threshold(per_order["lines_in_order"])
    )
    big_lines = out.filter(pl.col("qty_units") > outlier_threshold(out["qty_units"]))
    count = big_orders.height + big_lines.height
    sample = pl.concat(
        [
            big_orders.sort("lines_in_order", descending=True).head(10),
            big_lines.sort("qty_units", descending=True).head(10),
        ],
        how="diagonal_relaxed",
    )
    sev: Severity = "warning" if count else "ok"
    msg = (
        f"{big_orders.height} orders with unusually many lines, {big_lines.height} lines with "
        "unusually many units (listed, kept)"
    )
    return _res(
        "R13",
        "order_lines",
        sev,
        count,
        out.height,
        msg,
        sample=sample,
        sample_rows=OUTLIER_SAMPLE_ROWS,
    )


def _r14(
    inv: pl.DataFrame | None, lines: pl.DataFrame | None, now: datetime, tz: str
) -> RuleResult:
    if inv is None or not inv.height:
        return _res(
            "R14", "inventory", "warning", 0, 0, "no stock snapshot: stock statistics confidence L"
        )
    latest = inv["snapshot_date"].max()
    assert isinstance(latest, date)
    ref = now.date()
    if lines is not None and lines.height:
        last = local_dates(lines, tz).max()
        ref = last if isinstance(last, date) else ref
    old = latest < ref - relativedelta(months=R14_MAX_AGE_MONTHS)
    sev: Severity = "warning" if old else "ok"
    msg = (
        f"latest stock snapshot {latest} (reference {ref}); older than {R14_MAX_AGE_MONTHS} "
        "months → stock statistics confidence L"
    )
    return _res("R14", "inventory", sev, int(old), 1, msg)


def apply_rules(
    frames: CanonicalFrames,
    *,
    merge_duplicate_sku_lines: bool = True,
    timezone: str = "Europe/Paris",
    now: datetime | None = None,
) -> tuple[CanonicalFrames, list[RuleResult]]:
    """Run R1-R14 (+ REQ) and apply their actions; returns new frames and the results."""
    now = now or datetime.now(UTC)
    out = dict(frames)
    results: list[RuleResult] = []
    for ds in ("sku_master", "inventory", "receipts", "order_lines"):
        if ds not in out:
            continue
        df = out[ds]
        if ds == "order_lines":
            df, r = _r1(df, now, timezone)
            results.append(r)
        df, r_req = _req(ds, df)
        df, r5 = _r5(ds, df)
        out[ds] = df
        results += [r_req, r5]
    master = out.get("sku_master")
    if master is not None:
        master, r8 = _r8(master)
        out["sku_master"] = master
        results.append(r8)
    lines = out.get("order_lines")
    if lines is not None:
        lines, r34 = _r3_r4(lines)
        lines, r6 = _r6(lines, merge_duplicate_sku_lines)
        lines, r2 = _r2(lines, master)
        out["order_lines"] = lines
        results += [r6, *r34, r2, *_r9_r10(lines, timezone), _r11("order_lines", lines, master)]
        if lines.height:
            results += [_r12(lines, timezone), _r13(lines)]
    results.append(_r7(master, lines))
    if "inventory" in out:
        results.append(_r11("inventory", out["inventory"], master))
    results.append(_r14(out.get("inventory"), lines, now, timezone))
    results.sort(key=lambda r: RULE_ORDER.index(r.rule))
    return out, results


def run_rules(
    frames: CanonicalFrames,
    *,
    merge_duplicate_sku_lines: bool = True,
    timezone: str = "Europe/Paris",
    now: datetime | None = None,
) -> list[RuleResult]:
    """Spec signature: the results of `apply_rules` (input frames are not modified)."""
    return apply_rules(
        frames, merge_duplicate_sku_lines=merge_duplicate_sku_lines, timezone=timezone, now=now
    )[1]
