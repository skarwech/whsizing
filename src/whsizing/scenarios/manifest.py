"""Run folder (§2.4) and RunManifest of a run.

Manifest hash = sha256 of the manifest's identity: every field except `run_id`, `mapping_hashes`
(known only after ingest), `timings` and the `inputs/project.yaml` entry (written after the folder
is named; a rerun changes it). It is therefore the hash of the written manifest.json too: the
folder suffix can be recomputed from it. It includes `created_at` (microseconds), so two runs of
one project in the same second differ. The folder is `<out_dir>/<created_at as YYYY-MM-DDTHH-MM-SS>
_<first 6 hex of the hash>`; it is created with `mkdir`, never overwritten: on a name clash
`created_at` moves by 1 µs and the hash is taken again.

`project_hash` = sha256 of the project model without its paths (`project_hash()`): paths say where
files are, not what the run computes (the data and the copies under `inputs/` are hashed in
`inputs`), and `inputs/project.yaml` rewrites them. It is part of the hashed content, and `rerun`
compares it with the copy's: an edited `inputs/project.yaml` is a ConfigError (I75 b).

`manifest.inputs` (path → sha256): the data and mapping files the project names, by the path
the project gives (not copied into the run: client data stays where it is), and the copies the
run keeps: `inputs/basis.yaml`, `inputs/scenarios.yaml`, `inputs/catalog/<file>` and, once
written, `inputs/project.yaml`.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path

import yaml

from whsizing import __version__
from whsizing.catalog import Catalog, ParamSet, snapshot_catalog
from whsizing.errors import ConfigError
from whsizing.io.ingest import expand_files
from whsizing.schemas import DesignBasis, Project, RunManifest, ScenarioSet

SEED = 42  # no step of the pipeline is random (the salt is the project's, never per run); §2.5
SUBDIRS = ("inputs", "canonical", "dq", "profile", "design", "scenarios", "comparison", "report")
PACKAGES = (  # every §3.1 runtime dependency of pyproject.toml (a test keeps the two in step)
    "polars", "pyarrow", "pandera", "pydantic", "charset-normalizer", "rapidfuzz", "fastexcel",
    "python-dateutil", "holidays", "numpy", "scipy", "numpy-financial", "pint", "pyyaml", "typer",
    "rich", "matplotlib", "plotly", "jinja2", "weasyprint", "xlsxwriter", "structlog", "joblib",
)  # fmt: skip
PROJECT_COPY = "inputs/project.yaml"
PROJECT_PATHS = ("out_dir", "salt_file", "catalog", "basis", "scenarios")  # see `project_hash`
GIT_TIMEOUT_S = 5


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise ConfigError(f"{path}: cannot read file ({e.strerror})") from e
    return h.hexdigest()


def external_hashes(project: Project) -> dict[str, str]:
    """sha256 of every data file (globs expanded) and mapping file the project names."""
    files = [p for spec in project.inputs.values() if spec for p in expand_files(spec.files)]
    files += [spec.mapping for spec in project.inputs.values() if spec and spec.mapping]
    return {str(p): sha256_file(p) for p in files}


def project_hash(project: Project) -> str:
    """sha256 of the project model JSON without `out_dir`, `salt_file`, `catalog`, `basis`,
    `scenarios` and each dataset's files and mapping (a dataset keeps its `sheet`). The project of
    a run and the project loaded from that run's `inputs/project.yaml` hash the same."""
    body = project.model_dump(mode="json", exclude=set(PROJECT_PATHS))
    if not project.options.keep_descriptions:  # only when set, like ingest_key (old hashes hold)
        body["options"].pop("keep_descriptions", None)
    body["inputs"] = {
        ds: None if s is None else {"sheet": s.sheet} for ds, s in project.inputs.items()
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def internal_hashes(project: Project) -> dict[str, str]:
    """sha256 of the files `copy_inputs` keeps in the run, under their `inputs/...` names."""
    out = {
        "inputs/basis.yaml": sha256_file(project.basis),
        "inputs/scenarios.yaml": sha256_file(project.scenarios),
    }
    for f in sorted(_catalog_files(project.catalog)):
        out[f"inputs/catalog/{f.relative_to(project.catalog).as_posix()}"] = sha256_file(f)
    return out


def _catalog_files(root: Path) -> list[Path]:
    return [
        f
        for f in root.rglob("*")
        if f.is_file()
        and not any(p.startswith(".") or p == "__pycache__" for p in f.relative_to(root).parts)
    ]  # the files `snapshot_catalog` copies


def _git(*args: str, cwd: Path | None = None) -> str | None:
    """Output of `git <args>` in `cwd` (default: the checkout the package runs from); None without
    git, outside a checkout or in a repository with no commit."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd or Path(__file__).parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def git_sha(cwd: Path | None = None) -> str:
    """HEAD of the checkout the package runs from, or 'unknown' (see `_git`)."""
    return _git("rev-parse", "HEAD", cwd=cwd) or "unknown"


def engine_version(cwd: Path | None = None) -> str:
    """`<package version>+<git describe --always --dirty>` (C1): a working tree with changes to
    tracked files ends in `-dirty`. Just the package version when git gives nothing."""
    described = _git("describe", "--always", "--dirty", cwd=cwd)
    return f"{__version__}+{described}" if described else __version__


def package_versions() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = "not installed"
    return out


def params_snapshot(
    catalog: Catalog, basis: DesignBasis, scenarios: ScenarioSet
) -> dict[str, float]:
    """Every parameter value at typ after the basis overrides, plus each scenario's overrides as
    `<scenario id>:<param id>` (a scenario's override replaces the value for that scenario only).
    An unknown override id raises ConfigError."""
    snap = ParamSet(catalog, basis.overrides).snapshot()
    for s in scenarios.scenarios:
        ParamSet(catalog, basis.overrides, s.overrides)  # unknown id → ConfigError
        snap |= {f"{s.id}:{k}": float(v) for k, v in s.overrides.items()}
    return snap


def build_manifest(
    project: Project,
    catalog: Catalog,
    basis: DesignBasis,
    scenarios: ScenarioSet,
    created_at: datetime,
    external: Mapping[str, str] | None = None,
) -> RunManifest:
    """The manifest as known before ingest (empty `run_id`, `mapping_hashes`, `timings`).
    `external`: hashes of the data and mapping files when they cannot be read (a rerun)."""
    inputs = {**(external if external is not None else external_hashes(project))}
    inputs |= internal_hashes(project)
    return RunManifest(
        run_id="",
        created_at=created_at,
        engine_version=engine_version(),
        git_sha=git_sha(),
        catalog_version=catalog.version,
        inputs=inputs,
        basis_hash=inputs["inputs/basis.yaml"],
        scenarios_hash=inputs["inputs/scenarios.yaml"],
        mapping_hashes={},
        params_snapshot=params_snapshot(catalog, basis, scenarios),
        project_hash=project_hash(project),
        seed=SEED,
        python=platform.python_version(),
        platform=f"{sys.platform}-{platform.machine()}",
        packages=package_versions(),
    )


def manifest_hash(manifest: RunManifest) -> str:
    """sha256 (64 hex) of the manifest's identity; see the module docstring."""
    body = manifest.model_dump(mode="json", exclude={"run_id", "mapping_hashes", "timings"})
    body["inputs"] = {k: v for k, v in body["inputs"].items() if k != PROJECT_COPY}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def create_run_dir(
    out_dir: Path, manifest: RunManifest, run_dir: Path | None = None
) -> tuple[Path, RunManifest]:
    """Create the run folder with its §2.4 subfolders (+ `logs/`) and return it with the
    manifest carrying its `run_id`. An existing folder is never reused: an explicit `run_dir`
    that exists raises ConfigError; a generated name that exists gets a new hash (see above). A
    folder that cannot be created (`out_dir` is a file, no permission) is a ConfigError too."""
    if run_dir is not None:
        try:
            _mkdir(run_dir, parents=True)
        except FileExistsError:
            raise ConfigError(f"run folder {run_dir} exists: runs are immutable") from None
        return _with_subdirs(run_dir, manifest.model_copy(update={"run_id": run_dir.name}))
    try:
        _mkdir(out_dir, parents=True, exist_ok=True)
    except FileExistsError:  # exist_ok does not cover a file
        raise ConfigError(f"{out_dir}: exists and is not a folder") from None
    while True:
        stamp = manifest.created_at.strftime("%Y-%m-%dT%H-%M-%S")
        run_id = f"{stamp}_{manifest_hash(manifest)[:6]}"
        try:
            _mkdir(out_dir / run_id)
        except FileExistsError:
            manifest = manifest.model_copy(
                update={"created_at": manifest.created_at + timedelta(microseconds=1)}
            )
            continue
        return _with_subdirs(out_dir / run_id, manifest.model_copy(update={"run_id": run_id}))


def _mkdir(path: Path, *, parents: bool = False, exist_ok: bool = False) -> None:
    """`Path.mkdir`; FileExistsError passes through, any other OSError becomes a ConfigError."""
    try:
        path.mkdir(parents=parents, exist_ok=exist_ok)
    except FileExistsError:
        raise
    except OSError as e:
        raise ConfigError(f"{path}: cannot create the folder ({e.strerror})") from e


def _with_subdirs(run_dir: Path, manifest: RunManifest) -> tuple[Path, RunManifest]:
    for name in (*SUBDIRS, "logs"):
        (run_dir / name).mkdir(exist_ok=True)
    return run_dir, manifest


def copy_inputs(project: Project, run_dir: Path) -> str:
    """Keep the run's own copies under `inputs/`: basis.yaml, scenarios.yaml, the catalog
    snapshot and a project.yaml whose paths point at them (data files by absolute path, mapping
    files at `inputs/mapping/<dataset>.yaml`, which `ingest` fills). Returns the project.yaml
    sha256."""
    inputs = run_dir / "inputs"
    shutil.copyfile(project.basis, inputs / "basis.yaml")
    shutil.copyfile(project.scenarios, inputs / "scenarios.yaml")
    snapshot_catalog(project.catalog, inputs / "catalog")
    spec = {
        ds: None
        if s is None
        else {
            "files": [os.path.abspath(f) for f in s.files],
            "mapping": f"mapping/{ds}.yaml",
            "sheet": s.sheet,
        }
        for ds, s in project.inputs.items()
    }
    data = project.model_dump(mode="json")
    data |= {
        "out_dir": os.path.abspath(project.out_dir),
        "salt_file": os.path.abspath(project.salt_file) if project.salt_file else None,
        "catalog": "catalog",
        "basis": "basis.yaml",
        "scenarios": "scenarios.yaml",
        "inputs": spec,
    }
    path = inputs / "project.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return sha256_file(path)


def write_manifest(manifest: RunManifest, run_dir: Path) -> Path:
    path = run_dir / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_manifest(run_dir: Path) -> RunManifest:
    path = run_dir / "manifest.json"
    try:
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"{path}: cannot read the run manifest ({e.strerror})") from e
    except ValueError as e:
        raise ConfigError(f"{path}: invalid run manifest: {e}") from e
