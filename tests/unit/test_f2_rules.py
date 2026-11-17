"""F2 rules and DQ score: T2.6 each R-rule on its fixture, T2.7 the DQ score formula.

Fixtures (tests/fixtures/ingest/rules): `base/` is a clean 400-day study (20 SKUs, one order a
day of 1-3 lines, mostly 1 line of 1 unit, so both R13 MADs are 0 and only the floor keeps it
clean); `<rule>/<table>.csv` rows are appended to the base table, `<table>.replace.csv` replaces
it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from whsizing.io import apply_mapping, apply_rules, build_dq_report, read_any, run_rules
from whsizing.io.dq import band, dq_score, render_html
from whsizing.io.mapping import TARGETS
from whsizing.io.rules import outlier_threshold
from whsizing.schemas.ingest import DQReport, Mapping, RuleResult
from whsizing.schemas.params import DatasetKind

RULES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest" / "rules"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
BASE_TABLES: tuple[DatasetKind, ...] = ("order_lines", "sku_master", "inventory")
EXPECTED: dict[str, tuple[DatasetKind, str]] = {
    "R1": ("order_lines", "warning"),
    "R2": ("order_lines", "warning"),
    "R3": ("order_lines", "warning"),
    "R4": ("order_lines", "info"),
    "R5": ("order_lines", "warning"),
    "R6": ("order_lines", "info"),
    "R7": ("sku_master", "warning"),
    "R8": ("sku_master", "warning"),
    "R9": ("order_lines", "blocking"),
    "R10": ("order_lines", "warning"),
    "R11": ("inventory", "warning"),
    "R12": ("order_lines", "warning"),
    "R13": ("order_lines", "warning"),
    "R14": ("inventory", "warning"),
}


def _load(path: Path, ds: DatasetKind) -> pl.DataFrame:
    raw = read_any(path)
    columns = {t: t if t in raw.columns else None for t in TARGETS[ds]}
    return apply_mapping(raw, Mapping(dataset=ds, columns=columns))


def _frames(rule: str | None = None) -> dict[str, pl.DataFrame]:
    frames: dict[str, pl.DataFrame] = {
        ds: _load(RULES / "base" / f"{ds}.csv", ds) for ds in BASE_TABLES
    }
    for f in sorted((RULES / rule).glob("*.csv")) if rule else []:
        ds: DatasetKind = f.name.split(".")[0]  # pyright: ignore[reportAssignmentType]
        df = _load(f, ds)
        frames[ds] = df if ".replace." in f.name else pl.concat([frames[ds], df])
    return frames


def _get(results: list[RuleResult], rule: str, ds: str) -> RuleResult:
    return next(r for r in results if r.rule == rule and r.dataset == ds)


def test_base_fixture_is_clean() -> None:
    results = run_rules(_frames(), now=NOW)
    assert {(r.rule, r.severity) for r in results if r.severity != "ok"} == set()
    assert {r.rule for r in results} >= set(EXPECTED)


@pytest.mark.parametrize("rule", list(EXPECTED))
def test_T2_6_each_rule_triggers_on_its_fixture(rule: str) -> None:
    ds, severity = EXPECTED[rule]
    result = _get(run_rules(_frames(rule), now=NOW), rule, ds)
    assert result.severity == severity, result.message
    assert result.count > 0


def test_T2_6_rule_actions() -> None:
    def clean(rule: str) -> tuple[dict[str, pl.DataFrame], list[RuleResult]]:
        return apply_rules(_frames(rule), now=NOW)

    base_lines = _frames()["order_lines"].height
    for rule in ("R1", "R3", "R5"):  # rows dropped and counted
        frames, results = clean(rule)
        assert _get(results, rule, "order_lines").dropped == 2
        assert frames["order_lines"].height == base_lines
    frames, results = clean("R6")  # merged: 2 + 5 units of S02 on order O001
    o001 = frames["order_lines"].filter(pl.col("order_id") == "O001")
    assert o001["qty_units"].to_list() == [7] and _get(results, "R6", "order_lines").dropped == 1
    frames, _ = clean("R4")
    assert frames["order_lines"].filter(pl.col("qty_units") < 0)["is_return"].all()
    frames, _ = clean("R2")  # kept, without dims
    orphans = frames["order_lines"].filter(pl.col("sku").str.starts_with("ZZ"))
    assert orphans.height == 12 and not orphans["has_dims"].any()
    frames, _ = clean("R8")  # implausible values cleared
    m = frames["sku_master"].sort("sku")
    assert m["length_mm"][0] is None and m["weight_kg"][1] is None and m["length_mm"][2] is None
    frames, results = clean("R13")  # listed, never removed
    assert frames["order_lines"]["qty_units"].max() == 500
    assert any(r.get("qty_units") == "500" for r in _get(results, "R13", "order_lines").sample_rows)


UTC_TS = pl.Datetime("us", "UTC")


def _with_ts(lines: pl.DataFrame, row: int, ts: datetime) -> pl.DataFrame:
    """`lines` with the order_ts of row `row` replaced."""
    return lines.with_columns(
        order_ts=pl.when(pl.int_range(pl.len()) == row)
        .then(pl.lit(ts, dtype=UTC_TS))
        .otherwise(pl.col("order_ts"))
    )


def test_T2_6_clean_file_has_no_r1_hit_and_keeps_its_message() -> None:
    frames = _frames()
    out, results = apply_rules(frames, now=NOW)
    r1 = _get(results, "R1", "order_lines")
    assert (r1.severity, r1.count, r1.dropped) == ("ok", 0, 0)
    assert r1.message == "0 lines without a readable date, 0 dated in the future"
    assert out["order_lines"].height == frames["order_lines"].height


def test_T2_6_stray_epoch_line_is_an_r1_hit_and_cannot_stretch_the_history() -> None:
    """M2 / I83: one 1970-01-01 line made the history 662 months, so R9, R10 and R12 saw a
    long history and no zero-order day. The line is an R1 hit (implausible date), dropped and
    counted; R9, R10, R12, the calendar and the coverage are computed on the kept lines."""
    frames = _frames()
    base_out, base = apply_rules(frames, now=NOW)
    lines = frames["order_lines"]
    stray = _with_ts(lines, 300, datetime(1970, 1, 1, 10, tzinfo=UTC))
    out, results = apply_rules({**frames, "order_lines": stray}, now=NOW)
    r1 = _get(results, "R1", "order_lines")
    assert (r1.severity, r1.count, r1.dropped) == ("warning", 1, 1)
    assert "1 dated before" in r1.message and "0 lines without" in r1.message
    assert str(r1.sample_rows[0]["order_ts"]).startswith("1970-01-01")
    assert out["order_lines"].height == lines.height - 1
    for rule in ("R9", "R10", "R12"):  # the clean base run's verdicts, not 'ok' by accident
        got, want = _get(results, rule, "order_lines"), _get(base, rule, "order_lines")
        assert got.severity == want.severity
    assert _get(results, "R9", "order_lines").message == _get(base, "R9", "order_lines").message
    months = build_dq_report(results, out).coverage["history_months"]
    assert months == build_dq_report(base, base_out).coverage["history_months"] < 20
    # the short-history gate is the point of the fix: a 40-day file with a stray line stays blocked
    first = lines["order_ts"].min()
    assert isinstance(first, datetime)
    short = lines.filter(pl.col("order_ts") < first + timedelta(days=40))
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    _, r = apply_rules({**frames, "order_lines": _with_ts(short, 10, epoch)}, now=NOW)
    assert _get(r, "R9", "order_lines").severity == "blocking"
    assert _get(r, "R1", "order_lines").count == 1


def test_T2_6_r1_cuts_only_at_a_gap_of_more_than_90_days() -> None:
    """I83: a line 60 days before the first date is within the margin (kept, the history just
    grows); 150 days before is implausible (dropped). Same on a 60-line file, where the
    stray line must not be taken for the history itself."""
    frames = _frames()
    lines = frames["order_lines"]
    first = lines["order_ts"].min()
    assert isinstance(first, datetime)
    for days, hits in ((60, 0), (150, 1)):
        moved = _with_ts(lines, 300, first - timedelta(days=days))
        out, results = apply_rules({**frames, "order_lines": moved}, now=NOW)
        r1 = _get(results, "R1", "order_lines")
        assert r1.count == hits and out["order_lines"].height == lines.height - hits, days
    small = lines.head(60)
    _, results = apply_rules(
        {**frames, "order_lines": _with_ts(small, 30, datetime(1970, 1, 1, tzinfo=UTC))}, now=NOW
    )
    assert _get(results, "R1", "order_lines").count == 1


@pytest.mark.parametrize("k", [4, 12, 30, 45])
def test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped(k: int) -> None:
    """Final audit F1: a bound taken over LINES is the junk date itself once the junk is 0.5 % of
    the lines or more (a default-epoch export), so nothing was dropped, R9 saw a 661-month
    history and ingest exited 0. The gaps are those of the DISTINCT dates: one junk date is one
    date, however many lines. Above 1 % of the lines R1 is blocking (exit 3)."""
    frames = _frames()
    lines = frames["order_lines"]
    epoch = datetime(1970, 1, 1, 10, tzinfo=UTC)
    junk = lines.head(k).with_columns(order_ts=pl.lit(epoch, dtype=UTC_TS))
    base_out, base = apply_rules(frames, now=NOW)
    out, results = apply_rules({**frames, "order_lines": pl.concat([lines, junk])}, now=NOW)
    r1 = _get(results, "R1", "order_lines")
    assert (r1.count, r1.dropped) == (k, k)
    assert r1.severity == ("blocking" if k / (lines.height + k) > 0.01 else "warning")
    assert out["order_lines"].height == base_out["order_lines"].height
    assert _get(results, "R9", "order_lines").message == _get(base, "R9", "order_lines").message
    assert build_dq_report(results, out).coverage["history_months"] < 20


def test_T2_6_several_junk_dates_on_a_short_file_are_shed_in_turn() -> None:
    """Final audit F1: three junk dates (epoch, 1900, a 1980 default) on a 127-day file are all
    cut, whatever their number."""
    frames = _frames()
    lines = frames["order_lines"].head(200)
    short = {**frames, "order_lines": lines}
    junk = [datetime(y, m, 1, 10, tzinfo=UTC) for y, m in ((1970, 1), (1900, 1), (1980, 6))]
    stray = pl.concat(
        [lines.head(6).with_columns(order_ts=pl.lit(ts, dtype=UTC_TS)) for ts in junk]
    )
    base_out, base = apply_rules(short, now=NOW)
    out, results = apply_rules({**short, "order_lines": pl.concat([lines, stray])}, now=NOW)
    r1 = _get(results, "R1", "order_lines")
    assert (r1.count, r1.dropped, r1.severity) == (18, 18, "blocking")
    assert out["order_lines"].height == base_out["order_lines"].height
    assert _get(results, "R9", "order_lines").message == _get(base, "R9", "order_lines").message


def _junk(lines: pl.DataFrame, stamps: list[datetime], per_date: int = 1) -> pl.DataFrame:
    """`lines` plus `per_date` copies of its first line on each of the junk timestamps."""
    rows = [lines.head(per_date).with_columns(order_ts=pl.lit(ts, dtype=UTC_TS)) for ts in stamps]
    return pl.concat([lines, *rows])


def test_T2_6_junk_dates_within_90_days_of_each_other_are_all_dropped() -> None:
    """Final audit round 2 (F1): the epoch default rendered in UTC and in +01:00 gives
    1969-12-31 and 1970-01-01. A percentile of the distinct dates never reaches past its 2nd
    element on a short file, so one of the two stayed, with the 90-day margin keeping the other
    next to it, and R9 saw a 663-month history. A gap of more than 90 days splits the junk from the
    history whatever the junk's own spread: both are R1 hits, the clean base run's R9 stays."""
    frames = _frames()
    short = {**frames, "order_lines": frames["order_lines"].head(200)}  # 127 distinct days
    stamps = [datetime(1969, 12, 31, 12, tzinfo=UTC), datetime(1970, 1, 1, 10, tzinfo=UTC)]
    base_out, base = apply_rules(short, now=NOW)
    out, results = apply_rules(
        {**short, "order_lines": _junk(short["order_lines"], stamps)}, now=NOW
    )
    r1 = _get(results, "R1", "order_lines")
    assert (r1.count, r1.dropped, r1.severity) == (2, 2, "warning")
    assert out["order_lines"].height == base_out["order_lines"].height
    assert _get(results, "R9", "order_lines").message == _get(base, "R9", "order_lines").message
    assert build_dq_report(results, out).coverage["history_months"] < 6


def test_T2_6_a_dense_cluster_of_junk_dates_is_dropped_whatever_its_own_spread() -> None:
    """Final audit round 2 (F1): ten consecutive junk days on the 400-day base (2.4 % of the
    distinct dates), then twenty junk dates spread over 1969-1975 (4.8 %) are all R1 hits."""
    frames = _frames()
    lines = frames["order_lines"]
    base_out, _ = apply_rules(frames, now=NOW)
    consecutive = [datetime(1970, 1, d, 10, tzinfo=UTC) for d in range(1, 11)]
    spread = [datetime(1969 + i // 4, 3 * (i % 4) + 1, 5, 10, tzinfo=UTC) for i in range(20)]
    for stamps in (consecutive, spread):
        out, results = apply_rules({**frames, "order_lines": _junk(lines, stamps, 3)}, now=NOW)
        r1 = _get(results, "R1", "order_lines")
        assert (r1.count, r1.dropped) == (3 * len(stamps), 3 * len(stamps)), r1.message
        assert out["order_lines"].height == base_out["order_lines"].height
        assert build_dq_report(results, out).coverage["history_months"] < 20


def test_T2_6_a_real_early_season_before_a_long_closure_is_not_junk() -> None:
    """The gap rule must not eat a real history: 60 days of orders, 160 days of closure, then 180
    days. The early block is 25 % of the distinct dates, far above the share a junk cluster can
    hold, so nothing is dropped (R12 and R9 describe the closure instead)."""
    frames = _frames()
    lines = frames["order_lines"]
    first = lines["order_ts"].min()
    assert isinstance(first, datetime)
    season = lines.filter(
        (pl.col("order_ts") < first + timedelta(days=60))
        | (pl.col("order_ts") >= first + timedelta(days=220))
    )
    assert season.height < lines.height
    out, results = apply_rules({**frames, "order_lines": season}, now=NOW)
    r1 = _get(results, "R1", "order_lines")
    assert (r1.severity, r1.count, r1.dropped) == ("ok", 0, 0), r1.message
    assert out["order_lines"].height == season.height


def test_T2_6_slow_launch_ramp_is_not_an_implausible_early_start() -> None:
    """Final audit F2: 150 days of 1 line a day, then 215 days of 100 lines a day. The first
    0.5 % of the LINES spans 108 days, so a line-based bound dropped the first 18 real days; on
    the distinct dates the bound is day 2 − 90 days and nothing is dropped."""
    frames = _frames()
    first = datetime(2024, 1, 1, 10, tzinfo=UTC)
    per_day = [1] * 150 + [100] * 215
    stamps = [first + timedelta(days=d) for d, n in enumerate(per_day) for _ in range(n)]
    ramp = pl.DataFrame({"order_ts": stamps}, schema={"order_ts": UTC_TS}).join(
        frames["order_lines"].head(1).drop("order_ts"), how="cross"
    )
    r1 = _get(run_rules({**frames, "order_lines": ramp}, now=NOW), "R1", "order_lines")
    assert (r1.severity, r1.count, r1.dropped) == ("ok", 0, 0), r1.message


def test_T2_6_r1_with_no_usable_date_does_not_crash() -> None:
    frames = _frames()
    nulls = frames["order_lines"].with_columns(order_ts=pl.lit(None, dtype=UTC_TS))
    out, results = apply_rules({**frames, "order_lines": nulls}, now=NOW)
    assert out["order_lines"].is_empty()
    r1 = _get(results, "R1", "order_lines")
    assert r1.severity == "blocking" and "before" not in r1.message
    assert _get(results, "R9", "order_lines").severity == "blocking"


def test_T2_6_r11_fires_on_order_lines() -> None:
    """R11 on order lines: quantities that are whole cases on > 90 % of lines (case > 1)."""
    frames = _frames("R11")  # master: 6 units per case
    as_cases = frames["order_lines"].with_columns(pl.col("qty_units") * 6)
    r11 = _get(run_rules({**frames, "order_lines": as_cases}, now=NOW), "R11", "order_lines")
    cased = frames["sku_master"].filter(pl.col("units_per_case") > 1)["sku"].implode()
    case_lines = as_cases.filter(pl.col("sku").is_in(cased)).height
    assert r11.severity == "warning" and r11.count == case_lines > 0 and r11.share == 1.0
    units = _get(run_rules(frames, now=NOW), "R11", "order_lines")  # 1-3 units: not cases
    assert units.severity == "ok" and units.share < 0.9


def test_T2_6_r13_threshold_is_median_plus_10_mad_floored_at_1() -> None:
    """median + 10 × max(MAD, 1) (F2c interpretation, [EXPERT]): on [1,1,1,1,1,1,2,3,15] the
    MAD is 0, so the threshold is 1 + 10 = 11 and only 15 is listed (not 2 and 3)."""
    x = pl.Series([1, 1, 1, 1, 1, 1, 2, 3, 15])
    assert outlier_threshold(x) == 11.0
    assert outlier_threshold(pl.Series([1, 2, 3, 2, 2, 40])) == 12.0  # MAD 0.5 → floored at 1
    assert outlier_threshold(pl.Series([10, 20, 30, 20, 20, 400])) == 20 + 10 * 5  # MAD 5
    base = _get(run_rules(_frames(), now=NOW), "R13", "order_lines")
    assert base.severity == "ok"  # multi-line orders of 1-3 units: nothing listed
    frames = _frames()
    lines = frames["order_lines"].with_columns(qty_units=pl.lit(1, dtype=pl.Int64))
    big = lines.head(3).with_columns(
        order_id=pl.format("BIG{}", pl.int_range(pl.len())), qty_units=pl.Series([2, 3, 15])
    )
    r13 = _get(
        run_rules({**frames, "order_lines": pl.concat([lines, big])}, now=NOW), "R13", "order_lines"
    )
    assert r13.severity == "warning" and r13.count == 1 and "1 lines" in r13.message
    assert r13.sample_rows[0]["qty_units"] == "15"


def test_T2_6_severity_thresholds_r1_r2() -> None:
    frames = _frames()
    lines = frames["order_lines"]
    n_bad = lines.height // 50  # 2 % of the lines
    bad_dates = lines.head(n_bad).with_columns(
        order_ts=pl.lit(None, dtype=pl.Datetime("us", "UTC"))
    )
    r1 = _get(
        run_rules({**frames, "order_lines": pl.concat([lines, bad_dates])}, now=NOW),
        "R1",
        "order_lines",
    )
    assert r1.severity == "blocking" and r1.share > 0.01
    orphans = lines.head(lines.height // 15).with_columns(  # ≈ 6 % of the lines
        sku=pl.format("ZZ{}", pl.int_range(pl.len()))
    )
    r2 = _get(
        run_rules({**frames, "order_lines": pl.concat([lines, orphans])}, now=NOW),
        "R2",
        "order_lines",
    )
    assert r2.severity == "blocking" and r2.share > 0.05
    one = orphans.head(1)
    r2_info = _get(
        run_rules({**frames, "order_lines": pl.concat([lines, one])}, now=NOW), "R2", "order_lines"
    )
    assert r2_info.severity == "info"


def test_req_drops_rows_missing_required_values() -> None:
    frames = _frames()
    inv = frames["inventory"]
    bad = pl.concat([inv, inv.head(2).with_columns(qty_units=pl.lit(-5, dtype=pl.Int64))])
    out, results = apply_rules({**frames, "inventory": bad}, now=NOW)
    req = _get(results, "REQ", "inventory")
    assert req.severity == "warning" and req.dropped == 2 and out["inventory"].height == inv.height


def test_req_clears_negative_pallets_on_receipts() -> None:
    """Audit round 2: a negative `pallets` reached Pandera (≥ 0) and crashed ingest (exit 1).
    It is cleared (then derived from units_per_pallet) and counted; the receipt is kept."""
    ts = datetime(2025, 3, 4, 7, tzinfo=UTC)
    receipts = pl.DataFrame({"receipt_id": ["R1", "R2"], "receipt_ts": [ts, ts],
                             "sku": ["S01", "S02"], "qty_units": [80, 20],
                             "pallets": [-1.0, 2.0]})  # fmt: skip
    out, results = apply_rules({"receipts": receipts}, now=NOW)
    req = _get(results, "REQ", "receipts")
    assert out["receipts"]["pallets"].to_list() == [None, 2.0]
    assert req.severity == "warning" and req.count == 1 and req.dropped == 0
    assert "negative pallet" in req.message


def test_T2_6_r6_never_merges_a_return_into_a_sale() -> None:
    """Audit round 2: R6 ran before R3/R4, summed +5 shipped and -5 returned to 0 and R3
    dropped both. R3/R4 run first and R6 merges only lines of the same status and sign."""
    ts = datetime(2025, 1, 2, 10, tzinfo=UTC)
    lines = pl.DataFrame({"order_id": ["O1", "O1", "O1", "O2"], "order_ts": [ts] * 4,
                          "sku": ["A", "A", "A", "B"], "qty_units": [5, -5, 2, 3],
                          "channel": [None] * 4,
                          "line_status": ["shipped", "returned", "shipped", "shipped"],
                          "source_file": ["f"] * 4, "source_row": [1, 2, 3, 4]},
                         schema_overrides={"channel": pl.Utf8})  # fmt: skip
    out, results = apply_rules({"order_lines": lines}, now=NOW)
    got = out["order_lines"].sort("order_id", "qty_units").select("order_id", "qty_units",
                                                                  "is_return").rows()  # fmt: skip
    assert got == [("O1", -5, True), ("O1", 7, False), ("O2", 3, False)]
    assert _get(results, "R3", "order_lines").severity == "ok"
    assert _get(results, "R4", "order_lines").count == 1
    assert _get(results, "R6", "order_lines").dropped == 1  # the two shipped lines only
    # audit F2c round 1: the sign alone splits too ('shipped' +5 and -5 stay two lines)
    same = lines.head(2).with_columns(line_status=pl.lit("shipped"))
    out, results = apply_rules({"order_lines": same}, now=NOW)
    got = out["order_lines"].sort("qty_units", descending=True).select("qty_units", "is_return")
    assert got.rows() == [(5, False), (-5, True)]
    assert _get(results, "R6", "order_lines").dropped == 0


def test_without_master_r2_is_not_evaluated_and_coverage_is_zero() -> None:
    frames = _frames()
    out, results = apply_rules({"order_lines": frames["order_lines"]}, now=NOW)
    assert _get(results, "R2", "order_lines").severity == "info"
    assert _get(results, "R7", "sku_master").severity == "warning"
    assert not out["order_lines"]["has_dims"].any()
    assert _get(results, "R14", "inventory").severity == "warning"  # missing snapshot


T2_7_CASES = [
    # (blocking, warnings, dims coverage, short history) → score by hand
    (0, 0, 1.0, False, 100.0),
    (0, 1, 1.0, True, 85.0),
    (1, 2, 0.9, True, 53.0),  # 100 − 25 − 10 − 2 − 10
    (2, 5, 0.5, False, 15.0),  # 100 − 50 − 25 − 10
    (3, 7, 0.0, True, 0.0),  # caps 50 and 25, then −20 − 10 → −5 → clipped to 0
]


@pytest.mark.parametrize(("blocking", "warnings", "cov", "short", "expected"), T2_7_CASES)
def test_T2_7_dq_score_formula(
    blocking: int, warnings: int, cov: float, short: bool, expected: float
) -> None:
    score, parts = dq_score(blocking, warnings, cov, short)
    assert score == pytest.approx(expected)
    assert max(0.0, 100 + sum(parts.values())) == pytest.approx(expected)


def test_T2_7_bands() -> None:
    assert band(80) == "usable" and band(79.99) == "usable with caveats"
    assert band(60) == "usable with caveats" and band(59.99) == "remediation needed"


@pytest.mark.parametrize("rule", ["R7", "R9", "R10", "R2"])
def test_T2_7_report_score_matches_formula_on_fixtures(rule: str) -> None:
    frames, results = apply_rules(_frames(rule), now=NOW)
    report = build_dq_report(results, frames)
    n_blocking = sum(r.severity == "blocking" for r in results)
    n_warnings = sum(r.severity == "warning" for r in results)
    cov = float(frames["order_lines"]["has_dims"].mean())  # pyright: ignore[reportArgumentType]
    short = _get(results, "R10", "order_lines").severity != "ok"
    expected = (
        100 - min(25 * n_blocking, 50) - min(5 * n_warnings, 25) - 20 * (1 - cov) - 10 * short
    )
    assert report.score == pytest.approx(max(0.0, min(100.0, expected)), abs=0.01)
    assert report.coverage["dims_coverage_lines"] == pytest.approx(cov)
    assert report.band == band(report.score)


def test_dq_html_is_readable_and_escaped() -> None:
    frames, results = apply_rules(_frames("R8"), now=NOW)
    report = build_dq_report(results, frames, notes=["W_UNITS_DIMS: <b>converted</b>"])
    html = render_html(report)
    assert "Data quality report" in html and f">{int(report.score)}<small>" in html
    assert "Dimensions and weight plausible" in html and report.band in html
    assert "&lt;b&gt;converted&lt;/b&gt;" in html  # autoescaped


def test_T2_7_cover_score_never_rounds_into_a_better_band() -> None:
    """Audit: 79.6 printed as '80 / 100' next to 'usable with caveats'. The cover floors."""
    for score, shown in ((79.6, "79"), (99.6, "99"), (80.0, "80"), (59.99, "59")):
        report = DQReport(created_at=NOW, score=score, band=band(score), score_breakdown={},
                          coverage={}, rules=[])  # fmt: skip
        html = render_html(report)
        assert f'class="score">{shown}<small> / 100' in html and report.band in html
