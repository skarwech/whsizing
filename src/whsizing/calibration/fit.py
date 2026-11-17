"""F11 steps 3-5: the θ vector, the objective, the time split and the fit.

θ = one productivity multiplier m_g per calibration activity compared, η (flow efficiency) and
PF&D. Priors: m = 1 with σ = half the catalog range of the activity's standards (relative to typ;
0.75 for indirect, a constant without range), η = engine.eta_flow and PF&D = the basis value, both
with σ = half their [P] bounds. Bounds: m in [0.5, 2.0], η in [0.6, 1.0], PF&D in [0.05, 0.25].

    objective = Σ_i w_i (pred_i(θ) − actual_i)² + λ Σ_j ((θ_j − prior_j) / σ_j)²,  λ = 1

over the (activity, month) points of the fit months, w_i ∝ actual_i, scaled so that a residual of
`NOISE_REL` (0.3 %) of the mean point weighs 1; solved by `scipy.optimize.least_squares` (bounds,
`soft_l1`, `F_SCALE` residual units). Identification: η does not enter the monthly hours (I38: it
sets pickers and λ only) and PF&D is confounded with the multipliers (m and 1 + pfd trade off in
`hours / m × (1 + pfd)`); the prior fixes both. `effective` multiplier = m × (1 + pfd_basis) /
(1 + pfd): what the data identify and what the catalog update uses. Client-specific
activities are not in θ: hours per order = Σ actual / Σ orders over the fit months.

Model activities whose actual hours are all zero are not compared (and leave the indirect base).
A month whose days the calendar range of the daily series covers for less than 90 % [P] (a real
extract starts or ends mid-month; I74 e) is left out of the fit, the hold-out and the acceptance
(`W_PARTIAL_MONTH`): its actuals are whole-month hours. A first or last day without shipments
leaves the month complete. With every month partial there is nothing to fit: DataQualityError.

Time split: the last `holdout_months` months are held out and must contain the peak month (the
month of the highest total actual hours); when they do not, the hold-out becomes the
`holdout_months` months starting at the peak, the fit uses all the others, and `W_HOLDOUT_SHIFTED`
is raised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from scipy.optimize import least_squares

from whsizing.calibration.actuals import Actuals, without_months
from whsizing.calibration.models import (
    ETA_BOUNDS,
    LAMBDA,
    M_BOUNDS,
    NOISE_REL,
    PARTIAL_MONTH_COVERAGE_MIN,
    PFD_BOUNDS,
    ClientActivityFit,
    ThetaRow,
)
from whsizing.calibration.predict import INDIRECT, Baseline, predict, restrict
from whsizing.errors import ConfigError, DataQualityError
from whsizing.schemas import Flag

F_SCALE = 2.0  # soft_l1 residual unit: beyond 2 "noise units" a residual weighs linearly
MIN_FIT_MONTHS = 3


@dataclass(frozen=True)
class Split:
    """Month indices of the fit and of the hold-out; `peak` is in the hold-out."""

    fit: tuple[int, ...]
    holdout: tuple[int, ...]
    peak: int
    shifted: bool


@dataclass(frozen=True)
class Fit:
    """The fitted θ and the predictions on every month (model activities and client ones)."""

    months: tuple[str, ...]
    split: Split
    groups: tuple[str, ...]  # model activities compared (with actuals)
    excluded: tuple[str, ...]  # model activities without actuals
    client: tuple[ClientActivityFit, ...]
    m: dict[str, float]
    eta: float
    pfd: float
    theta: tuple[ThetaRow, ...]
    predicted: dict[str, np.ndarray]  # compared activities (model + client) -> hours per month
    actual: dict[str, np.ndarray]
    cost: float  # the spec objective at the optimum
    prior_cost: float  # its prior term
    status: int
    n_evals: int
    n_points: int
    flags: tuple[Flag, ...]

    def total(self, which: dict[str, np.ndarray]) -> np.ndarray:
        return np.sum(list(which.values()), axis=0)


def split_months(total: np.ndarray, holdout_months: int) -> Split:
    """Last `holdout_months` months, shifted to start at the peak month when it is not in them."""
    n, h = len(total), holdout_months
    if h < 1:
        raise ConfigError(f"holdout_months must be at least 1, got {h}")
    if n - h < MIN_FIT_MONTHS:
        raise DataQualityError(
            f"{n} month(s) of actuals: at least {MIN_FIT_MONTHS + h} are needed "
            f"({MIN_FIT_MONTHS} to fit, {h} held out)"
        )
    peak = int(np.argmax(total))
    start = n - h if peak >= n - h else peak
    hold = tuple(range(start, start + h))
    return Split(tuple(i for i in range(n) if i not in hold), hold, peak, start != n - h)


def fit_site(base: Baseline, actuals: Actuals, holdout_months: int = 3) -> Fit:
    """Fit θ on the fit months of `actuals` (months must be months of the daily series)."""
    missing = [m for m in actuals.months if m not in base.months]
    if missing:
        raise DataQualityError(f"actuals months {missing[:4]} are not in the daily series")
    partial = [m for m in actuals.months if base.coverage[m] < PARTIAL_MONTH_COVERAGE_MIN]
    actuals = without_months(actuals, partial)  # full-month actuals vs a part of the month
    if partial and not actuals.months:
        raise DataQualityError(
            f"W_PARTIAL_MONTH: every month of the actuals {partial[:4]} is only partly covered "
            f"by the daily series (under {PARTIAL_MONTH_COVERAGE_MIN:.0%} of its days; actuals "
            "are whole-month hours): extend the order lines to complete months"
        )
    b = restrict(base, actuals.months)
    seen = {g for g, h in actuals.hours.items() if h.sum() > 0}  # all zero: not done on site
    groups = tuple(g for g in b.hours if g in seen)
    excluded = tuple(g for g in b.hours if g not in seen)
    if not groups:
        raise DataQualityError(
            "no model activity has actual hours (missing or all zero): check the activity map"
        )
    names = (*groups, *actuals.client_activities)
    actual = {g: actuals.hours[g] for g in names}
    split = split_months(np.sum(list(actual.values()), axis=0), holdout_months)
    flags = [*_partial_flags(base, partial), *_split_flags(actuals.months, split, holdout_months)]
    sol = _solve(b, groups, actual, split)
    x, spec = sol.x, sol.spec
    m = dict(zip(groups, x[: len(groups)], strict=True))
    eta, pfd = float(x[-2]), float(x[-1])
    predicted = predict(b, m, pfd, groups)
    client = _client_fits(b, actuals, split)
    for c in client:
        predicted[c.name] = c.hours_per_order * b.orders
    theta = _theta_rows(b, spec, x, groups, actual, split)
    return Fit(
        months=actuals.months,
        split=split,
        groups=groups,
        excluded=excluded,
        client=client,
        m=m,
        eta=eta,
        pfd=pfd,
        theta=theta,
        predicted={n: predicted[n] for n in names},
        actual=actual,
        cost=sol.cost,
        prior_cost=sol.prior_cost,
        status=sol.status,
        n_evals=sol.n_evals,
        n_points=sol.n_points,
        flags=(*actuals.flags, *flags),
    )


@dataclass(frozen=True)
class _Spec:
    names: tuple[str, ...]
    prior: np.ndarray
    sigma: np.ndarray
    lo: np.ndarray
    hi: np.ndarray


def _spec(base: Baseline, groups: tuple[str, ...]) -> _Spec:
    k = len(groups)
    pfd_lo, pfd_hi = PFD_BOUNDS
    eta_lo, eta_hi = ETA_BOUNDS
    return _Spec(
        names=(*(f"m:{g}" for g in groups), "eta", "pfd"),
        prior=np.array([*[1.0] * k, base.eta, base.pfd]),
        sigma=np.array(
            [*(base.sigma[g] for g in groups), (eta_hi - eta_lo) / 2, (pfd_hi - pfd_lo) / 2]
        ),
        lo=np.array([*[M_BOUNDS[0]] * k, eta_lo, pfd_lo]),
        hi=np.array([*[M_BOUNDS[1]] * k, eta_hi, pfd_hi]),
    )


def weights(actual: np.ndarray) -> np.ndarray:
    """w_i ∝ actual_i, in 1 / h²: a residual of `NOISE_REL` × the mean point weighs 1 for a point
    of mean size."""
    mean = float(np.mean(actual))
    return (actual / mean) / (NOISE_REL * mean) ** 2


class _Solution(NamedTuple):
    x: np.ndarray
    spec: _Spec
    cost: float
    prior_cost: float
    status: int
    n_evals: int
    n_points: int


def _solve(
    base: Baseline, groups: tuple[str, ...], actual: dict[str, np.ndarray], split: Split
) -> _Solution:
    spec = _spec(base, groups)
    fit = list(split.fit)
    a = np.array([actual[g][fit] for g in groups])  # groups × fit months
    mean = float(a.mean())
    if mean <= 0:
        raise DataQualityError("the actual hours of the fit months are all zero")
    root_w = np.sqrt(weights(a))

    def pred(x: np.ndarray) -> np.ndarray:
        m = dict(zip(groups, x[: len(groups)], strict=True))
        p = predict(base, m, float(x[-1]), groups)
        return np.array([p[g][fit] for g in groups])

    def data(x: np.ndarray) -> np.ndarray:
        return (root_w * (pred(x) - a)).ravel()

    def prior(x: np.ndarray) -> np.ndarray:
        return np.sqrt(LAMBDA) * (x - spec.prior) / spec.sigma

    x0 = np.clip(spec.prior, spec.lo, spec.hi)
    sol = least_squares(
        lambda x: np.concatenate([data(x), prior(x)]),
        x0,
        bounds=(spec.lo, spec.hi),
        loss="soft_l1",
        f_scale=F_SCALE,
        x_scale="jac",
    )
    prior_cost = float(np.sum(prior(sol.x) ** 2))
    cost = float(np.sum(data(sol.x) ** 2)) + prior_cost
    return _Solution(sol.x, spec, cost, prior_cost, int(sol.status), int(sol.nfev), int(a.size))


def _client_fits(base: Baseline, actuals: Actuals, split: Split) -> tuple[ClientActivityFit, ...]:
    out = []
    fit = list(split.fit)
    for name in actuals.client_activities:
        orders = float(base.orders[fit].sum())
        if orders <= 0:
            raise DataQualityError(f"client activity {name!r}: no orders in the fit months")
        out.append(
            ClientActivityFit(
                name=name, hours_per_order=float(actuals.hours[name][fit].sum()) / orders
            )
        )
    return tuple(out)


def _theta_rows(
    base: Baseline,
    spec: _Spec,
    x: np.ndarray,
    groups: tuple[str, ...],
    actual: dict[str, np.ndarray],
    split: Split,
) -> tuple[ThetaRow, ...]:
    k = (1 + x[-1]) / (1 + base.pfd)
    rows = []
    for i, name in enumerate(spec.names):
        kind = "multiplier" if name.startswith("m:") else name
        g = name[2:] if kind == "multiplier" else ""
        note = ""
        identified = True
        if kind == "multiplier" and actual[g][list(split.fit)].sum() <= 0:
            identified, note = False, "no hours in the fit months: not identified by its own data"
        elif kind == "eta":
            identified, note = False, "does not enter monthly hours (I38): stays at its prior"
        elif kind == "pfd":
            identified, note = (
                False,
                "confounded with the multipliers: only m × (1 + pfd) is identified",
            )
        rows.append(
            ThetaRow(
                name=name,
                kind=kind,  # pyright: ignore[reportArgumentType]
                prior=float(spec.prior[i]),
                sigma=float(spec.sigma[i]),
                lo=float(spec.lo[i]),
                hi=float(spec.hi[i]),
                fitted=float(x[i]),
                effective=(float(x[i]) / (1.0 if g == INDIRECT else k)) if g else None,
                identified=identified,
                note=note,
            )
        )
    return tuple(rows)


def _partial_flags(base: Baseline, partial: list[str]) -> list[Flag]:
    return [
        Flag(
            code=f"W_PARTIAL_MONTH:{m}",
            severity="warning",
            message=f"the daily series covers {100 * base.coverage[m]:.0f} % of the days of {m} "
            f"(under {PARTIAL_MONTH_COVERAGE_MIN:.0%}) but the actuals are full-month hours: the "
            "month is left out of the fit, the hold-out and the acceptance",
            value=base.coverage[m],
        )
        for m in partial
    ]


def _split_flags(months: tuple[str, ...], split: Split, h: int) -> list[Flag]:
    if not split.shifted:
        return []
    first, last = months[split.holdout[0]], months[split.holdout[-1]]
    return [
        Flag(
            code="W_HOLDOUT_SHIFTED",
            severity="warning",
            message=f"the peak month {months[split.peak]} is not in the last {h} months: the "
            f"hold-out is {first} to {last}; the fit also uses the months after it, so this is "
            "not a pure forward back-test",
        )
    ]
