# R8c: final-audit fixes (Annex A values, pint units, snapshots, bench markers, app hygiene)

## 1. Verdict

**pass_with_issues**

1. The mandated test command re-run for this record gives 840 passed, 1 skipped (Docker, not applicable here), 0 failed. Every R8c finding from `docs/audit/FINAL.md` (M3, M6, L1, L6 and the low-list items) has a passing test, and the round 2 auditor confirmed the fixes live.
2. The round 2 audit still lists one medium and four low findings with no fix recorded after it. I re-ran the medium one while writing this record and it still reproduces: `units.is_unit('lines/0')` raises `ZeroDivisionError` instead of returning False, so a catalog unit like that would crash `validate-catalog` with exit 1 instead of a `ConfigError`. No real catalog Param is affected. This is why the verdict is not `pass`.

Scope: I87 (pint units), I88 (Annex A per-scenario values), M6 (syrupy snapshots), L1 (five C5 bench budgets), T5.3 (no silent skips), app and PDF hygiene. Nothing is committed; no revision id exists.

## 2. Tests

Fresh run, done for this record (section 7). Status values come from that run unless the cell says "audit".

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| M3 / I88 | `tests/unit/test_f9_tables.py::test_I88_every_annex_a_value_equals_the_params_snapshot_of_the_scenario_it_is_quoted_for` | pass | The table model's base column equals `snapshot[pid]`; the `override.S1` cell equals `snapshot['S1:pid']` (230 vs 250); the cell is empty when the scenario does not override. |
| M3 / I88 | `tests/unit/test_f9_pdf.py::test_I88_annex_a_prints_the_value_each_scenario_was_sized_with[fr,en]` | pass | PDF text: 72 parameter lines, each starts with the snapshot base value and ends with the S1 override value; S1 header and the scenario-columns note are on the page. |
| M3 / I88 | `tests/unit/test_f9_excel.py::test_I88_assumptions_sheet_carries_the_value_each_scenario_used[fr,en]` | pass | xlsx Assumptions: column C is the snapshot, the S1 column is `S1:<id>` or empty, the note row is present, the autofilter covers the new column. |
| M3 / I88 | `tests/unit/test_f9_annex_a.py::test_I88_each_scenario_column_holds_the_values_of_that_scenario_only` | pass | Several scenarios, two overrides in one scenario and one Param overridden by two scenarios: each scenario column holds exactly its own value or EMPTY on all 72 rows (added in round 1). |
| M3 / I88 | `tests/unit/test_f9_annex_a.py::test_I88_a_param_overridden_by_a_scenario_has_the_origin_the_table_note_names` | pass | A Param overridden by both the client basis and a scenario has origin Override, as the table note says (added in round 1, failed on the old precedence). |
| M3 / I88 | `tests/unit/test_f9_annex_a.py::test_I88_the_pdf_annex_puts_each_value_under_the_header_of_its_scenario` | pass | The PDF grid view puts each value under the header of its own scenario for all 72 lines. Tested at grid level, not on rendered coordinates (auditor note). |
| L6 / I87 | `tests/unit/test_f5_units.py::test_I87_*` (28 tests in the run) and `test_R8c_m3_and_FTE_are_aliases_of_meter_cubed_and_fte` | pass, weak | All units written in `catalog/**/*.yaml` and all 72 loaded Params parse in the pint registry; unknown or malformed units are rejected; `Param` and the loader name the id and unit. Weak: `is_unit` does not catch `ZeroDivisionError` or `TypeError` for `lines/0`, `1/0`, `m ** m`, and no test covers those (round 2 finding, open). |
| M6a | `tests/e2e/test_snapshots.py::test_golden_layer_typical_world_of_tiny_golden_matches_its_snapshot` | pass | 664 typ-world S0/S2 trace nodes through `size_scenario` and `compute_finance`, 6 significant digits, match the syrupy snapshot. Auditors showed that a one-value catalog change fails it. |
| M6a | `tests/e2e/test_snapshots.py::test_e2e_layer_ecom_mid_comparison_json_matches_its_snapshot` | pass | ecom_mid `comparison.json` (synthesize, then run_scenarios with the example scenarios, salt pinned by the fixture) matches its snapshot. Marked slow, runs in the CI test job. |
| M6a | `tests/e2e/test_snapshots.py::test_rounded_is_stable_under_float_noise` | pass | Rounding to 6 significant digits and noise below 1e-9 to 0.0 keeps the snapshot stable. |
| M6b | `tests/unit/test_f0_tooling.py::test_R8c_golden_update_regenerates_the_syrupy_snapshots_after_a_confirmation` | pass | `just golden-update` runs `pytest tests/e2e/test_snapshots.py --snapshot-update` behind the `[confirm]` prompt; the comment points at `build_golden` for `golden_values.json`. |
| L1 / M6c | `tests/unit/test_f0_tooling.py::test_R8c_just_bench_and_the_ci_bench_job_collect_all_five_c5_budgets` | pass | `pytest -m bench` collects all five C5 tests. I re-ran the collection at write time and it lists the same five. |
| T3.8 / T8.5 / T9.7 | `test_T3_8_one_million_lines_profiled_under_60_s`, `test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds`, `test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds`, `test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together` | pass (audit, bench run); the T9.7 pdf test also passed in the fresh run | The budgets pass under `-m bench` (5 passed in 48 to 49 s in rounds 0 and 1). The bench run itself was not repeated for this record. |
| T5.3 | `tests/unit/test_f5_eligibility.py::test_T5_3_golden_eligibility_shares` | pass | The three in-body `pytest.skip` branches are now assertions with a reason, so a missing golden file fails instead of skipping. |
| L-css / control characters | `tests/unit/test_f9_pdf.py::test_R8c_css_string_has_no_raw_newline_so_the_margin_text_survives[4]`, `..._a_client_name_with_a_cr_keeps_the_running_header_on_every_page` | pass | CR, FF, LF, quotes and angle brackets in the running header survive. Failed on the old `_css_str` (3 failures). |
| L-control characters | `tests/unit/test_f9_pdf.py::test_R8c_a_control_character_in_the_client_or_site_name_is_a_space_in_the_whole_report[7]`, `..._in_a_scenario_name_keeps_the_text_layer_of_every_page[6]`, `..._bidi_overrides_in_the_client_name_are_dropped_and_the_formulas_keep_their_lines` | pass | Control, line-separator and bidi characters in client, site and scenario names never reach the PDF text layer; Appendix C formulas keep their line breaks. With the `_finalize` hook stubbed, all 6 scenario-name cases fail (round 2 auditor). |
| L-run-param | `tests/unit/test_f10_app_hygiene.py::test_R8c_the_run_parameter_*`, `..._every_page_starts_through_the_guarded_setup`; `tests/e2e/test_f10_app_url.py::test_R8c_a_run_parameter_outside_the_runs_root_is_not_opened[7 pages]`, `..._a_relative_path_*`, `..._a_run_name_under_the_runs_root_is_still_opened`, `..._the_file_system_refuses_is_dropped_not_a_traceback[7 pages x 3 refs]` | pass | A `?run=` value that is not a bare run folder name under the runs root is dropped on all 7 entry pages, including a 300-character name and a NUL; a valid name still opens. Fails without the guard (8 failures in round 0; 7 page cases in round 1). |
| L-upload | `tests/unit/test_f10_app_hygiene.py::test_R8c_save_upload_*`, `..._the_cli_hint_quotes_every_file_name_for_the_shell`, `..._the_typed_path_field_says_it_is_for_local_use[fr,en]`; `tests/e2e/test_f10_app_pages.py::test_R8c_the_cli_hint_for_an_upload_with_a_quote_in_its_name_is_one_shell_word`; `tests/e2e/test_f10_app_url.py::test_R8c_a_typed_path_longer_than_a_file_name_is_an_error_message`, `..._an_uploaded_file_with_a_very_long_name_is_saved_and_read` | pass | Empty, dot and NUL names get a default name, long names are cut and keep their extension, the CLI hint is one shell word per file name, a too-long typed path is an error message, not a traceback. |
| T9.1 to T9.7 | `tests/unit/test_f9_*`, `tests/property/test_f9_*`, `tests/e2e/test_f9_*` (T9_1: 7, T9_2: 33, T9_3: 6, T9_4: 25, T9_5: 31, T9_6: 35, T9_7: 3 tests) | pass | F9 regression: sheets and headers, summary equals `comparison.json`, 12 to 18 pages on the example run, IC1 to IC8 each fail on a tampered fixture, FR and EN numbers identical, layout area equals zone sum, T9.7 time budgets. |
| T0.1 to T0.5 | `tests/unit/test_f0_*` (T0_1: 5, T0_2: 2, T0_3: 60, T0_4: 1, T0_5: 1 tests) | pass | CI has the six stages, the justfile has every recipe, ruff and pyright gates pass (`test_T0_1_lint_and_typecheck_gates_pass`), schemas round-trip, `Param` rejects min > typ, mock result renders a one-page PDF. |
| T5.1 to T5.5 | `tests/unit/test_f5_*` (T5_1: 25, T5_2: 1, T5_3: 1, T5_4: 3, T5_5: 36 tests) | pass | Catalog loader, eligibility and end-of-life inference still hold with the new unit check. |
| Docker | `tests/unit/test_f0_report.py:28` | skipped, not_applicable | Docker is not installed (pre-existing skip). |

