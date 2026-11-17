"""F8a RunManifest and run folder: hashes follow the input bytes, immutability, distinct folders
in one second, T6.9-style rerun from `inputs/` (originals deleted), canonical reuse, salts."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from tests.fixtures import mock_manifest
from tests.unit.test_f8_runner import (
    DATASETS,
    NOW,
    ROOT,
    log_records,
    salt_env,  # noqa: F401  (autouse fixture: $WHSIZING_SALT for every run of this module)
    small_data,
    small_project,
)

from whsizing import __version__
from whsizing.catalog import load_catalog
from whsizing.design import load_basis
from whsizing.errors import ConfigError
from whsizing.scenarios import find_canonical, ingest_key, load_scenarios, rerun, runner
from whsizing.scenarios import manifest as mf
from whsizing.schemas import Project
from whsizing.schemas.params import DatasetKind
from whsizing.schemas.run import RunOutput

FILES = ("result.json", "finance.json", "trace.jsonl")


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def base_run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return runner.run_scenarios(small_project(data, tmp_path_factory.mktemp("runs")), now=NOW)


def draft(project: Project) -> mf.RunManifest:
    return mf.build_manifest(
        project,
        load_catalog(project.catalog),
        load_basis(project.basis),
        load_scenarios(project.scenarios),
        NOW,
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ hashes
@pytest.fixture
def copied(data: Path, tmp_path: Path) -> Project:
    """A project whose data, basis, scenarios and catalog are copies we may edit."""
    src = tmp_path / "src"
    shutil.copytree(data, src / "data")
    shutil.copytree(ROOT / "catalog", src / "catalog")
    shutil.copy(ROOT / "basis" / "example_basis.yaml", src / "basis.yaml")
    shutil.copy(ROOT / "scenarios" / "example_scenarios.yaml", src / "scenarios.yaml")
    return small_project(
        src / "data", tmp_path / "runs",
        catalog=src / "catalog", basis=src / "basis.yaml", scenarios=src / "scenarios.yaml",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("target", "field"),
    [
        ("data/order_lines.csv", "inputs"),
        ("basis.yaml", "basis_hash"),
        ("scenarios.yaml", "scenarios_hash"),
        ("catalog/finance_defaults.yaml", "catalog_version"),
    ],
)
def test_hashes_change_when_one_input_byte_changes(
    copied: Project, target: str, field: str
) -> None:
    before = draft(copied)
    assert mf.manifest_hash(draft(copied)) == mf.manifest_hash(before)  # deterministic
    path = copied.basis.parent / target
    path.write_bytes(path.read_bytes() + b"\n# one more byte\n")
    after = draft(copied)
    assert mf.manifest_hash(after) != mf.manifest_hash(before)
    assert getattr(after, field) != getattr(before, field)
    changed = {k for k in after.inputs if after.inputs[k] != before.inputs.get(k)}
    assert changed and all(target.split("/")[-1] in k for k in changed), changed


def test_manifest_hash_ignores_run_id_mapping_hashes_timings_and_project_copy_not_created_at() -> (
    None
):
    m = mock_manifest()
    same = m.model_copy(
        update={
            "run_id": "other",
            "mapping_hashes": {"x": "y"},
            "timings": {"load": 9.0},
            "inputs": {**m.inputs, mf.PROJECT_COPY: "written after the folder is named"},
        }
    )
    assert mf.manifest_hash(same) == mf.manifest_hash(m)
    other_input = m.model_copy(update={"inputs": {**m.inputs, "data/new.csv": "0" * 64}})
    assert mf.manifest_hash(other_input) != mf.manifest_hash(m)
    later = m.model_copy(update={"created_at": m.created_at + timedelta(microseconds=1)})
    assert mf.manifest_hash(later) != mf.manifest_hash(m)


def test_params_snapshot_holds_basis_and_scenario_overrides(base_run: RunOutput) -> None:
    snap = base_run.manifest.params_snapshot
    assert snap["manual_p2p.pick_rate_shelving_lines_h"] == 62  # basis override (client)
    assert snap["S1:amr_gtp.station_rate_lines_h"] == 230  # scenario override
    catalog = load_catalog(ROOT / "catalog")
    assert (
        snap["amr_gtp.station_rate_lines_h"] == catalog.params["amr_gtp.station_rate_lines_h"].typ
    )
    assert all(isinstance(v, float) for v in snap.values())


def test_unknown_scenario_override_id_is_a_config_error(copied: Project) -> None:
    text = copied.scenarios.read_text(encoding="utf-8")
    copied.scenarios.write_text(text.replace("amr_gtp.station_rate_lines_h", "amr_gtp.nope"))
    with pytest.raises(ConfigError, match=r"unknown parameter id 'amr_gtp\.nope'"):
        draft(copied)


def test_manifest_records_inputs_environment_and_mapping_hashes(base_run: RunOutput) -> None:
    m, run = base_run.manifest, base_run.run_dir
    assert mf.read_manifest(run) == m  # manifest.json is the RunManifest, validated on read
    assert m.engine_version.startswith(__version__) and m.seed == mf.SEED
    assert m.python == platform.python_version()
    assert re.fullmatch(r"unknown|[0-9a-f]{40}", m.git_sha)
    assert m.packages["polars"] and m.packages["pydantic"]
    assert m.catalog_version == load_catalog(ROOT / "catalog").version
    assert m.basis_hash == sha(ROOT / "basis" / "example_basis.yaml")
    assert m.scenarios_hash == sha(ROOT / "scenarios" / "example_scenarios.yaml")
    data_keys = [k for k in m.inputs if not k.startswith("inputs/")]
    assert sorted(Path(k).name for k in data_keys) == sorted(f"{ds}.csv" for ds in DATASETS)
    assert all(m.inputs[k] == sha(Path(k)) for k in data_keys)
    for name in ("inputs/basis.yaml", "inputs/scenarios.yaml", "inputs/project.yaml"):
        assert m.inputs[name] == sha(run / name)
    assert m.inputs["inputs/catalog/area_factors.yaml"] == sha(
        run / "inputs/catalog/area_factors.yaml"
    )
    assert set(m.mapping_hashes) == set(DATASETS)
    for ds, digest in m.mapping_hashes.items():
        assert digest == sha(run / "inputs" / "mapping" / f"{ds}.yaml")


def test_manifest_packages_are_every_runtime_dependency_of_pyproject(base_run: RunOutput) -> None:
    """§3.1: record them all in RunManifest.packages (holidays and dateutil change F2/F3 output)."""
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    names = {re.match(r"[A-Za-z0-9_.-]+", d).group().lower() for d in deps}  # type: ignore[union-attr]
    assert len(names) == 23 and set(mf.PACKAGES) == names
    packages = base_run.manifest.packages
    assert set(packages) == names
    assert [n for n, v in packages.items() if v == "not installed"] == []
    assert mf.read_manifest(base_run.run_dir).packages == packages


def test_git_sha_is_unknown_when_git_is_missing_or_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_git(*a: object, **k: object) -> None:
        raise FileNotFoundError("git")

    def no_commit(*a: object, **k: object) -> None:
        raise subprocess.CalledProcessError(128, "git")

    for fail in (no_git, no_commit):
        monkeypatch.setattr(mf.subprocess, "run", fail)
        assert mf.git_sha() == "unknown"


def git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args]
    return subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_engine_version_is_git_describe_and_flags_a_dirty_working_tree(tmp_path: Path) -> None:
    """C1: `git describe --always --dirty`; the package version stays in front."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "engine.py").write_text("x = 1\n")
    git(repo, "add", "engine.py")
    git(repo, "commit", "-q", "-m", "first")
    head = git(repo, "rev-parse", "HEAD")
    assert mf.git_sha(repo) == head
    described = git(repo, "describe", "--always")
    assert mf.engine_version(repo) == f"{__version__}+{described}"
    (repo / "notes.txt").write_text("untracked files do not make a tree dirty (git describe)\n")
    assert mf.engine_version(repo) == f"{__version__}+{described}"
    (repo / "engine.py").write_text("x = 2\n")  # a tracked file changed
    assert mf.engine_version(repo) == f"{__version__}+{described}-dirty"
    assert mf.git_sha(repo) == head  # the sha itself stays the commit


