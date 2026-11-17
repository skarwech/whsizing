"""R6 on the runner: the read-back sites of a finished run under a folder with glob characters
(I75 i: report data, calibration inputs), `options.keep_descriptions` (I78 e) and the strict
required-input rule (I80)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import polars as pl
import pytest
from tests.unit.test_f8_r5_runner import WEIRD, weird_project
from tests.unit.test_f8_runner import (
    NOW,
    ROOT,
    salt_env,  # noqa: F401  (autouse fixture: $WHSIZING_SALT for every run of this module)
    small_data,
    small_project,
)

from whsizing.calibration import inputs_from_run
from whsizing.catalog import load_catalog
from whsizing.design import load_basis
from whsizing.errors import SizingInfeasibleError
from whsizing.report import load_report_data
from whsizing.scenarios import find_canonical, runner
from whsizing.scenarios.manifest import engine_version, git_sha, read_manifest
from whsizing.schemas import ProjectOptions
from whsizing.schemas.run import RunOutput


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def weird_run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    """One complete run whose every path (project, data, catalog, out_dir) holds glob characters."""
    root = tmp_path_factory.mktemp("weird") / WEIRD
    return runner.run_scenarios(weird_project(data, root), now=NOW)


# ------------------------------------------------------------------ I75 i: the read-back sites
def test_I75_i_report_data_reads_the_daily_series_of_a_run_under_glob_characters(
    weird_run: RunOutput,
) -> None:
    """Was: `ConfigError: report: cannot read the daily series` (polars read the path as a glob)."""
    assert "[" in str(weird_run.run_dir)
    report = load_report_data(weird_run, "en")
    assert report.daily.height > 100 and "date" in report.daily.columns


def test_I75_i_calibration_inputs_read_the_sku_master_of_a_run_under_glob_characters(
    weird_run: RunOutput,
) -> None:
    """Was: a raw polars ComputeError (`pl.read_parquet(sku_master.parquet)` as a glob)."""
    run = weird_run.run_dir
    basis = load_basis(run / "inputs" / "basis.yaml")
    inputs = inputs_from_run(run, basis, load_catalog(run / "inputs" / "catalog"))
    assert inputs.sku.height > 0 and inputs.daily.height > 0


# ------------------------------------------------------------------ I78 e: keep_descriptions
def with_descriptions(data: Path, folder: Path) -> Path:
    """A copy of the small site whose SKU master also has a free-text Description column."""
    shutil.copytree(data, folder)
    sku = pl.read_csv(folder / "sku_master.csv")
    sku = sku.with_columns(Description=pl.lit("item ") + pl.col("SKU"))
    sku.write_csv(folder / "sku_master.csv")
    return folder


def canonical_sku_columns(out: RunOutput) -> list[str]:
    return pl.read_parquet(out.run_dir / "canonical" / "sku_master.parquet").columns


def test_I78_e_keep_descriptions_reaches_ingest_and_is_off_by_default(
    data: Path, tmp_path: Path
) -> None:
    site = with_descriptions(data, tmp_path / "site")
    off = runner.run_scenarios(small_project(site, tmp_path / "off"), now=NOW)
    assert "description" not in canonical_sku_columns(off)  # dropped like any free text (C2)
    kept = ProjectOptions(sensitivity=False, keep_descriptions=True)
    on = runner.run_scenarios(small_project(site, tmp_path / "on", options=kept), now=NOW)
    assert "description" in canonical_sku_columns(on)
    texts = pl.read_parquet(on.run_dir / "canonical" / "sku_master.parquet")["description"]
    assert texts.str.starts_with("item ").all()
    copy = (on.run_dir / "inputs" / "project.yaml").read_text(encoding="utf-8")
    assert "keep_descriptions: true" in copy  # the run says it kept them


def test_I78_e_ingest_key_adds_keep_descriptions_only_when_true(data: Path, tmp_path: Path) -> None:
    project = small_project(data, tmp_path)
    external = {"a.csv": "0" * 64}
    old_body = {  # the key of a run made before R6, rebuilt by hand
        "hashes": external,
        "datasets": {k: s.model_dump(mode="json") for k, s in project.inputs.items() if s},
        "salt": hashlib.sha256(b"s").hexdigest(),
        "upp": 24,
        "engine": [engine_version(), git_sha()],
    }
    old_key = hashlib.sha256(json.dumps(old_body, sort_keys=True).encode()).hexdigest()
    assert runner.ingest_key(project, external, b"s", 24) == old_key  # existing keys stay valid
    kept = project.model_copy(update={"options": ProjectOptions(keep_descriptions=True)})
    assert runner.ingest_key(kept, external, b"s", 24) != old_key


def test_I78_e_canonical_tables_are_not_reused_across_keep_descriptions(
    data: Path, tmp_path: Path
) -> None:
    """A run that dropped the descriptions must not feed one that keeps them, even if offered."""
    off = small_project(data, tmp_path / "runs")
    first = runner.run_scenarios(off, now=NOW)
    assert find_canonical(off) == first.run_dir
    kept = ProjectOptions(sensitivity=False, keep_descriptions=True)
    on = off.model_copy(update={"options": kept})
    assert find_canonical(on) is None  # the key differs
    second = runner.run_scenarios(on, now=NOW, reuse_canonical=first.run_dir)
    events = [
        json.loads(ln) for ln in (second.run_dir / "logs" / "run.log").read_text().splitlines()
    ]
    assert "canonical_reused" not in {e["event"] for e in events}
    assert "canonical_not_reused" in {e["event"] for e in events}
    assert find_canonical(on) == second.run_dir and find_canonical(off) == first.run_dir


# ------------------------------------------------------------------ I80: strict required inputs
@pytest.mark.parametrize("missing", ["sku_master", "inventory"])
def test_I80_a_strict_run_without_a_required_input_is_exit_4_before_any_folder(
    missing: str, data: Path, tmp_path: Path
) -> None:
    runs = tmp_path / "runs"
    base = small_project(data, runs)
    inputs = {k: v for k, v in base.inputs.items() if k != missing}
    for strict, options in ((True, None), (None, ProjectOptions(strict=True, sensitivity=False))):
        project = base.model_copy(
            update={"inputs": inputs} | ({"options": options} if options else {})
        )
        with pytest.raises(SizingInfeasibleError, match=rf"required input.*{missing}") as exc:
            runner.run_scenarios(project, strict=strict)
        assert exc.value.exit_code == 4
    assert not runs.exists() or list(runs.iterdir()) == []  # refused before ingest and run folder
    # `inputs[ds] = None` is as absent as a missing key
    none = base.model_copy(update={"inputs": {**inputs, missing: None}})
    with pytest.raises(SizingInfeasibleError, match=missing):
        runner.run_scenarios(none, strict=True)


@pytest.mark.parametrize("missing", ["sku_master", "inventory"])
def test_I80_a_the_same_project_without_strict_runs_as_before(
    missing: str, data: Path, tmp_path: Path
) -> None:
    base = small_project(data, tmp_path / "runs")
    inputs = {k: v for k, v in base.inputs.items() if k != missing}
    out = runner.run_scenarios(base.model_copy(update={"inputs": inputs}), now=NOW)
    assert [r.status for r in out.results.values()] == ["computed"] * 3
    off = runner.run_scenarios(base.model_copy(update={"inputs": inputs}), strict=False, now=NOW)
    assert off.run_dir.is_dir()


def test_I80_a_check_required_inputs_names_every_missing_dataset() -> None:
    runner.check_required_inputs({"order_lines", "sku_master", "inventory", "receipts"})
    runner.check_required_inputs({"sku_master", "inventory"})
    with pytest.raises(SizingInfeasibleError, match="sku_master, inventory"):
        runner.check_required_inputs({"order_lines"})


def assume_eligible_setup(data: Path, tmp_path: Path) -> tuple[Path, Path]:
    """(site, scenarios.yaml): every tenth SKU of the master has no length, and the automated
    scenarios of the example may assume it fits (`assume_eligible_if_missing_dims`)."""
    site = tmp_path / "site"
    shutil.copytree(data, site)
    sku = pl.read_csv(site / "sku_master.csv")
    blank = pl.int_range(pl.len()) % 10 == 0
    sku.with_columns(Length=pl.when(blank).then(None).otherwise(pl.col("Length"))).write_csv(
        site / "sku_master.csv"
    )
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    scenarios = tmp_path / "scenarios_assume.yaml"
    scenarios.write_text(
        text.replace(
            "assume_eligible_if_missing_dims: false", "assume_eligible_if_missing_dims: true"
        ),
        encoding="utf-8",
    )
    return site, scenarios


def test_I80_b_strict_refuses_an_automated_scenario_that_assumes_eligibility(
    data: Path, tmp_path: Path
) -> None:
    site, scenarios = assume_eligible_setup(data, tmp_path)
    project = small_project(site, tmp_path / "runs", scenarios=scenarios)
    out = runner.run_scenarios(project, now=NOW)  # non-strict: the run goes on with the flag
    flags = {sid: [f.code.split(":")[0] for f in r.flags] for sid, r in out.results.items()}
    assert flags["S2"].count("F_ELIG_ASSUMED") == 1 and "F_ELIG_ASSUMED" not in flags["S0"]
    assert out.results["S2"].scenario.family == "cube_asrs"
    with pytest.raises(SizingInfeasibleError, match=r"F_ELIG_ASSUMED in S2") as exc:
        runner.run_scenarios(project, strict=True)
    assert exc.value.exit_code == 4
    (strict_run,) = (r for r in (tmp_path / "runs").iterdir() if r != out.run_dir)
    assert (strict_run / "comparison" / "comparison.json").is_file()  # written, then the exit 4
    assert read_manifest(strict_run).run_id == strict_run.name


def test_I80_b_without_the_assumption_flag_strict_passes_on_the_same_data(
    data: Path, tmp_path: Path
) -> None:
    site, _ = assume_eligible_setup(data, tmp_path)  # missing lengths, example scenarios (false)
    out = runner.run_scenarios(small_project(site, tmp_path / "runs"), strict=True, now=NOW)
    codes = {f.code.split(":")[0] for r in out.results.values() for f in r.flags}
    assert "F_ELIG_ASSUMED" not in codes
