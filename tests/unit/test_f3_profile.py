"""F3 demand profiling: T3.2-T3.5 and the definitions / edge cases of the F3 section."""

from __future__ import annotations

import json
import math
import warnings
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from whsizing.config import load_yaml_model
from whsizing.errors import ConfigError, DataQualityError, WhsizingError
from whsizing.io.canonical import validate
from whsizing.io.rules import _shorter  # pyright: ignore[reportPrivateUsage]
from whsizing.profile import (
    ProfileTables,
    build_profile,
    build_tables,
    profile_from_tables,
    write_profile,
)
from whsizing.profile.abc import CLASSES, class_stats, classify
from whsizing.profile.aggregate import (
    fsum_by,
    orders_table,
    series_stats,
    shipped_lines,
    sku_table,
    validate_daily,
    with_cube,
)
from whsizing.profile.charts import CHARTS
from whsizing.profile.seasonality import seasonality
from whsizing.profile.shipments import shipment_split, split_orders
from whsizing.profile.stock import EMPTY_INVENTORY, stock_stats
from whsizing.schemas import (
    AbcClassStats,
    DemandProfile,
    DesignBasis,
    Flows,
    ProfileCfg,
    SeriesStats,
)
from whsizing.synth import generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
TZ = "Europe/Paris"


def write_frames(d: Path, frames: dict[str, pl.DataFrame]) -> Path:
    """Write the frames as canonical Parquet; hand-built order_lines get the §4.1 provenance
    columns (source_file, source_row) that load_canonical's validation requires."""
    d.mkdir(parents=True, exist_ok=True)
    lines = frames["order_lines"]
    if "source_file" not in lines.columns:
        lines = lines.with_columns(source_file=pl.lit("t.csv"), source_row=pl.int_range(pl.len()))
    for name, df in (frames | {"order_lines": lines}).items():
        df.write_parquet(d / f"{name}.parquet")
    return d


def built(d: Path, cfg: ProfileCfg | None = None) -> tuple[DemandProfile, ProfileTables]:
    cfg = cfg or ProfileCfg()
    t = build_tables(d, None, cfg)
    return profile_from_tables(t, cfg), t


@pytest.fixture(scope="module")
def golden() -> tuple[DemandProfile, ProfileTables]:
    cfg = ProfileCfg()
    t = build_tables(
        GOLDEN / "tiny_golden", load_yaml_model(GOLDEN / "golden_basis.yaml", DesignBasis), cfg
    )
    return profile_from_tables(t, cfg), t


@pytest.fixture(scope="module")
def small_synth(tmp_path_factory: pytest.TempPathFactory) -> tuple[DemandProfile, ProfileTables]:
    """ecom_mid shape (2 years, no Sunday volume, monthly snapshots) at 40 orders/day."""
    prof = load_synth_profile(ROOT / "data/synth/profiles/ecom_mid.yaml")
    prof = prof.model_copy(update={"n_skus": 300, "orders_per_day_mean": 40.0})
    return built(write_frames(tmp_path_factory.mktemp("small_synth"), generate(prof, seed=7)))


# --- T3.2 - T3.5 ------------------------------------------------------------------------------
@pytest.mark.parametrize("data", ["golden", "small_synth"])
def test_T3_2_abc_shares_sum_to_one_and_class_A_line_share(
    data: str, request: pytest.FixtureRequest
) -> None:
    p, _ = request.getfixturevalue(data)
    for by in (p.abc.by_lines, p.abc.by_cube_movement, p.abc.by_stock_cube):
        assert set(by) == {"A", "B", "C"}
        for share in ("sku_share", "line_share", "cube_share"):
            assert sum(getattr(c, share) for c in by.values()) == pytest.approx(1.0, abs=1e-12)
    assert p.abc.by_lines["A"].line_share >= 0.8 - 1e-9
    assert p.abc.by_cube_movement["A"].cube_share >= 0.8 - 1e-9
    assert p.abc.by_stock_cube["A"].cube_share >= 0.8 - 1e-9
    assert p.abc.by_lines["A"].line_share + p.abc.by_lines["B"].line_share >= 0.95 - 1e-9
    curve = np.array(p.abc.pareto_lines)
    assert len(curve) == 100 and curve[-1] == pytest.approx(1.0)
    assert np.all(np.diff(curve) >= -1e-12)
    assert curve[int(100 * p.abc.by_lines["A"].sku_share) - 1] <= p.abc.by_lines["A"].line_share


def test_T3_3_monthly_indices_average_to_one(
    small_synth: tuple[DemandProfile, ProfileTables],
) -> None:
    p, t = small_synth
    op = t.daily.filter("is_operating")
    n_op = op.group_by(pl.col("date").dt.month()).len().sort("date")["len"].to_numpy()
    idx = np.array(p.seasonality.monthly_index, dtype=float)
    assert idx.size == 12 and not np.isnan(idx).any()
    assert float(np.sum(idx * n_op) / n_op.sum()) == pytest.approx(1.0, abs=1e-12)
    assert idx[11] > idx[7]  # ecom_mid month index: December peak 1.6 vs August 0.75