## 3. Proofs

All proofs below were captured by the auditors during the audit, not by this record. Output excerpts are the visible text of the audit data; where it was clipped I say "excerpt".

1. **M3 closed on a real end-to-end run (round 0).** Command: `uv run whsizing run-all <scratch>/project.yaml` (ecom_mid synth, example basis and scenarios, FR and EN), then pypdf and openpyxl on the run's `report/` folder. Output excerpt: manifest has base `250.0` and `'S1:amr_gtp.station_rate_lines_h': 230.0`. EN p13: `amr_gtp.station_rate_lines_h 250 lines/h 150 250 350 TODO L Override 230`; FR: `... Surcharge 230`. xlsx row `('amr_gtp.station_rate_lines_h', 'station rate lines h', 250, 'lines/h', 150, 250, 350, 'TODO', 'L', '', 'Override', '', 230)`, filter `A4:M76`.
2. **I88 holds for many scenarios (rounds 0 and 1).** A 5-scenario run (S0 with two overrides, S1, S3, S4 with two overrides) compared the xlsx with `params_snapshot` on all 72 rows and every scenario column. Output: `mismatches 0`, EN and FR. A run with no overrides adds no column and no note (filter `A4:L76`, 16 pages). Round 1 also showed `manual_p2p.pick_rate_shelving_lines_h base 62 origin Override {S0: 55}`.
3. **The override is what the engine used (round 2).** Hand check from `S0/trace.jsonl`: workload 1253.877, hours 25.5335, pfd 0.12 give an implied rate of 55.0, which is the Annex A S0 value. Round 1 did the same for S1 against S4: 2.96083 x 230 = 681.0 and 2.83746 x 240 = 681.0 (same lambda, so S1 used 230).
4. **L6 / I87: a bad catalog unit is a clear ConfigError, all 72 real units load (rounds 0 and 1).** A catalog copy with `banana/h` gave `ConfigError ... labor_standards.yaml: activities.receipt_check.standard: Value error, labor.receipt_check: unit 'banana/h' is not a pint unit (see whsizing.units)`. The real catalog: 72 params, 15 distinct units, all parse. Round 1 also: `'m3' True, 'eur/m3' True, 'FTE' True, 'FTE/shift' True, 'banana' False, '' False`.
5. **M6: the snapshot catches drift and is not tautological (rounds 0 and 2).** Mutation in a scratch copy: `manual_p2p.pick_rate_shelving_lines_h` typ 70 to 71 gave `'S0.finance.cash_flow.y2': -89235.7 / - 'S0.finance.cash_flow.y2': -89292.6 ... 1 snapshot failed`; the unmutated copy gives `2 snapshots passed`. In round 2, 507 snapshot keys that also exist in `tests/golden/golden_values.json` agreed with the spreadsheet oracle at 1e-5 (mismatches 0).
6. **L1: five C5 budgets under the bench marker (rounds 0 to 2).** `uv run pytest --collect-only -q -m bench` lists ingest, T3.8, T8.5, sensitivity and T9.7. `uv run pytest -m bench -q --durations=6`: `5 passed, 1937 deselected in 48.42s` (ingest 2.9 s, T8.5 0.40 s, tornado 0.91 s, T9_7 2.33 s); round 1: `5 passed, 2007 deselected in 49.27s`.
7. **Control characters (round 2).** `run-all` with scenario names containing FF, NUL, U+2028, U+2029, U+202E and a client with FF, U+202E and U+2028: `exit=0 (23 s) | en pages 17 NUL-garbled pages: [] ... | fr pages 17 NUL-garbled pages: [] | cover 'Acme Corp SA · Lyon' | header on 16 of 16 pages after the cover`. Stubbing `whsizing.report.pdf._finalize` to identity makes all 6 scenario-name cases fail.
8. **Hostile `?run=` and upload names (round 1).** AppTest on Home.py and pages 1 to 6 with refs `'a'*300`, `'a'*5000`, NUL, `..`, `/etc`, `a/b`, `'é'*200`, FF: `BAD 0` (against a root holding 3 runs, a valid ref is kept). A 300-character typed path shows `st.error`, no traceback. 21 hostile upload names: `BAD 0`, all at most 200 bytes, extension kept.
9. **No regression (rounds 1 and 2).** Round 1 whole suite: `1949 passed, 2 skipped, 61 deselected in 448.91s`. Round 2 target set: 840 passed, 0 failed.
10. **A real defect the auditor found and nobody has fixed yet (round 2).** `uv run whsizing validate-catalog <copy>` with `finance_defaults.yaml` unit set to `lines/0`: `exit=1 | error: unexpected ZeroDivisionError: division by zero`. `Param(unit='m ** m')` raises a raw `TypeError`. Re-run by me at write time: `'lines/0' RAISED ZeroDivisionError`, `'1/0' RAISED ZeroDivisionError`, `'m ** m' RAISED TypeError`.

