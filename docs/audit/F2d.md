# F2d audit: Ingestion remediation (FR decimal shapes, preamble regression, UTF-16 without BOM)

## Verdict: pass_with_issues

All F2 acceptance tests (T2.1 to T2.9), the C5 benchmark and the new F2d regression tests pass: 130 passed, 0 failed and 0 skipped. Mutation checks and an overlay of the pre-F2d `sniff.py` show that the new tests catch the bugs they target.
The verdict stays below `pass` because the last audit round (round 1) left one medium finding open and no fix round followed: a residual silent ×1000 misread of 3-decimal dot values ≥ 1 in `;` files. Six low findings are also open, and both spec audits returned pass_with_issues.

Scope: F2d owns `src/whsizing/io/**`, `src/whsizing/schemas/ingest.py`, `tests/fixtures/ingest/**`, `tests/unit/test_f2_*.py` and `tests/e2e/test_f2_*.py`. The build changed only `src/whsizing/io/sniff.py`, `tests/unit/test_f2_sniff.py` and `tests/e2e/test_f2_ingest.py`. Fix round 1 also changed `parse.number_shape` and `mapping.number_notes` (leading-zero groups). Schema changes: none (`schema_changes: []`). ruff check, ruff format and pyright were reported clean on `src/whsizing/io` and the F2 test files.

It closes these F2c open issues: 1 (date-range preamble taken as the header), 2 (I54 FR decimal shapes) and the BOM-less UTF-16/32 and `%Y%m%d` parts of issue 4.

## Acceptance tests