@pytest.mark.parametrize("data", ["golden", "small_synth"])
def test_T3_4_intraday_shares_sum_to_one_per_weekday(
    data: str, request: pytest.FixtureRequest
) -> None:
    p, t = request.getfixturevalue(data)
    op_weekdays = set(t.daily.filter("is_operating")["weekday"].to_list())
    assert set(p.intraday) == op_weekdays
    for shares in p.intraday.values():
        assert len(shares) == 24 and min(shares) >= 0
        assert sum(shares) == pytest.approx(1.0, abs=1e-12)
    wd = int(np.argmax(p.seasonality.weekday_index))
    assert p.peak_hour_share == max(p.intraday[wd])


def test_T3_5_shipment_split_400kg_order_is_pallet() -> None:
    orders = pl.DataFrame(
        {
            "order_id": ["heavy", "light", "two_parcels", "bulky"],
            "n_lines": [3, 1, 2, 1],
            "weight_kg": [400.0, 29.0, 31.0, 5.0],
            "cube_m3": [0.1, 0.05, 0.1, 0.7],
        }
    )
    s = split_orders(orders, Flows())  # [P] 300 kg / 0.6 m3 / 30 kg per parcel
    assert s["is_pallet"].to_list() == [True, False, False, True]
    assert s["pallets"].to_list() == [1, 0, 0, 1]  # I8: one pallet per pallet order
    assert s["parcels"].to_list() == [0, 1, 2, 0]
    split = shipment_split(s)
    assert split.pallet_share_orders == 0.5 and split.parcel_share_orders == 0.5
    assert split.pallet_share_lines == pytest.approx(4 / 7)
    assert split.mean_parcels_per_order == 1.5


def test_parcels_use_true_division_whatever_the_chunk_layout() -> None:
    """F3d: polars divides by a scalar with a reciprocal multiply except on a length-1 chunk
    (orders sorted at 12 threads: 513 orders → [256, 256, 1]), so 30.000000000000004 kg gave 1
    parcel on one chunk and 2 on the last chunk. ceil(weight / 30) = 2 like the oracle."""
    w = 30.000000000000004
    assert math.ceil(w / 30) == 2 and math.ceil(w * (1 / 30)) == 1
    orders = pl.DataFrame({"n_lines": [1] * 3, "weight_kg": [1.0, 2.0, w], "cube_m3": [0.0] * 3})
    chunked = pl.concat([orders[:2], orders[2:]], rechunk=False)
    assert chunked["weight_kg"].n_chunks() == 2
    for df in (orders, chunked):
        assert split_orders(df, Flows())["parcels"].to_list() == [1, 1, 2]


# --- definitions and edge cases -------------------------------------------------------------
def _local(ts: str) -> pl.Expr:
    return pl.lit(ts).str.to_datetime().dt.replace_time_zone(TZ).dt.convert_time_zone("UTC")


def mini_frames() -> dict[str, pl.DataFrame]:
    """2025-04-28 → 2025-05-10 (Paris): 20 one-line orders at 10:00 on Mon-Fri, 1 on Saturdays,
    none on 05-01 (Fête du travail) and Sundays; 05-08 (Victoire 1945) has volume."""
    rows = []
    day = date(2025, 4, 28)
    while day <= date(2025, 5, 10):
        n = 0 if day.weekday() == 6 or day == date(2025, 5, 1) else 1 if day.weekday() == 5 else 20
        rows += [(f"{day}-{i}", f"{day} 10:00", "A", 2, "shipped") for i in range(n)]
        day += timedelta(days=1)
    rows += [
        ("multi", "2025-04-30 23:30", "B", 1, "shipped"),  # multi-day order: first ts wins
        ("multi", "2025-05-02 08:00", "Z", 1, "shipped"),  # orphan SKU (not in the master)
        ("cancel", "2025-05-02 09:00", "A", 5, "cancelled"),
        ("ret-1", "2025-05-06 11:00", "A", -1, "returned"),  # fresh id: never an order
    ]
    lines = pl.DataFrame(
        rows, schema=["order_id", "ts", "sku", "qty_units", "line_status"], orient="row"
    )
    lines = lines.with_columns(
        order_ts=pl.col("ts")
        .str.to_datetime()
        .dt.replace_time_zone(TZ)
        .dt.convert_time_zone("UTC"),
        line_status=pl.col("line_status").cast(pl.Categorical),
    ).drop("ts")
    master = pl.DataFrame(
        {"sku": ["A", "B", "C"], "length_mm": [100.0, 200.0, 100.0], "width_mm": [100.0] * 3,
         "height_mm": [100.0] * 3, "weight_kg": [1.0, 40.0, 1.0]}
    )  # fmt: skip
    inventory = pl.DataFrame(
        {"sku": ["A", "C", "A", "C", "A", "C"], "qty_units": [60, 10, 160, 10, 260, 10],
         "snapshot_date": [date(2025, 1, 31)] * 2 + [date(2025, 3, 2)] * 2 + [date(2025, 4, 1)] * 2}
    )  # fmt: skip
    return {"order_lines": lines, "sku_master": master, "inventory": inventory}


@pytest.fixture
def mini(tmp_path: Path) -> Path:
    return write_frames(tmp_path / "canonical", mini_frames())


