# F8a audit record: scenario runner, run folder, manifest, rerun, comparison

Date of the fresh test run: 2026-11-09. Feature owner: F8a. Spec: `description.md` F8 (lines 1137-1163), section 2.4 run folder, section 2.5 `Project`/`RunManifest`/`Comparison`, section 2.7 errors, Appendix E, principle 5 (reproducibility).

## Final verdict: pass_with_issues

All F8a acceptance tests (T8.1, T8.2, T8.5, T8.6, T6.9) pass (119 passed, 0 failed, 0 skipped in the fresh run); T8.3 and T8.4 are F8b's and not applicable here.
Two medium and nine low findings are still open at the close of round 2 (no fix round followed it), the largest being a salt dependence of the sizing numbers rooted in F3 and an `out_dir` containing `[` that crashes after ingest. Both round-2 auditors returned pass_with_issues; nothing in this record is upgraded beyond that.

## T-id table

Fresh run (section "Fresh test output"): 119 passed, 0 failed, 0 skipped.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T8.1 | `test_T8_1_duplicate_scenario_id_is_a_config_error` (tests/unit/test_f8_runner_load.py) | pass | A scenarios.yaml with two `S0` entries raises `ConfigError` matching `duplicate scenario id.*S0`. |
| T8.1 | `test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder` (6 params) | pass | Ids that cannot name a folder (`../etc`, `S 1`, `S/1`, non-ASCII, 65 chars, reserved `client_current`) raise `ConfigError`. Related, not T-prefixed: `test_ids_that_differ_only_by_case_are_refused`. |
| T8.2 | `test_T8_2_every_scenario_appears_once_in_file_order` (tests/unit/test_f8_runner.py) | pass | On a real run on a small synthetic site, `results`, `finances` and `comparison.rows` each list S0, S1, S2 exactly once, in file order. |
| T8.2 | `test_T8_2_one_row_with_every_column_of_the_f8_list` (tests/unit/test_f8_compare.py) | pass | One row per scenario carries every column of the F8 list (areas, equipment, FTE, capex, opex, TCO range, NPV, payback, cost per line, warnings, low-confidence count), checked against result and finance. |
| T8.2 | `test_T8_2_every_scenario_appears_once_in_the_order_of_results` | pass | Row order follows result order, one row each. |
| T8.2 | `test_T8_2_not_computed_scenario_keeps_its_row_with_the_reason` | pass | A scenario that raised `SizingInfeasibleError` keeps its row, with status `not_computed` and the reason. |
| T8.2 | `test_T8_2_every_scenario_once_ranked_by_typ_and_consistent_with_the_overlaps` (hypothesis, tests/property) | pass | For generated scenario sets: every scenario once, `ranking_tco` sorted by typical TCO, consistent with the overlap pairs. |
| T8.3 | none (F8b, tornado sort) | not_applicable | Belongs to sensitivity (F8b); `scenarios/sensitivity.py` does not exist yet. |
| T8.4 | none (F8b, break-even root) | not_applicable | Belongs to sensitivity (F8b). |
| T8.5 | `test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds` (tests/e2e/test_f8_runner_e2e.py, marks `bench` + `slow`) | pass | On synthetic `ecom_mid` (730 days, about 0.98 M lines) the scenario stage (size + finance + write, 3 scenarios x 3 worlds) is read from `manifest.timings` and asserted `0 < t < 10` s. Fresh run: 0.49 s. A plain `pytest` runs it; `-m "not bench"` does not. |
| T8.6 | `test_T8_6_note_appears_iff_ranges_overlap` (tests/unit/test_f8_compare.py) | pass | The note `Ranking at typical values; ranges overlap for scenarios A and B; ...` appears iff closed TCO intervals intersect (touching counts, several pairs joined, a non-overlapping scenario absent); bare `Ranking at typical values` otherwise. |
| T8.6 | `test_T8_6_overlap_pairs_are_exactly_the_intersecting_distinct_pairs`, `test_T8_6_overlap_relation_is_symmetric_whatever_the_order`, `test_T8_6_note_appears_iff_overlaps_and_never_pairs_a_scenario_with_itself` (hypothesis) | pass | Pair set equals an independent `max(lo) <= min(hi)` oracle; symmetry under reordering; no self-pairs. |
| T6.9 | `test_T6_9_rerun_from_manifest_gives_identical_result_json` (tests/unit/test_f6_size.py) | pass | Replaces the skipped placeholder. Runs the example scenarios on a small site, deletes data, basis, scenarios, catalog and `WHSIZING_SALT`, calls `rerun()` and asserts byte-identical `result.json`, `finance.json`, `trace.jsonl` for S0..S2. |
| T6.9 | `test_T6_9_identical_inputs_give_byte_identical_result_json`, `test_T6_9_a_fresh_process_writes_the_same_result_json` | pass | Pre-existing F6 determinism tests in the same file, still green. |