## 4. Audit rounds

Severity counts are the auditors' own. "Fixed" means the round's fix step reported a fix with a test; the next round's audit then confirmed or reopened it.

### Round 0 (spec audit: pass_with_issues, 783 passed, 0 failed). Findings: 1 medium, 7 low.

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | medium | `?run=` guard in `app/entry.py` still crashed every page on a ~300-character ref (`OSError` ENAMETOOLONG; traceback shows the server path). | Fixed in round 1: `safe_run_name` catches `OSError` and drops the ref. The same class on the typed-path field was fixed in `ingest_ui.collect_files`. Round 1 audit confirmed. |
| 2 | low | Param overridden by client and by a scenario showed origin Client, while the note says Override. | Fixed in round 1 (precedence override, then client, then default). Confirmed in round 1. |
| 3 | low | I88 tests covered only one scenario and one Param. | Fixed in round 1 (`tests/unit/test_f9_annex_a.py`, 3 tests). Confirmed. |
| 4 | low | A form feed in the client name still garbled the PDF text layer of the cover. | Marked fixed in round 1 for client and site only. Round 1 audit reopened it (see below); closed in round 2. |
| 5 | low | `m3` and `FTE` rejected as not pint units. | Fixed in round 1 (aliases in `units.py`). Confirmed. |
| 6 | low | `safe_upload_name` did not handle names over the file system limit. | Fixed in round 1 (cut at 200 bytes, extension kept). Confirmed. |
| 7 | low | T3.8, sensitivity and T9.7 moved to the bench marker, so they leave `just test` and the CI test job. | Rejected with reason: spec C3 puts the performance gate on `just bench`; `ci.yml` has a bench job running `pytest -m bench`; sensitivity JSON byte-identity is still asserted in `test_f8_sens_runner.py:68` and `test_f8_sens_e2e.py:136`. |
| 8 | low | `tests/e2e/test_f10_app_pages.py` was 924 lines (limit 800). | Fixed in round 1: split into `_pages` (719), `_profile` (190), `_support` (93); same test names before and after. |