def test_engine_version_is_the_package_version_without_git_or_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "no_commit"
    empty.mkdir()
    git(empty, "init", "-q")
    assert mf.engine_version(empty) == __version__ and mf.git_sha(empty) == "unknown"

    def no_git(*a: object, **k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(mf.subprocess, "run", no_git)
    assert mf.engine_version() == __version__


# ------------------------------------------------------------------ immutable folders
def test_create_run_dir_never_reuses_a_folder_even_for_the_same_second(tmp_path: Path) -> None:
    m = mock_manifest().model_copy(update={"run_id": ""})
    first, m1 = mf.create_run_dir(tmp_path, m)
    (first / "result.json").write_text("first")
    second, m2 = mf.create_run_dir(tmp_path, m)  # same created_at, same inputs
    assert first != second and second.is_dir()
    assert first.name[:19] == second.name[:19] == "2026-11-18T14-02-11"  # the same second
    assert first.name != second.name and m1.run_id != m2.run_id
    assert m2.created_at == m.created_at + timedelta(microseconds=1)
    assert (first / "result.json").read_text() == "first"
    assert {p.name for p in first.iterdir()} >= {*mf.SUBDIRS, "logs", "result.json"}


def test_explicit_run_dir_that_exists_is_refused_and_left_untouched(
    data: Path, tmp_path: Path
) -> None:
    run = tmp_path / "my_run"
    run.mkdir()
    (run / "keep.txt").write_text("client work")
    with pytest.raises(ConfigError, match="runs are immutable"):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), run_dir=run)
    assert [p.name for p in run.iterdir()] == ["keep.txt"]


