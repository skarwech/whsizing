"""F4 design basis and design day: T4.2-T4.6 and the F4 edge cases, on tiny_golden (F3)."""

from __future__ import annotations

import itertools
import json
import shutil
from collections import Counter
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest

from whsizing.catalog import Catalog, load_catalog
from whsizing.design import (
    basis_template,
    derive_inbound,
    load_basis,
    select_design_day,
    sla_window_hours,
    with_pack_data,
    write_design,
)
from whsizing.design.basis import candidate_days, leaf_fields
from whsizing.errors import ConfigError, DataQualityError, WhsizingError
from whsizing.io.canonical import derive
from whsizing.profile import ProfileTables, build_tables, profile_from_tables
from whsizing.schemas import DemandProfile, DesignBasis, DesignDay, ProfileCfg, Service

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
DATA = GOLDEN / "tiny_golden"


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


def design(built, basis: DesignBasis, catalog: Catalog, daily=None) -> DesignDay:
    t, profile, sku = built
    daily = t.daily if daily is None else daily
    return select_design_day(profile, basis, daily, sku=sku, catalog=catalog)


def test_T4_2_design_percentile_moves_lines_monotonically(built, basis, catalog) -> None:
    pcts = [50.0, 75.0, 90.0, 95.0, 98.0, 100.0]
    lines = [
        design(built, with_(basis, "projection", design_percentile=q), catalog).lines for q in pcts
    ]
    assert all(a <= b for a, b in itertools.pairwise(lines)), lines
    assert lines[0] < lines[-1]
    op = built[0].daily.filter("is_operating")["lines"].to_numpy()
    gf = 1.04**5
    for q, v in zip(pcts, lines, strict=True):
        assert v == pytest.approx(np.percentile(op, q) * gf, rel=1e-12)


@pytest.mark.parametrize("weekday_rate", [(0.04, None), (0.0, 5)])
def test_T4_3_hourly_lines_sum_to_design_lines(built, basis, catalog, weekday_rate) -> None:
    g, keep_weekday = weekday_rate
    t = built[0]
    daily = t.daily
    if keep_weekday is not None:  # only Saturdays operating → design weekday 5
        daily = daily.with_columns(is_operating=pl.col("weekday") == keep_weekday)
    dd = design(built, with_(basis, "projection", growth_rate=g), catalog, daily)
    assert len(dd.hourly_lines) == 24
    assert abs(sum(dd.hourly_lines) - dd.lines) < 1e-6
    assert dd.peak_hour_lines == max(dd.hourly_lines)
    if keep_weekday is not None:
        assert dd.design_weekday == keep_weekday


def test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock(
    basis: DesignBasis, catalog: Catalog, tmp_path: Path
) -> None:
    for name in ("order_lines", "sku_master"):
        shutil.copy(DATA / f"{name}.parquet", tmp_path / f"{name}.parquet")
    inv = pl.read_parquet(DATA / "inventory.parquet")
    snaps = [inv.with_columns(pl.col("snapshot_date") - timedelta(days=7 * k)) for k in range(3)]
    pl.concat(snaps).write_parquet(tmp_path / "inventory.parquet")  # 3 equal snapshots
    b0 = with_(basis, "projection", growth_rate=0.0)
    t = build_tables(tmp_path, b0, ProfileCfg())
    profile = profile_from_tables(t, ProfileCfg())
    assert profile.stock.n_snapshots == 3
    assert profile.stock.growth_units_per_year == pytest.approx(0.0, abs=1e-9)
    sku = with_pack_data(t.skus, pl.read_parquet(tmp_path / "sku_master.parquet"))
    inb = derive_inbound(profile, b0, t.daily, sku, catalog=catalog)
    mean_out = float(t.daily.filter("is_operating")["units"].mean())  # pyright: ignore[reportArgumentType]
    assert inb.units_per_day == pytest.approx(mean_out, rel=1e-12)
    # growing stock adds Δstock / operating days: 252 units/yr over 252 days → +1 unit/day
    grown = profile.model_copy(
        update={"stock": profile.stock.model_copy(update={"growth_units_per_year": 252.0})}
    )
    inb2 = derive_inbound(grown, b0, t.daily, sku, catalog=catalog)
    assert inb2.units_per_day == pytest.approx(mean_out + 1.0, rel=1e-12)