Beyond the T-ids, 119 tests in total: test_f8_runner_load 14, test_f8_runner 23, test_f8_manifest 35, test_f8_compare 9, test_f8_compare_properties 4, test_f8_runner_e2e 5, test_f6_size 29. The e2e file also covers: every artifact of the run folder exists, comparison rows sane for the three families, baseline = S0 run, and a byte-identical rerun of the `ecom_mid` run.

## Proofs

All proofs below were captured by the auditors during the audit rounds, not produced by this write-up. `S` = `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F8a`. Scratch sub-folders map to rounds: scripts directly under `$S` (a*, t*) = round 0, `$S/r2` = round 1 audit, `$S/r3` = round 2 audit. Output excerpts are as the auditors reported them.

1. **Same salt gives byte-identical runs; the salt is stored nowhere (round 1 audit, resolves the round-0 high finding).**
   Command: `uv run python $S/r2/b1.py`.
   Output: `files 39 39 differing: ['dq/dq_report.json', 'dq/ingest_manifest.json'] (created_at only); salt strings in run c: []`. All `scenarios/*/{result,finance}.json`, `trace.jsonl`, canonical parquet, `comparison.json`, `design_day.json`, `demand_profile.json` identical.

2. **Determinism across processes (round 2 audit).**
   Command: `PYTHONHASHSEED=1 POLARS_MAX_THREADS=1 uv run python $S/r3/c5.py $S/r3/det1; PYTHONHASHSEED=77 POLARS_MAX_THREADS=8 uv run python $S/r3/c5.py $S/r3/det2`, then a checksum compare.
   Output: both runs got the same folder name `2026-05-05T05-05-05_688d2f`; `done compare` with no DIFF lines (html charts and `.sha256.json` excluded for the known dq/plotly reason).

3. **Rerun is byte-identical after the originals are gone, also rerun of a rerun.**
   Commands: `uv run python $S/r3/c1.py` (round 2); earlier `$S/t2.py`, `$S/a4.py` (round 0), `$S/r2/b3.py` (round 1).
   Output: `rerun scenario artifacts identical OK; comparison same: True`; `rerun vs original: ... 17/17 SAME`; `rerun-of-rerun: 17/17 SAME`; manifest differs only in `run_id`, `created_at`, timings.

4. **Comparison rows equal the on-disk artifacts; overlaps and ranking match a hand computation.**
   Command: `uv run python $S/r3/c3.py`.
   Output: `mismatches []; ranking_tco ['S0','S1','S2'] sorted by tco.typ True; overlaps [[S0,S1],[S0,S2],[S1,S2]]; note 'Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2'`. Other rounds: 0 mismatches over 13 numeric columns x 3 scenarios; `n_warnings` 0/2/2 equals the non-info flag count; `n_low_confidence_params` 30/49/50 equals the `F_LOW_CONFIDENCE` value.

