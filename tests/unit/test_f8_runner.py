"""F8a runner on a small synthetic site (F1: 300 SKUs, 120 days, ≈ 5,000 orders) with the example
basis and scenarios: run folder, baselines (client current / scenario, I42), T8.2 rows, strict and
non-strict infeasible scenarios (size_scenario monkeypatched), the F8b hook, the run log."""

from __future__ import annotations

import json
import re
import sys
import types
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from whsizing.errors import ConfigError, MappingError, SizingInfeasibleError
from whsizing.io import hash_id
from whsizing.scenarios import manifest as mf
from whsizing.scenarios import runner
from whsizing.scenarios.runner import SENSITIVITY_MODULE
from whsizing.schemas import Project, ProjectOptions, Sensitivity
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 18, 14, 2, 11, tzinfo=UTC)
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
SALT = "f8-test-salt"  # $WHSIZING_SALT of the F8 tests: the runner has no per-run salt of its own
SMALL = {"n_skus": 300, "n_days": 120, "orders_per_day_mean": 40}  # ≥ 3 months (R9)
_DATA: list[Path] = []


def small_data(factory: pytest.TempPathFactory) -> Path:
    """The small ecom site as English CSV files (generated once per session)."""
    if not _DATA:
        base = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
        out = factory.mktemp("f8_small")
        export(generate(base.model_copy(update=SMALL), seed=7), out, ("csv_en",))
        _DATA.append(out / "csv_en")
    return _DATA[0]


def small_project(data: Path, out_dir: Path, **update: object) -> Project:
    """The example project (Appendix E) on `data`, writing runs under `out_dir`."""
    project = Project(
        name="f8_small",
        out_dir=out_dir,
        catalog=ROOT / "catalog",
        inputs={ds: InputSpec(files=[data / f"{ds}.csv"]) for ds in DATASETS},
        basis=ROOT / "basis" / "example_basis.yaml",
        scenarios=ROOT / "scenarios" / "example_scenarios.yaml",
        options=ProjectOptions(sensitivity=False),  # F8b's hook is tested on its own below
    )
    return project.model_copy(update=update)


