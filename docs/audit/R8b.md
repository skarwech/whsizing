# R8b audit record: final-audit fixes (plausibility guards, calibrate semantics, failed-run marker, CLI errors)

Date of the fresh test run: 2026-11-10. Feature owner: R8b. Spec: `description.md` F6e queue (1006-1023), F10 CLI (1240-1281), F11 (1285-1323), section 2.4 run folder, section 2.7 errors; `docs/INTERPRETATIONS.md` I85 (b), I86, I89, I75, I78 (binding); `docs/audit/FINAL.md` findings M4, M5, L5 and the low list.

Owned code (as built): `src/whsizing/engine/{queue,throughput,area}.py`, `src/whsizing/scenarios/runner.py`, `src/whsizing/cli/{_core,_runio,sizing}.py`, `src/whsizing/app/state.py`, `src/whsizing/calibration/evaluate.py`, `catalog/engine_defaults.yaml`, and the tests `tests/unit/test_f6_{queue,throughput,area}.py`, `test_f8_r8b_runner.py`, `test_f10_cli.py`, `test_f10_app_state.py`, `test_f10_calibrate_swap.py`, `test_f11_evaluate.py`, `tests/e2e/test_f10_cli_r8b.py`.

R8b has no acceptance T-ids of its own. It remediates final-audit findings, so its tests carry the spec ids they extend (T6.4, T10.1, T10.3, T10.4, T11.3) and `test_L5_*` for the one finding that has no spec id.

## Final verdict: pass_with_issues

The fresh run is 726 passed, 1 skipped (the T11.4 real-pilot skip), 0 failed; both audit rounds returned pass_with_issues, and ruff and pyright are clean on the R8b paths, so nothing is upgraded.
No high or medium finding is open (the one medium, M5 ending as exit 0 with an all-not-computed report, was fixed and re-verified live in round 1), but six low findings from round 1 and an unregistered-behaviour gap in the register, runbook and catalog changelog stay open (see "Open issues").

## Test table

Status is from the fresh run of 2026-11-10. Parametrised cases are listed in brackets. Rows marked "existing" were already in the tree and still pass; the others were added by R8b (build or fix round).