def test_definitions_orders_lines_returns_and_calendar(mini: Path) -> None:
    p, t = built(mini, ProfileCfg(holiday_overrides=[date(2025, 5, 5)]))
    d = {r["date"]: r for r in t.daily.iter_rows(named=True)}
    assert t.daily.height == 13 and p.period_start == date(2025, 4, 28)
    assert int(t.daily["orders"].sum()) == 9 * 20 + 2 + 1  # returns and cancels are not orders
    assert int(t.daily["lines"].sum()) == 9 * 20 + 2 + 2  # cancelled line excluded
    assert d[date(2025, 4, 30)]["lines"] == 22  # both lines of the multi-day order
    assert d[date(2025, 5, 6)]["return_lines"] == 1 and t.daily["return_lines"].sum() == 1
    holiday, victory, saturday = d[date(2025, 5, 1)], d[date(2025, 5, 8)], d[date(2025, 5, 3)]
    assert holiday["is_holiday"] and not holiday["is_operating"]
    assert victory["is_holiday"] and victory["is_operating"]  # holiday with volume (I2)
    assert d[date(2025, 5, 5)]["is_holiday"]  # override
    assert not saturday["is_operating"]  # 1 line < max(1, 0.10 × median 20) = 2
    assert not d[date(2025, 5, 4)]["is_operating"]  # Sunday
    assert p.operating_days == 9 and set(p.intraday) == {0, 1, 2, 3, 4}
    assert p.intraday[2][23] > 0  # multi-day order keeps its first hour
    assert p.dims_coverage_lines == pytest.approx(1 - 1 / 184)  # one orphan line
    assert p.daily["lines"].p50 == 20 and p.seasonality.weekday_index[5] == 0.0


def test_stock_cover_dead_stock_and_growth(mini: Path) -> None:
    p, _ = built(mini, ProfileCfg(dead_stock_days=180))
    s = p.stock
    assert s.n_snapshots == 3 and s.last_snapshot == date(2025, 4, 1) and s.confidence == "H"
    assert s.avg_units == pytest.approx(160 + 10)
    assert s.cover_days == pytest.approx(170 / p.daily["units"].mean)
    assert s.dead_stock_skus == 1  # C: stock, never shipped
    assert s.dead_stock_cube_m3 == pytest.approx(10 * 0.001)
    assert s.growth_units_per_year == pytest.approx(100 / 30 * 365.25)  # +100 units per 30 days


def test_single_snapshot_has_no_growth_and_missing_inventory_is_low_confidence(
    mini: Path,
) -> None:
    inv = pl.read_parquet(mini / "inventory.parquet")
    inv.filter(pl.col("snapshot_date") == date(2025, 4, 1)).write_parquet(
        mini / "inventory.parquet"
    )
    assert built(mini)[0].stock.growth_units_per_year is None
    (mini / "inventory.parquet").unlink()
    s = built(mini)[0].stock
    # I49: no inventory → 0 stock per SKU → Σ stock / mean units = 0.0 (oracle stock.cover_days)
    assert s.n_snapshots == 0 and s.confidence == "L" and s.cover_days == 0.0


def test_lines_without_time_fall_back_to_default_intraday(tmp_path: Path) -> None:
    frames = mini_frames()
    midnight = (
        pl.col("order_ts").dt.convert_time_zone(TZ).dt.truncate("1d").dt.convert_time_zone("UTC")
    )
    frames["order_lines"] = frames["order_lines"].with_columns(order_ts=midnight)
    cfg = ProfileCfg()
    p, _ = built(write_frames(tmp_path, frames), cfg)
    assert p.intraday_confidence == "L"
    assert all(v == cfg.default_intraday for v in p.intraday.values())
    assert p.peak_hour_share == pytest.approx(1 / 9)


def test_no_shipped_lines_and_unknown_country_raise(mini: Path) -> None:
    with pytest.raises(ConfigError, match="holiday_country"):
        build_profile(mini, None, ProfileCfg(holiday_country="XX"))
    lines = pl.read_parquet(mini / "order_lines.parquet")
    lines.filter(pl.col("qty_units") < 0).write_parquet(mini / "order_lines.parquet")
    with pytest.raises(DataQualityError, match="no shipped order lines"):
        build_profile(mini, None, ProfileCfg())


def test_per_group_float_sums_are_exact_so_independent_of_the_adding_order() -> None:
    """F3c issue 1: polars adds a group's floats in a thread-count-dependent order (last-ULP
    drift between machines); fsum_by gives the exact sum, which no order can change."""
    df = pl.DataFrame({"k": ["b"] * 3 + ["a"] * 10, "w": [1e16, 1.0, -1e16] + [0.1] * 10})
    assert np.cumsum([0.1] * 10)[-1] != 1.0 and 1e16 + 1.0 - 1e16 == 0.0  # naive sums drift
    assert fsum_by(df, "k", ("w",)).rows() == [("a", 1.0), ("b", 1.0)]


