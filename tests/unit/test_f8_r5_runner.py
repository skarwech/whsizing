"""R5 remediation of the W5 findings on the runner (docs/INTERPRETATIONS.md I75): glob characters in
paths (i), `project_hash` checked by `rerun` (b), zero overrides (j), `delta` validated at project
load, load-stage records in logs/run.log, the RunOutput export."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest
import yaml
from tests.fixtures.factories import mock_manifest, mock_run_output, schema_examples
from tests.unit.test_f8_runner import (
    DATASETS,
    NOW,
    ROOT,
    log_records,
    salt_env,  # noqa: F401  (autouse fixture: $WHSIZING_SALT for every run of this module)
    small_data,
    small_project,
)

import whsizing.schemas as schemas
from whsizing.config import load_project
from whsizing.errors import ConfigError, MappingError
from whsizing.io.ingest import expand_files, read_parquet_file
from whsizing.logging import LOGGER_NAME
from whsizing.scenarios import find_canonical, rerun, runner
from whsizing.scenarios import manifest as mf
from whsizing.scenarios.logbuffer import LogBuffer
from whsizing.schemas import Project, ProjectOptions, RunManifest
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput

WEIRD = "client [2025] *x?"  # every glob character of fnmatch


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def base_run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return runner.run_scenarios(small_project(data, tmp_path_factory.mktemp("runs")), now=NOW)


# ------------------------------------------------------------------ I75 i: glob characters
def test_I75_i_expand_files_keeps_an_existing_path_literal_and_still_expands_patterns(
    tmp_path: Path,
) -> None:
    folder = tmp_path / WEIRD
    (folder / "data [1]").mkdir(parents=True)
    one, two = folder / "stock_1.csv", folder / "stock_2.csv"
    odd = folder / "data [1]" / "a [2025]?.csv"
    for f in (one, two, odd):
        f.write_text("x\n")
    assert expand_files([odd]) == [odd]  # an existing file named with glob characters
    assert expand_files([folder / "stock_*.csv"]) == [one, two]  # pattern in a weird folder
    assert expand_files([folder / "stock_?.csv", odd]) == [one, two, odd]
    assert expand_files([tmp_path / "*" / "stock_1.csv"]) == [one]  # a wildcard folder still works
    plain = tmp_path / "absent.csv"  # no glob character: left to the reader's "not found" error
    assert expand_files([plain]) == [plain]
    with pytest.raises(MappingError, match="no file matches"):
        expand_files([folder / "nothing_*.csv"])
    with pytest.raises(MappingError, match=r"no file matches.*absent \[1\]\.csv"):
        expand_files([folder / "absent [1].csv"])  # a missing file named with glob characters


def test_I75_i_expand_files_a_wildcard_folder_below_a_folder_with_glob_characters(
    tmp_path: Path,
) -> None:
    """R5 audit 4: `client [2025]/*/x.csv` read `[2025]` as a character class (no match)."""
    base = tmp_path / WEIRD / "deep [1]"
    for d in ("d1", "d2"):
        (base / d).mkdir(parents=True)
        (base / d / "x.csv").write_text("a\n")
    got = expand_files([base / "*" / "x.csv"])
    assert got == [base / "d1" / "x.csv", base / "d2" / "x.csv"]
    assert expand_files([base / "d?" / "x.csv"]) == got  # `?` below the literal part too
    with pytest.raises(MappingError, match="no file matches"):
        expand_files([base / "*" / "y.csv"])


def test_I75_i_read_parquet_file_reads_exactly_the_file_it_is_given(tmp_path: Path) -> None:
    path = tmp_path / WEIRD / "t.parquet"
    path.parent.mkdir()
    frame = pl.DataFrame({"a": [1, 2, 3]})
    frame.write_parquet(path)
    assert read_parquet_file(path).equals(frame)
    with pytest.raises(pl.exceptions.PolarsError):
        pl.read_parquet(path)  # why the helper exists: polars expands the path as a glob


def weird_project(data: Path, root: Path) -> Project:
    """project.yaml, data, basis, scenarios, catalog and out_dir all under `root` (glob characters),
    loaded as a client's project is; order_lines is given as a pattern."""
    root.mkdir(parents=True)
    shutil.copytree(data, root / "data [raw]")
    shutil.copytree(ROOT / "catalog", root / "catalog")
    shutil.copy(ROOT / "basis" / "example_basis.yaml", root / "basis.yaml")
    shutil.copy(ROOT / "scenarios" / "example_scenarios.yaml", root / "scenarios.yaml")
    files = {ds: f"data [raw]/{ds}.csv" for ds in DATASETS} | {
        "order_lines": "data [raw]/order_l*.csv"
    }
    spec = {
        "name": "weird",
        "out_dir": "runs [out]",
        "catalog": "catalog",
        "basis": "basis.yaml",
        "scenarios": "scenarios.yaml",
        "inputs": {ds: {"files": [f]} for ds, f in files.items()},
        "options": {"sensitivity": False},
    }
    (root / "project.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    return load_project(root / "project.yaml")


def test_I75_i_a_full_run_works_when_every_path_holds_glob_characters(
    data: Path, tmp_path: Path
) -> None:
    """Was: WhsizingError after a full ingest (polars read canonical/ as a glob), and a MappingError
    for a data path with `[2025]`."""
    root = tmp_path / WEIRD
    project = weird_project(data, root)
    out = runner.run_scenarios(project, now=NOW)
    assert out.run_dir.parent == root / "runs [out]"
    assert [r.status for r in out.results.values()] == ["computed"] * 3
    assert (out.run_dir / "canonical" / "order_lines.parquet").is_file()
    assert (out.run_dir / "profile" / "demand_profile.json").is_file()
    assert find_canonical(project) == out.run_dir  # the newest run with this ingest key
    assert runner.context_from_run(out.run_dir).sku.height > 0  # F10 stage commands read it back
    again = rerun(out.run_dir, now=NOW + timedelta(hours=1))  # reads canonical/ back, the same way
    for sid in out.results:
        one, two = (r.run_dir / "scenarios" / sid / "result.json" for r in (out, again))
        assert one.read_bytes() == two.read_bytes()
    reused = runner.run_scenarios(
        project, now=NOW + timedelta(hours=2), reuse_canonical=find_canonical(project)
    )
    assert "canonical_reused" in {r["event"] for r in log_records(reused.run_dir)}


# ------------------------------------------------------------------ I75 b: project_hash
def project_hash_of(run: Path) -> str | None:
    return RunManifest.model_validate_json((run / "manifest.json").read_text()).project_hash


def test_I75_b_the_manifest_carries_the_sha256_of_the_normalised_project(
    data: Path, base_run: RunOutput
) -> None:
    project = small_project(data, base_run.run_dir.parent)
    want = {  # name, language, profile_cfg and options, whichever dataset files are given
        "name": "f8_small",
        "language": ["fr"],
        "profile_cfg": project.profile_cfg.model_dump(mode="json"),
        # keep_descriptions is hashed only when set (like the ingest_key): old hashes stay valid
        "options": project.options.model_dump(mode="json", exclude={"keep_descriptions"}),
        "inputs": {ds: {"sheet": None} for ds in DATASETS},
    }
    digest = hashlib.sha256(json.dumps(want, sort_keys=True).encode()).hexdigest()
    assert base_run.manifest.project_hash == digest == project_hash_of(base_run.run_dir)
    # it is part of the hashed content: a manifest with another one is another run
    other = base_run.manifest.model_copy(update={"project_hash": "0" * 64})
    assert mf.manifest_hash(other) != mf.manifest_hash(base_run.manifest)
    assert base_run.run_dir.name.endswith(mf.manifest_hash(base_run.manifest)[:6])


def test_I75_b_project_hash_ignores_where_files_are_and_follows_what_the_run_computes(
    data: Path, tmp_path: Path
) -> None:
    project = small_project(data, tmp_path / "a")
    moved = project.model_copy(
        update={
            "out_dir": tmp_path / "elsewhere",
            "salt_file": tmp_path / "salt.txt",
            "catalog": tmp_path / "catalog2",
            "basis": tmp_path / "basis2.yaml",
            "scenarios": tmp_path / "scenarios2.yaml",
            "inputs": {ds: InputSpec(files=[tmp_path / "x.csv"], mapping=None) for ds in DATASETS},
        }
    )
    assert mf.project_hash(moved) == mf.project_hash(project)
    cfg = project.profile_cfg.model_copy(update={"abc_thresholds": (0.7, 0.9)})
    opts = ProjectOptions(sensitivity=False, delta=0.3)
    sheet = {**project.inputs, "inventory": InputSpec(files=[Path("i.xlsx")], sheet="Stock")}
    for change in (
        {"profile_cfg": cfg},
        {"options": opts},
        {"name": "other"},
        {"language": ["en"]},
        {"inputs": sheet},
        {"inputs": {k: v for k, v in project.inputs.items() if k != "receipts"}},
    ):
        assert mf.project_hash(project.model_copy(update=change)) != mf.project_hash(project)


def test_I75_b_rerun_keeps_the_project_hash_and_refuses_an_edited_project_copy(
    base_run: RunOutput, tmp_path: Path
) -> None:
    again = rerun(base_run.run_dir, now=NOW + timedelta(hours=1), out_dir=tmp_path / "ok")
    assert again.manifest.project_hash == base_run.manifest.project_hash is not None
    copy = tmp_path / "copy" / "run"
    shutil.copytree(base_run.run_dir, copy)
    path = copy / "inputs" / "project.yaml"
    text = path.read_text(encoding="utf-8")
    assert "- 0.8\n" in text  # profile_cfg.abc_thresholds: the edit of the finding
    path.write_text(text.replace("- 0.8\n", "- 0.7\n", 1), encoding="utf-8")
    with pytest.raises(ConfigError, match=r"inputs/project\.yaml differs.*project_hash") as exc:
        rerun(copy, out_dir=tmp_path / "out")
    assert exc.value.exit_code == 2
    assert not (tmp_path / "out").exists()  # refused before a folder is made


def test_I75_b_a_manifest_from_before_project_hash_is_not_checked() -> None:
    old = json.loads(mock_manifest().model_dump_json())
    del old["project_hash"]
    legacy = RunManifest.model_validate(old)
    assert legacy.project_hash is None
    draft = legacy.model_copy(update={"project_hash": "a" * 64})
    runner._check_copies(legacy, draft)  # pyright: ignore[reportPrivateUsage]  # no error
    with pytest.raises(ConfigError, match="project_hash"):
        runner._check_copies(draft, legacy.model_copy(update={"project_hash": "b" * 64}))  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------------ I75 j and delta
def test_I75_j_a_zero_station_rate_is_a_config_error_in_the_load_stage(
    data: Path, tmp_path: Path
) -> None:
    """Was: ZeroDivisionError from engine/throughput.py:446 after the whole ingest."""
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    assert '"amr_gtp.station_rate_lines_h": 230' in text
    path = tmp_path / "zero.yaml"
    path.write_text(text.replace('station_rate_lines_h": 230', 'station_rate_lines_h": 0'), "utf-8")
    project = small_project(data, tmp_path / "runs", scenarios=path)
    with pytest.raises(ConfigError, match=r"amr_gtp\.station_rate_lines_h: value 0.*> 0") as exc:
        runner.run_scenarios(project, now=NOW)
    assert exc.value.exit_code == 2
    assert not (tmp_path / "runs").exists()  # no folder: nothing was ingested


@pytest.mark.parametrize(
    "const", ["engine.eta_flow", "storage.skus_per_mixed_bin", "storage.default_units_per_pallet"]
)
def test_I75_j_a_zero_divisor_constant_in_a_scenario_is_a_config_error_in_the_load_stage(
    data: Path, tmp_path: Path, const: str
) -> None:
    """R5 audit 3: eta_flow = 0 was a raw ZeroDivisionError after the ingest and the profile, and
    the other two completed with inf."""
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    head = '{id: S0, name: "Manuel optimisé", family: manual_p2p, is_baseline: false'
    assert head + "}" in text
    path = tmp_path / "zero.yaml"
    path.write_text(text.replace(head, head + f', overrides: {{"{const}": 0}}'), "utf-8")
    project = small_project(data, tmp_path / "runs", scenarios=path)
    with pytest.raises(ConfigError, match=rf"{const} = 0.*> 0") as exc:
        runner.run_scenarios(project, now=NOW)
    assert exc.value.exit_code == 2
    assert not (tmp_path / "runs").exists()  # no folder: nothing was ingested


def write_project(tmp_path: Path, options: str) -> Path:
    path = tmp_path / "project.yaml"
    path.write_text(
        f"name: p\ninputs: {{}}\nbasis: b.yaml\nscenarios: s.yaml\noptions: {{{options}}}\n",
        "utf-8",
    )
    return path


@pytest.mark.parametrize("delta", ["1", "1.0", "1.5", "-0.1", ".nan"])
def test_delta_outside_zero_one_fails_at_project_load(tmp_path: Path, delta: str) -> None:
    with pytest.raises(ConfigError, match=r"options\.delta") as exc:
        load_project(write_project(tmp_path, f"delta: {delta}"))
    assert exc.value.exit_code == 2


@pytest.mark.parametrize("delta", [0, 0.2, 0.99])
def test_delta_inside_zero_one_is_accepted(tmp_path: Path, delta: float) -> None:
    assert load_project(write_project(tmp_path, f"delta: {delta}")).options.delta == delta


# ------------------------------------------------------------------ load-stage records
def test_load_stage_records_reach_the_run_log_once_with_the_runs_id(base_run: RunOutput) -> None:
    records = log_records(base_run.run_dir)
    events = [r["event"] for r in records]
    assert "catalog_todo_sources" in events  # logged by load_catalog, before the folder exists
    load_done = next(  # the load stage ends before the run starts, and its records come first
        i for i, r in enumerate(records) if r["event"] == "stage_done" and r["stage"] == "load"
    )
    assert events.index("catalog_todo_sources") < load_done < events.index("run_start")
    assert {r["run_id"] for r in records} == {base_run.manifest.run_id}  # not "setup"
    assert [r["stage"] for r in records if r["event"] == "catalog_todo_sources"] == ["load"]
    loads = [r for r in records if r["event"] == "stage_done" and r["stage"] == "load"]
    assert len(loads) == 1  # once: not also re-logged by hand
    assert loads[0]["duration_s"] == round(base_run.manifest.timings["load"], 6)
    stamps = [r["timestamp"] for r in records]
    assert stamps == sorted(stamps)  # replayed with their own time, in order


def test_a_load_stage_that_fails_leaves_no_buffer_on_the_logger(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WHSIZING_SALT")
    with pytest.raises(ConfigError, match="WHSIZING_SALT"):
        runner.run_scenarios(small_project(data, tmp_path / "runs"))
    assert not [h for h in logging.getLogger(LOGGER_NAME).handlers if isinstance(h, LogBuffer)]


# ------------------------------------------------------------------ RunOutput export
def test_run_output_is_exported_with_an_example() -> None:
    assert schemas.RunOutput is RunOutput and "RunOutput" in schemas.__all__
    example = mock_run_output()
    assert schema_examples()[RunOutput] == example
    assert RunOutput.model_validate_json(example.model_dump_json()) == example