| T-id | test function | status | what it proves |
|---|---|---|---|
| T6.4 | `test_T6_4_erlang_c_values`, `test_T6_4_w_q_matches_mm1_closed_form`, `test_T6_4_w_q_matches_mm2_closed_form` (`test_f6_queue.py`, existing) | pass | `erlang_c(1, 0.5) = 0.5`, `erlang_c(2, 1.0) = 1/3`, W_q equal to the M/M/1 and M/M/2 closed forms (as read by the spec auditor): the guard changes nothing below the bound |
| T6.4 | `test_T6_4_erlang_c_rejects_c_above_the_bound` | pass | `erlang_c` raises `SizingInfeasibleError` (exit 4) for c = 100,001 and c = 417,235,608 without looping; c = 100,000 still runs |
| T6.4 | `test_T6_4_queue_resource_passes_the_bound_to_erlang_c` | pass | `queue_resource` hands the world's `max_c` to `erlang_c` |
| T6.4 | `test_T6_4_default_bound_is_the_catalog_scalar` | pass | `MAX_SERVERS` equals `engine.max_equipment_count` = 100,000; it is a catalog constant and not a `Param`, so the I47 counts stay 30/49/50 |
| T6.4 | `test_T6_4_a_catalog_copy_without_the_bound_still_loads_with_the_default` | pass | `EngineDefaults.max_equipment_count` has a model default, so run folders written before this change still load |
| T6.4 | `test_T6_4_count_above_the_bound_is_infeasible_before_any_loop[manual_p2p-dd0-pickers, manual_p2p-dd1-forklifts, cube_asrs-dd2-pickers, amr_gtp-dd3-pickers]` (`test_f6_throughput.py`) | pass | pickers (manual, cube, AMR) and forklifts above the bound raise `SizingInfeasibleError` before any loop |
| T6.4 | `test_T6_4_automated_counts_are_bounded[cube_asrs-500-ports, cube_asrs-700-robots, amr_gtp-800-gtp_stations, amr_gtp-900-robots]` | pass | cube ports and robots, AMR GTP stations and robots are bounded |
| T6.4 | `test_T6_4_pods_are_bounded` | pass | the pod count read from `storage.py` is bounded in the AMR resource |
| T6.4 | `test_T6_4_infinite_load_is_reported_not_an_overflow` | pass | an infinite load gives `SizingInfeasibleError`, not `OverflowError` |
| T6.4 | `test_T6_4_normal_counts_are_unchanged_and_pass_the_bound` | pass | ordinary counts are unchanged by the check |
| T6.4 | `test_T6_4_pack_stations_above_the_bound_are_infeasible` (`test_f6_area.py`) | pass | pack stations in `area.py` are bounded |
| T6.4 | `test_T6_4_outlier_quantities_stop_in_seconds_with_exit_4_under_strict` (`test_f10_cli_r8b.py`) | pass | 50 order lines of quantity 1e12, sensitivity on, `run-all --strict`: exit 4 and a message naming the resource, the value and R13. The test's own time bound is loose (`seconds < 90`); the measured 2.83 s comes from the audit proof 1, not from the assertion |
| T6.4 | `test_T6_4_outlier_quantities_without_strict_stop_with_exit_4_and_no_report` | pass | Added in the fix round (replaces an exit-0 test): without `--strict`, when no scenario is computed, exit 4 with 'no scenario computed', three `not_computed` stubs, empty `report/`, no `logs/FAILED`, `is_run` true |
| T10.1 | `test_T10_1_calibrate_has_force_and_observed_peak_options` (`test_f10_cli.py`) | pass | `--force` and `--observed-peak-lines-h` appear in `calibrate --help` |
| T10.1 | `test_T10_1_calibrate_happy_path` (`test_f10_cli_e2e.py`, existing) and 40 further `test_T10_1_*` (help smoke per command, happy paths) | pass | Happy path on the generated 243-day site (the tiny_golden substitution is I84) |
| T10.3 | `test_T10_3_calibrate_failed_recalibration_leaves_the_earlier_one_untouched` (`test_f10_cli_r8b.py`) | pass | M4: good calibrate, then a bad actuals file: without `--force` exit 2, with `--force` exit 3; `calibration/` byte-identical, the user's own file is named, no scratch folder left |
| T10.3 | `test_T10_3_calibrate_with_force_replaces_and_reports_the_observed_peak` | pass | `--force` swaps the folder; `--observed-peak-lines-h` reaches `holdout.json` and the CLI output; 0, -3, nan, inf give exit 2 and change nothing |
| T10.3 | `test_T10_3_calibrate_first_failed_calibration_creates_no_calibration_folder` | pass | A first failed calibration leaves no `calibration/` at all |
| T10.3 | `test_T10_3_a_recalibration_replaces_the_earlier_one_and_leaves_no_folder_behind`, `test_T10_3_a_failing_calibrate_keeps_the_earlier_one_and_removes_the_scratch` (`test_f10_calibrate_swap.py`) | pass | The swap, and a `KeyboardInterrupt` inside `calibrate()`: earlier folder kept, no scratch left |
| T10.3 | `test_T10_3_a_failure_while_swapping_keeps_the_earlier_calibration` | pass | Added in the fix round: `Path.rename` patched to fail on the scratch-to-out step; the earlier calibration is byte-identical and no scratch or aside folder remains |
| T10.3 | `test_T10_3_a_first_calibration_has_the_modes_of_the_other_run_folders` | pass | Added in the fix round: `calibration/` is created with the umask like its siblings, not 0700 (the fix record also names a mode comparison against `dq/` in the e2e recalibration test) |
| T10.3 | `test_T10_3_the_returned_result_names_the_folder_it_ended_in` | pass | Added in the fix round: `CalibrationResult.out_dir` is the final folder and every `files` path exists under it |
| T10.3 | `test_T10_3_sigterm_during_sizing_marks_the_run_failed_and_exits_143` | pass | A real `whsizing run-all` subprocess killed with SIGTERM during sizing: returncode 143, `logs/FAILED`, `run_failed` in `run.log`, folder not listed by the app |
| T10.3 | `test_T10_3_corrupt_trace_is_a_one_line_error_naming_file_and_line[report, compare]` | pass | A corrupt `trace.jsonl`: exit 2 and one error line naming file and line |
| T10.3 | `test_T10_3_missing_trace_is_a_one_line_config_error_not_an_unexpected_one[report, compare]` | pass | Added in the fix round: a missing `trace.jsonl` is a `ConfigError` (exit 2), not 'unexpected FileNotFoundError' exit 1 |
| T10.3 | `test_T10_3_a_failing_stage_writes_the_marker_and_the_app_skips_the_folder`, `..._an_ingest_failure_or_an_interrupt_marks_the_run_too[MappingError, KeyboardInterrupt]` (`test_f8_r8b_runner.py`) | pass | `logs/FAILED` is written on a stage failure, an ingest failure and an interrupt, and `is_run` refuses the folder |
| T10.3 | `test_T10_3_exit_4_strict_is_a_complete_run_not_a_failed_one`, `..._a_finished_run_has_no_marker_and_is_listed`, `..._the_failed_marker_path_is_the_one_the_app_reads` | pass | Exit 4 under strict is a complete run (no marker); a finished run has no marker and is listed; the marker path in `runner.py` equals the one in `app/state.py` |
| T10.3 | `test_T10_3_strict_message_carries_the_reason_of_the_first_scenario_not_computed` | pass | The strict message ends with the first not-computed scenario's reason |
| T10.3 | `test_T10_3_no_scenario_computed_is_exit_4_even_without_strict`, `..._one_scenario_not_computed_without_strict_still_exits_0` | pass | Added in the fix round: zero computed scenarios raise exit 4 without `--strict`; a partial failure (S0 computed, S1 and S2 not) stays exit 0 |
| T10.3 | `test_T10_3_sigterm_becomes_terminated_with_exit_code_128_plus_signal`, `..._a_command_in_a_thread_keeps_the_default_sigterm_handler` (`test_f10_cli.py`) | pass | SIGTERM becomes `Terminated` with exit 128 + signal; in a non-main thread (Streamlit) the handler is not installed |
| T10.3 | 20 further `test_T10_3_*` (`test_f10_cli.py` 13, `test_f10_cli_e2e.py` 7) | pass | Existing exit-code table checks (exit 0 to 5) still hold |
| T10.4 | `test_T10_4_a_failed_run_is_neither_listed_nor_opened` (`test_f10_app_state.py`) | pass | `is_run`, `list_runs`, `resolve_run` and `restore` refuse a folder with `logs/FAILED` |
| T10.4 | 62 further `test_T10_4_*` (`test_f10_app_*.py`) | pass | Existing app state, form, results, drill-down and static checks |
| T11.3 | `test_T11_3_observed_peak_lines_h_must_be_a_finite_positive_number[0.0, -5.0, nan, inf, -inf]` (`test_f11_evaluate.py`) | pass | Added in the fix round: a non-finite or non-positive observed peak is a `ConfigError` |
| T11.3 | 13 further `test_T11_3_*` (`test_f11_fit.py`) | pass | Existing: the hold-out always includes the peak month, and a shifted split raises a documented warning |
| T11.1, T11.2 | `test_T11_1_*` (5), `test_T11_2_*` (2) | pass | Existing calibration fit recovers known multipliers within 5 percent; an unmapped activity goes to indirect with a warning |
| T11.4 | `test_T11_4_real_pilot_metrics_and_note` (`test_f11_calibrate_e2e.py:80`) | not_applicable | Skipped by its own mark: needs the real pilot data and the domain expert |
| L5 | `test_L5_too_long_out_dir_is_exit_2_naming_the_path` (`test_f10_cli_r8b.py`) | pass | A 300-character `out_dir` component is exit 2 and the error names the path |
| L5 | `test_L5_find_canonical_wraps_a_filesystem_error_as_config_error`, `test_L5_find_canonical_still_returns_none_without_earlier_runs`, `test_L5_a_key_file_that_cannot_be_read_is_a_config_error` (`test_f8_r8b_runner.py`) | pass | `find_canonical` wraps `OSError` as `ConfigError`; no earlier run still returns `None`; an unreadable key file is a `ConfigError` |
| T6.1, T6.2, T6.3, T6.10 | `test_T6_1_*` (4), `test_T6_2_*` (4), `test_T6_3_*` (4), `test_T6_10_*` (1) (`tests/golden/test_f6_*`) | pass | Existing storage, throughput, labor, area and queue golden values; unchanged by R8b |
| T6.5, T6.7, T6.8, T6.9, T6.11 | `test_T6_5_*` (3), `test_T6_7_*` (3), `test_T6_8_*` (3), `test_T6_9_*` (3), `test_T6_11_*` (4) | pass | Existing property, determinism and trace-coverage checks of the engine |
| T6.6 | `tests/property/test_f6_labor_properties.py` | not run here | Outside this test set. The round 1 spec auditor saw it pass in a whole-suite run; this record has no fresh run of it |
| T7.1 | `test_T7_1_*` (3) (`tests/golden/test_f7_golden.py`) | pass | Existing finance golden values; unchanged |
| T8.1 to T8.6 | `test_T8_1_*` (7), `T8_2` (4), `T8_3` (7), `T8_4` (6), `T8_5` (1), `T8_6` (1) | pass | Existing runner, comparison, tornado, break-even and speed checks |
| T10.2 | `test_T10_2_run_all_reuses_canonical_when_hashes_match` | pass | Existing: canonical reuse by log assertion |
| T1.5 and the G1 set | `tests/golden/test_g1_*` (77 passed in 8 files; `test_T1_5_*` 69 of them) | pass | The golden values did not change: Param counts and the oracle, parity and register checks all pass with the new catalog scalar |

