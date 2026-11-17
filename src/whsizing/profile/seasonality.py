"""F3 step 6: monthly and weekday indices, peak-to-average, trend (operating days only)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
from dateutil.relativedelta import relativedelta

from whsizing.schemas import Confidence, Seasonality

R10_MIN_MONTHS = 12  # R10: history < 12 months → seasonality flagged L
DAYS_PER_MONTH = 30.4375  # I52: leftover days → months


def _index(op: pl.DataFrame, key: pl.Expr, n: int, mean: float) -> list[float | None]:
    """Mean daily lines per key value (0..n-1) ÷ overall mean; None where the key is absent."""
    by = dict(op.group_by(key.alias("k")).agg(pl.col("lines").mean()).iter_rows())
    return [by[k] / mean if k in by else None for k in range(n)]


def trend_cagr(op: pl.DataFrame) -> float | None:
    """App. B: exp(12 × OLS slope(log monthly lines ~ month index)) − 1, monthly lines = mean
    daily lines of each calendar month (robust to partial months); None with < 2 months."""
    ym = pl.col("date").dt.year().cast(pl.Int64) * 12 + pl.col("date").dt.month().cast(pl.Int64)
    m = op.group_by(ym.alias("ym")).agg(pl.col("lines").mean()).sort("ym")
    if m.height < 2:
        return None
    slope = np.polyfit(m["ym"].to_numpy().astype(float), np.log(m["lines"].to_numpy()), 1)[0]
    return float(np.exp(12 * slope) - 1)


def calendar_months(start: date, end: date) -> float:
    """Whole calendar months from start to end (inclusive) + leftover days / 30.4375: two full
    calendar years are 24.0 months, leap year or not."""
    rd = relativedelta(end + timedelta(days=1), start)
    return rd.years * 12 + rd.months + rd.days / DAYS_PER_MONTH


def trend_confidence(months: float) -> Confidence:
    """[P] L if < 24 months, M if 24-36, H if > 36."""
    return "L" if months < 24 else "M" if months <= 36 else "H"


def seasonality(daily: pl.DataFrame) -> Seasonality:
    op = daily.filter("is_operating")
    lines = op["lines"].to_numpy()
    mean = float(lines.mean())
    months = calendar_months(daily["date"].min(), daily["date"].max())  # pyright: ignore[reportArgumentType]
    weekday = _index(op, pl.col("weekday"), 7, mean)
    return Seasonality(
        monthly_index=_index(op, pl.col("date").dt.month().cast(pl.Int64) - 1, 12, mean),
        weekday_index=[0.0 if v is None else v for v in weekday],
        peak_to_average=float(np.percentile(lines, 95) / mean),
        trend_cagr=trend_cagr(op),
        trend_confidence=trend_confidence(months),
        # R10 on calendar months, the same predicate as F2 io.rules._shorter(first, last, 12)
        confidence="L" if months < R10_MIN_MONTHS else "H",
    )