def scenarios_file(tmp_path: Path, baseline: str) -> Path:
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    path = tmp_path / f"scenarios_{baseline}.yaml"
    path.write_text(text.replace("baseline: client_current", f"baseline: {baseline}"), "utf-8")
    return path


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    """The salt every F8 run needs: $WHSIZING_SALT (the F8 test modules import this fixture)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", SALT)
        yield


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def base_run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    """The example scenarios, baseline client_current."""
    return runner.run_scenarios(small_project(data, tmp_path_factory.mktemp("runs")), now=NOW)


def test_run_folder_has_every_artifact(base_run: RunOutput) -> None:
    run = base_run.run_dir
    expected = [
        "manifest.json", "logs/run.log", "report", "inputs/project.yaml", "inputs/basis.yaml",
        "inputs/scenarios.yaml", "inputs/catalog/finance_defaults.yaml",
        *(f"inputs/mapping/{ds}.yaml" for ds in DATASETS),
        *(f"canonical/{ds}.parquet" for ds in DATASETS), "canonical/daily_series.parquet",
        "dq/dq_report.json", "dq/dq_report.html", "dq/ingest_manifest.json",
        "profile/demand_profile.json", "profile/charts", "design/design_day.json",
        "design/assumptions.json", "comparison/comparison.json",
        *(f"scenarios/{s}/{f}" for s in ("S0", "S1", "S2")
          for f in ("result.json", "finance.json", "trace.jsonl")),
    ]  # fmt: skip
    assert [p for p in expected if not (run / p).exists()] == []
    assert list((run / "report").iterdir()) == []  # F9 fills it
    assert not (run / "mapping").exists()  # moved under inputs/ (§2.4)
    assert not (run / "comparison" / "sensitivity.json").exists()
    assert json.loads((run / "comparison" / "comparison.json").read_text()) == json.loads(
        base_run.comparison.model_dump_json()
    )


def test_run_id_is_timestamp_and_first_six_hex_of_the_manifest_hash(base_run: RunOutput) -> None:
    run_id = base_run.manifest.run_id
    assert re.fullmatch(r"2026-11-18T14-02-11_[0-9a-f]{6}", run_id)
    assert base_run.run_dir.name == run_id
    assert base_run.manifest.created_at == NOW
    written = mf.read_manifest(base_run.run_dir)  # the hash of the file on disk, not of a draft
    assert mf.PROJECT_COPY in written.inputs and written.mapping_hashes and written.timings
    assert run_id == f"2026-11-18T14-02-11_{mf.manifest_hash(written)[:6]}"


def test_T8_2_every_scenario_appears_once_in_file_order(base_run: RunOutput) -> None:
    ids = ["S0", "S1", "S2"]
    assert list(base_run.results) == ids
    assert list(base_run.finances) == ids
    assert [r.scenario_id for r in base_run.comparison.rows] == ids
    assert all(r.status == "computed" for r in base_run.comparison.rows)
    cmp_json = (base_run.run_dir / "comparison" / "comparison.json").read_text().lower()
    assert "recommend" not in cmp_json  # no automatic label


def test_client_current_baseline_finances_every_scenario_against_basis_baseline(
    base_run: RunOutput,
) -> None:
    assert base_run.comparison.baseline_id == "client_current"
    for sid, fin in base_run.finances.items():
        assert fin.npv_vs_baseline is not None, sid
        assert fin.delta_cash_flows_typ[0] == -fin.capex_total.typ  # capex of the current: sunk
        assert any("client's current operation" in n for n in fin.notes), sid
    assert [r.payback_years is not None for r in base_run.comparison.rows] == [True] * 3


def test_stage_timings_are_in_the_manifest_and_the_run_log(base_run: RunOutput) -> None:
    stages = ("load", "inputs", "ingest", "profile", "design", "scenarios", "comparison")
    assert set(base_run.manifest.timings) == set(stages)
    assert all(t >= 0 for t in base_run.manifest.timings.values())
    records = [
        json.loads(line) for line in (base_run.run_dir / "logs" / "run.log").read_text().split("\n")
        if line
    ]  # fmt: skip
    assert {r["run_id"] for r in records} == {base_run.manifest.run_id}  # §2.8
    done = {r["stage"] for r in records if r["event"] == "stage_done"}
    assert done == set(stages)  # `load` runs before the folder exists: logged once it does
    load = next(r for r in records if r["event"] == "stage_done" and r["stage"] == "load")
    assert load["duration_s"] == round(base_run.manifest.timings["load"], 6)
    assert {r["scenario"] for r in records if r["event"] == "scenario_done"} == {"S0", "S1", "S2"}


def test_identifiers_are_hashed_in_the_canonical_tables(base_run: RunOutput, data: Path) -> None:
    raw = pl.read_csv(data / "order_lines.csv")["SKU"].unique().to_list()
    canon = pl.read_parquet(base_run.run_dir / "canonical" / "order_lines.parquet")["sku"]
    assert not set(raw) & set(canon.unique().to_list())
    assert canon.str.len_chars().unique().to_list() == [16]


def test_scenario_baseline_is_sized_first_and_the_others_are_financed_against_it(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real = runner.size_scenario

    def spy(profile, basis, dd, scenario, *args, **kwargs):
        order.append(scenario.id)
        return real(profile, basis, dd, scenario, *args, **kwargs)

    monkeypatch.setattr(runner, "size_scenario", spy)
    project = small_project(data, tmp_path / "runs", scenarios=scenarios_file(tmp_path, "S2"))
    out = runner.run_scenarios(project, now=NOW)
    assert order == ["S2", "S0", "S1"]  # the baseline first, then file order
    assert list(out.results) == ["S0", "S1", "S2"]  # results stay in file order
    assert out.comparison.baseline_id == "S2"
    assert out.finances["S2"].npv_vs_baseline is None  # no NPV against itself
    assert not out.finances["S2"].delta_cash_flows_typ
    for sid in ("S0", "S1"):  # I42: Δcf_0 = −(capex − capex of the baseline scenario)
        fin = out.finances[sid]
        capex_s2 = out.finances["S2"].capex_total.typ
        assert fin.delta_cash_flows_typ[0] == pytest.approx(-(fin.capex_total.typ - capex_s2))
        assert fin.npv_vs_baseline is not None
    assert "S2" not in out.comparison.ranking_payback


def fail_on(monkeypatch: pytest.MonkeyPatch, failing: set[str]) -> None:
    real = runner.size_scenario

    def fake(profile, basis, dd, scenario, *args, **kwargs):
        if scenario.id in failing:
            raise SizingInfeasibleError("no SKU can be stored in the family")
        return real(profile, basis, dd, scenario, *args, **kwargs)

    monkeypatch.setattr(runner, "size_scenario", fake)


def test_non_strict_infeasible_scenario_is_a_not_computed_row_and_the_others_continue(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_on(monkeypatch, {"S1"})
    out = runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    rows = {r.scenario_id: r for r in out.comparison.rows}
    assert list(rows) == ["S0", "S1", "S2"]
    assert rows["S1"].status == "not_computed"
    assert rows["S1"].status_reason == "SizingInfeasibleError: no SKU can be stored in the family"
    assert rows["S1"].tco is None and rows["S1"].payback_years is None
    assert rows["S0"].status == rows["S2"].status == "computed"
    assert out.comparison.ranking_tco == ["S0", "S2"]
    assert set(out.finances) == {"S0", "S2"}
    stub = json.loads((out.run_dir / "scenarios" / "S1" / "result.json").read_text())
    assert stub["status"] == "not_computed" and stub["status_reason"]
    assert not (out.run_dir / "scenarios" / "S1" / "finance.json").exists()
    assert out.results["S1"].area.fit is False


def test_strict_raises_exit_4_after_writing_every_artifact(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_on(monkeypatch, {"S2"})
    runs = tmp_path / "runs"
    by_argument = small_project(data, runs)
    by_option = small_project(data, runs, options=ProjectOptions(strict=True, sensitivity=False))
    for project, strict in ((by_argument, True), (by_option, None)):
        with pytest.raises(SizingInfeasibleError, match=r"not computed: S2") as exc:
            runner.run_scenarios(project, strict=strict)
        assert exc.value.exit_code == 4
    for run in runs.iterdir():  # all scenarios ran and everything was written first
        assert (run / "comparison" / "comparison.json").is_file()
        assert (run / "manifest.json").is_file()
        assert "run_failed" not in (run / "logs" / "run.log").read_text()  # exit 4 is not a crash
        assert (run / "scenarios" / "S1" / "finance.json").is_file()


def test_strict_false_overrides_the_project_option(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_on(monkeypatch, {"S2"})
    project = small_project(
        data, tmp_path / "runs", options=ProjectOptions(strict=True, sensitivity=False)
    )
    out = runner.run_scenarios(project, strict=False)
    assert out.comparison.rows[2].status == "not_computed"


def test_strict_raises_when_no_scenario_fits_the_building_and_non_strict_does_not(
    data: Path, tmp_path: Path
) -> None:
    text = (ROOT / "basis" / "example_basis.yaml").read_text(encoding="utf-8")
    assert "area_m2: 12000" in text
    basis = tmp_path / "tiny_building.yaml"
    basis.write_text(text.replace("area_m2: 12000", "area_m2: 50"), encoding="utf-8")
    project = small_project(data, tmp_path / "runs", basis=basis)
    out = runner.run_scenarios(project, now=NOW)
    assert [r.fit for r in out.comparison.rows] == [False] * 3
    assert all(any(f.code == "F_NO_FIT" for f in r.flags) for r in out.results.values())
    with pytest.raises(SizingInfeasibleError, match="no scenario fits the building"):
        runner.run_scenarios(project, strict=True)
    ok = runner.run_scenarios(small_project(data, tmp_path / "ok"), strict=True)  # they fit here
    assert all(r.fit for r in ok.comparison.rows)


def test_baseline_scenario_not_computed_leaves_the_others_without_npv(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_on(monkeypatch, {"S0"})
    project = small_project(data, tmp_path / "runs", scenarios=scenarios_file(tmp_path, "S0"))
    out = runner.run_scenarios(project)
    assert out.comparison.rows[0].status == "not_computed"
    for sid in ("S1", "S2"):
        fin = out.finances[sid]
        assert fin.npv_vs_baseline is None and fin.payback_years is None
        assert any("no baseline scenario" in n for n in fin.notes)
    assert out.comparison.ranking_payback == []


def test_sensitivity_hook_is_skipped_without_the_module_or_the_function(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = small_project(data, tmp_path / "runs", options=ProjectOptions())  # sensitivity on
    monkeypatch.setitem(sys.modules, SENSITIVITY_MODULE, None)  # import fails: module absent
    assert runner.run_scenarios(project, now=NOW).sensitivity is None
    monkeypatch.setitem(sys.modules, SENSITIVITY_MODULE, types.ModuleType(SENSITIVITY_MODULE))
    out = runner.run_scenarios(project, now=NOW)
    assert out.sensitivity is None
    assert not (out.run_dir / "comparison" / "sensitivity.json").exists()


def test_sensitivity_hook_receives_the_context_and_its_result_is_written(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook is F8b's entry point: it also re-sizes a variant with `evaluate_scenario`."""
    seen: dict[str, object] = {}

    def run_sensitivity(ctx: runner.RunContext, evaluated: dict[str, runner.Evaluated]):
        s1 = ctx.scenarios.scenarios[1]
        roles = dict.fromkeys(ctx.basis.finance.labor_cost_eur_h, 80.0)
        dearer = ctx.basis.finance.model_copy(update={"labor_cost_eur_h": roles})
        variant = runner.evaluate_scenario(
            ctx, s1, client_baseline=True, basis=ctx.basis.model_copy(update={"finance": dearer})
        )
        again = runner.evaluate_scenario(ctx, s1, client_baseline=True)
        seen.update(ctx=ctx, evaluated=evaluated, variant=variant, again=again)
        base = {sid: ev.finance.tco.typ for sid, ev in evaluated.items()}
        return Sensitivity(delta=ctx.project.options.delta, base_tco=base, tornado=[])

    module = types.ModuleType(SENSITIVITY_MODULE)
    module.run_sensitivity = run_sensitivity  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, SENSITIVITY_MODULE, module)
    project = small_project(data, tmp_path / "runs", options=ProjectOptions())  # sensitivity on
    out = runner.run_scenarios(project, now=NOW)
    ctx = seen["ctx"]
    assert isinstance(ctx, runner.RunContext)
    assert ctx.run_dir == out.run_dir and ctx.scenarios.baseline == "client_current"
    evaluated = seen["evaluated"]
    assert isinstance(evaluated, dict) and list(evaluated) == ["S0", "S1", "S2"]
    assert out.sensitivity is not None and set(out.sensitivity.base_tco) == {"S0", "S1", "S2"}
    written = json.loads((out.run_dir / "comparison" / "sensitivity.json").read_text())
    assert written["delta"] == 0.2
    assert "sensitivity" in out.manifest.timings
    # evaluate_scenario: the unchanged call gives the run's own result; a dearer labor cost
    # changes the finance, not the F6 sizing; nothing is written for a variant
    again, variant = seen["again"], seen["variant"]
    assert isinstance(again, runner.Evaluated) and isinstance(variant, runner.Evaluated)
    assert again.finance == out.finances["S1"] and again.result == out.results["S1"]
    assert variant.finance.opex_year1.typ > again.finance.opex_year1.typ
    assert variant.result == again.result
    assert len(list((out.run_dir / "scenarios").iterdir())) == 3
    off = project.options.model_copy(update={"sensitivity": False})
    seen.clear()
    assert runner.run_scenarios(project.model_copy(update={"options": off})).sensitivity is None
    assert not seen  # option off: the hook is not called