Counts from the `PASSED` lines of the fresh run: 726 passed, of which 323 have a `test_T<n>_<m>_` name. Per T-id: T6.4 21, T10.1 42, T10.3 44, T10.4 63, T11.3 18, T11.1 5, T11.2 2, T1.5 69, T6.1 4, T6.2 4, T6.3 4, T6.5 3, T6.7 3, T6.8 3, T6.9 3, T6.10 1, T6.11 4, T7.1 3, T8.1 7, T8.2 4, T8.3 7, T8.4 6, T8.5 1, T8.6 1, T10.2 1. R8b files: `test_f10_cli_r8b.py` 11, `test_f8_r8b_runner.py` 12, `test_f10_calibrate_swap.py` 5.

## Proofs

Every proof below was captured by the auditors during the audit rounds (scratch scripts and runs in the scratchpad `audit_R8b/`); none was re-executed for this record, except where it says so. Some output excerpts were clipped in the audit data and are reproduced as given.

1. M5 / I85 (b): 50 order lines of quantity 1e12 stop in about 3 s with exit 4 under `--strict`, sensitivity on (before the fix: a 41 s scenarios stage without sensitivity, minutes with it). Captured in round 0.
   Command: `cd /Users/skarwech/saas_v1 && WHSIZING_SALT=audit-salt /usr/bin/time -p .venv/bin/whsizing run-all $S/outl/project.yaml --strict --formats xlsx; echo exit=$?` (S = the scratchpad `audit_R8b`; project = 243-day synthetic site, clipped in the audit data).
   Output excerpt: `error: strict: not computed: S0, S1, S2 (see .../outl/runs/2026-11-10T00-58-28_2c9017); S0: SizingInfeasibleError: S0 (manual_p2p): forklifts = 263,327,479 exceeds engine.max_equipment_count (100,000); check units and outliers (R13)` / `real 2.83` / `exit=4`.

2. The defect that round 0 found and round 1 fixed: the same data without `--strict`. Round 0 (before the fix): exit 0 in 5.23 s, a comparison table with S0, S1, S2 all 'not computed', and `report_en.pdf` plus `report_en.xlsx` written. Round 1 (after the fix): exit 4 in 2.97 s, no report, folder still a complete run.
   Command (round 1): `WHSIZING_SALT=auditsalt uv run whsizing run-all $S/r2_outl/project.yaml --formats both --lang en` (strict false, sensitivity on, 50 added lines with quantity 1000000000000), then `ls run/report run/logs`.
   Output excerpt (round 1): `exit=4 (2.97 s total)` / `error: no scenario computed: not computed: S0, S1, S2 (see .../r2_outl/runs/2026-11-10T01-22-16_28704a); S0: SizingInfeasibleError: S0 (manual_p2p): forklifts = 263,327,479 exceeds engine.max_equipment_count (100,000); check units and outliers (R13)` / `report/ : (empty)   logs/: run.log only (no FAILED)   state.is_run(run) = True`.

