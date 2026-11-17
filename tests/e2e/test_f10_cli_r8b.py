"""R8b (final audit) on the CLI, end to end on the small F10 site (tests/e2e/test_f10_cli_e2e.py
fixtures): M4 / I86 `calibrate` (parse first, copy on success, --force, --observed-peak-lines-h),
M5 / I85 b (1e12-quantity outliers stop in seconds with exit 4), L5 (a too long out_dir is exit 2),
the failed-run marker with a SIGTERM during sizing, and a corrupt trace.jsonl (one line, exit 2)."""

from __future__ import annotations

import csv
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from tests.e2e import test_f10_cli_e2e as f10
from tests.unit.test_f11_pipeline import write_actuals

from whsizing.app.state import is_run, list_runs
from whsizing.calibration import baseline_monthly, inputs_from_run
from whsizing.catalog import load_catalog
from whsizing.design import load_basis
from whsizing.scenarios.runner import FAILED_FILE

cli, copy_run, run_path, write_project = f10.cli, f10.copy_run, f10.run_path, f10.write_project
DATASETS, SALT = f10.DATASETS, f10.SALT
# the module-scoped fixtures of the F10 e2e module, by name (fixtures resolve names per module)
data, ingested, sized, salt_env = f10.data, f10.ingested, f10.sized, f10.salt_env

MONTHS = tuple(f"2025-{m:02d}" for m in range(1, 9))
LONG = "x" * 300  # NAME_MAX is 255 on macOS and Linux


def snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


@pytest.fixture(scope="module")
def site(sized, tmp_path_factory: pytest.TempPathFactory):
    """A copy of the sized run and the actuals of that site (good, bad, shifted)."""
    work = tmp_path_factory.mktemp("r8b_calib")
    run = copy_run(sized.run, work)
    base = baseline_monthly(
        inputs_from_run(
            run, load_basis(run / "inputs" / "basis.yaml"), load_catalog(run / "inputs" / "catalog")
        )
    )
    good, amap = write_actuals(work, base, MONTHS)
    bad = work / "actuals_bad.csv"
    rows = list(csv.reader(good.open(encoding="utf-8")))
    rows[1][2] = "abc"  # line 2: hours is not a number
    with bad.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return run, good, bad, amap


def calibrate(run: Path, actuals: Path, amap: Path, *extra: object):
    return cli("calibrate", run, "--actuals", actuals, "--activity-map", amap, *extra)


# ----------------------------------------------------------------------------- M4 (I86) calibrate
@pytest.mark.slow
def test_T10_3_calibrate_failed_recalibration_leaves_the_earlier_one_untouched(site) -> None:
    """The audit's reproduction: a good calibrate, then one on a damaged actuals file. The bad
    file is never copied into calibration/, fit.json / holdout.json / the note stay the earlier
    ones (byte for byte) and the exit code is 3 (DataQualityError), with or without --force; without
    it the command refuses to replace a calibration at all (exit 2)."""
    run, good, bad, amap = site
    first = calibrate(run, good, amap)
    assert first.exit_code == 0, first.output
    out = run / "calibration"
    mode = lambda p: stat.S_IMODE(p.stat().st_mode)  # noqa: E731
    assert mode(out) == mode(run / "dq")  # was 0700 (mkdtemp) beside 0755 folders
    before = snapshot(out)
    assert {
        "fit.json",
        "holdout.json",
        "calibration_note.md",
        "actuals.csv",
        "activity_map.yaml",
    } <= set(before)
    assert before["actuals.csv"] == good.read_bytes()

    refused = calibrate(run, bad, amap)
    assert refused.exit_code == 2 and "--force" in refused.stderr
    assert snapshot(out) == before

    failed = calibrate(run, bad, amap, "--force")
    assert failed.exit_code == 3, failed.output
    assert (
        "actuals_bad.csv: line 2" in failed.stderr and "'abc'" in failed.stderr
    )  # the user's file
    assert snapshot(out) == before  # nothing replaced, nothing half-written
    assert [p.name for p in run.iterdir() if p.name.startswith(".calibration")] == []  # no scratch