# ------------------------------------------------------------------ salt, reproducibility (C1, C2)
def run_bytes(run: Path) -> dict[str, bytes]:
    """The files whose bytes must reproduce: canonical tables, profile, design day, scenarios,
    comparison."""
    names = [*run.glob("canonical/*.parquet"), run / "profile" / "demand_profile.json"]
    names += [run / "design" / "design_day.json", run / "comparison" / "comparison.json"]
    names += run.glob("scenarios/*/*")
    return {str(p.relative_to(run)): p.read_bytes() for p in sorted(names)}


def test_two_fresh_runs_with_the_same_salt_are_byte_identical_and_get_the_same_run_id(
    data: Path, base_run: RunOutput, tmp_path: Path
) -> None:
    """§2.2 principle 5: no per-run randomness. Nothing is reused: the second run ingests again."""
    again = runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    one, two = run_bytes(base_run.run_dir), run_bytes(again.run_dir)
    assert len(one) == 17 and one.keys() == two.keys()  # 5 canonical, 3 JSON, 3 x 3 scenario
    assert [k for k in one if one[k] != two[k]] == []
    assert again.run_dir.name == base_run.run_dir.name  # same manifest hash, same second
    assert mf.manifest_hash(again.manifest) == mf.manifest_hash(base_run.manifest)