T2.x are the F2 spec tests (description.md l.700) and C5 is the §4.1 ingest benchmark. The F2d-fix rows are the round-1 fixes as the round-1 spec audit rated them. Test paths are relative to `/Users/skarwech/saas_v1`.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T2.1 | `tests/unit/test_f2_sniff.py::test_T2_1_utf16_and_utf32_without_bom_are_told_by_their_nul_bytes` | pass | New (F2c open issue 4). BOM-less UTF-16-LE/BE and UTF-32-LE/BE tab-separated FR exports read correctly end to end through `read_any`. A euro-heavy UTF-16-LE head and a cp1252 control are included. It fails on the F2c `sniff.py`, and the mutants `no_wide` and `no_utf32_nobom` each fail it. |
| T2.1 | `test_T2_1_utf16_without_bom_with_many_non_latin1_letters` | pass | New in fix round 1. Polish UTF-16 LE and BE without a BOM are detected; UTF-8 with stray NULs stays utf-8. The `wide_090` mutant fails it. The threshold mutants `wide_mostly_030` and `wide_rarely_050` survive (open issue 4). |
| T2.1 | `test_T2_1_encoding_and_delimiter_detection[*]` (6 fixtures) and the BOM, coercion, quote and stray-quote T2_1 tests | pass | The 6 spec fixtures (utf8 `;`, utf8-BOM `,`, cp1252 `;`, latin1 tab, utf8 `\|`, cp1252 quoted `,`) and the F2c UTF-16/32 BOM cases still pass. |
| T2.2 | `test_T2_2_date_range_preamble_is_not_the_header` | pass | New (F2c open issue 1). With dotted and slash 'Période du;..;au;..' preambles, `header_row` is 3, the columns are right and sku/qty_units/snapshot_date map to Référence/Qté/Date stock. It fails on the F2c `sniff.py` (header_row 1), and the `label_ignores_dates` mutant fails it. |
| T2.2 | `test_T2_2_pivoted_date_header_falls_back_to_the_verbatim_rule` | pass (rated **weak** in round 1) | New in fix round 1. 'Référence;Désignation;01/01/2025;01/02/2025;01/03/2025' gives row 0 again. The `no_header_fallback` mutant fails it. It uses only dense numeric data rows, so it misses the sparse or text-heavy data row that wins the strict pass (open issue 2). |
| T2.2 | `test_T2_2_header_on_row_3_csv`, `test_T2_2_header_on_row_3_excel_picks_the_biggest_sheet`, `test_T2_2_header_rule_skips_sparse_and_numeric_rows`, `test_T2_2_leading_blank_line_and_cr_only_line_ends` | pass | The existing header tests still pass. |
| T2.3 | `test_T2_3_ungrouped_and_space_grouped_comma_decimals_are_decimal_comma` | pass | New (I54 amendment). `1037,5`, `1 200,5`, U+00A0 and U+202F grouped decimals sniff `,` and read 1037.5, 1200.5, 2345.25 and 12000.75, in `;` files and in quoted `,` files. Before, the file sniffed `.` and these values were null. Fails on the F2c code. |
| T2.3 | `tests/e2e/test_f2_ingest.py::test_T2_3_synthetic_stock_counts_with_grouped_thousands_are_read[b2b_cases\|ecom_mid]` | pass | New. F1 synthetic exports (150 days, seed 3, defects on), FR and EN. `inventory.csv` sniffs `,` for FR and `.` for EN, every Qté/Quantity cell parses, and the absolute values equal the generated `qty_units` row by row. It also asserts the other mark would lose rows. Fails on the F2c code. |
| T2.3 | `test_T2_3_french_integers_with_dot_thousands_in_a_file_without_decimals`, `test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma` | pass | Re-pointed to the I54 amendment. A `;` integer-only file is `,` and reads 1234 and 2500000; the same file with `,` delimiters is `.` and gives null. Thousands-only shapes are left out of the share. The 80 % threshold is pinned on both sides after fix round 1 (75 % and 799/1000 give `.`, 80 % and 800/1000 give `,`): `threshold_079` and `threshold_081` are both killed. |
| T2.3 | `test_T2_3_leading_zero_three_decimal_weights_in_a_semicolon_file_are_decimals` | pass | New in fix round 1 (round-0 medium). A `;` master with weights `0.125`, `0.250`, `0.369`, ... sniffs `.` and keeps the kg values. The mutants `thousands_leading_zero` and `number_shape_leading_zero` each fail it. The `mapping.number_notes` part of the fix is not pinned (`grouped_shape_leading_zero` survives, near no-op). |
| T2.3 | `tests/e2e/test_f2_ingest.py::test_dot_grouped_quantities_in_a_dot_file_are_counted_in_the_dq_note`, `test_unreadable_numbers_are_explained_in_the_dq_report` | pass | Re-pointed. The DQ-note scenario now uses a `,` file (`.` by the tie-break). The unreadable-number note uses a `;` file holding US `1,500`, which is `,` by the tie-break, reads 1.5 and the note names `decimal: '.'`. The mapping `decimal` override is still tested here and in test_f2_mapping. |
| T2.3 | the other `test_T2_3_*` tests in test_f2_sniff.py and test_f2_mapping.py | pass | Unchanged F2c cases (thousand dots/commas, int64 overflow, garbage, dotted codes) still pass. |
| T2.4 | `test_T2_4_all_digit_yyyymmdd_column_names_the_file_date_format` | pass | New (F2c open issue 4). An all-digit `%Y%m%d` column sets `SniffResult.date_format`; an 8-digit id column stays None. Its negative case was rewritten in fix round 1 (ids 20_000_000+37i, month 00), so the `yyyymmdd_loose` mutant is now killed. Date-valid sequential ids still give `%Y%m%d` (open issue 6). |
| T2.4 | `test_T2_4_each_date_format[*]` (14 formats) and the dotted, mixed, ambiguous, 2-digit-year and DST tests | pass | Unchanged; every step-5 format, Excel serial included, is checked at column level. |
| T2.5 | `tests/unit/test_f2_mapping.py::test_T2_5_*` (3 tests) | pass | Unchanged by F2d. The realistic FR/EN synthetic ingest maps with the same results in both rounds. |
| T2.6 | `tests/unit/test_f2_rules.py::test_T2_6_*` (R1-R14 fixtures and threshold tests) | pass | Unchanged by F2d; `rules.py` was not touched. |
| T2.7 | `tests/unit/test_f2_rules.py::test_T2_7_*` | pass | Unchanged. The realistic runs give the same DQ scores before and after F2d (63.51 and 60.9). |
| T2.8 | `tests/unit/test_f2_anonymize.py::test_T2_8_*` (3 tests) | pass | Unchanged by F2d. |
| T2.9 | `tests/e2e/test_f2_ingest.py::test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation` | pass | Tightened: the canonical inventory qty sum must equal the source sum. On the F2c code it fails (335,683 vs 1,135,619): F2c silently dropped 169 of 2,400 `1,234` stock rows. The `no_thousands_exclusion` mutant also fails it. Wall time 0.4-0.5 s (budget 15 min). |
| C5 | `tests/e2e/test_f2_ingest.py::test_C5_bench_ingest_and_validate_1m_line_csv` | pass | 1,030,012 order lines plus master, stock and receipts are ingested and validated in 2.7-2.8 s (budget 120 s). |
| F2 Done-when | DQ report readable by a non-technical reader | not_applicable | Needs the business lead's review. |

