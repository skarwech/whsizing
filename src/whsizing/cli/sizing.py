"""Stage commands on a run folder: size, compare, report, run-all, calibrate, rerun."""

from __future__ import annotations

import json
import secrets
import shutil
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any, Literal

import typer

from whsizing.calibration import CalibrationInputs, CalibrationResult, calibrate
from whsizing.calibration.inputs import DEFAULT_BASELINE
from whsizing.catalog import load_catalog
from whsizing.cli._core import (
    app,
    handle_errors,
    logged_seconds,
    open_run,
    print_comparison,
    print_notice,
    record_timings,
    require_sized,
    require_unsized,
    with_options,
)
from whsizing.cli._runio import (
    COMPARISON_FILE,
    SENSITIVITY_FILE,
    check_traces,
    load_evaluated,
    load_results,
    load_run,
)
from whsizing.cli._staged import profile_cfg_of, start_run, warn_units_per_pallet
from whsizing.config import load_project
from whsizing.design import load_basis, write_design
from whsizing.errors import ConfigError, ReportIntegrityError, WhsizingError
from whsizing.io import load_salt
from whsizing.io.ingest import DATASETS
from whsizing.logging import get_logger, stage_timer
from whsizing.profile import write_profile
from whsizing.scenarios.compare import compare as build_comparison
from whsizing.scenarios.load import load_scenarios
from whsizing.scenarios.runner import (
    _size_all,  # pyright: ignore[reportPrivateUsage]
    _strict_check,  # pyright: ignore[reportPrivateUsage]
    check_required_inputs,
    context_from_run,
    find_canonical,
    rerun,
    run_scenarios,
)
from whsizing.scenarios.sensitivity import run_sensitivity
from whsizing.schemas import IntegrityIssue, Project
from whsizing.schemas.project import ProjectOptions
from whsizing.schemas.run import RunOutput

Worlds = Literal["typ", "all"]
Lang = Literal["fr", "en", "both"]
Formats = Literal["pdf", "xlsx", "both"]
MAX_LISTED_ISSUES = 20


@app.command("size")
@handle_errors
def size_cmd(
    run: Annotated[Path, typer.Argument(help="Run folder made by `whsizing ingest`.")],
    basis: Annotated[Path, typer.Option(help="Design basis YAML.")],
    scenarios: Annotated[Path, typer.Option(help="Scenarios YAML.")],
    catalog: Annotated[Path, typer.Option(help="Catalog folder.")] = Path("catalog"),
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit 4 when an input is missing, a scenario is not computed, none fits, or an "
            "automated scenario assumes eligibility.",
        ),
    ] = False,
    worlds: Annotated[Worlds, typer.Option(help="Show typ only, or typ with lo-hi.")] = "all",
) -> None:
    """Design day and every scenario (sizing and finance): design/ and scenarios/ (F4-F7)."""
    run = open_run(run)
    require_unsized(run)
    basis_m, catalog_m = load_basis(basis), load_catalog(catalog)
    scenario_set = load_scenarios(scenarios)
    warn_units_per_pallet(catalog_m, basis_m)
    project = Project(
        name=run.name,
        out_dir=run.parent,
        catalog=catalog.resolve(),
        inputs={},  # the data stays where it was ingested from; dq/ingest_manifest.json lists it
        basis=basis.resolve(),
        scenarios=scenarios.resolve(),
        profile_cfg=profile_cfg_of(run),
        options=ProjectOptions(worlds=worlds, strict=strict),
    )
    if strict:  # before start_run seals the run: it can still be sized without --strict
        check_required_inputs(
            {ds for ds in DATASETS if (run / "canonical" / f"{ds}.parquet").is_file()}
        )
    manifest = start_run(run, project, catalog_m, basis_m, scenario_set)
    with stage_timer("profile"):  # includes the base design day: `context_from_run` does both
        ctx = context_from_run(run)
        write_profile(ctx.profile, run, ctx.tables)
    with stage_timer("design"):
        write_design(ctx.design_day, run)
    with stage_timer("scenarios"):
        results, evaluated = _size_all(ctx)
    ingest_s = logged_seconds(run, "ingest")  # ran in other processes, before the manifest
    record_timings(run, {} if ingest_s is None else {"ingest": ingest_s})
    finances = {sid: ev.finance for sid, ev in evaluated.items()}
    comparison = build_comparison(results, finances, scenario_set.baseline)
    print_comparison(comparison, worlds)
    print_notice()
    typer.echo(str(run))
    out = RunOutput(
        run_dir=run, manifest=manifest, results=results, finances=finances, comparison=comparison
    )
    _strict_check(out, strict)