3. The guard covers the staged path too, and a partial failure is unchanged. Captured in round 1.
   Command: `uv run whsizing size $RUN --basis basis/example_basis.yaml --scenarios scenarios/example_scenarios.yaml --catalog catalog ; uv run whsizing rerun $RUN`
   Output excerpt: `size exit=4 (2.55 s total): error: no scenario computed: not computed: S0, S1, S2 (see .../r2_staged/2026-11-10T01-24-48_7207ae); ...` / `rerun exit=4: error: no scenario computed: ... (new folder 2026-11-10T01-22-47_bd11b9)`. The partial case is covered by the unit test `test_T10_3_one_scenario_not_computed_without_strict_still_exits_0` (S0 computed, S1 and S2 not computed, no raise).

4. M4 / I86: a failed recalibration leaves `calibration/` untouched and names the user's own file; without `--force` it is refused; `--force` with `--observed-peak-lines-h` replaces it and reports the peak error. Captured in round 0, and the failed-recalibration part re-captured in round 1.
   Command (round 0): `whsizing calibrate RUN --actuals act/actuals_bad.csv --activity-map act/activity_map.yaml --force`, then `calibrate` good with `--force --observed-peak-lines-h 420`; checksum of `find calibration -type f` before and after.
   Output excerpt: without `--force`: `error: .../calibration: the run is already calibrated and runs are immutable; --force replaces it`. Bad file with `--force`: `exit=3`, `error: .../act/actuals_bad.csv: line 2: hours 'abc' is not a number`, snapshot before `dbb4e0d5bcd7` and after the bad run `dbb4e0d5bcd7`, no `.calibration-*` left. Good file with `--force` and peak: `exit=0`, `peak lines/h: model 12, observed 420, error -97.1 %`, `holdout.json` `peak_lines_h_observed 420.0`, snapshot now `faedc57dbbb8`. Round 1 repeat: `bad actuals --force: exit=3 'line 2: hours 'abc' is not a number'; 'calibration/ byte-identical'; ls -a run | grep -c '^.calibration' -> 0`.

5. Round 0 findings 2 and 4 (non-finite observed peak, directory mode) fixed. Captured in round 1.
   Command: `whsizing calibrate RUN --actuals A --activity-map M --force --observed-peak-lines-h=<v>` for v in nan inf -inf 0 -3 1e999; a first calibration with 20; `ls -ld calibration dq canonical`; `grep peak_lines calibration/holdout.json`.
   Output excerpt: nan, inf, -inf, 0, -3 and 1e999 all give `exit=2` with `error: observed_peak_lines_h must be a positive number, got nan` (and inf, -inf, 0.0, -3.0, inf). Valid 20: `peak lines/h: model 12, observed 20, error -38.2 %`, `holdout.json` `"peak_lines_h_observed": 20.0`, `"peak_lines_h_error_pct": -38.22574139724456`. Modes: `drwxr-xr-x calibration; drwxr-xr-x dq; drwxr-xr-x canonical; drwxr-xr-x calibration/plots`.

6. Round 0 finding 3 (non-atomic swap loses both calibrations) fixed: a failure in the swap restores the earlier one. Captured in round 1; the round 0 reproduction of the defect was `raised: [Errno 5] simulated rename failure` / `old calibration exists: False | scratch left: []`.
   Command (round 1): `uv run python $S/loss2.py` (`Path.rename` patched to fail on the scratch-to-out step).
   Output excerpt: `A scratch->out fails: raised OSError ... calibration/fit.json: OLD | stray: []`. The same script showed the residual nit of round 1 finding 6: case D (`KeyboardInterrupt` in `shutil.rmtree`) left `fit.json = NEW` and a stray `.calibration-old-992ead75`.

7. Failed-run marker and SIGTERM: a real `whsizing run-all` killed with SIGTERM during the sensitivity stage exits 143, writes `logs/FAILED`, logs `run_failed` once, and the Streamlit discovery refuses the folder. A DQ-blocking run (tiny_golden, exit 3) is marked too; an exit-4 complete run is not. Captured in round 0 and re-confirmed in round 1.
   Command: `.venv/bin/whsizing run-all $S/clean/project_sens.yaml --formats xlsx --lang en & ... kill -TERM $PID; wait $PID; echo exit=$?; cat $RUN2/logs/FAILED; uv run python isrun.py runs2`
   Output excerpt: `exit=143` / `{"error_type": "Terminated", "reason": "terminated by signal 15 (SIGTERM)"}` / `run_failed count: 1; stderr 'error: terminated by signal 15 (SIGTERM)'` / `is_run: False list_runs: []`. tiny_golden `run-all`: `exit=3`, `logs/FAILED = {"error_type": "DataQualityError", "reason": "1 blocking data-quality issue(s): R9 ..."}`. Round 1: `is_run: terminated False, exit-4 complete run True, clean run True`.

