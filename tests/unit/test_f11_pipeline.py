"""F11 `calibrate` end to end on the synthetic site: outputs, T11.2 through the API, flags,
determinism and the calibration note."""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import yaml
from tests.unit.test_f11_predict import KNOWN, site_inputs, synthetic_actuals

from whsizing.calibration import (
    CalibrationInputs,
    CalibrationResult,
    FitReport,
    HoldoutReport,
    baseline_monthly,
    calibrate,
)
from whsizing.calibration.predict import Baseline
from whsizing.errors import ConfigError, DataQualityError

MONTHS = tuple(f"2025-{m:02d}" for m in range(1, 13))
LABELS = {
    "receiving": "Réception",
    "put_away": "Mise en stock",
    "replenishment": "Réappro",
    "picking": "Préparation",
    "packing": "Emballage",
    "shipping": "Expédition",
    "returns": "Retours",
    "indirect": "Encadrement",
}
PNG = b"\x89PNG\r\n\x1a\n"


def write_actuals(
    folder: Path,
    base: Baseline,
    months: tuple[str, ...] = MONTHS,
    scale: dict[str, float] | None = None,
    extra: bool = True,
) -> tuple[Path, Path]:
    """actuals.csv and activity_map.yaml of the site with the KNOWN multipliers (2 % noise); with
    `extra` also a client-specific `kitting` (0.05 h per order) and an unmapped `Nettoyage`."""
    act = synthetic_actuals(base, KNOWN, months)
    rows = [
        (m, LABELS[g], round(float(h) * (scale or {}).get(m, 1.0), 2))
        for g, hours in act.hours.items()
        for m, h in zip(months, hours, strict=True)
    ]
    if extra:
        orders = dict(zip(base.months, base.orders, strict=True))
        rows += [(m, "Kitting", round(0.05 * float(orders[m]), 2)) for m in months]
        rows += [(m, "Nettoyage", 30.0) for m in months]
    csv_path = folder / "actuals.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "activity_client", "hours"])
        w.writerows(rows)
    amap = {"activities": {v: k for k, v in LABELS.items()}, "client_activities": ["kitting"]}
    amap["activities"]["Kitting"] = "kitting"
    map_path = folder / "activity_map.yaml"
    map_path.write_text(yaml.safe_dump(amap, allow_unicode=True), encoding="utf-8")
    return csv_path, map_path


@pytest.fixture(scope="module")
def inputs() -> CalibrationInputs:
    return site_inputs()


@pytest.fixture(scope="module")
def base(inputs: CalibrationInputs) -> Baseline:
    return baseline_monthly(inputs)


@pytest.fixture(scope="module")
def calibrated(
    tmp_path_factory: pytest.TempPathFactory, inputs: CalibrationInputs, base: Baseline
) -> CalibrationResult:
    folder = tmp_path_factory.mktemp("site")
    csv_path, map_path = write_actuals(folder, base)
    return calibrate(
        inputs, csv_path, map_path, folder / "calibration", observed_peak_lines_h=420.0
    )


def test_calibrate_writes_every_artifact(calibrated: CalibrationResult) -> None:
    out = calibrated.out_dir
    names = {p.relative_to(out).as_posix() for p in calibrated.files}
    assert names == {
        "fit.json",
        "holdout.json",
        "calibration_note.md",
        "plots/predicted_vs_actual.png",
        "plots/residuals_by_month.png",
        "plots/multipliers.png",
    }
    for p in calibrated.files:
        assert p.is_file() and p.stat().st_size > 0
        if p.suffix == ".png":
            assert p.read_bytes()[:8] == PNG
    fit = FitReport.model_validate_json((out / "fit.json").read_text(encoding="utf-8"))
    hold = HoldoutReport.model_validate_json((out / "holdout.json").read_text(encoding="utf-8"))
    assert fit == calibrated.fit and hold == calibrated.holdout
    assert calibrated.fit_seconds < calibrated.total_seconds < 60


