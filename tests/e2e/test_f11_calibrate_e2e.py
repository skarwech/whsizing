"""F11 end to end on F1 synthetic ecom_mid (730 days from 2024-01-01, ≈ 0.98 M order lines):
F1 generate + FR CSV export -> F2 ingest -> F3 tables + F4 design day (`inputs_from_run`) ->
actuals of a site with KNOWN multipliers (the predictor generates them, 2 % noise, a client-specific
kitting and an unmapped cleaning label) -> `calibrate` -> catalog update on a copy.
Prints the run times. T11.1 on realistic data; T11.4 (the real pilot) is a manual acceptance."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from tests.unit.test_f11_pipeline import write_actuals
from tests.unit.test_f11_predict import KNOWN

from whsizing.calibration import baseline_monthly, calibrate, inputs_from_run, update_catalog
from whsizing.catalog import load_catalog
from whsizing.design import load_basis
from whsizing.io import ingest
from whsizing.schemas.project import InputSpec
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")
MONTHS = tuple(f"2024-{m:02d}" for m in range(1, 13))
BUDGET_S = 180


@pytest.mark.slow
def test_T11_1_known_multipliers_are_recovered_on_synthetic_ecom_mid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    t0 = time.perf_counter()
    profile_cfg = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
    export(generate(profile_cfg, seed=42), tmp_path, ("csv_fr",))
    run = tmp_path / "run"
    for ds in DATASETS:
        ingest({ds: InputSpec(files=[tmp_path / "csv_fr" / f"{ds}.csv"])}, run, b"e2e-salt")
    catalog = load_catalog(ROOT / "catalog")
    basis = load_basis(ROOT / "basis" / "example_basis.yaml")
    t1 = time.perf_counter()
    inputs = inputs_from_run(run, basis, catalog)
    base = baseline_monthly(inputs)
    t2 = time.perf_counter()
    assert set(MONTHS) <= set(base.months) and all(base.coverage[m] == 1.0 for m in MONTHS)
    csv_path, map_path = write_actuals(tmp_path, base, MONTHS)
    out = tmp_path / "run" / "calibration"
    result = calibrate(inputs, csv_path, map_path, out, observed_peak_lines_h=None)
    t3 = time.perf_counter()

    fit = result.fit
    assert fit.months_fit == list(MONTHS[:9]) and fit.status > 0
    for t in fit.theta:
        if t.kind == "multiplier" and t.name != "m:indirect":
            assert t.effective == pytest.approx(KNOWN[t.name[2:]], rel=0.05), t.name  # T11.1
    assert result.holdout.peak_in_holdout or any(
        f.code == "W_HOLDOUT_SHIFTED" for f in result.flags
    )  # T11.3 on real-shaped data
    assert "W_UNMAPPED_ACTIVITY:Nettoyage" in [f.code for f in result.flags]  # T11.2
    assert {p.name for p in result.files} >= {"fit.json", "holdout.json", "calibration_note.md"}

    copy = tmp_path / "catalog_copy"
    shutil.copytree(ROOT / "catalog", copy)
    changes = update_catalog(copy, fit, reviewer="Domain Expert", site="ecom_mid synthetic")
    assert any(c.applied for c in changes)
    load_catalog(copy)  # the updated copy still validates

    with capsys.disabled():
        h = result.holdout
        print(
            f"\nF11 e2e ecom_mid: F1+F2 {t1 - t0:.1f} s, F3+F4 + engine {t2 - t1:.1f} s, "
            f"calibrate {t3 - t2:.1f} s (fit {result.fit_seconds * 1000:.0f} ms, "
            f"{fit.n_evals} evaluations); hold-out MAPE {h.total.mape:.1f} %, peak-month "
            f"error {h.peak_month_error_pct:+.1f} %, accepted {result.accepted}"
        )
    assert time.perf_counter() - t0 < BUDGET_S


@pytest.mark.skip(
    reason="T11.4 needs the real pilot data (12 months of order lines and monthly hours per "
    "activity); manual acceptance by the domain expert (review #2)"
)
def test_T11_4_real_pilot_metrics_and_note() -> None:
    """Real pilot: metrics computed and note generated; reviewed by the expert."""