def test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout() -> None:
    """F3d: sorts split frames into thread-count chunks ([256, 256, 1] for 513 SKUs at 24
    threads) and `Series.sum` adds per chunk, so stock.avg_units moved in the last ULP with the
    thread count. Stock and ABC sums are exact: the same on one chunk and on three."""
    n = 513
    avg = [(i * 37 % 1000) / 7 for i in range(n)]  # one chunk sums to ...71, three to ...72
    skus = pl.DataFrame(
        {
            "sku": [f"s{i:03d}" for i in range(n)],
            "avg_stock": avg,
            "last_stock": [i % 5 for i in range(n)],
            "unit_cube_m3": [(i % 17 + 1) / 7000 for i in range(n)],
            "last_line_date": pl.Series([None] * n, dtype=pl.Date),
            "lines": [i % 11 for i in range(n)],
            "abc": [CLASSES[i % 3] for i in range(n)],
        }
    ).with_columns(stock_cube_m3=pl.col("avg_stock") * pl.col("unit_cube_m3"))
    chunked = pl.concat([skus[:256], skus[256:512], skus[512:]], rechunk=False)
    assert chunked["avg_stock"].n_chunks() == 3 and skus["avg_stock"].n_chunks() == 1
    assert skus["avg_stock"].sum() != chunked["avg_stock"].sum()  # the drift being fixed

    stock = [stock_stats(df, EMPTY_INVENTORY, date(2025, 1, 1), 10.0, 90) for df in (skus, chunked)]
    assert stock[0] == stock[1] and stock[0].avg_units == math.fsum(avg)
    assert class_stats(skus, "avg_stock") == class_stats(chunked, "avg_stock")  # drifting floats
    by = ("stock_cube_m3", (0.8, 0.95))
    assert classify(skus, *by).equals(classify(chunked, *by))


def _null_sku(value: str) -> Callable[[pl.DataFrame], pl.DataFrame]:
    return lambda df: df.with_columns(sku=pl.when(pl.col("sku") != value).then("sku"))


@pytest.mark.parametrize(
    ("table", "change", "match"),
    [
        ("order_lines", lambda df: df.drop("order_ts"), 'find column "order_ts"'),
        ("order_lines", lambda df: df.drop("sku"), 'find column "sku"'),
        ("order_lines", lambda df: df.drop("qty_units"), 'find column "qty_units"'),
        (
            "order_lines",
            lambda df: df.with_columns(pl.col("qty_units").cast(pl.String) + "x"),
            "coerce 'qty_units'",
        ),
        (
            "order_lines",
            lambda df: df.with_columns(pl.col("order_ts").dt.replace_time_zone(None)),
            "'order_ts' to have type",
        ),
        ("order_lines", _null_sku("B"), "'sku' contains null"),
        ("inventory", _null_sku("C"), "'sku' contains null"),
        ("sku_master", lambda df: df.drop("weight_kg"), 'find column "weight_kg"'),
    ],
)
def test_invalid_canonical_table_raises_whsizing_error(
    mini: Path, table: str, change: Callable[[pl.DataFrame], pl.DataFrame], match: str
) -> None:
    """F3c issue 2: a missing column, an uncoercible dtype or a null sku (which was counted as
    an SKU in ABC) raises a whsizing error naming the column, never a raw polars error or a
    silent profile."""
    path = mini / f"{table}.parquet"
    change(pl.read_parquet(path)).write_parquet(path)
    with pytest.raises(WhsizingError, match=f"canonical {table}.*{match}"):  # F3d: names the table
        build_profile(mini, None, ProfileCfg())


@pytest.mark.parametrize(
    ("table", "col"),
    [
        ("order_lines", "order_ts"),
        ("order_lines", "sku"),
        ("order_lines", "qty_units"),
        ("sku_master", "weight_kg"),
        ("inventory", "snapshot_date"),
    ],
)
def test_I72_missing_required_column_has_one_wording_in_both_layers(
    mini: Path, table: str, col: str
) -> None:
    """I72 (F2e open issue 2, F3e open issue 2): the canonical column check reads the same
    whichever column or table: F2 `validate` gives `canonical <table>: cannot find column
    "<col>" (required by §4.1)`, F3 `load_canonical` re-raises it with `(in <dir>)` (the
    old `except ColumnNotFoundError` branch was unreachable and dropped the directory). A plain
    WhsizingError, exit 1, never DataQualityError (exit 3)."""
    path = mini / f"{table}.parquet"
    frame = pl.read_parquet(path).drop(col)
    frame.write_parquet(path)
    wording = f'canonical {table}: cannot find column "{col}" (required by §4.1)'
    with pytest.raises(WhsizingError) as f2:
        validate({table: frame})
    assert str(f2.value) == wording and f2.value.exit_code == 1
    with pytest.raises(WhsizingError) as f3:
        build_profile(mini, None, ProfileCfg())
    assert type(f3.value) is WhsizingError and f3.value.exit_code == 1
    assert str(f3.value) == f"{wording} (in {mini})"
    assert isinstance(f3.value.__cause__, WhsizingError)


def test_load_canonical_corrupt_parquet_is_a_whsizing_error(mini: Path) -> None:
    """R3 fix round 1, finding 3: a truncated canonical parquet escaped as polars' ComputeError
    (no exit code, not a §2.7 class). Now WhsizingError (exit 1) naming the table and the file,
    for a required table (order_lines) and an optional one (inventory)."""
    for table in ("inventory", "order_lines"):
        path = mini / f"{table}.parquet"
        path.write_bytes(path.read_bytes()[:40])  # cut the footer (the "PAR1" ending)
        with pytest.raises(WhsizingError) as e:
            build_profile(mini, None, ProfileCfg())
        assert type(e.value) is WhsizingError and e.value.exit_code == 1
        assert f"canonical {table}: cannot read {path}" in str(e.value)
        assert isinstance(e.value.__cause__, pl.exceptions.PolarsError)
        path.unlink()  # drop the corrupt file so the next table is the only corrupt one


