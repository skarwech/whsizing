# F2c audit: Ingestion remediation (W2 round-1 open findings)

## Verdict: pass_with_issues

All F2 acceptance tests (T2.1 to T2.9), the C5 benchmark and a test for each of the ten W2 findings (F2c-1 to F2c-10) pass: 121 passed, 0 failed and 0 skipped. Mutation checks show that the tests catch the bugs they target.
The verdict stays below `pass` because two low findings from round 1 are still open and no fix round followed. One is a regression caused by the round-1 dotted-date fix (a date-range preamble row is now taken as the header). The other is the spec's verbatim decimal regex, which needs a [VERIFY] decision. Both round-1 auditors returned pass_with_issues.

Schema changes: none (`schema_changes: []`). F2c owns `src/whsizing/io/**`, `src/whsizing/schemas/ingest.py`, `tests/fixtures/ingest/**`, `tests/unit/test_f2_*.py` and `tests/e2e/test_f2_*.py`. ruff check, ruff format and pyright were reported clean on these paths.

## Acceptance tests

Test ids F2c-1 to F2c-10 are the ten W2 round-1 open findings. T2.x are the F2 spec tests (description.md l.700), and C5 is the §4.1 ingest benchmark. The test names are the current ones from the fresh run below.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| F2c-1 | `tests/unit/test_f2_sniff.py::test_T2_3_french_integers_with_dot_thousands_in_a_file_without_decimals` | pass | An FR file with integers only sniffs `.`. Then `1.234` becomes null and is counted, and is never read as 1234. With `decimal: ','` in the mapping it reads 1234. The old `int_decimal` heuristic fails this test. |
| F2c-1 | `test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma` | pass | With 4 decimal columns and 1 grouped-integer column, the file sniffs `,` and `1.000` reads 1000. A file with 2 grouped columns out of 4 sniffs `.`, because one share is computed for the whole file, not per column. The 80 % threshold is pinned: the mutant `DECIMAL_MIN_SHARE=0.5` fails this test. |
| F2c-1 | `test_T2_3_a_mark_that_is_not_a_thousands_grouping_gives_null` | pass | Plain integers are ignored in the share. 2 of 2 separator values match, so the file sniffs `,` and `0,25` reads 0.25. |
| F2c-1 | `test_T2_3_dotted_codes_do_not_veto_a_french_decimal_comma` | pass | The dot veto is gone: 80 matching values out of 100 gives `,`. |
| F2c-1 | `tests/unit/test_f2_mapping.py::test_T2_3_number_notes_count_whole_values_shaped_like_thousands` | pass | Added in round 1 for round-0 medium #1. The column's DQ note counts the whole values shaped like thousands (`2.000` with `.`, `1,000` with `,`) that were read as small numbers. It also covers a column where every value is ambiguous, and a float column that must not be flagged. The mutant `grouped = pl.lit(False)` fails this test and the e2e test below. |
| F2c-1 | `tests/e2e/test_f2_ingest.py::test_dot_grouped_quantities_in_a_dot_file_are_counted_in_the_dq_note` | pass | Renamed in round 1 (it was `..._are_counted_never_scaled`). The column mixes `1.200` and `2.000` in a `.` file. REQ drops only the `1.200` rows (warning), and the note counts both kinds and names the `decimal:` fix. With `decimal: ','` the values read 1200 and 2000 and no note is left. In round 0 this test was rated **weak**: it used only `1.200`, which no decimal mark can turn into 1, so the silent scaling of `1.000` was never tested. |
| F2c-2 | `tests/unit/test_f2_rules.py::test_req_clears_negative_pallets_on_receipts` | pass | Negative pallets on receipts are set to null and counted in REQ (rules.py:91-95). The fix was already in the tree from W2 round 2, so the code is unchanged. |
| F2c-2 | `tests/e2e/test_f2_ingest.py::test_negative_receipt_pallets_are_derived_not_a_crash` | pass | End to end, the receipts give a REQ warning and pallets derived from `units_per_pallet`, not exit 1. |
| F2c-3 | `tests/unit/test_f2_sniff.py::test_T2_3_integers_outside_int64_and_infinities_become_null` | pass | Integers outside int64 and infinities become null with no polars error (parse.py:62 `is_finite`, :69 non-strict Int64 cast). |
| F2c-4 | `tests/e2e/test_f2_ingest.py::test_auto_picked_excel_sheet_is_not_forced_on_the_next_file` | pass | A sheet picked automatically is not saved and forced on the next file. Only a sheet the user chose is recorded (ingest.py:132). The build also removed `sheet=sn.sheet` from `resolve_mapping`, so that public function never returns an auto-picked sheet. |
| F2c-5 | `tests/e2e/test_f2_ingest.py::test_files_of_one_dataset_keep_their_own_decimal_mark` | pass | Two files of one dataset sniff `,` and `.`. The sniff field they disagree on is stored as None, so each file is sniffed again on the next run. Re-checked under the new decimal rule. |
| F2c-6 | `tests/unit/test_f2_rules.py::test_T2_6_r6_never_merges_a_return_into_a_sale` | pass | R6 dedup never merges a return into a sale. In round 0 this was rated **weak**: the mutant with `is_return` removed from `R6_KEY` passed every test, because the return line also had `line_status` 'returned'. Round 1 added two 'shipped' lines on the same (order_id, sku) with +5 and -5. They stay `[(5, False), (-5, True)]` with R6 dropped == 0, and the mutant now fails (re-run while writing this record). |
| F2c-7 | `tests/unit/test_f2_sniff.py::test_T2_1_utf32_with_bom_is_not_read_as_utf16_or_cp1252` | pass | New test. A UTF-32-LE BOM used to sniff as utf-16, and a UTF-32-BE BOM as cp1252. Both now read as `utf-32`, because the UTF-32 BOMs are checked first. The mutant without the UTF-32 BOMs fails it. |
| F2c-7 | `test_T2_1_utf16_unicode_text_export` | pass | The UTF-16 BOM file (Excel 'Unicode Text') still reads correctly. |
| F2c-8 | `tests/unit/test_f2_mapping.py::test_T2_5_exact_synonym_beats_subset_match_then_cardinality_breaks_ties` | pass | New test. 'Référence' (exact synonym, 5 distinct values) now beats 'Réf client' (subset match, 30 distinct). The old code picked 'Réf client'. Among fuzzy ties, sku proposes the column with more distinct values ('Réf article'), still as `suggest`. |
| F2c-8 | `test_tied_fuzzy_scores_are_asked_not_auto_accepted` | pass | A full tie is still asked, not auto-accepted. |
| F2c-9 | `tests/e2e/test_f2_ingest.py::test_one_dataset_per_call_keeps_the_issues_of_earlier_datasets` | pass | Ingesting one dataset per call keeps the raw-row rule results and notes of the datasets loaded earlier (ingest.py:158-177, :228-229). The fix was already in the tree. |
| F2c-10 | `tests/unit/test_f2_rules.py::test_T2_6_r13_threshold_is_median_plus_10_mad_floored_at_1` | pass | The R13 threshold is median + 10 × max(MAD, 1) (I53). On [1,1,1,1,1,1,2,3,15] the threshold is 11 and only 15 is listed. The mutant `R13_MAD_FLOOR=0` fails it. |
| F2c-10 | `test_base_fixture_is_clean` | pass | The base fixture was rebuilt: 628 lines over 400 days, 1-3 lines per order, mostly 1 unit, so MAD is 0 on both R13 measures. All rules are ok. The test fails if the floor is removed. |
| T2.1 | `tests/unit/test_f2_sniff.py::test_T2_1_encoding_and_delimiter_detection[*]` (6 fixtures) and 5 more T2_1 tests | pass | The 6 fixtures are utf8 `;`, utf8-BOM `,`, cp1252 `;`, latin1 tab, utf8 `|` and cp1252 quoted `,`. The other tests cover UTF-16/UTF-32 BOMs, coercion of charset_normalizer misreads, quoted delimiters and stray quotes. |
| T2.2 | `test_T2_2_header_on_row_3_csv`, `test_T2_2_header_on_row_3_excel_picks_the_biggest_sheet`, `test_T2_2_header_rule_skips_sparse_and_numeric_rows`, `test_T2_2_leading_blank_line_and_cr_only_line_ends` | pass | The header is found on row 3 in CSV and in Excel (biggest sheet). Sparse and numeric rows are skipped, and CR-only line ends are handled. **No test has a date-range preamble row**, which is why the round-1 regression (open issue 1) does not show in the suite. |
| T2.3 | `test_T2_3_*` in test_f2_sniff.py (11 tests) and test_f2_mapping.py (1 test) | pass | Decimal comma with thousand dots, and decimal dot with thousand commas, are checked against exact value lists. The edge cases are listed under F2c-1 and F2c-3. |
| T2.4 | `test_T2_4_each_date_format[*]` (14 formats), `test_T2_4_dotted_dates_are_dates_not_numbers_in_the_decimal_sniff`, and the mixed-format, ambiguous, 2-digit-year and DST tests | pass | Every step-5 format, including the Excel serial, is checked against an exact UTC instant. The dotted-date test was added in round 1 for round-0 medium #2. It asserts `(decimal, date_format) == (',', '%d.%m.%Y')` and pallets `[0.15, 0.25, 0.35]`. With `_DOTTED_DATE` disabled it fails with `assert ('.', None) == (',', '%d.%m.%Y')`. |
| T2.5 | `tests/unit/test_f2_mapping.py::test_T2_5_mapping_accuracy_on_fr_synthetic_csv`, `test_T2_5_mapping_accuracy_on_messy_fr_csv_and_en_csv` | pass | At least 95 % of targets are mapped on the FR synthetic CSV without a mapping file. On the 1M-line F1 FR set, the auditor's ingest mapped every dataset without asking a question. |
| T2.6 | `tests/unit/test_f2_rules.py::test_T2_6_each_rule_triggers_on_its_fixture[R1..R14]`, `test_T2_6_severity_thresholds_r1_r2`, `test_T2_6_rule_actions`, `test_T2_6_r11_fires_on_order_lines` and the R6/R13 tests above | pass | Each of R1-R14 triggers with its expected severity on its fixture. The R2 fixture grew to 12 orphan lines (1.9 % of the 640 lines with the fixture appended), so it is still a warning on the larger base. The R1/R2 bad-row counts are now derived from `lines.height`, not a hard-coded 480. |
| T2.7 | `test_T2_7_dq_score_formula[*]` (5 cases), `test_T2_7_bands`, `test_T2_7_report_score_matches_formula_on_fixtures[*]`, `test_T2_7_cover_score_never_rounds_into_a_better_band` | pass | The 5 cases are hand-computed, for example 1 blocking, 2 warnings, coverage 0.9 and short history gives 100 - 25 - 10 - 2 - 10 = 53. The score on the 1M-line FR run was also checked against the formula (proof 2). |
| T2.8 | `tests/unit/test_f2_anonymize.py::test_T2_8_*` (3 tests) | pass | The hash is stable with the same salt and differs with another. IDs are hashed the same way across tables. Description and customer columns are dropped unless kept. |
| T2.9 | `tests/e2e/test_f2_ingest.py::test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation` | pass | Three messy files become canonical with a scripted mapping confirmation in 0.4-0.5 s (budget 15 min). |
| C5 | `tests/e2e/test_f2_ingest.py::test_C5_bench_ingest_and_validate_1m_line_csv` | pass | 1,030,012 order lines plus master, stock and receipts are ingested and validated in 3.1 s (budget 120 s), as measured by the builder. |
| F2 Done-when | DQ report readable by a non-technical reader (review by the business lead) | not_applicable | This needs a human business reviewer. `test_dq_html_is_readable_and_escaped` checks only structure and escaping. |