def test_the_salt_of_the_environment_hashes_the_ids_and_is_never_stored_in_the_run(
    base_run: RunOutput, data: Path
) -> None:
    run = base_run.run_dir
    raw = pl.read_csv(data / "order_lines.csv")["SKU"].unique().to_list()
    canon = set(pl.read_parquet(run / "canonical" / "order_lines.parquet")["sku"].to_list())
    assert canon and canon <= {hash_id(r, SALT.encode()) for r in raw}  # HMAC(WHSIZING_SALT, id)
    assert not (run / ".salt").exists()
    leaks = [str(f) for f in run.rglob("*") if f.is_file() and SALT.encode() in f.read_bytes()]
    assert leaks == []


def test_no_salt_source_is_a_config_error_before_any_folder_is_created(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WHSIZING_SALT")
    with pytest.raises(ConfigError, match="WHSIZING_SALT") as exc:
        runner.run_scenarios(small_project(data, tmp_path / "runs"))
    assert exc.value.exit_code == 2
    assert not (tmp_path / "runs").exists()


def test_the_shipped_example_project_takes_its_salt_from_the_environment() -> None:
    from whsizing.config import load_project

    example = load_project(ROOT / "project" / "example_project.yaml")
    assert example.salt_file is None  # so $WHSIZING_SALT, never a per-run salt


# ------------------------------------------------------------------ a failing run leaves a record
def run_folder(runs: Path) -> Path:
    (run,) = runs.iterdir()
    return run


def log_records(run: Path) -> list[dict[str, str]]:
    text = (run / "logs" / "run.log").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.split("\n") if line]