@pytest.mark.slow
def test_T10_3_calibrate_with_force_replaces_and_reports_the_observed_peak(site) -> None:
    """--force swaps the folder (the new inputs are copied in); --observed-peak-lines-h reaches
    holdout.json (peak lines/h error) and the output; a bad value is exit 2 and changes nothing."""
    run, good, _, amap = site
    out = run / "calibration"
    if not out.exists():  # this test also runs alone
        assert calibrate(run, good, amap).exit_code == 0
    before = snapshot(out)
    res = calibrate(run, good, amap, "--force", "--observed-peak-lines-h", 420)
    assert res.exit_code == 0, res.output
    hold = json.loads((out / "holdout.json").read_text(encoding="utf-8"))
    assert hold["peak_lines_h_observed"] == 420.0
    assert hold["peak_lines_h_error_pct"] == pytest.approx(
        100 * (hold["peak_lines_h_pred"] - 420) / 420
    )
    match = re.search(r"peak lines/h: model (\d+), observed 420, error ([+-][\d.]+) %", res.stdout)
    assert match and float(match[2]) == pytest.approx(hold["peak_lines_h_error_pct"], abs=0.05)
    after = snapshot(out)
    assert after["holdout.json"] != before["holdout.json"]  # replaced, not kept
    assert after["actuals.csv"] == good.read_bytes()

    snap = snapshot(out)
    for bad in ("0", "-3", "nan", "inf"):  # nan and inf slipped through `<= 0` (final audit)
        bad_peak = calibrate(run, good, amap, "--force", "--observed-peak-lines-h", bad)
        assert bad_peak.exit_code == 2, (bad, bad_peak.output)
        assert snapshot(out) == snap


def test_T10_3_calibrate_first_failed_calibration_creates_no_calibration_folder(
    site, sized, tmp_path: Path
) -> None:
    _, _, bad, amap = site
    fresh = copy_run(sized.run, tmp_path)
    assert not (fresh / "calibration").exists()
    res = calibrate(fresh, bad, amap)
    assert res.exit_code == 3, res.output
    assert not (fresh / "calibration").exists()  # the audit left the bad file here
    assert [p.name for p in fresh.iterdir() if p.name.startswith(".calibration")] == []


