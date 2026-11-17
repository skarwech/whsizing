"""F11 back-test and calibration of the labor model against a real site's monthly hours.

    from whsizing.calibration import CalibrationInputs, calibrate, inputs_from_run

    inputs = inputs_from_run(run_dir, basis, catalog, scenario)     # F3 tables + F4 design day
    result = calibrate(inputs, "calibration/actuals.csv", "calibration/activity_map.yaml",
                       out_dir="<run>/calibration", holdout_months=3, observed_peak_lines_h=None)
    result.accepted, result.holdout.total.mape, result.fit.theta, result.files

`whsizing calibrate <run>` (F10) calls `calibrate` with `out_dir = <run>/calibration`; the baseline
scenario is `scenarios.baseline` (a scenario id; "client_current" = a manual_p2p `ScenarioDef`).
`calibrate` raises ConfigError (activity map, options) and DataQualityError (actuals; too few
months; a month outside the daily series).

Files written to `out_dir`: `fit.json` (θ: prior, σ, bounds, fitted and effective values; split;
catalog Params each multiplier scales; flags), `holdout.json` (MAPE per activity, MAPE and bias of
the total, peak-month error, peak lines/h error, acceptance), `plots/*.png`,
`calibration_note.md` ("calibrated on N site(s)"). Same inputs give byte-identical JSON.

Modules: `actuals` (CSV + map, step 1), `predict` (monthly hours, closed-form in θ, step 2),
`fit` (θ, objective, split, step 3-5), `evaluate` (metrics, step 6), `plots` (step 7), `note`
(step 8), `catalog_update` (step 9: `update_catalog` on a COPY of the catalog).

Interpretations (to register in docs/INTERPRETATIONS.md):
- One multiplier per row of the F6c table: receiving (+ receipt_check), put_away, decant,
  replenishment, picking, packing (S + ML), shipping (parcel + pallet), returns, indirect; the
  client maps its labels to these.
- Hours are linear in 1 / productivity and (1 + PF&D) (I38): the engine runs once, θ is evaluated
  in closed form. η does not enter the monthly hours (it stays at its prior); PF&D is confounded
  with the multipliers, so the identified (effective) multiplier is m × (1 + pfd_basis) / (1 + pfd).
- Objective scale: the data term is divided by (0.3 % of the mean point)² so that the prior is a
  tie-breaker (`NOISE_REL`); soft_l1 unit `F_SCALE` = 2 such units.
- Peak month = month of the highest total actual hours; the hold-out is the last `holdout_months`
  months, shifted to start at the peak month (flag `W_HOLDOUT_SHIFTED`) when it is not in them.
- A month the daily series covers only in part (`W_PARTIAL_MONTH`: an extract starting or ending
  mid-month) is left out of the fit, the hold-out and the acceptance: its actuals are whole-month
  hours. A calendar month with no actuals for any label is flagged `W_MISSING_MONTH`. Two map keys
  equal after case and space folding must map to the same target (ConfigError otherwise).
- Peak lines/h error = design peak-hour lines / (growth factor × η_fit) against the observed peak:
  η stays at its prior, so it does not depend on the actuals (disclosed in the note).
- Model activities without actuals are not compared and not in the indirect base; headcount-only
  rows use annual_paid_hours_per_fte / 12 hours per head and month; temp_hours is informational.
"""

from whsizing.calibration.actuals import Actuals, load_actuals, read_actuals
from whsizing.calibration.catalog_update import update_catalog
from whsizing.calibration.evaluate import bias, evaluate, mape
from whsizing.calibration.fit import Fit, Split, fit_site, split_months
from whsizing.calibration.inputs import CalibrationInputs, inputs_from_run
from whsizing.calibration.models import (
    ActivityMap,
    CatalogChange,
    FitReport,
    HoldoutReport,
)
from whsizing.calibration.pipeline import CalibrationResult, calibrate
from whsizing.calibration.predict import Baseline, baseline_monthly, predict

__all__ = [
    "ActivityMap",
    "Actuals",
    "Baseline",
    "CalibrationInputs",
    "CalibrationResult",
    "CatalogChange",
    "Fit",
    "FitReport",
    "HoldoutReport",
    "Split",
    "baseline_monthly",
    "bias",
    "calibrate",
    "evaluate",
    "fit_site",
    "inputs_from_run",
    "load_actuals",
    "mape",
    "predict",
    "read_actuals",
    "split_months",
    "update_catalog",
]