def test_a_failing_stage_is_logged_with_its_traceback_and_leaves_a_manifest(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(runner, "size_scenario", boom)
    with pytest.raises(RuntimeError, match="engine exploded"):  # the exception is not swallowed
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    run = run_folder(tmp_path / "runs")
    last = log_records(run)[-1]
    assert last["event"] == "run_failed" and last["error_type"] == "RuntimeError"
    assert last["error"] == "engine exploded"
    assert "Traceback" in last["traceback"] and "engine exploded" in last["traceback"]
    manifest = mf.read_manifest(run)  # written for the post-mortem
    assert manifest.run_id == run.name and manifest.created_at == NOW
    assert {"load", "inputs", "ingest", "profile", "design"} <= set(manifest.timings)
    assert (run / "inputs" / "mapping" / "order_lines.yaml").is_file()
    assert not (run / "mapping").exists()


def test_a_failed_ingest_files_the_mapping_under_inputs_and_keeps_its_exit_code(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_ingest(inputs: object, run_dir: Path, *args: object, **kwargs: object) -> None:
        (run_dir / "mapping").mkdir()
        (run_dir / "mapping" / "order_lines.yaml").write_text("dataset: order_lines\n")
        raise MappingError("column SKU: no candidate")

    monkeypatch.setattr(runner, "ingest", failing_ingest)
    with pytest.raises(MappingError, match="no candidate") as exc:
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    assert exc.value.exit_code == 2
    run = run_folder(tmp_path / "runs")
    assert (run / "inputs" / "mapping" / "order_lines.yaml").is_file()
    assert not (run / "mapping").exists()
    last = log_records(run)[-1]
    assert last["event"] == "run_failed" and last["error_type"] == "MappingError"
    assert mf.read_manifest(run).run_id == run.name


# ------------------------------------------------------------------ manifest after every stage (C1)
def test_manifest_is_written_when_the_folder_is_made_and_after_every_stage(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[set[str], bool]] = []
    real = runner.write_manifest

    def spy(manifest: mf.RunManifest, run_dir: Path) -> Path:
        seen.append((set(manifest.timings), bool(manifest.mapping_hashes)))
        return real(manifest, run_dir)

    monkeypatch.setattr(runner, "write_manifest", spy)
    out = runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    done: set[str] = set()
    expected = []
    for stage in (
        {"load"},
        {"inputs", "ingest"},
        {"profile", "design"},
        {"scenarios"},
        {"comparison"},
    ):
        done = done | stage
        expected.append(done)
    assert [t for t, _ in seen][:5] == expected  # folder made, then one write per finished stage
    assert [mapped for _, mapped in seen][:5] == [False, True, True, True, True]  # known at ingest
    assert seen[-1][0] == set(out.manifest.timings) == expected[-1]  # sensitivity is off here


def test_a_killed_run_keeps_the_manifest_of_its_last_finished_stage(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Killed(BaseException):  # SIGKILL stand-in: `except Exception` does not see it
        pass

    def killed(*args: object, **kwargs: object) -> None:
        raise Killed

    monkeypatch.setattr(runner, "size_scenario", killed)
    with pytest.raises(Killed):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    manifest = mf.read_manifest(run_folder(tmp_path / "runs"))
    assert set(manifest.mapping_hashes) == set(DATASETS)  # the ingest stage had finished
    assert {"load", "inputs", "ingest", "profile", "design"} <= set(manifest.timings)
    assert "scenarios" not in manifest.timings  # the stage that died is not recorded


def test_a_failed_run_keeps_the_mapping_hashes_of_the_stages_that_finished(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(runner, "size_scenario", boom)
    with pytest.raises(RuntimeError):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    failed = mf.read_manifest(run_folder(tmp_path / "runs"))
    assert set(failed.mapping_hashes) == set(DATASETS) and "scenarios" in failed.timings
