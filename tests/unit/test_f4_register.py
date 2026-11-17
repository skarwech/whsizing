"""F4b: register entries I55-I60 and the F4 audit findings (daily columns, catalog, sku frame)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from structlog.testing import capture_logs

from whsizing.catalog import Catalog, load_catalog
from whsizing.design import (
    derive_inbound,
    load_basis,
    select_design_day,
    with_pack_data,
    write_design,
)
from whsizing.design.basis import check_basis, growth_factor, window_months
from whsizing.errors import ConfigError, WhsizingError
from whsizing.profile import ProfileTables, build_tables, profile_from_tables
from whsizing.schemas import DemandProfile, DesignBasis, DesignDay, ProfileCfg, Projection

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
DATA = GOLDEN / "tiny_golden"
GF = 1.04**5  # golden growth factor (1 + g)^T


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load_catalog(ROOT / "catalog")


@pytest.fixture(scope="module")
def basis() -> DesignBasis:
    return load_basis(GOLDEN / "golden_basis.yaml")


@pytest.fixture(scope="module")
def built(basis: DesignBasis) -> tuple[ProfileTables, DemandProfile, pl.DataFrame]:
    t = build_tables(DATA, basis, ProfileCfg())
    sku = with_pack_data(t.skus, pl.read_parquet(DATA / "sku_master.parquet"))
    return t, profile_from_tables(t, ProfileCfg()), sku


def with_(basis: DesignBasis, section: str, **values: Any) -> DesignBasis:
    sub = getattr(basis, section).model_copy(update=values)
    return basis.model_copy(update={section: sub})


def unset_window(basis: DesignBasis) -> DesignBasis:
    """The basis with projection.trailing_months left at its default (not in fields_set)."""
    proj = Projection(**basis.projection.model_dump(exclude={"trailing_months"}))
    assert "trailing_months" not in proj.model_fields_set
    return basis.model_copy(update={"projection": proj})


def design(built, basis: DesignBasis, catalog: Catalog, daily=None) -> DesignDay:
    t, profile, sku = built
    daily = t.daily if daily is None else daily
    return select_design_day(profile, basis, daily, sku=sku, catalog=catalog)


def synth_daily(t: ProfileTables, start: date, end: date) -> pl.DataFrame:
    """Mon-Fri operating days start..end, every metric = 1, 2, 3, ... (grows by day)."""
    days = pl.date_range(start, end, eager=True)
    vals = pl.Series(np.arange(1.0, len(days) + 1))
    cols = {c: vals for c in t.daily.columns if t.daily[c].dtype == pl.Float64}
    d = pl.DataFrame({"date": days, **cols}).with_columns(
        weekday=pl.col("date").dt.weekday().cast(pl.Int64) - 1, is_holiday=pl.lit(False)
    )
    return d.with_columns(is_operating=pl.col("weekday") < 5)


# --- I55: design-day window ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [
        (date(2024, 1, 1), date(2025, 12, 30), 24),  # 730 days / 30.4375 = 23.98 ≥ 23.9 (audit)
        (date(2023, 4, 2), date(2025, 3, 31), 24),  # 730 days
        (date(2023, 5, 1), date(2025, 3, 31), 12),  # 701 days = 23.03 months < 23.9
        (date(2025, 3, 1), date(2025, 3, 31), 12),  # tiny_golden length: I5 then applies
    ],
)
def test_I55_default_window_is_24_months_when_history_covers_it(
    built, basis, start: date, end: date, months: int
) -> None:
    daily = synth_daily(built[0], start, end)
    assert window_months(unset_window(basis).projection, daily) == months
    assert window_months(basis.projection, daily) == 12  # set in the basis file: as given


def test_I55_default_window_drives_design_day_and_inbound(built, basis, catalog) -> None:
    t, profile, _ = built
    daily = synth_daily(t, date(2023, 4, 2), date(2025, 3, 31))  # 2 years
    op = daily.filter("is_operating")
    last12 = op.filter(pl.col("date") > date(2024, 3, 31))
    auto = design(built, unset_window(basis), catalog, daily)
    given = design(built, basis, catalog, daily)  # trailing_months: 12 in the file
    assert auto.percentile_values["lines"] == pytest.approx(np.percentile(op["lines"], 95))
    assert given.percentile_values["lines"] == pytest.approx(np.percentile(last12["lines"], 95))
    # derived inbound uses the same window: mean units out over the 24 months × gf (Δstock 0)
    assert profile.stock.growth_units_per_year is None
    assert auto.inbound.units_per_day == pytest.approx(float(op["units"].mean()) * GF)  # pyright: ignore[reportArgumentType]
    used = {a.key: a for a in auto.assumptions}["projection.trailing_months"]
    assert (used.value, used.origin) == (24.0, "derived")
    given_row = {a.key: a for a in given.assumptions}["projection.trailing_months"]
    assert (given_row.value, given_row.origin) == (12.0, "client")


@pytest.mark.parametrize(
    ("start", "months", "warns"),
    [
        (date(2023, 4, 2), None, False),  # default → 24 months used
        (date(2023, 4, 2), 12, False),  # 12 whole calendar months (365 days) is not < 12
        (date(2024, 4, 1), None, False),  # 365-day history: I52 calendar months 12.0, not 11.99
        (date(2023, 4, 2), 6, True),  # explicit window < 12
        (date(2024, 10, 1), None, True),  # 6 months of history only
        (date(2024, 10, 1), 24, True),
    ],
)
def test_I55_short_window_warning_on_window_used(
    built, basis, catalog, start: date, months: int | None, warns: bool
) -> None:
    daily = synth_daily(built[0], start, date(2025, 3, 31))
    b = unset_window(basis)
    if months is not None:
        b = with_(basis, "projection", trailing_months=months)
    with capture_logs() as logs:
        design(built, b, catalog, daily)
    events = [e["event"] for e in logs]
    assert ("design_day_short_window" in events) is warns
    assert "design_day_window_below_24_months" not in events  # superseded by I55


def test_I55_template_leaves_window_unset(tmp_path: Path) -> None:
    for lang in ("fr", "en"):
        text = (ROOT / "basis" / f"template_{lang}.yaml").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if "trailing_months" in ln)
        assert line.lstrip().startswith("# trailing_months:"), line
        assert "24" in line.split("#", 2)[2]  # the comment states the 24-month rule
        b = load_basis(ROOT / "basis" / f"template_{lang}.yaml")
        assert "trailing_months" not in b.projection.model_fields_set


# --- I56: receipts mode ----------------------------------------------------------------------


def test_I56_receipts_peak_factor_defaults_to_one(built, basis, catalog) -> None:
    t, profile, sku = built
    b = with_(basis, "flows", inbound_mode="receipts")
    assert b.flows.inbound_peak_factor is None
    assert derive_inbound(profile, b, t.daily, sku, catalog=catalog).peak_factor == 1.0
    dd = design(built, b, catalog)
    assert dd.inbound.peak_factor == 1.0
    assert {a.key: a for a in dd.assumptions}["flows.inbound_peak_factor"].value == 1.0
    # derived mode is unchanged: outbound peak-to-average
    derived = derive_inbound(profile, basis, t.daily, sku, catalog=catalog)
    assert derived.peak_factor == profile.seasonality.peak_to_average


def test_I56_unknown_pallet_days_left_out_of_pallets_percentile_only(built, basis, catalog) -> None:
    t, profile, sku = built
    b = with_(basis, "flows", inbound_mode="receipts")
    first = t.daily["date"].min()
    daily = t.daily.with_columns(  # pallet count unknown on the first 10 days
        receipts_pallets=pl.when(pl.col("date") < first + timedelta(days=10))
        .then(None)
        .otherwise(pl.col("receipts_pallets"))
    )
    inb = derive_inbound(profile, b, daily, sku, catalog=catalog)
    op = daily.filter("is_operating")
    known = op["receipts_pallets"].drop_nulls()
    assert known.len() < op.height
    assert inb.pallets_per_day == pytest.approx(np.percentile(known, 95) * GF, rel=1e-12)
    assert inb.units_per_day == pytest.approx(np.percentile(op["receipts_units"], 95) * GF)
    assert inb.receipt_lines_per_day == pytest.approx(np.percentile(op["receipts_lines"], 95) * GF)


# --- I71: receipts mode needs receipts in the history --------------------------------------


def _build_with_receipts(tmp_path: Path, basis: DesignBasis, shift_days: int | None) -> tuple:
    """tiny_golden canonical copy whose receipts are moved by `shift_days` (None: no receipts
    table); → (tables, profile, sku table)."""
    for name in ("order_lines", "sku_master", "inventory", "receipts"):
        df = pl.read_parquet(DATA / f"{name}.parquet")
        if name == "receipts":
            if shift_days is None:
                continue
            df = df.with_columns(pl.col("receipt_ts") + pl.duration(days=shift_days))
        df.write_parquet(tmp_path / f"{name}.parquet")
    t = build_tables(tmp_path, basis, ProfileCfg())
    sku = with_pack_data(t.skus, pl.read_parquet(tmp_path / "sku_master.parquet"))
    return t, profile_from_tables(t, ProfileCfg()), sku


@pytest.mark.parametrize("shift", [-400, 400])
def test_I71_receipts_mode_with_receipts_outside_the_history_raises(
    tmp_path: Path, basis, catalog, shift: int
) -> None:
    """F3e open issue 1 / I71: receipts none of which falls in the shipped-date window gave an
    all-zero inbound (0 units, pallets, lines and trucks, flags []). Now F3 treats the table
    as absent and F4 receipts mode raises ConfigError naming the mode, the receipts date range
    and the history window, in derive_inbound and in select_design_day; derived mode is fine."""
    t, profile, sku = _build_with_receipts(tmp_path, basis, shift)
    assert not {"receipts_lines", "receipts_units", "receipts_pallets"} & set(t.daily.columns)
    first, last = pl.read_parquet(DATA / "receipts.parquet")["receipt_ts"].dt.date().sort()[[0, -1]]
    moved = (first + timedelta(days=shift), last + timedelta(days=shift))
    assert profile.receipts_period == moved
    b = with_(basis, "flows", inbound_mode="receipts")
    for call in (
        lambda: derive_inbound(profile, b, t.daily, sku, catalog=catalog),
        lambda: select_design_day(profile, b, t.daily, sku=sku, catalog=catalog),
    ):
        with pytest.raises(ConfigError) as e:
            call()
        msg = str(e.value)
        assert "flows.inbound_mode is 'receipts'" in msg
        assert f"{moved[0]} to {moved[1]}" in msg  # the receipts date range
        assert f"{profile.period_start} to {profile.period_end}" in msg  # the history window
        assert "daily frame" not in msg  # no internal jargon (R3 fix round 1, finding 5)
    derived = with_(basis, "flows", inbound_mode="derived")
    assert derive_inbound(profile, derived, t.daily, sku, catalog=catalog).units_per_day > 0


def test_I71_receipts_mode_without_a_receipts_table_raises(tmp_path: Path, basis, catalog) -> None:
    """Same ConfigError with no receipts table at all: names the mode and the history window."""
    t, profile, sku = _build_with_receipts(tmp_path, basis, None)
    assert profile.receipts_period is None
    b = with_(basis, "flows", inbound_mode="receipts")
    with pytest.raises(ConfigError) as e:
        derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    msg = str(e.value)
    assert "flows.inbound_mode is 'receipts'" in msg and "no receipts" in msg
    assert f"{profile.period_start} to {profile.period_end}" in msg


def _build_edited(
    tmp_path: Path,
    basis: DesignBasis,
    *,
    order_lines: pl.DataFrame | None = None,
    receipts: pl.DataFrame | None = None,
) -> tuple:
    """tiny_golden canonical copy with the given order_lines / receipts frames; → (tables,
    profile, sku table)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    edits = {"order_lines": order_lines, "receipts": receipts}
    for name in ("order_lines", "sku_master", "inventory", "receipts"):
        df = edits.get(name)
        (pl.read_parquet(DATA / f"{name}.parquet") if df is None else df).write_parquet(
            tmp_path / f"{name}.parquet"
        )
    t = build_tables(tmp_path, basis, ProfileCfg())
    sku = with_pack_data(t.skus, pl.read_parquet(tmp_path / "sku_master.parquet"))
    return t, profile_from_tables(t, ProfileCfg()), sku