## Proofs

Proofs 1 to 6 were captured by the auditors during the audit (rounds 0 and 1). Proofs 7 to 9 were re-run while writing this record on 2026-11-08. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F2c/`, written `<audit>/` below. All commands were run from `/Users/skarwech/saas_v1`. The round-0 and round-1 proof audits returned pass_with_issues with no findings and no proofs listed, so every proof below comes from the spec audits.

1. **The 1M-line FR ingest works end to end and no question is asked** (captured in round 1). The input is the F1 ecom_mid FR CSVs with defects: 1.03M order lines, 5k SKUs, 114k stock rows and 106k receipts. The output is typed canonical Parquet.
   Command: `uv run python <audit>/e2e_fr.py <audit>/ecom/csv_fr <audit>/out_fr`
   ```
   wall 3.0 s; asked [] | score 73.25 usable with caveats
   order_lines (1030012, 10) {... 'order_ts': Datetime(us, UTC), 'qty_units': 'Int64', 'line_status': 'Categorical'}
   ```
   (The schema line is from the round-0 run, which took 2.8 s.)

2. **The DQ score reproduces the T2.7 formula at runtime** (captured in round 0). 100 - 25 (5 warnings, capped) - 20 × (1 - 0.912438) = 73.2488, shown as 73.25.
   Command: `uv run python -c "import json; d=json.load(open('<audit>/out_fr/dq/dq_report.json')); print(d['score'], d['score_breakdown'], d['coverage'])"`
   ```
   'score': 73.25, 'score_breakdown': {'blocking': 0.0, 'warnings': -25.0, 'dims_coverage': -1.75124, 'short_history': 0.0}, 'coverage': {'dims_coverage_lines': 0.912438, ... 'history_months': 23.98}
   ```

3. **Round-0 medium #1 is fixed in the DQ report** (captured in round 1). In round 0, the FR inventory had 127 dot-grouped 'Qté' values, but the note counted only 125. Two of them were exact thousands: SKU 7596aa2287c675a4 had a true stock of 1000 and a canonical `qty_units` of 1. The note now counts all 127, and the EN mirror (`,` file with `1,000`) gives the same count.
   Command: `uv run python <audit>/e2e_fr.py <audit>/ecom/csv_fr ...` and the same with `<audit>/ecom/csv_en`
   ```
   NOTE [inventory] inventory.csv, column 'Qté' (qty_units): 125 values are not whole numbers with the decimal mark '.' and count as missing; 2 values such as '2.000' look like thousands but were read with th...
   NOTE [inventory] inventory.csv, column 'Quantity' (qty_units): 125 values are not whole numbers with the decimal mark ',' and count as missing; 2 values such as '2,000' look like thousands but were read wi...
   ```

4. **The fixes are guarded by tests: the mutants are killed** (captured in rounds 0 and 1). The mutants were applied in memory or to a scratch copy, and the repository was not changed.
   Commands: `<audit>/mutate.py mad_floor_0`, `<audit>/mutate2.py no_utf32`, `<audit>/mutate2.py decimal_threshold_half`, `<audit>/mutate3.py` (`_DOTTED_DATE` disabled), and a scratch copy with `grouped = pl.lit(False)`
   ```
   mad_floor_0: FAILED test_base_fixture_is_clean, FAILED test_T2_6_r13_threshold_is_median_plus_10_mad_floored_at_1
   no_utf32: FAILED test_T2_1_utf32_with_bom_is_not_read_as_utf16_or_cp1252
   decimal_threshold_half: FAILED test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma
   _DOTTED_DATE off: E AssertionError: assert ('.', None) == (',', '%d.%m.%Y') ; 1 failed, 81 passed
   grouped = pl.lit(False): 2 failed, 32 passed
   ```

5. **The thousands clause handles signs, padding and the override** (captured in round 1). Negative and padded values are counted. `decimal: ','` in the mapping clears the note. Single-digit dotted dates and dotted date-times also sniff `,`.
   Command: `uv run python <audit>/probes3.py <audit>/probe3`
   ```
   E decimal . [-2, 3, 7, None] ... 1 values are not whole numbers ...; 2 values such as '2.000' look like thousands
   F sniff . notes with decimal ',' override: []
   C 1.3.2025 decimal , date_format %d.%m.%Y | D dotted datetime decimal , %d.%m.%Y %H:%M
   ```

6. **The R13 threshold matches a hand computation (I53)** (captured in round 0, re-run below).
   ```
   6 R13 11.0 26.0 15.0   # [1x6,2,3,15]: med 1, MAD 0->1 => 11; [2,4,6,8,100]: med 6, MAD 2 => 26; [5,5,5,5]: med 5, MAD 0->1 => 15
   ```

7. **Probes re-run on the current tree** (re-run while writing this record). Dotted dates no longer veto the decimal comma. UTF-32 LE/BE and UTF-16 BE files with a BOM read correctly end to end. Out-of-range integers become null. The ungrouped and NBSP-grouped comma decimals are still read with `.` (open issue 2).
   Command: `uv run python <audit>/probes.py <audit>/probe_rec`
   ```
   1 dotted dates: decimal , pallets [0.15, 0.25, 0.35]
   2 utf-32-le utf-32 ['Référence', 'Qté', 'Date'] 2 ['A°', 'B']
   2 utf-32-be utf-32 ['Référence', 'Qté', 'Date'] 2 ['A°', 'B']
   2 utf-16-be utf-16 ['Référence', 'Qté', 'Date'] 2 ['A°', 'B']
   3 int64 [None, None, -9223372036854775808, 9007199254740992, 0]
   4 ungrouped 1234,5: decimal . Longueur [None, None, None]
   5 nbsp: decimal . [None, None]
   6 R13 11.0 26.0 15.0
   7 sku Référence auto 1.0 exact synonym 'reference'
   ```

8. **The R6 test now kills the `is_return` mutant** (round-1 audit, re-run while writing this record). In round 0 the same mutant gave `82 passed`.
   Command: `uv run python <audit>/mutate.py r6_key tests/unit/test_f2_rules.py -k r6`
   ```
   FAILED tests/unit/test_f2_rules.py::test_T2_6_r6_never_merges_a_return_into_a_sale
   1 failed, 1 passed, 33 deselected, 1 warning in 0.16s
   ```

9. **The preamble regression is still present** (round-1 finding, re-run while writing this record). A 'Période du;01.01.2025;au;31.12.2025' row is now taken as the header. With `_DOTTED_DATE` disabled (the pre-F2c behaviour), the real header on row 3 is found.
   Command: `uv run python <audit>/probe_preamble.py <audit>/probe3_rec`
   ```
   F2c code: header_row 1 ['Période du', '01.01.2025', 'au', '31.12.2025']
     mapping: [('sku', 'Période du', 'suggest'), ('qty_units', None, 'unmapped'), ('snapshot_date', None, 'unmapped')]
   pre-F2c (no _DOTTED_DATE): header_row 3 ['Référence', 'Qté', 'Date stock']
   ```

## Audit rounds

### Build (before round 0)

The builder changed code for findings 1, 7, 8 and 10:

- **F2c-1 (decimal sniff):**
  - `_DOT_DECIMAL`, `_COMMA_OR_GROUPED`, `parse.dot_grouped_integers` and `mapping.int_decimal` were deleted. Integer columns now use `parse_int(src, decimal)`, and the "read as thousands" branch of `number_notes` was removed.
  - `detect_decimal` computes one share per file. It uses the verbatim step-4 regex and ignores plain integers. It keeps the filter that a column counts as numeric when ≥ 80 % of its values look numeric.
- **F2c-7 (encoding):**
  - The UTF-32 BOMs are checked before UTF-16, because the UTF-16-LE BOM is a prefix of the UTF-32-LE BOM.
  - A charset_normalizer verdict that names utf_16 or utf_32 is now accepted, normalised with `codecs.lookup().name`.
- **F2c-8 (mapping ties):**
  - The ×0.9 preference multiplier is removed. The score is the header score, halved when the type does not fit.
  - The ranking is: score, then exact synonym before subset match, then the content preference, then the number of distinct sku values.
  - Fuzzy ties stay `suggest`.
  - Side effect: fuzzy columns that used to score 0.81 can now score 0.9 and be auto-accepted.
- **F2c-10 (R13):**
  - `R13_MAD_FLOOR = 1`.
  - The base fixture was regenerated with `scratchpad/F2c/gen_base.py`, which is kept outside the repo.

Findings 2, 3, 4, 5, 6 and 9 were already fixed in the tree by W2 round 2. Each was verified and has a passing test. For F2c-4 the builder also removed `sheet=sn.sheet` from `resolve_mapping`.

The builder measured the cost of the new decimal rule on F1 synthetic data with defects (150 days). Integer-only stock files with grouped thousands sniff the wrong mark in both languages: FR `1.234` gives `.` and EN `1,234` gives `,`. b2b_cases loses 176 of 8,000 stock rows and ecom_mid 18 of 20,000. REQ drops them as warnings, and the DQ note names the `decimal:` fix.

### Round 0: tests 119 passed, 0 failed

The spec audit returned **pass_with_issues**, with F2c-1 and F2c-6 rated weak and every other id pass. The proof audit returned **pass_with_issues** with no findings listed.

| Audit | Severity | Finding | Resolution (round-1 fix) |
|---|---|---|---|
| spec | medium | In a file sniffed `.`, a dot-grouped integer that is an exact multiple of 1000 (`1.000`, `2.000`) is read as 1 or 2. Other grouped values (`1.145`) become null and are counted. The DQ note counted only the nulls (125 of 127 'Qté' values on the FR ecom_mid inventory), so the claim "counted, never scaled" was false. | **Fixed (reporting only).** The parser was not changed, because two existing T2.3 tests pin `1.000` → 1 in a `.` file (the SAP 3-decimal case). `number_notes` now also counts non-null integer values shaped like `^\s*[-+]?\d{1,3}(<mark>\d{3})+\s*$` and names them in a second clause of the note. Float columns are not flagged. The `detect_decimal` docstring was corrected. New unit test `test_T2_3_number_notes_count_whole_values_shaped_like_thousands`. The e2e test was renamed and now mixes `1.200` and `2.000`. The value 1 is still stored (open issue 3). |
| spec | medium | Date-only `%d.%m.%Y` cells counted as numeric values in the decimal sniff. An FR file with dotted dates and comma decimals sniffed `.` and all its decimals became null. | **Fixed.** A new `_DOTTED_DATE` regex `^\d{1,2}\.\d{1,2}\.\d{4}$` in `is_numeric_text` marks such a cell as a date. That one change fixes both the decimal sniff and the file date format. The builder corrected part of the audit's diagnosis: `detect_file_date_format` had not identified the column either (it returned None, because the column looked all-numeric). The round-1 auditor confirmed this with the mutant (`('.', None)`). New test `test_T2_4_dotted_dates_are_dates_not_numbers_in_the_decimal_sniff`. |
| spec | low | The spec's verbatim step-4 regex `^\d{1,3}(\.\d{3})*,\d+$` rejects ungrouped comma decimals (`1037,5`, the usual FR Excel CSV export) and NBSP- or space-grouped ones (`1 200,5`). Such FR files sniff `.`. | **Deferred.** The task rules forbid changing the spec value, and `docs/INTERPRETATIONS.md` is outside F2c's paths. It was escalated as a [VERIFY] blocker. The DQ note gives the `decimal: ','` fix. |
| spec | low | The F2c-6 test did not cover `is_return` in `R6_KEY`. The mutant without it passed all F2 tests (82 passed). | **Fixed.** A 'shipped' +5/-5 case was added to the test, and the mutant now fails. rules.py is unchanged. |

Round-1 fix totals: 3 fixed and 1 deferred.

### Round 1: tests 121 passed, 0 failed

The spec audit returned **pass_with_issues** with every T-id pass and 0 medium and 2 low findings. The proof audit returned **pass_with_issues** with no findings listed. No fix round followed, so both findings are open.

| Severity | Finding | Status |
|---|---|---|
| low (carried from round 0) | The verbatim step-4 regex rejects `1037,5` and `1 200,5`. Probes 4 and 5 still give `decimal .` and null lengths. `grep -n I54 docs/INTERPRETATIONS.md` (l.416) shows no note on the dotted-date exclusion. | **Open, deferred.** [VERIFY] escalation to the spec owner. Re-run while writing this record: unchanged (proof 7). |
| low (new, **regression caused by the round-1 fix**) | `detect_header_row` also uses `is_numeric_text`. A dotted-date preamble row such as 'Période du;01.01.2025;au;31.12.2025' now counts 4 of 4 cells as text and is taken as the header. Before F2c, 2 of 4 text cells (50 % < 60 %) skipped it and the real header on row 3 was found. This is the literal reading of spec step 3 (a date is not numeric), and a `%d/%m/%Y` preamble already behaved this way. No T2.2 test has such a row, so the suite stays green. | **Open.** Found in the last round. Re-run while writing this record: still present (proof 9). |

### W2 round-1 findings scorecard

| Id | Finding | Outcome |
|---|---|---|
| F2c-1 | decimal sniff | Rewritten in the build. Strengthened in round 1 (thousands note, dotted dates). Exact thousands in a `.` file are still read as small numbers, but the note now reports them. |
| F2c-2 | negative receipt pallets | Already fixed. Verified. |
| F2c-3 | integers outside int64, infinities | Already fixed. Verified. |
| F2c-4 | auto-picked Excel sheet forced on the next file | Already fixed. `resolve_mapping` was also cleaned. |
| F2c-5 | per-file decimal mark in a dataset | Already fixed. Verified. |
| F2c-6 | R6 merges a return into a sale | Already fixed. The test was strengthened in round 1. |
| F2c-7 | UTF-32 BOM | Fixed in the build. Files without a BOM are not covered (open issue 4). |
| F2c-8 | mapping ties | Fixed in the build. |
| F2c-9 | issues of earlier datasets lost | Already fixed. Verified. |
| F2c-10 | R13 MAD floor | Fixed in the build. I53 is now in INTERPRETATIONS.md. [EXPERT] confirmation is pending. |

## Open issues

1. **Low, F2c-owned, regression from round 1:** a dotted-date preamble row ('Période du;01.01.2025;au;31.12.2025') is taken as the header. Mapping then suggests sku = 'Période du' and leaves qty_units and snapshot_date unmapped. It was reproduced on 2026-11-08. A possible fix is to treat date cells as neither text nor numeric in `detect_header_row`, or to add a T2.2 test with such a preamble. Either way the spec owner should confirm how step 3 treats dates.
2. **Low, [VERIFY] escalation (deferred since round 0):** the verbatim step-4 regex makes FR files with ungrouped (`1037,5`) or NBSP-grouped (`1 200,5`) comma decimals sniff `.` when more than 20 % of their separator values have those shapes. Their decimals become null. The DQ note names the `decimal: ','` fix, so no value is lost silently, but the file needs a manual mapping edit.
3. **Low, residual data hazard behind round-0 medium #1:** in a file sniffed `.`, exact dot-grouped thousands (`1.000`, `2.000`) are still stored as 1 and 2, and the same holds for `1,000` in a `,` file. Only the DQ note reports them. The parser was kept as it is on purpose, because the SAP 3-decimal case pins `1.000` → 1. This is a known behaviour, not a fix.
4. **Builder blockers:**
   - UTF-16 and UTF-32 files without a BOM still fall back to cp1252. charset_normalizer gives no verdict on them.
   - With the new decimal rule, integer-only stock files with grouped thousands sniff the wrong mark in both languages. On the builder's 150-day synthetic data, b2b_cases loses 176 of 8,000 stock rows and ecom_mid 18 of 20,000. On the auditor's 1M-line ecom_mid FR set, 127 'Qté' values were affected (125 null, 2 read as small numbers). REQ flags all of them as warnings, and the DQ note names the fix.
   - Cosmetic: all-digit `%Y%m%d` and Excel-serial date columns are skipped by the all-numeric gate of `detect_file_date_format`, so `SniffResult.date_format` stays None for files that have only those forms. Per-column parsing in `mapping._typed` still parses them.
5. **Docs, outside F2c's paths:** the build reported that the two decisions lived only in docstrings. That is out of date: I53 (R13 floor) and I54 (decimal sniff) are now in `docs/INTERPRETATIONS.md` (l.411-420). What is still missing is the round-1 change: I54 does not say that `%d.%m.%Y` date cells are left out of the share. The INTERPRETATIONS owner needs to add it.
6. **Side effect to watch:** with the ×0.9 multiplier gone, fuzzy header matches that used to score 0.81 can now score 0.9 and be auto-accepted. No test or audit found a wrong mapping from this.

## Not applicable here and why

- **Real client data:** none is available here, and client data must not leave the machine. Ingest was exercised on the F1 synthetic ecom_mid FR and EN sets with defects (1.03M lines), on b2b_cases, and on the fixtures under `tests/fixtures/ingest/`.
- **[EXPERT] confirmation of the R13 MAD floor (I53):** this needs a warehouse domain expert.
- **[VERIFY] decision on the step-4 regex:** this needs the spec owner (open issue 2).
- **F2 Done-when, DQ report readable by a non-technical reader:** this needs the business lead's review. `test_dq_html_is_readable_and_escaped` checks only structure and HTML escaping.
- **Docker and GitHub CI:** F2 does not depend on either, and no F2 test is skipped.
- **Edits to `docs/INTERPRETATIONS.md`:** outside F2c's paths (open issue 5).

## Fresh test output (run while writing this record, 2026-11-08)

The captured `ingest_done`, `rows_skipped` and similar log lines have been removed, and parametrized cases are collapsed.

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f2_*.py tests/e2e/test_f2_*.py -q -rA
=========================== short test summary info ============================
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_hash_is_stable_with_same_salt_and_differs_with_another
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_ids_hashed_consistently_across_tables_and_nulls_kept
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_description_and_customer_dropped_unless_kept
PASSED tests/unit/test_f2_anonymize.py::test_salt_from_env_or_file_outside_a_repository
PASSED tests/unit/test_f2_mapping.py::test_T2_5_mapping_accuracy_on_fr_synthetic_csv
PASSED tests/unit/test_f2_mapping.py::test_T2_5_mapping_accuracy_on_messy_fr_csv_and_en_csv
PASSED tests/unit/test_f2_mapping.py::test_normalize_strips_accents_case_and_punctuation
PASSED tests/unit/test_f2_mapping.py::test_header_score_exact_then_fuzzy
PASSED tests/unit/test_f2_mapping.py::test_greedy_assignment_uses_each_column_once_and_checks_content
PASSED tests/unit/test_f2_mapping.py::test_tied_fuzzy_scores_are_asked_not_auto_accepted
PASSED tests/unit/test_f2_mapping.py::test_T2_5_exact_synonym_beats_subset_match_then_cardinality_breaks_ties
PASSED tests/unit/test_f2_mapping.py::test_suggested_required_column_needs_confirmation
PASSED tests/unit/test_f2_mapping.py::test_unmapped_required_target_is_offered_every_column_interactively
PASSED tests/unit/test_f2_mapping.py::test_saved_mapping_sniff_values_fix_a_mis_sniffed_file
PASSED tests/unit/test_f2_mapping.py::test_apply_mapping_types_filters_and_defaults
PASSED tests/unit/test_f2_mapping.py::test_T2_3_number_notes_count_whole_values_shaped_like_thousands
PASSED tests/unit/test_f2_mapping.py::test_unit_hints_detect_cm_and_grams
PASSED tests/unit/test_f2_mapping.py::test_mapping_yaml_round_trip
PASSED tests/unit/test_f2_mapping.py::test_mapping_yaml_with_unknown_time_zone_is_a_config_error
PASSED tests/unit/test_f2_rules.py::test_base_fixture_is_clean
PASSED tests/unit/test_f2_rules.py::test_T2_6_each_rule_triggers_on_its_fixture[R1 .. R14]   (14 cases)
PASSED tests/unit/test_f2_rules.py::test_T2_6_rule_actions
PASSED tests/unit/test_f2_rules.py::test_T2_6_r11_fires_on_order_lines
PASSED tests/unit/test_f2_rules.py::test_T2_6_r13_threshold_is_median_plus_10_mad_floored_at_1
PASSED tests/unit/test_f2_rules.py::test_T2_6_severity_thresholds_r1_r2
PASSED tests/unit/test_f2_rules.py::test_req_drops_rows_missing_required_values
PASSED tests/unit/test_f2_rules.py::test_req_clears_negative_pallets_on_receipts
PASSED tests/unit/test_f2_rules.py::test_T2_6_r6_never_merges_a_return_into_a_sale
PASSED tests/unit/test_f2_rules.py::test_without_master_r2_is_not_evaluated_and_coverage_is_zero
PASSED tests/unit/test_f2_rules.py::test_T2_7_dq_score_formula[*]   (5 cases)
PASSED tests/unit/test_f2_rules.py::test_T2_7_bands
PASSED tests/unit/test_f2_rules.py::test_T2_7_report_score_matches_formula_on_fixtures[R7|R9|R10|R2]   (4 cases)
PASSED tests/unit/test_f2_rules.py::test_dq_html_is_readable_and_escaped
PASSED tests/unit/test_f2_rules.py::test_T2_7_cover_score_never_rounds_into_a_better_band
PASSED tests/unit/test_f2_sniff.py::test_T2_1_encoding_and_delimiter_detection[*]   (6 fixtures)
PASSED tests/unit/test_f2_sniff.py::test_T2_1_charset_normalizer_misreads_are_coerced_to_cp1252
PASSED tests/unit/test_f2_sniff.py::test_T2_1_utf16_unicode_text_export
PASSED tests/unit/test_f2_sniff.py::test_T2_1_utf32_with_bom_is_not_read_as_utf16_or_cp1252
PASSED tests/unit/test_f2_sniff.py::test_T2_1_delimiter_ignores_decimal_commas_and_quoted_delimiters
PASSED tests/unit/test_f2_sniff.py::test_T2_2_header_on_row_3_csv
PASSED tests/unit/test_f2_sniff.py::test_T2_2_header_on_row_3_excel_picks_the_biggest_sheet
PASSED tests/unit/test_f2_sniff.py::test_T2_2_header_rule_skips_sparse_and_numeric_rows
PASSED tests/unit/test_f2_sniff.py::test_T2_3_decimal_comma_with_thousand_dots
PASSED tests/unit/test_f2_sniff.py::test_T2_3_decimal_dot_with_thousand_commas
PASSED tests/unit/test_f2_sniff.py::test_T2_3_french_integers_with_dot_thousands_in_a_file_without_decimals
PASSED tests/unit/test_f2_sniff.py::test_T2_3_english_three_decimal_weights_next_to_integers_are_not_thousands
PASSED tests/unit/test_f2_sniff.py::test_T2_3_dotted_codes_do_not_veto_a_french_decimal_comma
PASSED tests/unit/test_f2_sniff.py::test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma
PASSED tests/unit/test_f2_sniff.py::test_T2_3_english_file_with_comma_grouped_quantities_stays_decimal_dot
PASSED tests/unit/test_f2_sniff.py::test_T2_3_three_decimal_quantities_in_a_dot_file_are_not_thousands
PASSED tests/unit/test_f2_sniff.py::test_T2_3_a_mark_that_is_not_a_thousands_grouping_gives_null
PASSED tests/unit/test_f2_sniff.py::test_T2_4_dotted_dates_are_dates_not_numbers_in_the_decimal_sniff
PASSED tests/unit/test_f2_sniff.py::test_T2_3_non_integral_and_garbage_become_null
PASSED tests/unit/test_f2_sniff.py::test_T2_3_integers_outside_int64_and_infinities_become_null
PASSED tests/unit/test_f2_sniff.py::test_bool_parsing_fr_en
PASSED tests/unit/test_f2_sniff.py::test_T2_4_each_date_format[*]   (14 formats, ISO with offset/Z ... %Y%m%d, excel_serial)
PASSED tests/unit/test_f2_sniff.py::test_T2_4_mixed_formats_are_coalesced_and_best_format_wins
PASSED tests/unit/test_f2_sniff.py::test_T2_4_ambiguous_day_month_assumes_ddmm_and_warns
PASSED tests/unit/test_f2_sniff.py::test_T2_4_two_digit_years_are_not_read_as_year_24
PASSED tests/unit/test_f2_sniff.py::test_T2_4_dst_gap_and_overlap_in_paris
PASSED tests/unit/test_f2_sniff.py::test_sniff_reports_rows_and_date_format
PASSED tests/unit/test_f2_sniff.py::test_parquet_input_is_read_as_text_and_round_trips
PASSED tests/unit/test_f2_sniff.py::test_T2_2_leading_blank_line_and_cr_only_line_ends
PASSED tests/unit/test_f2_sniff.py::test_T2_1_stray_quote_in_an_unquoted_field_is_read_as_text
PASSED tests/e2e/test_f2_ingest.py::test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation
PASSED tests/e2e/test_f2_ingest.py::test_persisted_mapping_is_reused_non_interactively
PASSED tests/e2e/test_f2_ingest.py::test_T1_4_fr_csv_reingests_with_zero_blocking_issues
PASSED tests/e2e/test_f2_ingest.py::test_C5_bench_ingest_and_validate_1m_line_csv
PASSED tests/e2e/test_f2_ingest.py::test_blocking_issue_raises_exit_3_after_writing_the_dq_report
PASSED tests/e2e/test_f2_ingest.py::test_several_files_per_dataset_are_appended_and_deduplicated
PASSED tests/e2e/test_f2_ingest.py::test_dates_without_time_flag_the_hour_as_unknown
PASSED tests/e2e/test_f2_ingest.py::test_site_filter_from_the_mapping_yaml
PASSED tests/e2e/test_f2_ingest.py::test_receipts_without_pallets_are_derived_from_units_per_pallet
PASSED tests/e2e/test_f2_ingest.py::test_mapping_file_missing_a_required_target_exits_2
PASSED tests/e2e/test_f2_ingest.py::test_non_interactive_unit_hint_needs_a_decision_in_the_mapping
PASSED tests/e2e/test_f2_ingest.py::test_incremental_ingest_keeps_the_order_lines_zone_and_merge_setting
PASSED tests/e2e/test_f2_ingest.py::test_one_dataset_per_call_keeps_the_issues_of_earlier_datasets
PASSED tests/e2e/test_f2_ingest.py::test_files_of_one_dataset_keep_their_own_decimal_mark
PASSED tests/e2e/test_f2_ingest.py::test_auto_picked_excel_sheet_is_not_forced_on_the_next_file
PASSED tests/e2e/test_f2_ingest.py::test_dot_grouped_quantities_in_a_dot_file_are_counted_in_the_dq_note
PASSED tests/e2e/test_f2_ingest.py::test_unreadable_numbers_are_explained_in_the_dq_report
PASSED tests/e2e/test_f2_ingest.py::test_negative_receipt_pallets_are_derived_not_a_crash
PASSED tests/e2e/test_f2_ingest.py::test_header_only_file_says_it_has_no_data_rows
121 passed in 13.29s
```