def test_fit_json_describes_the_fit(calibrated: CalibrationResult) -> None:
    fit = calibrated.fit
    assert (fit.scenario, fit.family, fit.sites) == ("BASE", "manual_p2p", 1)
    assert fit.months_fit == list(MONTHS[:9]) and fit.months_holdout == list(MONTHS[9:])
    assert fit.peak_month == "2025-12" and "highest total actual hours" in fit.peak_definition
    names = [t.name for t in fit.theta]
    assert names == [f"m:{g}" for g in KNOWN] + ["eta", "pfd"]
    assert [c.name for c in fit.client_activities] == ["kitting"]
    assert fit.client_activities[0].hours_per_order == pytest.approx(0.05, rel=1e-3)
    assert {t.param for t in fit.targets["receiving"]} == {"labor.receiving", "labor.receipt_check"}
    assert "labor.indirect_share_of_direct_hours" in {t.param for t in fit.targets["indirect"]}
    assert fit.n_points == 8 * 9 and fit.status > 0  # 8 model activities × 9 fit months
    assert fit.mape_fit_total is not None and fit.mape_fit_total < 5
    for t in fit.theta:
        if t.kind == "multiplier" and t.name != "m:indirect":
            truth = KNOWN[t.name[2:]]
            assert t.effective == pytest.approx(truth, rel=0.05), t.name


def test_T11_2_unmapped_activity_warns_and_lands_in_indirect(
    calibrated: CalibrationResult, base: Baseline
) -> None:
    """Through `calibrate`: the warning is in the result and the note, and the indirect actuals
    of the hold-out are the mapped indirect hours plus the 30 h a month of the unmapped label."""
    codes = {f.code: f for f in calibrated.flags}
    warn = codes["W_UNMAPPED_ACTIVITY:Nettoyage"]
    assert warn.severity == "warning" and warn.value == pytest.approx(360.0)
    assert "F_CLIENT_ACTIVITY:kitting" in codes and "I_TEMPS_COMBINED" in codes
    mapped = synthetic_actuals(base, KNOWN, MONTHS).hours["indirect"]
    for i, row in enumerate(calibrated.holdout.table, start=9):
        assert row.actual["indirect"] == pytest.approx(mapped[i] + 30.0, abs=0.01)
    note = (calibrated.out_dir / "calibration_note.md").read_text(encoding="utf-8")
    assert "W_UNMAPPED_ACTIVITY:Nettoyage" in note


def test_the_acceptance_flag_is_reported(calibrated: CalibrationResult) -> None:
    h = calibrated.holdout
    assert h.peak_in_holdout and h.peak_month == "2025-12"
    assert h.peak_lines_h_observed == 420.0
    assert h.peak_lines_h_error_pct == pytest.approx(100 * (h.peak_lines_h_pred / 420 - 1))
    assert h.peak_lines_h_pred == pytest.approx(395.3469383512482 / 0.85)
    # unmapped cleaning hours are not in the model: the total is a few % off, still accepted
    assert calibrated.accepted and h.total.mape is not None and h.total.mape < 15
    assert set(h.per_activity) == {*KNOWN, "kitting"}


def test_the_same_inputs_give_identical_files(
    tmp_path: Path, inputs: CalibrationInputs, base: Baseline
) -> None:
    csv_path, map_path = write_actuals(tmp_path, base)
    one = calibrate(inputs, csv_path, map_path, tmp_path / "a")
    two = calibrate(inputs, csv_path, map_path, tmp_path / "b")
    for name in ("fit.json", "holdout.json", "calibration_note.md"):
        assert (one.out_dir / name).read_bytes() == (two.out_dir / name).read_bytes(), name
    assert json.loads((one.out_dir / "fit.json").read_text(encoding="utf-8"))["sites"] == 1


def test_calibration_note_content(calibrated: CalibrationResult) -> None:
    note = (calibrated.out_dir / "calibration_note.md").read_text(encoding="utf-8")
    for needle in (
        "# Calibration note: Client X, Lyon",
        "Calibrated on 1 site(s)",
        "ACCEPTED",
        "## Method",
        "scipy.optimize.least_squares",
        "Period: 2025-01 to 2025-12 (12 months)",
        "Fit months (9)",
        "Hold-out months (3): 2025-10, 2025-11, 2025-12",
        "Peak month: 2025-12",
        "| m:picking |",
        "| eta |",
        "## Hold-out errors",
        "| **total** |",
        "Peak lines/h: predicted 465, observed 420",
        "`kitting`",
        "## Caveats",
        "Temps are not separated",
        "stays at its prior",
        "does not move with the fit",
    ):
        assert needle in note, needle