def test_T4_4_derived_inbound_below_zero_is_a_data_quality_error(
    basis: DesignBasis, catalog: Catalog, tmp_path: Path
) -> None:
    """L4 / I85 (a): a hostile inventory history (10 rows of 1e12 units in the first snapshot)
    gave units_per_day -1.55e10 and a staged `size` printed negative FTE. Now exit 3, naming
    the delta-stock term and its value."""
    for name in ("order_lines", "sku_master"):
        shutil.copy(DATA / f"{name}.parquet", tmp_path / f"{name}.parquet")
    inv = pl.read_parquet(DATA / "inventory.parquet")
    hostile = inv.with_columns(
        qty_units=pl.when(pl.int_range(pl.len()) < 10).then(10**12).otherwise(pl.col("qty_units"))
    )
    snaps = [hostile.with_columns(pl.col("snapshot_date") - timedelta(days=14))] + [
        inv.with_columns(pl.col("snapshot_date") - timedelta(days=7 * k)) for k in (1, 0)
    ]
    pl.concat(snaps).write_parquet(tmp_path / "inventory.parquet")
    b0 = with_(basis, "projection", growth_rate=0.0)
    t = build_tables(tmp_path, b0, ProfileCfg())
    profile = profile_from_tables(t, ProfileCfg())
    delta = profile.stock.growth_units_per_year
    assert delta is not None and delta < -1e12  # the destock term dwarfs the outbound flow
    sku = with_pack_data(t.skus, pl.read_parquet(tmp_path / "sku_master.parquet"))
    with pytest.raises(DataQualityError, match="delta-stock term") as e:
        derive_inbound(profile, b0, t.daily, sku, catalog=catalog)
    assert e.value.exit_code == 3
    assert f"{delta:.6g} units/year" in str(e.value)
    with pytest.raises(DataQualityError, match="delta-stock term"):  # the design day too
        select_design_day(profile, b0, t.daily, sku=sku, catalog=catalog)


def test_T4_4_mild_destock_keeps_a_positive_derived_inbound(built, basis, catalog) -> None:
    """The guard only fires below 0: Δstock of -252 units/year over 250 operating days is
    -1.008 units/day on top of outbound × growth, unchanged otherwise."""
    t, profile, sku = built
    flat = profile.model_copy(
        update={"stock": profile.stock.model_copy(update={"growth_units_per_year": 0.0})}
    )
    mild = profile.model_copy(
        update={"stock": profile.stock.model_copy(update={"growth_units_per_year": -252.0})}
    )
    base = derive_inbound(flat, basis, t.daily, sku, catalog=catalog)
    inb = derive_inbound(mild, basis, t.daily, sku, catalog=catalog)
    days = basis.operations.operating_days_per_year
    assert inb.units_per_day == pytest.approx(base.units_per_day - 252.0 / days, rel=1e-12)
    assert inb.units_per_day > 0 and inb.pallets_per_day > 0


def _check_assumptions(dd: DesignDay, b: DesignBasis) -> None:
    keys = Counter(a.key for a in dd.assumptions)
    fields = [p for p, _, _ in leaf_fields(b)]
    assert "overrides" in fields  # no exclusion: the overrides field has its own row
    assert {k: n for k, n in keys.items() if n != 1} == {}
    assert set(fields) <= set(keys)
    overrides = {a.key: a for a in dd.assumptions if a.origin == "override"}
    assert set(overrides) == {f"overrides.{k}" for k in b.overrides}
    rest = set(keys) - set(fields) - set(overrides)
    assert all(a.origin == "derived" for a in dd.assumptions if a.key in rest)


def test_T4_5_assumptions_list_every_basis_field_exactly_once(built, basis, catalog) -> None:
    origins = []
    for b in (basis, load_basis(ROOT / "basis" / "example_basis.yaml")):
        dd = design(built, b, catalog)
        _check_assumptions(dd, b)
        row = {a.key: a for a in dd.assumptions}["overrides"]
        origins.append((row.origin, row.value))
    assert basis.overrides == {}  # golden: the empty overrides field still has a row
    assert origins == [
        ("default", "{}"),
        ("client", '{"manual_p2p.pick_rate_shelving_lines_h": 62.0}'),
    ]
    by_key = {a.key: a for a in dd.assumptions}
    assert by_key["overrides.manual_p2p.pick_rate_shelving_lines_h"].value == 62
    assert by_key["client"].origin == "client"
    assert by_key["currency"].origin == "default"  # not in the example basis
    assert by_key["currency"].note.startswith("[P]")
    sla = by_key["service.sla_window_hours"]
    assert (sla.origin, sla.value) == ("derived", 3.5)  # 15:00 → 18:30
    assert by_key["flows.inbound_peak_factor"].origin == "derived"
    assert by_key["finance.labor_cost_eur_h"].value == (
        '{"operator": 25.5, "forklift_driver": 27.8, "team_leader": 33.0}'
    )


