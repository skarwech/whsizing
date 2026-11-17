"""F1 steps 1-7: SKUs, orders, returns, inventory snapshots and receipts.

Vectorised with numpy: no Python loop per order or per line (loops run over resampling rounds,
calendar shifts and month-end snapshots only). Times are drawn as Europe/Paris wall time and
stored as UTC. Output frames match `whsizing.schemas.frames`.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from whsizing.errors import ConfigError
from whsizing.synth.profile import LOCAL_TZ, SynthProfile, daily_lambda

RESAMPLE_ROUNDS = 20
GUMBEL_CHUNK_CELLS = 2**21  # caps the Gumbel fallback at ~16 MB per (orders × SKUs) array
_HEX = np.frombuffer(b"0123456789abcdef", dtype=np.uint8)
_EPOCH_WEEKDAY = 3  # 1970-01-01 was a Thursday (weekday 0 = Monday)


def generate(profile: SynthProfile, seed: int = 42) -> dict[str, pl.DataFrame]:
    """Return canonical frames: order_lines, sku_master, inventory, receipts."""
    if seed < 0:
        raise ConfigError(f"seed must be a non-negative integer, got {seed}")
    rng = np.random.default_rng(seed)
    order_key, sku_key, receipt_key = rng.integers(0, 2**64, size=3, dtype=np.uint64)
    sku_ids = _hex_ids(profile.n_skus, sku_key)
    sku = _sku_master(profile, sku_ids, rng)
    weights = _popularity(profile, rng)
    outbound, n_orders = _outbound(profile, sku, weights, order_key, rng)
    returns = _returns(profile, outbound, order_key, n_orders, rng)
    shipped = outbound.filter(pl.col("line_status") == "shipped")
    return {
        "order_lines": _finalize_lines(profile, pl.concat([outbound, returns]), sku_ids),
        "sku_master": sku,
        "inventory": _inventory(profile, shipped, sku_ids, rng),
        "receipts": _receipts(profile, shipped, sku, receipt_key, rng),
    }


def _hex_ids(n: int, key: np.uint64, start: int = 0) -> np.ndarray:
    """16-hex-char ids (§3.5). splitmix64 finalizer is a bijection: distinct index → distinct id."""
    x = np.arange(start, start + n, dtype=np.uint64) + key
    x ^= x >> np.uint64(30)
    x *= np.uint64(0xBF58476D1CE4E5B9)
    x ^= x >> np.uint64(27)
    x *= np.uint64(0x94D049BB133111EB)
    x ^= x >> np.uint64(31)
    b = x.astype(">u8").view(np.uint8).reshape(-1, 8)
    nibbles = np.stack([b >> 4, b & 15], axis=-1).reshape(-1, 16)
    return _HEX[nibbles].view("S16").ravel().astype("U16")


def _sku_master(p: SynthProfile, sku_ids: np.ndarray, rng: np.random.Generator) -> pl.DataFrame:
    """Step 1: lognormal dims (mm, 0.1 mm) and weight (kg, 1 g); case and pallet quantities."""
    n = p.n_skus
    dims = np.exp(rng.normal(np.asarray(p.mu_log_mm), p.sigma_log_mm, size=(n, 3)))
    dims = np.clip(np.round(dims, 1), 1.0, 2999.0)  # §4.1 plausible range (0, 3000)
    weight = np.clip(np.round(np.exp(rng.normal(p.mu_log_kg, p.sigma_log_kg, n)), 3), 0.001, 1499)
    upc_p = np.asarray(p.units_per_case_weights) / sum(p.units_per_case_weights)
    upc = rng.choice(np.asarray(p.units_per_case_values, dtype=np.int64), size=n, p=upc_p)
    unit_cube = dims.prod(axis=1) / 1e9
    pallet_cube = float(np.prod(p.pallet_dims_m))
    cpp = np.maximum(1, np.floor(pallet_cube / (upc * unit_cube))).astype(np.int64)
    category = rng.integers(1, p.n_categories + 1, n)
    return pl.DataFrame(
        {
            "sku": sku_ids,
            "length_mm": dims[:, 0],
            "width_mm": dims[:, 1],
            "height_mm": dims[:, 2],
            "weight_kg": weight,
            "units_per_case": upc,
            "cases_per_pallet": cpp,
            "units_per_pallet": upc * cpp,
            "category": np.char.add("CAT", category.astype(str)),
            "unit_cube_m3": unit_cube,
        }
    )


def _popularity(p: SynthProfile, rng: np.random.Generator) -> np.ndarray:
    """Step 2: w ∝ rank^(−s) on a random permutation; the last `inactive_share` get weight 0."""
    n_active = max(1, p.n_skus - round(p.n_skus * p.inactive_share))
    w = np.zeros(p.n_skus)
    w[rng.permutation(p.n_skus)[:n_active]] = np.arange(1, n_active + 1) ** -p.zipf_s
    return w / w.sum()


def _outbound(
    p: SynthProfile, sku: pl.DataFrame, w: np.ndarray, key: np.uint64, rng: np.random.Generator
) -> tuple[pl.DataFrame, int]:
    """Steps 3-4: orders per day ~ Poisson(λ_d), then lines, SKUs, quantities, times, channel."""
    day = np.repeat(np.arange(p.n_days), rng.poisson(daily_lambda(p)))
    n_orders = day.size
    if n_orders == 0:
        raise ConfigError(f"profile {p.name!r} generated no orders; check its scale/calendar")
    single = rng.random(n_orders) < p.single_line_prob
    n_lines = np.where(single, 1, 1 + rng.poisson(p.extra_lines_mean, n_orders))
    order = np.repeat(np.arange(n_orders), np.minimum(n_lines, np.count_nonzero(w)))
    sku_idx = _draw_skus(order, w, rng)
    hour = rng.choice(24, size=n_orders, p=_hourly_p(p))
    minute_of_period = day * 1440 + hour * 60 + rng.integers(0, 60, n_orders)
    local = np.datetime64(p.start_date, "m") + minute_of_period.astype("timedelta64[m]")
    names = np.asarray(list(p.channel_shares))
    shares = np.asarray(list(p.channel_shares.values()))
    channel = rng.choice(names.size, size=n_orders, p=shares / shares.sum())[order]
    cancelled = (rng.random(n_orders) < p.cancel_rate)[order]
    upc = sku["units_per_case"].to_numpy()[sku_idx]
    cases = upc * (1 + rng.poisson(p.cases_per_line_extra_mean, order.size))
    units = 1 + rng.poisson(p.units_per_line_extra_mean, order.size)
    frame = pl.DataFrame(
        {
            "order_id": _hex_ids(n_orders, key)[order],
            "local_ts": local[order].astype("datetime64[us]"),
            "sku_idx": sku_idx,
            "qty_units": np.where(names[channel] == "B2B", cases, units).astype(np.int64),
            "channel": names[channel],
            "line_status": np.where(cancelled, "cancelled", "shipped"),
        }
    )
    return frame, n_orders


def _draw_skus(order: np.ndarray, w: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """SKUs by weight, without replacement within an order (`order` is sorted, lines ≤ active
    SKUs): redraw duplicates for a few rounds, then redraw the orders still duplicated whole
    with Gumbel-top-k (exact), in chunks of ≤ GUMBEL_CHUNK_CELLS (orders × n_skus) cells."""
    cdf = np.cumsum(w)
    sku = np.searchsorted(cdf, rng.random(order.size) * cdf[-1], side="right")
    for _ in range(RESAMPLE_ROUNDS):
        dup = ~pl.Series(order * w.size + sku).is_first_distinct().to_numpy()
        if not dup.any():
            return sku
        sku[dup] = np.searchsorted(cdf, rng.random(int(dup.sum())) * cdf[-1], side="right")
    rows = np.flatnonzero(np.isin(order, order[dup]))
    _, first, k = np.unique(order[rows], return_index=True, return_counts=True)
    with np.errstate(divide="ignore"):  # inactive SKUs: log(0) = −inf, ranked last
        log_w = np.log(w)
    step = max(1, GUMBEL_CHUNK_CELLS // w.size)
    for a in range(0, k.size, step):
        kc, fc = k[a : a + step], first[a : a + step]
        ranked = np.argsort(-(log_w + rng.gumbel(size=(kc.size, w.size))), axis=1, kind="stable")
        pos = np.arange(kc.sum()) - np.repeat(np.cumsum(kc) - kc, kc)  # line rank in its order
        sku[rows[fc[0] : fc[0] + kc.sum()]] = ranked[np.repeat(np.arange(kc.size), kc), pos]
    return sku


def _hourly_p(p: SynthProfile) -> np.ndarray:
    w = np.asarray(p.hourly_weights, dtype=float)
    w[(p.cutoff_hour - 1) % 24] *= p.cutoff_boost  # pre-cut-off rush
    return w / w.sum()


def _weekday(days: np.ndarray) -> np.ndarray:
    """Weekday (0 = Monday) of datetime64 values."""
    return (days.astype("datetime64[D]").astype(np.int64) + _EPOCH_WEEKDAY) % 7


def _returns(
    p: SynthProfile, lines: pl.DataFrame, key: np.uint64, start: int, rng: np.random.Generator
) -> pl.DataFrame:
    """Step 5: `returns_rate` of shipped lines come back 3-20 days later as negative lines with a
    fresh order id (reusing the original id would net them out under F2's R6 merge). The delay is
    uniform over the open days (weekday weight > 0) of the window; returns with no open day in
    the window or landing after the period are dropped."""
    shipped = lines.filter(pl.col("line_status") == "shipped")
    picked = shipped.filter(pl.Series(rng.random(shipped.height) < p.returns_rate))
    lo, hi = p.return_delay_days
    sent = picked["local_ts"].to_numpy()
    offsets = np.arange(lo, hi + 1)
    landing = sent.astype("datetime64[D]")[:, None] + offsets.astype("timedelta64[D]")
    is_open = (np.asarray(p.weekday_weights) > 0)[_weekday(landing)]
    pick = np.where(is_open, rng.random(is_open.shape), -1.0).argmax(axis=1)
    ts = sent + offsets[pick].astype("timedelta64[D]")
    keep = is_open.any(axis=1) & (ts.astype("datetime64[D]") <= np.datetime64(p.end_date, "D"))
    return picked.filter(pl.Series(keep)).with_columns(
        order_id=pl.Series(_hex_ids(int(keep.sum()), key, start=start)),
        local_ts=pl.Series(ts[keep]),
        qty_units=-pl.col("qty_units"),
        line_status=pl.lit("returned"),
    )


def _to_utc(col: str) -> pl.Expr:
    """Paris wall time → UTC. DST gap times (02:xx on spring-forward day) shift by +1 h."""

    def local(e: pl.Expr) -> pl.Expr:
        return e.dt.replace_time_zone(LOCAL_TZ, ambiguous="earliest", non_existent="null")

    c = pl.col(col)
    utc = pl.coalesce(local(c), local(c + pl.duration(hours=1))).dt.convert_time_zone("UTC")
    return utc.dt.cast_time_unit("us")


def _finalize_lines(p: SynthProfile, lines: pl.DataFrame, sku_ids: np.ndarray) -> pl.DataFrame:
    """Canonical order_lines: UTC timestamps, SKU ids, total row order, provenance columns."""
    return (
        lines.with_columns(
            order_ts=_to_utc("local_ts"), sku=pl.Series(sku_ids[lines["sku_idx"].to_numpy()])
        )
        .sort(["order_ts", "order_id", "sku"])
        .select(
            "order_id",
            "order_ts",
            "sku",
            "qty_units",
            "channel",
            pl.col("line_status").cast(pl.Categorical),
            source_file=pl.lit(f"synth:{p.name}/order_lines"),
            source_row=pl.int_range(1, pl.len() + 1, dtype=pl.Int64),
        )
    )


def _day_index(p: SynthProfile, lines: pl.DataFrame) -> np.ndarray:
    start = np.datetime64(p.start_date, "D")
    return (lines["local_ts"].to_numpy().astype("datetime64[D]") - start).astype(np.int64)


def _inventory(
    p: SynthProfile, shipped: pl.DataFrame, sku_ids: np.ndarray, rng: np.random.Generator
) -> pl.DataFrame:
    """Step 6: month-end snapshots, stock = units shipped over 30 d × cover / 30 × noise.
    A period with no month end gets one snapshot on its last day."""
    dates = np.datetime64(p.start_date, "D") + np.arange(p.n_days)
    month_end = np.flatnonzero(
        (dates + np.timedelta64(1, "D")).astype("datetime64[M]") != dates.astype("datetime64[M]")
    )
    snaps = month_end if month_end.size else np.array([p.n_days - 1])
    day, sku, qty = _day_index(p, shipped), shipped["sku_idx"].to_numpy(), shipped["qty_units"]
    qty = qty.to_numpy().astype(float)
    sigma = p.stock_noise_sigma
    stock = []
    for m in snaps:  # ≤ 1 iteration per month
        sel = (day > m - 30) & (day <= m)
        demand = np.bincount(sku[sel], weights=qty[sel], minlength=p.n_skus)
        noise = np.exp(rng.normal(-(sigma**2) / 2, sigma, p.n_skus))
        stock.append(np.round(demand * p.days_of_cover / 30 * noise).astype(np.int64))
    return pl.DataFrame(
        {
            "sku": np.tile(sku_ids, snaps.size),
            "qty_units": np.concatenate(stock),
            "snapshot_date": np.repeat(dates[snaps], p.n_skus),
        }
    )


def _receipts(
    p: SynthProfile,
    shipped: pl.DataFrame,
    sku: pl.DataFrame,
    key: np.uint64,
    rng: np.random.Generator,
) -> pl.DataFrame:
    """Step 7: each Monday, replenish per SKU last week's shipped units in full cases, carrying
    the rounding surplus over: cumulative receipts = cumulative shipments rounded up to a case,
    so stock (and the cover it was set to) stays level and inbound ≈ outbound. One receipt id
    per (day, category); arrival 07:00-15:00 local."""
    # ponytail: base-stock (stock held level); seasonal re-targeting of the cover not modelled
    start = int(np.datetime64(p.start_date, "D").astype(np.int64))
    week0 = start - (start + _EPOCH_WEEKDAY) % 7  # Monday of the first week
    n_weeks = (start + p.n_days - 1 - week0) // 7 + 1
    week = (start + _day_index(p, shipped) - week0) // 7
    cells = week * p.n_skus + shipped["sku_idx"].to_numpy()
    out_qty = shipped["qty_units"].to_numpy()
    units = np.bincount(cells, weights=out_qty, minlength=n_weeks * p.n_skus).astype(np.int64)
    cum = units.reshape(n_weeks, p.n_skus).cumsum(axis=0)  # (week, sku)
    upc = sku["units_per_case"].to_numpy()
    step = np.diff(-(-cum // upc) * upc, axis=0, prepend=0)  # cumulative in full cases → weekly
    r_week, r_sku = np.nonzero(step)  # sorted by week, then SKU
    qty = step[r_week, r_sku]
    r_day = week0 + 7 * r_week + 7
    keep = r_day <= np.datetime64(p.end_date, "D").astype(np.int64)
    r_day, r_sku, qty = r_day[keep], r_sku[keep], qty[keep]
    cat = np.unique(sku["category"].to_numpy(), return_inverse=True)[1][r_sku]
    rkeys, rinv = np.unique(r_day * (p.n_categories + 1) + cat, return_inverse=True)
    minutes = p.receipt_hour * 60 + rng.integers(0, 480, rkeys.size)
    local = r_day.astype("datetime64[D]") + minutes[rinv].astype("timedelta64[m]")
    frame = pl.DataFrame(
        {
            "receipt_id": _hex_ids(rkeys.size, key)[rinv],
            "local_ts": local.astype("datetime64[us]"),
            "sku": sku["sku"].gather(r_sku),
            "qty_units": qty,
            "pallets": qty / sku["units_per_pallet"].to_numpy()[r_sku],
        }
    )
    return (
        frame.with_columns(receipt_ts=_to_utc("local_ts"))
        .select("receipt_id", "receipt_ts", "sku", "qty_units", "pallets")
        .sort(["receipt_ts", "receipt_id", "sku"])
    )
