"""F8a runner: project → ingest → profile → design day → every scenario (size + finance) →
comparison, inside one immutable run folder (§2.4) with its RunManifest. See `whsizing.scenarios`
for the public API and the hook F8b implements."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import traceback
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import polars as pl
import structlog

from whsizing.catalog import Catalog, ParamSet, load_catalog
from whsizing.config import load_project
from whsizing.design import load_basis, select_design_day, write_design
from whsizing.engine import size_scenario, sku_frame, write_scenario
from whsizing.errors import ConfigError, SizingInfeasibleError
from whsizing.finance import compute_finance, write_finance
from whsizing.io import ingest, load_salt
from whsizing.io.canonical import MANIFEST as INGEST_MANIFEST
from whsizing.io.readers import read_parquet_file
from whsizing.logging import configure_logging, get_logger, stage_timer, timings
from whsizing.profile import ProfileTables, build_tables, profile_from_tables, write_profile
from whsizing.profile.build import DAILY_SERIES_PATH
from whsizing.scenarios.compare import compare, not_computed_result
from whsizing.scenarios.load import CLIENT_CURRENT, load_scenarios
from whsizing.scenarios.logbuffer import LogBuffer
from whsizing.scenarios.manifest import (
    PROJECT_COPY,
    build_manifest,
    copy_inputs,
    create_run_dir,
    engine_version,
    external_hashes,
    git_sha,
    read_manifest,
    sha256_file,
    write_manifest,
)
from whsizing.schemas import (
    DemandProfile,
    DesignBasis,
    DesignDay,
    FinancialResult,
    IngestManifest,
    Project,
    RunManifest,
    ScenarioDef,
    ScenarioResult,
    ScenarioSet,
    Sensitivity,
)
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.schemas.trace import Tracer

FAILED_FILE = Path("logs") / "FAILED"  # the Streamlit run list (app/state.py) skips such a run
KEY_FILE = ".ingest_key"  # canonical/<KEY_FILE>: what the canonical tables were built from
HASHES_FILE = ".sha256.json"  # canonical/<HASHES_FILE>: sha256 of every file a reuse copies
UPP_ID = "storage.default_units_per_pallet"
SENSITIVITY_MODULE = "whsizing.scenarios.sensitivity"
REQUIRED_INPUTS = ("sku_master", "inventory")  # I80 (a); order_lines: ingest refuses without it


@dataclass(frozen=True, eq=False)
class RunContext:
    """Everything the scenario stage reads; handed to `run_sensitivity` (F8b)."""

    project: Project
    basis: DesignBasis
    scenarios: ScenarioSet
    catalog: Catalog
    tables: ProfileTables
    profile: DemandProfile
    sku: pl.DataFrame  # I58 frame
    design_day: DesignDay
    run_dir: Path


class Evaluated(NamedTuple):
    """One computed scenario: its result, finance and the Tracer holding every F6 and F7 node
    (finance nodes included: use a new Tracer per variant, I73)."""

    result: ScenarioResult
    finance: FinancialResult
    tracer: Tracer


def evaluate_scenario(
    ctx: RunContext,
    scenario: ScenarioDef,
    baseline: Evaluated | None = None,
    *,
    client_baseline: bool = False,
    basis: DesignBasis | None = None,
    design_day: DesignDay | None = None,
) -> Evaluated:
    """`size_scenario` (own Tracer) then `compute_finance` for one scenario; writes nothing.
    `baseline`: the baseline scenario's Evaluated (I42); None with `client_baseline` = the
    client's current operation from `basis.baseline`, None without = no baseline. `basis` /
    `design_day` replace the context's (sensitivity variants). May raise SizingInfeasibleError."""
    basis = basis or ctx.basis
    design_day = design_day or ctx.design_day
    tracer = Tracer(scenario.id)
    result = size_scenario(
        ctx.profile, basis, design_day, scenario, ctx.catalog, ctx.sku, ctx.tables.daily, tracer,
        lines=ctx.tables.lines,
    )  # fmt: skip
    fin = compute_finance(
        result,
        basis,
        ctx.catalog,
        baseline.result if baseline else None,
        daily=ctx.tables.daily,
        tracer=tracer,
        baseline_tracer=baseline.tracer if baseline else None,
        client_baseline=client_baseline,
    )
    return Evaluated(result, fin, tracer)