def test_T4_5_template_basis_tells_placeholder_defaults_from_client_values(
    built, catalog, tmp_path: Path
) -> None:
    """basis_template → client edits → load_basis: the template writes every [P] default, so
    being in the file must not make a value the client's (F4 step 9)."""
    path = tmp_path / "basis.yaml"
    basis_template(path, "en")
    text = path.read_text(encoding="utf-8")
    tags = {}  # leaf path → "[P]" / "[CLIENT]", read from the template lines
    section = ""
    for ln in text.splitlines():
        if ln.endswith(":") and not ln.startswith("#"):
            section = ln[:-1] + "."
        elif "# [" in ln and not ln.startswith("#"):
            name = ln.strip().lstrip("# ").split(":")[0]
            key = (section if ln.startswith(" ") else "") + name
            tags[key] = "[CLIENT]" if "# [CLIENT]" in ln else "[P]"
    for edited in (False, True):
        if edited:  # the client confirms one placeholder with another value
            path.write_text(text.replace("utilisation: 0.85", "utilisation: 0.9"), encoding="utf-8")
        b = load_basis(path)
        dd = design(built, b, catalog)
        _check_assumptions(dd, b)
        rows = {a.key: a for a in dd.assumptions if a.key in tags}
        assert set(rows) == set(tags) and len(tags) == len(leaf_fields(b))
        client = {k for k, a in rows.items() if a.origin == "client"}
        expected = {k for k, t in tags.items() if t == "[CLIENT]"}
        assert client == (expected | {"operations.utilisation"} if edited else expected)
        assert len(expected) == 9
        for k, a in rows.items():
            assert a.origin in ("client", "default", "derived"), k
            assert (a.origin == "default") == a.note.startswith("[P]"), k
        assert rows["overrides"].origin == "default"
        assert rows["operations.utilisation"].value == (0.9 if edited else 0.85)