def _tripled_history() -> pl.DataFrame:
    """tiny_golden orders repeated 3 times 40 days apart: a 3.6-month history (03-01 to 06-19)."""
    o = pl.read_parquet(DATA / "order_lines.parquet")
    return pl.concat(
        o.with_columns(
            order_id=pl.col("order_id") + f"-{k}",
            order_ts=pl.col("order_ts") + pl.duration(days=40 * k),
        )
        for k in range(3)
    )


def test_I71_receipts_before_the_design_day_window_raise(tmp_path: Path, basis, catalog) -> None:
    """R3 fix round 1, finding 1 (a): receipts inside the shipped-date window (03-03 to 03-31,
    so F3 keeps the receipts_* columns) but all before F4's trailing window (the last month of
    a 03-01 to 06-19 history) gave P_p = 0: an all-zero inbound with no flag. Now ConfigError
    in derive_inbound and select_design_day, naming the receipts range and the candidate days."""
    b = with_(with_(basis, "projection", trailing_months=1), "flows", inbound_mode="receipts")
    t, profile, sku = _build_edited(tmp_path, b, order_lines=_tripled_history())
    assert {"receipts_lines", "receipts_units", "receipts_pallets"} <= set(t.daily.columns)
    assert profile.receipts_period == (date(2025, 3, 3), date(2025, 3, 31))
    assert (profile.period_start, profile.period_end) == (date(2025, 3, 1), date(2025, 6, 19))
    cand = t.daily.filter(pl.col("is_operating") & (pl.col("date") > date(2025, 5, 19)))
    assert cand["receipts_lines"].sum() == 0  # the premise: no receipt on a candidate day
    for call in (
        lambda: derive_inbound(profile, b, t.daily, sku, catalog=catalog),
        lambda: select_design_day(profile, b, t.daily, sku=sku, catalog=catalog),
    ):
        with pytest.raises(ConfigError) as e:
            call()
        msg = str(e.value)
        assert "flows.inbound_mode is 'receipts'" in msg
        assert "2025-03-03 to 2025-03-31" in msg  # the receipts date range
        assert f"{cand['date'].min()} to {cand['date'].max()}" in msg  # the candidate days
        assert "projection.trailing_months" in msg and "'derived'" in msg
        assert "daily frame" not in msg  # no internal jargon (finding 5)