### Round 1 (spec audit: pass_with_issues, 833 passed, 0 failed). Findings: 1 medium, 2 low.

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | medium | `printable()` covered only client and site; a form feed in a scenario name garbled every PDF page (19 of 19 EN, 20 of 20 FR). | Fixed in round 2: Jinja `finalize` hook in `pdf.py` runs every template expression through `printable()`. Confirmed in round 2. |
| 2 | low | `printable()` mapped only category Cc; U+2028 garbled the cover, U+2029 injected a break, U+202E reversed the name. | Fixed in round 2 (Zl, Zp and bidi controls handled). Confirmed in round 2. |
| 3 | low | `test_f10_cli_e2e.py` (827 lines) and `test_f4_register.py` (810 lines) exceed 800 lines. | Deferred: both files are outside R8c's paths. Still open. |

### Round 2 (spec audit: pass_with_issues, 840 passed, 0 failed). Findings: 1 medium, 4 low. No fix round followed.

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | medium | `units.is_unit()` catches only `PintError`, `ValueError`, `TokenError`; `lines/0`, `1/0`, `m ** m` escape as raw `ZeroDivisionError` or `TypeError` (no `ConfigError`, exit 1 instead of 2). | Open. Reproduced again at write time. |
| 2 | low | Some Unicode Cf characters (BMP U+0890, U+0891, U+FFF9 to U+FFFB; supplementary U+110BD, U+110CD, U+13430 to U+1343F, U+1BCA0 to U+1BCA3) still garble every PDF page when they appear in a scenario name. | Open. |
| 3 | low | Scenario names reach the Excel report unsanitised (`_x000C_` shows for FF, U+202E stays in the Summary cell). | Open. |
| 4 | low | A lone surrogate in a scenario name fails with a raw `PydanticSerializationError` after the scenarios stage (exit 1). | Open; auditor says outside R8c paths (`src/whsizing/scenarios`). |
| 5 | low | Two test files outside R8c's paths exceed 800 lines (same as round 1 finding 3). | Open (deferred in round 2). |