@pytest.mark.parametrize(
    "text",
    [
        "colour: blue\n",  # top level
        "projection: {horizon_years: 5, unknown_key: 1}\n",  # nested
    ],
)
def test_T4_6_basis_with_unknown_key_raises_config_error(tmp_path: Path, text: str) -> None:
    good = (GOLDEN / "golden_basis.yaml").read_text(encoding="utf-8")
    if text.startswith("projection"):
        good = good.replace(
            "projection:\n  horizon_years: 5\n", "projection:\n  bogus: 1\n  horizon_years: 5\n"
        )
        assert "bogus" in good
    else:
        good += text
    path = tmp_path / "basis.yaml"
    path.write_text(good, encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown key"):
        load_basis(path)


@pytest.mark.parametrize(
    ("cutoff", "departure", "given", "hours"),
    [
        (time(15), time(18, 30), None, 3.5),
        (time(22), time(2), None, 4.0),  # crossing midnight
        (time(15), time(15), None, 24.0),  # equal times: next day's departure (I16)
        (time(15), time(18), 6.0, 6.0),  # given window wins
    ],
)
def test_sla_window_derived_from_times_crossing_midnight(cutoff, departure, given, hours) -> None:
    s = Service(cutoff_time=cutoff, carrier_departure_time=departure, sla_window_hours=given)
    assert sla_window_hours(s) == hours


def test_sla_window_given_must_be_positive() -> None:
    s = Service(cutoff_time=time(15), carrier_departure_time=time(18), sla_window_hours=0.0)
    with pytest.raises(ConfigError, match="sla_window_hours"):
        sla_window_hours(s)


def test_percentile_above_100_clipped_to_max_and_flagged(built, basis, catalog) -> None:
    dd = design(built, with_(basis, "projection", design_percentile=120.0), catalog)
    op = built[0].daily.filter("is_operating")
    assert dd.percentile == 100.0
    assert dd.lines == pytest.approx(float(op["lines"].max()) * 1.04**5, rel=1e-12)  # pyright: ignore[reportArgumentType]
    assert [f.code for f in dd.flags][:2] == ["F_PERCENTILE_CLIPPED", "F_SHORT_HISTORY"]


def _long_daily(t: ProfileTables, years: int) -> pl.DataFrame:
    """Synthetic daily series: Mon-Fri operating, lines growing by 1 per calendar day."""
    end = date(2025, 3, 31)
    days = pl.date_range(end - timedelta(days=365 * years - 1), end, eager=True)
    n = len(days)
    cols = {
        c: pl.Series(np.arange(1.0, n + 1))
        for c in t.daily.columns
        if t.daily[c].dtype == pl.Float64
    }
    d = pl.DataFrame({"date": days, **cols}).with_columns(
        weekday=pl.col("date").dt.weekday().cast(pl.Int64) - 1, is_holiday=pl.lit(False)
    )
    return d.with_columns(is_operating=pl.col("weekday") < 5)


def test_trailing_window_and_short_history(built, basis, catalog) -> None:
    t = built[0]
    daily = _long_daily(t, 2)
    cand = candidate_days(daily, 12)
    assert cand["date"].min() == date(2024, 4, 1)  # > 2025-03-31 − 12 months
    assert (
        cand.height
        == daily.filter(pl.col("is_operating") & (pl.col("date") >= date(2024, 4, 1))).height
    )
    assert candidate_days(daily, 36).height == daily.filter("is_operating").height  # I5
    dd = design(built, basis, catalog, daily)
    assert "F_SHORT_HISTORY" not in [f.code for f in dd.flags]
    assert dd.reference_date >= date(2024, 4, 1)
    short = design(built, basis, catalog)  # tiny_golden: 26 operating days
    assert "F_SHORT_HISTORY" in [f.code for f in short.flags]


def test_stock_growth_rate_override_replaces_g_for_stock(built, basis, catalog) -> None:
    profile = built[1]
    dd = design(built, basis.model_copy(update={"overrides": {"stock_growth_rate": 0.0}}), catalog)
    assert dd.stock_units == pytest.approx(profile.stock.avg_units * 1.15, rel=1e-12)
    assert dd.lines == pytest.approx(design(built, basis, catalog).lines, rel=1e-12)


def test_derived_inbound_falls_back_to_default_units_per_pallet(built, basis, catalog) -> None:
    t, profile, _ = built
    inb = derive_inbound(profile, basis, t.daily, with_pack_data(t.skus, None), catalog=catalog)
    assert inb.pallets_per_day == pytest.approx(inb.units_per_day / 400, rel=1e-12)
    # every SKU receives < 400 units a day → mixed pallets, 4 receipt lines per pallet
    assert inb.receipt_lines_per_day == pytest.approx(4 * inb.pallets_per_day, rel=1e-12)
    assert inb.cases_per_day == pytest.approx(inb.units_per_day, rel=1e-12)  # upc fallback 1
    assert [(f.code, f.value) for f in inb.flags] == [("F_DEFAULT_UPP", 1.0)]


def test_receipts_mode_takes_percentile_of_daily_receipts(built, basis, catalog) -> None:
    t, profile, sku = built
    b = with_(basis, "flows", inbound_mode="receipts", inbound_peak_factor=1.3)
    inb = derive_inbound(profile, b, t.daily, sku, catalog=catalog)
    op = t.daily.filter("is_operating")
    gf = 1.04**5
    assert inb.mode == "receipts"
    assert inb.units_per_day == pytest.approx(np.percentile(op["receipts_units"], 95) * gf)
    assert inb.pallets_per_day == pytest.approx(np.percentile(op["receipts_pallets"], 95) * gf)
    assert inb.receipt_lines_per_day == pytest.approx(np.percentile(op["receipts_lines"], 95) * gf)
    assert inb.trucks_per_day == pytest.approx(inb.pallets_per_day / 26)
    assert inb.peak_factor == 1.3
    no_receipts = t.daily.drop("receipts_lines", "receipts_units", "receipts_pallets")
    with pytest.raises(ConfigError, match="receipts"):
        derive_inbound(profile, b, no_receipts, sku, catalog=catalog)


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_basis_template_loads_and_marks_every_default(tmp_path: Path, lang: str) -> None:
    out = tmp_path / f"template_{lang}.yaml"
    basis_template(out, lang)  # pyright: ignore[reportArgumentType]
    b = load_basis(out)
    text = out.read_text(encoding="utf-8")
    assert text == (ROOT / "basis" / f"template_{lang}.yaml").read_text(encoding="utf-8")
    field_lines = [ln for ln in text.splitlines() if ": " in ln and not ln.startswith("#")]
    assert len(field_lines) == len(leaf_fields(b))
    for ln in field_lines:
        assert ("# [P]" in ln) != ("# [CLIENT]" in ln), ln
    assert text.count("[CLIENT]") == 9 + 1  # 9 required fields + the header legend
    assert b.service.cutoff_time == time(15)


def test_write_design_writes_design_day_and_assumptions(built, basis, catalog, tmp_path) -> None:
    dd = design(built, basis, catalog)
    paths = write_design(dd, tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in paths] == [
        "design/design_day.json",
        "design/assumptions.json",
    ]
    back = DesignDay.model_validate_json(paths[0].read_text(encoding="utf-8"))
    assert back == dd
    rows = json.loads(paths[1].read_text(encoding="utf-8"))
    assert [r["key"] for r in rows] == [a.key for a in dd.assumptions]


def test_default_upp_flagged_on_canonical_sku_master(built, basis, catalog) -> None:
    """F2 always fills units_per_pallet (case × cases/pallet, else 400): the fallback is
    detected on the case data, so the flag also fires on the production (canonical) path."""
    t, profile, _ = built
    master = pl.read_parquet(DATA / "sku_master.parquet").drop("units_per_pallet")
    no_pack = master["sku"].head(5).to_list()
    master = master.with_columns(
        pl.when(pl.col("sku").is_in(no_pack)).then(None).otherwise(pl.col(c)).alias(c)
        for c in ("units_per_case", "cases_per_pallet")
    )
    canon = derive({"sku_master": master})["sku_master"]
    assert canon.filter(pl.col("sku").is_in(no_pack))["units_per_pallet"].to_list() == [400] * 5
    inb = derive_inbound(profile, basis, t.daily, with_pack_data(t.skus, canon), catalog=catalog)
    units = t.skus.filter(pl.col("sku").is_in(no_pack))["units"].sum()
    share = units / t.skus["units"].sum()
    assert share > 0
    assert [(f.code, pytest.approx(f.value)) for f in inb.flags] == [("F_DEFAULT_UPP", share)]


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("flows", "pallets_per_truck", 0.0),
        ("operations", "operating_days_per_year", 0),
        ("projection", "design_percentile", float("nan")),
        ("projection", "design_percentile", -1.0),
        ("projection", "horizon_years", -1),
        ("projection", "growth_rate", -1.0),
        ("projection", "trailing_months", 0),
    ],
)
def test_invalid_basis_values_raise_config_error(
    built, basis, catalog, tmp_path: Path, section: str, field: str, value: Any
) -> None:
    bad = with_(basis, section, **{field: value})
    with pytest.raises(ConfigError, match=field):
        design(built, bad, catalog)
    t, profile, sku = built
    with pytest.raises(ConfigError, match=field):
        derive_inbound(profile, bad, t.daily, sku, catalog=catalog)
    path = tmp_path / "basis.yaml"
    path.write_text(bad.model_dump_json(), encoding="utf-8")  # JSON is YAML
    if value == value:  # nan does not survive JSON
        with pytest.raises(ConfigError, match=field):
            load_basis(path)


def test_no_operating_day_in_window_raises(built, basis, catalog) -> None:
    daily = built[0].daily.with_columns(is_operating=pl.lit(False))
    with pytest.raises(WhsizingError, match="no operating day"):
        design(built, basis, catalog, daily)


def test_non_positive_pack_data_raises(built, basis, catalog) -> None:
    t, profile, sku = built
    bad = sku.with_columns(units_per_pallet=pl.lit(0.0), units_per_case=pl.lit(None, pl.Float64))
    with pytest.raises(WhsizingError, match="units_per_pallet"):
        derive_inbound(profile, basis, t.daily, bad, catalog=catalog)


def test_derived_inbound_without_sku_table_names_the_fix(built, basis, catalog) -> None:
    t, profile, _ = built
    with pytest.raises(WhsizingError, match="sku=with_pack_data"):
        select_design_day(profile, basis, t.daily, catalog=catalog)