def test_I71_receipts_only_on_non_operating_days_raise(tmp_path: Path, basis, catalog) -> None:
    """Finding 1 (b): five receipts, all on Sunday 2025-03-02 (not an operating day): the
    columns exist and the date is inside the window, but candidate_days excludes it, so inbound
    was all-zero. Now ConfigError; a Monday receipt (control, at P100) sizes inbound."""
    b = with_(basis, "flows", inbound_mode="receipts")
    r = pl.read_parquet(DATA / "receipts.parquet").head(5)
    sunday = r.with_columns(receipt_ts=pl.lit(datetime(2025, 3, 2, 8, tzinfo=UTC)))
    t, profile, sku = _build_edited(tmp_path / "sun", b, receipts=sunday)
    day = t.daily.filter(pl.col("date") == date(2025, 3, 2)).row(0, named=True)
    assert not day["is_operating"] and day["receipts_lines"] == 5.0
    with pytest.raises(ConfigError, match="none of the receipts") as e:
        derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    assert "2025-03-02 to 2025-03-02" in str(e.value)
    monday = r.with_columns(receipt_ts=pl.lit(datetime(2025, 3, 3, 8, tzinfo=UTC)))
    t, profile, sku = _build_edited(tmp_path / "mon", b, receipts=monday)
    p100 = with_(b, "projection", design_percentile=100.0)  # P95 of one day in 26 is 0, P100 not
    assert derive_inbound(profile, p100, t.daily, sku, catalog=catalog).units_per_day > 0


