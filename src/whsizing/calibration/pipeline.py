"""F11 end to end: `calibrate(...)` (re-exported by `whsizing.calibration`)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from whsizing.calibration.actuals import load_actuals
from whsizing.calibration.evaluate import evaluate, mape
from whsizing.calibration.fit import Fit, fit_site
from whsizing.calibration.inputs import CalibrationInputs
from whsizing.calibration.models import CatalogTarget, FitReport, HoldoutReport
from whsizing.calibration.note import render_note
from whsizing.calibration.plots import write_plots
from whsizing.calibration.predict import INDIRECT, Baseline, baseline_monthly, restrict
from whsizing.errors import ConfigError
from whsizing.schemas import Flag

MIN_MONTHS = 12  # spec F11 data required: at least 12 months
PEAK_DEFINITION = "month of the highest total actual hours"
SHARE_ID = "labor.indirect_share_of_direct_hours"


@dataclass(frozen=True)
class CalibrationResult:
    """What `calibrate` computed and wrote. `fit_seconds`: the θ fit alone; `total_seconds`: the
    whole call (one F6 engine run, actuals, fit, hold-out, plots, files)."""

    fit: FitReport
    holdout: HoldoutReport
    flags: tuple[Flag, ...]
    accepted: bool
    out_dir: Path
    files: tuple[Path, ...]
    fit_seconds: float
    total_seconds: float


def calibrate(
    inputs: CalibrationInputs,
    actuals_path: Path | str,
    activity_map_path: Path | str,
    out_dir: Path | str,
    holdout_months: int = 3,
    *,
    observed_peak_lines_h: float | None = None,
) -> CalibrationResult:
    """Back-test the baseline scenario's labor against a site's monthly hours and calibrate it.

    Writes `fit.json`, `holdout.json`, `plots/*.png` and `calibration_note.md` into `out_dir`
    (F10: `<run>/calibration`). Raises ConfigError (map, options) or DataQualityError (actuals,
    too few months, months outside the daily series)."""
    t0 = time.perf_counter()
    out = Path(out_dir)
    if holdout_months < 1:
        raise ConfigError(f"holdout_months must be at least 1, got {holdout_months}")
    base = baseline_monthly(inputs)
    paid = inputs.basis.operations.annual_paid_hours_per_fte / 12
    actuals = load_actuals(actuals_path, activity_map_path, base.groups, paid)
    t1 = time.perf_counter()
    fit = fit_site(base, actuals, holdout_months)
    fit_seconds = time.perf_counter() - t1
    b = restrict(base, fit.months)
    holdout = evaluate(fit, b, observed_peak_lines_h)
    report = _fit_report(inputs, fit, b, [*fit.flags, *_data_flags(fit)])
    out.mkdir(parents=True, exist_ok=True)
    files = _write(out, report, holdout, fit, f"{inputs.basis.client}, {inputs.basis.site}")
    return CalibrationResult(
        report,
        holdout,
        tuple([*report.flags, *holdout.flags]),
        holdout.accepted,
        out,
        files,
        fit_seconds,
        time.perf_counter() - t0,
    )


def _data_flags(fit: Fit) -> list[Flag]:
    flags: list[Flag] = []
    if len(fit.months) < MIN_MONTHS:
        flags.append(
            Flag(
                code="W_SHORT_HISTORY",
                severity="warning",
                message=f"{len(fit.months)} month(s) of actuals; the spec asks for {MIN_MONTHS}",
                value=float(len(fit.months)),
            )
        )
    flags += [
        Flag(
            code=f"W_NO_ACTUALS:{g}",
            severity="warning",
            message=f"no actual hours map to {g!r}: its model hours are not compared (nor "
            "counted in the indirect base)",
        )
        for g in fit.excluded
    ]
    return flags


def _fit_report(
    inputs: CalibrationInputs, fit: Fit, base: Baseline, flags: list[Flag]
) -> FitReport:
    sp = fit.split
    targets = {g: list(base.targets[g]) for g in fit.groups if g in base.targets}
    if INDIRECT in fit.groups:
        targets[INDIRECT] = [CatalogTarget(param=SHARE_ID, typ_prior=base.indirect_share)]
    pred_fit = fit.total(fit.predicted)[list(sp.fit)]
    return FitReport(
        scenario=inputs.scenario.id,
        family=inputs.scenario.family,
        sites=1,
        months_fit=[fit.months[i] for i in sp.fit],
        months_holdout=[fit.months[i] for i in sp.holdout],
        peak_month=fit.months[sp.peak],
        peak_definition=PEAK_DEFINITION,
        theta=list(fit.theta),
        targets=targets,
        client_activities=list(fit.client),
        excluded_activities=list(fit.excluded),
        n_points=fit.n_points,
        cost=fit.cost,
        cost_prior_term=fit.prior_cost,
        status=fit.status,
        n_evals=fit.n_evals,
        mape_fit_total=mape(pred_fit, fit.total(fit.actual)[list(sp.fit)]),
        flags=flags,
    )


def _write(out: Path, fit: FitReport, hold: HoldoutReport, f: Fit, site: str) -> tuple[Path, ...]:
    paths = [out / "fit.json", out / "holdout.json", out / "calibration_note.md"]
    paths[0].write_text(fit.model_dump_json(indent=2) + "\n", encoding="utf-8")
    paths[1].write_text(hold.model_dump_json(indent=2) + "\n", encoding="utf-8")
    paths[2].write_text(render_note(fit, hold, site), encoding="utf-8")
    return (*paths, *write_plots(f, out))
