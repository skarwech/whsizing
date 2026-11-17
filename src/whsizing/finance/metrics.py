"""F7 metrics as pure functions of cash-flow lists (EUR, year 0..T; flows are Δcf = baseline
minus scenario, so a positive flow is a saving). No tracing here; compute.py traces the results."""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
import numpy_financial as npf  # pyright: ignore[reportMissingTypeStubs]

from whsizing.errors import DataQualityError


def tco(capex: float, opex: Sequence[float], rate: float) -> float:
    """capex + Σ_{t=1..T} opex_t / (1 + r)^t (renewals are inside opex_t)."""
    return capex + sum(x / (1 + rate) ** t for t, x in enumerate(opex, start=1))


def npv(flows: Sequence[float], rate: float) -> float:
    """Σ_t Δcf_t / (1 + r)^t with Δcf_0 undiscounted (I42); equals `numpy_financial.npv`."""
    return sum(x / (1 + rate) ** t for t, x in enumerate(flows))


def irr(flows: Sequence[float]) -> tuple[float | None, str | None]:
    """I37: `numpy_financial.irr` only with exactly one sign change (zeros ignored). Returns
    (irr, None), or (None, why) when it is undefined."""
    signs = [x > 0 for x in flows if x != 0]
    changes = sum(a != b for a, b in itertools.pairwise(signs))
    if changes == 0:
        return None, "IRR undefined: the flows have no sign change"
    if changes > 1:
        return None, f"IRR undefined: the flows change sign {changes} times"
    value = float(npf.irr(list(flows)))  # pyright: ignore[reportUnknownMemberType]
    if not np.isfinite(value):
        return None, "IRR undefined: no solution"
    return value, None


def payback(flows: Sequence[float]) -> float | None:
    """First t where the cumulative undiscounted Δcf is ≥ 0, linearly interpolated within the
    year; 0 when Δcf_0 ≥ 0 (capex delta ≤ 0); None when not reached within the horizon."""
    cum = flows[0]
    if cum >= 0:
        return 0.0
    for t, x in enumerate(flows[1:], start=1):
        if cum + x >= 0:
            return (t - 1) + (-cum) / x
        cum += x
    return None


def annuity_factor(rate: float, years: int) -> float:
    """r / (1 − (1 + r)^−T); 1 / T when r = 0."""
    return 1 / years if rate == 0 else rate / (1 - (1 + rate) ** -years)


def cost_per_line(tco_eur: float, rate: float, years: int, lines_year1: float) -> float:
    """Annualised TCO (TCO × annuity factor) / annual lines of year 1 (I36). Lines ≤ 0 (the
    operating days of the daily series ship nothing) raise DataQualityError."""
    if not lines_year1 > 0:
        raise DataQualityError(
            f"finance: the annual lines of year 1 are {lines_year1:g}, so the cost per line is "
            "undefined: the operating days of the daily series have no order line"
        )
    return tco_eur * annuity_factor(rate, years) / lines_year1