5. **I42 finance wiring with a scenario baseline (round 0).**
   Command: `uv run python $S/a4.py`.
   Output: `S1 d0 ok True dt ok True, npv -345466.978013 indep -345466.978013; S2 d0 ok True dt ok True, npv -380894.234001 indep -380894.234001; S0 npv None payback None`. (`d0 = -(capex_S - capex_S0)`, `d_t = opex_S0,t - opex_S,t`.)

6. **Folder suffix is the first 6 hex of the manifest hash of the written `manifest.json` (round 2 audit, after the round-1 fix).**
   Command: independent `sha256(json.dumps(body, sort_keys=True))` over `$S/r3/runs/*/manifest.json`, plus `$S/r3/c2.py`.
   Output: `b9f086 b9f086 2026-11-18T14:02:11Z` (independent hash equals the folder suffix); `rerun hash==suffix True`. Before the fix (round 0, `$S/a7.py`) the folder said `644a79` while the written manifest hashed to `a21daf`.

7. **A failing run keeps its exit code, writes the manifest and logs the traceback (round 1 audit).**
   Command: `uv run python $S/r2/b3.py`.
   Output: `[short data] DataQualityError exit=3 ... manifest=True ... last_event=run_failed DataQualityError`; no stray top-level `mapping/`. No salt: `ConfigError exit=2`, no folder created.

8. **Integrity checks refuse tampered replays before any folder exists.**
   Commands: `$S/r2/b3.py` (round 1), `$S/r3/c2.py` (round 2).
   Output: `ConfigError exit=2: rerun: inputs/scenarios.yaml differs from the run's manifest (sha256 mismatch); folders unchanged: True`; `rerun with tampered canonical parquet -> ConfigError exit=2: rerun: canonical/, dq/ or inputs/mapping/ ... are missing or changed`; reuse of a changed run falls back to a fresh ingest (`canonical_not_reused`).

9. **Appendix E shapes, all-not-computed and strict mode.**
   Commands: `$S/r3/c2.py`, `$S/r3/c4.py`.
   Output: `receipts null: ok [computed x3]`, `receipts null rerun ok`, `mapped run ok ... rerun of mapped run ok`; all scenarios not computed (non-strict) still writes results and a comparison with empty rankings; `strict: SizingInfeasibleError 4 strict: not computed: S0, S1, S2`.

10. **Mutation checks (round 1 proof auditor).**
    Mutants M1, M3, M17 (ranking, warning count, dropped stub), M2 (`<` instead of `<=` in overlap), M18 (note dropped), M8 (ingest key ignores spec/sheet), M9 (project.yaml kept in hash), M10 (`is_baseline` conflict undetected), M16 (8 hex instead of 6), M19 (load duration not logged) were each killed by a named test, e.g. M8 by `test_ingest_key_follows_every_input_of_canonical`, M10 by `test_is_baseline_must_agree_with_the_baseline_key`.

Also captured: lint and types clean (round 0 auditor: ruff clean, `13 files already formatted`, pyright `0 errors`); full suite `1052 passed, 2 skipped` in round 0 and `1082 passed, 0 failed` reported by the round-2 proof auditor; salt edge cases (empty, whitespace, missing file, salt file inside a git repo) give `ConfigError` exit 2 with no folder (`$S/r2/b2.py`, round 1 audit).

## Audit rounds

Two auditors per round: "spec" (checks the spec and tests against the code) and "proof" (runs the feature end to end and tries to break it).

### Round 0 (first build): both auditors verdict fail

| Auditor | Findings | Verdict |
|---|---|---|
| spec | 1 high, 4 medium, 7 low | fail |
| proof | 1 high, 5 medium, 6 low | fail |

The build had 89 tests passing; the fail came from the high finding. The engineer's fix (round 1) resolved 15 reported items: 10 fixed, 5 deferred, 0 rejected.

