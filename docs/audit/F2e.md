# F2e audit: Ingestion (tie-break DQ warning, canonical.validate error leak, threshold pins)

## Verdict: pass_with_issues

All F2 acceptance tests (T2.1 to T2.9), the C5 benchmark and the new F2e tests pass: 153 passed, 0 failed and 0 skipped. All four F2e items are done. Of the round-1 audit's 20 mutants, 18 are killed, 1 is equivalent and 1 survives; this tally was re-run while writing this record.
The verdict stays below `pass` because the last audit round (round 1) left one medium finding open and no fix round followed: for int targets, the tie-break note shows a parsed value that the canonical table never holds. Four low findings are also open, and both spec audits returned pass_with_issues.

Scope: F2e owns `src/whsizing/io/**`, `src/whsizing/schemas/ingest.py`, `tests/fixtures/ingest/**`, `tests/unit/test_f2_*.py` and `tests/e2e/test_f2_*.py`. The build changed `io/sniff.py`, `io/readers.py`, `io/mapping.py`, `io/ingest.py` and `io/canonical.py`, plus `tests/unit/test_f2_sniff.py`, `test_f2_mapping.py`, `test_f2_canonical.py` and `tests/e2e/test_f2_ingest.py`. Schema change (additive): `SniffResult.decimal_by_delimiter: bool = False` in `src/whsizing/schemas/manifest.py`. The manifest JSON gains one key, and the T0.3 round-trip and F0 schema tests pass. ruff check, ruff format and pyright were reported clean on `src/whsizing/io`, `schemas/manifest.py`, `schemas/ingest.py` and the F2 test files.

Effect on the F2d open issues (`docs/audit/F2d.md`):
- **Issue 4 closed.** The NUL thresholds are now pinned from both sides, and the `number_notes` leading-zero shape is pinned too.
- **Issue 2 narrowed.** A sparse or text-heavy data row below a pivoted header now gives row 0. A data row with no number at all still gives row 1 (open issue 5).
- **Issue 1 narrowed, not closed.** The `;` tie-break case now carries a DQ warning. A `;` file whose other columns show comma decimals still reads `1.250` kg as 1250 kg with no signal (open issue 4, [VERIFY]).
- **Issue 3 handled by the docs owner.** `docs/INTERPRETATIONS.md` now has the step-1 NUL rule and the step-3 date-cell rule in I67, and the `^[1-9]\d{0,2}` refinement in I54.

## Acceptance tests