def test_a_folder_that_cannot_be_created_is_a_config_error_not_an_oserror(
    data: Path, tmp_path: Path
) -> None:
    afile = tmp_path / "afile"
    afile.write_text("not a folder")
    for out, run_dir in ((afile, None), (afile / "runs", None), (tmp_path / "runs", afile / "r")):
        with pytest.raises(ConfigError, match=r"not a folder|cannot create") as exc:
            runner.run_scenarios(small_project(data, out), run_dir=run_dir)
        assert exc.value.exit_code == 2
    assert afile.read_text() == "not a folder"


def test_run_dir_argument_names_the_new_folder(data: Path, tmp_path: Path) -> None:
    out = runner.run_scenarios(small_project(data, tmp_path / "runs"), run_dir=tmp_path / "mine")
    assert out.run_dir == tmp_path / "mine" and out.manifest.run_id == "mine"
    assert not (tmp_path / "runs").exists()  # out_dir untouched: the folder was given


def test_two_runs_in_the_same_second_get_distinct_folders(
    data: Path, base_run: RunOutput, tmp_path: Path
) -> None:
    project = small_project(data, base_run.run_dir.parent)  # the folder of the first run
    before = (base_run.run_dir / "manifest.json").read_bytes()
    second = runner.run_scenarios(project, now=NOW, reuse_canonical=base_run.run_dir)
    assert second.run_dir != base_run.run_dir
    assert second.run_dir.name[:19] == base_run.run_dir.name[:19]  # same second, other hash
    assert second.run_dir.name[-6:] != base_run.run_dir.name[-6:]
    assert (base_run.run_dir / "manifest.json").read_bytes() == before  # the first one is intact


