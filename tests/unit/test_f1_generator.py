"""F1 generator: determinism (T1.1), order volume (T1.2), Zipf skew (T1.3), canonical frames."""

from __future__ import annotations

import datetime as dt
import hashlib
import tracemalloc
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

from whsizing.errors import ConfigError
from whsizing.schemas.frames import Inventory, OrderLines, Receipts, SkuMaster
from whsizing.synth import (
    SynthProfile,
    daily_lambda,
    export,
    generate,
    generator,
    load_synth_profile,
)
from whsizing.synth.generator import _draw_skus, _returns  # pyright: ignore[reportPrivateUsage]
from whsizing.synth.profile import Promo

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "data" / "synth" / "profiles"
GOLDEN = ROOT / "tests" / "golden" / "tiny_golden"
TABLES = ("order_lines", "sku_master", "inventory", "receipts")


@pytest.fixture(scope="module")
def tiny() -> SynthProfile:
    return load_synth_profile(PROFILES / "tiny_golden.yaml")


@pytest.fixture(scope="module")
def ecom_short() -> SynthProfile:
    """ecom_mid with 120 days (same s, n_skus, rates)."""
    return load_synth_profile(PROFILES / "ecom_mid.yaml").model_copy(update={"n_days": 120})


@pytest.fixture(scope="module")
def ecom_frames(ecom_short: SynthProfile) -> dict[str, pl.DataFrame]:
    return generate(ecom_short, seed=42)


def _parquet_hashes(frames: dict[str, pl.DataFrame], out: Path) -> dict[str, str]:
    export(frames, out, formats=("parquet",))
    return {t: hashlib.sha256((out / f"{t}.parquet").read_bytes()).hexdigest() for t in TABLES}


def test_T1_1_same_seed_identical_parquet_hash(tiny: SynthProfile, tmp_path: Path) -> None:
    first = _parquet_hashes(generate(tiny, seed=42), tmp_path / "a")
    again = _parquet_hashes(generate(tiny, seed=42), tmp_path / "b")
    other = _parquet_hashes(generate(tiny, seed=43), tmp_path / "c")
    assert first == again
    assert all(first[t] != other[t] for t in TABLES)


def test_tiny_golden_dataset_matches_profile_and_seed(tiny: SynthProfile) -> None:
    """The committed golden dataset is exactly what the README command regenerates."""
    frames = generate(tiny, seed=42)
    for table in TABLES:
        assert_frame_equal(pl.read_parquet(GOLDEN / f"{table}.parquet"), frames[table])


def _lambda_by_hand(p: SynthProfile) -> float:
    """F1 step 3, written out day by day (independent of `daily_lambda`)."""
    total = 0.0
    for d in range(p.n_days):
        day = p.start_date + dt.timedelta(days=d)
        promo = 1.0
        for e in p.promos:
            if e.date <= day < e.date + dt.timedelta(days=e.duration_days):
                promo *= e.multiplier
        total += (
            p.orders_per_day_mean
            * p.weekday_weights[day.weekday()]
            * p.month_index[day.month - 1]
            * (1 + p.annual_growth) ** (d / 365)
            * promo
        )
    return total


def _n_orders(lines: pl.DataFrame) -> int:
    return lines.filter(pl.col("line_status") != "returned")["order_id"].n_unique()


def test_T1_2_order_count_within_5pct_of_expected(
    ecom_short: SynthProfile, ecom_frames: dict[str, pl.DataFrame], tiny: SynthProfile
) -> None:
    expected = _lambda_by_hand(ecom_short)
    assert daily_lambda(ecom_short).sum() == pytest.approx(expected, rel=1e-12)
    assert _n_orders(ecom_frames["order_lines"]) == pytest.approx(expected, rel=0.05)
    # golden case (~1,000 orders, Poisson σ ≈ 3 %): holds at seed 42
    assert _n_orders(generate(tiny, seed=42)["order_lines"]) == pytest.approx(
        _lambda_by_hand(tiny), rel=0.05
    )