def test_I71_receipts_inside_the_history_still_size_inbound(built, basis, catalog) -> None:
    """The golden receipts (inside the window) give the P95 inbound, not an error."""
    t, profile, sku = built
    assert profile.receipts_period is not None
    b = with_(basis, "flows", inbound_mode="receipts", inbound_peak_factor=1.3)
    inb = derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    assert inb.units_per_day > 0 and inb.pallets_per_day > 0 and inb.trucks_per_day > 0


# --- R4: F_INBOUND_SPARSE and F_RECEIPTS_NO_PALLETS (I71 residuals) ---------------------------


def _monday_only(tmp_path: Path, basis: DesignBasis) -> tuple:
    """Five receipt rows, all on Monday 2025-03-03: one receipt day among the 26 operating days."""
    r = pl.read_parquet(DATA / "receipts.parquet").head(5)
    monday = r.with_columns(receipt_ts=pl.lit(datetime(2025, 3, 3, 8, tzinfo=UTC)))
    return _build_edited(tmp_path, basis, receipts=monday)


def test_I71_sparse_receipts_raise_f_inbound_sparse_in_inbound_and_design_day(
    tmp_path: Path, basis, catalog
) -> None:
    """R3 round 1 residual: one receipt day in 26 gives P95 = 0 (the spec's percentile rule) and
    an all-zero inbound with no flag. Now a warning, value = the receipt days among the candidate
    days, in Inbound.flags and, after the design-day flags, in DesignDay.flags."""
    b = with_(basis, "flows", inbound_mode="receipts")
    t, profile, sku = _monday_only(tmp_path, b)
    inb = derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    assert (inb.units_per_day, inb.pallets_per_day, inb.trucks_per_day) == (0.0, 0.0, 0.0)
    (flag,) = [f for f in inb.flags if f.code == "F_INBOUND_SPARSE"]
    assert flag.severity == "warning" and flag.value == 1.0
    assert "P95" in flag.message and "1 of 26" in flag.message
    dd = select_design_day(profile, b, t.daily, sku=sku, catalog=catalog)
    codes = [f.code for f in dd.flags]
    assert dd.inbound.flags == inb.flags and dd.flags[-len(inb.flags) :] == inb.flags
    assert codes.index("F_INBOUND_SPARSE") > codes.index("F_SHORT_HISTORY")  # after design-day
    json_path, _ = write_design(dd, tmp_path / "out")
    written = {f["code"]: f for f in json.loads(json_path.read_text(encoding="utf-8"))["flags"]}
    assert written["F_INBOUND_SPARSE"]["severity"] == "warning"
    assert written["F_INBOUND_SPARSE"]["value"] == 1.0


def test_I71_percentile_that_is_not_zero_raises_no_sparse_flag(
    tmp_path: Path, built, basis, catalog
) -> None:
    """The same single receipt day at P100 sizes inbound (percentile > 0), and the golden
    receipts (many receipt days) at P95: neither is sparse, no flag."""
    b = with_(basis, "flows", inbound_mode="receipts")
    t, profile, sku = _monday_only(tmp_path, b)
    p100 = with_(b, "projection", design_percentile=100.0)
    inb = derive_inbound(profile, p100, t.daily, sku, catalog=catalog)
    assert inb.units_per_day > 0 and inb.flags == []
    t, profile, sku = built
    assert derive_inbound(profile, b, t.daily, sku, catalog=catalog).flags == []