def run_scenarios(
    project: Project,
    *,
    now: datetime | None = None,
    strict: bool | None = None,
    run_dir: Path | None = None,
    reuse_canonical: Path | None = None,
) -> RunOutput:
    """The F8 runner (see the module docstring and `whsizing.scenarios`). `now`: created_at and
    folder timestamp (default: current UTC time). `strict`: default `project.options.strict`.
    `run_dir`: the folder to create instead of `<out_dir>/<timestamp>_<hash>` (ConfigError if it
    exists). `reuse_canonical`: an earlier run folder (see `find_canonical`) whose canonical tables
    are copied instead of ingesting, when its ingest key is the same (`ingest_key`); otherwise
    the data is ingested again and a `canonical_not_reused` record says why. The anonymisation
    salt is the project's `salt_file`, else $WHSIZING_SALT (ConfigError when neither is set, before
    any folder is created). Strict mode raises SizingInfeasibleError (exit 4) before any folder is
    made when the project has no `sku_master` or no `inventory` input, and once everything is
    written when no scenario fits, one is not computed or an automated scenario carries
    `F_ELIG_ASSUMED` (I80). `options.keep_descriptions` keeps the description and customer columns
    through the anonymisation (I78 e). A run that fails after its folder was
    created logs `run_failed` (with the traceback) to logs/run.log; manifest.json is written when
    the folder is created and after every stage. `now` must carry a timezone (ConfigError)."""
    return _run(project, now, strict, run_dir, reuse_canonical, None)


def rerun(run_dir: Path, *, now: datetime | None = None, out_dir: Path | None = None) -> RunOutput:
    """A new run folder (in `out_dir`, default the original's parent) built from the manifest and
    the copies in `<run_dir>/inputs/` (basis, scenarios, catalog, mapping): the original YAML paths
    are never read, nor the data files: the canonical tables of `run_dir` are reused, so no salt
    is needed. result.json and finance.json come out byte-identical (T6.9). ConfigError, before a
    folder is made, when `run_dir` has no canonical/.ingest_key, its canonical/, dq/ or
    inputs/mapping/ no longer match canonical/.sha256.json, or inputs/project.yaml no longer
    matches the manifest's `project_hash` (I75 b)."""
    run_dir = Path(run_dir)
    old = read_manifest(run_dir)
    project = load_project(run_dir / "inputs" / "project.yaml")
    out = Path(out_dir) if out_dir is not None else run_dir.parent
    project = project.model_copy(update={"out_dir": out.resolve()})
    return _run(project, now, None, None, run_dir, old)


def _run(
    project: Project,
    now: datetime | None,
    strict: bool | None,
    run_dir: Path | None,
    reuse: Path | None,
    replay: RunManifest | None,
) -> RunOutput:
    if now is not None and now.tzinfo is None:
        raise ConfigError(f"now must carry a timezone (UTC): got the naive datetime {now}")
    now = now or datetime.now(UTC)
    configure_logging("setup")
    buffer = LogBuffer()  # what the load stage logs goes to logs/run.log once the folder exists
    try:
        with stage_timer("load"):
            if not replay and (project.options.strict if strict is None else strict):
                check_required_inputs({k for k, v in project.inputs.items() if v is not None})
            catalog, basis = load_catalog(project.catalog), load_basis(project.basis)
            scenarios = load_scenarios(project.scenarios)
            external = _external(replay) if replay else None
            if replay and reuse is not None:
                _check_replayable(reuse)  # before any folder is made
            salt = b"" if replay else load_salt(project.salt_file)  # a replay re-hashes nothing
            draft = build_manifest(project, catalog, basis, scenarios, now, external)
            if replay:
                _check_copies(replay, draft)
    finally:
        buffer.detach()
    early = timings()
    run_dir, manifest = create_run_dir(project.out_dir, draft, run_dir)
    configure_logging(manifest.run_id, run_dir / "logs" / "run.log")
    buffer.replay(manifest.run_id)
    log = get_logger()
    log.info("run_start", run_dir=str(run_dir), rerun_of=replay.run_id if replay else None)
    manifest = _save(manifest, run_dir, early)  # C1: what the run is, should it die in a stage
    if project.options.worlds == "typ":
        log.warning("worlds_typ_ignored", detail="the three worlds are always computed")
    ctx = _Setup(project, catalog, basis, scenarios, salt, run_dir, reuse, replay is not None)
    try:
        out = _stages(ctx, manifest, now, early)
    except (Exception, KeyboardInterrupt) as e:  # §2.7: the traceback goes to run.log, then up
        _mark_failed(run_dir, e)  # first: nothing below may leave a failed run looking whole
        log.error(
            "run_failed",
            error_type=type(e).__name__,
            error=str(e),
            traceback=traceback.format_exc(),
        )
        _save(read_manifest(run_dir), run_dir, early)  # the last checkpoint, for the post-mortem
        raise
    _strict_check(out, project.options.strict if strict is None else strict)
    return out