8. L5 and CLI errors: a 300-character `out_dir` component is exit 2 on `run-all`, `ingest --out-dir` and `rerun --out-dir`; a corrupt, truncated or binary `trace.jsonl` is one error line naming file and line; round 1 added the missing-trace case. Captured in rounds 0 and 1.
   Command: `whsizing run-all project_long.yaml; whsizing ingest ... --out-dir $LONG; whsizing rerun RUN --out-dir $LONG`; edit `S1/trace.jsonl` line 3, then `whsizing compare RUN` / `whsizing report RUN`; `rm scenarios/S1/trace.jsonl; whsizing compare RUN`.
   Output excerpt: `run-all long out_dir exit=2; ingest long exit=2; rerun long out-dir exit=2`; `error: .../scenarios/S1/trace.jsonl: line 3: invalid trace node (label: Field required)` (compare and report, exit 2, one error line); truncated: `... line 3: invalid trace node (Invalid JSON: EOF while parsing an object at line 1 column 5)`; binary: `... cannot read the trace (utf-8 codec can't decode byte 0xff ...)` exit 2. Round 1, missing trace: `compare (missing trace): exit=2 'error: .../scenarios/S1/trace.jsonl: not found (run `whsizing size`)'`.

9. The numbers: Erlang-C, W_q and P(W>t) equal closed forms and a hand computation; the bound is enforced at its boundary; golden counts did not move. Captured in rounds 0 and 1.
   Command: `uv run python $S/erlang.py` and `$S/erl.py`; `run-all` on a clean site, then `grep -ho 'F_LOW_CONFIDENCE:[0-9]*' scenarios/S*/result.json`; `python -c 'len(load_catalog("catalog").constants)'`.
   Output excerpt: `c=1 a=0.5 -> 0.5; c=2 a=1 -> 0.33333333333333337 (expect 1/3); c=10 a=8 -> 0.4091801507964436 (closed form 0.4091801507964435); W_q 0.20459007539822 (expect 0.20459007539822174); P(W>1h) 0.0553765116 (expect 0.0553765116)`; `a=c -> stable False, c_min 4 (ceil(3)+1); a=3.2 -> c_min 5`; `c=100000 ok in 3.6 ms, c=100001 -> SizingInfeasibleError 'exceeds the bound 100,000 (engine.max_equipment_count); check units and outliers (R13)'`; `F_LOW_CONFIDENCE:30 / :49 / :50 (I47 unchanged); constants 72 (was 71)`.

10. Gates run when this record was written (fresh, not an auditor capture): `uv run ruff check` on the R8b source and test files gave `All checks passed!`; `uv run ruff format --check` gave `32 files already formatted`; `uv run pyright src/whsizing/engine src/whsizing/scenarios/runner.py src/whsizing/cli src/whsizing/app/state.py src/whsizing/calibration src/whsizing/catalog/models.py` gave `0 errors, 0 warnings, 0 informations`.

## Audit rounds

Each round had a spec audit and a "proof" audit. The "proof" audit record of each round carries only the verdict `pass_with_issues` and the test counts (703 in round 0, 726 in round 1); it has no findings, T-ids or proofs, so nothing more can be reported from it. The build stage reported 703 passed and 1 skipped for the R8b test command. The fix round that followed round 0 left the count at net 23 more passing tests (726 minus 703; one exit-0 test was replaced by an exit-4 one). No fix round follows round 1 in the audit history.

### Round 0 (build as delivered): spec audit pass_with_issues, 703 passed, 0 failed

Severity count: 0 high, 1 medium, 7 low. The auditor marked T6.4, T10.1, T10.2, T10.3, T10.4, T11.1, T11.2, T11.3 and L5 as pass and T11.4 as not applicable; its hand computation of the Erlang-C values agreed with the code.

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | medium | M5 without `--strict`: a 1e12-quantity run no longer takes minutes, but exits 0 and builds a full PDF/XLSX report in which every scenario is not computed; FINAL.md item 6 and I85 (b) say the run must stop with `SizingInfeasibleError` (exit 4). Disclosed by the engineer as a deliberate choice. | Fixed. `_strict_check` in `runner.py` now raises exit 4 also without `--strict` when every scenario is not computed, after everything is written (folder stays a complete run, no report is built). Covers `run-all`, `rerun` and `size`. A partial failure is unchanged (exit 0). This departs from the literal 'Only in --strict' of spec 2.7 row 4 for the zero-computed case. Verified live in round 1 (proofs 2 and 3) |
| 2 | low | `--observed-peak-lines-h nan` and `inf` accepted (exit 0); `holdout.json` stored null while the console printed `observed inf, error +nan %`. | Fixed. The guard is `not (math.isfinite(obs) and obs > 0)`, a `ConfigError` (exit 2). Verified in round 1 (proof 5) |
| 3 | low | The swap in `_calibrate_into` is not atomic: `rmtree(out)` then rename; a failure between them deletes both the earlier and the new calibration. | Fixed. The old folder is renamed aside, the scratch is renamed in, the old one is then removed; on any `BaseException` the old one is renamed back. Verified in round 1 (proof 6) |
| 4 | low | `calibration/` created through `tempfile.mkdtemp` is mode 0700 while sibling run folders are 0755. | Fixed. The scratch folder is made with `Path.mkdir` under a `secrets.token_hex` name, so the umask applies. Verified in round 1 (proof 5) |
| 5 | low | A missing `scenarios/<id>/trace.jsonl` ends as 'unexpected FileNotFoundError', exit 1; an empty `trace.jsonl` is accepted silently. | Partly fixed. `check_traces` now checks the trace beside every `scenarios/*/result.json` and a missing file is a `ConfigError` (exit 2). An empty trace is not rejected, because a not-computed stub legitimately has one. Re-audited in round 1 (finding 3 there) |
| 6 | low | New behaviour is not registered or documented: the `logs/FAILED` marker, exit 143, the `.calibration-XXXX` staging, the runbook (`--force`, `--observed-peak-lines-h`, refusal to overwrite), '71 structural constants' (now 72), the `catalog/CHANGELOG.md` entry. | Deferred. All of it lives in `docs/INTERPRETATIONS.md`, `docs/runbook.md`, `docs/methodology` and `catalog/CHANGELOG.md`, outside the R8b paths. Listed as blockers with the exact text needed. Still open in round 1 |
| 7 | low | FINAL.md item 6 also asked to 'log progress in long stages'; there is no progress logging in `src`. | Deferred. The cause of the minutes-long stage is removed (every Erlang-C loop is bounded) and the runner already logs `scenario_done` or `scenario_not_computed` per scenario with stage timers; the 784 s sensitivity sweep lives in `scenarios/sensitivity.py` (F8b, not an R8b path). Still open in round 1 |
| 8 | low | After the swap, the returned `CalibrationResult` still names the removed scratch folder. | Fixed. `_calibrate_into` returns the result with `out_dir` and each `files` path re-based to `out`. Verified in round 1 (proof 6, 'control swap' and case C) |