def test_a_hold_out_that_misses_the_target_is_flagged_and_noted(
    tmp_path: Path, inputs: CalibrationInputs, base: Baseline
) -> None:
    csv_path, map_path = write_actuals(
        tmp_path, base, scale={"2025-10": 1.6, "2025-11": 1.6, "2025-12": 1.6}
    )
    r = calibrate(inputs, csv_path, map_path, tmp_path / "cal")
    assert not r.accepted and r.holdout.total.mape is not None and r.holdout.total.mape > 15
    assert "F_CALIB_ERROR" in [f.code for f in r.flags]
    assert "NOT ACCEPTED" in (r.out_dir / "calibration_note.md").read_text(encoding="utf-8")


def test_a_peak_outside_the_last_months_shifts_the_split_with_a_warning(
    tmp_path: Path, inputs: CalibrationInputs, base: Baseline
) -> None:
    csv_path, map_path = write_actuals(tmp_path, base, scale={"2025-03": 3.0})
    r = calibrate(inputs, csv_path, map_path, tmp_path / "cal")
    assert r.fit.peak_month == "2025-03" and r.fit.months_holdout == [
        "2025-03",
        "2025-04",
        "2025-05",
    ]
    assert "W_HOLDOUT_SHIFTED" in [f.code for f in r.flags] and r.holdout.peak_in_holdout
    note = (r.out_dir / "calibration_note.md").read_text(encoding="utf-8")
    assert "W_HOLDOUT_SHIFTED" in note


def test_partial_months_short_history_and_missing_activities_are_warned(
    tmp_path: Path,
) -> None:
    full = site_inputs(n_months=13)  # the daily series ends on 2026-01-28: 90.3 % of January
    keep = pl.col("date") <= date(2026, 1, 15)  # I74 (e): cut mid-month, under 90 %
    part = replace(full, daily=full.daily.filter(keep), lines=full.lines.filter(keep))
    b = baseline_monthly(part)
    months = tuple(b.months[1:])  # 2025-02 .. 2026-01
    csv_path, map_path = write_actuals(tmp_path, b, months)
    r = calibrate(part, csv_path, map_path, tmp_path / "cal")
    assert "W_PARTIAL_MONTH:2026-01" in [f.code for f in r.flags]
    short = tmp_path / "short"
    short.mkdir()
    csv8, map8 = write_actuals(short, b, tuple(b.months[:8]))
    r8 = calibrate(part, csv8, map8, short / "cal")
    assert "W_SHORT_HISTORY" in [f.code for f in r8.flags]
    text = csv8.read_text(encoding="utf-8").replace("Retours", "Nettoyage")  # no returns actuals
    csv8.write_text(text, encoding="utf-8")
    csv_dupe = short / "dupe.csv"
    csv_dupe.write_text(text, encoding="utf-8")
    with pytest.raises(DataQualityError, match="twice"):  # two 'Nettoyage' rows a month
        calibrate(part, csv_dupe, map8, short / "cal2")