@app.command("compare")
@handle_errors
def compare_cmd(
    run: Annotated[Path, typer.Argument(help="Sized run folder.")],
    sensitivity: Annotated[
        bool, typer.Option("--sensitivity/--no-sensitivity", help="Tornado, break-even, sweep.")
    ] = True,
    delta: Annotated[
        float | None, typer.Option(help="Sensitivity step (project option, 0.2).")
    ] = None,
) -> None:
    """Comparison table and sensitivity of a sized run: comparison/ (F8)."""
    run = open_run(run)
    require_sized(run)
    scenarios = load_scenarios(run / "inputs" / "scenarios.yaml")
    results, finances = load_results(run, scenarios)  # fail before the expensive context
    ctx = context_from_run(run)
    if delta is not None:
        ctx = replace(ctx, project=with_options(ctx.project, delta=delta))
    with stage_timer("comparison"):
        comparison = build_comparison(results, finances, scenarios.baseline)
        (run / COMPARISON_FILE).write_text(comparison.model_dump_json(indent=2) + "\n", "utf-8")
    sens_path = run / SENSITIVITY_FILE
    sens_path.unlink(missing_ok=True)  # never leave a sensitivity of other options behind
    if sensitivity:
        with stage_timer("sensitivity"):
            sens = run_sensitivity(ctx, load_evaluated(run, results, finances))
            sens_path.write_text(sens.model_dump_json(indent=2) + "\n", encoding="utf-8")
    record_timings(run)
    print_comparison(comparison, ctx.project.options.worlds)
    print_notice()
    typer.echo(str(run / "comparison"))


@app.command("report")
@handle_errors
def report_cmd(
    run: Annotated[Path, typer.Argument(help="Compared run folder.")],
    lang: Annotated[Lang | None, typer.Option(help="Report language (project language).")] = None,
    formats: Annotated[Formats, typer.Option(help="Which files to build.")] = "both",
) -> None:
    """Excel and PDF report of a run: report/ (F9). A failed integrity check exits 5."""
    run = open_run(run)
    require_sized(run)
    check_traces(run)  # one line naming file and line, not pydantic's dump (report/data.py's)
    out = load_run(run)
    project = load_project(run / "inputs" / "project.yaml")
    paths = build_reports(out, _langs(lang, project), formats)
    record_timings(run)
    _print_report(paths)


def _langs(lang: Lang | None, project: Project) -> list[str]:
    return list(project.language) if lang is None else ["fr", "en"] if lang == "both" else [lang]


def _report_fn(name: str) -> Any:
    """`whsizing.report.<name>`, imported when needed (F9 is built apart from the CLI)."""
    import whsizing.report as report

    fn = getattr(report, name, None)
    if fn is None:
        raise WhsizingError(f"whsizing.report.{name} is not available (the F9 report is missing)")
    return fn


def build_reports(out: RunOutput, langs: Sequence[str], formats: str) -> list[Path]:
    """`check_integrity` first (any issue: ReportIntegrityError, exit 5), then the files."""
    issues = _report_fn("check_integrity")(out)
    if issues:
        raise ReportIntegrityError(_integrity_message(issues))
    paths: list[Path] = []
    with stage_timer("report"):
        for lang in langs:
            if formats in ("xlsx", "both"):
                paths.append(Path(_report_fn("build_excel")(out, lang)))
            if formats in ("pdf", "both"):
                paths.append(Path(_report_fn("build_pdf")(out, lang)))
    return paths


def _integrity_message(issues: Sequence[IntegrityIssue]) -> str:
    """One line per issue (`IC1 location: message`), the first MAX_LISTED_ISSUES only."""
    lines = [f"  {i.id} {i.location}: {i.message}" for i in issues[:MAX_LISTED_ISSUES]]
    if len(issues) > MAX_LISTED_ISSUES:
        lines.append(f"  ... and {len(issues) - MAX_LISTED_ISSUES} more")
    return f"{len(issues)} integrity check(s) failed\n" + "\n".join(lines)