def test_I71_receipts_without_pallet_counts_raise_f_receipts_no_pallets(
    tmp_path: Path, basis, catalog
) -> None:
    """R3 residual: receipts_pallets null on every receipt day (F3 puts 0.0 on the days without a
    receipt) sizes pallets and trucks at 0 next to non-zero units with no flag. Now a warning;
    the zero pallets are not reported twice as a sparse series."""
    b = with_(basis, "flows", inbound_mode="receipts")
    r = pl.read_parquet(DATA / "receipts.parquet").with_columns(pallets=pl.lit(None, pl.Float64))
    t, profile, sku = _build_edited(tmp_path, b, receipts=r)
    receipt_days = t.daily.filter(pl.col("receipts_lines") > 0)
    assert receipt_days["receipts_pallets"].null_count() == receipt_days.height > 1
    inb = derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    assert inb.units_per_day > 0 and (inb.pallets_per_day, inb.trucks_per_day) == (0.0, 0.0)
    assert [f.code for f in inb.flags] == ["F_RECEIPTS_NO_PALLETS"]
    assert inb.flags[0].severity == "warning" and inb.flags[0].value == receipt_days.height
    dd = select_design_day(profile, b, t.daily, sku=sku, catalog=catalog)
    assert dd.flags[-1].code == "F_RECEIPTS_NO_PALLETS" and dd.inbound.flags == inb.flags


def test_I56_some_unknown_pallet_days_raise_no_flag(built, basis, catalog) -> None:
    """Pallet counts unknown on the first 10 days only: the pallets percentile uses the known
    days (I56) and nothing is flagged."""
    t, profile, sku = built
    b = with_(basis, "flows", inbound_mode="receipts")
    first = t.daily["date"].min()
    daily = t.daily.with_columns(
        receipts_pallets=pl.when(pl.col("date") < first + timedelta(days=10))
        .then(None)
        .otherwise(pl.col("receipts_pallets"))
    )
    assert derive_inbound(profile, b, daily, sku, catalog=catalog).flags == []


# --- I57: F_RATIO_DRIFT with P_m = 0 ---------------------------------------------------------


def test_I57_ratio_drift_raised_when_percentile_is_zero(built, basis, catalog) -> None:
    dd = design(built, with_(basis, "projection", design_percentile=10.0), catalog)
    assert dd.percentile_values["pallets_out"] == 0.0
    assert dd.pallets_out > 0
    drift = {f.code: f for f in dd.flags}["F_RATIO_DRIFT:pallets_out"]
    assert drift.value is None
    assert drift.severity == "info"  # I70


def test_I57_no_ratio_drift_when_both_zero(built, basis, catalog) -> None:
    daily = built[0].daily.with_columns(pallets_out=pl.lit(0.0))
    dd = design(built, with_(basis, "projection", design_percentile=10.0), catalog, daily)
    assert (dd.percentile_values["pallets_out"], dd.pallets_out) == (0.0, 0.0)
    assert "F_RATIO_DRIFT:pallets_out" not in [f.code for f in dd.flags]


# --- I70: design-day flag severities ----------------------------------------------------------


def test_I70_design_day_flags_are_info_in_the_object_and_in_design_day_json(
    built, basis, catalog, tmp_path: Path
) -> None:
    """I70: F_SHORT_HISTORY, F_RATIO_DRIFT:<m> and F_PERCENTILE_CLIPPED are `info` (they were
    warnings), in the DesignDay and in the design/design_day.json that write_design writes.
    The golden days raise all three kinds: P120 clips and has 26 operating days; P10 drifts."""
    clipped = design(built, with_(basis, "projection", design_percentile=120.0), catalog)
    drifting = design(built, with_(basis, "projection", design_percentile=10.0), catalog)
    kinds = {f.code.split(":")[0] for day in (clipped, drifting) for f in day.flags}
    assert {"F_PERCENTILE_CLIPPED", "F_SHORT_HISTORY", "F_RATIO_DRIFT"} <= kinds
    for i, day in enumerate((clipped, drifting)):
        assert {f.severity for f in day.flags} == {"info"}
        json_path, _ = write_design(day, tmp_path / str(i))
        written = json.loads(json_path.read_text(encoding="utf-8"))["flags"]
        assert [f["code"] for f in written] == [f.code for f in day.flags]
        assert {f["severity"] for f in written} == {"info"}


# --- I59: F_DEFAULT_UPP ----------------------------------------------------------------------


def test_I59_default_upp_is_info_with_share_of_design_inbound_units(built, basis, catalog) -> None:
    t, profile, _ = built
    master = pl.read_parquet(DATA / "sku_master.parquet")
    no_pack = master["sku"].head(5).to_list()
    master = master.with_columns(
        pl.when(pl.col("sku").is_in(no_pack)).then(None).otherwise(pl.col(c)).alias(c)
        for c in ("units_per_case", "cases_per_pallet", "units_per_pallet")
    )
    sku = with_pack_data(t.skus, master)
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    share = t.skus.filter(pl.col("sku").is_in(no_pack))["units"].sum() / t.skus["units"].sum()
    upp = [f for f in dd.flags if f.code == "F_DEFAULT_UPP"]
    assert len(upp) == 1
    assert (upp[0].severity, upp[0].value) == ("info", pytest.approx(share))
    assert [f.code for f in dd.flags][-1] == "F_DEFAULT_UPP"  # after the design-day flags