def test_write_profile_artifacts(
    golden: tuple[DemandProfile, ProfileTables], tmp_path: Path
) -> None:
    p, t = golden
    paths = write_profile(p, tmp_path, t)
    assert (
        DemandProfile.model_validate_json(
            (tmp_path / "profile/demand_profile.json").read_text(encoding="utf-8")
        )
        == p
    )
    daily = pl.read_parquet(tmp_path / p.daily_series_path)
    assert p.daily_series_path == "canonical/daily_series.parquet"
    assert daily.columns == [
        "date", "weekday", "is_operating", "is_holiday", "orders", "lines", "units", "cube_m3",
        "weight_kg", "parcels", "pallets_out", "return_lines", "receipts_lines", "receipts_units",
        "receipts_pallets",
    ]  # fmt: skip
    assert int(daily["pallets_out"].sum()) == 39  # golden basis: 39 pallet orders
    assert daily["receipts_lines"].sum() == 233  # tiny_golden README
    charts = tmp_path / "profile" / "charts"
    for name in CHARTS:
        assert (charts / f"{name}.png").read_bytes()[:4] == b"\x89PNG"
        assert "plotly.min.js" in (charts / f"{name}.html").read_text(encoding="utf-8")
    assert (charts / "plotly.min.js").is_file()  # local bundle: no CDN, data stays offline
    assert len(paths) == 2 + 2 * 8
    assert json.loads((tmp_path / "profile/demand_profile.json").read_text())["intraday"]["0"]


# --- audit fixes (round 1) --------------------------------------------------------------------
def test_stock_only_sku_is_an_orphan_counted_in_stock_and_dead_stock(tmp_path: Path) -> None:
    """A SKU in stock but in neither the master nor the shipped lines (discontinued) is kept."""
    frames = mini_frames()
    ghost = pl.DataFrame(
        {"sku": ["GHOST"], "qty_units": [600], "snapshot_date": [date(2025, 4, 1)]}
    )
    frames["inventory"] = pl.concat([frames["inventory"], ghost])
    p, t = built(write_frames(tmp_path, frames))
    row = t.skus.filter(pl.col("sku") == "GHOST").row(0, named=True)
    assert row["orphan"] and not row["has_dims"] and row["lines"] == 0
    assert p.stock.avg_units == pytest.approx(170 + 600 / 3)
    assert p.stock.n_skus_in_stock == 3 and p.stock.dead_stock_skus == 2  # C and GHOST


def test_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero(tmp_path: Path) -> None:
    """F3 step 5 'average over snapshots': C only in the last of 3 snapshots → 30 / 3."""
    frames = mini_frames()
    inv = frames["inventory"]
    frames["inventory"] = inv.filter(
        (pl.col("sku") == "A") | (pl.col("snapshot_date") == date(2025, 4, 1))
    ).with_columns(qty_units=pl.when(pl.col("sku") == "C").then(30).otherwise("qty_units"))
    p, t = built(write_frames(tmp_path, frames))
    assert t.skus.filter(pl.col("sku") == "C")["avg_stock"].item() == pytest.approx(10.0)
    assert p.stock.avg_units == pytest.approx(160 + 10)


@pytest.mark.parametrize(
    ("snapshot", "conf"), [(date(2024, 11, 10), "H"), (date(2024, 11, 9), "L")]
)
def test_stale_snapshot_uses_the_F2_R14_six_month_rule(
    tmp_path: Path, snapshot: date, conf: str
) -> None:
    """period_end 2025-05-10: a snapshot older than 2024-11-10 (6 calendar months) → L."""
    frames = mini_frames()
    frames["inventory"] = frames["inventory"].with_columns(snapshot_date=pl.lit(snapshot))
    assert built(write_frames(tmp_path, frames))[0].stock.confidence == conf


def test_receipts_pallets_null_when_unknown_never_an_undercount(tmp_path: Path) -> None:
    """Receipts on 29/04 (r1, r2) and 30/04 (r3). Unknown pallets (no column, or a null on one
    receipt) make that day's receipts_pallets null; a day without receipts has 0 pallets."""
    frames = mini_frames()
    frames["receipts"] = pl.DataFrame(
        {"receipt_id": ["r1", "r2", "r3"], "sku": ["A"] * 3, "qty_units": [10, 20, 5],
         "receipt_ts": [datetime(2025, 4, 29, 8, tzinfo=UTC)] * 2
         + [datetime(2025, 4, 30, 8, tzinfo=UTC)]}
    )  # fmt: skip

    def pallets() -> dict[date, float | None]:
        daily = built(write_frames(tmp_path, frames))[1].daily
        validate_daily(daily)  # the daily_series.parquet schema accepts the nulls
        return dict(zip(daily["date"], daily["receipts_pallets"], strict=True))

    daily = built(write_frames(tmp_path, frames))[1].daily
    day = daily.filter(pl.col("date") == date(2025, 4, 29)).row(0, named=True)
    assert (day["receipts_lines"], day["receipts_units"]) == (2.0, 30.0)
    assert daily["receipts_pallets"].dtype == pl.Float64
    p = pallets()  # no pallets column
    assert p[date(2025, 4, 29)] is None and p[date(2025, 4, 30)] is None
    assert p[date(2025, 5, 2)] == 0.0
    frames["receipts"] = frames["receipts"].with_columns(pallets=pl.Series([1.0, None, 0.5]))
    p = pallets()
    assert p[date(2025, 4, 29)] is None  # r2 unknown: not 1.0
    assert p[date(2025, 4, 30)] == 0.5 and p[date(2025, 5, 2)] == 0.0
    frames["receipts"] = frames["receipts"].with_columns(pallets=pl.lit(1.0))
    p = pallets()
    assert p[date(2025, 4, 29)] == 2.0 and sum(v or 0.0 for v in p.values()) == 3.0
    assert None not in p.values()