@pytest.mark.parametrize(
    ("start", "end", "partial", "months"),
    [
        (date(2025, 1, 1), date(2025, 12, 9), "2025-12", MONTHS[:11]),  # the extract ends mid-month
        (date(2025, 1, 20), date(2025, 12, 31), "2025-01", MONTHS[1:]),  # and starts mid-month
    ],
)
def test_a_partial_month_is_left_out_of_fit_holdout_and_acceptance(
    tmp_path: Path,
    inputs: CalibrationInputs,
    base: Baseline,
    start: date,
    end: date,
    partial: str,
    months: tuple[str, ...],
) -> None:
    """Whole-month actuals against a part of the month would blame the model (MAPE 23 %, peak
    month -69 % when December is cut at the 9th): the month is dropped and flagged instead."""
    keep = pl.col("date").is_between(start, end)
    cut = replace(inputs, daily=inputs.daily.filter(keep), lines=inputs.lines.filter(keep))
    csv_path, map_path = write_actuals(tmp_path, base)  # the actuals of the full months
    r = calibrate(cut, csv_path, map_path, tmp_path / "cal")
    codes = [f.code for f in r.flags]
    assert f"W_PARTIAL_MONTH:{partial}" in codes and "W_SHORT_HISTORY" in codes
    assert [*r.fit.months_fit, *r.fit.months_holdout] == list(months)
    assert partial not in {*r.fit.months_fit, *r.fit.months_holdout, *r.holdout.months}
    assert r.fit.months_holdout == list(months[-3:])
    assert r.accepted and "F_CALIB_ERROR" not in codes
    assert r.holdout.total.mape is not None and r.holdout.total.mape < 5
    assert abs(r.holdout.peak_month_error_pct) < 5


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2025, 1, 2), date(2025, 12, 31)),  # no shipment on Jan 1
        (date(2025, 1, 1), date(2025, 12, 30)),  # none on Dec 31, the peak month of the actuals
    ],
)
def test_I74e_a_complete_month_with_an_empty_edge_day_stays_in_the_holdout(
    tmp_path: Path,
    inputs: CalibrationInputs,
    base: Baseline,
    start: date,
    end: date,
) -> None:
    """F11 audit finding 10: the daily series spans the first to the last shipped date, so a
    closed Jan 1 or Dec 31 gave coverage 30/31 < 1 and the complete month was dropped as partial
    (the true December peak left the hold-out). Partial now means under 90 % of the days."""
    keep = pl.col("date").is_between(start, end)
    cut = replace(inputs, daily=inputs.daily.filter(keep), lines=inputs.lines.filter(keep))
    csv_path, map_path = write_actuals(tmp_path, base)
    r = calibrate(cut, csv_path, map_path, tmp_path / "cal")
    codes = [f.code for f in r.flags]
    assert not [c for c in codes if c.startswith("W_PARTIAL_MONTH")]
    assert [*r.fit.months_fit, *r.fit.months_holdout] == list(MONTHS)
    assert r.fit.months_holdout == list(MONTHS[9:]) and r.fit.peak_month == "2025-12"
    assert r.holdout.peak_in_holdout and "W_HOLDOUT_SHIFTED" not in codes
    assert r.accepted and abs(r.holdout.peak_month_error_pct) < 5


def test_a_missing_activity_is_excluded_with_a_warning(
    tmp_path: Path, inputs: CalibrationInputs, base: Baseline
) -> None:
    csv_path, map_path = write_actuals(tmp_path, base)
    rows = [r for r in csv_path.read_text(encoding="utf-8").splitlines() if "Retours" not in r]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    r = calibrate(inputs, csv_path, map_path, tmp_path / "cal")
    assert r.fit.excluded_activities == ["returns"]
    assert "W_NO_ACTUALS:returns" in [f.code for f in r.flags]
    assert "m:returns" not in [t.name for t in r.fit.theta]


def test_calibrate_input_errors(tmp_path: Path, inputs: CalibrationInputs, base: Baseline) -> None:
    csv_path, map_path = write_actuals(tmp_path, base)
    with pytest.raises(ConfigError, match="holdout_months"):
        calibrate(inputs, csv_path, map_path, tmp_path / "x", holdout_months=0)
    with pytest.raises(DataQualityError, match="at least"):
        calibrate(inputs, csv_path, map_path, tmp_path / "x", holdout_months=10)
    with pytest.raises(ConfigError, match="cannot read"):
        calibrate(inputs, csv_path, tmp_path / "absent.yaml", tmp_path / "x")
    assert not (tmp_path / "x").exists()  # nothing written when the inputs are refused
    assert np.isfinite(base.orders).all()


def test_without_indirect_actuals_indirect_is_not_compared(
    tmp_path: Path, inputs: CalibrationInputs, base: Baseline
) -> None:
    csv_path, map_path = write_actuals(tmp_path, base, extra=False)
    rows = [r for r in csv_path.read_text(encoding="utf-8").splitlines() if "Encadrement" not in r]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    r = calibrate(inputs, csv_path, map_path, tmp_path / "cal")
    assert r.fit.excluded_activities == ["indirect"] and "indirect" not in r.fit.targets
    assert "W_NO_ACTUALS:indirect" in [f.code for f in r.flags]
    assert "indirect" not in r.holdout.per_activity
