"""F3 step 7: intraday profile per weekday on operating days, design weekday, peak hour."""

from __future__ import annotations

import polars as pl

from whsizing.schemas import Confidence, ProfileCfg

HOURS = 24


def design_weekday(daily: pl.DataFrame) -> int:
    """Weekday with the highest mean lines on operating days; lowest index on ties (I7)."""
    wk = (
        daily.filter("is_operating")
        .group_by("weekday")
        .agg(pl.col("lines").mean())
        .sort(["lines", "weekday"], descending=[True, False])
    )
    return int(wk["weekday"][0])


def intraday(
    lines: pl.DataFrame, daily: pl.DataFrame, cfg: ProfileCfg
) -> tuple[dict[int, list[float]], float, Confidence]:
    """→ (weekday → 24 line shares, peak_hour_share, confidence). Weekdays without operating
    days are absent. Lines without a time (local 00:00:00) carry no hour: they are left out of
    the shares (a weekday with no timed line takes `cfg.default_intraday`). Above
    `no_time_share_max` of such lines every weekday takes the default, flagged L."""
    op_dates = daily.filter("is_operating")["date"].implode()
    op = lines.filter(pl.col("date").is_in(op_dates)).with_columns(
        weekday=pl.col("date").dt.weekday().cast(pl.Int64) - 1
    )
    counts = op.filter(~pl.col("no_time")).group_by("weekday", "hour").len()
    shares = {int(wd): list(cfg.default_intraday) for wd in op["weekday"].unique()}
    for (wd,), g in counts.group_by("weekday"):
        hours = dict(zip(g["hour"].to_list(), g["len"].to_list(), strict=True))
        total = sum(hours.values())
        shares[int(wd)] = [hours.get(h, 0) / total for h in range(HOURS)]  # pyright: ignore[reportArgumentType]
    conf: Confidence = "H"
    if float(lines["no_time"].mean()) > cfg.no_time_share_max:  # pyright: ignore[reportArgumentType]
        shares, conf = {wd: list(cfg.default_intraday) for wd in shares}, "L"
    shares = dict(sorted(shares.items()))
    return shares, max(shares[design_weekday(daily)]), conf