def test_lines_without_time_below_the_switch_are_left_out_of_the_hourly_shares(
    tmp_path: Path,
) -> None:
    """Fridays all at local midnight, plus order '-0' of every day: 49 / 184 lines without
    time (< 0.5). They must not land in hour 0; Friday has no timed line → default profile."""
    frames = mini_frames()
    local = pl.col("order_ts").dt.convert_time_zone(TZ)
    no_time = (local.dt.weekday() == 5) | pl.col("order_id").str.ends_with("-0")
    midnight = local.dt.truncate("1d").dt.convert_time_zone("UTC")
    frames["order_lines"] = frames["order_lines"].with_columns(
        order_ts=pl.when(no_time).then(midnight).otherwise("order_ts")
    )
    cfg = ProfileCfg(no_time_share_max=0.5)
    p, _ = built(write_frames(tmp_path, frames), cfg)
    assert p.intraday_confidence == "H"
    assert p.intraday[4] == cfg.default_intraday
    assert all(p.intraday[wd][0] == 0 for wd in (0, 1, 2, 3))
    assert p.peak_hour_share == pytest.approx(38 / 40)  # Wednesday: 38 at 10:00, 2 at 23:00
    assert all(sum(v) == pytest.approx(1.0) for v in p.intraday.values())


def test_sub_second_after_local_midnight_is_a_line_without_time() -> None:
    """I51 '00:00:00' to the second, like the oracle's hour/minute/second test."""
    local = [datetime(2025, 3, 3, 0, 0, 0, us) for us in (0, 1, 500_000)]
    local += [datetime(2025, 3, 3, 0, 0, 1), datetime(2025, 3, 3, 10)]
    ts = pl.Series(local).dt.replace_time_zone(TZ).dt.convert_time_zone("UTC")
    lines = pl.DataFrame(
        {"order_id": [f"o{i}" for i in range(5)], "sku": "A", "qty_units": 1, "order_ts": ts}
    )
    no_time = shipped_lines(lines, TZ).sort("order_id")["no_time"].to_list()
    assert no_time == [True, True, True, False, False]


def _weekday_daily(start: date, end: date) -> pl.DataFrame:
    """20 lines on every Monday-Friday, none at weekends."""
    d = pl.DataFrame({"date": pl.date_range(start, end, eager=True)})
    wd = pl.col("date").dt.weekday().cast(pl.Int64) - 1
    return d.with_columns(
        weekday=wd, is_operating=wd < 5, lines=pl.when(wd < 5).then(20.0).otherwise(0.0)
    )


def test_two_full_calendar_years_give_trend_confidence_M_and_flat_demand_no_trend() -> None:
    assert seasonality(_weekday_daily(date(2025, 1, 1), date(2026, 12, 31))).trend_confidence == "M"
    assert seasonality(_weekday_daily(date(2024, 1, 1), date(2025, 12, 31))).trend_confidence == "M"
    assert seasonality(_weekday_daily(date(2025, 1, 2), date(2026, 12, 31))).trend_confidence == "L"
    flat = seasonality(_weekday_daily(date(2025, 1, 25), date(2026, 12, 31)))  # partial January
    assert flat.trend_cagr == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    ("start", "end", "conf"),
    [
        (date(2025, 1, 1), date(2025, 12, 31), "H"),  # 12 calendar months, 365 days
        (date(2024, 1, 1), date(2024, 12, 31), "H"),  # leap year
        (date(2025, 1, 2), date(2025, 12, 31), "L"),  # one day short
        (date(2025, 3, 15), date(2026, 3, 14), "H"),
    ],
)
def test_R10_seasonality_confidence_on_calendar_months_like_F2(
    start: date, end: date, conf: str
) -> None:
    """R10 'history < 12 months → seasonality flagged L' agrees with F2's DQ R10 warning."""
    assert seasonality(_weekday_daily(start, end)).confidence == conf
    assert _shorter(start, end, 12) == (conf == "L")


# --- F3e: zero-row frames and ABC ties --------------------------------------------------------
F2_EMPTY_RECEIPTS = pl.DataFrame(  # what F2 writes when its REQ rule drops every receipt row
    schema={"receipt_id": pl.String, "receipt_ts": pl.Datetime("us", "UTC"), "sku": pl.String,
            "qty_units": pl.Int64, "pallets": pl.Float64, "source_file": pl.String,
            "source_row": pl.Int64}
)  # fmt: skip