def test_T1_2_promo_and_weekday_shape_lambda() -> None:
    p = SynthProfile(
        name="t",
        start_date=dt.date(2024, 11, 25),  # Monday
        n_days=7,
        annual_growth=0.0,
        promos=[Promo(date=dt.date(2024, 11, 29), multiplier=2.0, duration_days=3)],
    )
    lam = daily_lambda(p)
    nov = 800 * 1.4
    expected = [1.15 * nov, 1.10 * nov, 1.05 * nov, 1.00 * nov, 0.95 * nov * 2, 0.35 * nov * 2, 0.0]
    assert lam == pytest.approx(expected)


def test_T1_3_zipf_top20_skus_carry_70pct_of_lines(
    ecom_short: SynthProfile, ecom_frames: dict[str, pl.DataFrame]
) -> None:
    lines = ecom_frames["order_lines"]
    counts = np.sort(lines.group_by("sku").len()["len"].to_numpy())[::-1]
    top = int(0.2 * ecom_short.n_skus)
    share = counts[:top].sum() / lines.height
    print(f"T1.3 top-20% SKU line share = {share:.3f}")  # measured ≈ 0.88
    assert share >= 0.70


def test_frames_validate_against_pandera_schemas(
    ecom_frames: dict[str, pl.DataFrame], tiny: SynthProfile
) -> None:
    for frames in (ecom_frames, generate(tiny, seed=7)):
        OrderLines.validate(frames["order_lines"])
        SkuMaster.validate(frames["sku_master"])
        Inventory.validate(frames["inventory"])
        Receipts.validate(frames["receipts"])


def test_order_lines_canonical_shape(ecom_frames: dict[str, pl.DataFrame]) -> None:
    lines = ecom_frames["order_lines"]
    assert lines.schema["order_ts"] == pl.Datetime("us", "UTC")
    assert lines.schema["line_status"] == pl.Categorical
    assert set(lines["line_status"].cast(pl.Utf8).unique()) == {"shipped", "cancelled", "returned"}
    assert lines["source_row"].to_list() == list(range(1, lines.height + 1))
    assert lines["source_file"].unique().to_list() == ["synth:ecom_mid/order_lines"]
    assert lines["order_id"].str.contains(r"^[0-9a-f]{16}$").all()
    assert lines.select("order_id", "sku").is_unique().all()  # no line merges under F2's R6
    returned = lines["line_status"] == "returned"
    assert (lines.filter(returned)["qty_units"] < 0).all()
    assert (lines.filter(~returned)["qty_units"] > 0).all()
    assert lines["order_ts"].is_sorted()


def test_times_are_paris_wall_time_stored_as_utc(ecom_frames: dict[str, pl.DataFrame]) -> None:
    """Sunday has weekday weight 0: no Paris-local Sunday line, but some UTC-Sunday ones
    (Monday 00:xx Paris is Sunday 23:xx/22:xx UTC)."""
    ts = ecom_frames["order_lines"]["order_ts"]
    assert (ts.dt.convert_time_zone("Europe/Paris").dt.weekday() == 7).sum() == 0
    assert (ts.dt.weekday() == 7).sum() > 0
    receipts = ecom_frames["receipts"]["receipt_ts"].dt.convert_time_zone("Europe/Paris")
    assert (receipts.dt.weekday() == 1).all()  # weekly receipts on Monday
    assert receipts.dt.hour().is_between(7, 14).all()


def test_returns_share_and_fresh_order_ids(tiny: SynthProfile) -> None:
    lines = generate(tiny.model_copy(update={"returns_rate": 0.5}), seed=3)["order_lines"]
    returned = lines.filter(pl.col("line_status") == "returned")
    shipped = lines.filter(pl.col("line_status") == "shipped")
    share = returned.height / shipped.height
    assert 0.25 < share < 0.5  # 50 % sampled, minus those beyond the 31-day period
    assert returned["order_id"].is_in(shipped["order_id"].implode()).sum() == 0