| Finding (severity) | Resolution |
|---|---|
| Random per-run salt, `WHSIZING_SALT` ignored, `.salt` next to hashed tables (high; reported by both) | fixed: salt = `load_salt(project.salt_file)` (file, else `$WHSIZING_SALT`), resolved before any folder exists, `ConfigError` exit 2 if none, never written into the run |
| Sizing results depend on the salt (medium) | deferred: root cause is F3 `profile/abc.py:23`, ties broken on the hashed sku id; outside F8a paths |
| Folder suffix is not the hash of the written manifest (medium) | fixed: `manifest_hash` also excludes `inputs/project.yaml`; test recomputes from the written file |
| Failed run leaves no manifest, stray `mapping/`, no error record (medium) | fixed: `run_failed` with traceback in `run.log`, draft manifest written, mapping moved under `inputs/mapping`, exception type and exit code unchanged |
| No git describe / dirty flag (medium) | fixed: `engine_version = <pkg>+<git describe --always --dirty>`; falls back to the package version without git or commit |
| Reuse key ignores `InputSpec.sheet` (medium) | fixed: public `ingest_key` hashes files, mappings, each dataset's `InputSpec`, salt hash, units per pallet, engine version, git sha; a mismatch logs `canonical_not_reused` |
| `rerun()` without `.salt` raises raw `FileNotFoundError` (medium) | fixed: replay needs no salt |
| `is_baseline` ignored (low) | fixed: `ConfigError` when it disagrees with `baseline:` |
| `options.worlds: typ` ignored (low) | deferred: F6 has no single-world mode, `--worlds` is F10; warning `worlds_typ_ignored` kept |
| Canonical reuse manual, no public lookup (low) | fixed: public `find_canonical(project)` |
| `_write_secret` umask window (low) | fixed (moot: no salt file is written any more) |
| Load-stage duration not in `run.log` (low) | fixed for the duration (the records emitted during load are a remaining finding, see below) |
| `RunOutput` not exported from `whsizing.schemas` (low) | deferred: F0 blocker, needs `mock_run_output` in `tests/fixtures/factories.py` |
| F8a decisions absent from `docs/INTERPRETATIONS.md` (low) | deferred: file outside F8a paths |
| Raw `ZeroDivisionError` from `engine/throughput.py:446` on a zero rate override (low) | deferred: F5/F6; F8a now logs `run_failed` and keeps the manifest |

### Round 1 (after the fix): both auditors verdict pass_with_issues

| Auditor | Findings | Verdict |
|---|---|---|
| spec | 0 high, 2 medium, 7 low | pass_with_issues (102 passed) |
| proof | 0 high, 2 medium, 9 low | pass_with_issues |

The round-0 high is confirmed resolved. The round-2 history carries no fix record (`fix: null`), but the round-2 auditors observed the following round-1 findings as resolved in the tree; I report them as confirmed by those proofs, with no engineer description.

| Finding (severity) | Status after round 2 |
|---|---|
| `RunManifest.packages` lists 11 of the 23 section 3.1 packages (medium) | fixed: all 23 recorded; a test compares the list with `pyproject.toml` |
| Scenario ids differing only by case share a folder on a case-insensitive FS (medium) | fixed: `ConfigError` (`$S/r2/b5.py`) |
| Salt dependence of results, F3 `abc.py:23` (medium, both auditors) | open, deferred (outside F8a) |
| `rerun()` trusts `canonical/` without integrity check (low) | fixed: `canonical/.sha256.json`, tampered canonical/dq/mapping refused before any folder |
| Naive `now` fails mid-ingest with a raw polars error (low) | fixed: `ConfigError` exit 2 |
| `out_dir` that is a file gives raw `FileExistsError` (low) | fixed: `ConfigError` exit 2 |
| `rerun()` of a run without `.ingest_key` creates a folder first (low) | fixed: checked before the folder |
| Reuse of a damaged earlier run raises raw `FileNotFoundError` (low) | fixed: falls back to a fresh ingest with `canonical_not_reused` |
| Manifest only written at the end (low) | mostly fixed: written when the folder is made and after each stage group (see open issue 10) |
| Load-stage records only on console (low) | open (issue 6) |
| `options.worlds: typ`; `RunOutput` export; INTERPRETATIONS; `ZeroDivisionError`; dq/chart bytes (low) | open (issues 4, 5, 7, 8, 9) |