def _no_hash(p: DemandProfile) -> dict[str, object]:
    return p.model_dump(exclude={"dataset_hash"})  # the hash covers which tables exist


def test_zero_row_receipts_profile_like_no_receipts(tmp_path: Path) -> None:
    """F3d open issue 1 (high): F2 can write a 0-row receipts.parquet and call the ingest
    usable; fsum_by then raised builtins.ValueError (zip strict on 0 runs). F3e round 1: §4.1
    has receipts_* 'if receipts present', so a 0-row table is absent: no receipts_* columns
    (all-zero ones made F4 receipts mode size inbound at 0 trucks without a flag)."""
    frames = mini_frames()
    base, base_t = built(write_frames(tmp_path / "none", frames))
    d = write_frames(tmp_path / "empty", frames | {"receipts": F2_EMPTY_RECEIPTS})
    p, t = built(d)
    validate_daily(t.daily)
    assert not {"receipts_lines", "receipts_units", "receipts_pallets"} & set(t.daily.columns)
    assert t.daily.equals(base_t.daily)
    assert _no_hash(p) == _no_hash(base)
    assert build_profile(d, None, ProfileCfg()) == p


def _receipts_at(*stamps: datetime) -> pl.DataFrame:
    n = len(stamps)
    return pl.DataFrame(
        {"receipt_id": [f"r{i}" for i in range(n)], "sku": ["A"] * n, "qty_units": [10] * n,
         "pallets": [1.0] * n, "receipt_ts": list(stamps)}
    )  # fmt: skip


@pytest.mark.parametrize(
    ("stamps", "period"),
    [
        # window 2025-04-28 → 2025-05-10 (Paris): before it, after it, and local dates just
        # outside although the UTC date is inside (05-10 23:30 UTC = 05-11 01:30 Paris)
        ([datetime(2025, 3, 3, 8, tzinfo=UTC), datetime(2025, 4, 20, 8, tzinfo=UTC)],
         (date(2025, 3, 3), date(2025, 4, 20))),
        ([datetime(2025, 5, 12, 8, tzinfo=UTC)], (date(2025, 5, 12), date(2025, 5, 12))),
        ([datetime(2025, 5, 10, 23, 30, tzinfo=UTC)], (date(2025, 5, 11), date(2025, 5, 11))),
        ([datetime(2025, 4, 27, 21, 30, tzinfo=UTC)], (date(2025, 4, 27), date(2025, 4, 27))),
    ],
)  # fmt: skip
def test_I71_receipts_outside_the_shipped_window_are_absent(
    tmp_path: Path, stamps: list[datetime], period: tuple[date, date]
) -> None:
    """F3e open issue 1 (medium): receipts with rows, none inside the shipped-date window
    (first to last shipped local date, I2), gave all-zero receipts_* columns on every day, so
    F4 receipts mode sized inbound at 0 without a flag. I71: such a table is absent, as a
    0-row one is: no receipts_* columns; the profile keeps the receipts' local date range."""
    frames = mini_frames()
    base, base_t = built(write_frames(tmp_path / "none", frames))
    p, t = built(write_frames(tmp_path / "out", frames | {"receipts": _receipts_at(*stamps)}))
    validate_daily(t.daily)
    assert not {"receipts_lines", "receipts_units", "receipts_pallets"} & set(t.daily.columns)
    assert t.daily.equals(base_t.daily)
    assert p.model_dump(exclude={"dataset_hash", "receipts_period"}) == base.model_dump(
        exclude={"dataset_hash", "receipts_period"}
    )
    assert p.receipts_period == period and base.receipts_period is None


def test_I71_receipts_touching_the_window_keep_their_columns(tmp_path: Path) -> None:
    """Only a table with no row in [first, last shipped date] is dropped. One receipt inside
    (04-27 22:30 UTC = 04-28 00:30 Paris, the first window day) and one outside (05-10 22:30
    UTC = 05-11 00:30 Paris) keep the columns; only the inside receipt is counted."""
    inside = datetime(2025, 4, 27, 22, 30, tzinfo=UTC)
    outside = datetime(2025, 5, 10, 22, 30, tzinfo=UTC)
    frames = mini_frames() | {"receipts": _receipts_at(inside, outside)}
    p, t = built(write_frames(tmp_path, frames))
    first = t.daily.filter(pl.col("date") == date(2025, 4, 28)).row(0, named=True)
    assert (first["receipts_lines"], first["receipts_units"]) == (1.0, 10.0)
    assert t.daily["receipts_lines"].sum() == 1.0
    assert p.receipts_period == (date(2025, 4, 28), date(2025, 5, 11))


def test_zero_row_inventory_profiles_like_no_inventory(tmp_path: Path) -> None:
    """A 0-row inventory.parquet takes the I49 no-inventory path: 0 stock, cover 0.0, L."""
    frames = mini_frames()
    inventory = frames.pop("inventory")
    base, _ = built(write_frames(tmp_path / "none", frames))
    p, _ = built(write_frames(tmp_path / "empty", frames | {"inventory": inventory.clear()}))
    s = p.stock
    assert (s.n_snapshots, s.avg_units, s.cover_days, s.confidence) == (0, 0.0, 0.0, "L")
    assert s.growth_units_per_year is None and p.abc.by_stock_cube["C"].sku_share == 1.0
    assert _no_hash(p) == _no_hash(base)