## 5. Open issues

1. **Medium, `src/whsizing/units.py:49`.** `is_unit()` lets `ZeroDivisionError` and `TypeError` escape for units such as `lines/0`, `1/0`, `m ** m`. A fix would add those two exception types to the `except` and a test for the three strings. No current catalog unit is affected. This is the item that keeps the verdict at pass_with_issues.
2. **Low, Cf characters in the PDF text layer** (round 2 finding 2): exotic code points in a scenario name still garble every page.
3. **Low, Excel scenario names unsanitised** (round 2 finding 3).
4. **Low, lone surrogate in a scenario name** (round 2 finding 4): outside R8c's paths, raw exit 1.
5. **Low, two test files over 800 lines** (`tests/e2e/test_f10_cli_e2e.py` 827, `tests/unit/test_f4_register.py` 810): outside R8c's paths.
6. **Blocker reported by the builder, outside R8c's paths:** `src/whsizing/app/state.py` `restore()` and `resolve_run()` still accept an absolute or relative path in `?run=`. The new `app/entry.py` guard drops such a value before `state.setup` runs on all 7 pages (pinned by a static test), so the pages are safe, but a direct caller of `state.restore` or `state.resolve_run` is not. The owner of `state.py` should restrict `resolve_run` itself. No later record shows this was done.
7. **Reported by the builder, outside R8c's paths:** `tests/e2e/test_f8_sens_e2e.py::test_ecom_mid_sensitivity_stage_takes_seconds` (60 s budget on ecom_mid) is slow but not bench; R8c marked the unit-level sensitivity test instead. The owner may add the bench marker.
8. **Not proven:** the snapshots do not prove salt independence (the fixture pins `WHSIZING_SALT`); the bench run was not repeated for this record; the ecom_mid-scale sensitivity e2e was never run under bench.
9. **Platform note:** the 400-byte `'é'` run reference does not trip ENAMETOOLONG on the APFS volume used here, so that case is only exercised for real on Linux.
10. **Consequence of the L1 fix:** T3.8, the sensitivity test (which carries a byte-identical JSON assertion) and the combined T9.7 are now excluded from `just test` and the CI test job (`-m "not bench"`) and run only under `just bench` and the CI bench job.
11. **Open from FINAL.md, not R8c scope:** definition-of-done items 6 and 8 (hold-out error on a real site, expert reviews).

