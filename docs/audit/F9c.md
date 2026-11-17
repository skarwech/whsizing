# F9c audit record: PDF report (Jinja2 + WeasyPrint), A4, sections 0-8 + appendices A-C, integrity gate

Written 2026-11-09 from the audit history of the F9c build (three audit rounds: round 0 on the initial build, rounds 1 and 2 after fixes; a spec-compliance auditor and a runtime-proof auditor in each) and from a fresh test run made while writing this record. Spec: `description.md` lines 1167-1236 (F9 PDF). F9c builds `report/report_<lang>.pdf` (and `report/trace.jsonl` plus `report/diagram_<sid>.svg`) with `whsizing.report.build_pdf(run, lang)`, on top of the F9a core.

## Final verdict: pass_with_issues

- Fresh run: 108 passed, 0 failed, 1 skipped (F0's Docker test, not an F9c test). T9.3, T9.5, T9.7 and the done-when (three Summary numbers per scenario reproduced from Appendix C, FR and EN) have real assertions, which both round-2 auditors confirmed with independent recomputation and mutation checks.
- No round 3 was run: the round-2 findings are still open. The main one (medium, reported by both round-2 auditors) is that the 12-18 page budget holds only up to 4 scenarios (5 scenarios give 19 pages, 6 give 21); the others are low (English free text in the FR PDF, F9a-side tornado and diagram limits, spec fonts not proven on this Mac, F9c helper modules outside the owned-path list).

## Acceptance tests

Test files: `tests/unit/test_f9_pdf.py` (42 test items), `tests/unit/test_f9_pdf_many.py` (46, the 4- and 6-scenario studies and the fit loop), `tests/unit/test_f9_pdf_support.py` (support module, no tests), `tests/unit/test_f9_i18n_pdf.py` (4), `tests/property/test_f9_pdf_grid.py` (1), `tests/e2e/test_f9_pdf_e2e.py` (4), plus `tests/unit/test_f0_report.py` (F0 stub contract, 1 passed and 1 skipped) and `tests/unit/test_f9_i18n.py` (10, F9a's T9.5 preparation, part of the command). Together: 108 passed, 1 skipped.

The spec names three F9c ids (T9.3, T9.5, T9.7) and the done-when. Every other row below is an F9c test added by the engineer or in the fix rounds (id "F9c"). `[fr|en]` or `[4|6]` means the function is parametrised; the status is for all parameters. All paths are under `tests/`.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T9.3 | `unit/test_f9_pdf.py::test_T9_3_pdf_has_at_least_12_pages_and_the_run_id_on_each[fr\|en]` | pass | Real PDF of the small run parsed with pypdf: 12 <= pages <= 18 (17 in FR and EN), the run id and "i / N" on every page. |
| T9.3 | `unit/test_f9_pdf.py::test_T9_3_sections_0_to_8_and_appendices_come_in_the_spec_order[fr\|en]` | pass | Cover facts, banner, DQ band, then the 11 section titles (0-8, A-C) in spec order. |
| T9.3 | `unit/test_f9_pdf.py::test_T9_3_the_cover_dates_follow_the_language` | pass | Cover date dd/mm/yyyy in FR, yyyy-mm-dd in EN. |
| T9.3 | `e2e/test_f9_pdf_e2e.py::test_T9_3_pdf_of_a_real_run_has_12_to_18_pages_and_the_run_id` | pass | Synthetic `ecom_mid` run (730 days, 3 scenarios): 12 <= pages <= 18 (17, FR and EN) and the run id on every page. |
| T9.5 | `unit/test_f9_pdf.py::test_T9_5_fr_and_en_render_the_same_numbers` | pass | Every right-aligned table cell of the HTML (typical value and lo-hi range, more than 400 cells) parsed back through the FR and EN locale parsers: identical sequences. |
| T9.5 | `unit/test_f9_pdf.py::test_T9_5_summary_cells_parse_back_to_the_raw_values` | pass | Section 1 table in both languages equals the raw typical `Cell` values to the format precision (percent as percent). |
| T9.5 | `unit/test_f9_pdf.py::test_T9_5_the_pdf_text_holds_the_summary_numbers_of_its_language[fr\|en]` | pass | Every Summary number, as printed by the language formatter, is in the pypdf text of page 2; parsed value equals the raw `Cell` (more than 100 numbers). |
| T9.5 | `unit/test_f9_pdf.py::test_T9_5_french_html_uses_the_french_separators` | pass | FR HTML has U+202F thousands and decimal comma, EN has comma thousands; no `{{ missing` sentinel in either. |
| T9.5 | `property/test_f9_pdf_grid.py::test_T9_5_prop_a_stacked_range_prints_back_to_its_raw_values` | pass | Hypothesis, 200 examples: lo/typ/hi stacked in one column parse back to the raw values in FR and EN. |
| done-when | `unit/test_f9_pdf.py::test_T9_5_three_summary_numbers_are_reproduced_from_appendix_c[fr\|en]` | pass | Per scenario, total area (sum of the 9 printed zones), design-day heads (sum of the printed activities) and TCO (capex + discounted opex from the printed formula inputs) recomputed from the Appendix C text of the PDF equal the printed value and the Summary cell. |
| done-when | `e2e/test_f9_pdf_e2e.py::test_F9c_three_summary_numbers_of_every_scenario_are_reproduced_from_appendix_c` | pass | The same three recomputations on the `ecom_mid` run, FR and EN, three scenarios. |
| T9.7 | `e2e/test_f9_pdf_e2e.py::test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together` | pass | `build_excel` plus `build_pdf`, FR and EN, on `ecom_mid`: the sum is under 60 s (asserted as one sum since round 1). Fresh run: FR PDF 4.9 s + Excel 0.6 s, EN PDF 4.2 s + Excel 0.5 s, 17 pages, 586 / 567 KiB. |
| T0.5 | `unit/test_f0_report.py::test_T0_5_mock_result_renders_one_page_pdf` | pass | The F0 stub PDF is unchanged and still one page (`styles.css` is shared with it). |
| T0.5 | `unit/test_f0_report.py::test_T0_5_docker_image_renders_one_page_pdf` | not_applicable (skipped) | Skipped by its own skipif, "Docker not installed". F0's test. |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_executive_summary_is_exactly_one_page[fr\|en]` | pass | Page 2 holds section 1 up to its last caveat, section 2 starts on page 3. |
| F9c | `unit/test_f9_pdf.py::test_F9c_no_text_runs_beyond_the_right_margin[fr\|en]` | pass | No text run of any page starts beyond the 18 mm margin (3 scenarios). Caught, in round 1, the FR section 2 `.triple` table that ran off the page (text at x=674 pt), since fixed. |
| F9c | `unit/test_f9_pdf.py::test_F9c_diagram_labels_and_appendix_c_are_set_at_legible_sizes[fr\|en]` | pass | Effective font size read from the PDF: block diagram labels >= 4.0 pt, Appendix C >= 5.7 pt. |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_cover_has_no_running_header_and_the_other_pages_have_it[fr\|en]` | pass | Client/site once on the cover, "Indicative study" header absent on page 1 and present on every other page. |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_running_footer_is_in_the_language_of_the_report[fr\|en]` | pass | Footer line of every page reads run id, engine/moteur version, "Page i / N" in the report language. |
| F9c | `unit/test_f9_pdf.py::test_F9c_appendix_c_formulas_are_titled_without_a_wrong_appendix_letter[fr\|en]` | pass | Appendix C formulas heading is "Formulas"/"Formules", not "(Appendix B)". |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_limitations_box_of_section_8_is_not_split_across_pages[fr\|en]` | pass | Section 8 heading, fixed and generated items stay on one page. |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_limitations_box_is_drawn` | pass | `.limits` is a bordered, shaded box (CSS rule present). |
| F9c | `unit/test_f9_pdf.py::test_F9c_trace_numbers_print_counts_as_whole_numbers` | pass | Appendix C prints whole numbers without decimals, other values with two (four below 1). |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_warnings_count_of_appendix_c_has_no_decimals` | pass | The `n_warnings` row of Appendix C reads "Warnings 2", not "2.00". |
| F9c | `unit/test_f9_pdf.py::test_F9c_key_messages_have_no_recommended_label_and_carry_the_overlap_note[fr\|en]` | pass | Three key messages, ranking sentence with the localised overlap note, no "recommend"/"recommand" anywhere. |
| F9c | `unit/test_f9_pdf.py::test_F9c_every_chart_and_diagram_has_an_alt_with_the_source_note` | pass | 9 charts and 3 diagrams inline, each alt = title + "engine v, catalog v, run id". |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_appendix_c_trace_index_lists_every_summary_number` | pass | Every Summary trace id of every scenario is in Appendix C; `data:basis` leaf printed with its value; more than 8 parameter inputs collapsed to a count. |
| F9c | `unit/test_f9_pdf.py::test_F9c_build_writes_the_pdf_the_trace_and_the_diagrams` | pass | `report/` holds exactly the 2 PDFs, `trace.jsonl` and 3 diagrams (this was order-dependent on F9b's xlsx files in round 0, fixed). |
| F9c | `unit/test_f9_pdf.py::test_F9c_a_failed_integrity_check_raises_exit_5_and_writes_no_file` | pass | `S1.capex.total` doubled in the on-disk trace: `ReportIntegrityError`, exit code 5, message names IC1, `report/` not created. |
| F9c | `unit/test_f9_pdf.py::test_F9c_an_untranslated_text_in_the_rendered_html_fails_ic8_and_writes_no_file` | pass | A removed i18n key renders the `{{ missing: }}` sentinel: IC8, exit 5, nothing written. |
| F9c | `unit/test_f9_pdf.py::test_F9c_an_unsupported_language_is_a_clear_config_error` | pass | `ConfigError` "report: unsupported language 'de' (use one of fr, en)". |
| F9c | `unit/test_f9_pdf.py::test_F9c_a_scenario_not_computed_is_greyed_with_its_reason` | pass | Reason printed in sections 1, 4, 5, 6; greyed column and paragraph; PDF still builds (17 pages, >= 12); no diagram or trace entry for it. |
| F9c | `unit/test_f9_pdf.py::test_F9c_without_a_baseline_the_business_case_shows_absolute_values_only` | pass | No NPV or payback rows, "No baseline was given" in EN and FR, absolute TCO and cost per line kept. |
| F9c | `unit/test_f9_pdf.py::test_F9c_the_html_is_built_from_the_model_not_from_a_recomputation` | pass | A raw `Cell` changed in the model is what section 1 prints. |
| F9c | `unit/test_f9_pdf.py::test_F9c_a_client_name_with_markup_cannot_break_the_running_header` | pass | Running-header text is CSS-escaped, body text HTML-escaped. |
| F9c | `unit/test_f9_pdf.py::test_F9c_each_scenario_has_its_chart_colour_in_the_tables_and_descriptions` | pass | Scenario colour of the charts as a rule above table headers and beside section 4 paragraphs. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer[4\|6 scenarios, fr\|en]` | pass | 4 scenarios: 12 <= pages <= 18. 6 scenarios: at most 22 pages (measured 21); bounded growth, as the budget is a limit only up to 4 scenarios (I81 c). |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget[4\|6, fr\|en]` | pass | Diagram labels keep >= 4.0 pt (4.41 measured) at 4 and 6 scenarios (round 1 had 2.35 pt). |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget[4\|6, fr\|en]` | pass | Appendix C keeps >= 5.7 pt (5.8 measured) at every typesetting level (round 1 had 5.2 pt). |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios[4\|6, fr\|en]` | pass | Section 1 on page 2 and section 2 from page 3 for 4 and 6 scenarios. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_appendix_c_traces_every_scenario_of_a_large_study[4\|6, fr\|en]` | pass | Every scenario of a large study is traced in Appendix C. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios[4\|6, fr\|en]` | pass | No text run starts beyond the margin at 4 and 6 scenarios (start-x check, kept next to the layout check). |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios[4\|6, fr\|en]` | pass | `layout_overflow` walks the WeasyPrint boxes (text, images, tables) on the tightest typesetting and finds no right edge beyond the margin. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_the_overflow_check_sees_a_box_that_ends_beyond_the_margin` | pass | Positive control: the overflow check detects an overflowing nowrap paragraph. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_the_tornado_has_at_most_three_scenarios_per_figure[4\|6]` | pass | Tornado drawn in figures of at most 3 scenarios, shared evenly (4: 2+2, 6: 3+3); one `alt` per figure. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_a_many_scenario_report_draws_its_charts_without_a_collapsed_layout[4\|6]` | pass | The matplotlib "constrained_layout not applied" warning, turned into an error, does not occur. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_the_cash_flow_is_cut_into_tables_of_at_most_three_scenarios[4\|6]` | pass | Section 6 cash flow is cut into tables of at most 3 scenarios (nothing clipped at the A4 edge). |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[6 params]` | pass | `pdf_view.split` balances 3..8 scenarios over the tables. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_split_keeps_the_three_columns_of_a_scenario_together` | pass | lo/typ/hi column groups with a second header row stay together. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_split_leaves_a_table_that_is_not_by_scenario_alone` | pass | A grid whose heads carry no scenario colour is never cut. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_fit_pdf_takes_the_loosest_typesetting_within_the_budget` | pass | `fit_pdf` keeps the loosest typesetting level with <= 18 pages. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_fit_pdf_keeps_the_tightest_and_logs_when_nothing_fits` | pass | When nothing fits, the tightest is kept and `report_over_page_budget` is logged. |
| F9c | `unit/test_f9_pdf_many.py::test_F9c_a_report_folder_that_cannot_be_written_is_a_whsizing_error` | pass | `report` being a file gives `WhsizingError` "report: cannot write ...", not a raw `OSError`. |
| F9c | `e2e/test_f9_pdf_e2e.py::test_F9c_the_report_folder_holds_the_pdfs_the_trace_and_the_diagrams` | pass | `ecom_mid`: both PDFs, `trace.jsonl`, `diagram_<sid>.svg`; every Summary trace id resolves in the exported trace. |
| F9c | `unit/test_f9_i18n_pdf.py::test_F9c_i18n_every_key_of_the_pdf_exists_in_both_languages` | pass | Every literal `t('...')` key of the PDF code and templates exists in fr and en. |
| F9c | `unit/test_f9_i18n_pdf.py::test_F9c_i18n_the_pdf_section_titles_and_family_texts_exist` | pass | Section titles and family texts exist in both languages. |
| F9c | `unit/test_f9_i18n_pdf.py::test_F9c_i18n_pdf_texts_have_the_same_placeholders_in_both_languages[pdf.\|msg.]` | pass | `pdf.*` and `msg.*` placeholders match in fr and en. |
| T9.5 (F9a prep) | `unit/test_f9_i18n.py` (10 functions: same keys, placeholders, sentinel, FR/EN number format, dates, `render_cell`, flag codes, table keys, unsupported language) | pass | F9a's i18n parity tests, run here because F9c adds keys to both yaml files. Not an F9c test; they stay green. |

Not F9c tests, so not listed: T9.1 and T9.2 (Excel, F9b), T9.4 (IC1-IC8 on tampered fixtures, F9a), T9.6 (block diagram area, F9a). F9c's own use of the gate is covered by the two `test_F9c_*integrity*`/`ic8` rows above and by the CLI proof below.

## Proofs

All proofs below were captured by the auditors during the audit (not by me while writing this record); the scripts are in the audit scratchpad, `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F9c/`, not in the repository. Outputs are excerpts as reported by the auditors. Hand-rolled scratch runs use the synthetic datasets only.

1. **The feature command and the whole suite pass (round 2, runtime auditor).** Claim: 108 passed, 1 skipped for the F9c command, and the whole repository suite has no failure.
   Command: `cd /Users/skarwech/saas_v1 && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/unit/test_f9_pdf*.py tests/e2e/test_f9_pdf*.py tests/property/test_f9_pdf*.py tests/unit/test_f0_report.py tests/unit/test_f9_i18n*.py -q -rA; then uv run pytest -q`
   Output: `108 passed, 1 skipped in 168.25s (0:02:48); full suite: 1754 passed, 2 skipped in 758.50s (0:12:38)`. (In round 0 the same whole-suite run had failed: `1 failed, 1602 passed, 2 skipped in 684.28s`, an order-dependent F9c test, fixed in round 1.)

2. **Done-when reproduced by hand from the printed Appendix C (round 0, spec auditor).** Claim: a reader other than the author can recompute TCO, total area and design-day heads from the PDF text.
   Command: `uv run python -c "o=[81886.02,84236.63,86729.47,89373.44,92178.04]; r=0.08; print(134092.82+sum(x/(1+r)**t for t,x in enumerate(o,1)))"` (capex and opex values read off Appendix C of the small-run EN PDF; same for S1 with capex 369466.65)
   Output: `479408.16301849607` (printed 479,408.17); S1 `825102.8015749597` (printed 825,102.81); area `0.5779+2.10+12.00+0.00+19.09+30.26+40.00+234.80+79.93 = 418.7579` (printed 418.77); heads: sum of the 11 printed activities `1.1007` (printed 1.10). Differences are the 2-decimal rounding of the printed inputs.

3. **Done-when reproduced by independent parsers on the compact typesettings (rounds 1 and 2, both auditors).** Claim: the three numbers are reproducible for every scenario at 3, 4 and 6 scenarios, in EN and FR, including the PDFs set at the tighter page-budget levels.
   Command: `uv run python audit_F9c/r2_indep.py` on the rebuilt 3-, 4- and 6-scenario PDFs (round 2 spec auditor); a separate recomputation script on `run4` and `run6` (round 1 runtime auditor).
   Output: round 2: e.g. S0 area `1048.98` vs printed `1048.99`, heads `32.39` vs `32.39`, TCO `4696269.17` vs `4696269.17` (`ecom_mid`), all scenarios matching to 0.01; round 1: `run4 en 12/12, fr 12/12; run6 en 18/18, fr 18/18 reproduced, 0 mismatches`.

4. **Summary numbers equal `comparison.json`, checked outside the test helpers (round 0, runtime auditor).** Claim: every Summary number on page 2 of both PDFs is the raw value, formatted for the language.
   Command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python .../audit_F9c/indep.py`
   Output: `checked 186 missing 0` (lo/typ/hi of 10 rows x 3 scenarios plus payback, FR and EN). Round 1 spec auditor: the 38 numbers of the generated prose (key messages, caveats, limitations, break-even sentences, eligibility shares) are identical in FR and EN.

5. **The integrity gate works through the public CLI (round 2, runtime auditor).** Claim: a tampered trace gives exit 5 and no `report/` folder.
   Command: `uv run whsizing report <tampered run> --formats pdf --lang en; echo exit=$?` (S1 capex node doubled in `scenarios/S1/trace.jsonl`)
   Output: `error: 2 integrity check(s) failed / IC1 summary/comparison/capex/S1.typ: cell value 369466.65 differs from trace node S1.capex.total: 738933.30 ... exit=5`; the run folder lists `canonical comparison design dq inputs logs manifest.json profile scenarios`, no `report/`. The untampered run writes `report_fr.pdf`, `report_en.pdf`, `trace.jsonl`, `diagram_S0..S2.svg`; `whsizing run-all` on synthetic data wrote the 4 report files in 14.5 s.

6. **Page count, summary page, legibility for 1 to 8 scenarios (round 2, runtime auditor).** Claim: the page counts quoted in the open issue below, and the legibility floors hold at every scenario count.
   Command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python .../audit_F9c/probe_c.py 1 2 3 4 5 6 7 8`
   Output (EN/FR pages): 1: 15/15, 2: 16/15, 3: 17/17, 4: 17/18, 5: 19/19 (log `report_over_page_budget max=18 pages=19 scenarios=5`), 6: 21/21, 7: 23/24, 8: 25/26; `exec_one_page=False` for 7 and 8 scenarios (FR); diagram labels `4.41 pt` and Appendix C `5.8 pt` at every n.

7. **No ink in the side margins (rounds 1 and 2, both runtime auditors).** Claim: nothing is clipped at the A4 right edge.
   Command: `gs -sDEVICE=pnggray -r72` on the PDFs of 4, 5, 6 and 8 scenarios, EN and FR, then a numpy scan of the 18 mm side bands (round 1: `.../audit_F9c/ink.py` on 3, 4, 6, 8 scenarios).
   Output: `pages scanned: 166 pages with ink in side margins: {}`; round 1 `ink in side margins (page,left_px,right_px): []` for every PDF.

8. **The tests are not tautological: mutation checks (rounds 1 and 2).** Claim: removing a feature makes the matching test fail.
   Command: `PYTHONPATH=<scratchpad>/audit_F9c/mut<N>/src uv run pytest -x <selected tests>`, N in 1,2,3,5,7,8,9 (scratch copy of `src`, repo untouched), and a scratch pytest plugin patching `pdf.COMPACT_LEVELS=0` / `pdf.split` to identity (round 1).
   Output: M1 diagrams two per row: `FAILED ...labels_are_not_shrunk_to_fit_the_page_budget[4_scenarios-fr]`; M2 `TORNADO_MAX_PANELS=99`: `FAILED ...tornado_has_at_most_three_scenarios_per_figure[6_scenarios]`; M3 Appendix C shrunk: `FAILED ...appendix_c_type_is_not_shrunk...[4_scenarios-fr]`; M5 integrity gate removed: `FAILED ...failed_integrity_check_raises_exit_5_and_writes_no_file`; M7 trace numbers at 0 decimals: `FAILED test_F9c_trace_numbers_print_counts_as_whole_numbers` plus 3 done-when tests; M8 FR range printed with the EN formatter is killed by `test_T9_5_fr_and_en_render_the_same_numbers`; `COMPACT_LEVELS=0`: `assert 21 <= 18` (4 scenarios), `assert 24 <= 18` and `26 <= 18` (6); `split` disabled: every margin test fails.

9. **The build is deterministic (rounds 1 and 2, runtime auditors).** Claim: two builds of the same run give byte-identical output.
   Command: `uv run python .../audit_F9c/probe_a.py` (round 2), `.../rt/determ2.py` (round 1)
   Output: `fr pages 17 bytes-equal True text-equal True sha 4fa959d0a7b8 4fa959d0a7b8 / en pages 17 bytes-equal True text-equal True sha 11ec6850830d 11ec6850830d; no WeasyPrint warnings logged`; round 1: HTML, SVG and `trace.jsonl` also `SAME`.

10. **Edge cases build and keep their contract (rounds 0 to 2, runtime auditors).** Claim: no sensitivity, baseline = S0, scenarios not computed, no baseline, hostile names, odd paths and a read-only folder do not break the build.
    Command: `uv run python .../audit_F9c/probe_d.py` (round 2), `rt/edges3.py`, `rt/names2.py`, `rt/perm2.py` (round 1)
    Output: `OK all scenarios not computed: pages=12; OK no baseline: pages=17; OK long client: pages=17; OK odd scenario names: pages=17 (script text present as text: True); OK path with spaces/unicode: pages=17`; read-only run dir gives `WhsizingError: report: cannot write .../report/report_en.pdf: [Errno 13] Permission denied`. Round 1: `only_S0_and_S2 fr 16 / en 15`, one scenario 15/15; the literal client name `{{ missing: foo }}` correctly fails IC8; a 300-character client name spills the cover TOC onto page 2 (18 pages), 85 and 150 characters are fine.

## Audit rounds

Round 0 audited the initial build. The fix after round 0 (called round 1 in the history) and the fix after round 1 (round 2) were each followed by a new pair of audits. No finding was rejected as invalid: each was fixed or deferred. Ids: R0-S = round 0 spec auditor, R0-P = round 0 runtime-proof auditor, and so on.

### Round 0: initial build

Spec auditor: pass_with_issues, 45 passed, 0 failed; 1 medium, 6 low. Runtime-proof auditor: fail (the F9c command passed 45 + 1 skipped, but the whole-suite run had 1 failed); 1 high, 2 medium, 4 low. Resolutions are from the fix made after round 0.

| id | sev | finding | resolution |
|---|---|---|---|
| R0-S1 | medium | 12-18 pages not held beyond 3 scenarios (4 scenarios: 19 pages), no degradation, no test | fixed: `fit_pdf` tries typesettings 0..2 (`.compact`, `.compact2`) and keeps the loosest with <= 18 pages, logs `report_over_page_budget` when none fits; new `test_f9_pdf_many.py` on real 4- and 6-scenario runs. Measured then (EN/FR): 4: 17/17, 6: 17/18. Later trade-off in round 2, see R1-S1. |
| R0-S2 | low | "Formulas (Appendix B)" title in Appendix C | fixed: new key `pdf.appc.formulas` ("Formulas"/"Formules") |
| R0-S3 | low | Section 8 not a limitations box; layout nits (lone Appendix A row, heading at page foot) | fixed: `.limits` bordered, shaded, `break-inside: avoid`; Appendix A fits one page. The Equipment table split across two pages is ordinary table flow and was left. |
| R0-S4 | low | footer hard-codes "engine" in both languages | fixed: key `pdf.footer.engine` (engine / moteur) |
| R0-S5 | low | T9.7 asserts only the PDF half | fixed: Excel and PDF, FR and EN, summed under 60 s |
| R0-S6 | low | one-page executive summary and the 18-page bound beyond 3 scenarios not asserted | fixed: `test_F9c_the_executive_summary_is_exactly_one_page` and the many-scenario variants |
| R0-S7 | low | Appendix C count nodes printed as "2.00"; F9c conventions not in INTERPRETATIONS | fixed: whole numbers print without decimals; I81 added to `docs/INTERPRETATIONS.md` |
| R0-P1 | high | `test_F9c_build_writes_the_pdf_the_trace_and_the_diagrams` order-dependent: `own_run()` copied F9b's xlsx files, whole suite red | fixed: `copytree(..., ignore_patterns('report'))`; `pytest tests/unit/test_f9_excel.py tests/unit/test_f9_pdf.py` gives 85 passed (was 1 failed) |
| R0-P2 | medium | tables clipped at the A4 right edge with 4+ scenarios (cash flow loses the 4th scenario, comparison the 6th) | fixed: `pdf_view.split` cuts scenario tables (3 per table inline and for cash flow, 4 stacked), geometric test with pypdf. Extra defect found by that test and not reported by the auditors: FR section 2 third ABC table ran off the page even with 3 scenarios (x=674 pt), fixed in `styles.css` (`.triple`). |
| R0-P3 | medium | page budget exceeded beyond 3 scenarios, no mechanism or check | fixed: as R0-S1 |
| R0-P4 | low | cover page carries the running header (inline `@page` overrode `@page :first`) | fixed: same `@page :first` rule in the inline block; test added |
| R0-P5 | low | "Formulas (Appendix B)" heading | fixed: duplicate of R0-S2 |
| R0-P6 | low | FR PDF prints the Appendix C formulas block in English; raw flag codes in section 8 | deferred: `methodology.formulas` is an F9a key shared with the F9b Excel sheet (identical in `fr.yaml` and `en.yaml`), translating it is content work outside F9c; recorded as I81 (g). See open issue O2. |
| R0-P7 | low | file-system errors in `build_pdf` are raw `OSError`s; partial `report/` folder | fixed: writes moved to `_write()`, which wraps `OSError` in `WhsizingError`; write order trace, SVGs, PDF last is kept on purpose, so a failed write can still leave trace and SVGs without a PDF (not rolled back) |

### Round 1: after the first fix

Spec auditor: pass_with_issues, 89 passed, 0 failed; 6 low. Runtime-proof auditor: pass_with_issues, 89 passed, 0 failed; 2 medium, 3 low. The whole suite had no failure. Resolutions are from the fix made after round 1.

| id | sev | finding | resolution |
|---|---|---|---|
| R1-S1 | low | 12-18 pages held only up to 6 scenarios (8 scenarios: 22 pages, summary spills) | deferred: the trade-off changed in round 2 (legibility over pages, I81 c): the budget now holds for 3 and 4 scenarios, 6 give 21. See O1. |
| R1-S2 | low | F9a tornado (`charts.py:82`) collapses with 6 scenarios, ships unreadable | fixed in F9c by a workaround (figures of at most 3 scenarios, `TORNADO_MAX_PANELS`); F9a root cause not touched. See O3. |
| R1-S3 | low | FR formulas block, F4/DQ/F7 notes and raw flag codes in English | deferred (same as R0-P6). See O2. |
| R1-S4 | low | `pdf_text.py`, `pdf_view.py` outside the owned paths; `INTERPRETATIONS.md` edited | deferred to the integrator. See O6. |
| R1-S5 | low | compact typesetting sets Appendix C at 5.2-5.6 pt | fixed: the `.compact` rules for the trace tables and formulas removed; 5.8 pt minimum at every level, tests added |
| R1-S6 | low | right-margin tests check only where a text run starts | fixed: `layout_overflow` walks the WeasyPrint boxes (text, images, tables), with a positive-control test |
| R1-P1 | medium | from 4 scenarios the diagrams are two per row, labels about 2.3 pt, unreadable | fixed: two-per-row rules removed, one diagram per row at every level, labels 4.41 pt; spacing of `.compact2` tightened to pay for it; tests read the font size from the PDF and fail on the old PDF (2.35 pt < 4.0 floor) |
| R1-P2 | medium | tornado collapses with 6 scenarios, cramped at 4, page counts measured with the collapsed chart | fixed in F9c by the 3-per-figure workaround (the "constrained_layout" warning is gone); F9a root cause remains. See O3. |
| R1-P3 | low | page range held only to 6 scenarios; no test above | deferred, as R1-S1 (test now requires 12-18 for 4 scenarios and at most 22 for 6) |
| R1-P4 | low | FR formulas and generated notes in English | deferred, as R1-S3 |
| R1-P5 | low | Appendix C at 5.2-5.6 pt in the compact typesettings | fixed, as R1-S5 |

### Round 2: after the second fix (last audit)

Spec auditor: pass_with_issues, 108 passed, 0 failed; 1 medium, 4 low. Runtime-proof auditor: pass_with_issues, 108 passed, 0 failed; 1 medium, 5 low. No further fix round was run, so all of these are open (the same defects appear on both sides; see Open issues).

| id | sev | finding | status |
|---|---|---|---|
| R2-S1 | medium | 12-18 pages and the one-page summary hold only up to 4 scenarios (5: 19, 6: 21, 8: 25/26); the 4-scenario FR PDF is exactly 18 pages | open, O1 |
| R2-S2 | low | tornado workaround: FR tick labels run together ("-500 0000 500 000", also at 3 scenarios), separate x scale per figure at 4+ | open, O3 |
| R2-S3 | low | FR PDF prints the Appendix C formulas, generated notes and raw flag codes in English | open, O2 |
| R2-S4 | low | `pdf_text.py` and `pdf_view.py` outside the owned paths; `INTERPRETATIONS.md` edited | open, O6 |
| R2-S5 | low | PDF embeds Verdana/Andale Mono on this Mac, not the spec fonts; layout machine-dependent | open, O5 |
| R2-P1 | medium | 12-18 pages and the one-page summary no longer hold from 5 scenarios on (previous findings moved, not resolved); summary spills at 7+ | open, O1 |
| R2-P2 | low | FR PDF prints English texts (F7 notes, formulas, flag codes) | open, O2 |
| R2-P3 | low | `pdf_text.py` and `pdf_view.py` outside the owned paths | open, O6 |
| R2-P4 | low | block diagram labels 4.4 pt at full A4 width (F9a `diagram.py`: 5.5 px in a 560 px drawing) | open, O4 |
| R2-P5 | low | tornado workaround draws several figures with the same title, no part number, separate scales | open, O3 |
| R2-P6 | low | spec fonts (Liberation Sans, DejaVu Sans) not installed here, Docker typesetting not proven | open, O5 |

## Open issues

Last audit pass (round 2, pass_with_issues). None blocks the done-when; none was rejected.

- **O1 (medium, R2-S1, R2-P1; deferred, I81 c)** The 12-18 page budget is held for 3 and 4 scenarios only. Measured EN/FR pages: 3: 17/17, 4: 17/18, 5: 19/19, 6: 21/21, 7: 23/24, 8: 25/26. From 5 scenarios the build logs `report_over_page_budget` and writes the tightest typesetting, longer than 18 pages by design; at 7 and 8 scenarios the executive summary also spills onto page 3 (tested for 4 and 6 only). The 4-scenario FR PDF is exactly 18 pages, so a longer client, site or scenario name could make it 19. Round 2 chose legibility (diagram labels, Appendix C) over pages. Bringing 5+ scenarios back to 18 pages at legible sizes needs smaller diagrams from F9a. The spec example has 3 scenarios, so the shipped case is within budget.
- **O2 (low, R2-S3, R2-P2; deferred, I81 g)** The French PDF prints in English: the Appendix C formulas block (`methodology.formulas` is byte-identical in `fr.yaml` and `en.yaml`, shared with the Excel Methodology sheet and its F9b test, so outside F9c's additive-only yaml permission), the F4/DQ/F7 free-text notes (for example "S0, S1, S2: baseline = the client's current operation: capex 0 (sunk)..."), and raw flag codes in the section 8 generated items (`F_UNSTABLE:packing`). The spec says i18n covers labels and fixed texts; I79 h and I81 g declare these texts language-neutral. They should be translated once for the PDF and the Excel sheet together.
- **O3 (low, R2-S2, R2-P5; F9a root cause)** F9a `report/charts.py::_tornado` draws one panel per scenario in a fixed 7.2 x 3.8 in figure: cramped at 4, collapsed above 4. F9c draws groups of at most 3 scenarios (4: 2+2, 6: 3+3), which is readable, but each figure has its own x scale and the same title with no part number, and in the FR PDF the three x tick labels of each panel run together (`-500 0000 500 000`, also in the 3-scenario example; EN reads `-500,000  0  500,000`). `TORNADO_MAX_PANELS` can go once F9a scales or stacks the panels.
- **O4 (low, R2-P4; F9a)** Block diagram zone labels are 4.4 pt at full A4 width (5.5 px in a 560 px drawing, `report/diagram.py`): readable on screen or zoomed, small on paper. They never shrink below that now.
- **O5 (low, R2-S5, R2-P6)** On this host neither Liberation Sans nor DejaVu Sans is installed; WeasyPrint embeds Verdana and Andale Mono (`/BaseFont` of the PDF: Verdana, Verdana-Bold, Andale-Mono). The Dockerfile installs `fonts-dejavu` and `fonts-liberation`, but the Docker typesetting is not proven here (Docker not installed). Arial-metric proxies (Liberation Sans widths) gave the same counts for 3 scenarios (17 in round 0, with Verdana, Arial and Helvetica alike) and, in round 2, 1: 15, 2: 15/16, 3: 17, 4: 17/17, 5: 19, so the minimum of 12 is not at risk, but the page counts quoted here are for this Mac.
- **O6 (low, R1-S4, R2-S4, R2-P3; integrator)** `src/whsizing/report/pdf_text.py` (296 lines) and `src/whsizing/report/pdf_view.py` (224 lines) are F9c modules outside the listed owned paths (kept apart for the file-size limit); they should be added to F9c's owned paths. `docs/INTERPRETATIONS.md` I81 (F9c PDF conventions, items a-h, edited again in round 2) is also outside them; no numbering clash with I80 was found.
- **O7 (low, documented behaviour)** The write order is `trace.jsonl`, diagram SVGs, then the PDF last, so a failed write can leave a partial `report/` folder (the integrity gate runs before any write, so a gate failure leaves none). `diagram_<sid>.svg` has no language suffix (spec name): building FR then EN leaves the EN labels on disk; each `build_pdf` re-renders its own diagrams, so the PDFs are right. `build_excel` also writes `report/trace.jsonl` with identical bytes. The sweep chart is not placed (section 7 shows the sweep table, as the spec asks); 9 charts are placed.
- **O8 (low, test limits)** Numbers drawn inside the chart PNGs are not parsed back (F9a draws them). A 300-character client name spills the cover TOC onto page 2. Page-count tests assert 12-18 for the example study and need a re-check in a narrow-font environment.

## Not applicable here and why

- `tests/unit/test_f0_report.py::test_T0_5_docker_image_renders_one_page_pdf`: needs Docker, which is not installed on this Mac; skipped by its own skipif. It is F0's test. As a consequence the spec-font typesetting of the Docker image is not proven (O5).
- Real client data: none was used. Every run is synthetic (the small run and the 730-day `ecom_mid`, plus 4- to 8-scenario variants built by the auditors), and nothing leaves the machine.
- Domain-expert or human review of the report wording and French text: not possible in this environment, and no such review is recorded in the audit history. The checks are mechanical (numbers, order, separators, layout).
- GitHub CI: not run here.
- T9.1, T9.2 (Excel, F9b), T9.4 and T9.6 (F9a): other features' tests. F9c's gate integration is covered by the tests above and proof 5.
- The whole repository suite was not re-run by me; I ran the F9c command only. The round-2 runtime auditor ran the whole suite (1754 passed, 2 skipped).

## Quality gates, schema changes, size

Run read-only while writing this record, from `/Users/skarwech/saas_v1` (`--no-cache`, no file changed): `uv run ruff check` on the 3 F9c source modules and the 6 F9c test files: `All checks passed!`; `uv run ruff format --check`: `9 files already formatted`; `uv run pyright src/whsizing/report/pdf.py src/whsizing/report/pdf_text.py src/whsizing/report/pdf_view.py`: `0 errors, 0 warnings, 0 informations`. I did not run pyright on the test files.

Schema changes: none (`whsizing.schemas` untouched). New i18n keys only, in both `en.yaml` and `fr.yaml` (`pdf.*`, `msg.*`, and later `pdf.appc.formulas`, `pdf.footer.engine`). `report/__init__.py`: additive export of `build_pdf` and one docstring line. No package added. Outside the owned paths: `docs/INTERPRETATIONS.md` I81 (O6).

Sizes: `pdf.py` 310 lines, `pdf_text.py` 296, `pdf_view.py` 224, `styles.css` 157, `templates/report.html.j2` 34 plus 12 partials; tests: `test_f9_pdf.py` 506, `test_f9_pdf_support.py` 245, `test_f9_pdf_many.py` 276, `test_f9_i18n_pdf.py` 61, `test_f9_pdf_grid.py` 55, `test_f9_pdf_e2e.py` 144.

## Fresh test output

Command, run from `/Users/skarwech/saas_v1` on 2026-11-09 while writing this record, with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`:

```
uv run pytest tests/unit/test_f9_pdf*.py tests/e2e/test_f9_pdf*.py tests/property/test_f9_pdf*.py tests/unit/test_f0_report.py tests/unit/test_f9_i18n*.py -q -rA -s
```

Exit code 0. Passes per file (counted from the `PASSED` lines): `tests/unit/test_f9_pdf.py` 42, `tests/unit/test_f9_pdf_many.py` 46, `tests/e2e/test_f9_pdf_e2e.py` 4, `tests/property/test_f9_pdf_grid.py` 1, `tests/unit/test_f0_report.py` 1 (plus 1 skipped), `tests/unit/test_f9_i18n.py` 10, `tests/unit/test_f9_i18n_pdf.py` 4: 108 in total. Output below, trimmed: the structlog and captured-log lines (the `catalog_todo_sources` warnings of the synthetic runs and the expected `report_over_page_budget` warnings of the 6-scenario and fit-loop tests) are left out; the two timing lines printed by the T9.7 test, every `PASSED` line, the `SKIPPED` line and the summary line are verbatim.

```
F9 [fr]: PDF 4.9 s (17 pages, 586 KiB), Excel 0.6 s
F9 [en]: PDF 4.2 s (17 pages, 567 KiB), Excel 0.5 s
PASSED tests/unit/test_f9_pdf.py::test_T9_3_pdf_has_at_least_12_pages_and_the_run_id_on_each[fr]
PASSED tests/unit/test_f9_pdf.py::test_T9_3_pdf_has_at_least_12_pages_and_the_run_id_on_each[en]
PASSED tests/unit/test_f9_pdf.py::test_T9_3_sections_0_to_8_and_appendices_come_in_the_spec_order[fr]
PASSED tests/unit/test_f9_pdf.py::test_T9_3_sections_0_to_8_and_appendices_come_in_the_spec_order[en]
PASSED tests/unit/test_f9_pdf.py::test_T9_3_the_cover_dates_follow_the_language
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_executive_summary_is_exactly_one_page[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_executive_summary_is_exactly_one_page[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_no_text_runs_beyond_the_right_margin[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_no_text_runs_beyond_the_right_margin[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_diagram_labels_and_appendix_c_are_set_at_legible_sizes[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_diagram_labels_and_appendix_c_are_set_at_legible_sizes[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_cover_has_no_running_header_and_the_other_pages_have_it[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_cover_has_no_running_header_and_the_other_pages_have_it[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_running_footer_is_in_the_language_of_the_report[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_running_footer_is_in_the_language_of_the_report[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_appendix_c_formulas_are_titled_without_a_wrong_appendix_letter[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_appendix_c_formulas_are_titled_without_a_wrong_appendix_letter[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_limitations_box_of_section_8_is_not_split_across_pages[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_limitations_box_of_section_8_is_not_split_across_pages[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_limitations_box_is_drawn
PASSED tests/unit/test_f9_pdf.py::test_F9c_trace_numbers_print_counts_as_whole_numbers
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_warnings_count_of_appendix_c_has_no_decimals
PASSED tests/unit/test_f9_pdf.py::test_T9_5_fr_and_en_render_the_same_numbers
PASSED tests/unit/test_f9_pdf.py::test_T9_5_summary_cells_parse_back_to_the_raw_values
PASSED tests/unit/test_f9_pdf.py::test_T9_5_the_pdf_text_holds_the_summary_numbers_of_its_language[fr]
PASSED tests/unit/test_f9_pdf.py::test_T9_5_the_pdf_text_holds_the_summary_numbers_of_its_language[en]
PASSED tests/unit/test_f9_pdf.py::test_T9_5_french_html_uses_the_french_separators
PASSED tests/unit/test_f9_pdf.py::test_F9c_key_messages_have_no_recommended_label_and_carry_the_overlap_note[fr]
PASSED tests/unit/test_f9_pdf.py::test_F9c_key_messages_have_no_recommended_label_and_carry_the_overlap_note[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_every_chart_and_diagram_has_an_alt_with_the_source_note
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_appendix_c_trace_index_lists_every_summary_number
PASSED tests/unit/test_f9_pdf.py::test_T9_5_three_summary_numbers_are_reproduced_from_appendix_c[fr]
PASSED tests/unit/test_f9_pdf.py::test_T9_5_three_summary_numbers_are_reproduced_from_appendix_c[en]
PASSED tests/unit/test_f9_pdf.py::test_F9c_build_writes_the_pdf_the_trace_and_the_diagrams
PASSED tests/unit/test_f9_pdf.py::test_F9c_a_failed_integrity_check_raises_exit_5_and_writes_no_file
PASSED tests/unit/test_f9_pdf.py::test_F9c_an_untranslated_text_in_the_rendered_html_fails_ic8_and_writes_no_file
PASSED tests/unit/test_f9_pdf.py::test_F9c_an_unsupported_language_is_a_clear_config_error
PASSED tests/unit/test_f9_pdf.py::test_F9c_a_scenario_not_computed_is_greyed_with_its_reason
PASSED tests/unit/test_f9_pdf.py::test_F9c_without_a_baseline_the_business_case_shows_absolute_values_only
PASSED tests/unit/test_f9_pdf.py::test_F9c_the_html_is_built_from_the_model_not_from_a_recomputation
PASSED tests/unit/test_f9_pdf.py::test_F9c_a_client_name_with_markup_cannot_break_the_running_header
PASSED tests/unit/test_f9_pdf.py::test_F9c_each_scenario_has_its_chart_colour_in_the_tables_and_descriptions
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_traces_every_scenario_of_a_large_study[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios[fr-4_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios[4_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_traces_every_scenario_of_a_large_study[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios[en-4_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios[4_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_traces_every_scenario_of_a_large_study[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios[en-6_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios[6_scenarios-en]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_appendix_c_traces_every_scenario_of_a_large_study[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios[fr-6_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios[6_scenarios-fr]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_tornado_has_at_most_three_scenarios_per_figure[6_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_many_scenario_report_draws_its_charts_without_a_collapsed_layout[6_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_cash_flow_is_cut_into_tables_of_at_most_three_scenarios[6_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_tornado_has_at_most_three_scenarios_per_figure[4_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_many_scenario_report_draws_its_charts_without_a_collapsed_layout[4_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_cash_flow_is_cut_into_tables_of_at_most_three_scenarios[4_scenarios]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_the_overflow_check_sees_a_box_that_ends_beyond_the_margin
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[3-4-sizes0]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[4-3-sizes1]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[5-4-sizes2]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[6-3-sizes3]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[7-3-sizes4]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_balances_the_scenarios_over_the_tables[8-4-sizes5]
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_keeps_the_three_columns_of_a_scenario_together
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_split_leaves_a_table_that_is_not_by_scenario_alone
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_fit_pdf_takes_the_loosest_typesetting_within_the_budget
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_fit_pdf_keeps_the_tightest_and_logs_when_nothing_fits
PASSED tests/unit/test_f9_pdf_many.py::test_F9c_a_report_folder_that_cannot_be_written_is_a_whsizing_error
PASSED tests/e2e/test_f9_pdf_e2e.py::test_T9_3_pdf_of_a_real_run_has_12_to_18_pages_and_the_run_id
PASSED tests/e2e/test_f9_pdf_e2e.py::test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together
PASSED tests/e2e/test_f9_pdf_e2e.py::test_F9c_three_summary_numbers_of_every_scenario_are_reproduced_from_appendix_c
PASSED tests/e2e/test_f9_pdf_e2e.py::test_F9c_the_report_folder_holds_the_pdfs_the_trace_and_the_diagrams
PASSED tests/property/test_f9_pdf_grid.py::test_T9_5_prop_a_stacked_range_prints_back_to_its_raw_values
PASSED tests/unit/test_f0_report.py::test_T0_5_mock_result_renders_one_page_pdf
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
SKIPPED [1] tests/unit/test_f0_report.py:28: Docker not installed
108 passed, 1 skipped in 203.88s (0:03:23)
```