# --- I60: basis validation -------------------------------------------------------------------

INF, NAN = float("inf"), float("nan")
BAD = [
    ("projection", "peak_stock_factor", 0.0),
    ("projection", "peak_stock_factor", -1.0),
    ("projection", "peak_stock_factor", NAN),
    ("projection", "growth_rate", INF),
    ("projection", "growth_rate", -1.0),
    ("flows", "inbound_peak_factor", 0.0),
    ("flows", "inbound_peak_factor", -2.0),
    ("flows", "inbound_peak_factor", NAN),
    ("operations", "utilisation", 0.0),
    ("operations", "utilisation", 1.01),
    ("flows", "dock_utilisation", 0.0),
    ("flows", "dock_utilisation", 1.5),
    ("operations", "absenteeism", 1.0),
    ("operations", "absenteeism", -0.01),
    ("operations", "pfd_allowance", 1.0),
    ("flows", "returns_rate", 1.01),
    ("flows", "returns_rate", -0.01),
    ("service", "same_day_share", 1.5),
    ("operations", "shifts_per_day", 0),
    ("operations", "hours_per_shift", 0.0),
    ("operations", "paid_hours_per_person_day", -7.0),
    ("operations", "annual_paid_hours_per_fte", 0.0),
    ("flows", "truck_dwell_hours", 0.0),
    ("building", "area_m2", 0.0),
    ("building", "clear_height_m", -1.0),
    ("building", "rent_eur_m2_year", INF),
    ("finance", "discount_rate", NAN),
    ("finance", "energy_price_eur_kwh", -INF),
    ("service", "sla_window_hours", NAN),
    ("flows", "pallet_order_weight_kg", INF),
]


@pytest.mark.parametrize(("section", "field", "value"), BAD)
def test_I60_check_basis_rejects_invalid_values(
    basis, section: str, field: str, value: Any
) -> None:
    with pytest.raises(ConfigError, match=rf"{section}\.{field}"):
        check_basis(with_(basis, section, **{field: value}))


def test_I60_rejects_non_finite_labor_cost(basis) -> None:
    bad = with_(basis, "finance", labor_cost_eur_h={"operator": 25.5, "team_leader": INF})
    with pytest.raises(ConfigError, match=r"finance\.labor_cost_eur_h"):
        check_basis(bad)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("operations", "utilisation", 1.0),
        ("operations", "absenteeism", 0.0),
        ("operations", "pfd_allowance", 0.0),
        ("flows", "returns_rate", 0.0),
        ("flows", "dock_utilisation", 1.0),
        ("service", "same_day_share", 1.0),
        ("flows", "inbound_peak_factor", None),
        ("projection", "design_percentile", 120.0),  # clipped later, not rejected
    ],
)
def test_I60_boundary_values_accepted(basis, section: str, field: str, value: Any) -> None:
    b = with_(basis, section, **{field: value})
    assert check_basis(b) is b


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("peak_stock_factor: 1.15", "peak_stock_factor: .nan", "projection.peak_stock_factor"),
        ("growth_rate: 0.04", "growth_rate: .inf", "projection.growth_rate"),
        ("area_m2: 410", "area_m2: -.inf", "building.area_m2"),
        ("operator: 25.5", "operator: .nan", "finance.labor_cost_eur_h"),
    ],
)
def test_I60_load_basis_rejects_nan_and_inf_from_yaml(
    tmp_path: Path, old: str, new: str, field: str
) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "basis.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ConfigError, match=field.replace(".", r"\.")):
        load_basis(path)


# --- daily frame columns, catalog, I58 sku frame ---------------------------------------------


@pytest.mark.parametrize("column", ["cube_m3", "pallets_out", "is_operating", "weekday"])
def test_daily_missing_column_raises_whsizing_error(built, basis, catalog, column: str) -> None:
    with pytest.raises(WhsizingError, match=column):
        design(built, basis, catalog, built[0].daily.drop(column))


def test_receipts_mode_missing_receipt_column_names_it(built, basis, catalog) -> None:
    t, profile, sku = built
    b = with_(basis, "flows", inbound_mode="receipts", inbound_peak_factor=1.3)
    with pytest.raises(ConfigError, match="receipts_pallets"):
        derive_inbound(profile, b, t.daily.drop("receipts_pallets"), sku, catalog=catalog)


