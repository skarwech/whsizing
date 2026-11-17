"""F11 step 6: MAPE, bias, peak-month and peak lines/h errors, acceptance (hand-computed)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pytest

from whsizing.calibration.evaluate import bias, evaluate, mape
from whsizing.calibration.fit import Fit, split_months
from whsizing.calibration.predict import Baseline
from whsizing.errors import ConfigError

MONTHS = tuple(f"2025-{m:02d}" for m in range(1, 7))


def test_mape_and_bias_definitions_by_hand() -> None:
    """errors = (pred − actual) / actual: [+0.1, −0.1, 0] → MAPE 6.667 %, bias 0 %;
    [+0.2, +0.6] → MAPE 40 %, bias 40 %."""
    pred, act = np.array([110.0, 90.0, 100.0]), np.array([100.0, 100.0, 100.0])
    assert mape(pred, act) == pytest.approx(20 / 3)
    assert bias(pred, act) == pytest.approx(0.0, abs=1e-12)
    assert mape(np.array([120.0, 80.0]), np.array([100.0, 50.0])) == pytest.approx(40.0)
    assert bias(np.array([120.0, 80.0]), np.array([100.0, 50.0])) == pytest.approx(40.0)
    assert bias(np.array([90.0, 90.0]), np.array([100.0, 100.0])) == pytest.approx(-10.0)


def test_a_month_without_actual_hours_is_skipped_and_none_when_all_are() -> None:
    assert mape(np.array([90.0, 55.0]), np.array([100.0, 0.0])) == pytest.approx(10.0)
    assert bias(np.array([90.0, 55.0]), np.array([100.0, 0.0])) == pytest.approx(-10.0)
    assert mape(np.array([5.0]), np.array([0.0])) is None
    assert bias(np.array([5.0]), np.array([0.0])) is None


def make_fit(
    pred: Mapping[str, Sequence[float]], act: Mapping[str, Sequence[float]], eta: float = 0.8
) -> Fit:
    """A Fit with given predicted / actual monthly hours (6 months, 3 held out)."""
    p = {g: np.array(v) for g, v in pred.items()}
    a = {g: np.array(v) for g, v in act.items()}
    split = split_months(np.sum(list(a.values()), axis=0), 3)
    return Fit(
        months=MONTHS, split=split, groups=tuple(a), excluded=(), client=(), m={}, eta=eta,
        pfd=0.12, theta=(), predicted=p, actual=a, cost=0.0, prior_cost=0.0, status=1,
        n_evals=1, n_points=0, flags=(),
    )  # fmt: skip


def hand_base() -> Baseline:
    return Baseline(
        months=MONTHS, hours={}, orders=np.ones(6), coverage={}, targets={}, sigma={}, pfd=0.12,
        eta=0.85, indirect_share=0.12, peak_hour_lines=400.0,
    )  # fmt: skip


ACT = {"A": [100, 100, 100, 100, 100, 150], "B": [50, 50, 50, 50, 50, 50]}  # totals 150 .. 200
PRED = {"A": [100, 100, 100, 110, 90, 165], "B": [50, 50, 50, 50, 50, 40]}  # 160, 140, 205


def test_holdout_metrics_by_hand() -> None:
    """Hold-out = months 4-6 (peak month 6, total 200). Total errors +6.667 %, −6.667 %, +2.5 %:
    MAPE 5.2778 %, bias 0.8333 %, peak-month error +2.5 %. A: +10, −10, +10 % → MAPE 10,
    bias 3.3333; B: 0, 0, −20 % → MAPE 6.6667, bias −6.6667. Peak lines/h 400 / 0.8 = 500 vs 400
    observed: +25 %."""
    r = evaluate(make_fit(PRED, ACT), hand_base(), observed_peak_lines_h=400.0)
    assert r.months == ["2025-04", "2025-05", "2025-06"] and r.peak_month == "2025-06"
    assert r.peak_in_holdout
    assert r.total.mape == pytest.approx(5.277778, abs=1e-5)
    assert r.total.bias == pytest.approx(0.833333, abs=1e-5)
    assert r.peak_month_error_pct == pytest.approx(2.5)
    assert r.per_activity["A"].mape == pytest.approx(10.0)
    assert r.per_activity["A"].bias == pytest.approx(10 / 3)
    assert r.per_activity["B"].mape == pytest.approx(20 / 3)
    assert r.per_activity["B"].bias == pytest.approx(-20 / 3)
    assert r.peak_lines_h_pred == pytest.approx(500.0)
    assert r.peak_lines_h_error_pct == pytest.approx(25.0)
    assert r.accepted and not r.flags and r.threshold_pct == 15.0
    assert [m.month for m in r.table] == r.months
    assert r.table[2].predicted["total"] == pytest.approx(205.0)
    assert r.table[2].actual["total"] == pytest.approx(200.0)


def test_peak_lines_per_hour_is_optional() -> None:
    r = evaluate(make_fit(PRED, ACT), hand_base())
    assert r.peak_lines_h_observed is None and r.peak_lines_h_error_pct is None
    with pytest.raises(ConfigError, match="observed_peak_lines_h"):
        evaluate(make_fit(PRED, ACT), hand_base(), observed_peak_lines_h=0.0)


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf"), float("-inf")])
def test_T11_3_observed_peak_lines_h_must_be_a_finite_positive_number(bad: float) -> None:
    """Final audit: nan and inf passed `<= 0` and holdout.json stored null for the user's value."""
    with pytest.raises(ConfigError, match=r"observed_peak_lines_h must be a positive number"):
        evaluate(make_fit(PRED, ACT), hand_base(), observed_peak_lines_h=bad)


def scaled(k: float) -> dict[str, list[float]]:
    """Hold-out months predicted k × actual for both activities."""
    return {g: [*v[:3], *(k * x for x in v[3:])] for g, v in ACT.items()}


def test_acceptance_needs_total_mape_and_peak_month_error_within_15_percent() -> None:
    """Gate: total MAPE ≤ 15 % and |peak-month error| ≤ 15 %; per-activity errors are not gated."""
    # A is +45 % / −45 % / 0 and B −90 % / +90 % / 0 off, the total is exact: accepted
    off = {"A": [100, 100, 100, 145, 55, 150], "B": [50, 50, 50, 5, 95, 50]}
    r = evaluate(make_fit(off, ACT), hand_base())
    assert r.per_activity["A"].mape == pytest.approx(30.0)
    assert r.per_activity["B"].mape == pytest.approx(60.0)
    assert r.total.mape == pytest.approx(0.0, abs=1e-9) and r.accepted
    # 14.9 % passes, 15.1 % fails (every hold-out month off by that much)
    assert evaluate(make_fit(scaled(1.149), ACT), hand_base()).accepted
    late = evaluate(make_fit(scaled(1.151), ACT), hand_base())
    assert late.total.mape == pytest.approx(15.1) and not late.accepted
    assert [f.code for f in late.flags] == ["F_CALIB_ERROR"]
    assert "diagnose by activity" in late.flags[0].message
    # total MAPE 8.89 % but the peak month is +20 % off: not accepted
    peaky = {"A": [100, 100, 100, 105, 105, 190], "B": [50, 50, 50, 50, 50, 50]}
    p = evaluate(make_fit(peaky, ACT), hand_base())
    assert p.total.mape == pytest.approx((10 / 3 + 10 / 3 + 20) / 3)
    assert p.peak_month_error_pct == pytest.approx(20.0) and not p.accepted
