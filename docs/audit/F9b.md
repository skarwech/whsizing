# F9b audit record: Excel report (XlsxWriter), 12 sheets, FR/EN, trace comments, integrity gate

Written 2026-11-09 from the audit history of the F9b build (one audit round, round 0 on the initial build, with a spec-compliance auditor and a runtime-proof auditor; no fix round and no round 1 were run) and from a fresh test run, ruff and pyright run made while writing this record.

## Final verdict: pass_with_issues

- Fresh run: 71 passed, 0 failed, 0 skipped over the F9b test globs (57 Excel tests in 3 files, plus 14 i18n tests that the glob `tests/unit/test_f9_i18n*.py` also picks up: 10 in `test_f9_i18n.py` and 4 in F9c's `test_f9_i18n_pdf.py`); every F9b-owned acceptance id (T9.1, T9.2, T9.5, and T9.7 for the Excel half) has real assertions, and both round 0 auditors returned `pass_with_issues` with no high or medium finding.
- Only round 0 was run, so the eight distinct low findings are all still open (the F9b conventions are not registered in `docs/INTERPRETATIONS.md`, the layout was never seen in Excel or LibreOffice, FR/EN separators follow the viewer's locale, and five more, see Open issues); T9.3 (PDF) and the 60 s budget for both files are F9c's and were not exercised here.

## Acceptance tests

Entry point: `whsizing.report.build_excel(run, lang)` in `src/whsizing/report/excel.py` (440 lines). It writes `<run>/report/report_<lang>.xlsx` and `<run>/report/trace.jsonl`. It calls `assert_integrity` first, builds the workbook in memory, checks the Excel strings for untranslated sentinels (IC8), and only then writes the two files. `render_workbook(data, charts) -> bytes` is the pure core the property tests call. It renders `Cell` values from the F9a tables and computes no number itself.

Test files (abbreviations used in the table):

- `U` = `tests/unit/test_f9_excel.py` (45 items; `tests/unit/test_f9_excel_support.py` is a support module with no tests)
- `E` = `tests/e2e/test_f9_excel_e2e.py` (9 items, synthetic `ecom_mid`)
- `P` = `tests/property/test_f9_excel_properties.py` (3 items, Hypothesis)
- `I` = `tests/unit/test_f9_i18n.py` (10 items, F9a-owned; F9b added one key, `excel.trace`, to both language files and these parity tests cover it)

Spec ids: T9.1 Excel opens with 12 sheets and expected headers, T9.2 Summary values equal `comparison.json` (snapshot), T9.3 PDF (F9c), T9.4 integrity IC1-IC8 (F9a), T9.5 FR and EN identical, T9.6 block diagram (F9a), T9.7 build time of both files (60 s). Rows marked `extra` are F9b tests beyond the spec ids.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T9.1 | `U::test_T9_1_the_workbook_opens_with_the_twelve_sheets_in_order[en,fr]` | pass | openpyxl opens the file; exactly 12 visible sheets in spec order; sheet names asserted as literal EN and FR lists. |
| T9.1 | `U::test_T9_1_every_sheet_has_its_title_and_header_cells[en,fr]` | pass | Per sheet, the first block title (A3) and the header row equal written-out literals (not rebuilt from i18n), FR and EN. |
| T9.1 | `U::test_T9_1_the_sheet_name_never_holds_a_character_excel_forbids` | pass | `Capex / Opex` becomes the sheet `Capex - Opex` (Excel forbids `/`); the title cell A1 keeps the i18n text. |
| T9.1 | `E::test_T9_1_ecom_mid_workbook_has_the_twelve_sheets_and_their_headers[en,fr]` | pass | Same 12-sheet and header checks on synthetic `ecom_mid`, plus the frozen header row. |
| T9.2 | `U::test_T9_2_summary_values_equal_comparison_json[en,fr]` | pass | Every `ComparisonRow` field of `comparison/comparison.json` (ranges lo/typ/hi, scalars, equipment, fit) equals its Summary cell; numbers come from the JSON, not from the report model; a new JSON field without a row fails. Not a syrupy snapshot (see Open issues). |
| T9.2 | `U::test_T9_2_scenario_sheets_equal_result_and_finance_json` | pass | Scenarios area total, FTE total heads, Capex total, TCO and Cash flow own flows equal `result.json` and `finance.json`. |
| T9.2 | `U::test_T9_2_every_numeric_model_cell_is_a_number_in_the_sheets[en,fr]` | pass | The numeric cells of the report model (more than 2000) are exactly the numeric cells of the workbook; none became text. |
| T9.2 | `E::test_T9_2_ecom_mid_summary_equals_comparison_json[en,fr]` | pass | Summary equals `comparison.json` on `ecom_mid`. |
| T9.5 | `U::test_T9_5_fr_and_en_workbooks_hold_identical_numeric_cells` | pass | Same coordinates and values on every sheet in FR and EN; same merges, comments, freeze panes, autofilter and image anchors. |
| T9.5 | `U::test_T9_5_the_build_is_deterministic` | pass | Two renders give identical bytes. |
| T9.5 | `E::test_T9_5_ecom_mid_fr_and_en_workbooks_hold_identical_numbers` | pass | `ecom_mid` FR and EN hold identical numbers; comment count equals the traced-cell count (more than 1000). Excel half only; the rendered PDF half is F9c. |
| T9.5 | `P::test_T9_5_property_random_content_never_turns_a_number_into_text_or_text_into_a_number` | pass | Random cells (text like `=1+1`, `123`, dates, traced cells with no node, not-computed columns) keep every number numeric and every text a string, no formula cell, comments exactly on traced cells, no comment lost in a merged range. It found two real defects during the build (see Audit rounds). |
| T9.5 | `P::test_T9_5_property_fr_and_en_hold_the_same_numbers_at_the_same_coordinates` | pass | FR and EN numeric cells identical for random content. |
| T9.7 | `E::test_T9_7_the_excel_report_builds_within_budget[en,fr]` | pass | Excel half only: build under 30 s per language (half of the 60 s budget for both files) and size above 50 kB on `ecom_mid`; fresh run 0.50 s EN (359 kB) and 0.60 s FR (363 kB). The 60 s budget for both files cannot be closed until F9c's half exists. |
| T9.3 | none in F9b | not_applicable | PDF page count and run id: F9c. |
| T9.4 | none in F9b (gate tests below are `extra`) | not_applicable | IC1-IC8 tamper tests are F9a (`tests/unit/test_f9_integrity.py`). F9b only calls the gate. |
| T9.6 | none in F9b | not_applicable | Block diagram area: F9a. |
| extra | `U::test_header_row_is_frozen_on_every_sheet[en,fr]` | pass | Freeze panes at the first block header and the label column on all 12 sheets. |
| extra | `U::test_number_formats_and_values_stay_numbers` | pass | `#,##0`, `#,##0.0`, `#,##0.00`, `0.0 %` per row; shares stay 0..1; the fit flag stays 1/0 with a yes/no (Oui/Non) format; dates are real dates. |
| extra | `U::test_the_fit_flag_has_a_green_and_a_red_conditional_format` | pass | Two conditional-format rules per fit row (green on 1, red on 0, blanks untouched); a run where S1 does not fit gives 0. |
| extra | `U::test_scenarios_sheet_has_lo_typ_hi_columns_per_scenario` | pass | Low/Typical/High under a merged scenario group header. |
| extra | `U::test_assumptions_have_one_row_per_param_and_the_filter_is_on` | pass | One row per catalog `Param`; autofilter A4:L<4+n> only on Assumptions. |
| extra | `U::test_print_setup_is_landscape_a4_one_page_wide_with_the_run_id_in_the_footer` | pass | Landscape, A4, fit to one page wide, run id in the footer, on every sheet. |
| extra | `U::test_demand_profile_carries_the_charts_as_images_below_the_tables` | pass | 5 PNG demand charts placed below the tables; no images on other sheets. |
| extra | `U::test_summary_carries_the_indicative_banner_and_the_confidence_note` | pass | Banner in A2 and the localised confidence note, FR and EN. |
| extra | `U::test_methodology_has_the_formulas_one_row_per_line_and_the_versions` | pass | Appendix B text split one row per line; run id in the versions block. |
| extra | `U::test_every_traced_cell_has_a_comment_with_its_trace_id_and_formula[en,fr]` | pass | A comment on every traced cell (more than 1000) with id, world, label, formula and inputs; the cell value equals the node value in the exported `trace.jsonl`. |
| extra | `U::test_the_exported_trace_resolves_every_cited_id` | pass | `report/trace.jsonl` is written, every cited id resolves, it includes the report-only `n_warnings` node, FR and EN bytes identical. |
| extra | `E::test_ecom_mid_every_summary_number_has_a_comment_that_resolves_in_the_exported_trace` | pass | On `ecom_mid`, the S2 TCO cell comment starts with `Trace S2.finance.tco (typ world)`, holds the node formula and every input id, and the cell equals the node value to 1e-12. |
| extra | `U::test_no_untranslated_text_in_the_cells_or_the_comments[en,fr]` | pass | No `{{ missing: }}` sentinel in any string cell or comment. |
| extra | `U::test_the_workbook_is_value_only_with_no_formula_in_any_cell` | pass | Cell types limited to number, string, date (live formulas stretch not built). |
| extra | `U::test_a_scenario_not_computed_is_a_grey_column_with_the_reason` | pass | Grey merged region with the reason in Summary and Cash flow, no numbers or comments there; other scenarios keep their numbers. |
| extra | `U::test_a_run_without_a_baseline_shows_absolute_values_and_no_npv_or_payback` | pass | No NPV or payback rows, no delta column, the no-baseline limit text present. |
| extra | `U::test_a_scenario_as_the_baseline_has_no_delta_and_no_cumulative_column` | pass | With S0 as baseline, one Cash flow column for S0. |
| extra | `E::test_ecom_mid_with_a_scenario_as_the_baseline_builds_and_keeps_the_gate_open` | pass | S0 baseline on `ecom_mid`: integrity holds and the workbook builds. |
| extra | `U::test_an_integrity_failure_raises_exit_5_and_writes_nothing` | pass | Tampered comparison row raises `ReportIntegrityError` IC1 with `exit_code` 5; no `report/` folder, no xlsx, no `trace.jsonl`. |
| extra | `U::test_an_untranslated_text_fails_the_build_before_any_file_is_written` | pass | IC8 on the Excel strings fails before any file is written. |
| extra | `U::test_an_unsupported_language_is_a_config_error_and_writes_nothing` | pass | `build_excel(run, "de")` raises `ConfigError`, nothing written. |
| extra | `U::test_the_workbook_of_an_unreadable_output_folder_is_a_whsizing_error` | pass | A file where `report/` should be raises a `WhsizingError`, not a bare OS error. |
| extra | `U::test_cell_content_*` (9 items: 6 numeric formats, bool, text and keys, refusals) | pass | The pure cell writer: a numeric format in gives a number out, never a string; text and keys are never formulas; text in a numeric cell and non-finite or out-of-Excel-range numbers are refused. |
| extra | `U::test_build_excel_is_the_function_the_cli_looks_up` | pass | `whsizing.report.build_excel` is `excel.build_excel` and is in `__all__` (what `cli build_reports` looks up). |
| extra | `P::test_property_strategies_reach_the_hard_cases` | pass | Guard against a vacuous property (derandomized): formula-looking text, unresolvable trace ids, dates and not-computed columns are drawn. |
| extra | `I::test_T9_5_*` (10 items) | pass | F9a's i18n parity: same keys, same placeholders, sentinel on a missing key, FR and EN number and date formats, every table key exists in both languages. Covers the new `excel.trace` key. |
| extra | `tests/unit/test_f9_i18n_pdf.py::test_F9c_i18n_*` (4 items) | pass | F9c's key parity for the PDF texts; picked up by the glob, not F9b's. |

No test carries a skip marker (0 skipped in the fresh run).

## Proofs

Captured by the two round 0 auditors during the audit (not re-run for this record, except the first, which this record's fresh run reproduces). Paths under `$A` are in the audit scratchpad `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F9b`.

1. **The F9b suites pass.** Command: `cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f9_excel*.py tests/e2e/test_f9_excel*.py tests/property/test_f9_excel*.py tests/unit/test_f9_i18n*.py -q -rA`. Spec auditor: `67 passed in 55.01s`, plus 86 passed in 13.19s for the F9a regression suites, ruff "All checks passed!", pyright "0 errors, 0 warnings, 0 informations". Proof auditor: `67 passed in 55.32s`, then `71 passed in 45.74s` after F9c's `test_f9_i18n_pdf.py` appeared (45 + 9 + 3 + 10 + 4).
2. **T9.2 checked without the test helper.** Script `t92.py`: `independent T9.2 spot check: 54 cells compared against comparison.json, 0 mismatches` (capex, TCO, NPV, total area, opex y1, cost per line, x lo/typ/hi x 3 scenarios).
3. **Cash flow is consistent with finance.json and the NPV is right.** Script `indep.py` reads `report_en.xlsx` and `scenarios/S*/finance.json`: `Cumulative max |running sum - cell| = 4.66e-10 / 9.31e-10 / 2.33e-10; S0 own flows eq True, delta eq True; npv hand 6440249.74 json 6440249.74 summary 6440249.741149231; S1 6103034.36`; S1 and S2 NPV recomputed by hand (6103034.36, 6065551.48) equal the Summary typ cells.
4. **The rendered workbook is internally consistent (IC4, IC5, IC6 recomputed on the xlsx, not on the model).** Script `consist2.py`: `IC4 on the workbook: max |sum(zones) - total| over 9 columns = 5.68e-14`, `IC5 ... max |sum(activities) - total| = 6.66e-16`, `IC6 col 4: 4.66e-10, col 7: 9.31e-10, col 10: 2.33e-10`.
5. **Real CLI path on a run loaded from disk.** Command: `uv run whsizing report $A/cli_run --lang both --formats xlsx && uv run python $A/dump.py $A/cli_run/report/report_en.xlsx`. Output: `report_fr.xlsx` and `report_en.xlsx` written, `trace.jsonl` 1281287 bytes, `formula tags: 0`, `Summary nums=127 comments=126 freeze=B6`, `Scenarios nums=286 comments=286`, `FTE nums=477 comments=477`, `Capex - Opex nums=231 comments=231`, `Assumptions filter=A4:L76`; FR sheets `Synthese, Base de dimensionnement, Profil de la demande, ... Methodologie`. The CLI logged `stage_done stage=report duration_s=1.018998` for both languages including the integrity check.
6. **Determinism across processes and fresh folders.** Command: `shasum -a 256 $A/cli_run/report/report_*.xlsx $A/cli_run/report/trace.jsonl > h1.txt`, rebuild on a fresh copy of the run with `report/` removed, `diff h1.txt h2.txt`. Result: `IDENTICAL across processes and fresh folders` (xlsx EN and FR and `trace.jsonl`).
7. **The integrity gate works through the real CLI.** The auditor doubled `S1.capex.total` (typ) in `$A/run_tamper/scenarios/S1/trace.jsonl`, then `uv run whsizing report $A/run_tamper --lang en --formats xlsx; echo exit=$?; ls $A/run_tamper/report`. Output: `error: 2 integrity check(s) failed`, `IC1 summary/comparison/capex/S1.typ: cell value 369466.65 differs from trace node S1.capex.total: 738933.30`, `exit=5`, `ls: report: No such file or directory`.
8. **Edge runs build in FR and EN.** Scripts `probe1.py` to `probe4.py`: no sensitivity (Sensitivity sheet holds only the title and `The sensitivity analysis was not run for this study.`), one scenario (12 sheets), S0 not computed, S0 and S2 not computed, all scenarios not computed (`all_dead OK A1:G6`), payback not reached (`en F21 'not reached within the horizon'` as a string, `fr F21 "non atteint dans l'horizon"`).
9. **Hostile text never becomes a formula.** Script `probe2.py`: `=HYPERLINK(...)`, `=cmd|' /C calc'!A0`, `+1+1`, `@SUM(A1)`, markup and emoji written into a text cell come back as strings (`dtype=['s']`) equal to the input. A 40000-character string is cut to 32767 without an error (Excel's limit, not reachable with real data).
10. **Chart images do not overlap, dates follow the language.** zip `drawing1.xml` anchors and openpyxl number formats: anchors at rows 95/115/135/155/175, each image ends 18 rows after its start; dates `yyyy-mm-dd` in EN and `dd/mm/yyyy` in FR.

Mutation evidence: the builder ran 8 mutations of `excel.py` (numbers as text, no comments, no autofilter, no freeze, no conditional format, no gate, text as formula, file written before the gate), each caught by at least one test. Mutation 7 ran before fix (1) below, so fix (1) is guarded only by the property test. The proof auditor added mutants (numbers rounded to 1 decimal, fit flag as text, percent x100): each killed by `test_T9_2_summary_values_equal_comparison_json`, not by the T9.1 tests, as intended.

## Audit rounds

### Build phase (before round 0), defects found by the builder's own tests

| # | severity | defect | resolution |
|---|---|---|---|
| 1 | not rated | `merge_range` in xlsxwriter writes through `write()`, so a merged header text starting with `=` became a formula | fixed: a `merged()` helper overwrites the first cell with `write_string`; guarded only by the property test |
| 2 | not rated | merging of disabled (not-computed) columns swallowed enabled columns of the same scenario when disabled states differed | fixed |
| 3 | not rated | numbers above 9.99999999999999e307 read back as inf (XlsxWriter's 16-digit output) | fixed by refusal: `build_excel` raises `ReportIntegrityError` for such a number; not reachable with real sizing data |

### Round 0 (initial build; spec auditor and runtime-proof auditor)

Both auditors returned `pass_with_issues`. Spec auditor: 67 passed, 0 failed. Proof auditor: 71 passed, 0 failed (the extra 4 are F9c's i18n_pdf tests). Findings by severity: 0 high, 0 medium, 12 low raw (6 from each auditor), 8 distinct after merging duplicates. No fix round followed, so no finding was fixed; all stay open or deferred (see Open issues). None was rejected.

| # | severity | found by | finding | resolution |
|---|---|---|---|---|
| 1 | low | spec, proof | F9b conventions not registered in `docs/INTERPRETATIONS.md` (highest entry is I80); the sheet-name deviation `Capex - Opex` is undocumented outside `excel.py` | deferred: the file is outside F9b's paths (reported as a blocker); still unregistered at the time of this record |
| 2 | low | spec, proof | FR/EN thousands and decimal separators are not forced: numbers are real numeric cells with language-independent format codes, so the display follows the viewer's regional settings; only dates follow the language | deferred: inherent to numeric cells and what makes T9.5 hold; differs from the spec's i18n sentence for display |
| 3 | low | spec, proof | Trace comment on a Low or High cell can name the opposite world (Low capex reads `hi world`) | deferred: disclosed convention (cell value equals the node value, tested), not explained inside the workbook |
| 4 | low | spec, proof | Layout and appearance unverified: Excel and LibreOffice not installed (`soffice not found`) | deferred: environment limit |
| 5 | low | spec | No syrupy snapshot of the Summary; labels outside the first block header are not pinned as literals | deferred: numbers are asserted against the JSON instead; optional in the task |
| 6 | low | spec | Empty-string text cells are written as strings (Assumptions columns J and L, 72 rows), not as blank cells | deferred |
| 7 | low | proof | Footer (engine, catalog, run id) is silently dropped when the source note exceeds Excel's 255-character limit; a catalog with about 7 or more families loses the run id from every printed page; only a `UserWarning` per sheet | deferred: today's footer is 122 characters (fits) |
| 8 | low | proof | One numeric Summary cell has no trace comment: the data quality score (Summary 126 comments for 127 numbers) | deferred: inherited from F9a open issue (dataset metric with no `TraceNode`) |

## Open issues

1. `docs/INTERPRETATIONS.md` has no F9b entry (`grep` for `F9b` and `Capex - Opex` returns nothing at the time of this record). Proposed next entry, from the builder's blockers: (a) the sheet `Capex / Opex` is written `Capex - Opex` because Excel forbids `/` (all of `[]:*?/\` become `-`, 31 characters at most; the title cell A1 keeps the i18n text); (b) the workbook is value-only, live formulas not built; (c) every cell with a trace id (the four IC1 tables and cash_flow) gets a comment with id, world, node label, formula and inputs, the cell value equals the node value, and a lo or hi cell cites the world whose node holds the value, so a `Low` cell can read `hi world`; (d) the fit flag stays numeric 1/0 with a yes/no number format; (e) a not-computed scenario is a grey merged region holding the `limit.gen.not_computed` text; (f) Summary writes its comparison block first so the frozen header is the comparison header; (g) `build_excel` runs `assert_integrity` first, builds in memory, checks the Excel strings for sentinels (IC8), then writes `report/trace.jsonl` and the xlsx; (h) demand charts go below the tables of Demand profile and the other charts are not in the workbook. Needs an engineer who owns that file.
2. Display separators follow the viewer's Excel locale, not the report language (FR report on an English-locale Excel shows `1,234.5`). Only dates follow the language.
3. Trace comments on Low and High cells can cite the opposite world; not explained in the workbook.
4. Untraced numeric cells: the Summary data quality score, and the Cash flow cumulative columns (3 per year, years 0..5) which have no `TraceNode` by I79 e/f. All other numeric cells in Summary, Scenarios, FTE and Capex - Opex carry a comment (127, 286, 477, 231 numbers; Summary is 126 of 127).
5. Printed footer is lost on a catalog with about 7 or more families (255-character Excel limit), with only a warning.
6. Empty text cells are empty strings, not blank cells (affects `COUNTBLANK`, `ISBLANK`).
7. No syrupy snapshot for T9.2; the "(snapshot)" in the spec is met by equality to `comparison.json`, not by a snapshot file.
8. Rendering never seen in Excel or LibreOffice: row autofit of wrapped text, comment box size and look, print scaling, the overflow of long italic notes (for example Summary A43) and the look of grey merged regions are unverified.
9. Scope left out on purpose: live formulas (stretch, stated in the `excel.py` docstring); charts other than the five demand charts are not in the workbook; opex by year is typical-world only (F9a/I79 c); text from F4, F7 and DQ stays in English in the FR workbook (F9a/I79 h); trace node labels and formulas in comments stay in the language the engine wrote (English).
10. The 60 s budget for both files (T9.7) is not closed: only the Excel half (about 0.5 to 0.7 s per language) is measured.
11. `report/__init__.py` and `i18n/{fr,en}.yaml` are edited concurrently by F9c. F9b appended `build_excel` and one key, `excel.trace`. The key-parity tests can fail transiently if F9c adds a key to one language only; they pass in the fresh run below.
12. Fix (1) of the build phase (formula injection through a merged header) is guarded by the property test only; mutation 7 predates it.

## Not applicable here and why

- **PDF (T9.3, and the PDF half of T9.5 and T9.7):** F9c.
- **IC1-IC8 tamper tests (T9.4) and block diagram (T9.6):** F9a. F9b only has gate tests (IC1 tamper gives exit 5 and writes nothing; IC8 sentinel fails before any file is written).
- **Real client data:** every run used here is synthetic (`ecom_mid` in the e2e tests; a 120-day synthetic run and a small synthetic run folder in the auditors' CLI runs); client data never leaves the machine.
- **Excel or LibreOffice rendering:** neither is installed; layout was checked by reading the files back with openpyxl and the package XML (44 parts, 0 malformed, `testzip()` clean, Print_Titles quoted for all 12 sheets in EN and FR), not by looking at a rendered sheet.
- **Domain expert review:** no review of the FR wording or the sheet layout by a native speaker or a warehouse-sizing expert was done; text checks assert literal labels and the absence of untranslated sentinels only.
- **Docker and GitHub CI:** not used by F9b and not run here.
- **Live formulas:** optional stretch, not built; a test asserts no formula cell exists.
- **syrupy snapshot:** optional in the task, not used.

## Fresh test output

Run 2026-11-09 from `/Users/skarwech/saas_v1`, trimmed to the relevant lines (captured stderr log lines removed):

```
$ uv run pytest tests/unit/test_f9_excel*.py tests/e2e/test_f9_excel*.py tests/property/test_f9_excel*.py tests/unit/test_f9_i18n*.py -q -rA

F9b Excel [en] on ecom_mid: 0.50 s, 359 kB
F9b Excel [fr] on ecom_mid: 0.60 s, 363 kB
=========================== short test summary info ============================
PASSED tests/unit/test_f9_excel.py::test_T9_1_the_workbook_opens_with_the_twelve_sheets_in_order[en]
PASSED tests/unit/test_f9_excel.py::test_T9_1_the_workbook_opens_with_the_twelve_sheets_in_order[fr]
PASSED tests/unit/test_f9_excel.py::test_T9_1_every_sheet_has_its_title_and_header_cells[en]
PASSED tests/unit/test_f9_excel.py::test_T9_1_every_sheet_has_its_title_and_header_cells[fr]
PASSED tests/unit/test_f9_excel.py::test_T9_1_the_sheet_name_never_holds_a_character_excel_forbids
PASSED tests/unit/test_f9_excel.py::test_T9_2_summary_values_equal_comparison_json[en]
PASSED tests/unit/test_f9_excel.py::test_T9_2_summary_values_equal_comparison_json[fr]
PASSED tests/unit/test_f9_excel.py::test_T9_2_scenario_sheets_equal_result_and_finance_json
PASSED tests/unit/test_f9_excel.py::test_T9_2_every_numeric_model_cell_is_a_number_in_the_sheets[en]
PASSED tests/unit/test_f9_excel.py::test_T9_2_every_numeric_model_cell_is_a_number_in_the_sheets[fr]
PASSED tests/unit/test_f9_excel.py::test_T9_5_fr_and_en_workbooks_hold_identical_numeric_cells
PASSED tests/unit/test_f9_excel.py::test_T9_5_the_build_is_deterministic
PASSED tests/unit/test_f9_excel.py::test_header_row_is_frozen_on_every_sheet[en]
PASSED tests/unit/test_f9_excel.py::test_header_row_is_frozen_on_every_sheet[fr]
PASSED tests/unit/test_f9_excel.py::test_number_formats_and_values_stay_numbers
PASSED tests/unit/test_f9_excel.py::test_the_fit_flag_has_a_green_and_a_red_conditional_format
PASSED tests/unit/test_f9_excel.py::test_scenarios_sheet_has_lo_typ_hi_columns_per_scenario
PASSED tests/unit/test_f9_excel.py::test_assumptions_have_one_row_per_param_and_the_filter_is_on
PASSED tests/unit/test_f9_excel.py::test_print_setup_is_landscape_a4_one_page_wide_with_the_run_id_in_the_footer
PASSED tests/unit/test_f9_excel.py::test_demand_profile_carries_the_charts_as_images_below_the_tables
PASSED tests/unit/test_f9_excel.py::test_summary_carries_the_indicative_banner_and_the_confidence_note
PASSED tests/unit/test_f9_excel.py::test_methodology_has_the_formulas_one_row_per_line_and_the_versions
PASSED tests/unit/test_f9_excel.py::test_every_traced_cell_has_a_comment_with_its_trace_id_and_formula[en]
PASSED tests/unit/test_f9_excel.py::test_every_traced_cell_has_a_comment_with_its_trace_id_and_formula[fr]
PASSED tests/unit/test_f9_excel.py::test_the_exported_trace_resolves_every_cited_id
PASSED tests/unit/test_f9_excel.py::test_no_untranslated_text_in_the_cells_or_the_comments[en]
PASSED tests/unit/test_f9_excel.py::test_no_untranslated_text_in_the_cells_or_the_comments[fr]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[int-1234.0-#,##0]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[eur-1234.5-#,##0]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[dec1-1.25-#,##0.0]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[dec2-1.255-#,##0.00]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[pct-0.123-0.0 %]
PASSED tests/unit/test_f9_excel.py::test_cell_content_numbers_are_numbers_with_their_format[num-0.05-None]
PASSED tests/unit/test_f9_excel.py::test_cell_content_bool_is_one_or_zero_shown_as_yes_or_no_by_the_format
PASSED tests/unit/test_f9_excel.py::test_cell_content_text_and_keys_are_strings_never_formulas
PASSED tests/unit/test_f9_excel.py::test_cell_content_refuses_text_in_a_numeric_cell_and_non_finite_numbers
PASSED tests/unit/test_f9_excel.py::test_a_scenario_not_computed_is_a_grey_column_with_the_reason
PASSED tests/unit/test_f9_excel.py::test_a_run_without_a_baseline_shows_absolute_values_and_no_npv_or_payback
PASSED tests/unit/test_f9_excel.py::test_a_scenario_as_the_baseline_has_no_delta_and_no_cumulative_column
PASSED tests/unit/test_f9_excel.py::test_an_integrity_failure_raises_exit_5_and_writes_nothing
PASSED tests/unit/test_f9_excel.py::test_an_unsupported_language_is_a_config_error_and_writes_nothing
PASSED tests/unit/test_f9_excel.py::test_an_untranslated_text_fails_the_build_before_any_file_is_written
PASSED tests/unit/test_f9_excel.py::test_the_workbook_of_an_unreadable_output_folder_is_a_whsizing_error
PASSED tests/unit/test_f9_excel.py::test_the_workbook_is_value_only_with_no_formula_in_any_cell
PASSED tests/unit/test_f9_excel.py::test_build_excel_is_the_function_the_cli_looks_up
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_7_the_excel_report_builds_within_budget[en]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_7_the_excel_report_builds_within_budget[fr]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_1_ecom_mid_workbook_has_the_twelve_sheets_and_their_headers[en]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_1_ecom_mid_workbook_has_the_twelve_sheets_and_their_headers[fr]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_2_ecom_mid_summary_equals_comparison_json[en]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_2_ecom_mid_summary_equals_comparison_json[fr]
PASSED tests/e2e/test_f9_excel_e2e.py::test_T9_5_ecom_mid_fr_and_en_workbooks_hold_identical_numbers
PASSED tests/e2e/test_f9_excel_e2e.py::test_ecom_mid_every_summary_number_has_a_comment_that_resolves_in_the_exported_trace
PASSED tests/e2e/test_f9_excel_e2e.py::test_ecom_mid_with_a_scenario_as_the_baseline_builds_and_keeps_the_gate_open
PASSED tests/property/test_f9_excel_properties.py::test_T9_5_property_random_content_never_turns_a_number_into_text_or_text_into_a_number
PASSED tests/property/test_f9_excel_properties.py::test_T9_5_property_fr_and_en_hold_the_same_numbers_at_the_same_coordinates
PASSED tests/property/test_f9_excel_properties.py::test_property_strategies_reach_the_hard_cases
PASSED tests/unit/test_f9_i18n.py::test_T9_5_i18n_files_hold_the_same_keys
PASSED tests/unit/test_f9_i18n.py::test_T9_5_i18n_placeholders_match_in_both_languages
PASSED tests/unit/test_f9_i18n.py::test_T9_5_missing_key_gives_the_sentinel_and_never_raises
PASSED tests/unit/test_f9_i18n.py::test_T9_5_fr_number_format_uses_narrow_no_break_space_and_comma
PASSED tests/unit/test_f9_i18n.py::test_T9_5_en_number_format_uses_comma_thousands_and_point
PASSED tests/unit/test_f9_i18n.py::test_T9_5_dates_are_dd_mm_yyyy_in_fr_and_iso_in_en
PASSED tests/unit/test_f9_i18n.py::test_T9_5_render_cell_formats_by_fmt
PASSED tests/unit/test_f9_i18n.py::test_T9_5_every_flag_code_of_the_engine_has_a_message_in_both_languages
PASSED tests/unit/test_f9_i18n.py::test_T9_5_every_key_the_tables_use_exists_in_both_languages
PASSED tests/unit/test_f9_i18n.py::test_T9_5_an_unsupported_language_is_a_config_error_not_a_file_error
PASSED tests/unit/test_f9_i18n_pdf.py::test_F9c_i18n_every_key_of_the_pdf_exists_in_both_languages
PASSED tests/unit/test_f9_i18n_pdf.py::test_F9c_i18n_the_pdf_section_titles_and_family_texts_exist
PASSED tests/unit/test_f9_i18n_pdf.py::test_F9c_i18n_pdf_texts_have_the_same_placeholders_in_both_languages[pdf.]
PASSED tests/unit/test_f9_i18n_pdf.py::test_F9c_i18n_pdf_texts_have_the_same_placeholders_in_both_languages[msg.]
71 passed in 55.20s
```

Lint and types on the F9b files (excel.py and the four test files), run the same day:

```
$ uv run ruff check <excel.py and the 4 test files>          -> All checks passed!
$ uv run ruff format --check <same 5 files>                  -> 5 files already formatted
$ uv run pyright src/whsizing/report/excel.py                -> 0 errors, 0 warnings, 0 informations
```

Counts: 71 passed, 0 failed, 0 skipped (45 in `test_f9_excel.py`, 9 in `test_f9_excel_e2e.py`, 3 in `test_f9_excel_properties.py`, 10 in `test_f9_i18n.py`, 4 in `test_f9_i18n_pdf.py`).