def test_catalog_is_required_whatever_the_working_directory(
    built, basis, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    t, profile, sku = built
    for cwd in (ROOT, tmp_path):
        monkeypatch.chdir(cwd)
        with pytest.raises(ConfigError, match="catalog"):
            select_design_day(profile, basis, t.daily, sku=sku)
        with pytest.raises(ConfigError, match="catalog"):
            derive_inbound(profile, basis, t.daily, sku)


def test_explicit_catalog_gives_the_same_result_from_any_directory(
    built, basis, catalog, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    here = design(built, basis, catalog)
    monkeypatch.chdir(tmp_path)
    assert design(built, basis, catalog) == here


def test_I58_engine_sku_frame_with_extra_columns_accepted(built, basis, catalog) -> None:
    t, profile, sku = built
    master = pl.read_parquet(DATA / "sku_master.parquet").with_columns(
        hazmat=pl.when(pl.col("sku").str.ends_with("1")).then(None).otherwise(False),
        temperature_class=pl.when(pl.col("sku").str.ends_with("2"))
        .then(None)
        .otherwise(pl.lit("ambient"))
        .cast(pl.Categorical),
    )
    engine = with_pack_data(t.skus, master).join(
        master.select("sku", "hazmat", "temperature_class"), on="sku", how="left"
    )
    orphan = engine.head(1).with_columns(  # a stock-only orphan row without master data
        sku=pl.lit("ORPHAN-X"),
        has_dims=pl.lit(False),
        orphan=pl.lit(True),
        lines=pl.lit(0, pl.UInt32),
        units=pl.lit(0, pl.Int64),
        units_per_pallet=pl.lit(None, pl.Int64),
        units_per_case=pl.lit(None, pl.Int64),
        cases_per_pallet=pl.lit(None, pl.Int64),
        hazmat=pl.lit(None, pl.Boolean),
    )
    engine = pl.concat([engine, orphan])
    assert {"hazmat", "temperature_class", "has_dims", "orphan", "abc"} <= set(engine.columns)
    plain = derive_inbound(profile, basis, t.daily, sku, catalog=catalog)
    assert derive_inbound(profile, basis, t.daily, engine, catalog=catalog) == plain
    dd = select_design_day(profile, basis, t.daily, sku=engine, catalog=catalog)
    assert dd == design(built, basis, catalog)
    # with_pack_data on a frame that already carries the pack columns keeps them, no _right
    again = with_pack_data(engine, master)
    assert not [c for c in again.columns if c.endswith("_right")]
    assert derive_inbound(profile, basis, t.daily, again, catalog=catalog) == plain


# --- F4b fix round 1: overrides.stock_growth_rate, growth overflow, inbound_peak_factor label ---


@pytest.mark.parametrize("value", [-1.0, -5.0, NAN, INF])
def test_I60_stock_growth_rate_override_must_exceed_minus_one(basis, value: float) -> None:
    bad = basis.model_copy(update={"overrides": {"stock_growth_rate": value}})
    with pytest.raises(ConfigError, match=r"overrides\.stock_growth_rate"):
        check_basis(bad)


def test_I60_load_basis_rejects_stock_growth_rate_override_le_minus_one(tmp_path: Path) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    assert "overrides" not in text
    path = tmp_path / "basis.yaml"
    path.write_text(text + "\noverrides:\n  stock_growth_rate: -5.0\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"overrides\.stock_growth_rate = -5\.0"):
        load_basis(path)


def test_I60_stock_growth_rate_override_above_minus_one_accepted(basis) -> None:
    ok = basis.model_copy(update={"overrides": {"stock_growth_rate": -0.5}})
    assert check_basis(ok) is ok


@pytest.mark.parametrize(("rate", "years"), [(1e308, 5), (0.5, 5000)])
def test_growth_factor_overflow_raises_config_error(rate: float, years: int) -> None:
    with pytest.raises(ConfigError, match="overflow"):
        growth_factor(rate, years)


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_I56_template_label_states_both_inbound_modes(lang: str) -> None:
    text = (ROOT / "basis" / f"template_{lang}.yaml").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if "inbound_peak_factor:" in x)
    assert ("receipts mode" if lang == "en" else "mode réceptions") in line
    assert ("1.0" if lang == "en" else "1,0") in line


# --- F4c: residual validation gaps (F4b audit open issues 1, 2, 4, 9) ------------------------

HUGE = 1e308  # finite, > -1: passes the I60 ranges, but × any design quantity overflows


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"projection": {"growth_rate": HUGE, "horizon_years": 1}}, r"design_day\.lines = inf"),
        (
            {"projection": {"horizon_years": 1}, "overrides": {"stock_growth_rate": HUGE}},
            r"design_day\.stock_units = inf.*overrides\.stock_growth_rate",
        ),
        ({"flows": {"pallets_per_truck": 5e-324}}, r"inbound\.trucks_per_day = inf"),
    ],
)
def test_I60_finite_but_huge_basis_value_never_gives_inf(
    built, basis, catalog, update: dict[str, Any], match: str
) -> None:
    b = basis
    for section, values in update.items():
        b = (
            b.model_copy(update={section: values})
            if section == "overrides"
            else with_(b, section, **values)
        )
    with pytest.raises(ConfigError, match=match):
        design(built, b, catalog)


def test_I60_huge_growth_named_by_derive_inbound(built, basis, catalog) -> None:
    t, profile, sku = built
    b = with_(basis, "projection", growth_rate=HUGE, horizon_years=1)
    with pytest.raises(ConfigError, match=r"inbound\.units_per_day = inf.*projection\.growth_rate"):
        derive_inbound(profile, b, t.daily, sku, catalog=catalog)