### Round 1 (after the fix round): spec audit pass_with_issues, 726 passed, 0 failed

Severity count: 0 high, 0 medium, 6 low. The auditor marked T6.1 to T6.11, T8.1 to T8.6, T10.1 to T10.4 and T11.1 to T11.3 as pass and T11.4 as not applicable (L5, having no spec id, is not in its T-id list; its tests pass in the fresh run). Round 0 findings 1, 2, 3, 4 and 8 were confirmed fixed with live runs or scratch scripts. No fix round followed, so every finding below stays open.

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | low | Round 0 finding 6 is not resolved: the register and docs still contradict the code. `INTERPRETATIONS.md` I75 (f), I85 (b) and spec 2.7 row 4 say exit 4 is strict-only while `_strict_check` also raises without `--strict` when nothing is computed; the `run_scenarios` docstring (`runner.py:145-148`) omits this non-strict raise; `logs/FAILED`, exit 143 and the staging are in no register or doc; runbook lines 370 and 520 still say '71 structural constants'; `catalog/CHANGELOG.md` has no `max_equipment_count` line. | Open (deferred, outside the owned paths). Re-checked while writing this record: still true (see "Open issues" 1) |
| 2 | low | Round 0 finding 7 is not resolved: no progress logging for long stages. The cause of the M5 stage is removed (1e12 run ends in 2.9 s), so the residual risk is a large sensitivity sweep (F8b, not owned). | Open (deferred) |
| 3 | low | Round 0 finding 5 is only partly resolved: a missing trace is exit 2, but an empty `trace.jsonl` of a COMPUTED scenario is accepted by `compare` with sensitivity (exit 0, sensitivity runs on an empty tracer), and `report` only catches it later as exit 5 (`IC1 ... trace node S1.labor.total.heads (hi) does not exist ... and 364 more`). `check_traces` could read the status and reject an empty trace of a computed scenario. | Open |
| 4 | low | `calibrate` into a run folder that is not writable ends as 'unexpected PermissionError', exit 1, instead of a `ConfigError` exit 2 as `run-all` gives; `scratch.mkdir()` runs before the `try` block. Evidence: `chmod a-w r2_ro` then `calibrate` gave `exit=1 'error: unexpected PermissionError: [Errno 13] Permission denied: .../r2_ro/.calibration-eb91ce48'`. | Open |
| 5 | low | After `run-all` stops with exit 4 because no scenario was computed, the explicit staged commands still build output from that run: `compare` and `report` exit 0 and write a PDF whose rows are all 'not computed'. This matches the F10 exit table but is the same all-stubs report that M5 complained about. | Open |
| 6 | low | Swap nit: an interrupt that lands in the cleanup of the old folder (after `scratch.rename(out)` succeeded) leaves the NEW calibration intact but a stray `.calibration-old-<hex>` folder in the run. Not data loss. | Open |

## Open issues

None is high or medium. Items 1 to 6 are the six open findings of audit round 1; items 7 to 12 are further notes from the build and fix records and from this record's own checks.