T2.x are the F2 spec tests (description.md l.700). C5 is the §4.1 ingest benchmark. F2e-1 to F2e-4 are the four task items: (1) the I67 step-4 tie-break DQ warning; (2) the canonical.validate error leak; (3) the threshold pins; (4) a pivoted header followed by a sparse data row. Test paths are relative to `/Users/skarwech/saas_v1`. Statuses come from the fresh run below.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T2.3 / F2e-1 | `tests/e2e/test_f2_ingest.py::test_T2_3_semicolon_file_of_dot_3_decimal_weights_carries_a_tie_break_warning` | pass | F2d proof 7, end to end. A `;` sku_master with weights `2;5;10;1.250;3;4` gets a DQ note naming the file, the mark `,`, the delimiter `;`, `'1.250' (weight_kg) → 1250` and the `decimal: '.'` override. `sniff.decimal_by_delimiter` is True and the saved mapping keeps `decimal` None, so a re-ingest warns again. With `decimal: '.'`, the weight reads 1.25 kg and there is no note. An FR comma-decimal master gets no note. Kills `no_tie_break_note`, `tie_break_recorded`, `ingest_no_tb_notes` and `ingest_no_decimal_override`. |
| T2.3 / F2e-1 | `tests/unit/test_f2_mapping.py::test_T2_3_tie_break_note_names_file_mark_examples_and_override` | pass (gap) | Asserts the exact note text after fix round 1: up to 5 distinct examples, columns taking turns (6 ambiguous lengths and the weights), each example named by its column, the sign kept, unmapped columns left out, exact repr (`1234.567`), and "no number in the first 2000 data rows". No note when the mapping sets `decimal`, when the values decided the mark, or when the file has only whole numbers. Kills `tb_head6`, `tb_head4`, `tb_no_sign_strip`, `tb_no_unique`, `tb_no_turns`, `tb_sort_by_col`, `tb_fmt_g`, `tb_parse_other_mark` and `tb_ignores_mapping_decimal`. Gap: no int-target example is pinned, so `tb_float_only` survives (open issue 1). |
| T2.3 / F2e-1 | `tests/unit/test_f2_mapping.py::test_T2_3_tie_break_note_ignores_rows_the_site_filter_drops` | pass | New in fix round 1. The ambiguous values are only on PARIS rows and the site filter keeps LYON, so there is no note. Without the filter, both values are shown. Kills `tb_no_filter`. |
| T2.3 / F2e-1 | `tests/e2e/test_f2_ingest.py::test_T2_3_one_tie_break_file_among_several_keeps_the_mark_unrecorded` | pass | New in fix round 1. File m1 has FR comma decimals, so the values decide `,`. File m2 has integers and `1.250`, so `,` comes from the tie-break. Over two ingests the saved mapping keeps `decimal` None, and exactly one note names `m2.csv`. Kills `agreed_any_to_all`. |
| T2.3 / F2e-1 | `tests/unit/test_f2_sniff.py::test_T2_3_tie_break_flag_is_set_only_when_the_delimiter_chose_the_mark` | pass | The flag is True for `;` and `,` files where the delimiter chose the mark. It is False when comma evidence decides and when a saved mapping fixes `decimal`. Kills `flag_ignores_saved`, `by_delim_semicolon_only` and `sniff_by_delim_ignores_fixed`. The docstring says Excel never sets the flag, but no Excel case is asserted. It holds by construction: `readers.py` discards the 4th value of `sniff_rows`. |
| T2.9 / F2e-2 | `tests/unit/test_f2_canonical.py::test_T2_9_missing_required_column_is_a_whsizing_error_exit_1` (6 cases) | pass | Replaces the round-0 test `test_T2_9_missing_coerced_column_is_a_data_quality_error`. The 6 cases are a missing `sku`; `qty_units` plus `source_file`; `weight_kg`; `snapshot_date`; `order_ts`; and `receipt_ts`. Each raises `type(e) is WhsizingError` with `exit_code == 1` and the message `canonical <table>: cannot find column "x" (required by §4.1)` for every missing column. No raw polars `ColumnNotFoundError` leaks. Kills `validate_first_only`, `validate_coerce_only`, `validate_no_missing_check` and `validate_dq_class`. In round 0, the test it replaces killed `validate_no_precheck`. |
| T2.9 / F2e-2 | `tests/unit/test_f2_canonical.py::test_T2_9_complete_frames_pass_and_a_bad_dtype_is_a_whsizing_error` | pass | Replaces the round-0 test `test_T2_9_complete_frames_pass_and_a_missing_timestamp_is_a_whsizing_error`. Complete frames with the optional columns absent still pass. A bad dtype stays pandera's `WhsizingError`. In round 0, the test it replaces killed `validate_coerce_any`. |
| T2.1 / F2e-3 | `tests/unit/test_f2_sniff.py::test_T2_1_utf16_without_bom_nul_thresholds_are_50_and_10_percent` (utf-16-le, utf-16-be) | pass | Uses 4 KB built byte strings. A 50 % NUL share at the high-byte offsets gives wide; 48.97 % gives None. A 9.96 % share at the low-byte offsets gives wide; 10.01 % gives None. Mostly-Cyrillic UTF-16 gives None. The auditor checked the shares by hand (1024/2048, 1003/2048, 204/2048, 205/2048). Kills `wide_mostly_030`, `wide_rarely_050`, `wide_mostly_051`, `wide_rarely_009` and `wide_ge_to_gt`. |
| T2.3 / F2e-3 | `tests/unit/test_f2_mapping.py::test_T2_3_number_notes_never_read_a_leading_zero_group_as_thousands` | pass | In an int column of a `.` file, `0.000` is not flagged as thousands; only `2.000` is. The note text is asserted exactly. Kills `grouped_shape_leading_zero`, which survived in F2d. |
| T2.2 / F2e-4 | `tests/unit/test_f2_sniff.py::test_T2_2_pivoted_date_header_with_a_sparse_data_row_is_still_row_0` (7 cases) | pass | A pivot header followed by a sparse row, a text-heavy row, a dense row then a sparse row, or a blank line then a sparse row gives 0. A date preamble directly above the header gives 1, or 2 with a blank line between them. A preamble above a 'labels + date' header gives 1. 4 cases fail on the F2d rule (`header_f2d`), and `header_any_to_all` is killed. |
| T2.2 / F2e-4 | `tests/unit/test_f2_sniff.py::test_T2_2_pivoted_csv_with_a_sparse_first_data_row_reads_the_pivot_header` | pass | Through `read_any`: `header_row` is 1, the columns are the pivot names and there are 2 data rows. |
| T2.9 | `tests/e2e/test_f2_ingest.py::test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation` | pass | Unchanged by F2e. Wall time 0.4-0.6 s against the 15 min budget. |
| T2.1-T2.8 | the other `test_T2_1_*` to `test_T2_8_*` tests in `test_f2_sniff.py`, `test_f2_mapping.py`, `test_f2_rules.py` and `test_f2_anonymize.py` | pass | Unchanged by F2e, still pass. On F1 b2b_cases and ecom_mid (150 days, seed 3, defects, FR and EN), the DQ scores (63.51 and 60.9) and the row counts match the F2d audit. |
| C5 | `tests/e2e/test_f2_ingest.py::test_C5_bench_ingest_and_validate_1m_line_csv` | pass | 1,030,012 order lines ingested and validated in 3.0 s (2.9 s in another run) against the 120 s budget. |
| F2 Done-when | DQ report readable by a non-technical reader | not_applicable | Needs the business lead's review. |