# ---------------------------------------------------------------------- M5 (I85 b) outlier quantity
def with_outliers(data: Path, folder: Path, n: int = 50) -> Path:
    """The site's CSVs with `n` extra order lines of quantity 1e12 (R13 lists such lines and keeps
    them), spread over the history."""
    out = folder / "outliers"
    out.mkdir()
    for ds in DATASETS:
        (out / f"{ds}.csv").write_bytes((data / f"{ds}.csv").read_bytes())
    rows = list(csv.reader((data / "order_lines.csv").open(encoding="utf-8")))[1:]
    with (out / "order_lines.csv").open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        for i in range(n):
            r = rows[(i * len(rows)) // n]
            w.writerow([f"outlier{i:03d}", r[1], r[2], "1000000000000", r[4], r[5]])
    return out


def test_T6_4_outlier_quantities_stop_in_seconds_with_exit_4_under_strict(
    data: Path, tmp_path: Path
) -> None:
    """50 lines of quantity 1e12 gave 4e8 cube ports and a run of 10 minutes or more (audit M5).
    Now the first count above engine.max_equipment_count raises SizingInfeasibleError: `--strict`
    exits 4 naming the resource, the value and R13, and the run is over in seconds."""
    project = write_project(with_outliers(data, tmp_path), tmp_path)
    cfg = yaml.safe_load(project.read_text(encoding="utf-8"))
    cfg["options"]["sensitivity"] = True  # the audit's case: the hook sees no computed scenario
    project.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    t0 = time.perf_counter()
    res = cli("run-all", project, "--strict", "--formats", "xlsx")
    seconds = time.perf_counter() - t0
    assert res.exit_code == 4, res.output
    assert seconds < 90  # 40 s of Erlang-C loop for the cube alone, before
    assert "not computed: S0, S1, S2" in res.stderr
    assert re.search(
        r"S0: .*forklifts = [\d,]+ exceeds engine.max_equipment_count \(100,000\)", res.stderr
    )
    assert "check units and outliers (R13)" in res.stderr


def test_T6_4_outlier_quantities_without_strict_stop_with_exit_4_and_no_report(
    data: Path, tmp_path: Path
) -> None:
    """Final audit M5 (I85 b): without --strict the 1e12 run used to exit 0 and build a report in
    which every scenario was not computed. When no scenario is computed at all it now exits 4 with
    the reason, builds no report, and the folder is a complete run (the three stubs, no FAILED)."""
    project = write_project(with_outliers(data, tmp_path), tmp_path)
    res = cli("run-all", project, "--formats", "xlsx", "--no-sensitivity")
    assert res.exit_code == 4, res.output
    assert "no scenario computed: not computed: S0, S1, S2" in res.stderr
    assert "check units and outliers (R13)" in res.stderr
    (run,) = [p for p in (tmp_path / "runs").iterdir() if p.is_dir()]
    assert list((run / "report").iterdir()) == []  # the folder is made empty (§2.4): no report
    for sid in ("S0", "S1", "S2"):
        stub = json.loads((run / "scenarios" / sid / "result.json").read_text(encoding="utf-8"))
        assert stub["status"] == "not_computed"
        assert "check units and outliers (R13)" in stub["status_reason"]
    assert not (run / FAILED_FILE).exists() and is_run(run)


# ----------------------------------------------------------------------------- L5 long out_dir
def test_L5_too_long_out_dir_is_exit_2_naming_the_path(data: Path, tmp_path: Path) -> None:
    project = write_project(data, tmp_path)
    cfg = yaml.safe_load(project.read_text(encoding="utf-8"))
    cfg["out_dir"] = str(tmp_path / LONG)
    project.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    res = cli("run-all", project)
    assert res.exit_code == 2, res.output
    assert LONG in res.stderr and "unexpected" not in res.stderr
    assert "cannot look for earlier runs" in res.stderr or "cannot create the folder" in res.stderr


# ------------------------------------------------------------- failed-run marker, SIGTERM (LOW)
KILL_DRIVER = """\
import sys, time
from pathlib import Path
import whsizing.scenarios.runner as runner

def slow(*args, **kwargs):  # a Python-level wait: the signal handler runs between bytecodes
    Path(sys.argv[2]).write_text("sizing")
    time.sleep(120)

runner.evaluate_scenario = slow
from whsizing.cli import app
app(["run-all", sys.argv[1], "--formats", "xlsx", "--no-sensitivity"])
"""


def test_T10_3_sigterm_during_sizing_marks_the_run_failed_and_exits_143(
    data: Path, tmp_path: Path
) -> None:
    """A run-all killed with SIGTERM while sizing: exit 143, `run_failed` in run.log, a
    logs/FAILED marker (class and reason only); the Streamlit run list does not offer the folder."""
    project = write_project(data, tmp_path)
    driver, started = tmp_path / "driver.py", tmp_path / "started"
    driver.write_text(KILL_DRIVER, encoding="utf-8")
    env = {**os.environ, "WHSIZING_SALT": SALT}
    proc = subprocess.Popen(
        [sys.executable, str(driver), str(project), str(started)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + 120
        while not started.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.monotonic() < deadline, "the run never reached the scenarios stage"
            time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        _, err = proc.communicate(timeout=60)
    finally:
        proc.kill()
    assert proc.returncode == 128 + signal.SIGTERM, err
    (run,) = [p for p in (tmp_path / "runs").iterdir() if p.is_dir()]
    marker = json.loads((run / FAILED_FILE).read_text(encoding="utf-8"))
    assert marker["error_type"] == "Terminated" and "SIGTERM" in marker["reason"]
    assert set(marker) == {"error_type", "reason"}  # no data
    events = [json.loads(line) for line in (run / "logs" / "run.log").read_text().splitlines()]
    failed = [e for e in events if e.get("event") == "run_failed"]
    assert len(failed) == 1 and failed[0]["error_type"] == "Terminated"
    assert not is_run(run) and list_runs(run.parent) == []
    assert SALT not in (run / FAILED_FILE).read_text(encoding="utf-8")


# ------------------------------------------------------------------ corrupt trace.jsonl (LOW)
@pytest.mark.parametrize("command", ["report", "compare"])
def test_T10_3_corrupt_trace_is_a_one_line_error_naming_file_and_line(
    command: str,
    sized,
    tmp_path: Path,
) -> None:
    run = copy_run(sized.run, tmp_path)
    trace = run / "scenarios" / "S1" / "trace.jsonl"
    lines = trace.read_text(encoding="utf-8").splitlines()
    lines[2] = '{"id": "x", "value": "nope"}'
    trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
    res = cli(command, run)
    assert res.exit_code == 2, res.output
    errors = [ln for ln in res.stderr.splitlines() if ln.startswith("error:")]
    assert len(errors) == 1 and "S1/trace.jsonl: line 3" in errors[0]
    assert "validation error" not in res.stderr and "pydantic" not in res.stderr
    trace.write_text("not json\n", encoding="utf-8")
    again = cli(command, run)
    assert again.exit_code == 2 and "trace.jsonl: line 1: invalid trace node" in again.stderr


@pytest.mark.parametrize("command", ["report", "compare"])
def test_T10_3_missing_trace_is_a_one_line_config_error_not_an_unexpected_one(
    command: str, sized, tmp_path: Path
) -> None:
    """Final audit: a deleted scenarios/S1/trace.jsonl ended as 'unexpected FileNotFoundError'
    (exit 1); it is exit 2 naming the file, like a corrupt one."""
    run = copy_run(sized.run, tmp_path)
    (run / "scenarios" / "S1" / "trace.jsonl").unlink()
    res = cli(command, run)
    assert res.exit_code == 2, res.output
    errors = [ln for ln in res.stderr.splitlines() if ln.startswith("error:")]
    assert len(errors) == 1 and "S1/trace.jsonl: not found" in errors[0]
    assert "unexpected" not in res.stderr and "Traceback" not in res.stderr