# ------------------------------------------------------------------ rerun
def test_rerun_rebuilds_from_the_run_copies_when_every_original_is_gone_and_needs_no_salt(
    copied: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = runner.run_scenarios(copied, now=NOW)
    shutil.rmtree(tmp_path / "src")  # basis, scenarios, catalog, mapping and the data files
    monkeypatch.delenv("WHSIZING_SALT")  # canonical/ is reused: nothing is hashed again
    elsewhere = tmp_path / "reruns"
    again = rerun(first.run_dir, now=NOW + timedelta(hours=1), out_dir=elsewhere)
    assert again.run_dir.parent == elsewhere.resolve() and again.run_dir != first.run_dir
    assert again.manifest.created_at == NOW + timedelta(hours=1)
    for sid in first.results:
        for f in FILES:
            one, two = (r.run_dir / "scenarios" / sid / f for r in (first, again))
            assert one.read_bytes() == two.read_bytes(), (sid, f)
    assert again.comparison == first.comparison
    a, b = first.manifest, again.manifest
    # every input hash is carried over; only project.yaml differs (it records the new out_dir)
    assert {k: v for k, v in b.inputs.items() if k != mf.PROJECT_COPY} == {
        k: v for k, v in a.inputs.items() if k != mf.PROJECT_COPY
    }
    assert (b.basis_hash, b.scenarios_hash) == (a.basis_hash, a.scenarios_hash)
    assert b.mapping_hashes == a.mapping_hashes and b.params_snapshot == a.params_snapshot
    assert b.catalog_version == a.catalog_version
    for name in ("canonical/order_lines.parquet", "dq/ingest_manifest.json"):
        assert (first.run_dir / name).read_bytes() == (again.run_dir / name).read_bytes(), name
    assert not (first.run_dir / ".salt").exists() and not (again.run_dir / ".salt").exists()
    assert rerun(first.run_dir).run_dir.parent == first.run_dir.parent  # default: next to it


def test_rerun_refuses_an_input_copy_that_no_longer_matches_the_manifest(
    base_run: RunOutput, tmp_path: Path
) -> None:
    for name in ("inputs/basis.yaml", "inputs/catalog/finance_defaults.yaml"):
        copy = tmp_path / name.replace("/", "_") / "run"
        shutil.copytree(base_run.run_dir, copy)
        with (copy / name).open("a", encoding="utf-8") as f:
            f.write("\n# edited after the run\n")
        with pytest.raises(ConfigError, match=rf"{name} differs from the run's manifest"):
            rerun(copy, out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_rerun_without_a_manifest_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read the run manifest"):
        rerun(tmp_path)


def _copy_run(run: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "copy" / "run"
    shutil.copytree(run, copy)
    return copy


def _truncate(parquet: Path) -> None:
    pl.read_parquet(parquet).head(5).write_parquet(parquet)


def _drop_dq(run: Path) -> None:
    shutil.rmtree(run / "dq")


def _add_file_to_mapping(run: Path) -> None:
    (run / "inputs" / "mapping" / "extra.yaml").write_text("dataset: extra\n")


CHANGES = {
    "a truncated canonical table": lambda run: _truncate(run / "canonical" / "sku_master.parquet"),
    "a missing dq/ folder": _drop_dq,
    "a changed mapping": lambda run: (run / "inputs/mapping/order_lines.yaml").write_text("x: 1\n"),
    "an extra mapping file": _add_file_to_mapping,
}


@pytest.mark.parametrize("what", CHANGES)
def test_rerun_refuses_a_run_whose_canonical_changed_and_makes_no_folder(
    base_run: RunOutput, tmp_path: Path, what: str
) -> None:
    """The byte-identical promise needs the canonical tables the run was made from."""
    copy = _copy_run(base_run.run_dir, tmp_path)
    CHANGES[what](copy)
    with pytest.raises(ConfigError, match=r"missing or changed since the run") as exc:
        rerun(copy, out_dir=tmp_path / "out")
    assert exc.value.exit_code == 2
    assert not (tmp_path / "out").exists()  # refused in the load stage, no failed folder left


def test_a_finished_run_passes_the_integrity_check_of_every_later_stage(
    base_run: RunOutput,
) -> None:
    """canonical/, dq/ and inputs/mapping/ are not written by the stages after ingest."""
    assert runner._intact(base_run.run_dir)
    recorded = json.loads((base_run.run_dir / "canonical/.sha256.json").read_text())
    assert recorded == runner._reused_files(base_run.run_dir)
    assert {"canonical/sku_master.parquet", "dq/ingest_manifest.json"} <= set(recorded)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in recorded.values())
    assert not [k for k in recorded if k.endswith((runner.KEY_FILE, runner.HASHES_FILE))]


def test_rerun_of_a_run_that_has_no_ingest_key_makes_no_folder(
    base_run: RunOutput, tmp_path: Path
) -> None:
    copy = _copy_run(base_run.run_dir, tmp_path)  # e.g. a run whose ingest failed
    (copy / "canonical" / runner.KEY_FILE).unlink()
    with pytest.raises(ConfigError, match=r"has no canonical/\.ingest_key") as exc:
        rerun(copy, out_dir=tmp_path / "out")
    assert exc.value.exit_code == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("what", ["a truncated canonical table", "a missing dq/ folder"])
def test_reuse_canonical_of_a_changed_run_falls_back_to_a_fresh_ingest(
    data: Path, base_run: RunOutput, tmp_path: Path, what: str
) -> None:
    copy = _copy_run(base_run.run_dir, tmp_path)
    CHANGES[what](copy)
    out = runner.run_scenarios(
        small_project(data, tmp_path / "runs"), now=NOW, reuse_canonical=copy
    )
    (record,) = [r for r in log_records(out.run_dir) if r["event"] == "canonical_not_reused"]
    assert record["source"] == str(copy) and "missing or changed" in record["reason"]
    for sid in out.results:  # ingested again from the data: the result is the original's
        res = "scenarios", sid, "result.json"
        one, two = (r.run_dir.joinpath(*res).read_bytes() for r in (out, base_run))
        assert one == two
    assert runner._intact(out.run_dir)


def test_naive_now_is_a_config_error_before_any_folder_is_created(
    data: Path, base_run: RunOutput, tmp_path: Path
) -> None:
    naive = datetime(2026, 1, 2, 3, 4, 5)
    with pytest.raises(ConfigError, match="timezone") as exc:
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=naive)
    assert exc.value.exit_code == 2
    with pytest.raises(ConfigError, match="timezone"):
        rerun(base_run.run_dir, now=naive, out_dir=tmp_path / "reruns")
    assert not (tmp_path / "runs").exists() and not (tmp_path / "reruns").exists()


# ------------------------------------------------------------------ canonical reuse and salt
def test_reuse_canonical_skips_ingest_when_inputs_and_salt_match(
    data: Path, base_run: RunOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_ingest(*a: object, **k: object) -> None:
        raise AssertionError("ingest must not run: the canonical tables are reused")

    monkeypatch.setattr(runner, "ingest", no_ingest)
    out = runner.run_scenarios(
        small_project(data, tmp_path / "runs"), reuse_canonical=base_run.run_dir
    )
    for name in ("canonical/order_lines.parquet", "canonical/sku_master.parquet"):
        assert (out.run_dir / name).read_bytes() == (base_run.run_dir / name).read_bytes(), name
    assert out.manifest.mapping_hashes == base_run.manifest.mapping_hashes
    assert (out.run_dir / "inputs/mapping/order_lines.yaml").is_file()
    for sid in out.results:
        res = "scenarios", sid, "result.json"
        assert (out.run_dir.joinpath(*res)).read_bytes() == base_run.run_dir.joinpath(
            *res
        ).read_bytes()


def test_salt_file_changes_the_hashes_and_prevents_reuse_with_a_logged_reason(
    data: Path, base_run: RunOutput, tmp_path: Path
) -> None:
    salt = tmp_path / "salt_client"  # outside any git repository
    salt.write_text("client-secret-salt\n")
    project = small_project(data, tmp_path / "runs", salt_file=salt)
    out = runner.run_scenarios(project, reuse_canonical=base_run.run_dir)  # key differs: re-ingest
    assert not (out.run_dir / ".salt").exists()
    one, two = (
        pl.read_parquet(r.run_dir / "canonical" / "order_lines.parquet")["sku"]
        for r in (base_run, out)
    )
    assert one.n_unique() == two.n_unique() and not set(one) & set(two)  # other salt, other hashes
    (record,) = [r for r in log_records(out.run_dir) if r["event"] == "canonical_not_reused"]
    assert record["source"] == str(base_run.run_dir) and "salt" in record["reason"]


def with_spec(project: Project, name: DatasetKind, **update: object) -> Project:
    """`project` with one dataset's InputSpec changed."""
    spec = project.inputs[name]
    assert spec is not None
    inputs = {**project.inputs, name: spec.model_copy(update=update)}
    return project.model_copy(update={"inputs": inputs})


def test_ingest_key_follows_every_input_of_canonical(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reuse key: file hashes, which file is which dataset, sheet, mapping, salt, units per
    pallet and engine version. A sheet the old key ignored would reuse tables of another sheet."""
    project = small_project(data, tmp_path)
    ext = mf.external_hashes(project)
    key = ingest_key(project, ext, b"salt", 1)
    assert key == ingest_key(project, dict(reversed(ext.items())), b"salt", 1)  # order: no effect
    ins = project.inputs
    swapped = {**ins, "inventory": ins["receipts"], "receipts": ins["inventory"]}
    changed = {
        "sheet": with_spec(project, "sku_master", sheet="half"),
        "mapping": with_spec(project, "inventory", mapping=data / "m.yaml"),
        "assignment": project.model_copy(update={"inputs": swapped}),
    }
    for what, other in changed.items():
        assert ingest_key(other, ext, b"salt", 1) != key, what
    assert ingest_key(project, {**ext, "x": "y"}, b"salt", 1) != key  # a data file changed
    assert ingest_key(project, ext, b"other", 1) != key
    assert ingest_key(project, ext, b"salt", 2) != key
    monkeypatch.setattr(runner, "git_sha", lambda cwd=None: "f" * 40)
    assert ingest_key(project, ext, b"salt", 1) != key  # another version of the ingest code


class Reingested(Exception):
    """Raised by the fake ingest: the runner did not reuse canonical/."""


def test_a_changed_sheet_is_not_reused(
    data: Path, base_run: RunOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(*args: object, **kwargs: object) -> None:
        raise Reingested

    monkeypatch.setattr(runner, "ingest", fake)
    project = small_project(data, tmp_path / "runs")
    other = with_spec(project, "sku_master", sheet="half")
    with pytest.raises(Reingested):
        runner.run_scenarios(other, reuse_canonical=base_run.run_dir)


def test_find_canonical_returns_the_newest_run_with_the_same_key(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = small_project(data, tmp_path / "runs")
    assert find_canonical(project) is None  # no run folder yet
    first = runner.run_scenarios(project, now=NOW)
    assert find_canonical(project) == first.run_dir
    second = runner.run_scenarios(
        project, now=NOW + timedelta(hours=1), reuse_canonical=find_canonical(project)
    )
    assert find_canonical(project) == second.run_dir  # newest first
    assert find_canonical(with_spec(project, "sku_master", sheet="half")) is None
    monkeypatch.setenv("WHSIZING_SALT", "another salt")
    assert find_canonical(project) is None  # other salt, other hashed ids
    monkeypatch.delenv("WHSIZING_SALT")
    with pytest.raises(ConfigError, match="WHSIZING_SALT"):
        find_canonical(project)


def test_run_scenarios_reuses_what_find_canonical_found(
    data: Path, base_run: RunOutput, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_ingest(*a: object, **k: object) -> None:
        raise AssertionError("ingest must not run: T10.2 reuses canonical/")

    monkeypatch.setattr(runner, "ingest", no_ingest)
    project = small_project(data, base_run.run_dir.parent)
    out = runner.run_scenarios(project, reuse_canonical=find_canonical(project))
    assert [r["event"] for r in log_records(out.run_dir) if r["event"] == "canonical_reused"]