1. [low] Register, runbook and catalog changelog not updated (outside the R8b paths; needs an integrator). Checked in the files while writing this record: `docs/INTERPRETATIONS.md` has no entry for `logs/FAILED`, exit 143, the strict message tail, or the `.calibration-<hex>` staging with the aside swap; I75 (f) still reads 'strict mode raises exit 4 ... when a scenario is not computed or none fits' and spec `description.md:426` (2.7 row 4) still reads 'Only in `--strict`', while the code raises exit 4 without `--strict` when no scenario is computed (the one place where behaviour departs from the literal spec wording). `docs/runbook.md` lines 370 and 520 say '71 structural constants' (the code has 72 constants), and it has no mention of `--force`, `--observed-peak-lines-h`, `logs/FAILED` or exit 143. `catalog/CHANGELOG.md` has no line for the new scalar; suggested text: 'engine_defaults.yaml: max_equipment_count 100000 [P] (I85 b), a scalar plausibility bound on any sized equipment count'. Suggested register text: I85 (b) gains 'without `--strict`, a run in which NO scenario is computed also raises exit 4 after everything is written; a partial failure stays a not-computed row with exit 0'; I75 (h) or I78 gains the marker (a JSON line `{error_type, reason}` skipped by `app/state.py` `is_run`; strict exit 4 is not marked) and the SIGTERM handler (`Terminated`, exit 128 + signal, main thread only); I86 gains the staging and aside swap. Also: the `W_UNMAPPED_ACTIVITY` flag message in `fit.json` now carries the user's actuals file name instead of the always-`actuals.csv` copy name.
2. [low] No progress logging in long stages (FINAL.md item 6, second half). The sensitivity sweep is F8b's (`scenarios/sensitivity.py`).
3. [low] An empty `trace.jsonl` of a computed scenario is still accepted by `compare` (exit 0) and only fails in `report` with exit 5. The library path (`report/data.py` of F9, which wraps pydantic's whole dump in 'report: cannot read the trace ...', and `Tracer.load_jsonl` of F0, which lets a raw `ValidationError` through) and the Streamlit app are unchanged: R8b added only a CLI-side pre-check (`cli/_runio.py` `check_trace` and `check_traces`, called by `report` and by `compare` through `load_evaluated`).
4. [low] `calibrate` into an unwritable run folder is exit 1 ('unexpected PermissionError'), not exit 2.
5. [low] `compare` and `report` on a run that stopped with exit 4 (nothing computed) still build all-stubs output and exit 0.
6. [low] A stray `.calibration-old-<hex>` folder can remain after an interrupt during the removal of the old calibration (the new calibration is intact).
7. [scope] The plausibility bound is not applied to docks (`area._dock`): they were not in the task's resource list and they do not feed any loop. Pickers, forklifts, ports, robots, `gtp_stations`, pods and pack stations are bounded.
8. [scope] A failed run gets no 'failed' tag in the Streamlit run list; it is simply not listed or opened (the task allowed either). Staged commands other than `run-all` and `rerun` (`size`, `ingest`) get no `logs/FAILED` marker on SIGTERM because they do not go through the runner failure path; a killed new staged `ingest` still drops its folder as before.
9. [scope] Files outside the R8b paths that the build had to touch: `src/whsizing/catalog/models.py` (new `EngineDefaults.max_equipment_count: float = 100_000`, with a default so older run folders still load), `tests/unit/test_f5_loader.py` (constants count 71 to 72) and `docs/assumptions.md` (regenerated by `python -m whsizing.catalog.assumptions catalog docs/assumptions.md`, which `test_docs_assumptions_md_is_regenerated` requires). The default of `MAX_SERVERS` duplicates the catalog scalar; a test pins the two together.
10. [info] F9 blocker reported at build time: the whole non-bench suite then showed 13 failed and 75 errors, all in `tests/unit/test_f9_pdf.py`, `tests/unit/test_f9_pdf_many.py` and `tests/e2e/test_f9_pdf_e2e.py` (jinja2 `UndefinedError 'assumptions_notes'`), caused by another engineer's in-progress PDF template work, not by R8b. It was not reproduced when this record was written: a probe run of those three files gave `59 passed` and `54 passed` (113 passed, 0 failed, run with `-p no:cacheprovider`). That probe is outside the R8b test set and the whole suite was not re-run, so the blocker is reported as not reproduced, not as closed.
11. [info] `tests/unit/test_f9_annex_a.py:114` (F9) has an E501 line and is not ruff-formatted, as reported by the engineer; not touched by R8b.
12. [info] The e2e timing assertion `seconds < 90` in `test_T6_4_outlier_quantities_stop_in_seconds_with_exit_4_under_strict` is loose; the 2.83 s to 2.97 s figures are audit measurements, not asserted by the test.

## Not applicable here and why

- Real client data and domain-expert acceptance: `tests/e2e/test_f11_calibrate_e2e.py` T11.4 (`test_T11_4_real_pilot_metrics_and_note`) is skipped by its own mark (needs the real pilot data and manual acceptance by the expert). The `calibrate` behaviour changed by R8b (M4, I86) was proven on synthetic data only (the generated 243-day site, `ecom_mid`).
- Docker: the Docker test of `tests/unit/test_f0_report.py` is a pre-existing skip in the whole suite (Docker not installed); it is not in this test set.
- GitHub CI: no CI run exists for this tree (no commits); everything ran locally with `uv run`.
- Real client-scale hostile input: the 1e12 outlier cases used a 243-day synthetic site with 50 added lines, not a client dataset.
- Streamlit by hand: the app change (`is_run` refusing a failed run) is covered by unit tests and by a live Python call on really killed runs; no one clicked through the Streamlit UI.
- `bench` marker tests (C5 performance budgets) are not in this test set.
- T6.6 (`tests/property/test_f6_labor_properties.py`) is outside this test set (see the table).

## Fresh test run

Command (run from `/Users/skarwech/saas_v1` when this record was written, 2026-11-10; output saved to the scratchpad file `r8b_pytest.txt`):

```
uv run pytest tests/unit/test_f6_*.py tests/unit/test_f8_*.py tests/unit/test_f10_*.py tests/unit/test_f11_*.py tests/e2e/test_f6_*.py tests/e2e/test_f8_*.py tests/e2e/test_f10_cli*.py tests/e2e/test_f11_*.py tests/golden/test_f6_*.py tests/golden/test_f7_golden.py tests/golden/test_g1_*.py -q -rA
```

Result: exit 0, `726 passed, 1 skipped in 265.65s (0:04:25)`. The output has 726 `PASSED` lines, 1 `SKIPPED` line and no `FAILED`, `ERROR`, `XFAIL` or `XPASS` line. The round 1 audit run also had 726 passed.

Trimmed output (progress lines, the two timing lines the tests print, the R8b `PASSED` lines and the summary):

```
........................................................................ [  9%]
...
F8b tiny_golden tornado (7 parameters x 2 scenarios x 2 runs): 0.91 s
...
F6 e2e ecom_mid: F1+F2 4.2 s, F3+F4 1.0 s, F6 x3 0.4 s, total 5.6 s
  981,910 shipped lines, design day 3393 lines
...
=========================== short test summary info ============================
PASSED tests/unit/test_f6_queue.py::test_T6_4_erlang_c_values
PASSED tests/unit/test_f6_queue.py::test_T6_4_erlang_c_rejects_c_above_the_bound
PASSED tests/unit/test_f6_queue.py::test_T6_4_queue_resource_passes_the_bound_to_erlang_c
PASSED tests/unit/test_f6_queue.py::test_T6_4_default_bound_is_the_catalog_scalar
PASSED tests/unit/test_f6_queue.py::test_T6_4_a_catalog_copy_without_the_bound_still_loads_with_the_default
PASSED tests/unit/test_f6_area.py::test_T6_4_pack_stations_above_the_bound_are_infeasible
PASSED tests/unit/test_f6_throughput.py::test_T6_4_infinite_load_is_reported_not_an_overflow
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_a_failing_stage_writes_the_marker_and_the_app_skips_the_folder
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_an_ingest_failure_or_an_interrupt_marks_the_run_too[error0-MappingError]
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_an_ingest_failure_or_an_interrupt_marks_the_run_too[error1-KeyboardInterrupt]
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_exit_4_strict_is_a_complete_run_not_a_failed_one
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_no_scenario_computed_is_exit_4_even_without_strict
PASSED tests/unit/test_f8_r8b_runner.py::test_T10_3_one_scenario_not_computed_without_strict_still_exits_0
PASSED tests/unit/test_f8_r8b_runner.py::test_L5_find_canonical_wraps_a_filesystem_error_as_config_error
PASSED tests/unit/test_f10_app_state.py::test_T10_4_a_failed_run_is_neither_listed_nor_opened
PASSED tests/unit/test_f10_calibrate_swap.py::test_T10_3_a_failure_while_swapping_keeps_the_earlier_calibration
PASSED tests/unit/test_f10_calibrate_swap.py::test_T10_3_a_failing_calibrate_keeps_the_earlier_one_and_removes_the_scratch
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_calibrate_failed_recalibration_leaves_the_earlier_one_untouched
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_calibrate_with_force_replaces_and_reports_the_observed_peak
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_calibrate_first_failed_calibration_creates_no_calibration_folder
PASSED tests/e2e/test_f10_cli_r8b.py::test_T6_4_outlier_quantities_stop_in_seconds_with_exit_4_under_strict
PASSED tests/e2e/test_f10_cli_r8b.py::test_T6_4_outlier_quantities_without_strict_stop_with_exit_4_and_no_report
PASSED tests/e2e/test_f10_cli_r8b.py::test_L5_too_long_out_dir_is_exit_2_naming_the_path
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_sigterm_during_sizing_marks_the_run_failed_and_exits_143
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_corrupt_trace_is_a_one_line_error_naming_file_and_line[report]
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_corrupt_trace_is_a_one_line_error_naming_file_and_line[compare]
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_missing_trace_is_a_one_line_config_error_not_an_unexpected_one[report]
PASSED tests/e2e/test_f10_cli_r8b.py::test_T10_3_missing_trace_is_a_one_line_config_error_not_an_unexpected_one[compare]
PASSED tests/golden/test_g1_sync.py::test_T1_5_cube_building_works_add_floor_prep_on_the_grid
PASSED tests/golden/test_g1_sync.py::test_T1_5_oracle_param_ids_and_values_match_the_catalog
PASSED tests/golden/test_g1_sync.py::test_T1_5_share_stock_cube_is_zero_without_stock
SKIPPED [1] tests/e2e/test_f11_calibrate_e2e.py:80: T11.4 needs the real pilot data (12 months of order lines and monthly hours per activity); manual acceptance by the domain expert (review #2)
726 passed, 1 skipped in 265.65s (0:04:25)
```

Passed per file (counted from the `PASSED` lines, parametrised cases one by one): `tests/e2e/test_f10_cli_e2e.py` 37, `test_f10_cli_r8b.py` 11, `test_f11_calibrate_e2e.py` 1, `test_f6_size_e2e.py` 1, `test_f8_runner_e2e.py` 5, `test_f8_sens_e2e.py` 4; `tests/golden/test_f6_*` 13 (area 3, labor 4, size 4, storage 2), `test_f7_golden.py` 3, `test_g1_*` 77; `tests/unit/test_f10_*` 149 (app_calls 12, app_drilldown 6, app_form 13, app_hygiene 35, app_results 14, app_state 16, app_static 10, calibrate_swap 5, cli 38), `test_f11_*` 110, `test_f6_*` 124, `test_f8_*` 191.

Gates re-run now on the R8b paths: `uv run ruff check` gave `All checks passed!`; `uv run ruff format --check` gave `32 files already formatted`; `uv run pyright` on the R8b source paths gave `0 errors, 0 warnings, 0 informations`. Informational probe outside the test set: `uv run pytest tests/unit/test_f9_pdf.py -q -x -p no:cacheprovider` gave `59 passed in 75.42s`, and `tests/unit/test_f9_pdf_many.py tests/e2e/test_f9_pdf_e2e.py` gave `54 passed in 141.20s`.