def _print_report(paths: Sequence[Path]) -> None:
    for p in paths:
        typer.echo(str(p))
    print_notice()


@app.command("run-all")
@handle_errors
def run_all_cmd(
    project_yaml: Annotated[Path, typer.Argument(help="project.yaml (Appendix E).")],
    strict: Annotated[
        bool | None, typer.Option("--strict/--no-strict", help="Override options.strict.")
    ] = None,
    worlds: Annotated[
        Worlds | None, typer.Option(help="Show typ only, or typ with lo-hi (options.worlds).")
    ] = None,
    sensitivity: Annotated[
        bool | None,
        typer.Option("--sensitivity/--no-sensitivity", help="Override options.sensitivity."),
    ] = None,
    delta: Annotated[
        float | None, typer.Option(help="Sensitivity step, 0 to 1 (options.delta).")
    ] = None,
    lang: Annotated[Lang | None, typer.Option(help="Report language (project language).")] = None,
    formats: Annotated[Formats, typer.Option(help="Which report files to build.")] = "both",
    salt_file: Annotated[
        Path | None, typer.Option(help="Anonymisation salt file (project, $WHSIZING_SALT).")
    ] = None,
    basis: Annotated[Path | None, typer.Option(help="Design basis YAML (project).")] = None,
    scenarios: Annotated[Path | None, typer.Option(help="Scenarios YAML (project).")] = None,
    catalog: Annotated[Path | None, typer.Option(help="Catalog folder (project).")] = None,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Accepted: run-all never asks anything.")
    ] = False,
    keep_descriptions: Annotated[
        bool, typer.Option("--keep-descriptions", help="Keep description and customer columns.")
    ] = False,
) -> None:
    """Ingest (or reuse canonical/ when the inputs are unchanged), size, compare and report."""
    del non_interactive  # ponytail: the runner's ingest has no confirm callback, it never asks
    project = _project_with_overrides(
        load_project(project_yaml), salt_file, basis, scenarios, catalog,
        {"worlds": worlds, "sensitivity": sensitivity, "delta": delta,
         "keep_descriptions": keep_descriptions or None},
    )  # fmt: skip
    load_salt(project.salt_file)  # ConfigError (exit 2) before the lookup and the run
    earlier = find_canonical(project)
    out = run_scenarios(project, strict=strict, reuse_canonical=earlier)
    if earlier is not None and _logged(out.run_dir, "canonical_reused"):
        get_logger().info("canonical reused", source=str(earlier), run_dir=str(out.run_dir))
    print_comparison(out.comparison, project.options.worlds)
    try:
        paths = build_reports(out, _langs(lang, project), formats)
    except WhsizingError:  # the run is complete: say where it is, the run folder is printed last
        typer.echo(f"run folder: {out.run_dir}", err=True)
        raise
    record_timings(out.run_dir)
    _print_report(paths)
    typer.echo(str(out.run_dir))


def _project_with_overrides(
    project: Project,
    salt_file: Path | None,
    basis: Path | None,
    scenarios: Path | None,
    catalog: Path | None,
    options: dict[str, Any],
) -> Project:
    """The project with the command-line overrides (those given) and a usable order_lines."""
    if project.inputs.get("order_lines") is None:  # before any run folder: exit 2, not 1
        raise ConfigError("project.yaml: inputs.order_lines is required (files to ingest)")
    paths = {"salt_file": salt_file, "basis": basis, "scenarios": scenarios, "catalog": catalog}
    changed = {k: v.resolve() for k, v in paths.items() if v is not None}
    project = project.model_copy(update=changed)
    return with_options(project, **{k: v for k, v in options.items() if v is not None})


def _logged(run_dir: Path, event: str) -> bool:
    """Did the runner log `event` in this run's logs/run.log?"""
    for line in (run_dir / "logs" / "run.log").read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("event") == event:
                return True
        except ValueError:  # not a JSON record: not ours to judge
            continue
    return False


