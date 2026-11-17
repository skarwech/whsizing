"""Data-side commands: synth, ingest, profile, basis init, validate-catalog."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

import typer
import yaml

from whsizing.catalog.loader import check_catalog
from whsizing.cli._core import (
    app,
    basis_app,
    handle_errors,
    open_run,
    require_unsized,
)
from whsizing.cli._staged import PROFILE_CFG_COPY
from whsizing.config import load_yaml_model
from whsizing.design import basis_template, load_basis
from whsizing.errors import ConfigError, WhsizingError
from whsizing.io import ingest as ingest_files
from whsizing.io import load_salt
from whsizing.io.canonical import DEFAULT_UNITS_PER_PALLET
from whsizing.io.ingest import expand_files
from whsizing.logging import configure_logging, get_logger, stage_timer
from whsizing.profile import build_tables, profile_from_tables, write_profile
from whsizing.scenarios.manifest import SUBDIRS, sha256_file
from whsizing.schemas import DatasetKind, InputSpec, ProfileCfg
from whsizing.synth import synthesize


@app.command("synth")
@handle_errors
def synth(
    profile: Annotated[Path, typer.Argument(help="Synthetic profile YAML (data/synth/profiles).")],
    out: Annotated[Path | None, typer.Option(help="Output folder (data/generated/<name>).")] = None,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 42,
    defects: Annotated[bool, typer.Option(help="Inject the profile's defects.")] = False,
) -> None:
    """Generate synthetic data (Parquet and CSV EN/FR) from a profile YAML (F1)."""
    out = out or Path("data/generated") / profile.stem
    for path in synthesize(profile, out, seed=seed, defects=defects):
        typer.echo(str(path))


@app.command("ingest")
@handle_errors
def ingest_cmd(
    files: Annotated[list[Path], typer.Argument(help="Input file(s) of one dataset.")],
    dataset: Annotated[DatasetKind, typer.Option(help="Which dataset these files hold.")],
    mapping: Annotated[Path | None, typer.Option(help="Mapping YAML to use.")] = None,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Never ask: an unclear mapping is exit 2.")
    ] = False,
    salt_file: Annotated[
        Path | None, typer.Option(help="Anonymisation salt file ($WHSIZING_SALT).")
    ] = None,
    keep_descriptions: Annotated[
        bool, typer.Option("--keep-descriptions", help="Keep description and customer columns.")
    ] = False,
    out_dir: Annotated[Path, typer.Option(help="Folder that holds the runs.")] = Path("runs"),
    run: Annotated[
        Path | None, typer.Option(help="Add this dataset to an existing run folder.")
    ] = None,
) -> None:
    """Read, map, anonymise and validate files into canonical/ and dq/ of a run folder (F2).

    Prints the run folder. Ingest sku_master first: the other datasets are checked against it.
    """
    salt = load_salt(salt_file)  # ConfigError (exit 2) before anything is created
    spec = InputSpec(files=files, mapping=mapping)
    now = datetime.now(UTC)
    target = _existing_run(run) if run else _new_run(out_dir, dataset, spec.files, now)
    configure_logging(target.name, target / "logs" / "run.log")
    get_logger().info("ingest_start", run_dir=str(target), dataset=dataset)
    confirm = None if non_interactive else (lambda code, question: typer.confirm(question))
    _move_mappings(target / "inputs" / "mapping", target / "mapping")  # F2 looks in mapping/
    try:
        with stage_timer("ingest"):  # to logs/run.log: `size` puts it in the manifest timings
            ingest_files(
                {dataset: spec},
                target,
                salt,
                confirm=confirm,
                keep_descriptions=keep_descriptions,
                now=now,
                default_units_per_pallet=DEFAULT_UNITS_PER_PALLET,
            )
    except WhsizingError:  # exit 2 or 3 (exit 1 keeps the folder: its run.log has the traceback)
        if run is None:
            _drop_if_unused(target)
        raise
    finally:  # also after a failed ingest: mapping/ belongs under inputs/ (§2.4)
        _file_mapping(target)
    typer.echo(str(target))


def _existing_run(run: Path) -> Path:
    """`--run`: a folder `ingest` (or run-all) made, that no stage has sealed yet. Runs are
    immutable (§2.4): once manifest.json or design/ exist, nothing is ingested into them."""
    if not all((run / name).is_dir() for name in (*SUBDIRS, "logs")):
        raise ConfigError(f"{run}: not a run folder made by `whsizing ingest`")
    if (run / "manifest.json").exists():
        raise ConfigError(f"{run}: already sized and runs are immutable; ingest into a new run")
    require_unsized(run)
    return run.resolve()


def _drop_if_unused(run: Path) -> None:
    """Remove the run folder a failed ingest made when it wrote nothing but logs/run.log."""
    log = run / "logs" / "run.log"
    if all(p == log for p in run.rglob("*") if p.is_file()):
        shutil.rmtree(run, ignore_errors=True)


def _new_run(out_dir: Path, dataset: str, spec_files: list[Path], now: datetime) -> Path:
    """`<out_dir>/<YYYY-MM-DDTHH-MM-SS>_<6 hex of the input hashes>` with the §2.4 subfolders."""
    digest = hashlib.sha256(dataset.encode())
    for h in sorted(sha256_file(p) for p in expand_files(spec_files)):
        digest.update(h.encode())
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ConfigError(f"{out_dir}: cannot create the folder ({e.strerror})") from e
    while True:
        path = out_dir / f"{now:%Y-%m-%dT%H-%M-%S}_{digest.hexdigest()[:6]}"
        try:
            path.mkdir()
        except FileExistsError:  # same inputs in the same second: never overwrite
            now += timedelta(seconds=1)
            continue
        for name in (*SUBDIRS, "logs"):
            (path / name).mkdir()
        return path.resolve()


def _move_mappings(src: Path, dst: Path) -> None:
    """Move the *.yaml of folder `src` into `dst` (made when needed); `src` goes when empty."""
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.yaml"):
        f.replace(dst / f.name)
    src.rmdir()


def _file_mapping(run: Path) -> None:
    """Back under inputs/mapping/ the mapping/*.yaml `ingest` wrote (like the F8 runner)."""
    _move_mappings(run / "mapping", run / "inputs" / "mapping")


@app.command("profile")
@handle_errors
def profile_cmd(
    run: Annotated[Path, typer.Argument(help="Run folder made by `whsizing ingest`.")],
    cfg: Annotated[Path | None, typer.Option(help="ProfileCfg YAML (ABC thresholds, ...).")] = None,
    basis: Annotated[
        Path | None, typer.Option(help="Design basis YAML (time zone, flows); defaults without.")
    ] = None,
) -> None:
    """Demand profile of a run: profile/ (F3). `size` redoes it with the design basis."""
    run = open_run(run)
    require_unsized(run)
    profile_cfg = load_yaml_model(cfg, ProfileCfg) if cfg else ProfileCfg()
    with stage_timer("profile"):
        tables = build_tables(run / "canonical", load_basis(basis) if basis else None, profile_cfg)
        result = profile_from_tables(tables, profile_cfg)
        write_profile(result, run, tables)
    if cfg:  # `size` uses the same configuration
        text = yaml.safe_dump(profile_cfg.model_dump(mode="json"), sort_keys=False)
        (run / PROFILE_CFG_COPY).write_text(text, encoding="utf-8")
    typer.echo(
        f"profile: {result.period_start} to {result.period_end}, "
        f"{result.operating_days} operating days, dataset {result.dataset_hash}"
    )
    typer.echo(str(run / "profile"))


@basis_app.command("init")
@handle_errors
def basis_init(
    lang: Annotated[Literal["fr", "en"], typer.Option(help="Comment language.")] = "fr",
    out: Annotated[Path, typer.Option(help="File to write.")] = Path("basis.yaml"),
) -> None:
    """Write a commented basis.yaml template (F4): [P] defaults, [CLIENT] values to fill."""
    if out.exists():
        raise ConfigError(f"{out} exists: remove it or choose another --out")
    basis_template(out, lang)
    typer.echo(str(out))


@app.command("validate-catalog")
@handle_errors
def validate_catalog(
    folder: Annotated[Path, typer.Argument(help="Catalog folder.")],
) -> None:
    """Validate a catalog folder (F5): every file error is listed (exit 2), then the parameters
    sourced TODO."""
    errors, catalog = check_catalog(folder)
    if catalog is None:
        raise ConfigError(f"{folder}: {len(errors)} error(s)\n" + "\n".join(errors))
    todo = sorted(pid for pid, p in catalog.params.items() if p.source == "TODO")
    typer.echo(f"{folder}: valid, catalog {catalog.version}")
    typer.echo(f"{len(catalog.params)} parameters, {len(catalog.families)} families")
    for w in catalog.warnings:
        typer.echo(f"warning: {w}")
    typer.echo(f"{len(todo)} parameter(s) with source TODO")
    for pid in todo:
        typer.echo(f"  TODO {pid}")