def test_return_delay_stays_in_window_and_lands_on_open_days(tiny: SynthProfile) -> None:
    """Step 5: delay ∈ [3, 20] d, never on a closed weekday (Sunday), no Monday pile-up.
    21,000 lines sent 1-7 Mar 2025 (Sat-Fri), 3,000 per weekday; `qty_units` is a row id."""
    p = tiny.model_copy(update={"returns_rate": 1.0, "n_days": 60})
    n = 21_000
    sent = np.datetime64("2025-03-01T10:00", "us") + (np.arange(n) % 7).astype("timedelta64[D]")
    lines = pl.DataFrame(
        {
            "order_id": ["x"] * n,
            "local_ts": sent,
            "sku_idx": np.zeros(n, dtype=np.int64),
            "qty_units": np.arange(1, n + 1),
            "channel": ["B2C"] * n,
            "line_status": ["shipped"] * n,
        }
    )
    ret = _returns(p, lines, np.uint64(1), 0, np.random.default_rng(42))
    assert (ret["qty_units"] == -lines["qty_units"]).all()  # one return per line, same order
    delay = (ret["local_ts"] - lines["local_ts"]).dt.total_days()
    assert (delay.min(), delay.max()) == (3, 20)
    weekday = ret["local_ts"].dt.weekday().value_counts().sort("local_ts")["count"].to_list()
    assert len(weekday) == 6  # Monday..Saturday, no Sunday
    assert max(weekday[:5]) < 1.2 * min(weekday[:5])  # weekdays evenly hit
    # a window with no open day (Saturday + 1 d = Sunday) drops those returns
    narrow = _returns(
        p.model_copy(update={"return_delay_days": (1, 1)}),
        lines,
        np.uint64(1),
        0,
        np.random.default_rng(42),
    )
    assert narrow.height == n - n // 7


def test_sku_master_derived_fields(ecom_frames: dict[str, pl.DataFrame]) -> None:
    sku = ecom_frames["sku_master"]
    cube = sku["length_mm"] * sku["width_mm"] * sku["height_mm"] / 1e9
    assert (sku["unit_cube_m3"] - cube).abs().max() < 1e-12  # type: ignore[operator]
    cpp = (1.2 * 0.8 * 1.2 / (sku["units_per_case"] * cube)).floor().clip(lower_bound=1)
    assert (sku["cases_per_pallet"] == cpp.cast(pl.Int64)).all()
    assert (sku["units_per_pallet"] == sku["units_per_case"] * sku["cases_per_pallet"]).all()
    assert set(sku["units_per_case"].unique()) <= {1, 6, 12, 24}
    assert sku["category"].n_unique() == 8
    assert sku["sku"].is_unique().all()
    assert sku.null_count().sum_horizontal().item() == 0


def test_inactive_skus_never_ordered(ecom_frames: dict[str, pl.DataFrame]) -> None:
    ordered = ecom_frames["order_lines"]["sku"].n_unique()
    assert ordered <= 5000 * 0.9


def test_inventory_month_end_cover_formula(tiny: SynthProfile) -> None:
    """Step 6 with zero noise: stock = round(shipped units over 30 d × cover / 30)."""
    frames = generate(tiny.model_copy(update={"stock_noise_sigma": 0.0}), seed=42)
    inv = frames["inventory"]
    assert inv["snapshot_date"].unique().to_list() == [dt.date(2025, 3, 31)]
    shipped = frames["order_lines"].filter(pl.col("line_status") == "shipped")
    local = shipped["order_ts"].dt.convert_time_zone("Europe/Paris").dt.date()
    in_window = shipped.filter(local > dt.date(2025, 3, 1))  # (31 Mar − 30 d, 31 Mar]
    demand = in_window.group_by("sku").agg(pl.col("qty_units").sum())
    joined = inv.join(demand, on="sku", how="left").fill_null(0)
    expected = (joined["qty_units_right"] * tiny.days_of_cover / 30).round().cast(pl.Int64)
    assert (joined["qty_units"] == expected).all()


def test_receipts_replenish_in_full_cases(ecom_frames: dict[str, pl.DataFrame]) -> None:
    rec = ecom_frames["receipts"].join(ecom_frames["sku_master"], on="sku")
    assert (rec["qty_units"] % rec["units_per_case"] == 0).all()
    assert (rec["pallets"] - rec["qty_units"] / rec["units_per_pallet"]).abs().max() < 1e-12  # type: ignore[operator]
    assert rec["receipt_id"].n_unique() < rec.height  # several SKU lines per receipt