### Round 2 (no fix record supplied): both auditors verdict pass_with_issues

| Auditor | Findings | Verdict |
|---|---|---|
| spec | 0 high, 1 medium, 8 low | pass_with_issues (119 passed) |
| proof | 0 high, 2 medium, 7 low | pass_with_issues (1082 passed, 0 failed reported) |

New in round 2: the `[` in `out_dir` crash (medium), `inputs/project.yaml` not verified on rerun (low), manifest written per stage group rather than per stage (low), canonical reuse opt-in (low). None was fixed afterwards: no round followed. All are listed under open issues.

## Open issues

Status is that of the end of round 2; the fresh test run above is consistent with it (119 passed).

1. **medium, outside F8a (F3, deferred)**: sizing results depend on the anonymisation salt. `src/whsizing/profile/abc.py:23` sorts by `[by, "sku"]`, so ties on `by` are broken by the hashed sku id. Same salt reproduces exactly; different salts moved S0 TCO typ 479399.93 / 479623.10 / 479629.42 / 479634.33 while S1 (825102.81) and S2 (860530.06) were equal (`$S/r3/c6.py`). Fix: a salt-independent tie-break or an INTERPRETATIONS entry.
2. **medium, new in round 2, open**: an `out_dir` whose path contains `[` makes the run die after a full ingest with a `WhsizingError` (exit 1) `canonical order_lines: cannot read ...`, because polars treats the path as a glob (`profile/aggregate.py:44` `load_canonical`; the same pattern at `runner.py:408` and `io/ingest.py:170`). A data path containing `[2025]` is refused by `expand_files` with a misleading `MappingError` (exit 2). `(`, `{`, `*`, `?` were fine (`$S/r3/c3.py`). The fix spans F8a, F2 and F3 files.
3. **low, new in round 2, open (F8a)**: `rerun()` does not verify `inputs/project.yaml` against the sha256 in the manifest (`runner.py:268` excludes `PROJECT_COPY`). Editing `profile_cfg.abc_thresholds` in that file reruns without an error and changes S0/S1/S2 `result.json` (`$S/r3/c9.py`).
4. **low, F0 blocker**: `RunOutput` is not exported from `whsizing.schemas` (importable from `whsizing.schemas.run`). `test_f0_schemas.py::test_T0_3` requires an example in `tests/fixtures/factories.py` for every exported model. Fix: add `mock_run_output()` to `schema_examples()`, then export. F8b and F9 import from `whsizing.schemas.run` meanwhile.
5. **low, deferred**: `options.worlds: typ` is accepted but ignored (the three worlds are always computed; logged as `worlds_typ_ignored`). F6 has no single-world mode; `--worlds` is F10.
6. **low**: records emitted during the load stage before the run folder exists (`catalog_todo_sources`, `catalog_warning`) appear only on the console (`run_id=setup`), not in `logs/run.log`; only the load duration is re-logged.
7. **low, outside F8a**: `docs/INTERPRETATIONS.md` (binding) has no F8a entries; the last is I74 (F11). To register: run folder name and clash rule, manifest hash exclusions (run_id, mapping_hashes, timings, `inputs/project.yaml`), `ingest_key`, `canonical/.sha256.json`, salt source rule, `engine_version`, the not_computed stub, payback ranking leaving out scenarios without a payback, `baseline_id` semantics, `is_baseline` agreement, `run_failed` handling.
8. **low**: `engine/throughput.py:446` raises a raw `ZeroDivisionError` for zero overrides (`amr_gtp.station_rate_lines_h`, `amr_gtp.oee`, `manual_p2p.pick_rate_shelving_lines_h`); `ParamSet` checks finiteness only. F8a logs `run_failed` and keeps the manifest, but the exception is not a `WhsizingError` and has no section 2.7 exit code. F5/F6.
9. **low, outside F8a (F2/F3)**: same-salt runs are not byte-identical for `dq/dq_report.json`, `dq/ingest_manifest.json` (`created_at` is the wall clock, not the injected `now`; `canonical/.sha256.json` follows) nor `profile/charts/*.html` (random plotly ids). The F8a byte-identity test therefore covers 17 files, not all of them.
10. **low**: the manifest is written when the folder is made and after each stage group ({inputs, ingest}, {profile, design}), not after every stage as C1 words it; a hard kill between two stages of a group loses the first stage's entry.
11. **low, design**: canonical reuse is opt-in. `run_scenarios(project)` always ingests; the caller passes `reuse_canonical=find_canonical(project)` (F10 run-all, T10.2).
12. **Behaviour change for F9, F10 and callers**: `run_scenarios` needs a salt (`project.salt_file` or `$WHSIZING_SALT`) and raises `ConfigError` exit 2 before any folder is created otherwise. The shipped `project/example_project.yaml` has `salt_file: null`, so export `WHSIZING_SALT`. `rerun()` needs none.
13. **Minor, housekeeping**: `runner.py` is 474 lines (above the 400 typical, below the 800 max). `ruff format` on `tests/unit/test_f6_size.py` may have changed formatting outside the T6.9 edit; no git baseline exists (no commit in the repo) to rule it out.
14. T8.3 (tornado sort) and T8.4 (break-even root) are F8b's. F8a's hook `whsizing.scenarios.sensitivity.run_sensitivity(ctx, evaluated)` is called only if that module exists (`test_sensitivity_hook_receives_the_context_and_its_result_is_written` covers it); until then `sensitivity` is `null`.