def test_I60_realistic_growth_gives_finite_design_values(built, basis, catalog) -> None:
    dd = design(built, with_(basis, "projection", growth_rate=0.5, horizon_years=30), catalog)
    values = [dd.lines, dd.stock_units, dd.stock_cube_m3, dd.inbound.units_per_day]
    assert all(np.isfinite(values)) and dd.lines > 0


@pytest.mark.parametrize(
    ("entry", "shown"),
    [
        ("stock_growth_rate: true", "True"),  # YAML bool, not 1.0
        ("stock_growth_rate: false", "False"),
        ("manual_p2p.pick_rate_shelving_lines_h: .nan", "nan"),
        ("manual_p2p.pick_rate_shelving_lines_h: .inf", "inf"),
    ],
)
def test_I60_override_values_must_be_real_numbers(tmp_path: Path, entry: str, shown: str) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    path = tmp_path / "basis.yaml"
    path.write_text(f"{text}\noverrides:\n  {entry}\n", encoding="utf-8")
    pid = entry.split(":")[0]
    with pytest.raises(ConfigError, match=rf"overrides\.{pid} = {shown} \(must be a finite number"):
        load_basis(path)


def test_I60_override_bool_rejected_on_a_model_too(basis) -> None:
    with pytest.raises(ConfigError, match=r"overrides\.stock_growth_rate = True"):
        check_basis(basis.model_copy(update={"overrides": {"stock_growth_rate": True}}))


def test_I60_integer_and_float_overrides_accepted(tmp_path: Path) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    path = tmp_path / "basis.yaml"
    path.write_text(
        f"{text}\noverrides:\n  stock_growth_rate: 0\n"
        "  manual_p2p.pick_rate_shelving_lines_h: 62\n",
        encoding="utf-8",
    )
    b = load_basis(path)
    assert b.overrides == {"stock_growth_rate": 0.0, "manual_p2p.pick_rate_shelving_lines_h": 62.0}


@pytest.mark.parametrize(
    ("entry", "value"),
    [
        ("stock_growth_rate: 1e-2", 0.01),  # PyYAML (YAML 1.1) reads a dot-less exponent as text
        ("stock_growth_rate: 1.0e-2", 0.01),
        ('stock_growth_rate: "0.5"', 0.5),  # numeric text, coerced like any typed basis field
    ],
)
def test_I60_override_numeric_text_accepted_like_typed_fields(
    tmp_path: Path, entry: str, value: float
) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    path = tmp_path / "basis.yaml"
    path.write_text(f"{text}\noverrides:\n  {entry}\n", encoding="utf-8")
    assert load_basis(path).overrides == {"stock_growth_rate": value}
    typed = tmp_path / "typed.yaml"
    typed.write_text(text.replace("growth_rate: 0.04", "growth_rate: 4e-2"), encoding="utf-8")
    assert load_basis(typed).projection.growth_rate == 0.04  # same notation, typed field


def test_I60_non_numeric_override_text_rejected(tmp_path: Path) -> None:
    text = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    path = tmp_path / "basis.yaml"
    path.write_text(f'{text}\noverrides:\n  stock_growth_rate: "abc"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"overrides\.stock_growth_rate"):
        load_basis(path)


INBOUND_IDS = (
    "engine.receipt_lines_per_pallet_full",
    "engine.receipt_lines_per_pallet_mixed",
    "storage.default_units_per_pallet",
)


@pytest.mark.parametrize("value", [-5.0, 0.0])
@pytest.mark.parametrize("pid", INBOUND_IDS)
def test_I60_inbound_catalog_values_must_be_positive(
    built, basis, catalog, pid: str, value: float
) -> None:
    """A catalog constant override is stored as given (ParamSet widens no range for constants):
    a negative receipt-lines-per-pallet used to give negative receipt lines with no error."""
    b = basis.model_copy(update={"overrides": {pid: value}})
    with pytest.raises(ConfigError, match=rf"{pid.replace('.', r'\.')} = {value}"):
        design(built, b, catalog)


def test_I60_inbound_overflow_names_the_catalog_override(built, basis, catalog) -> None:
    pid = "engine.receipt_lines_per_pallet_mixed"
    b = with_(basis, "projection", growth_rate=1.0)  # > 1 pallet/day: × HUGE overflows
    b = b.model_copy(update={"overrides": {pid: HUGE}})
    with pytest.raises(ConfigError, match=r"inbound\.receipt_lines_per_day = inf.*" + pid):
        design(built, b, catalog)


@pytest.mark.parametrize(
    ("lang", "words"), [("en", "12 calendar months"), ("fr", "12 mois calendaires")]
)
def test_I55_template_states_calendar_month_warning(lang: str, words: str) -> None:
    text = (ROOT / "basis" / f"template_{lang}.yaml").read_text(encoding="utf-8")
    line = next(x for x in text.splitlines() if "trailing_months:" in x)
    assert words in line