## 6. Not applicable here, and why

- **Docker:** not installed. `tests/unit/test_f0_report.py:28` is skipped (1 skip in the fresh run).
- **Real client data:** none on this machine. `tests/e2e/test_f11_calibrate_e2e.py` (T11.4) is a pre-existing skip and is outside the test files of this feature.
- **GitHub CI:** not runnable here. The `ci.yml` bench and test jobs were read by the auditors and `test_R8c_just_bench_and_the_ci_bench_job_collect_all_five_c5_budgets` checks the marker wiring, but no CI run happened.
- **Domain-expert review:** not available. Nothing in R8c replaces expert reviews #1 and #2 of the definition of done.
- **Excel, LibreOffice and poppler:** not installed. The xlsx files were opened with openpyxl only; the effect of U+202E in an Excel cell was not tested in Excel (round 2 auditor note). PDFs were checked through pypdf and WeasyPrint.

## 7. Fresh test output

Run for this record from `/Users/skarwech/saas_v1`, with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (the WeasyPrint setting from the justfile):

```
uv run pytest tests/unit/test_f9_*.py tests/property/test_f9_*.py tests/e2e/test_f9_*.py \
  tests/unit/test_f10_app*.py tests/e2e/test_f10_app*.py tests/unit/test_f5_*.py \
  tests/unit/test_f0_*.py tests/e2e/test_snapshots*.py -q -rA
```

Result lines (the progress dots are all `.` except one `s` at about 94 %; 840 `PASSED` lines, 0 `FAILED`, 0 `ERROR`):

```
SKIPPED [1] tests/unit/test_f0_report.py:28: Docker not installed
840 passed, 1 skipped in 395.83s (0:06:35)
```

Passed tests per file:

```
  58 tests/e2e/test_f10_app_pages.py       35 tests/unit/test_f10_app_hygiene.py
   7 tests/e2e/test_f10_app_profile.py     14 tests/unit/test_f10_app_results.py
  32 tests/e2e/test_f10_app_url.py         16 tests/unit/test_f10_app_state.py
   5 tests/e2e/test_f9_core_e2e.py         10 tests/unit/test_f10_app_static.py
   9 tests/e2e/test_f9_excel_e2e.py        21 tests/unit/test_f5_eligibility.py
   4 tests/e2e/test_f9_pdf_e2e.py          69 tests/unit/test_f5_loader.py
   3 tests/e2e/test_snapshots.py           47 tests/unit/test_f5_paramset.py
   3 tests/property/test_f9_excel_properties.py   17 tests/unit/test_f5_r6.py
   8 tests/property/test_f9_formats.py     29 tests/unit/test_f5_units.py
   4 tests/property/test_f9_layout.py       3 tests/unit/test_f9_annex_a.py
   1 tests/property/test_f9_pdf_grid.py    32 tests/unit/test_f9_charts.py
   8 tests/unit/test_f0_cli.py             35 tests/unit/test_f9_diagram.py
   9 tests/unit/test_f0_config.py          50 tests/unit/test_f9_excel.py
   1 tests/unit/test_f0_report.py          15 tests/unit/test_f9_i18n.py
  69 tests/unit/test_f0_schemas.py          4 tests/unit/test_f9_i18n_pdf.py
   7 tests/unit/test_f0_tooling.py         25 tests/unit/test_f9_integrity.py
   5 tests/unit/test_f0_trace_logging.py   66 tests/unit/test_f9_pdf.py
  12 tests/unit/test_f10_app_calls.py      50 tests/unit/test_f9_pdf_many.py
   6 tests/unit/test_f10_app_drilldown.py  38 tests/unit/test_f9_tables.py
  13 tests/unit/test_f10_app_form.py
```

