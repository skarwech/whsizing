"""F11 properties: the hold-out split (T11.3), the error metrics and the fit's recovery of
random multipliers."""

from __future__ import annotations

from functools import cache

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.unit.test_f11_predict import KNOWN, site_inputs, synthetic_actuals

from whsizing.calibration.evaluate import bias, mape
from whsizing.calibration.fit import MIN_FIT_MONTHS, fit_site, split_months
from whsizing.calibration.predict import INDIRECT, Baseline, baseline_monthly, predict, restrict

MONTHS = tuple(f"2025-{m:02d}" for m in range(1, 13))


@cache
def base() -> Baseline:
    return baseline_monthly(site_inputs())


@st.composite
def series(draw: st.DrawFn) -> tuple[np.ndarray, int]:
    n = draw(st.integers(MIN_FIT_MONTHS + 1, 48))
    h = draw(st.integers(1, min(6, n - MIN_FIT_MONTHS)))
    values = draw(st.lists(st.floats(0.1, 1e6), min_size=n, max_size=n))
    return np.array(values), h


@given(series())
def test_T11_3_split_always_contains_the_peak_month_and_partitions_the_months(
    case: tuple[np.ndarray, int],
) -> None:
    total, h = case
    n = len(total)
    s = split_months(total, h)
    assert s.peak == int(np.argmax(total)) and s.peak in s.holdout
    assert len(s.holdout) == h and list(s.holdout) == list(range(s.holdout[0], s.holdout[0] + h))
    assert sorted(s.fit + s.holdout) == list(range(n)) and len(s.fit) >= MIN_FIT_MONTHS
    assert s.shifted == (s.peak < n - h)
    assert s.holdout[0] == (s.peak if s.shifted else n - h)  # unshifted = the last h months


@given(
    st.lists(st.floats(1.0, 1e5), min_size=1, max_size=24),
    st.lists(st.floats(-0.9, 5.0), min_size=1, max_size=24),
)
def test_mape_is_at_least_the_absolute_bias_and_zero_on_a_perfect_prediction(
    actual: list[float], rel: list[float]
) -> None:
    n = min(len(actual), len(rel))
    a = np.array(actual[:n])
    p = a * (1 + np.array(rel[:n]))
    m, b = mape(p, a), bias(p, a)
    assert m is not None and b is not None
    assert m >= abs(b) - 1e-9 and m >= 0
    assert mape(a, a) == 0.0 and bias(a, a) == 0.0


@given(
    st.dictionaries(
        st.sampled_from(sorted(KNOWN)),
        st.floats(0.6, 1.8),
        min_size=len(KNOWN),
        max_size=len(KNOWN),
    )
)
@settings(max_examples=25, deadline=None)
def test_the_fit_recovers_random_multipliers_from_noise_free_actuals(
    truth: dict[str, float],
) -> None:
    """Noise-free actuals from random multipliers in [0.6, 1.8]: the effective multipliers come
    back within 5 % (T11.1's tolerance), inside the bounds."""
    fit = fit_site(base(), synthetic_actuals(base(), truth, MONTHS, noise=0.0))
    for t in fit.theta:
        assert t.lo - 1e-9 <= t.fitted <= t.hi + 1e-9
        if t.kind == "multiplier":
            assert t.effective is not None
            assert abs(t.effective / truth[t.name[2:]] - 1) < 0.05, t.name


@given(st.floats(0.5, 2.0), st.floats(0.05, 0.25))
def test_direct_hours_scale_with_one_over_m_and_with_one_plus_pfd(m: float, pfd: float) -> None:
    b = restrict(base(), MONTHS)
    groups = tuple(g for g in b.groups if g != INDIRECT)
    ones = predict(b, dict.fromkeys(groups, 1.0), b.pfd, groups)
    got = predict(b, dict.fromkeys(groups, m), pfd, groups)
    for g in groups:
        assert np.allclose(got[g], ones[g] * (1 + pfd) / (1 + b.pfd) / m, rtol=1e-12)