def test_a_single_line_dataset_profiles_and_writes_its_artifacts(tmp_path: Path) -> None:
    """One shipped line (Mon 2025-04-28 10:00, SKU A, 2 units): one operating day, every
    statistic of a one-value series, one A SKU, all lines at 10:00."""
    frames = mini_frames()
    frames["order_lines"] = frames["order_lines"].head(1)
    p, t = built(write_frames(tmp_path / "canonical", frames))
    assert p.operating_days == 1 and p.period_start == p.period_end == date(2025, 4, 28)
    one = SeriesStats(mean=1.0, p50=1.0, p90=1.0, p95=1.0, p98=1.0, max=1.0, cv=0.0)
    assert p.daily["lines"] == one and p.eiq.lines_per_order == one
    assert p.eiq.order_class_shares == {"S": 1.0, "M": 0.0, "L": 0.0}
    assert p.abc.by_lines["A"].n_skus == 1 and p.abc.by_lines["A"].line_share == 1.0
    assert p.abc.pareto_lines[-1] == 1.0
    assert p.intraday == {0: [1.0 if h == 10 else 0.0 for h in range(24)]}
    assert p.peak_hour_share == 1.0 and p.seasonality.trend_cagr is None
    assert p.seasonality.monthly_index == [None] * 3 + [1.0] + [None] * 8  # April
    assert p.shipment_split.parcel_share_orders == 1.0
    assert p.shipment_split.mean_parcels_per_order == 1.0
    assert len(write_profile(p, tmp_path / "run", t)) == 2 + 2 * len(CHARTS)


def test_zero_row_sku_master_makes_every_sku_an_orphan_without_dims(tmp_path: Path) -> None:
    """A 0-row sku_master: every shipped or stocked SKU is an orphan without dims (I10), so no
    order has a cube; the cube/weight scatter is drawn empty, without a legend warning."""
    frames = mini_frames()
    d = write_frames(tmp_path / "canonical", frames | {"sku_master": frames["sku_master"].clear()})
    p, t = built(d)
    assert t.skus.sort("sku")["sku"].to_list() == ["A", "B", "C", "Z"]
    assert t.skus["orphan"].all() and p.dims_coverage_lines == 0.0
    assert p.eiq.cube_per_order_m3.max == 0.0 and p.abc.by_cube_movement["C"].sku_share == 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        assert len(write_profile(p, tmp_path / "run", t)) == 2 + 2 * len(CHARTS)


def test_aggregation_helpers_accept_zero_row_frames() -> None:
    """Per-key helpers give 0 rows on 0 rows; helpers that need one value raise WhsizingError
    (§2.7), never a builtin error (build_profile stops earlier: no shipped line)."""
    empty = pl.DataFrame(schema={"k": pl.String, "w": pl.Float64})
    assert fsum_by(empty, "k", ("w",)).schema == empty.schema
    assert fsum_by(empty, "k", ("w",)).height == 0
    lines = pl.DataFrame(
        schema={"order_id": pl.String, "sku": pl.String, "qty_units": pl.Int64,
                "date": pl.Date, "hour": pl.Int64, "no_time": pl.Boolean}
    )  # fmt: skip
    orders = split_orders(orders_table(with_cube(lines, sku_table(None, lines["sku"]))), Flows())
    assert orders.height == 0 and {"n_lines", "cube_m3", "parcels"} <= set(orders.columns)
    with pytest.raises(WhsizingError, match="at least one shipped order"):
        shipment_split(orders)
    with pytest.raises(WhsizingError, match="at least one value"):
        series_stats(np.array([]))


@pytest.mark.parametrize(
    ("lines", "expected"), [([28, 7], ["A", "B"]), ([851, 764, 85], ["A", "A", "C"])]
)
def test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6(
    lines: list[int], expected: list[str]
) -> None:
    """F3d open issue 2 (abc.py:24): the share before the last SKU is exactly 0.80 (28/35) or
    0.95 (851/1700 + 764/1700), so I6 'A if cum < 0.80, B if cum < 0.95' gives B, then C. The
    old polars division multiplied by 1/total: 28 × (1/35) < 0.80 made it A. An empty class
    gets zero shares."""
    assert 28 / 35 == 0.8 and 28 * (1 / 35) < 0.8  # the drift being fixed
    assert 851 / 1700 + 764 / 1700 == 0.95 and 851 * (1 / 1700) + 764 * (1 / 1700) < 0.95
    n = len(lines)
    skus = pl.DataFrame(
        {"sku": [f"s{i}" for i in range(n)], "lines": lines, "cube_movement_m3": [1.0] * n}
    )
    ranked = classify(skus, "lines", (0.8, 0.95))
    assert ranked["abc"].to_list() == expected
    stats = class_stats(ranked, "cube_movement_m3")
    assert sum(s.n_skus for s in stats.values()) == n
    for c in set(CLASSES) - set(expected):
        assert stats[c] == AbcClassStats(n_skus=0, sku_share=0.0, line_share=0.0, cube_share=0.0)