Selected PASSED lines from the same run:

```
PASSED tests/unit/test_f9_annex_a.py::test_I88_each_scenario_column_holds_the_values_of_that_scenario_only
PASSED tests/unit/test_f9_annex_a.py::test_I88_a_param_overridden_by_a_scenario_has_the_origin_the_table_note_names
PASSED tests/unit/test_f9_annex_a.py::test_I88_the_pdf_annex_puts_each_value_under_the_header_of_its_scenario
PASSED tests/unit/test_f9_excel.py::test_I88_assumptions_sheet_carries_the_value_each_scenario_used[en]
PASSED tests/unit/test_f9_excel.py::test_I88_assumptions_sheet_carries_the_value_each_scenario_used[fr]
PASSED tests/unit/test_f9_pdf.py::test_I88_annex_a_prints_the_value_each_scenario_was_sized_with[fr]
PASSED tests/unit/test_f9_pdf.py::test_I88_annex_a_prints_the_value_each_scenario_was_sized_with[en]
PASSED tests/unit/test_f9_tables.py::test_I88_every_annex_a_value_equals_the_params_snapshot_of_the_scenario_it_is_quoted_for
PASSED tests/unit/test_f5_units.py::test_I87_every_unit_written_in_the_catalog_files_parses
PASSED tests/unit/test_f5_units.py::test_I87_every_loaded_param_has_a_pint_unit
PASSED tests/unit/test_f5_units.py::test_I87_loader_rejects_a_bad_unit_with_the_id_and_the_unit
PASSED tests/unit/test_f5_units.py::test_R8c_m3_and_FTE_are_aliases_of_meter_cubed_and_fte
PASSED tests/unit/test_f0_tooling.py::test_R8c_just_bench_and_the_ci_bench_job_collect_all_five_c5_budgets
PASSED tests/unit/test_f0_tooling.py::test_R8c_golden_update_regenerates_the_syrupy_snapshots_after_a_confirmation
PASSED tests/unit/test_f5_eligibility.py::test_T5_3_golden_eligibility_shares
PASSED tests/e2e/test_f9_pdf_e2e.py::test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together
PASSED tests/e2e/test_snapshots.py::test_rounded_is_stable_under_float_noise
PASSED tests/e2e/test_snapshots.py::test_golden_layer_typical_world_of_tiny_golden_matches_its_snapshot
PASSED tests/e2e/test_snapshots.py::test_e2e_layer_ecom_mid_comparison_json_matches_its_snapshot
```

The full output (2811 lines) is at `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/R8c_run.txt`. The warnings in its captured stderr (`catalog_todo_sources count=72`, `salt_too_short length=12`) come from the test fixtures and do not fail any test.

Checks I ran at write time, outside the pytest run:

```
uv run pytest --collect-only -q -m bench
  tests/e2e/test_f2_ingest.py::test_C5_bench_ingest_and_validate_1m_line_csv
  tests/e2e/test_f8_runner_e2e.py::test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds
  tests/e2e/test_f9_pdf_e2e.py::test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together
  tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s
  tests/unit/test_f8_sens_oat.py::test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds

uv run python -c "from whsizing.units import is_unit; ..."
  'lines/0'  RAISED ZeroDivisionError division by zero
  '1/0'      RAISED ZeroDivisionError division by zero
  'm ** m'   RAISED TypeError unsupported operand type(s) for ** or pow(): 'int' and 'ParserHelper'
  'm3' True   'FTE' True   'banana/h' False
```

Dependencies: pint 0.26.2 and syrupy were already installed. `pyproject.toml`, `uv.lock` and `catalog/**/*.yaml` were not changed, so `catalog_version` is unchanged. Schema changes: no new field or model; `Param` gained a unit check in its after-validator, and the `assumptions` report table gained one column per overriding scenario plus the note key `assumptions.scenario_columns` (FR and EN).
