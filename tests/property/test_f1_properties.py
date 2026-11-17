"""F1 property tests: seed determinism and stock/flow invariants on random small profiles."""

from __future__ import annotations

import datetime as dt

import polars as pl
from hypothesis import given, settings
from hypothesis import strategies as st

from whsizing.synth import SynthProfile, generate


def _profile(n_skus: int, n_days: int, orders: float, start: dt.date) -> SynthProfile:
    return SynthProfile(
        name="prop", n_skus=n_skus, start_date=start, n_days=n_days, orders_per_day_mean=orders
    )


profiles = st.builds(
    _profile,
    n_skus=st.integers(5, 300),
    n_days=st.integers(7, 70),
    orders=st.floats(5, 120),
    start=st.dates(dt.date(2023, 1, 1), dt.date(2025, 12, 1)),
)


@settings(max_examples=25, deadline=None)
@given(profile=profiles, seed=st.integers(0, 2**32 - 1))
def test_seed_determinism(profile: SynthProfile, seed: int) -> None:
    a, b = generate(profile, seed), generate(profile, seed)
    for table in a:
        assert a[table].equals(b[table]), table


@settings(max_examples=25, deadline=None)
@given(profile=profiles, seed=st.integers(0, 2**32 - 1))
def test_non_negative_stock_and_consistent_flows(profile: SynthProfile, seed: int) -> None:
    frames = generate(profile, seed)
    inv, lines, rec = frames["inventory"], frames["order_lines"], frames["receipts"]
    assert (inv["qty_units"] >= 0).all()
    assert inv.height >= profile.n_skus  # ≥ 1 snapshot covering every SKU
    assert (rec["qty_units"] > 0).all()
    assert (lines["qty_units"] != 0).all()
    assert lines.select("order_id", "sku").is_unique().all()
    assert lines["sku"].is_in(frames["sku_master"]["sku"].implode()).all()
    local = lines["order_ts"].dt.convert_time_zone("Europe/Paris").dt.date()
    end = profile.start_date + dt.timedelta(days=profile.n_days - 1)
    assert local.is_between(profile.start_date, end).all()
    assert lines["line_status"].cast(pl.Utf8).is_in(["shipped", "cancelled", "returned"]).all()