## Proofs

All proofs were captured by the auditors during the audit (round 0 or round 1). Proofs 6, 7, 9 and 10 were re-run while writing this record on 2026-11-08, and the output was unchanged. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F2d/`, written `<audit>/` below. All commands were run from `/Users/skarwech/saas_v1`. The round-0 and round-1 proof audits returned pass_with_issues with no findings and no proofs listed, so every proof below comes from the spec audits.

1. **The new and tightened tests catch the pre-F2d code** (round 0). The F2c `sniff.py` (only `sniff.py` differs in `io/`) is put on an overlay PYTHONPATH. 9 F2 tests fail; the audit record clips the list after 7 names.
   Command: `PYTHONPATH=<audit>/overlay uv run pytest tests/unit/test_f2_*.py tests/e2e/test_f2_*.py -q -p no:cacheprovider`
   ```
   FAILED test_T2_3_french_integers_with_dot_thousands_in_a_file_without_decimals
   FAILED test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma
   FAILED test_T2_3_ungrouped_and_space_grouped_comma_decimals_are_decimal_comma
   FAILED test_T2_2_date_range_preamble_is_not_the_header
   FAILED test_T2_1_utf16_and_utf32_without_bom_are_told_by_their_nul_bytes
   FAILED test_T2_4_all_digit_yyyymmdd_column_names_the_file_date_format
   FAILED test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation
   ```

2. **Every build code path is guarded: 9 of 10 single-point mutants of `sniff.py` are killed** (round 0). The survivor `threshold_079` became round-0 finding 6 and was killed after fix round 1 (proof 8).
   Command: `for m in no_thousands_exclusion tiebreak_always_dot ... threshold_081; do uv run python <audit>/mutate.py $m; done`
   ```
   no_thousands_exclusion 5 failed | tiebreak_always_dot 4 failed | no_ungrouped_evidence 1 failed | no_space_grouped_evidence 1 failed | label_ignores_dates 1 failed | no_wide 1 failed | no_utf32_nobom 1 failed | no_yyyymmdd 1 failed | threshold_079 88 passed (survives) | threshold_081 2 failed
   ```

3. **FR Excel CSV decimal shapes (I54 amendment) read exactly through `ingest()`** (round 0). The input is a 200-row sku_master in mm with 112 values ≥ 1000, written ungrouped (`1037,5`) and NBSP-, narrow-NBSP- and space-grouped.
   Command: `uv run python <audit>/probe2.py <audit>/p2`
   ```
   A3_ungrouped decimal , | 112 grouped/4-digit lengths | length/width/weight exact: True | nulls 0
   A3_nbsp decimal , | ... exact: True | nulls 0
   A3_nnbsp decimal , | ... exact: True | nulls 0
   A3_space decimal , | ... exact: True | nulls 0
   ```

4. **A large BOM-less UTF-16-LE export ingests identically to its cp1252 original** (round 0). The F1 FR order_lines (83,073 rows, about 10 MB, more than the 1 MB sniff head) were re-encoded as BOM-less UTF-16-LE with tabs. The canonical table equals the `;` cp1252 original apart from `source_file`. The saved mapping keeps utf-16-le and is reused non-interactively. A 'Période du' preamble gives header row 3.
   Command: `uv run python <audit>/e2e_probes.py <audit>/e2e` (then a column diff against the base)
   ```
   B utf16le utf-16-le '\t' 83073 82680 | qty sum 1912676 vs base 1912676
   B saved mapping encoding utf-16-le delimiter '\t'
   B reuse non-interactive utf-16-le 82680
   C preamble header_row 3 ['Référence', 'Qté', 'Date stock']
   B_utf16 differs: source_file only; C_preamble differs: source_file, source_row [2,3,4]->[4,5,6]
   ```

5. **The builder's realistic before/after claims reproduce** (round 0, and identical again in round 1). F1 synthetic b2b_cases and ecom_mid, 150 days, seed 3, defects on. Inventory REQ goes 226 → 51 (b2b) and 154 → 136 (ecom); the remaining REQ rows are the negative-quantity defect rows. The unreadable-number notes disappear in FR and EN, and the DQ scores are unchanged.
   Command: `uv run python <audit>/realistic.py <audit>/real_new ; PYTHONPATH=<audit>/overlay uv run python <audit>/realistic.py <audit>/real_old`
   ```
   NEW: b2b_cases csv_fr score=63.51 inventory [','] 8000 7949 {'REQ': 51}; ecom_mid csv_fr score=60.9 inventory [','] 20000 19864 {'REQ': 136}; EN mirrors ['.'] same counts; no inventory notes
   OLD: b2b_cases csv_fr inventory ['.'] 8000 7774 {'REQ': 226} note: 176 values are not whole numbers ...; ecom_mid ['.'] {'REQ': 154} note: 18 values ...
   ```

6. **Round-0 medium found and fixed: leading-0 3-decimal weights in a `;` file** (round 0 negative proof, round 1 fix proof, re-run while writing this record). Before fix round 1, the weights were read ×1000 with no DQ signal, while the pre-F2d code read them correctly. After the fix they read correctly.
   Command: `uv run python <audit>/probe_light.py <out>` (and with the F2c overlay)
   ```
   round 0, F2d build: L decimal , | weight_kg [125.0, 250.0, 369.0, 80.0, 450.0, 200.0] source ['0.125', '0.250', '0.369', '0.080', '0.450', '0.200'] | non-ok [('R14', 'warning')] | notes []
   round 0, F2c overlay: L decimal . | weight_kg [0.125, 0.25, 0.369, 0.08, 0.45, 0.2]
   round 1 and 2026-11-08: L decimal . | weight_kg [0.125, 0.25, 0.369, 0.08, 0.45, 0.2] source ['0.125', '0.250', '0.369', '0.080', '0.450', '0.200']
   ```

7. **A residual silent ×1000 remains (open medium)** (round 1, re-run while writing this record). When the only separator-bearing values in a `;` file are 3-decimal dot values ≥ 1 among integers, the tie-break gives `,` and `1.250` kg becomes 1250 kg with only the unrelated R14 warning and no note. When every value has that shape, W_UNITS_WEIGHT stops the ingest.
   Command: `uv run python <audit>/r1_probes.py <out>`
   ```
   P1_fixed3_ge1 decimal , | MappingError: sku_master W_UNITS_WEIGHT: median weight is 1787.5 (> 500); values look like g...
   P2_ints_plus_1.250 decimal , | weight [2.0, 5.0, 10.0, 1250.0, 3.0, 4.0] | length [300.0, 301.0, 302.0] | non-ok [('R14', 'warning')] | notes 0
   P4_fr_stray_dot decimal , | weight [0.125, 0.25, 1.5, None, 2.75, 0.3] | ... non-ok [('R7', 'warning'), ('R14', 'warning')] | notes 1
   ```

8. **The fix-round-1 tests catch what they target; three secondary items are not pinned** (round 1).
   Command: `for m in thousands_leading_zero ... yyyymmdd_loose; do uv run python <audit>/mutate_r1.py $m; done`
   ```
   thousands_leading_zero 1 failed, 90 passed | number_shape_leading_zero 1 failed | grouped_shape_leading_zero 91 passed | no_header_fallback 1 failed | wide_090 1 failed | wide_rarely_050 91 passed | wide_mostly_030 91 passed | threshold_079 1 failed | threshold_081 2 failed | yyyymmdd_loose 1 failed
   ```

9. **The 80 % [P] threshold is applied exactly, and `number_shape` never reads a leading-0 group as thousands** (round 1, re-run while writing this record). P5 inputs are `0.125, 0,125, 1.250, 1,250, -0,5, 0.000, 10.000,5, 01.234`.
   Command: `uv run python <audit>/r1_probes.py <out>`
   ```
   P8 799/1000 -> . | 800/1000 -> ,
   P5 ',' -> [None, 0.125, 1250.0, 1.25, -0.5, None, 10000.5, None]
   P5 '.' -> [0.125, None, 1.25, 1250.0, None, 0.0, None, 1.234]
   P9 ';' 0,125 only -> , | tab 0,125 -> , | ',' 0.125 -> .
   ```

10. **Edge cases on the current tree** (round 1, re-run while writing this record). Polish UTF-16 without a BOM is detected, the pivoted header gives row 0 with dense data, and UTF-8 with stray NULs stays utf-8. The sparse-data pivot and Cyrillic UTF-16 limits are still present.
    Command: `uv run python <audit>/edge.py` and `uv run python <audit>/r1_probes.py <out>`
    ```
    E1 utf8 with 3 stray NULs: utf-8
    E2 utf-16-le Polish (pre-existing path): utf-16-le | wide: utf-16-le
    E10 pivoted date header -> 0
    E11 'Édité le;<datetime>;par;user' preamble -> header index 0
    E13 8-digit ids 20240101..20240128 -> %Y%m%d
    P6 pivot, dense data -> 0 | P6 pivot, sparse data row -> 1 | P6 pivot, text data row -> 1
    P7 ru utf-16-le no BOM -> utf-8 | P7 el utf-16-le no BOM -> utf-16-le | P7 odd-length utf-16-le (+1 byte) -> cp1252
    ```

## Audit rounds

### Build (before round 0)

All changes are in `src/whsizing/io/sniff.py`:

- **I54 amendment, as registered.** `detect_decimal(columns, delimiter)` leaves out plain integers, dotted dates and thousands-only shapes `^\d{1,3}([.,]\d{3})+$`. Three shapes count as comma evidence: the verbatim step-4 regex, `^\d{4,},\d+$` and `^\d{1,3}([ U+00A0 U+202F]\d{3})+,\d+$`. If no separator-bearing value is left, `;` gives `,` and any other delimiter (or Excel, delimiter None) gives `.`. An explicit mapping `decimal` still overrides the sniff.
- **Header step 3.** A cell counts as text only when it is neither numeric nor date-shaped (`_is_label` with `_DATE_CELL`: d.m.Y, d/m/Y, d-m-Y and Y-m-d with an optional time).
- **BOM-less UTF-16/32.** `_wide_without_bom` reads the NUL-byte offsets in the first 4 KB, after the BOM check and before charset_normalizer, and returns endian-explicit utf-32-le/be or utf-16-le/be. Repro: charset_normalizer returned None on a 30-row tab-separated UTF-16-LE FR export, and F2c read it as cp1252.
- **`%Y%m%d`.** An all-digit column matching the strict regex at ≥ 98 % sets `date_format`, only when no text date column is found. Excel serials are deliberately not used at file level (5-digit quantities and postcodes look the same); per-column parsing still reads them.

The builder flagged the 3-decimal hazard itself before round 0: values such as `0.369` or `12.500` also match the registered thousands-only shape, so a `;` file whose only separator values have that shape is sniffed `,` and reads `0.369` as 369. It was left unchanged as the registered I54 text ([VERIFY]). Round 0 confirmed it end to end (finding 1).

`parse.py` was not changed in the build: `parse_number` already strips space, U+00A0 and U+202F thousands separators. The builder reported all 6 new or tightened tests fail with the F2c `sniff.py` on PYTHONPATH (the auditor's overlay found 9 failing F2 tests, proof 1).

### Round 0: tests 127 passed, 0 failed

The spec audit returned **pass_with_issues** with every T-id pass (T2.4's negative half noted as weak). The proof audit returned **pass_with_issues** with no findings listed.

| # | Severity | Finding | Resolution (fix round 1) |
|---|---|---|---|
| 1 | medium | The I54 amendment as registered reads 3-decimal dot values as thousands (×1000) in `;` files whose only separator values have exactly 3 decimals. `0.125` matched `_THOUSANDS_ONLY`, and `parse_number(',')` accepted it as 125. Regression from F2c on that input (proof 6). | **Fixed.** A thousands group must now start with `[1-9]\d{0,2}` instead of `\d{1,3}`, in `sniff._THOUSANDS_ONLY`, `parse.number_shape` and `mapping.number_notes`. `0.125` stays in the share as dot evidence and is never read as 125 under either mark. New test `test_T2_3_leading_zero_three_decimal_weights_in_a_semicolon_file_are_decimals`. This narrows the regex that I54 registers verbatim (blocker for the INTERPRETATIONS owner). Not fully closed: `1.250`-type values remain (round-1 medium). |
| 2 | low | Step-3 regression for pivoted headers with date labels ('Référence;Désignation;01/01/2025;...'): no row qualified, MappingError 'no header row found', pointing at the wrong cause. | **Fixed.** `detect_header_row` runs a second pass with the verbatim rule (a non-numeric cell is text) when the date-aware pass finds no row. New test `test_T2_2_pivoted_date_header_falls_back_to_the_verbatim_rule`. Side effect found in round 1 (open issue 2). |
| 3 | low | File-level `%Y%m%d` gives a false positive on sequential 8-digit ids that are valid dates; the test's negative case (ids starting with `10`) could not match the regex by construction. | **Fixed (test only).** The negative case now uses ids 20_000_000+37i (month 00), which kills the loose mutant. The behaviour is kept as spec step 5 verbatim: ids 20240101..20240128 still give `%Y%m%d` (open issue 6). |
| 4 | low | BOM-less UTF-16 heavy in non-Latin-1 letters (Polish) fell back to cp1252 because of the 90 % NUL threshold. Not a regression. | **Fixed.** `WIDE_MIN_NUL_SHARE=0.9` is split into `WIDE_MOSTLY_NUL=0.5` (high bytes) and `WIDE_RARELY_NUL=0.1` (low bytes). New test `test_T2_1_utf16_without_bom_with_many_non_latin1_letters`. Greek, Cyrillic and CJK are left to charset_normalizer (`ponytail:` note). |
| 5 | low | The step-1 NUL-byte heuristic and the step-3 date-cell rule are not registered in `docs/INTERPRETATIONS.md`. | **Deferred.** Outside F2d's paths; the exact text is in the builder's blockers. |
| 6 | low | The 80 % threshold was not pinned from below: `threshold_079` survived (88 passed). | **Fixed.** 799/1000 gives `.` and 800/1000 gives `,`; `threshold_079` now fails. |
| 7 | low | File-level `SniffResult.date_format` never names the Excel serial format that step 5 lists. | **Deferred (by design).** Documented `ponytail:` shortcut: at file level 5-digit integers 20000-60000 cannot be told apart from serial dates. Column-level parsing reads serials, and the T2_4 excel_serial case passes. |

Fix round 1 totals: 5 fixed (one of them test only) and 2 deferred.

### Round 1: tests 130 passed, 0 failed

The spec audit returned **pass_with_issues**: T2.1-T2.9 pass, F2d-fix1 and F2d-fix6 pass, F2d-fix2 and F2d-fix4 rated **weak**, F2 Done-when not_applicable. The proof audit returned **pass_with_issues** with no findings listed. No fix round followed, so every round-1 finding is open.

| Severity | Finding | Status |
|---|---|---|
| medium | Residual of round-0 #1. In a `;` file whose only separator-bearing values are 3-decimal dot values ≥ 1 among integers (`2;5;10;1.250;3;4`), they are all excluded as thousands-only, the I54 `;` tie-break gives `,`, and `1.250` kg becomes 1250 kg with no warning. R8 does not fire (1250 < 1500 kg), W_UNITS_WEIGHT does not fire (median 4 < 500) and there is no DQ note, because `number_notes` flags thousands-shaped values only in int columns. | **Open.** This follows the I54 amendment as registered ([VERIFY]); the spec owner needs to decide. Reproduced on 2026-11-08 (proof 7). |
| low | Side effect of the round-0 #2 fix: in a pivoted header followed by a sparse or text-heavy data row, that data row passes the strict pass and is taken as the header (index 1); F2c returned 0. Pivoted files cannot be mapped either way, only the reported header and the error that follows are wrong. | **Open.** Reproduced on 2026-11-08 (proof 10). |
| low | Round-0 #5 still unresolved. `docs/INTERPRETATIONS.md` lacks the step-1 NUL-byte rule (now 50 % / 10 %), the step-3 date-cell rule with its verbatim fallback, and the leading-zero refinement. The code's `_THOUSANDS_ONLY = ^[1-9]\d{0,2}([.,]\d{3})+$` and `parse.number_shape` no longer match the I54 regex `^\d{1,3}([.,]\d{3})+$`. | **Open, outside F2d's paths.** Checked while writing this record: I54 (l.416-428) still reads `^\d{1,3}([.,]\d{3})+$`. |
| low | Thresholds pinned from one side only: `wide_mostly_030` and `wide_rarely_050` (overlapping at 0.5/0.5) pass every F2 test, so the "no overlap, LE/BE stay distinguishable" claim is unguarded. The `mapping.py` grouped-shape change to `[1-9]` is also unpinned (its only effect is `0.000` in an int column). | **Open** (proof 8). |
| low | Documented ceiling of round-0 #4. BOM-less UTF-16 Cyrillic has every byte < 0x80, so charset_normalizer says ascii/utf_8; the file decodes to NUL-laden column names with no read error, and non-interactive mapping fails with a misleading 'unmapped targets' error. A UTF-16 file with one stray trailing byte falls back to cp1252. Same behaviour as before F2d. | **Open** (proof 10). |
| low | Round-0 #3 behaviour kept: sequential 8-digit ids that are valid dates (20240101..20240128) still set `%Y%m%d` as the file `date_format`, saved in `mapping/<dataset>.yaml`. Cosmetic, because `parse_datetime` coalesces every format; spec step 5 as written. | **Open, accepted** (proof 10). |
| low | Round-0 #7 unresolved by design: the file-level `date_format` never names the Excel serial format. | **Open, deferred** (documented `ponytail:` note). |

## Open issues

1. **Medium, [VERIFY] decision needed:** in a `;` file, 3-decimal dot values ≥ 1 that are the only separator-bearing values (for example `1.250` among integer weights) are read ×1000 with no DQ signal (proof 7). When all values have that shape, W_UNITS_WEIGHT stops the ingest. This is the I54 amendment as registered; the spec owner must decide whether to keep the `;` tie-break for float columns or to flag such values in `number_notes`.
2. **Low:** a pivoted date header followed by a sparse or text-heavy data row takes that data row as the header (index 1). The test covers only dense data. (An 'Édité le;<datetime>;par;user' preamble is still taken as the header, E11; that is spec step 3 as written and the auditor did not charge it to F2d.)
3. **Low, docs outside F2d's paths:** `docs/INTERPRETATIONS.md` needs the step-1 NUL-byte UTF-16/32 rule (≥ 50 % NUL at high-byte offsets, < 10 % at low-byte offsets, first 4 KB, before charset_normalizer, mostly-Latin text), the step-3 date-cell rule with its verbatim fallback, and the I54 leading-zero refinement (`^[1-9]\d{0,2}([.,]\d{3})+$`). The date-cell exclusion for the decimal share is already in I54 and should not be added again.
4. **Low, test gaps:** the BOM-less UTF-16/32 thresholds (`WIDE_MOSTLY_NUL`, `WIDE_RARELY_NUL`) and the `mapping.number_notes` leading-zero change are not pinned by any test.
5. **Low, known ceiling:** BOM-less UTF-16 Cyrillic (and CJK) is decoded as UTF-8 garbage with a misleading mapping error; an odd-length UTF-16 file falls back to cp1252. Unchanged from F2c.
6. **Low, accepted:** date-valid sequential 8-digit ids set `date_format` to `%Y%m%d` (cosmetic, spec step 5 verbatim).
7. **Low, deferred by design:** file-level `date_format` never names the Excel serial format.
8. **Builder blockers outside F2d:**
   - The audit owner should close F2c open issues 1, 2 and the BOM-less UTF-16/32 and `%Y%m%d` parts of issue 4, which F2d fixes.
   - `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` fails (hypothesis seed 531, `0.003281593932 != 0.0032815939320000004` in `eiq.cube_per_order_m3.p50`). It fails the same way with the F2c `sniff.py` and does not touch `whsizing.io`; it belongs to the F3 owner.
   - The T0.1 ruff and pyright gates in `test_f0_tooling` failed once during a full-suite run, most likely during concurrent edits; a re-run passed and repo-wide ruff and pyright were clean.

## Not applicable here and why

- **F2 Done-when, DQ report readable by a non-technical reader:** needs the business lead's review. `test_dq_html_is_readable_and_escaped` checks only structure and escaping.
- **Real client data:** none is available here, and client data must not leave the machine. Ingest was exercised on the F1 synthetic b2b_cases and ecom_mid sets (FR and EN, with defects), on an 83,073-row UTF-16 re-encoding of F1 order lines, on the C5 1M-line bench and on the fixtures under `tests/fixtures/ingest/`.
- **[VERIFY] decision on the I54 amendment and its leading-zero refinement:** needs the spec owner (open issues 1 and 3).
- **Edits to `docs/INTERPRETATIONS.md`:** outside F2d's paths (open issue 3).
- **Docker and GitHub CI:** F2 does not depend on either, and no F2 test is skipped.

## Fresh test output (run while writing this record, 2026-11-08)

Captured log lines are removed and parametrized cases are collapsed.

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
130 passed in 13.29s
```
