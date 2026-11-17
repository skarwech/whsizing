"""F11 step 6: hold-out metrics (percent, hand-checkable definitions).

    error_i  = (pred_i − actual_i) / actual_i                     (months with actual = 0 skipped)
    MAPE     = 100 × mean_i |error_i|          bias = 100 × mean_i error_i (signed)
    total    = Σ over the compared activities (model + client-specific) of each month
    peak month error = 100 × error of the total of the peak month (signed)
    peak lines/h     = design peak-hour lines / (growth factor × η_fit) against the observed one

Acceptance (per spec, reported; per-activity errors are not gated): total MAPE and |peak-month
error| both ≤ 15 % [P].
"""

from __future__ import annotations

import math

import numpy as np

from whsizing.calibration.fit import Fit
from whsizing.calibration.models import (
    HOLDOUT_MAPE_MAX,
    ActivityMetrics,
    HoldoutMonth,
    HoldoutReport,
)
from whsizing.calibration.predict import Baseline
from whsizing.errors import ConfigError
from whsizing.schemas import Flag


def errors(pred: np.ndarray, actual: np.ndarray) -> np.ndarray:
    """Relative errors (pred − actual) / actual over the months where actual > 0."""
    p, a = np.asarray(pred, dtype=float), np.asarray(actual, dtype=float)
    keep = a > 0
    return (p[keep] - a[keep]) / a[keep]


def mape(pred: np.ndarray, actual: np.ndarray) -> float | None:
    """Mean absolute percentage error in %, None when no month has hours."""
    e = errors(pred, actual)
    return float(100 * np.mean(np.abs(e))) if e.size else None


def bias(pred: np.ndarray, actual: np.ndarray) -> float | None:
    """Mean signed error in % (> 0: the model over-predicts), None when no month has hours."""
    e = errors(pred, actual)
    return float(100 * np.mean(e)) if e.size else None


def metrics(pred: np.ndarray, actual: np.ndarray) -> ActivityMetrics:
    return ActivityMetrics(mape=mape(pred, actual), bias=bias(pred, actual))


def evaluate(fit: Fit, base: Baseline, observed_peak_lines_h: float | None = None) -> HoldoutReport:
    """Metrics on the hold-out months of `fit`."""
    obs = observed_peak_lines_h
    if obs is not None and not (math.isfinite(obs) and obs > 0):  # nan and inf are not `<= 0`
        raise ConfigError(f"observed_peak_lines_h must be a positive number, got {obs}")
    hold = list(fit.split.holdout)
    pred_total, act_total = fit.total(fit.predicted), fit.total(fit.actual)
    peak = fit.split.peak
    peak_err = float(100 * (pred_total[peak] - act_total[peak]) / act_total[peak])
    total = metrics(pred_total[hold], act_total[hold])
    lines_h = base.peak_hour_lines / fit.eta
    lines_err = (
        None
        if observed_peak_lines_h is None
        else float(100 * (lines_h - observed_peak_lines_h) / observed_peak_lines_h)
    )
    accepted = _accepted(total, peak_err)
    table = [
        HoldoutMonth(
            month=fit.months[i],
            actual={
                **{n: float(a[i]) for n, a in fit.actual.items()},
                "total": float(act_total[i]),
            },
            predicted={
                **{n: float(p[i]) for n, p in fit.predicted.items()},
                "total": float(pred_total[i]),
            },
        )
        for i in hold
    ]
    return HoldoutReport(
        months=[fit.months[i] for i in hold],
        peak_month=fit.months[peak],
        peak_in_holdout=peak in hold,
        per_activity={n: metrics(fit.predicted[n][hold], fit.actual[n][hold]) for n in fit.actual},
        total=total,
        peak_month_error_pct=peak_err,
        peak_lines_h_pred=float(lines_h),
        peak_lines_h_observed=observed_peak_lines_h,
        peak_lines_h_error_pct=lines_err,
        threshold_pct=HOLDOUT_MAPE_MAX,
        accepted=accepted,
        table=table,
        flags=_flags(total, peak_err),
    )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f} %"


def _accepted(total: ActivityMetrics, peak_err: float) -> bool:
    ok = total.mape is not None and total.mape <= HOLDOUT_MAPE_MAX
    return ok and abs(peak_err) <= HOLDOUT_MAPE_MAX


def _flags(total: ActivityMetrics, peak_err: float) -> list[Flag]:
    """F_CALIB_ERROR when the hold-out misses the target: diagnose by activity (spec step 10)."""
    if _accepted(total, peak_err):
        return []
    return [
        Flag(
            code="F_CALIB_ERROR",
            severity="warning",
            message=f"hold-out total MAPE {_pct(total.mape)} / peak-month error {peak_err:+.1f} % "
            f"exceed the {HOLDOUT_MAPE_MAX:.0f} % target: diagnose by activity (data gap, wrong "
            "driver, missing activity such as VAS, peak definition) and record the correction",
            value=total.mape,
        )
    ]