@app.command("calibrate")
@handle_errors
def calibrate_cmd(
    run: Annotated[Path, typer.Argument(help="Sized run folder.")],
    actuals: Annotated[Path, typer.Option(help="Monthly actual hours CSV.")],
    activity_map: Annotated[Path, typer.Option(help="Activity map YAML.")],
    holdout_months: Annotated[
        int, typer.Option(min=1, help="Months held out for the back-test.")
    ] = 3,
    observed_peak_lines_h: Annotated[
        float | None,
        typer.Option(help="The client's observed peak lines/h: adds the peak lines/h error."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace the calibration/ the run already has.")
    ] = False,
) -> None:
    """Back-test and calibrate the baseline labor against a site's actuals: calibration/ (F11).

    The inputs are parsed and the calibration computed first; calibration/ (the two inputs and the
    results) is written only when that succeeded, so a failed run leaves an earlier one intact."""
    run = open_run(run)
    for f in (actuals, activity_map):
        if not f.is_file():
            raise ConfigError(f"{f}: file not found")
    out = run / "calibration"
    if out.exists() and not force:
        raise ConfigError(
            f"{out}: the run is already calibrated and runs are immutable; --force replaces it"
        )
    ctx = context_from_run(run)
    baseline = next(
        (s for s in ctx.scenarios.scenarios if s.id == ctx.scenarios.baseline), DEFAULT_BASELINE
    )
    t = ctx.tables
    inputs = CalibrationInputs(
        ctx.basis, ctx.design_day, baseline, ctx.catalog, ctx.sku, t.daily, t.lines
    )
    with stage_timer("calibration"):
        result = _calibrate_into(
            out, inputs, actuals, activity_map, holdout_months, observed_peak_lines_h
        )
    record_timings(run)
    h = result.holdout
    typer.echo(
        f"calibration {'accepted' if result.accepted else 'NOT accepted'}: hold-out MAPE "
        f"{h.total.mape:.1f} %, peak-month error {h.peak_month_error_pct:+.1f} %"
    )
    if h.peak_lines_h_error_pct is not None:
        typer.echo(
            f"peak lines/h: model {h.peak_lines_h_pred:.0f}, observed "
            f"{h.peak_lines_h_observed:.0f}, error {h.peak_lines_h_error_pct:+.1f} %"
        )
    for flag in result.flags:
        typer.echo(f"  {flag.code}: {flag.message}")
    print_notice()
    typer.echo(str(out))


def _calibrate_into(
    out: Path,
    inputs: CalibrationInputs,
    actuals: Path,
    activity_map: Path,
    holdout_months: int,
    observed_peak_lines_h: float | None,
) -> CalibrationResult:
    """`calibrate` into a scratch folder next to `out`, copy the two inputs in, then swap: an
    existing `out` is renamed aside, the scratch folder takes its place, the old one is removed.
    Any failure (also in the swap) removes the scratch folder and puts the earlier `out` back."""
    token = secrets.token_hex(4)  # mkdir, not mkdtemp: that one is 0700 and the run's folders not
    scratch, old = (
        out.with_name(f".calibration-{token}"),
        out.with_name(f".calibration-old-{token}"),
    )
    scratch.mkdir()
    try:
        result = calibrate(
            inputs, actuals, activity_map, scratch, holdout_months,
            observed_peak_lines_h=observed_peak_lines_h,
        )  # fmt: skip
        shutil.copyfile(actuals, scratch / "actuals.csv")
        shutil.copyfile(activity_map, scratch / "activity_map.yaml")
        if out.exists():
            out.rename(old)
        scratch.rename(out)
    except BaseException:
        if old.exists() and not out.exists():
            old.rename(out)
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)
    files = tuple(out / f.relative_to(scratch) for f in result.files)  # paths of the folder now
    return replace(result, out_dir=out, files=files)


@app.command("rerun")
@handle_errors
def rerun_cmd(
    run: Annotated[Path, typer.Argument(help="Run folder made by `whsizing run-all`.")],
    out_dir: Annotated[
        Path | None, typer.Option(help="Folder for the new run (that of the original).")
    ] = None,
) -> None:
    """A new run folder from the manifest and the inputs/ copies of an earlier run (C1)."""
    if not run.is_dir():
        raise ConfigError(f"{run}: run folder not found")
    out = rerun(run, out_dir=out_dir)
    worlds = load_project(out.run_dir / "inputs" / "project.yaml").options.worlds
    print_comparison(out.comparison, worlds)  # the run's own display option, like run-all
    print_notice()
    typer.echo(str(out.run_dir))