def _mark_failed(run_dir: Path, e: BaseException) -> None:
    """`logs/FAILED`: one JSON line, the exception class and the first line of its message (no
    data). A failed or killed run is otherwise a folder like a finished one (§2.4); `is_run` of
    the Streamlit app refuses it. Not being able to write it is logged, not raised: the original
    exception is the one to report."""
    reason = (str(e).splitlines() or [""])[0][:200]
    try:
        (run_dir / FAILED_FILE).write_text(
            json.dumps({"error_type": type(e).__name__, "reason": reason}) + "\n", encoding="utf-8"
        )
    except OSError as err:
        get_logger().warning("failed_marker_not_written", error=str(err))


@dataclass(frozen=True, eq=False)
class _Setup:
    """What `_stages` needs besides the manifest: the loaded inputs and how to ingest."""

    project: Project
    catalog: Catalog
    basis: DesignBasis
    scenarios: ScenarioSet
    salt: bytes
    run_dir: Path
    reuse: Path | None
    replay: bool


def _stages(su: _Setup, manifest: RunManifest, now: datetime, early: dict[str, float]) -> RunOutput:
    """Stages inputs, ingest, profile, design, scenarios, comparison, sensitivity; manifest.json
    is rewritten after each (C1)."""
    run_dir = su.run_dir
    manifest = _save(_ingest(su, manifest, now), run_dir, early)
    ctx = _context(su.project, su.basis, su.scenarios, su.catalog, run_dir)
    manifest = _save(manifest, run_dir, early)
    with stage_timer("scenarios"):
        results, evaluated = _size_all(ctx)
    manifest = _save(manifest, run_dir, early)
    with stage_timer("comparison"):
        finances = {sid: ev.finance for sid, ev in evaluated.items()}
        comparison = compare(results, finances, su.scenarios.baseline)
        (su.run_dir / "comparison" / "comparison.json").write_text(
            comparison.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    manifest = _save(manifest, run_dir, early)
    sensitivity = _sensitivity(ctx, evaluated) if su.project.options.sensitivity else None
    manifest = _save(manifest, run_dir, early)
    return RunOutput(
        run_dir=run_dir,
        manifest=manifest,
        results=results,
        finances=finances,
        comparison=comparison,
        sensitivity=sensitivity,
    )


def _save(manifest: RunManifest, run_dir: Path, early: dict[str, float]) -> RunManifest:
    """Write manifest.json with the stage timings so far (`early`: load, before the folder)."""
    manifest = manifest.model_copy(update={"timings": {**early, **timings()}})
    write_manifest(manifest, run_dir)
    return manifest


def _external(replay: RunManifest) -> dict[str, str]:
    """Hashes of the data and mapping files recorded by the run being replayed."""
    return {k: v for k, v in replay.inputs.items() if not k.startswith("inputs/")}


def _check_copies(replay: RunManifest, draft: RunManifest) -> None:
    """The copies under inputs/ must still be the bytes the original run hashed, and the project of
    inputs/project.yaml (paths aside) the one it ran with (None: a manifest from before I75 b)."""
    if replay.project_hash is not None and replay.project_hash != draft.project_hash:
        raise ConfigError(
            "rerun: inputs/project.yaml differs from the run's manifest (project_hash)"
        )
    for name, digest in replay.inputs.items():
        if name.startswith("inputs/") and name != PROJECT_COPY and draft.inputs.get(name) != digest:
            raise ConfigError(f"rerun: {name} differs from the run's manifest (sha256 mismatch)")


# ------------------------------------------------------------------ ingest and canonical reuse
def _ingest(su: _Setup, manifest: RunManifest, now: datetime) -> RunManifest:
    """Stages `inputs` and `ingest`: the run's copies of the inputs, then canonical/ and dq/ by
    ingest or by copy of `su.reuse`'s. Returns the manifest with `mapping_hashes`, project.yaml."""
    run_dir, reuse = su.run_dir, su.reuse
    with stage_timer("inputs"):
        project_sha = copy_inputs(su.project, run_dir)
    with stage_timer("ingest"):
        upp = _upp(su.catalog, su.basis)
        stored = _stored_key(reuse)
        if su.replay:  # the canonical tables of the run being replayed are the input
            assert stored is not None  # `_check_replayable` ran before the folder was made
            key = stored
        else:
            key = ingest_key(su.project, _external(manifest), su.salt, upp)
        if reuse is not None and key == stored and _intact(reuse):
            get_logger().info("canonical_reused", source=str(reuse))
            shutil.copytree(reuse / "canonical", run_dir / "canonical", dirs_exist_ok=True)
            shutil.copytree(reuse / "dq", run_dir / "dq", dirs_exist_ok=True)
            shutil.copytree(reuse / "inputs" / "mapping", run_dir / "inputs" / "mapping")
        else:
            if reuse is not None:
                why = (
                    "no ingest key"
                    if stored is None
                    else "inputs, mapping, salt or engine differ"
                    if key != stored
                    else "its canonical/, dq/ or inputs/mapping/ are missing or changed"
                )
                get_logger().info("canonical_not_reused", source=str(reuse), reason=why)
            inputs: dict[str, InputSpec | None] = {str(k): v for k, v in su.project.inputs.items()}
            try:
                ingest(
                    inputs,
                    run_dir,
                    su.salt,
                    keep_descriptions=su.project.options.keep_descriptions,
                    now=now,
                    default_units_per_pallet=upp,
                )
            finally:  # also after a failed ingest: mapping/ belongs under inputs/ (§2.4)
                if (run_dir / "mapping").is_dir():
                    shutil.move(run_dir / "mapping", run_dir / "inputs" / "mapping")
        (run_dir / "canonical" / KEY_FILE).write_text(key, encoding="utf-8")
        (run_dir / "canonical" / HASHES_FILE).write_text(
            json.dumps(_reused_files(run_dir), sort_keys=True, indent=1) + "\n", encoding="utf-8"
        )
    ing = IngestManifest.model_validate_json(
        (run_dir / "dq" / INGEST_MANIFEST).read_text(encoding="utf-8")
    )
    return manifest.model_copy(
        update={
            "mapping_hashes": {d.dataset: d.mapping_hash for d in ing.datasets},
            "inputs": {**manifest.inputs, PROJECT_COPY: project_sha},
        }
    )


def _upp(catalog: Catalog, basis: DesignBasis) -> int:
    return round(ParamSet(catalog, basis.overrides).value(UPP_ID))


def ingest_key(project: Project, external: Mapping[str, str], salt: bytes, upp: int) -> str:
    """What canonical/ is built from: the sha256 of every data and mapping file (`external`), what
    the project says about them (which files make which dataset, mapping, sheet), the salt (as a
    hash), storage.default_units_per_pallet, the engine version (the ingest code) and
    `options.keep_descriptions` (when set). Two runs with the same key have the same canonical
    tables."""
    body = {
        "hashes": external,
        "datasets": {
            k: s.model_dump(mode="json") if s else None for k, s in project.inputs.items()
        },
        "salt": hashlib.sha256(salt).hexdigest(),
        "upp": upp,
        "engine": [engine_version(), git_sha()],
    }
    if project.options.keep_descriptions:  # only when set: the keys of earlier runs stay valid
        body["keep_descriptions"] = True
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def find_canonical(project: Project) -> Path | None:
    """The newest run folder in `project.out_dir` whose canonical tables were built with the key
    this project would produce now (inputs, salt, engine), to pass as `reuse_canonical`; None when
    there is none. Needs the salt like `run_scenarios` does (ConfigError without)."""
    upp = _upp(load_catalog(project.catalog), load_basis(project.basis))
    key = ingest_key(project, external_hashes(project), load_salt(project.salt_file), upp)
    try:  # L5: an out_dir that cannot be listed (name too long, no permission) is a ConfigError
        keys = sorted(project.out_dir.glob(f"*/canonical/{KEY_FILE}"), reverse=True)  # = timestamp
        return next((k.parent.parent for k in keys if k.read_text(encoding="utf-8") == key), None)
    except OSError as e:
        raise ConfigError(f"{project.out_dir}: cannot look for earlier runs ({e.strerror})") from e


def _reused_files(run_dir: Path) -> dict[str, str]:
    """sha256 of every file a canonical reuse copies: canonical/, dq/ and inputs/mapping/ (the
    profile stage rewrites canonical/daily_series.parquet, so it is not an input of the reuse)."""
    skip = {f"canonical/{KEY_FILE}", f"canonical/{HASHES_FILE}", DAILY_SERIES_PATH}
    files = (
        p
        for sub in ("canonical", "dq", "inputs/mapping")
        for p in sorted((run_dir / sub).rglob("*"))
        if p.is_file()
    )
    return {
        rel: sha256_file(p) for p in files if (rel := p.relative_to(run_dir).as_posix()) not in skip
    }


def _intact(run_dir: Path) -> bool:
    """canonical/, dq/ and inputs/mapping/ of `run_dir` are still what its ingest stage wrote."""
    try:
        stored = json.loads((run_dir / "canonical" / HASHES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return stored == _reused_files(run_dir)


def _check_replayable(run_dir: Path) -> None:
    if _stored_key(run_dir) is None:
        raise ConfigError(f"rerun: {run_dir} has no canonical/{KEY_FILE} (did its ingest fail?)")
    if not _intact(run_dir):
        raise ConfigError(
            f"rerun: canonical/, dq/ or inputs/mapping/ of {run_dir} are missing or changed "
            f"since the run (canonical/{HASHES_FILE})"
        )


def _stored_key(run_dir: Path | None) -> str | None:
    path = None if run_dir is None else run_dir / "canonical" / KEY_FILE
    return path.read_text(encoding="utf-8") if path and path.is_file() else None


# ------------------------------------------------------------------ profile, design, scenarios
def _context(
    project: Project,
    basis: DesignBasis,
    scenarios: ScenarioSet,
    catalog: Catalog,
    run_dir: Path,
) -> RunContext:
    """Stages `profile` (F3 + I58 sku frame) and `design` (F4)."""
    cfg = project.profile_cfg
    with stage_timer("profile"):
        tables = build_tables(run_dir / "canonical", basis, cfg)
        profile = profile_from_tables(tables, cfg)
        write_profile(profile, run_dir, tables)
        master = run_dir / "canonical" / "sku_master.parquet"
        sku = sku_frame(tables, read_parquet_file(master) if master.is_file() else None)
    with stage_timer("design"):
        design_day = select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
        write_design(design_day, run_dir)
    return RunContext(project, basis, scenarios, catalog, tables, profile, sku, design_day, run_dir)


def context_from_run(run_dir: Path) -> RunContext:
    """Rebuild the `RunContext` of an existing run folder without writing anything (F10 stage
    commands `compare`, `report`, `calibrate`): `inputs/project.yaml` and the copies it points to
    (basis, scenarios, catalog), then the profile, I58 sku frame and base design day the same way
    `_context` does. ConfigError when `inputs/project.yaml` is missing (the run was never sized)."""
    run_dir = Path(run_dir)
    if not (run_dir / "inputs" / "project.yaml").is_file():
        raise ConfigError(f"{run_dir}: no inputs/project.yaml (run `whsizing size` first)")
    project = load_project(run_dir / "inputs" / "project.yaml")
    catalog, basis = load_catalog(project.catalog), load_basis(project.basis)
    scenarios = load_scenarios(project.scenarios)
    tables = build_tables(run_dir / "canonical", basis, project.profile_cfg)
    profile = profile_from_tables(tables, project.profile_cfg)
    master = run_dir / "canonical" / "sku_master.parquet"
    sku = sku_frame(tables, read_parquet_file(master) if master.is_file() else None)
    design_day = select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
    return RunContext(project, basis, scenarios, catalog, tables, profile, sku, design_day, run_dir)


def _size_all(ctx: RunContext) -> tuple[dict[str, ScenarioResult], dict[str, Evaluated]]:
    """Every scenario, the baseline one first (I42); results in scenarios.yaml order. A scenario
    raising SizingInfeasibleError becomes a not-computed result (the others go on); when it is
    the baseline, the others get no baseline (NPV, IRR and payback None, noted in finance)."""
    sc = ctx.scenarios
    client = sc.baseline == CLIENT_CURRENT
    results: dict[str, ScenarioResult] = {}
    evaluated: dict[str, Evaluated] = {}
    base: Evaluated | None = None
    for s in sorted(sc.scenarios, key=lambda s: s.id != sc.baseline):  # stable: baseline first
        with structlog.contextvars.bound_contextvars(scenario=s.id):
            try:
                ev = evaluate_scenario(
                    ctx, s, None if s.id == sc.baseline else base, client_baseline=client
                )
            except SizingInfeasibleError as e:
                reason = f"SizingInfeasibleError: {e}"
                get_logger().warning("scenario_not_computed", reason=reason)
                results[s.id] = not_computed_result(s, reason, ctx.basis.building.area_m2)
                write_scenario(results[s.id], Tracer(s.id), ctx.run_dir)
                continue
            write_finance(ev.finance, ctx.run_dir)  # finance nodes are in the trace: export last
            write_scenario(ev.result, ev.tracer, ctx.run_dir)
            get_logger().info("scenario_done", tco_typ=ev.finance.tco.typ, fit=ev.result.area.fit)
            results[s.id], evaluated[s.id] = ev.result, ev
            base = ev if s.id == sc.baseline else base
    order = [s.id for s in sc.scenarios]
    return {i: results[i] for i in order}, {i: evaluated[i] for i in order if i in evaluated}


def _sensitivity(ctx: RunContext, evaluated: Mapping[str, Evaluated]) -> Sensitivity | None:
    """F8b hook: `whsizing.scenarios.sensitivity.run_sensitivity(ctx, evaluated)`; skipped (None)
    while that module or function does not exist. The result is written to sensitivity.json."""
    try:
        module = importlib.import_module(SENSITIVITY_MODULE)
    except ModuleNotFoundError as e:
        if e.name != SENSITIVITY_MODULE:
            raise
        module = None
    hook = getattr(module, "run_sensitivity", None)
    if hook is None:
        get_logger().info("sensitivity_skipped", reason="F8b not installed")
        return None
    with stage_timer("sensitivity"):
        sensitivity: Sensitivity = hook(ctx, evaluated)
        path = ctx.run_dir / "comparison" / "sensitivity.json"
        path.write_text(sensitivity.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return sensitivity


def check_required_inputs(present: Collection[str]) -> None:
    """I80 (a), strict mode: a SKU master and a stock snapshot are required inputs (Appendix A
    minimum), `present` the datasets the run has. SizingInfeasibleError (exit 4) otherwise."""
    missing = [d for d in REQUIRED_INPUTS if d not in present]
    if missing:
        raise SizingInfeasibleError(
            f"strict: required input(s) missing: {', '.join(missing)} (a SKU master with "
            "dimensions and weight and a stock snapshot are needed; run without --strict "
            "to size with the flags and warnings)"
        )


def _not_computed_message(out: RunOutput, failed: list[str]) -> str:
    return (
        f"not computed: {', '.join(failed)} (see {out.run_dir}); "
        f"{failed[0]}: {out.results[failed[0]].status_reason}"
    )


def _strict_check(out: RunOutput, strict: bool) -> None:
    """Exit 4 (I75 f, I85 b): in strict mode when a scenario is not computed or none fits; without
    --strict only when NO scenario is computed (nothing is left to compare or report, so the run
    stops with the first reason instead of ending as a report of not-computed rows)."""
    failed = [sid for sid, r in out.results.items() if r.status == "not_computed"]
    if not strict:
        if failed and len(failed) == len(out.results):
            raise SizingInfeasibleError(
                f"no scenario computed: {_not_computed_message(out, failed)}"
            )
        return
    if failed:
        raise SizingInfeasibleError(f"strict: {_not_computed_message(out, failed)}")
    if not any(r.area.fit for r in out.results.values()):
        raise SizingInfeasibleError(f"strict: no scenario fits the building (see {out.run_dir})")
    assumed = [  # I80 (b): the flag code carries the share (`F_ELIG_ASSUMED:0.012000`)
        sid
        for sid, r in out.results.items()
        if r.scenario.family != "manual_p2p"
        and any(f.code.startswith("F_ELIG_ASSUMED") for f in r.flags)
    ]
    if assumed:
        raise SizingInfeasibleError(
            f"strict: F_ELIG_ASSUMED in {', '.join(assumed)}: eligibility assumed for SKUs "
            f"without dimensions (see {out.run_dir})"
        )