## Not applicable here and why

- **T8.3, T8.4**: sensitivity (F8b), not part of F8a; no test function exists in this feature's files.
- **Docker / container run**: no F8a test needs it (F0's Docker test is skipped for lack of Docker, outside this feature).
- **Real client data**: every run used synthetic data (`ecom_mid`, 730 days; a small 300-SKU 120-day site for unit tests, because `tiny_golden` has 31 days and fails ingest rule R9). The numbers (S0 TCO 4.70 M EUR, S1 5.72, S2 6.46; paybacks 0.42, 2.04, 2.84 years) are synthetic placeholders, not findings, and the T8.5 timing is for this machine on synthetic data.
- **Domain expert review**: no expert has reviewed the runner, the baseline handling or the comparison semantics; the confidence note carries no recommendation text by design.
- **GitHub CI**: not run.
- **Not built (out of scope)**: `whsizing run-all` / `rerun` CLI wiring (F10); the Excel/PDF report (F9, `report/` is created empty); joblib parallel scenarios (optional in the spec; the serial stage takes about 0.4-0.5 s); a `FinancialResult` for a not-computed scenario (its `ScenarioResult` is a zero-valued stub, no `finance.json`).

## Fresh test output

Command, run on 2026-11-09 from `/Users/skarwech/saas_v1` with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (output trimmed to the relevant lines):

```
uv run pytest tests/unit/test_f8_runner*.py tests/unit/test_f8_compare*.py tests/unit/test_f8_manifest*.py tests/property/test_f8_*.py tests/e2e/test_f8_*.py tests/unit/test_f6_size.py -q -rA

T8.5 scenario stage (3 scenarios x 3 worlds, size + finance + write): 0.49 s; all stages load 0.12, inputs 0.00, ingest 3.05, profile 1.46, design 0.00, scenarios 0.49, comparison 0.00

F8a e2e ecom_mid, baseline client_current
  S0 manual_p2p: capex 0.32 M€ [0.17-0.71], opex y1 0.99 M€ [0.71-1.42], TCO 4.70 M€ [3.30-6.99], NPV vs client 3.13 M€ [1.27-4.24], payback 0.42 y, ...
  S1 amr_gtp: capex 1.85 M€ [0.73-6.02], ... TCO 5.72 M€ [3.37-12.73], NPV vs client 2.15 M€ [-4.32-4.15], payback 2.04 y, ...
  S2 cube_asrs: capex 2.71 M€ [1.11-7.68], ... TCO 6.46 M€ [3.67-14.18], NPV vs client 1.38 M€ [-5.88-3.84], payback 2.84 y, ...
  ranking TCO ['S0', 'S1', 'S2'], payback ['S0', 'S1', 'S2']
  Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2
F8a e2e ecom_mid, baseline S0: S1 NPV -1.02 M€ [-5.74--0.08] payback None, S2 NPV -1.76 M€ [-7.20--0.38] payback None; ranking payback []

PASSED tests/unit/test_f8_runner_load.py::test_T8_1_duplicate_scenario_id_is_a_config_error
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['../etc']
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['S 1']
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['S/1']
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['\xe9']
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['xxxx...(65 x)']
PASSED tests/unit/test_f8_runner_load.py::test_T8_1_id_guard_rejects_ids_that_cannot_name_a_folder['client_current']
PASSED tests/unit/test_f8_runner.py::test_T8_2_every_scenario_appears_once_in_file_order
PASSED tests/unit/test_f8_compare.py::test_T8_2_one_row_with_every_column_of_the_f8_list
PASSED tests/unit/test_f8_compare.py::test_T8_2_every_scenario_appears_once_in_the_order_of_results
PASSED tests/unit/test_f8_compare.py::test_T8_2_not_computed_scenario_keeps_its_row_with_the_reason
PASSED tests/unit/test_f8_compare.py::test_T8_6_note_appears_iff_ranges_overlap
PASSED tests/property/test_f8_compare_properties.py::test_T8_6_overlap_pairs_are_exactly_the_intersecting_distinct_pairs
PASSED tests/property/test_f8_compare_properties.py::test_T8_6_overlap_relation_is_symmetric_whatever_the_order
PASSED tests/property/test_f8_compare_properties.py::test_T8_6_note_appears_iff_overlaps_and_never_pairs_a_scenario_with_itself
PASSED tests/property/test_f8_compare_properties.py::test_T8_2_every_scenario_once_ranked_by_typ_and_consistent_with_the_overlaps
PASSED tests/e2e/test_f8_runner_e2e.py::test_F8_every_artifact_of_the_run_folder_exists
PASSED tests/e2e/test_f8_runner_e2e.py::test_F8_comparison_rows_are_sane_for_the_three_families
PASSED tests/e2e/test_f8_runner_e2e.py::test_F8_scenario_baseline_run_compares_against_s0
PASSED tests/e2e/test_f8_runner_e2e.py::test_F8_rerun_of_the_ecom_mid_run_is_byte_identical
PASSED tests/e2e/test_f8_runner_e2e.py::test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds
PASSED tests/unit/test_f6_size.py::test_T6_9_identical_inputs_give_byte_identical_result_json
PASSED tests/unit/test_f6_size.py::test_T6_9_a_fresh_process_writes_the_same_result_json
PASSED tests/unit/test_f6_size.py::test_T6_9_rerun_from_manifest_gives_identical_result_json

119 passed in 52.54s
```

Passed per file (all 119 are PASSED lines, none FAILED, SKIPPED or ERROR): test_f8_runner_load 14, test_f8_runner 23, test_f8_manifest 35, test_f8_compare 9, test_f8_compare_properties 4, test_f8_runner_e2e 5, test_f6_size 29.

Fresh static checks on the owned paths (same day): `uv run ruff check ...` gives `All checks passed!`; `uv run ruff format --check ...` gives `13 files already formatted`; `uv run pyright src/whsizing/scenarios src/whsizing/schemas/run.py` gives `0 errors, 0 warnings, 0 informations`.