def test_receipts_carry_the_case_surplus_over(
    ecom_short: SynthProfile, ecom_frames: dict[str, pl.DataFrame]
) -> None:
    """Step 7 keeps cover: per SKU, units received = units shipped in the weeks replenished
    (receipt on the next Monday within the period) rounded up by less than one case."""
    shipped = ecom_frames["order_lines"].filter(pl.col("line_status") == "shipped")
    monday = shipped["order_ts"].dt.convert_time_zone("Europe/Paris").dt.date().dt.truncate("1w")
    covered = shipped.filter((monday + dt.timedelta(days=7)) <= ecom_short.end_date)
    out = covered.group_by("sku").agg(pl.col("qty_units").sum().alias("out"))
    received = ecom_frames["receipts"].group_by("sku").agg(pl.col("qty_units").sum().alias("in"))
    per_sku = out.join(received, on="sku", how="full", coalesce=True).fill_null(0)
    per_sku = per_sku.join(ecom_frames["sku_master"], on="sku")
    surplus = per_sku["in"] - per_sku["out"]
    assert (surplus >= 0).all()
    assert (surplus < per_sku["units_per_case"]).all()


def test_b2b_lines_are_case_multiples() -> None:
    p = load_synth_profile(PROFILES / "b2b_cases.yaml").model_copy(update={"n_days": 30})
    frames = generate(p, seed=42)
    lines = frames["order_lines"].join(frames["sku_master"], on="sku")
    b2b = lines.filter(pl.col("channel") == "B2B")
    assert b2b.height > 0
    assert (b2b["qty_units"] % b2b["units_per_case"] == 0).all()
    local = frames["order_lines"]["order_ts"].dt.convert_time_zone("Europe/Paris")
    assert local.dt.weekday().is_in([6, 7]).sum() == 0  # closed at weekends


def test_tiny_golden_exercises_the_engine() -> None:
    """Golden dataset coverage: cube_asrs overflow, pallet_rack and shelving classes, returns.
    Stock cube uses the snapshot stock (design stock adds peak factor and growth on top);
    ≤ 0.24 m³ = shelf_bin_net_cube 0.04 × max_bins_per_sku_shelf 6 (fits_shelf_bin not checked)."""
    sku = pl.read_parquet(GOLDEN / "sku_master.parquet")
    lines = pl.read_parquet(GOLDEN / "order_lines.parquet")
    inv = pl.read_parquet(GOLDEN / "inventory.parquet")
    assert sku.height == 100
    cols = ["length_mm", "width_mm", "height_mm", "weight_kg", "units_per_case", "cases_per_pallet"]
    assert sku.select(cols).null_count().sum_horizontal().item() == 0
    dims = -np.sort(-sku.select(cols[:3]).to_numpy(), axis=1)
    beyond = (dims > np.array([600, 400, 300])).any(axis=1) | (sku["weight_kg"].to_numpy() > 25)
    assert beyond.sum() >= 3
    stock_cube = inv.join(sku, on="sku").select(pl.col("qty_units") * pl.col("unit_cube_m3"))
    assert (stock_cube.to_series() >= 0.6).sum() >= 3
    assert (stock_cube.to_series().is_between(0, 0.24, closed="right")).sum() >= 30
    assert (lines["qty_units"] < 0).sum() >= 20
    assert 900 <= _n_orders(lines) <= 1100
    local = lines["order_ts"].dt.convert_time_zone("Europe/Paris").dt.date()
    assert local.is_between(dt.date(2025, 3, 1), dt.date(2025, 3, 31)).all()


