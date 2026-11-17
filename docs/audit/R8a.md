# R8a audit record: ingestion date bound, derived-inbound guard, header and salt hygiene

Feature: final-audit fixes M2 (R1 implausible early dates, I83), L4 (derived inbound below zero, I85 a) and the low list (duplicate column headers, salt file hygiene) from docs/audit/FINAL.md.
Owned paths: src/whsizing/io/**, src/whsizing/design/**, tests/unit/test_f2_*.py, tests/unit/test_f4_*.py, tests/e2e/test_f2_*.py, tests/fixtures/ingest/**.
Spec read: description.md section 4.1 (R1-R14), F4 inbound, C2 data protection; INTERPRETATIONS I83, I85, I12, I56.

## Final verdict: pass_with_issues

All 350 tests of the R8a test files pass in a fresh run (0 failed, 0 skipped), ruff and pyright are clean on the R8a paths, and the two headline fixes (M2 stray early dates, L4 negative derived inbound) were reproduced before the fix and proven through the real CLI after it.
The verdict is not "pass" because the last audit round (round 2) left three medium findings with no fix round after it: the R1 gap rule still lets a junk date cluster above 5 % of the distinct dates through, it can drop a real early block and exit 3, and register I83 still describes the removed percentile rule.

## Fresh test run (this record)

Command, run from /Users/skarwech/saas_v1:

```
uv run pytest tests/unit/test_f2_*.py tests/unit/test_f4_*.py tests/e2e/test_f2_*.py \
  tests/golden/test_f3_golden.py tests/golden/test_f4_golden.py -q -rA
```

Result line: `350 passed in 20.37s`. The `-rA` summary has 350 `PASSED` lines and no `FAILED`, `SKIPPED`, `ERROR` or `XFAIL` line.

Tests per spec id in this run (counted from the `PASSED` lines):

```
T1.4 1 | T2.1 15 | T2.2 14 | T2.3 23 | T2.4 20 | T2.5 3 | T2.6 38 | T2.7 11 | T2.8 3 | T2.9 9
T3.1 3 | T4.1 1 | T4.2 1 | T4.3 2 | T4.4 3 | T4.5 2 | T4.6 2        (= 151)
other tests in the same files without a T-id prefix (f2 mapping/r6/sniff/headers/anonymize,
  f4 register and design, e2e ingest)                                 (= 199)
```

Trimmed `-rA` lines for the tests R8a added or changed:

```
PASSED tests/unit/test_f2_rules.py::test_T2_6_clean_file_has_no_r1_hit_and_keeps_its_message
PASSED tests/unit/test_f2_rules.py::test_T2_6_stray_epoch_line_is_an_r1_hit_and_cannot_stretch_the_history
PASSED tests/unit/test_f2_rules.py::test_T2_6_r1_cuts_only_at_a_gap_of_more_than_90_days
PASSED tests/unit/test_f2_rules.py::test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[4]
PASSED tests/unit/test_f2_rules.py::test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[12]
PASSED tests/unit/test_f2_rules.py::test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[30]
PASSED tests/unit/test_f2_rules.py::test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[45]
PASSED tests/unit/test_f2_rules.py::test_T2_6_several_junk_dates_on_a_short_file_are_shed_in_turn
PASSED tests/unit/test_f2_rules.py::test_T2_6_junk_dates_within_90_days_of_each_other_are_all_dropped
PASSED tests/unit/test_f2_rules.py::test_T2_6_a_dense_cluster_of_junk_dates_is_dropped_whatever_its_own_spread
PASSED tests/unit/test_f2_rules.py::test_T2_6_a_real_early_season_before_a_long_closure_is_not_junk
PASSED tests/unit/test_f2_rules.py::test_T2_6_slow_launch_ramp_is_not_an_implausible_early_start
PASSED tests/unit/test_f2_rules.py::test_T2_6_r1_with_no_usable_date_does_not_crash
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_one_stray_1970_line_on_a_31_day_file_still_exits_3_through_r9
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_thirty_stray_1970_lines_on_a_31_day_file_block_through_r1_and_r9
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_two_stray_dates_within_90_days_of_each_other_still_exit_3_through_r9
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_clean_synthetic_files_have_no_r1_hit[b2b_cases]
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_clean_synthetic_files_have_no_r1_hit[ecom_mid]
PASSED tests/e2e/test_f2_ingest.py::test_T2_6_clean_file_has_no_r1_hit_and_keeps_every_line
PASSED tests/unit/test_f4_design.py::test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock
PASSED tests/unit/test_f4_design.py::test_T4_4_derived_inbound_below_zero_is_a_data_quality_error
PASSED tests/unit/test_f4_design.py::test_T4_4_mild_destock_keeps_a_positive_derived_inbound
PASSED tests/unit/test_f2_headers.py::test_dupheader_two_quantity_columns_with_different_values_give_a_note
PASSED tests/unit/test_f2_headers.py::test_dupheader_identical_duplicate_columns_stay_silent
PASSED tests/unit/test_f2_headers.py::test_dupheader_semicolon_file_and_padded_header_names_are_compared_after_stripping
PASSED tests/unit/test_f2_headers.py::test_dupheader_names_differing_only_by_case_are_one_name
PASSED tests/unit/test_f2_headers.py::test_dupheader_note_only_when_the_first_is_mapped_and_the_second_is_not
PASSED tests/unit/test_f2_headers.py::test_dupheader_excel_repeated_header[False]
PASSED tests/unit/test_f2_headers.py::test_dupheader_excel_repeated_header[True]
PASSED tests/e2e/test_f2_ingest.py::test_dupheader_repeated_quantity_header_lands_in_the_dq_report_notes
PASSED tests/unit/test_f2_anonymize.py::test_salt_file_readable_by_group_or_world_is_accepted_with_a_warning
PASSED tests/unit/test_f2_anonymize.py::test_salt_short_is_accepted_with_a_warning_that_never_prints_it
PASSED tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet
PASSED tests/golden/test_f4_golden.py::test_T4_1_design_day_and_inbound_equal_golden_spreadsheet
350 passed in 20.37s
```

Fresh static checks on the R8a paths (read-only, no `--fix`), also run for this record:

```
uv run ruff check <io, design, f2/f4 unit tests, e2e f2 tests, fixtures/ingest>   -> All checks passed!
uv run ruff format --check <same python paths>                                     -> 26 files already formatted
uv run pyright <same python paths>                                                 -> 0 errors, 0 warnings, 0 informations
```

No new dependency was needed. Nothing was committed. pyproject.toml, uv.lock, tests/golden and other features' files were not touched. `schema_changes`: none (`RawTable.duplicate_headers` is a defaulted dataclass field in `io/readers.py`, not a `whsizing.schemas` model).

## T-id table

Status comes from the fresh run above. The "what it proves" column comes from the spec audits (rounds 0 to 2) and the build record.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T1.4 | test_T1_4_fr_csv_reingests_with_zero_blocking_issues | pass | A clean FR ecom_mid CSV re-ingests with zero blocking issues and rows_out == rows_in, so the new R1 bound drops nothing from a clean file. |
| T2.1 | test_T2_1_encoding_and_delimiter_detection (15 tests) | pass | Encoding and delimiter sniffing, including utf16/utf32 and cp1252 coercion. Unchanged by R8a. |
| T2.2 | test_T2_2_header_on_row_3_csv and Excel variants (14 tests) | pass | Header row found on row 3 (CSV) and rows 2-5 (Excel). Unchanged by R8a. |
| T2.3 | test_T2_3_decimal_comma_with_thousand_dots (23 tests) | pass | Decimal comma and thousand separators are read correctly. |
| T2.4 | test_T2_4_each_date_format (20 tests) | pass | Every supported date format parses. |
| T2.5 | test_T2_5_mapping_accuracy_on_fr_synthetic_csv (3 tests) | pass | Column mapping accuracy on the French synthetic CSV. |
| T2.6 | test_T2_6_each_rule_triggers_on_its_fixture and 37 more (38 tests) | pass | Each rule R1-R14 triggers on its fixture. The R1 additions (listed individually below) prove M2: a stray early line (or thirty, or a dense cluster) becomes an R1 hit, cannot stretch the history, and R9 equals the clean run. Open residuals in "Open issues". |
| T2.6 (M2, unit) | test_T2_6_stray_epoch_line_is_an_r1_hit_and_cannot_stretch_the_history | pass | One 1970-01-01 line: R1 count 1, 'dated before' message, R9/R10/R12 severities and R9 message equal the clean base run. |
| T2.6 (M2, unit) | test_T2_6_r1_cuts_only_at_a_gap_of_more_than_90_days | pass | Gap boundary: 60 days before is kept, 91 and 150 days before are dropped. |
| T2.6 (M2, unit) | test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[4,12,30,45] | pass | Many lines on one junk date are all dropped (distinct-date logic, not line percentile). |
| T2.6 (M2, unit) | test_T2_6_several_junk_dates_on_a_short_file_are_shed_in_turn | pass | 1970, 1900 and 1980 junk dates are shed one after the other (fixed-point recompute). |
| T2.6 (M2, unit) | test_T2_6_junk_dates_within_90_days_of_each_other_are_all_dropped | pass | 1969-12-31 plus 1970-01-01 are dropped together. Was RED before the round 2 fix (0 != 2). |
| T2.6 (M2, unit) | test_T2_6_a_dense_cluster_of_junk_dates_is_dropped_whatever_its_own_spread | pass | A dense junk cluster up to the cap is dropped. Was RED before the fix (0 != 30). The auditor notes the cluster above 5 % is not covered (open issue). |
| T2.6 (M2, unit) | test_T2_6_a_real_early_season_before_a_long_closure_is_not_junk | pass | A real early block above 5 % of the distinct dates before a long closure is kept. The block of 5 % or less is not tested (open issue). |
| T2.6 (M2, unit) | test_T2_6_slow_launch_ramp_is_not_an_implausible_early_start | pass | A slow launch ramp is not trimmed. Fails on the earlier line-percentile code. |
| T2.6 (M2, unit) | test_T2_6_clean_file_has_no_r1_hit_and_keeps_its_message | pass | Clean base fixture: R1 ok, count 0, unchanged message, same row count. |
| T2.6 (M2, unit) | test_T2_6_r1_with_no_usable_date_does_not_crash | pass | All-null order_ts gives no bound, R1 and R9 blocking, no crash. |
| T2.6 (M2, e2e) | test_T2_6_one_stray_1970_line_on_a_31_day_file_still_exits_3_through_r9 | pass | tiny_golden csv_en plus one 1970 line gives DataQualityError exit 3 with blocking == ['R9'] (1.02 months); R1 warning count 1 and the manifest dropped_by_rule R1 == 1. Before the fix: exit 0, DQ 100, 662.97 months. |
| T2.6 (M2, e2e) | test_T2_6_thirty_stray_1970_lines_on_a_31_day_file_block_through_r1_and_r9 | pass | 30 stray lines (1.5 %) give exit 3 with R1 and R9 blocking. |
| T2.6 (M2, e2e) | test_T2_6_two_stray_dates_within_90_days_of_each_other_still_exit_3_through_r9 | pass | The auditor's two-line repro (1969-12-31, 1970-01-01) exits 3, R1 count 2. |
| T2.6 (M2, e2e) | test_T2_6_clean_synthetic_files_have_no_r1_hit[b2b_cases, ecom_mid] and test_T2_6_clean_file_has_no_r1_hit_and_keeps_every_line | pass | Clean synthetic files have R1 ok and rows_out == rows_in. |
| T2.7 | test_T2_7_dq_score_formula (11 tests) | pass | DQ score formula, bands, report score. |
| T2.8 | test_T2_8_hash_is_stable_with_same_salt_and_differs_with_another (3 tests) | pass | Salted hash is stable with the same salt and differs with another; ids hashed consistently; description and customer dropped. |
| T2.9 | test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation (9 tests) | pass | Three messy files go to canonical with scripted confirmation; wall time 0.4-0.5 s against the 900 s budget; C5 ingest of 1,030,012 lines takes 3.2 s (audit measurement). |
| T3.1 | test_T3_1_profile_stats_equal_golden_spreadsheet (3 tests) | pass | Profile statistics equal the golden spreadsheet; dead stock and trend equal the oracle. |
| T4.1 | test_T4_1_design_day_and_inbound_equal_golden_spreadsheet | pass | Golden design day and derived inbound equal the spreadsheet; unchanged by the new guard. |
| T4.2 | test_T4_2_design_percentile_moves_lines_monotonically | pass | Design-day lines are monotone in the percentile and equal np.percentile times the growth factor at rel 1e-12. |
| T4.3 | test_T4_3_hourly_lines_sum_to_design_lines (2 tests) | pass | Sum of hourly lines equals design lines within 1e-6. |
| T4.4 | test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock | pass | Derived inbound equals outbound at zero growth and constant stock (original property). |
| T4.4 (L4) | test_T4_4_derived_inbound_below_zero_is_a_data_quality_error | pass | L4/I85 a: 3 snapshots with 10 rows of 1e12 units in the first one; derive_inbound and select_design_day raise DataQualityError (exit 3) naming the delta-stock term and its value. Fails with the guard disabled. |
| T4.4 (L4) | test_T4_4_mild_destock_keeps_a_positive_derived_inbound | pass | A mild decline (-252 units/year) leaves inbound positive and equal to base - 252/operating_days. |
| T4.5 | test_T4_5_assumptions_list_every_basis_field_exactly_once (2 tests) | pass | Assumptions list every basis field exactly once. |
| T4.6 | test_T4_6_basis_with_unknown_key_raises_config_error (2 tests) | pass | Unknown key in the basis YAML raises ConfigError. |
| none (low: duplicate headers) | test_dupheader_* (6 unit incl. Excel [False/True], 1 e2e) | pass | A repeated column header with different values gives one DQ note (file, column, first used, second ignored); identical copies are silent; names are compared stripped and case-insensitive; the note reaches dq_report.json and survives a later ingest into the same run folder. Not a spec T-id: renamed from test_T2_2_* in round 1 because spec T2.2 is "header on row 3". |
| none (low: salt hygiene) | test_salt_file_readable_by_group_or_world_is_accepted_with_a_warning, test_salt_short_is_accepted_with_a_warning_that_never_prints_it | pass | Salt file modes 0600/0400 are silent, 0640/0644 log `salt_file_permissions`; salt under 16 characters (file or $WHSIZING_SALT) logs `salt_too_short`; the salt is never logged; 16 characters is silent. Not a spec T-id: renamed from test_T2_8_* in round 1 because spec T2.8 is hash stability. The permission test is skipped only on Windows. |

## Proofs

All proofs below were captured by the auditors during the audit rounds (commands run in audit scratch directories, not in the repo). Some commands are abridged in the audit record and are shown as recorded. They are not re-run in this record; only the pytest and static checks above are fresh.

1. M2 through the real CLI, one stray line (round 0 audit).
   Claim: one 1970-01-01 line on the 31-day tiny_golden used to exit 0 (DQ 100, 662.97 months); it now exits 3 via R9. The before-fix figures were reproduced by the build engineer.
   Command: copy tests/golden/tiny_golden/csv_en, append `STRAY-1,1970-01-01T10:00:00+01:00,<sku>,1,B2C,shipped` to order_lines.csv, then `whsizing ingest --dataset sku_master --non-interactive ...` and `whsizing ingest --dataset order_lines --non-interactive --run <run> ...` (abridged in the record).
   Output: `error: 1 blocking data-quality issue(s): R9 (order_lines): history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed.  exit=3`

2. M2 with 30 stray lines, 1.5 % of the file (round 1 audit).
   Claim: the percentile-over-lines version (round 0) still exited 0 with a 663-month history; the distinct-date fix stops it.
   Command: tiny_golden csv_en plus 30 appended `STRAY-n,1970-01-01T10:00:00+01:00,...` lines; `whsizing ingest --dataset order_lines --non-interactive --run <run> ...`
   Output: `error: 2 blocking data-quality issue(s): R1 (order_lines): 0 lines without a readable date, 0 dated in the future, 30 dated before 2024-12-03 (implausible: more than 90 days before the bulk of the history); R9 (order_lines): history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed.  exit=3`
   Before the fix (round 0 audit): `30 stray lines: exit=0 | score 95.0 usable | R1 ok 0 | R9 ok 0 history 1970-01-01 -> 2025-03-31 (662.97 months)`.

3. M2 with two junk dates within 90 days of each other (round 2 audit).
   Claim: after the gap-rule fix, 1969-12-31 plus 1970-01-01 are shed together and the run exits 3 on the real 31-day history.
   Command: append `STRAY-1,1969-12-31T23:00:00+01:00,...` and `STRAY-2,1970-01-01T10:00:00+01:00,...` to tiny_golden order_lines.csv; staged `whsizing ingest` as in proof 1.
   Output: `error: 1 blocking data-quality issue(s): R9 (order_lines): history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed.  exit=3`

4. M2 does not damage a clean file; junk dates are R1 hits (round 2 audit).
   Claim: on a clean 200-day ecom_mid file, three junk dates (1969-12-31, 1970-01-01, 1900-01-01) are R1 hits and the history is unchanged; the clean file has no R1 hit. R1 sample rows carry hashed ids, not the raw `STRAY-n`.
   Command: `whsizing ingest --dataset order_lines --non-interactive --run <run> $S/ecom_stray/csv_en/order_lines.csv`, then read dq/dq_report.json rules R1 and R9.
   Output: `clean: R1 ok 0 | R9 ok 'history 2024-01-01 -> 2024-07-18 (6.57 months)' | score 80.0 usable. with 3 stray lines: R1 warning 3 '3 dated before 2024-01-01 (implausible: more than 90 days before the rest of the history)' | R9 ok 6.57 months | score 75.0 usable with caveats.`

5. Slow ramp and junk shapes through the rule function (round 1 audit).
   Claim: a slow launch ramp is not trimmed (earlier finding F2 resolved), and junk-date shapes on a clean 365-day file are all dropped.
   Command: `uv run python scratchpad/audit_R8a/edge_r1.py` (calls `whsizing.io.rules._r1` on synthetic frames).
   Output: `slow ramp 200dx5 then 165dx1000: sev=ok dropped=0 first_kept=2024-01-01 hist=11.99; 365d x100 + 20000 lines on 1970-01-01: blocking dropped=20000 first_kept=2024-01-01; 10 yearly junk dates: dropped=50 first_kept=2024-01-01`.
   Also on a realistic 130-day, 157,904-line file: 0.7 % junk gives R1 warning, exit 0, R9 identical to the clean run (4.27 months); 1.5 % junk gives R1 blocking, exit 3.

6. L4/I85 a through `run-all` and staged `size` (round 2 audit).
   Claim: a hostile 1e12-unit first inventory snapshot makes derived inbound negative; both `run-all` and the staged `size` exit 3 with a message naming the delta-stock term and no traceback. The unmodified dataset exits 0. Before the guard the staged flow exited 0 with negative FTE (round 2 audit wording).
   Command: `uv run whsizing run-all $S/inb_hostile.yaml --formats xlsx --lang en --non-interactive; echo exit=$?` (260-day ecom_mid, 10 inventory rows of 1000000000000 units, example_basis.yaml, inbound_mode derived), and `uv run whsizing size $R --basis basis/example_basis.yaml --scenarios scenarios/example_scenarios.yaml`.
   Output: `hostile exit=3 ... error: derived inbound is negative (-3.92896e+10 units/day): the delta-stock term is -9.90097e+12 units/year (-3.92896e+10 units/day over 252 operating days) against mean outbound x growth of 2299.25 units/day. Check the inventory snapshots (units, outlier quantities, stock-take dates) or set flows.inbound_mode to 'receipts'.` Control: `run-all exit 0`.

7. L4 boundary (round 0 and round 2 audits).
   Claim: exactly zero derived inbound is accepted (spec says "negative"); a value just below zero raises; just above is accepted.
   Command: `uv run python $S/zero_inbound.py` (derive_inbound on tiny_golden with growth_units_per_year = -(mean_out x gf) x days, scaled by (1+1e-9) and (1-1e-9)); round 2: delta giving exactly +1, 0 and -1 unit/day.
   Output: `exact: OK units/day= 0.0 pallets 0.0 flags [] | just below: DataQualityError derived inbound is negative (-1.25502e-07 units/day) | just above: OK units/day= 1.255e-07`; round 2: `exact -1 unit/day above zero -> units/day=1`, `exactly zero -> units/day=0`, `-1 unit/day below zero -> DataQualityError exit=3`.

8. Duplicate headers and salt hygiene through the CLI (round 2 audit).
   Claim: a repeated differing `Quantity` column leaves a DQ note naming file, column and the ignored second column; a mode-644 short salt file warns without printing the salt; empty, whitespace-only, in-repo and missing salts are refused with exit 2 and a clear message; the salt text never reaches the run folder.
   Command: order_lines.csv with a second `Quantity` column of doubled values, `whsizing ingest --dataset order_lines --non-interactive --run <run> dup_order_lines.csv`, then read dq_report.json notes; `whsizing ingest --dataset sku_master --non-interactive --salt-file salt_short.txt ...` with mode 644 (abridged in the record).
   Output: `notes: "[order_lines] dup_order_lines.csv, column 'Quantity' appears twice with different values: the first is used, the second (column 7, read as 'Quantity_duplicated_0') was ignored. Rename or remove one of them if the second is the right one."` Warnings: `salt_file_permissions expected=600 mode=644` and `salt_too_short length=6 minimum=16`; empty file: `error: salt file ... is empty` exit=2; whitespace env salt: `error: no anonymisation salt` exit=2; in-repo: `is inside a git repository; keep it o...` (clipped in the record). Round 1 also showed a 37-character mode-600 salt logs no `salt_*` warning, and a grep for the secret over the whole run folder found 0 files.

9. Mutation checks: the new tests fail when the fix is removed (round 1 audit).
   Claim: the R1 tests assert real properties.
   Command: `PYTHONPATH=scratchpad/audit_R8a/mut/{a,b} uv run pytest tests/unit/test_f2_rules.py tests/e2e/test_f2_ingest.py -k T2_6 -x` on a scratch copy of src.
   Output: `a (unique() removed): FAILED test_T2_6_many_stray_lines_on_one_junk_date_are_all_dropped[12] (0 != 12); b (single pass, no loop): FAILED test_T2_6_several_junk_dates_on_a_short_file_are_shed_in_turn (6 != 18)`. The build record also states the M2/L4 tests fail with the bound neutered or the guard disabled, and the round 2 fix recorded two tests RED before the gap rule (0 != 2 and 0 != 30).

## Audit rounds

Each round has one spec audit and one proof-audit entry; the proof-audit entries in the record carry only a verdict, a test count and empty lists, so all findings and proofs below come from the spec audits. Test counts: round 0 audit 336 passed, round 1 audit 344 passed, round 2 audit 350 passed (all 0 failed); fresh run in this record 350 passed. Verdict was pass_with_issues in every round. No fix round followed the round 2 audit.

### Round 0 audit of the build (336 passed, pass_with_issues)

| id | sev | finding | resolution (round 1 fix) |
|---|---|---|---|
| F1 | medium | I83 bound (0.5th percentile of lines, minus 90 days): once 0.5 % or more of lines carry the junk date, nothing is dropped and ingest exits 0 with a 663-month history (30 lines on 1970-01-01 repro). | Reported fixed in round 1 (percentile over distinct dates, recomputed until stable). The round 1 audit found it only partly closed: see round 1 below. |
| F2 | low | A slow launch ramp has its early lines dropped as implausible; I83 "no clean dataset is affected" not true. | Fixed as a side effect of the distinct-date change. Pinned by test_T2_6_slow_launch_ramp_is_not_an_implausible_early_start. Round 1 audit confirmed resolved (proof 5). |
| F3 | low | A stray date inside the 90-day margin is kept and still stretches the history. | Deferred, by design: the 90-day margin is the [P] value of I83. Still open after round 2 (see Open issues). |
| F4 | low | R1 title text stale ('not in the future'). | Fixed in `io/dq.py` RULE_TEXT['R1']. Report-side `dq.rule.R1` (en.yaml:357, fr.yaml:357, report feature) is outside R8a and not fixed: deferred, still open. |
| F5 | low | Duplicate-header detection compares exact names only ('Quantity' vs 'quantity' silent). | Fixed: names are keyed by strip + casefold; test_dupheader_names_differing_only_by_case_are_one_name. Confirmed in the round 1 audit (proof 8). |
| F6 | low | Test labels loose: duplicate-header tests named test_T2_2_*, salt tests test_T2_8_*. | Fixed: renamed to test_dupheader_* and test_salt_*. Confirmed in the round 1 audit. |

### Round 1 audit (344 passed, pass_with_issues)

| id | sev | finding | resolution (round 2 fix) |
|---|---|---|---|
| 1 | medium | F1 only partly closed: two stray lines on two distinct junk dates within 90 days of each other (or a dense junk cluster) still give exit 0 with a 663-month history; the 2nd-earliest-date bound sheds only one junk date. | Fixed: bound replaced by a gap rule (among the earliest max(3, 5 %) distinct dates, the last gap of more than 90 days splits junk from history; recomputed until stable). RED tests before the fix (0 != 2, 0 != 30). Confirmed in the round 2 audit (proof 3). The unbounded median-run variant was rejected because it would drop a real early season before a long closure and block with exit 3. |
| 2 | medium | Register I83 no longer matches the code (percentile of lines in the register, distinct dates and fixed point in the code). | Deferred: docs/ is outside R8a paths. Replacement text for I83 was supplied in the round 2 fix's blockers. Still unresolved after round 2. |
| 3 | low | `dq.rule.R1` in report/i18n (en, fr) still says 'not in the future'. | Deferred: owned by the report feature (F9). Target strings supplied. Still unresolved after round 2. |
| 4 | low | A stray date within 90 days before the first date is kept (same as F3). | Deferred by design (pinned by test_T2_6_r1_cuts_only_at_a_gap_of_more_than_90_days). |

L4 (derived-inbound guard) had no finding in any round. The round 2 fix only recorded it as a regression check (not rebuilt, its test still passes), and the auditors exercised it through the CLI in rounds 0, 1 and 2 (proofs 6 and 7).

### Round 2 audit (350 passed, pass_with_issues): findings left open

| id | sev | finding | status |
|---|---|---|---|
| 1 | medium | Register I83 (docs/INTERPRETATIONS.md:823-829) still describes the removed rule ("0.5th percentile of the local order dates minus 90 days", "No clean dataset is affected"); the new [P] constants R1_EARLY_MAX_DATE_SHARE 0.05 and R1_EARLY_MIN_DATES 3 are registered nowhere. | Open. Re-checked for this record: the register text is unchanged. |
| 2 | medium | The M2 symptom still reproduces when the junk cluster exceeds 5 % of the distinct dates: 12 consecutive junk dates (1970-01-01 to 12) on a 200-day file give ingest exit 0, R1 ok, R9 'history 1970-01-01 -> 2024-07-18 (654.55 months)', R12 ok (vacuous), period_start 1970-01-01 and seasonality confidence L -> H. | Open. Documented ceiling in a `ponytail:` comment in `_earliest_plausible` (upgrade path: a per-client history_start input). |
| 3 | medium | The gap rule drops a real early block of up to 5 % of the distinct dates followed by a closure of more than 90 days; R1 turns blocking when that block holds more than 1 % of lines, so a genuine file exits 3 with no override. Repro through `_r1`: 12 days x 400 lines, closed to 2024-04-01, then 300 days x 100 lines -> 4800 of 34800 dropped, blocking. The 5 % share is an unregistered [P] and the false-positive side below the cap is pinned by no test. | Open. |
| 4 | low | `dq.rule.R1` in en.yaml:357 and fr.yaml:357 unchanged (report feature, outside R8a); the PDF/Excel DQ rule table shows the old text. | Open. Re-checked for this record: both lines unchanged. |
| 5 | low | A stray date within 90 days before the first date is kept (90 exact kept, 91 dropped). | Open, by design. |
| 6 | low | Salt warnings are not recorded where a reviewer reads them: SALT_MIN_CHARS = 16 is an unregistered [P]; neither the register nor docs/runbook.md mentions the warnings or the minimum. | Open. Re-checked: docs/runbook.md still has no mention. Behaviour itself works (proof 8). |
| 7 | low | tests/unit/test_f4_register.py is 810 lines (800 max). Carried over from FINAL.md 6.2. | Open. Re-checked: still 810 lines. |

## Open issues

1. R1 gap-rule residual, false negative (round 2 finding 2, medium): a junk date cluster above 5 % of the distinct dates and isolated by more than 90 days is taken for a real earlier period; ingest exits 0 with a multi-hundred-month history, R9/R10/R12 pass. Mitigation noted in code: `history_start` input per client.
2. R1 gap-rule residual, false positive (round 2 finding 3, medium): a real early block of up to 5 % of the distinct dates before a closure of more than 90 days is dropped, and above 1 % of lines R1 blocks the dataset (exit 3). Needs a registered [P] review of the 5 % share and a test for the below-cap case.
3. Register I83 is stale relative to the code (medium). Replacement text was supplied by the round 2 fix; docs/INTERPRETATIONS.md is outside R8a paths. The two new [P] constants (0.05, 3) and SALT_MIN_CHARS = 16 need registering.
4. Report-side R1 title (`dq.rule.R1`) in src/whsizing/report/i18n/en.yaml:357 and fr.yaml:357 still reads 'not in the future' only, while io/dq.py says 'not implausibly early'. Suggested EN: "Order dates readable, not in the future and not implausibly early". Suggested FR: "Dates de commande lisibles, non futures et non aberrantes (trop anciennes)".
5. Stray date within 90 days before the first date is kept and stretches the history (by design, I83 margin). Only the R9 message and R12 show it.
6. docs/runbook.md does not mention the new salt warnings (`salt_too_short`, `salt_file_permissions`) or the duplicate-header DQ note.
7. tests/unit/test_f4_register.py is 810 lines, above the 800 maximum.
8. The L4 guard is tested at function level only (derive_inbound, select_design_day); the exit code 3 through the CLI was verified by hand by the auditors (proof 6), not by a test.
9. Duplicate-header and salt tests carry no spec T-id (spec T2.2 and T2.8 describe other properties); coverage exists but is not mapped to a T-id.
10. Outside R8a paths, reported by the build engineer at build time and not re-run for this record: ruff errors in tests/e2e/test_f10_cli_r8b.py (another engineer's in-flight file; none in R8a files); 4 failures in tests/unit/test_f9_pdf_many.py (report layout, right margin with many scenarios); two F10 tests (test_T10_4_an_upload_larger_than_memory_suggests_the_cli and test_T9_4_corrupt_trace_..._[compare]) that failed in a full run but passed alone while other engineers were editing. New salt warnings now fire in any test using a short salt or default-umask salt file (F10 tests use 'f10-unit-salt' and a 9-character 'tiny-salt'); no test asserting exact stderr was found.

## Not applicable here and why

- Real client data: none exists in this environment. All R1/R9/R12 behaviour is proven on synthetic profiles (ecom_mid, b2b_cases at 120-260 days) and tiny_golden. Whether sparse real exports have no gap of more than 90 days among their earliest dates is unverified.
- Domain-expert review: the [P] values introduced or kept here (90-day margin, 5 % date share, 3-date minimum, 16-character salt minimum) have not been reviewed by a domain expert; they are not yet in the register (see open issue 3).
- Docker and GitHub CI: not exercised by R8a; no R8a test needs them. No test in the R8a files is skipped in this run.
- Windows: the salt file permission test skips only on Windows; this run is on macOS (Darwin), so the Windows path was not exercised.
- Report rendering (PDF, Excel, HTML i18n of the R1 title): outside R8a paths; the dq_report.html shows the new `RULE_TEXT['R1']` title, but the report-side i18n table does not (open issue 4).
- Benchmarks: the C5 1.03 M-line ingest time (3.1-3.2 s) comes from the build and audit measurements, not from the fresh pytest run above.
