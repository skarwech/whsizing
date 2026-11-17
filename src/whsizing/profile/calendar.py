"""F3 operating-day rule and holiday calendar (I2, Appendix B 'operating day')."""

from __future__ import annotations

from datetime import date

import holidays
import numpy as np
import polars as pl

from whsizing.errors import ConfigError
from whsizing.schemas import ProfileCfg


def operating_threshold(daily_lines: np.ndarray, share: float) -> float:
    """App. B: max(1, share × median(lines_d > 0)), median over the calendar's positive days."""
    positive = daily_lines[daily_lines > 0]
    return max(1.0, share * float(np.median(positive))) if positive.size else 1.0


def holiday_dates(start: date, end: date, cfg: ProfileCfg) -> list[date]:
    """Country public holidays (`holidays` package) between start and end, plus the overrides."""
    try:
        cal = holidays.country_holidays(cfg.holiday_country, years=range(start.year, end.year + 1))
    except NotImplementedError as e:
        raise ConfigError(
            f"profile_cfg.holiday_country: unknown country {cfg.holiday_country!r}"
        ) from e
    return sorted({d for d in cal if start <= d <= end} | set(cfg.holiday_overrides))


def flag_calendar(daily: pl.DataFrame, cfg: ProfileCfg) -> pl.DataFrame:
    """Add weekday (0 = Mon), is_holiday and is_operating. Operating iff lines_d ≥ threshold:
    the holiday clause ("a public holiday with no volume") is implied by the threshold (I2)."""
    thr = operating_threshold(daily["lines"].to_numpy().astype(float), cfg.operating_day_threshold)
    hol = holiday_dates(daily["date"].min(), daily["date"].max(), cfg)  # pyright: ignore[reportArgumentType]
    return daily.with_columns(
        weekday=pl.col("date").dt.weekday().cast(pl.Int64) - 1,
        is_operating=pl.col("lines") >= thr,
        is_holiday=pl.col("date").is_in(pl.Series(hol, dtype=pl.Date).implode()),
    )