def test_profile_loader_rejects_bad_yaml(tmp_path: Path) -> None:
    good = (PROFILES / "tiny_golden.yaml").read_text(encoding="utf-8")
    cases = {
        "unknown_key": good + "\nbogus_key: 1\n",
        "weekday_len": good.replace("[1.15, 1.10, 1.05, 1.00, 0.95, 0.35, 0.0]", "[1, 1]"),
        "share_range": good.replace("returns_rate: 0.04", "returns_rate: 1.5"),
        "bad_delay": good.replace("return_delay_days: [3, 20]", "return_delay_days: [20, 3]"),
    }
    for name, text in cases.items():
        path = tmp_path / f"{name}.yaml"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_synth_profile(path)
    with pytest.raises(ConfigError):
        load_synth_profile(tmp_path / "missing.yaml")


def test_every_profile_carries_every_parameter() -> None:
    """Profiles spell out every generator parameter (no silent defaults)."""
    import yaml

    fields = set(SynthProfile.model_fields)
    for name in ("ecom_mid", "b2b_cases", "tiny_golden"):
        keys = set(yaml.safe_load((PROFILES / f"{name}.yaml").read_text(encoding="utf-8")))
        assert keys == fields, f"{name}: missing {fields - keys}"


def test_sampling_without_replacement_when_orders_use_every_sku(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orders as long as the active range force the Gumbel-top-k fallback; still no repeats,
    with the fallback split over many chunks (3 orders × 4 SKUs per chunk)."""
    monkeypatch.setattr(generator, "GUMBEL_CHUNK_CELLS", 12)
    p = SynthProfile(
        name="t",
        n_skus=4,
        inactive_share=0.0,
        start_date=dt.date(2025, 1, 6),
        n_days=14,
        single_line_prob=0.0,
        extra_lines_mean=20.0,
        zipf_s=3.0,
    )
    lines = generate(p, seed=1)["order_lines"].filter(pl.col("line_status") != "returned")
    per_order = lines.group_by("order_id").agg(pl.len(), pl.col("sku").n_unique().alias("u"))
    assert (per_order["len"] == 4).all()
    assert (per_order["u"] == 4).all()


@pytest.mark.parametrize(
    ("day", "hour", "offset"),
    [(dt.date(2025, 3, 30), 3, "+02:00"), (dt.date(2025, 10, 26), 2, "+02:00")],
)
def test_dst_gap_and_overlap_times_are_resolved(day: dt.date, hour: int, offset: str) -> None:
    """All orders drawn at 02:xx on DST days: the spring-forward gap shifts to 03:xx CEST,
    the fall-back overlap takes the earliest (CEST) instant. No null or raised timestamp."""
    p = SynthProfile(
        name="dst",
        start_date=day,
        n_days=1,
        n_skus=20,
        orders_per_day_mean=50,
        weekday_weights=[1.0] * 7,
        hourly_weights=[1.0 if h == 2 else 0.0 for h in range(24)],
        returns_rate=0.0,
    )
    ts = generate(p, seed=42)["order_lines"]["order_ts"]
    assert ts.null_count() == 0
    paris = ts.dt.convert_time_zone("Europe/Paris")
    assert (paris.dt.hour() == hour).all()
    assert (paris.dt.strftime("%:z") == offset).all()


def test_gumbel_fallback_memory_is_bounded() -> None:
    """Skewed popularity (s = 2) and 16-line orders send most orders to the Gumbel fallback;
    peak memory stays near the chunk budget instead of growing with orders × SKUs
    (measured: 52 MB chunked; 89 MB unchunked at 3,000 orders, growing linearly)."""
    w = np.arange(1, 2001) ** -2.0
    w /= w.sum()
    order = np.repeat(np.arange(6000), 16)
    tracemalloc.start()
    try:
        sku = _draw_skus(order, w, np.random.default_rng(42))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 80e6, f"peak {peak / 1e6:.0f} MB"
    assert pl.DataFrame({"o": order, "s": sku}).is_unique().all()


def test_negative_seed_and_empty_profile_raise_config_error(tiny: SynthProfile) -> None:
    with pytest.raises(ConfigError, match="seed"):
        generate(tiny, seed=-1)
    sunday_only = tiny.model_copy(update={"start_date": dt.date(2025, 3, 2), "n_days": 1})
    with pytest.raises(ConfigError, match="no orders"):
        generate(sunday_only, seed=42)