Mutant names come from three sets: the engineer's (`scratchpad/F2e/mutate.py`, 10 mutants), the round-0 audit (`audit_F2e/mutate.py`, 12) and the round-1 audit (`audit_F2e/r1/mutate.py`, 20).

## Proofs

The auditors captured all of these proofs during the audit, in round 0 or round 1. Proofs 3, 6, 7, 8 and 9 were re-run on 2026-11-09 while writing this record, and the output was the same. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F2e/`, written `<audit>/` below. The scratchpad folder itself is written `<scratchpad>`. All commands were run from `/Users/skarwech/saas_v1`. Neither proof audit listed findings or proofs, so every proof below comes from the spec audits.

1. **The tie-break warning works end to end on F1 FR data** (round 0). The input is F1 b2b_cases with integer dims and weights `2;5;10;1.250;3;4` in a `;` master. The flag is set, and the note names the file, the mark, the delimiter, the examples and the override. The mapping keeps `decimal` None, and a re-ingest into the same folder warns again. The round-0 note text was later changed by fix round 1 (proof 7).
   Command: `uv run python <audit>/p3_e2e_int.py`
   ```
   == semi: score 62.14 ... NOTE: [sku_master] art_semicolon.csv: warning, decimal mark ',' chosen by the field delimiter ';', because no value in the file shows the mark; values that can be thousands or 3 decimals were read as '1.250' → 1250, '2.158' → 2158, ... set decimal: '.' in mapping/sku_master.yaml and re-run (decimal: ',' confirms this reading).
   sniff [(';', ',', True)] / mapping sku_master decimal = None / weights read [2.0, 3.0, 4.0, 5.0, 10.0, 1250.0] / == semi_again: (same note, ...   [clipped in the audit record]
   ```

2. **The tie-break works the other way for a `,` file, and the override silences it** (round 0, same script). A `,` file gets `.` with a note. Setting `decimal: '.'` removes the note and reads 1.25 kg.
   ```
   == comma: ... warning, decimal mark '.' chosen by the field delimiter ',', ... '1.250' → 1.25 ... / sniff [(',', '.', True)]
   == semi_fixed: (no tie-break note) sniff [(';', '.', False)] / mapping sku_master decimal = . / weights read [1.25, 2.0, 3.0, 4.0, 5.0, 10.0]
   ```

3. **canonical.validate: the exit code depended on the column in round 0 and is uniform after fix round 1** (round 0 negative proof; round 1 fix proof, re-run 2026-11-09). In round 0, a missing `sku` gave exit 3 and a missing `order_ts` gave exit 1. Now every missing required column gives `WhsizingError` exit 1, both directly and through F3's `load_canonical`.
   Command: `uv run python <audit>/p1_validate.py ; uv run python <audit>/p5_load_canonical.py`
   ```
   round 0:    missing sku -> DataQualityError exit 3: canonical order_lines: cannot find column "sku" (required by §4.1) ...
               missing order_ts -> WhsizingError exit 1: canonical order_lines failed schema validation: column 'order_ts' not in dataframe
   2026-11-09: missing sku        -> WhsizingError exit 1: canonical order_lines: cannot find column "sku" (required by §4.1); columns present: [...]
               missing qty_units  -> WhsizingError exit 1 ... | missing order_id -> WhsizingError exit 1 ... | missing order_ts -> WhsizingError exit 1 ...
               missing source_row -> WhsizingError exit 1 ... | receipts -> WhsizingError exit 1: canonical receipts: cannot find column "receipt_ts" ...
               inventory -> WhsizingError exit 1: canonical inventory: cannot find column "qty_units" ...
   round 1:    profile on canonical without sku: WhsizingError exit 1 | without order_ts: WhsizingError exit 1
               qty_units 'abc' -> WhsizingError exit 1: canonical order_lines failed schema validation: Could not coerce 'qty_units' ...
   ```

4. **The F2 tests kill all 10 of the engineer's mutants** (round 0).
   Command: `for m in wide_mostly_030 ... flag_ignores_saved; do uv run python <scratchpad>/F2e/...; done`. The audit record clips the script path; the engineer's mutant script is `<scratchpad>/F2e/mutate.py`.
   ```
   wide_mostly_030 2 failed / wide_rarely_050 2 failed / wide_mostly_051 2 failed / wide_rarely_009 2 failed / grouped_shape_leading_zero 1 failed / header_f2d 5 failed / no_tie_break_note 2 failed / tie_break_recorded 1 failed / validate_no_precheck 4 failed / flag_ignores_saved 1 failed
   ```

5. **Round-0 audit mutants: 10 of 12 killed** (round 0). The two survivors became round-0 finding 8. Each mutant runs on an overlay PYTHONPATH, so the repo is not changed.
   Command: `uv run python <audit>/mutate.py`
   ```
   tb_no_filter SURVIVED / tb_head6 KILLED / tb_no_sign_strip KILLED / by_delim_semicolon_only KILLED / ingest_no_tb_notes KILLED / validate_first_only KILLED / header_any_to_all KILLED / tb_ignores_mapping_decimal KILLED / wide_ge_to_gt KILLED / agreed_any_to_all SURVIVED / tb_no_unique KILLED / validate_coerce_any KILLED
   ```

6. **Round-1 audit mutants: 18 of 20 killed, one equivalent, one surviving** (round 1, re-run 2026-11-09 with the same tally). `tb_no_filter` and `agreed_any_to_all` are now killed. `tb_no_fill_null` is equivalent, because a polars filter drops null predicates. `tb_float_only` survives: no test pins an int-column example, which is the test gap behind open issue 1.
   Command: `uv run python <audit>/r1/mutate.py`
   ```
   tb_no_filter KILLED by FAILED tests/unit/test_f2_mapping.py::test_T2_3_tie_break_note_ignores_rows_the_site_filter_drops
   agreed_any_to_all KILLED by FAILED tests/e2e/test_f2_ingest.py::test_T2_3_one_tie_break_file_among_several_keeps_the_mark_unrecorded
   validate_coerce_only KILLED ... | validate_no_missing_check KILLED ... | validate_dq_class KILLED ... | tb_sort_by_col KILLED ... | tb_head4 KILLED ...
   tb_parse_other_mark KILLED ... | ingest_no_decimal_override KILLED ... | sniff_by_delim_ignores_fixed KILLED ...
   tb_no_fill_null SURVIVED
   tb_float_only SURVIVED
   ```

7. **The note's edge cases are fixed by fix round 1, and the header limits remain** (round 0 negative proof; round 1 fix proof, re-run 2026-11-09). Case A: columns take turns, so the 1.250 kg weight is shown next to 5 or more ambiguous lengths, and each example names its column. Case D: the parsed value uses the exact repr. Case E: the note says "first 2000 data rows". Case F: the two documented header limits are unchanged.
   Command: `uv run python <audit>/p4_edges.py`
   ```
   round 0:    A ... read as '1.100' → 1100, '2.101' → 2101, '3.102' → 3102, '4.103' → 4103, '5.104' → 5104   (no weight shown)
               D ... '1,234.567' → 1234.57
   2026-11-09: A ... because no number in the first 2000 data rows shows the mark; values that can be thousands or 3 decimals were read as '1.100' (L) → 1100, '1.250' (Poids) → 1250, '2.101' (L) → 2101, '3.102' (L) → 3102, '4.103' (L) → 4103.
               D ... '1,234.567' (Poids) → 1234.567
               E , True [... because no number in the first 2000 data rows shows the mark ... '1.250' (Poids) → 1250 ...]
               F pivot + no-number text row -> 1
               F preamble + header with bare-number label -> 0
   ```

8. **On a real-shaped export, the warning reaches dq_report.json and dq_report.html** (round 1, re-run 2026-11-09). The input is an F1 b2b_cases FR export of 120 days. `decimal` stays unrecorded only for the datasets where the delimiter chose the mark.
   Command: `uv run python <audit>/r1/p7_html.py`
   ```
   tie notes in json: 1
      [inventory] inventory.csv: warning, decimal mark ',' chosen by the field delimiter ';', because no number in the first 2000 data rows shows the mark; ...
      in html: True
   mapping order_lines decimal = None
   mapping sku_master decimal = ,
   mapping inventory decimal = None
   mapping receipts decimal = ,
   ```

9. **Open medium: for int targets, the note's parsed value is not the ingested value** (round 1, re-run 2026-11-09). The input is a `;` inventory file holding US `1,500` stock counts, the scenario of F2d's `test_unreadable_numbers_are_explained_in_the_dq_report`. The tie-break note says `→ 1.5`. The canonical `qty_units` is null, and `number_notes` says the values count as missing.
   Command: `uv run python <audit>/r1/p8_us_stock.py`
   ```
   sniff (';', ',', True)
   tie : values that can be thousands or 3 decimals were read as '1,500' (Qte) → 1.5. If the file uses '.' as decimal m...
   num : [inventory] inventory.csv, column 'Qte' (qty_units): 4 values are not whole numbers with the decimal mark ',' and count ...
   canonical qty_units [None, None, None, None]
   ```

## Audit rounds

### Build (before round 0)

The engineer reproduced each of the four items before fixing it.

- **F2e-1, I67 step 4.**
  - `sniff_rows` now returns a 4th value, `by_delimiter`. It is True when no counted separator value is left and the file has a field delimiter.
  - `sniff_csv` stores it in `SniffResult.decimal_by_delimiter`, and sets it False when a saved mapping fixes `decimal`. Excel and Parquet never set it.
  - `mapping.tie_break_notes(raw, mapping)` writes the warning as a DQReport note, not a scored RuleResult, so DQ scores do not change. The note is prefixed `[<ds>]` so incremental ingests carry it forward.
  - Two interpretations were disclosed:
    - (a) The note fires only when a mapped numeric column holds an ambiguous thousands-shaped value. Otherwise every FR integer-only order_lines file would be warned.
    - (b) When any file's mark came from the tie-break, the auto-saved mapping keeps `decimal: null`, so each re-ingest warns again. This departs from mapping step 7. Limit: a mapping saved before F2e already holds `decimal: ','`, and it silences the warning.
- **F2e-2, canonical.validate leak.**
  - The build added a pre-check for the required columns that pandera coerces. That is where the raw polars `ColumnNotFoundError` leaked through.
  - The pre-check raised `DataQualityError` (exit 3). A missing `order_ts` or `receipt_ts` still went through pandera as `WhsizingError` (exit 1).
  - Fix round 1 reversed the exit-3 choice (round-0 finding 1).
- **F2e-3, threshold pins.** Tests pin both NUL thresholds from both sides, and they pin the leading-zero shape in `number_notes`.
- **F2e-4, pivot header with a sparse data row.**
  - New step-3 rule: a row above the date-aware pick may qualify only under the verbatim rule. If the pick contains a number cell, that verbatim row is the header.
  - The limits are documented in a `ponytail:` comment (`sniff.py` l.187).
- **Realistic check.** On F1 b2b_cases and ecom_mid, the DQ scores and row counts match the F2d audit. The new note appears only on inventory, for example `'3.137' → 3137`.

### Round 0: tests 149 passed, 0 failed

The spec audit returned **pass_with_issues**, with every F2e T-id pass. The proof audit returned **pass_with_issues** and listed no findings and no proofs.

| # | Severity | Finding | Resolution (fix round 1) |
|---|---|---|---|
| 1 | medium | canonical.validate gave different exit codes for the same defect. A missing `sku`, `qty_units`, `order_id`, `source_row` or `weight_kg` gave `DataQualityError` (exit 3). A missing `order_ts` or `receipt_ts` gave `WhsizingError` (exit 1). §2.7 reserves exit 3 for blocking R-rule issues, and validate's own docstring calls such a failure an F2 bug. | **Fixed.** Every missing required column, coerced or not, now raises `WhsizingError` (exit 1) with one message: `canonical <table>: cannot find column "x" (required by §4.1); columns present: [...]`. The 6-case test asserts the exact class and exit code. `validate_dq_class`, `validate_coerce_only` and `validate_first_only` are killed. `tests/unit/test_f3_*.py` gives 46 passed, unchanged. Residual: the F3 code that added the directory to the message can no longer be reached (round-1 low). |
| 2 | low | The examples came from the mapped columns in TARGETS order, capped at 5, with no column named. When 5 or more ambiguous lengths come first, the `1.250` kg weight that motivated I67 step 4 is never shown. | **Fixed.** Distinct ambiguous values are ranked within each column and sorted by rank, so columns take turns. Each example names its column, for example `'1.250' (Poids) → 1250` (proof 7). `tb_no_turns` is killed. |
| 3 | low | Interpretations (a) and (b) are not registered in `docs/INTERPRETATIONS.md`. | **Deferred.** This needs an edit outside F2e's paths and a decision by the spec owner. The behaviour is now pinned by tests. The text to register is in open issue 3. |
| 4 | low | A `;` master whose other columns show comma decimals reads a dot 3-decimal weight `1.250` as 1250 kg with no DQ signal. The values decided the mark, so I67 step 4 rightly stays silent, and `number_notes` checks only int columns. The auditor rated this not an F2e defect. | **Deferred.** It belongs to the I54 [VERIFY] decision (F2d open issue 1), and the engineer did not want to preempt it. |
| 5 | low | The note said "no value in the file shows the mark", but the sniff samples only the first 2,000 data rows. | **Fixed.** The note now says "no number in the first 2000 data rows", using `sniff.DECIMAL_SAMPLE_ROWS` (proof 7, case E). |
| 6 | low | Examples were formatted with `{x:g}`, which misreports the parsed value (`'1,234.567' → 1234.57`). | **Fixed.** Non-integer values now use Python's shortest round-trip repr (proof 7, case D). `tb_fmt_g` is killed. |
| 7 | low | The documented limits of the new step-3 rule reproduce. Below a pivoted date header, a data row with no number is still the header. A real header with a bare-number label below a date preamble falls back to the preamble. | **Deferred.** This is the residual of F2d open issue 2. It needs a design decision on the header heuristic. Neither file shape can be mapped under either rule. |
| 8 | low | Test gaps: the audit mutants `tb_no_filter` (the note ignores the site filter) and `agreed_any_to_all` (one decided file plus one tie-break file would save the mark) survive. | **Fixed.** Two new tests were added: `test_T2_3_tie_break_note_ignores_rows_the_site_filter_drops` and `test_T2_3_one_tie_break_file_among_several_keeps_the_mark_unrecorded`. Both mutants are now killed (proof 6). |

Fix round 1 totals: 5 fixed and 3 deferred.

### Round 1: tests 153 passed, 0 failed

The spec audit returned **pass_with_issues**: T2.1-T2.9 pass and F2 Done-when is not_applicable. The proof audit returned **pass_with_issues** and listed no findings and no proofs. No fix round followed, so every round-1 finding is still open.

| Severity | Finding | Status |
|---|---|---|
| medium | `tie_break_notes` (`io/mapping.py` l.416) parses every example with `parse_number`. `apply_mapping` reads int targets (`qty_units`, `units_per_case`, `cases_per_pallet`) with `parse_int`, and `number_notes` (l.365) already picks the parser by kind. So the note can show a value the canonical table never holds. In one DQ report, the tie-break note says `'1,500' (Qte) → 1.5` while `number_notes` says those values count as missing, and canonical `qty_units` is null. | **Open.** Re-run on 2026-11-09 (proof 9); `tb_float_only` still survives (proof 6). |
| low | Residual of round-0 #1, outside F2e's paths. F3's `load_canonical` (`src/whsizing/profile/aggregate.py` l.44) has an `except pl.exceptions.ColumnNotFoundError` that can no longer be reached. The canonical directory is gone from the message a profile run shows. The F3 tests still pass, because their regexes do not check the directory. | **Open, F3 owner.** Checked on 2026-11-09: the `except` is still at l.44. |
| low | Round-0 #3 is still unresolved, now with four items (a)-(d), listed in open issue 3. | **Open, docs owner.** |
| low | Round-0 #4 is still open: the mixed-mark `;` master reads `1.250` kg as 1250 kg with no signal. | **Open, [VERIFY] spec owner.** |
| low | Round-0 #7 is still open: the step-3 header limits. | **Open.** Re-run on 2026-11-09 (proof 7, case F). |

## Open issues

1. **Medium:** for int targets, the tie-break note shows a value that is not what was ingested (proof 9). The note parses with `parse_number`, while `apply_mapping` uses `parse_int`. The auditor points to the existing pattern in `number_notes` (l.365), which picks the parser by target kind. No test pins an int-column example (`tb_float_only` survives).
2. **Low, F3 owner (outside F2):** in `src/whsizing/profile/aggregate.py` l.42-46, the `except pl.exceptions.ColumnNotFoundError` in `load_canonical` can no longer be reached, so the canonical directory no longer appears in the error. Suggested fix: catch `WhsizingError` from `validate` and re-raise `WhsizingError(f"{e} (in {canonical_dir})") from e`.
3. **Low, `docs/INTERPRETATIONS.md` owner (outside F2):** I67 step 4 should record these points.
   - (a) The warning fires only when a mapped numeric column holds a thousands-only value `^[1-9]\d{0,2}([.,]\d{3})+$` (sign allowed) in the rows the mapping keeps, after site filters. An integer-only file gets no note.
   - (b) When any file of a dataset got its mark from the tie-break, the auto-saved `mapping/<dataset>.yaml` keeps `decimal: null`. This departs from F2 mapping step 7.
   - (c) The note shows up to 5 distinct examples, taken in turn from each mapped numeric column, each named by its column and shown as raw → exact parsed value. The note says "no number in the first 2000 data rows", not "in the file".
   - (d) A canonical table missing a required §4.1 column is `WhsizingError` (exit 1), never `DataQualityError`, which is for R-rules only.

   The round-1 auditor checked with `grep`: `docs/INTERPRETATIONS.md` holds only the original I67 text (l.550). Re-checked on 2026-11-09: I67 (l.544-552) still contains none of (a)-(d).
4. **Low, [VERIFY] spec owner, carried from F2d open issue 1:** in a `;` file, dot 3-decimal values such as `1.250` kg are read ×1000. With no other evidence, the tie-break gives `,` and the note now warns. When other columns show comma decimals, the values decide `,` and there is still no DQ signal, because `number_notes` checks only int columns.
5. **Low, known ceiling, residual of F2d open issue 2:** below a pivoted date header, a data row with no number is taken as the header. A real header with a bare-number label (`Réf;Qté;2025`) below a date preamble falls back to the preamble row. This is documented in a `ponytail:` comment in `sniff.py`. Neither shape can be mapped.
6. **Low, known limit:** a mapping saved before F2e already holds `decimal: ','`, which silences the warning for that client.
7. **Minor test gap from the round-0 evidence:** the sniff-flag test's docstring says Excel never sets the flag, but no Excel case is asserted. It holds by construction in `readers.py`.
8. **Builder blockers outside F2, reported at build time:**
   - The T0.1 ruff gate failed on `tests/golden/test_f6_area_golden.py:7` (E501).
   - `tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[cube_asrs]` failed.

   Checked on 2026-11-09: `uv run ruff check` on that file passes, and the T6_8 test gives 3 passed. Both look like concurrent edits that have since settled. Neither touches `whsizing.io`.
9. **Housekeeping:** the F2d `no_header_fallback` mutant no longer applies, because `detect_header_row` was refactored into `_first_header`. Replacement mutants are in the engineer's `scratchpad/F2e/mutate.py`, and all are killed.

## Not applicable here and why

- **F2 Done-when (the DQ report is readable by a non-technical reader):** needs the business lead's review. `test_dq_html_is_readable_and_escaped` checks only structure and escaping. Proof 8 shows the new note reaches the HTML, but not that a reader understands it.
- **Real client data:** none is available here, and client data must not leave the machine. These inputs were used instead:
  - the F1 synthetic sets (b2b_cases and ecom_mid, FR and EN, with defects);
  - the C5 1M-line bench;
  - the built fixtures in the F2 tests and the audit scripts.
- **[VERIFY] decision on the I54 amendment:** needs the spec owner (open issue 4).
- **Edits to `docs/INTERPRETATIONS.md` and `src/whsizing/profile/aggregate.py`:** outside F2e's paths (open issues 2 and 3).
- **Docker and GitHub CI:** F2 does not depend on either, and no F2 test is skipped.

## Fresh test output (run while writing this record, 2026-11-09)

Captured log lines are removed and parametrized cases are collapsed (`[*]`, with the case count).

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f2_*.py tests/e2e/test_f2_*.py -q -rA
=========================== short test summary info ============================
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_hash_is_stable_with_same_salt_and_differs_with_another
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_ids_hashed_consistently_across_tables_and_nulls_kept
PASSED tests/unit/test_f2_anonymize.py::test_T2_8_description_and_customer_dropped_unless_kept
PASSED tests/unit/test_f2_anonymize.py::test_salt_from_env_or_file_outside_a_repository
PASSED tests/unit/test_f2_canonical.py::test_T2_9_missing_required_column_is_a_whsizing_error_exit_1[*]   (6 cases)
PASSED tests/unit/test_f2_canonical.py::test_T2_9_complete_frames_pass_and_a_bad_dtype_is_a_whsizing_error
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
PASSED tests/unit/test_f2_mapping.py::test_T2_3_number_notes_never_read_a_leading_zero_group_as_thousands
PASSED tests/unit/test_f2_mapping.py::test_T2_3_tie_break_note_names_file_mark_examples_and_override
PASSED tests/unit/test_f2_mapping.py::test_T2_3_tie_break_note_ignores_rows_the_site_filter_drops
PASSED tests/unit/test_f2_rules.py::test_base_fixture_is_clean
PASSED tests/unit/test_f2_rules.py::test_T2_6_each_rule_triggers_on_its_fixture[*]   (14 cases)
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
PASSED tests/unit/test_f2_rules.py::test_T2_7_report_score_matches_formula_on_fixtures[*]   (4 cases)
PASSED tests/unit/test_f2_rules.py::test_dq_html_is_readable_and_escaped
PASSED tests/unit/test_f2_rules.py::test_T2_7_cover_score_never_rounds_into_a_better_band
PASSED tests/unit/test_f2_sniff.py::test_T2_1_encoding_and_delimiter_detection[*]   (6 cases)
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
PASSED tests/unit/test_f2_sniff.py::test_T2_4_each_date_format[*]   (14 cases)
PASSED tests/unit/test_f2_sniff.py::test_T2_4_mixed_formats_are_coalesced_and_best_format_wins
PASSED tests/unit/test_f2_sniff.py::test_T2_4_ambiguous_day_month_assumes_ddmm_and_warns
PASSED tests/unit/test_f2_sniff.py::test_T2_4_two_digit_years_are_not_read_as_year_24
PASSED tests/unit/test_f2_sniff.py::test_T2_4_dst_gap_and_overlap_in_paris
PASSED tests/unit/test_f2_sniff.py::test_sniff_reports_rows_and_date_format
PASSED tests/unit/test_f2_sniff.py::test_parquet_input_is_read_as_text_and_round_trips
PASSED tests/unit/test_f2_sniff.py::test_T2_2_leading_blank_line_and_cr_only_line_ends
PASSED tests/unit/test_f2_sniff.py::test_T2_1_stray_quote_in_an_unquoted_field_is_read_as_text
PASSED tests/unit/test_f2_sniff.py::test_T2_3_ungrouped_and_space_grouped_comma_decimals_are_decimal_comma
PASSED tests/unit/test_f2_sniff.py::test_T2_2_date_range_preamble_is_not_the_header
PASSED tests/unit/test_f2_sniff.py::test_T2_1_utf16_and_utf32_without_bom_are_told_by_their_nul_bytes
PASSED tests/unit/test_f2_sniff.py::test_T2_4_all_digit_yyyymmdd_column_names_the_file_date_format
PASSED tests/unit/test_f2_sniff.py::test_T2_3_leading_zero_three_decimal_weights_in_a_semicolon_file_are_decimals
PASSED tests/unit/test_f2_sniff.py::test_T2_2_pivoted_date_header_falls_back_to_the_verbatim_rule
PASSED tests/unit/test_f2_sniff.py::test_T2_1_utf16_without_bom_with_many_non_latin1_letters
PASSED tests/unit/test_f2_sniff.py::test_T2_1_utf16_without_bom_nul_thresholds_are_50_and_10_percent[*]   (2 cases: utf-16-le, utf-16-be)
PASSED tests/unit/test_f2_sniff.py::test_T2_2_pivoted_date_header_with_a_sparse_data_row_is_still_row_0[*]   (7 cases)
PASSED tests/unit/test_f2_sniff.py::test_T2_2_pivoted_csv_with_a_sparse_first_data_row_reads_the_pivot_header
PASSED tests/unit/test_f2_sniff.py::test_T2_3_tie_break_flag_is_set_only_when_the_delimiter_chose_the_mark
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
PASSED tests/e2e/test_f2_ingest.py::test_T2_3_synthetic_stock_counts_with_grouped_thousands_are_read[*]   (2 cases: b2b_cases, ecom_mid)
PASSED tests/e2e/test_f2_ingest.py::test_T2_3_semicolon_file_of_dot_3_decimal_weights_carries_a_tie_break_warning
PASSED tests/e2e/test_f2_ingest.py::test_T2_3_one_tie_break_file_among_several_keeps_the_mark_unrecorded
153 passed in 15.96s
```
