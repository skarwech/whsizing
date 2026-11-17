"""F8 scenario runner, run folder, manifest, rerun and comparison (F8a); F8b adds sensitivity.

Public API (stable; F8b builds on it):

    scenarios = load_scenarios(path)                 # ScenarioSet; ConfigError: duplicate or bad id
    out = run_scenarios(project, now=None, strict=None, run_dir=None, reuse_canonical=None)
    out = rerun(run_dir, now=None, out_dir=None)     # new folder, same result.json / finance.json
    earlier = find_canonical(project)                # newest run whose canonical/ still matches
    cmp = compare(results, finances, baseline_id)    # Comparison, one row per entry of `results`

`run_scenarios` returns `RunOutput` (whsizing.schemas.run): `run_dir`, `manifest`, `results` (every
scenario of scenarios.yaml in file order; status "not_computed" stub when sizing raised
SizingInfeasibleError), `finances` (computed scenarios), `comparison`, `sensitivity`. Stages, each
under `stage_timer` and copied to `manifest.timings`: load, inputs, ingest, profile, design,
scenarios (size + finance + write of every scenario), comparison, sensitivity.

Run folder (§2.4): `<project.out_dir>/<YYYY-MM-DDTHH-MM-SS>_<6 hex of the manifest hash>/`, created
with mkdir and never overwritten; `manifest.json`, `inputs/` (basis.yaml, scenarios.yaml,
project.yaml whose paths point inside the run, mapping/*.yaml, catalog/), canonical/, dq/,
profile/, design/, scenarios/<id>/{result,finance}.json + trace.jsonl, comparison/, report/ (empty,
F9) and logs/run.log. The anonymisation salt is the project's `salt_file`, else $WHSIZING_SALT
(ConfigError when neither is set): it is never written into the run folder, and the same salt on
the same inputs gives the same run (§2.2 principle 5). manifest.json is written when the folder is
made and again after every stage (C1); a run that fails once its folder exists logs `run_failed`
with the traceback to logs/run.log and keeps the manifest of its last finished stage. What the load
stage logged before the folder existed (`catalog_todo_sources`, ...) is written to logs/run.log too.
Paths are never read as globs where a literal path is meant (I75 i): `[`, `]`, `*`, `?` are fine in
`out_dir`, data and project paths. `RunManifest.project_hash` (sha256 of the project model without
its paths) is checked by `rerun`: an edited `inputs/project.yaml` is a ConfigError (I75 b). A
scenario or basis override of a Param must be finite, and > 0 where its catalog `min` is (I75 j).

Canonical reuse: `canonical/.ingest_key` = `ingest_key(...)` (input and mapping hashes, the
project's dataset/sheet assignment, salt, units per pallet, engine version). `run_scenarios(project,
reuse_canonical=find_canonical(project))` copies canonical/, dq/ and inputs/mapping/ of the newest
run with the same key instead of ingesting (F10 run-all, T10.2). `canonical/.sha256.json` holds the
sha256 of those files: a run whose files changed since is not reused (a fresh ingest, with a
`canonical_not_reused` record), and `rerun` refuses it with a ConfigError before making a folder.

Baseline: `scenarios.baseline` is "client_current" (every scenario is financed against
`basis.baseline`, I73 b) or a scenario id (that scenario is sized and financed first, with no
baseline of its own, and the others are financed against it, I42). If the baseline scenario is
not computed the others get no baseline: NPV, IRR and payback are None, with a note in finance.

Strict (`options.strict` or `strict=`): all scenarios run and everything is written, then
SizingInfeasibleError (exit 4) is raised when a scenario is not computed or none fits the building.

For F8b (sensitivity, break-even, percentile sweep)
---------------------------------------------------
`runner.RunContext` holds what one run read: project, basis, scenarios, catalog, F3 `tables` and
`profile`, the I58 `sku` frame, the base `design_day` and `run_dir`. Re-size a variant with

    ev = evaluate_scenario(ctx, scenario, baseline=None, client_baseline=False,
                           basis=changed_basis, design_day=changed_design_day)

(`scenario.overrides` carries catalog changes; a new Tracer is made inside; nothing is written;
it may raise SizingInfeasibleError). `ev` is `Evaluated(result, finance, tracer)`.

Hook: when `options.sensitivity` is true the runner calls, if it exists,

    run_sensitivity(ctx: RunContext, evaluated: Mapping[str, Evaluated]) -> Sensitivity
    # in whsizing/scenarios/sensitivity.py

`evaluated` = the computed scenarios of the run (baseline included; `ctx.scenarios.baseline` names
the baseline, `ctx.project.options.delta` is δ). The runner writes the returned model to
`comparison/sensitivity.json`, times the call as stage "sensitivity" and returns it in
`RunOutput.sensitivity`; without that module or function `sensitivity` is None.

F8b: sensitivity, break-even and percentile sweep
-------------------------------------------------
`run_sensitivity` (sensitivity.py) is that hook. Its pieces are public too, and work on a run's
`RunContext` (the spec's `project` argument: it carries the loaded project and the frames already
computed, so nothing is ingested again; a `Project` is a ConfigError, call `run_scenarios` first):

    sensitivity_oat(ctx, params=None, delta=0.2) -> Sensitivity  # tornado; PARAMS names them
    break_even_rows(ctx, target_payback=5.0) -> list[BreakEven]  # one per automated scenario
    percentile_sweep(ctx, percentiles=(80, 90, 95, 98)) -> list[PercentileSweepRow]
    from whsizing.scenarios.breakeven import breakeven           # one scenario's k, or None

(`breakeven` is not re-exported here: the module of that name would be hidden by the function.)
Each module docstring documents the variants, units and the bracketing function of the break-even.
`Sensitivity.skipped` lists, one line each, the variants a SizingInfeasibleError left out (scenario,
parameter, direction, reason; the baseline's too) and the runs whose paybacks are None because the
baseline scenario is not computed.
"""

from whsizing.scenarios.breakeven import break_even_rows
from whsizing.scenarios.compare import compare, not_computed_result, overlap_note, tco_overlaps
from whsizing.scenarios.load import load_scenarios
from whsizing.scenarios.runner import (
    Evaluated,
    RunContext,
    evaluate_scenario,
    find_canonical,
    ingest_key,
    rerun,
    run_scenarios,
)
from whsizing.scenarios.sensitivity import PARAMS, run_sensitivity, sensitivity_oat
from whsizing.scenarios.sweep import percentile_sweep

__all__ = [
    "PARAMS",
    "Evaluated",
    "RunContext",
    "break_even_rows",
    "compare",
    "evaluate_scenario",
    "find_canonical",
    "ingest_key",
    "load_scenarios",
    "not_computed_result",
    "overlap_note",
    "percentile_sweep",
    "rerun",
    "run_scenarios",
    "run_sensitivity",
    "sensitivity_oat",
    "tco_overlaps",
]
