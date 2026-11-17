# F9a audit record: Reporting core (report tables with trace ids, i18n, integrity checks IC1-IC8, charts, block diagram)

Written 2026-11-09 from the audit history of the F9a build (three audit rounds: round 0 on the initial build, rounds 1 and 2 after fixes; a spec-compliance auditor and a runtime-proof auditor in each) and from a fresh test run made while writing this record.

## Final verdict: pass_with_issues

- Fresh run: 205 passed, 0 failed, 0 skipped (136 F9a test items plus 69 in `test_f0_schemas.py`); every F9a-owned acceptance id (T9.2 precondition, T9.4, T9.5 prep, T9.6) has real assertions, and both round 2 audits (spec and runtime) returned `pass_with_issues` with no high or medium finding open.
- Eight low findings are still open (no round 3 was run), including one new in round 2 (the "Deficit" label can overlap the legend for envelopes of 60 m2 or less), and the report stage does not yet write the exported trace (`export_trace` exists but nothing calls it); T9.1, T9.3, T9.7 and the rendered part of T9.5 belong to F9b and F9c and were not exercised.

## Acceptance tests

Test files: `tests/unit/test_f9_tables.py` (plus `test_f9_tables_support.py`, a fixture module with no tests), `tests/unit/test_f9_integrity.py`, `tests/unit/test_f9_i18n.py`, `tests/unit/test_f9_charts.py`, `tests/unit/test_f9_diagram.py`, `tests/property/test_f9_formats.py`, `tests/property/test_f9_layout.py`, `tests/e2e/test_f9_core_e2e.py`, and `tests/unit/test_f0_schemas.py` (T0.3 round trip of the six new report models). 136 F9a test items in the fresh run (37 tables, 25 integrity, 10 i18n, 16 charts, 31 diagram, 8 formats, 4 layout, 5 e2e) plus 69 schema items. Nothing is skipped.

Test ids follow the spec: T9.1 Excel (F9b), T9.2 Excel values equal the JSON files (F9a covers the report-table side only: the "precondition"), T9.3 PDF (F9c), T9.4 integrity IC1-IC8, T9.5 FR/EN equal (F9a covers the "prep": identical raw numbers, formats, i18n parity), T9.6 block diagram area, T9.7 build time of both files (F9b and F9c). Rows marked `extra` are F9a tests beyond the spec ids (edge cases, charts, round 1 and round 2 regression tests).

| T-id | test function | status | what it proves |
|---|---|---|---|
| T9.1 | none in F9a | not_applicable | The Excel workbook is F9b (`excel.py` does not exist yet). F9a supplies the 12 `ReportTable` ids (next row). |
| T9.2 | `tests/unit/test_f9_tables.py::test_T9_2_twelve_tables_with_the_spec_names` | pass | `TABLE_IDS` is the 12 spec sheet names (summary, design_basis, demand_profile, design_day, scenarios, fte, capex_opex, cash_flow, sensitivity, assumptions, data_quality, methodology). |
| T9.2 | `test_T9_2_summary_values_equal_comparison_json` | pass | Reads `comparison/comparison.json` from the run folder and compares every `ComparisonRow` field (ranges lo/typ/hi, scalars, equipment, fit) to the Summary cells, with a guard that a new JSON field needs a row. The Excel snapshot itself is F9b. |
| T9.2 | `test_T9_2_scenario_tables_equal_result_json` | pass | The scenarios and fte tables equal the raw eligibility, storage, equipment, area and labor values of each scenario's `result.json` (ranges lo/typ/hi). |
| T9.2 | `test_T9_2_business_tables_equal_finance_json` | pass | capex_opex and cash_flow equal each scenario's `finance.json`: capex items and total, year-1 opex, TCO, NPV, payback, opex by year, own and delta cash flows. |
| T9.2 | `test_T9_2_every_row_has_one_cell_per_column_and_keys_are_unique` | pass | Structure: each row has one cell per block column, row keys are unique. |
| T9.2 | `test_T9_2_scenario_tables_have_lo_typ_hi_columns_per_scenario` | pass | Scenario tables carry lo/typ/hi columns per scenario. |
| T9.2 | `test_T9_2_numeric_cells_of_scenario_tables_are_raw_numbers_with_units` | pass | Numeric cells hold raw numbers (not strings) with a unit. |
| T9.2 | `test_T9_2_every_euro_cell_carries_the_eur_unit` | pass | Invariant over every cell of the 12 tables: a euro cell carries unit `eur` (round 1 regression: the opex-by-year cells had none and escaped IC7). |
| T9.2 | `test_T9_2_assumptions_one_row_per_catalog_param_with_origin` | pass | Assumptions: one row per catalog `Param` with its origin. |
| T9.2 | `test_T9_2_blocks_name_the_header_of_their_label_column` | pass | Blocks name the header of the row-label column (`TableBlock.label_header`). |
| T9.2 | `test_T9_2_design_basis_lists_every_basis_field_with_its_origin` | pass | Design basis lists every basis field with its origin. |
| T9.2 | `test_T9_2_demand_profile_and_design_day_hold_the_profile_numbers` | pass | demand_profile and design_day hold the profile numbers. |
| T9.2 | `test_T9_2_data_quality_table_holds_rules_coverage_and_dropped_rows` | pass | data_quality holds the rules, coverage and dropped rows of the DQ report. |
| T9.2 | `test_T9_2_methodology_counts_todo_and_confidence_l_parameters_it_used` | pass | Methodology limits count the TODO-source and confidence-L parameters actually used. |
| T9.2 | `test_T9_2_summary_notes_hold_the_banner_and_the_localised_confidence_note` | pass | Summary notes: the "indicative study" banner and the localised confidence note (rebuilt via i18n from `Comparison.overlaps`, not the English F8 string). |
| T9.2 | `test_T9_2_sensitivity_table_holds_tornado_break_even_and_sweep` | pass | Sensitivity table holds the tornado, the break-even and the sweep. |
| T9.2 | `test_T9_2_cash_flow_without_baseline_scenario_keeps_every_cumulative_column` | pass | Round 1 fix: with no scenario that has a baseline, the cash_flow keeps the own-flow cumulative column for every scenario. |
| T9.2 | `test_T9_2_cash_flow_baseline_scenario_has_no_cumulative_of_its_own_cost` | pass | Round 1 fix: with a scenario as baseline (S0), the baseline has no cumulative column, so every cumulative column is a cumulative delta. |
| T9.2 | `test_T9_2_payback_not_reached_is_said_not_left_empty` | pass | Round 1 fix: payback None with a baseline shows the `payback.not_reached` text in summary and capex_opex, FR and EN. |
| T9.2 | `test_T9_2_finance_notes_are_shown_in_capex_opex_and_in_the_limitations` | pass | Round 1 fix: `FinancialResult.notes` appear under capex_opex and as `limit.gen.finance.<i>` limitation rows. |
| T9.2 | `test_T9_2_a_note_of_one_scenario_names_it` | pass | A note that applies to one scenario names that scenario. |
| T9.2 | `test_T9_2_flag_counts_show_as_integers` | pass | Flag counts use the integer format (were shown as `30.00`). |
| T9.2 | `test_T9_2_the_data_quality_limit_is_translated_in_both_languages[usable / usable with caveats / remediation needed]` (3 items) | pass | The DQ limitation uses one i18n key per band, so the FR text has no English band code. |
| T9.2 | `test_T9_2_no_baseline_at_all_is_not_the_clients_current_operation` | pass | `baseline_id None` is shown as "none", not as "client's current operation". |
| extra | `test_edge_scenario_not_computed_gives_a_greyed_column_with_the_reason` | pass | A not-computed scenario gives a greyed column with its reason and empty cells; integrity holds. |
| extra | `test_edge_no_baseline_shows_absolute_values_and_omits_npv_and_payback` | pass | No baseline: absolute values, NPV and payback rows absent, no delta columns, no empty payback ranking row. |
| extra | `test_edge_no_sensitivity_leaves_the_table_empty_with_a_note` | pass | No sensitivity: the table is empty with a note; integrity holds. |
| extra | `test_edge_payback_not_reached_leaves_out_the_payback_ranking_row` | pass | Round 2 fix: the ranking-by-payback row is omitted when nothing is ranked. |
| extra | `test_edge_a_run_folder_without_the_profile_is_a_config_error` | pass | A run folder without the profile raises `ConfigError`. |
| extra | `test_edge_an_unsupported_language_is_a_config_error` | pass | `load_report_data(run, 'de')` raises `ConfigError`. |
| extra | `test_edge_a_corrupt_run_file_is_a_config_error_naming_it[trace / design_day / dq_report / daily series]` (4 items) | pass | Truncated run files raise `ConfigError` naming the file (no raw pydantic or polars exception). |
| extra | `test_edge_n_warnings_node_recorded_upstream_is_kept` | pass | The report's in-memory `<sid>.report.n_warnings` node yields to one recorded upstream by F6/F8. |
| T9.4 | `tests/unit/test_f9_integrity.py::test_T9_4_untampered_real_run_passes_all_checks` | pass | `check_integrity(run) == []` on the real small run (also with `html=` and with `data=`). |
| T9.4 | `test_T9_4_ic1_fails_on_a_numeric_cell_without_a_trace_id` | pass | IC1 fires on a numeric cell without a trace id (asserts the id and the location). |
| T9.4 | `test_T9_4_ic1_fails_when_the_trace_node_does_not_exist` | pass | IC1 fires when the cited trace node does not exist. |
| T9.4 | `test_T9_4_ic1_fails_when_the_trace_node_holds_another_value` | pass | IC1 fires when the node holds another value or another world than the cell. |
| T9.4 | `test_T9_4_ic1_really_looks_at_hundreds_of_cells` | pass | Guard against a no-op IC1: more than 600 cells are inspected. |
| T9.4 | `test_T9_4_ic2_fails_on_an_input_that_resolves_to_nothing` | pass | IC2 fires on a trace input that resolves to nothing (world-specific node removed). |
| T9.4 | `test_T9_4_ic2_fails_on_an_unknown_param_but_accepts_data_leaves` | pass | IC2 fires on an unknown `param:` id; `data:` ids are accepted as dataset leaves (see open issue 4). |
| T9.4 | `test_T9_4_ic3_fails_on_a_used_param_without_a_source` | pass | IC3 fires on a used parameter without a source (catalog tampered). |
| T9.4 | `test_T9_4_ic3_fails_when_the_todo_count_of_section_8_is_wrong` | pass | IC3 fires when the TODO count in the methodology limits differs from the count recomputed from the traces. |
| T9.4 | `test_T9_4_ic4_fails_when_the_area_total_is_not_the_sum_of_the_zones` | pass | IC4 boundary: +0.6 m2 fails, +0.4 m2 passes (0.5 m2 tolerance). |
| T9.4 | `test_T9_4_ic5_fails_when_the_fte_total_is_not_the_sum_of_the_activities` | pass | IC5 fires when the FTE total is not the sum of the activities. |
| T9.4 | `test_T9_4_ic6_fails_when_the_cumulative_is_not_the_sum_of_the_flows` | pass | IC6 fires on a tampered cumulative (asserts the ids set is `{'IC6'}`). |
| T9.4 | `test_T9_4_ic6_fails_when_a_cumulative_has_no_delta_column_to_sum` | pass | Round 1 fix: IC6 flags a cumulative column with no delta column to sum. |
| T9.4 | `test_T9_4_ic6_holds_with_a_scenario_as_the_baseline` | pass | IC6 holds when S0 is the baseline scenario. |
| T9.4 | `test_T9_4_ic7_fails_on_a_negative_area_hours_or_cost` | pass | IC7 fires on a negative m2, h or eur value. |
| T9.4 | `test_T9_4_ic7_accepts_signed_flows_that_are_negative_by_nature` | pass | Cells marked `signed` (NPV, own and delta cash flows, cumulative) are exempt; un-marking one makes IC7 fire. |
| T9.4 | `test_T9_4_ic7_covers_the_opex_by_year_cells` | pass | Round 1 fix: cell and trace node both set to -5, IC7 alone fires on an opex-by-year cell. |
| T9.4 | `test_T9_4_ic7_reads_a_euro_cell_without_a_unit_as_euros` | pass | Round 1 fix: IC7 treats a cell with fmt `eur` as euros even without a unit. |
| T9.4 | `test_T9_4_ic8_fails_on_a_missing_sentinel_in_the_rendered_html` | pass | IC8 fires on an untranslated `{{ missing: ... }}` sentinel in the HTML. |
| T9.4 | `test_T9_4_ic8_without_html_fails_on_a_key_missing_in_a_language` | pass | Without HTML, IC8 fires on an i18n key missing in one language. |
| T9.4 | `test_T9_4_a_flag_code_without_a_message_fails_ic8` | pass | IC8 fires on a flag code that has no message. |
| T9.4 | `test_T9_4_assert_integrity_raises_with_exit_code_5_and_lists_the_issues` | pass | `assert_integrity` raises `ReportIntegrityError` with `exit_code` 5 and lists the issues. |
| T9.4 | `test_T9_4_every_cited_trace_id_resolves_in_the_exported_trace` | pass | Round 2 fix: every trace id cited in the four IC1 tables resolves in the reloaded exported file with the cell's value and scenario scope; the scenario files lack the n_warnings node. |
| T9.4 | `test_T9_4_the_exported_trace_is_reproducible_and_holds_every_scenario` | pass | `export_trace` output is reproducible and holds every scenario's nodes. |
| T9.4 | `test_T9_4_export_trace_reports_an_unwritable_path_and_conflicting_nodes` | pass | `export_trace` raises `WhsizingError` on an unwritable path or a node id recorded with two contents. |
| T9.5 (prep) | `tests/unit/test_f9_i18n.py::test_T9_5_i18n_files_hold_the_same_keys` | pass | `fr.yaml` and `en.yaml` have identical key sets. |
| T9.5 (prep) | `test_T9_5_i18n_placeholders_match_in_both_languages` | pass | Placeholders match in both languages. |
| T9.5 (prep) | `test_T9_5_missing_key_gives_the_sentinel_and_never_raises` | pass | A missing key gives the sentinel and never raises. |
| T9.5 (prep) | `test_T9_5_fr_number_format_uses_narrow_no_break_space_and_comma` | pass | FR numbers: U+202F thousands separator and decimal comma. |
| T9.5 (prep) | `test_T9_5_en_number_format_uses_comma_thousands_and_point` | pass | EN numbers: comma thousands and decimal point. |
| T9.5 (prep) | `test_T9_5_dates_are_dd_mm_yyyy_in_fr_and_iso_in_en` | pass | Dates: dd/mm/yyyy in FR, ISO in EN. |
| T9.5 (prep) | `test_T9_5_render_cell_formats_by_fmt` | pass | `render_cell` follows `Cell.fmt`. |
| T9.5 (prep) | `test_T9_5_every_flag_code_of_the_engine_has_a_message_in_both_languages` | pass | Every flag code found by scanning the engine source has a message in both languages. |
| T9.5 (prep) | `test_T9_5_every_key_the_tables_use_exists_in_both_languages` | pass | Every i18n key the tables use exists in both languages. |
| T9.5 (prep) | `test_T9_5_an_unsupported_language_is_a_config_error_not_a_file_error` | pass | `t(key, 'de')` raises `ConfigError`, not `FileNotFoundError`. |
| T9.5 (prep) | `tests/property/test_f9_formats.py::test_T9_5_prep_number_format_round_trips` | pass | Hypothesis: FR/EN number format then parse round-trips. |
| T9.5 (prep) | `test_T9_5_prep_fr_and_en_print_the_same_number` | pass | FR and EN print the same number (property). |
| T9.5 (prep) | `test_T9_5_prep_percent_format_round_trips` | pass | Percent format round-trips. |
| T9.5 (prep) | `test_T9_5_prep_general_format_keeps_six_significant_digits` | pass | The general format keeps six significant digits. |
| T9.5 (prep) | `test_T9_5_prep_dates_round_trip_in_both_languages` | pass | Dates round-trip in FR and EN. |
| T9.5 (prep) | `test_T9_5_prep_fr_and_en_tables_hold_identical_raw_numbers` | pass | `fr.tables == en.tables` (labels are i18n keys, numbers raw). |
| T9.5 (prep) | `test_T9_5_prep_numbers_render_to_the_same_values_in_fr_and_en` | pass | Every numeric cell rendered FR and EN, parsed back, is equal. |
| T9.5 (prep) | `test_T9_5_prep_fr_text_uses_the_french_separators` | pass | FR text uses the French separators. |
| T9.5 | rendered Excel and PDF identical in FR and EN | not_applicable | Needs F9b and F9c; only the prep above is in F9a. |
| T9.6 | `tests/unit/test_f9_diagram.py::test_T9_6_drawn_area_equals_the_zone_sum[S0, S1, S2]` (3 items) | pass | Layout area equals the zone sum (rel 1e-12) and the areas parsed back from the written SVG (`zone-<name>-<n>` groups, shoelace) equal the zone sum (rel 1e-4). |
| T9.6 | `test_T9_6_overflow_is_drawn_hatched_outside_with_the_deficit` | pass | Building at 60 % of the budget: drawn area equals zone sum, overflow area equals the deficit, hatch pattern and "Deficit: N m2" in the SVG. |
| T9.6 | `test_T9_6_layout_follows_the_spec_algorithm` | pass | Geometry follows the spec algorithm (storage strip, full-width strips, docks). |
| T9.6 | `test_T9_6_scale_is_two_pixels_per_metre` | pass | 1 m = 2 px. |
| T9.6 | `test_T9_6_the_svg_is_sized_in_px_so_that_one_metre_is_two_px` | pass | Round 1 fix: the root `width`/`height` are in px, not pt. |
| T9.6 | `test_T9_6_labels_carry_the_zone_name_and_its_area[en-Storage, fr-Stockage]` (2 items) | pass | Labels carry the translated zone name and its area. |
| T9.6 | `test_T9_6_the_svg_is_reproducible` | pass | Same input, same SVG bytes. |
| T9.6 | `test_T9_6_build_diagrams_skips_a_scenario_not_computed` | pass | `build_diagrams` skips a not-computed scenario. |
| T9.6 | `test_T9_6_a_building_without_area_is_a_config_error` | pass | A building without an area raises `ConfigError`. |
| T9.6 | `test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[0.5, 0.85, 0.9, 0.99, 1.0, 1.1, 1.5]` (7 items) | pass | Round 1 fix: docks touch the south wall (receiving west, shipping east), area kept, overflow equals the deficit, no overlap, at each utilisation. |
| T9.6 | `test_T9_6_docks_larger_than_the_building_join_the_strips_and_keep_their_area` | pass | Docks larger than the whole building join the strips and keep their area. |
| T9.6 | `test_T9_6_labels_of_a_narrow_building_stay_inside_the_picture[en, fr]` (2 items) | pass | Round 1 fix: for a 60 m2 building with a deficit, every text extent is inside the figure (fails with the margin set to 0). |
| T9.6 | `test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[en, fr x 300, 600, 1000, 1500 m2]` (8 items) | pass | Round 2 fix: no pair of text boxes overlaps for short buildings with nine zones. |
| T9.6 | `test_T9_6_an_unwritable_folder_is_a_whsizing_error` | pass | An unwritable output folder raises `WhsizingError`. |
| T9.6 | `tests/property/test_f9_layout.py::test_T9_6_property_drawn_area_is_the_zone_sum` | pass | Hypothesis: drawn area equals the zone sum. |
| T9.6 | `test_T9_6_property_no_overlap_and_the_envelope_is_respected` | pass | Hypothesis: no overlap, envelope respected. |
| T9.6 | `test_T9_6_property_overflow_area_is_the_deficit` | pass | Hypothesis: overflow area equals the deficit. |
| T9.6 | `test_T9_6_property_docks_are_on_the_south_wall_whenever_they_fit` | pass | Hypothesis: docks on the south wall whenever they fit. |
| T9.7 | none in F9a | not_applicable | Both files built in under 60 s needs F9b and F9c. The F9a core budget is checked by the e2e row below. |
| extra | `tests/unit/test_f9_charts.py::test_charts_build_every_chart_as_a_png_named_by_id_and_language` | pass | 10 PNGs per language, named by id and language. |
| extra | `test_charts_png_is_reproducible` | pass | Same input, same PNG bytes. |
| extra | `test_charts_have_title_caption_and_source_note_from_i18n[fr, en]` (2 items) | pass | Title, caption and the "engine v, catalog v, run id" source note, from i18n. |
| extra | `test_charts_labels_are_translated_and_numbers_use_the_language_format` | pass | Labels translated, FR/EN tick formats. |
| extra | `test_charts_a_scenario_has_the_same_colour_in_every_chart` | pass | A scenario keeps one colour across charts. |
| extra | `test_charts_the_data_charts_use_no_scenario_colour` | pass | Round 1 fix: the demand charts use a neutral colour outside every scenario palette. |
| extra | `test_charts_plot_the_numbers_of_the_run` | pass | Plotted numbers equal the run's. |
| extra | `test_charts_without_sensitivity_leave_out_tornado_and_sweep` | pass | Tornado and sweep are skipped without sensitivity. |
| extra | `test_charts_use_the_spec_fonts` | pass | Liberation Sans / DejaVu Sans font choice. |
| extra | `test_charts_cash_flow_with_a_baseline_scenario_plots_cumulative_deltas_only` | pass | Round 1 fix: with S0 as baseline, only cumulative deltas are plotted. |
| extra | `test_charts_title_caption_and_source_note_fit_inside_the_picture[fr, en]` (2 items) | pass | Round 2 fix: window extents of title, caption and source note of all 10 charts stay inside the figure. |
| extra | `test_charts_cash_caption_says_what_is_drawn[fr, en]` (2 items) | pass | Round 2 fix: the delta caption only when a non-disabled delta column exists, else the own-flows caption. |
| extra | `test_charts_an_unwritable_folder_is_a_whsizing_error` | pass | An unwritable output folder raises `WhsizingError`. |
| extra | `tests/e2e/test_f9_core_e2e.py::test_F9a_core_builds_tables_charts_and_diagrams_within_budget[fr, en]` (2 items) | pass | On synthetic ecom_mid (730 days, about 1 M lines), tables, charts and diagrams build in under 20 s per language (builder measured about 0.6 to 0.8 s). |
| extra | `test_F9a_core_integrity_holds_with_a_scenario_as_the_baseline` | pass | Integrity holds with S0 as the baseline scenario on ecom_mid. |
| extra | `test_F9a_core_every_summary_number_resolves_to_a_trace_tree_down_to_params` | pass | Every Summary number resolves through the trace tree down to params. |
| extra | `test_F9a_core_fr_and_en_models_are_identical` | pass | FR and EN report models are identical. |
| T0.3 | `tests/unit/test_f0_schemas.py::test_T0_3_every_exported_model_has_an_example` and `test_T0_3_schema_json_round_trip[Cell, IntegrityIssue, ReportTable, TableBlock, TableColumn, TableRow]` | pass | The six new `schemas/report.py` models are exported, have a factory example (`mock_report_table_parts`) and round-trip through JSON (69 items pass in the file). |

## Proofs

All proofs below were captured by the auditors during the audit; the scripts are in the audit scratchpad (`/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F9a/`, written `$AUD` below), not in the repository. Outputs are excerpts as reported by the auditors; they were not re-run for this record. The fresh run for this record is the last section.

1. **Exported trace: every cited id resolves and the file is reproducible (round 2, spec and runtime auditors).** Claim: `export_trace` writes one JSONL holding every scenario's nodes plus the report's own `<sid>.report.n_warnings`; every trace id cited in the summary, scenarios, fte and capex_opex tables resolves in it with the cell's value; EN and FR give identical bytes; the scenario `trace.jsonl` files still lack the n_warnings node.
   Command: `uv run python $AUD/r3_export.py`
   Output: `run nodes 3289 hash en/fr 79c4eed16b 79c4eed16b | n_warnings nodes [('S0.report.n_warnings',0.0,'S0','typ'),('S1.report.n_warnings',2.0,'S1','typ'),...] | cited 1120 unresolved/different 0 integrity [] | scenario trace.jsonl contains report.n_warnings: False x3` and, runtime auditor, `b2b en nodes 3293 deterministic True cited 1124 unresolved 0 mismatch 0 issues []`; also `grep -rn export_trace src/whsizing` outside `report/` finds nothing.

2. **Tamper detection on a real run folder through the public API (round 0 and round 1, runtime auditor).** Claim: doubling `S1.capex.total` in `scenarios/S1/trace.jsonl` on disk is caught by IC1 and `assert_integrity` raises with exit code 5.
   Command: `uv run python $AUD/disk_tamper.py`
   Output: `untampered: [] | disk-tampered trace (S1.capex.total x2): [('IC1','summary/comparison/capex/S1.typ',...),('IC1','capex_opex/capex/capex.total/S1.typ',...)] | exit_code 5 | report integrity: 2 issue(s)`.

3. **IC7 gap found, then closed (round 0 failure, round 1 pass; both auditors).** Claim (round 0): a negative opex-by-year cell, with cell and trace node consistent, passed all eight checks because the 120 opex-by-year euro cells had unit `''`. Round 1: the cells carry unit `eur` and IC7 also reads fmt `eur` as euros.
   Command: `uv run python $AUD/ic7_gap.py`
   Output round 0: `opex cell: 4165.0 unit='' fmt='eur' trace=S0.opex.y1.energy signed=False` and `issues=[]` after setting cell and node to -1234.5 (control on capex.total: IC7 `negative value -1234.5 with unit eur`). Output round 1: `opex cell: 4165.0 unit='eur' fmt='eur' ...` and `issues with negative opex (cell+trace consistent): [('IC7', 'negative value -1234.5 with unit eur')]`.

4. **T9.6 area read back from the written SVG, and a hand-computed layout (rounds 0 and 2).** Claim: the area drawn in the SVG equals the zone sum for every scenario and language; the hatched overflow equals the deficit; the layout matches a hand computation.
   Commands: `uv run python $AUD/svgarea.py tiny b2b` (runtime, round 0); `uv run python $AUD/probe9.py` (spec, round 0); `uv run python $AUD/r3_layout.py` (spec, round 2).
   Output: `tiny S1 rects 10 drawn 455.383 zone sum 455.383 area.total typ 455.383 hatched 395.383 deficit typ 395.383 building 60.0`; `b2b S1 drawn 950.936 zone sum 950.936 area.total typ 950.936`; hand example, building 10000 m2 (W = H = 100 m): `storage 0,0,100x40 | packing y=40 h=10 | circulation y=50 h=8 | receiving x=0 y=77.639 w=22.361 h=22.361 | shipping x=77.639 y=77.639` equal to the hand values (sqrt(500) = 22.361); round 2 example, 9 zones totalling 9000 m2: `drawn 9000.0 = sum 9000`, and at a 5000 m2 building `deficit 4000 = sum of the OVER rectangles`.

5. **Dock zones leave the dock wall above about 87 % utilisation (round 0 failure), fixed (round 1 pass).** Claim: docks stay on the south wall at any utilisation, with area kept, no overlap and overflow equal to the deficit; a 3000-case random fuzz of `layout_blocks` finds no violation.
   Commands: `uv run python $AUD/probe15.py` (round 0); `uv run python $AUD/r2_diag.py` and `uv run python $AUD/r2_fuzz.py` (round 1).
   Output round 0: `util 0.85 docks on south wall: True | util 0.90 docks on south wall: False {'shipping_staging': (81.2, False), 'receiving_staging': (87.2, False)} H=99.7 | util 1.10 receiving_staging (96.5, True)`. Output round 1: `u=0.90 onwall=True kept=True overlap=False | u=1.10 onwall=True kept=True overflow=813.6 deficit=813.6 | util=3.0 ... overflow=5966.7 deficit=5966.7 | fuzz 3000 cases: {'area': 0, 'overlap': 0, 'wall': 0, 'nowidth': 0, 'inside': 0, 'ovl_inside': 0}`.

6. **Chart text clipped (round 1 failure), fixed (round 2 pass).** Claim: the reworded cash-flow caption ran past the figure edge in EN and FR; after the fix no title, caption or source note is clipped or overlaps the axes in any of 104 charts (6 runs x 2 languages x up to 10 charts).
   Commands: `uv run python $AUD/r2_caption.py` (round 1); `uv run python $AUD/r3_clip.py` (round 2).
   Output round 1: `CLIPPED s0base en cash: text ends x=823 > fig width 720` and `CLIPPED s0base fr cash: text ends x=816 > fig width 720`. Output round 2: `charts checked 104 defects 0`; the new own-flows caption ends at x=341 px (EN) and 397 px (FR) of 720.

7. **Diagram legend overlapped the caption and source note for short buildings (round 1 failure), fixed (round 2 pass).** Claim: with nine zones, a building of 600 m2 gave 2 text overlaps; after the fix all 30 probe lines give 0 overlaps and 0 clipped labels, including 60 m2 and 500,000 m2 buildings, EN and FR.
   Command: `uv run python $AUD/r2_legend2.py`
   Output round 1: `tight en S1 bldg=600 figH=196px text-overlaps=2 clipped=[]` (`'Shipping staging 2 m2'` against `'Zones drawn to scale...'`, `'Receiving staging 1 m2'` against `'Source: engine 0.1.0...'`). Output round 2: `tight en S1 bldg=600 figH=281px text-overlaps=0 clipped=[]`, `tiny en S1 bldg=60 figH=291px text-overlaps=0`, `huge en S1 bldg=500000 figH=2092px text-overlaps=0`.

8. **The round 2 regression tests are not tautological (round 2, runtime auditor).** Claim: each new test fails when its fix is removed, checked on a mutated copy of the package in the audit scratchpad (`PYTHONPATH=$AUD/mut`).
   Command: `PYTHONPATH=$AUD/mut uv run pytest tests/unit/test_f9_diagram.py -k legend_clear -q -x` and the analogous `-k` selections for M2 to M5.
   Output: `M1 1 failed, 23 deselected | M2 1 failed, 1 passed, 14 deselected | M3 1 failed, 14 deselected | M4 1 failed, 33 deselected | M5 1 failed, 23 deselected`. (M1 is the legend-height fix removed and M2 the old long cash caption restored; the exact test behind M3 to M5 was clipped in the auditor's report.) The engineer reported analogous mutation checks in round 1: removing the IC7 unit fix, the IC6 guard and the dock-wall rule makes 3, 4 and 6 tests fail respectively.

9. **Determinism across processes (round 0, runtime auditor).** Claim: charts and SVGs are byte-identical when built in two separate Python processes (26 files, EN and FR, b2b run).
   Command: `cd $AUD/out/b2b && shasum -a 256 en/* fr/* > h1; (rerun exercise.py b2b); shasum -a 256 en/* fr/* > h2; diff h1 h2`
   Output: `IDENTICAL across processes: 26 files`.

10. **i18n parity and format spot checks (round 0 spec auditor; round 1 spec auditor).** Claim: the two YAML files have identical key sets and no duplicate keys, FR uses U+202F thousands and a decimal comma, EN the English format, dates follow the language, and a missing key gives the sentinel without raising.
    Command: `uv run python $AUD/probe8.py` (round 0), repeated in round 1.
    Output: `NNBSP=0x202f; fr '1 234 567,89' en '1,234,567.89'; fmt_pct(0.123,'fr') = '12,3 %'; dates 09/11/2026 vs 2026-11-09; set(en)^set(fr) = set()` (462 keys per file at round 0); round 1: `fmt_number(1234567.891,'fr',1) = '1 234 567,9'`, missing key gives `{{ missing:nokey.x }}`.

## Audit rounds

Auditors per round: spec-compliance (spec) and runtime-proof (proof). Round 0 audits the initial build; the fix step before round 1 and the fix step before round 2 are the engineer's. All six audits returned `pass_with_issues`; none returned `fail`.

### Round 0 (initial build, 151 F9a tests)

Both audits: `pass_with_issues`, 151 passed, 0 failed. 18 raw findings (spec 10: 4 medium, 6 low; proof 8: 2 medium, 6 low), merged into the 16 rows below. Whole-suite run (proof auditor): 2 failed, 1363 passed, 2 skipped; the 2 failures are strict-XPASS tests in `tests/golden/test_g1_*` about the F3 ABC tie-break, not in an F9a file.

| # | severity | finding | resolution in the round 1 fix |
|---|---|---|---|
| 1 | medium (spec + proof) | IC7 does not cover the 120 opex-by-year euro cells (unit `''`); a negative opex consistent with its trace passes | fixed: unit `eur` on those rows, IC7 also reads fmt `eur` as euros; 3 new tests; mutation check |
| 2 | medium (spec) | cash_flow table and chart mix the baseline scenario's own cumulative with the others' cumulative delta | fixed: the baseline scenario has no cumulative column when any scenario has a delta; table note; IC6 flags a cumulative with no delta column; caption changed; 5 new tests |
| 3 | medium (spec) | `FinancialResult.notes` never rendered; the payback row disappears when every payback is None | fixed: notes shown under capex_opex and as limitation rows; NPV and payback rows appear together; `payback.not_reached` text; 3 new tests |
| 4 | medium (spec) | block diagram: receiving and shipping leave the dock wall above about 87 % utilisation | fixed: docks always on the south wall when they fit in the envelope; strips that no longer fit move below as hatched overflow; 3 new tests, mutation check (the old rule fails 6) |
| 5 | medium (proof; the spec auditor noted it inside its low IC1-scope finding) | `<sid>.report.n_warnings` exists only in memory, absent from the exported `trace.jsonl` | deferred to F6/F8 (runs are immutable); node now skipped if upstream records it; blocker raised. Later covered inside F9a by `export_trace` (round 2 fix) |
| 6 | low (spec) | opex by year shown in the typical world only; lo/hi exist as trace nodes | deferred: `FinancialResult.opex_by_year` is typical-only; a layout decision for F9b/F9c |
| 7 | low (spec + proof) | IC1 inspects scenario columns only; the Summary `dq_score` cell has no trace id | deferred: dataset metric with no `TraceNode`; removing the row could break F9b/F9c |
| 8 | low (spec) | FR report shows the English DQ band code in `limit.gen.dq` | fixed: one i18n key per band; 3-band test |
| 9 | low (spec) | IC2 accepts any `data:` id without resolving it | deferred: no registry of `data:` roots; an allow-list would exit 5 on any new engine root |
| 10 | low (spec) | F9a interpretations not in `docs/INTERPRETATIONS.md` | deferred: outside F9a paths; proposed I79 text handed over in the blockers |
| 11 | low (spec) | nits: (a) flag count shown `30.00`, (b) demand charts reuse scenario colours, (c) SVG sized in pt, (d) `svg.fonttype none` | (a), (b), (c) fixed with tests; (d) deferred: text stays text on purpose, font is the spec's choice |
| 12 | low (proof) | baseline `None` shown as "Client's current operation", contradicting the "no baseline" limit | fixed: new `baseline.none` key; test |
| 13 | low (proof) | unsupported language gives a bare `FileNotFoundError` | fixed: `ConfigError` in `load_report_data` and `i18n.texts`; 2 tests |
| 14 | low (proof) | corrupt run files and unwritable output folders raise raw pydantic/OSError | fixed: `ConfigError` naming the file; `WhsizingError` for charts and diagrams; tests |
| 15 | low (proof) | narrow building: "Building N m2" and "Deficit" labels clipped at x < 0 | fixed: left margin widened; test fails with margin 0 |
| 16 | low (proof) | five helper modules (`cells.py`, `grid.py`, `style.py`, `tables_fin.py`, `tables_data.py`) are outside the owned-paths list | deferred, not a defect: kept for the file-size limit, collide with nothing; the integrator may add them to F9a's paths |

Tally of the round 1 fix report (17 entries): 10 fixed (one of them, nits, partly), 7 deferred.

### Round 1 (after fix 1, 189 F9a-set tests)

Both audits: `pass_with_issues`, 189 passed, 0 failed. 20 raw findings (spec 10: 3 medium, 7 low; proof 10: 3 medium, 7 low). Whole-suite run (proof auditor, one strict-XPASS test deselected): 1 failed, 1403 passed, 2 skipped, 1 deselected; the failure is the other F3/G1 strict-XPASS test (`tests/golden/test_g1_finance_register.py`), not F9a. Lint, format and types on the F9a paths: `All checks passed!`, `23 files already formatted`, `0 errors, 0 warnings, 0 informations`. The auditors confirmed the round 0 findings fixed (IC7, cash-flow convention, notes and payback, dock wall, band token, nits a to c, baseline None, language, raw exceptions). They found two new medium defects (the caption that the cash-flow fix lengthened, and the diagram legend), carried the `n_warnings` medium over, and listed the deferred lows again plus new ones:

| # | severity | finding | resolution in the round 2 fix |
|---|---|---|---|
| 1 | medium (spec + proof) | cash-flow chart caption, lengthened by the round 1 fix, is clipped in EN (x=823 of 720 px) and FR (816) | fixed: one short caption line, a second variant for the own-flows case; new extent test over the title, caption and source note of 10 charts x 2 languages |
| 2 | medium (spec + proof) | diagram legend overlaps the caption and source note for short buildings (nine zones, under about 1,200 m2) | fixed: figure height includes the legend; 8-case test; mutation check (6 of 8 fail without the fix) |
| 3 | medium (spec + proof) | `n_warnings` trace node exists only in memory (unresolved from round 0) | fixed inside F9a by `export_trace(data, path)`, exported from `whsizing.report`; the new test also caught a real bug (the in-memory node had scope `global`, now the scenario id). Caveat stated by the engineer and re-rated low by the round 2 auditors: nothing calls `export_trace` yet and the scenario `trace.jsonl` files still lack the node |
| 4 | low (spec + proof) | Summary `dq_score` numeric cell untraced, IC1 scenario columns only | deferred: needs a non-scenario tracer in `ReportData.tracers`, which would change the F9b/F9c contract |
| 5 | low (spec + proof) | opex by year typical world only | deferred: layout decision for F9b/F9c |
| 6 | low (spec + proof) | IC2 accepts any `data:` id | deferred: needs a registry owned by F2/F6 |
| 7 | low (spec + proof) | F9a interpretations still not in `docs/INTERPRETATIONS.md` | deferred: outside F9a paths; proposed I79 in the blockers |
| 8 | low (spec + proof) | `svg.fonttype none` (font fallback), labels 5.5 px at 1 m = 2 px | deferred, informational: F9c must scale the SVG up (about 1.5x gives about 6 pt) |
| 9 | low (spec, new) | Summary ranking block keeps an empty "Ranking by payback" row with no baseline or no payback | fixed: empty ranking rows omitted; test |
| 10 | low (spec + proof, new) | `FinancialResult.notes` appear in English in the FR report; the package docstring was stale; F7's S0 note ("no baseline scenario (client baseline switched off)") contradicts "Baseline = S0" | deferred: free text from F7, no key to translate; the stale docstring is fixed; F7 wording reported as a blocker |
| 11 | low (proof, new) | with only the baseline computed, the cash chart plots own cumulative cost under the caption "Cumulative delta ... baseline is the zero line" | fixed: caption variant `chart.cash.caption_own` chosen when no non-disabled delta column exists; test for client baseline, S0 baseline and baseline-only run |

### Round 2 (after fix 2, 205 tests of the feature set)

Both audits: `pass_with_issues`, 205 passed, 0 failed, no high or medium finding. The auditors confirmed the round 1 medium findings resolved (chart clipping: 0 defects in 104 charts; legend overlap: 0 on all real runs; `export_trace` resolves every cited id) and both re-rated the `n_warnings` finding from medium to low. 8 low findings each (spec 8, proof 8), all carried into "Open issues" below. One is new: the "Deficit: N m2" label can overlap a legend row for very small envelopes with a deficit. No fix round followed, so none of these has been addressed. No whole-suite run is recorded for round 2.

## Open issues

Not resolved at the time of this record. None is high or medium.

1. **Report stage does not emit the exported trace.** `whsizing.report.export_trace(data, path)` writes the scenario nodes plus the report's `<sid>.report.n_warnings`, but nothing in `src/whsizing` outside `report/` calls it, and the per-scenario `trace.jsonl` files still lack the node. On disk the Summary `n_warnings` cells resolve only once F9b/F9c/F10 (`cli/sizing.py build_reports`) call `export_trace(data, run_dir/'report'/'trace.jsonl')`. Optional upstream fix: F6/F8 record the non-info flag count as a node in each scenario trace; the report skips its own node when upstream has it.
2. **New in round 2, not fixed: Deficit label vs legend.** For an envelope of about 60 m2 or less with a deficit, the centred "Deficit: N m2" label can overlap a legend row (150-case grid: 19 collisions, all with building 20, 40 or 60 m2 and deficit above 0; 240 random layouts: 3). The real 60 m2 "tiny" run and the other five real runs show 0 overlaps. The spec auditor's rough threshold was wider (envelope side below about 22 m, under roughly 480 m2), but the observed hits are all at 60 m2 or less.
3. **IC1 scope.** The Summary study block holds one numeric cell without a trace id (`dq_score`, a dataset metric from F2 with no `TraceNode`); IC1 inspects only cells in scenario columns of summary, scenarios, fte and capex_opex (1124 of 1125 numeric cells on b2b). Narrower than the literal "every numeric cell in Summary".
4. **IC2 accepts any `data:` id.** A typo in a `data:` input passes; the check is weaker than "resolves to a Param or a dataset-derived node". The exported `S1.report.n_warnings` node itself has input `data:S1.flags`, which resolves to no node.
5. **Opex by year in the typical world only** (`FinancialResult.opex_by_year` is schema-limited); the spec row reads "item x scenario (lo/typ/hi), opex by year". Capex items, capex total, year-1 opex, TCO, NPV and cost per line carry lo/typ/hi.
6. **`docs/INTERPRETATIONS.md` has no F9a entry** (checked at writing time: no `I79` or `F9` line). Proposed I79 (no `[EXPERT]` or `[VERIFY]` marker, since `test_g1_expert_rulings.py` parses markers): (a) IC7 exempts cells marked `signed` and treats fmt `eur` as euros; (b) the block-diagram envelope is a square of side sqrt(building area), the legend sets the picture height for a short envelope, 1 m = 2 px; (c) opex by year typical world only; (d) `n_warnings` is a report-derived node, scope = scenario id, written by `export_trace`; (e) cash flow: cumulative = sum of the delta flows, the baseline scenario has no delta and no cumulative column, own-flow cumulative only when no scenario has a baseline; (f) IC1 scope as in issue 3; (g) payback "not reached" shown as text, the ranking-by-payback row omitted when nothing is ranked; (h) `FinancialResult.notes`, design_basis notes and DQ rule messages shown in the language the pipeline wrote them (English).
7. **English text in the FR report.** `FinancialResult.notes` (capex_opex notes and `limit.gen.finance.<i>` rows), design_basis row labels (F4 notes) and DQ rule messages are free text and pass through untranslated; IC8 cannot catch free text. F7's note for a scenario that is itself the baseline ("no baseline scenario (client baseline switched off)") contradicts "Baseline = S0"; the wording is F7's.
8. **Diagram fonts and size.** `svg.fonttype none` with `DejaVu Sans` means labels depend on the font where the file is opened (QuickLook falls back to a serif font); labels are 5.5 px at the spec scale of 1 m = 2 px, so F9c must scale the SVG up on the A4 page.
9. **Spec gap: `Building` has no width.** The diagram assumes a square envelope of side sqrt(area); `layout_blocks(..., width_m=)` overrides it (marked `ponytail` in `diagram.py`).
10. **Hand-off notes for F9b and F9c.** The `cash_flow` baseline scenario has no delta and no cumulative column; `cash_flow.notes`, `capex_opex.notes` and `limit.gen.finance.<i>` rows are new cells to render; the payback row can hold the key cell `payback.not_reached`; `Tracer.tree` reports `data:` inputs as `unresolved`, which are valid dataset leaves, so the F9c trace index must treat kind `unresolved` with a `data:` id as a leaf; the trace index appendix should read `ReportData.tracers`.
11. **Scope left out on purpose (builder's list).** The overflow share has no row in the scenarios table (it is 1 minus row `eligibility.share_lines`, no trace node; F9c computes it for the section 4 text); no queue block (Erlang-C pools) in the scenarios table; the live-formula stretch of the Excel sheets (F9b); T9.1, T9.3, T9.7.
12. **Outside F9a (pre-existing, found by the auditors).** `tests/golden/test_g1_abc_tiebreak.py::test_T1_5_engine_abc_follows_the_same_tie_break_chain` and `tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7` were strict-XPASS failures about the F3 `profile/abc.py` tie-break; the xfail markers need removing by the F3/G1 owner. At build time `tests/unit/test_f10_cli.py` (F10) had 4 pyright errors, so `tests/unit/test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[pyright]` fails repo-wide while the F9a paths are pyright-clean. Neither was re-run for this record.
13. **Environment.** Liberation Sans is not installed on the build machine; `style.fonts()` falls back to DejaVu Sans, which the spec allows.

## Not applicable here and why

- T9.1 (Excel workbook with 12 sheets) and the Excel snapshot comparison of T9.2: F9b (`excel.py`). F9a only supplies the 12 `ReportTable` models, checked against `comparison.json`, `result.json` and `finance.json`.
- T9.3 (PDF of 12 to 18 pages with the run id in the text): F9c (`pdf.py` is still the walking-skeleton stub; templates and `styles.css` untouched).
- T9.7 (both files built in under 60 s): needs F9b and F9c. The F9a core (tables, charts, diagrams) is asserted under 20 s per language in the e2e test; the builder measured about 0.6 to 0.8 s per language on ecom_mid (tables 0.05 s, charts 0.55 to 0.71 s, diagrams 0.03 to 0.04 s) and the round 2 runtime auditor measured 1.4 s for load, charts and diagrams in EN and FR on the b2b run and 0.08 s for `check_integrity(run)`. Not re-measured here.
- T9.5 rendered comparison (Excel and PDF identical in FR and EN): needs F9b and F9c; the F9a prep tests pass.
- No test in F9a carries a skip marker: the tests for T9.1, T9.3 and T9.7 do not exist in the repository yet (`grep` for `test_T9_1`, `test_T9_3`, `test_T9_7` under `tests/` finds nothing at writing time) because they belong to F9b and F9c.
- Real client data: not available; all runs use the small real pipeline run (F1 data, F2 to F8) and the synthetic profiles (ecom_mid, b2b_cases); no real client data was used.
- Domain expert review: not possible here and not required by an F9a acceptance test; F9a adds no `[EXPERT]` or `[VERIFY]` value. The F9a interpretations in open issue 6 are not yet in the register. No human has reviewed the look of the charts and diagrams; only the auditors' own renders (QuickLook, PNG views) and text-extent probes.
- Docker, GitHub CI: not needed for the F9a tests; nothing was run in a container or in CI.
- Repository state: no git commits; `pyproject.toml` and `uv.lock` untouched; no new dependency. Schema changes are additive only (next section).

## Quality gates, schema changes, size

As reported by the auditors and the builder during the audit (not re-run for this record):

```
uv run ruff check <F9a src, schemas, F9a tests, fixtures>     All checks passed!        (round 0 audits)
uv run ruff format --check <same>                             41 files already formatted
uv run pyright <same>                                         0 errors, 0 warnings, 0 informations
```

Round 1 runtime audit on the same gates: `All checks passed!`, `23 files already formatted`, `0 errors, 0 warnings, 0 informations`. Round 2: the auditors report the test set only; gates were not reported separately. Size (round 2 runtime audit): largest file 457 lines, no function over 50 lines. Builder-reported coverage of the report modules: about 96 to 97 % with the F9a tests (not re-measured).

Schema changes (additive): new `src/whsizing/schemas/report.py` with `Cell` (the spec's five fields value, unit, fmt, trace_id, world, plus `signed` and `args`), `TableColumn`, `TableRow`, `TableBlock`, `ReportTable`, `IntegrityIssue`; re-exported from `whsizing.schemas`; examples in `tests/fixtures/factories.py` (`mock_report_table_parts`) so T0.3 passes. Helper modules added inside `report/` beyond the owned-paths list: `cells.py`, `grid.py`, `style.py`, `tables_fin.py`, `tables_data.py`.

Public API (stable, documented in `report/__init__.py`): `load_report_data(run, lang)`, `build_charts`, `chart_png`, `build_diagram`, `build_diagrams`, `layout_blocks`, `check_integrity`, `assert_integrity`, `export_trace`, `t`, `fmt_number`, `fmt_pct`, `fmt_date`, `render_cell`, `unit_label`. Tracer extension (reported as a blocker for F6/F8): `ComparisonRow.n_warnings` has no engine node, so `report/data.py` adds `<sid>.report.n_warnings` in memory (typ world, scope = scenario id).

## Fresh test output

Command, run from `/Users/skarwech/saas_v1` on 2026-11-09 while writing this record, with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`:

```
uv run pytest tests/unit/test_f9_tables*.py tests/unit/test_f9_integrity*.py tests/unit/test_f9_i18n*.py tests/unit/test_f9_charts*.py tests/unit/test_f9_diagram*.py tests/property/test_f9_*.py tests/e2e/test_f9_core*.py tests/unit/test_f0_schemas.py -q -rA -p no:cacheprovider
```

Exit code 0. Passes per file (counted from the `PASSED` lines): `tests/unit/test_f9_tables.py` 37, `tests/unit/test_f9_integrity.py` 25, `tests/unit/test_f9_i18n.py` 10, `tests/unit/test_f9_charts.py` 16, `tests/unit/test_f9_diagram.py` 31, `tests/property/test_f9_formats.py` 8, `tests/property/test_f9_layout.py` 4, `tests/e2e/test_f9_core_e2e.py` 5, `tests/unit/test_f0_schemas.py` 69; total 205. The captured stderr of the run holds only structlog lines (for example the loader's `catalog_todo_sources` warning with `count: 72, total: 72`); no test failed and none was skipped.

Output, trimmed (progress lines, the `PASSED` lines of the F9a files and of the new-model T0.3 items in `test_f0_schemas.py`, and the summary line; the other 62 `test_f0_schemas.py` `PASSED` lines and the captured-log sections are omitted):

```
........................................................................ [ 35%]
........................................................................ [ 70%]
.............................................................            [100%]
==================================== PASSES ====================================
PASSED tests/unit/test_f9_tables.py::test_T9_2_twelve_tables_with_the_spec_names
PASSED tests/unit/test_f9_tables.py::test_T9_2_every_row_has_one_cell_per_column_and_keys_are_unique
PASSED tests/unit/test_f9_tables.py::test_T9_2_scenario_tables_have_lo_typ_hi_columns_per_scenario
PASSED tests/unit/test_f9_tables.py::test_T9_2_summary_values_equal_comparison_json
PASSED tests/unit/test_f9_tables.py::test_T9_2_scenario_tables_equal_result_json
PASSED tests/unit/test_f9_tables.py::test_T9_2_business_tables_equal_finance_json
PASSED tests/unit/test_f9_tables.py::test_T9_2_numeric_cells_of_scenario_tables_are_raw_numbers_with_units
PASSED tests/unit/test_f9_tables.py::test_T9_2_assumptions_one_row_per_catalog_param_with_origin
PASSED tests/unit/test_f9_tables.py::test_T9_2_blocks_name_the_header_of_their_label_column
PASSED tests/unit/test_f9_tables.py::test_T9_2_design_basis_lists_every_basis_field_with_its_origin
PASSED tests/unit/test_f9_tables.py::test_T9_2_demand_profile_and_design_day_hold_the_profile_numbers
PASSED tests/unit/test_f9_tables.py::test_T9_2_data_quality_table_holds_rules_coverage_and_dropped_rows
PASSED tests/unit/test_f9_tables.py::test_T9_2_methodology_counts_todo_and_confidence_l_parameters_it_used
PASSED tests/unit/test_f9_tables.py::test_T9_2_summary_notes_hold_the_banner_and_the_localised_confidence_note
PASSED tests/unit/test_f9_tables.py::test_T9_2_sensitivity_table_holds_tornado_break_even_and_sweep
PASSED tests/unit/test_f9_tables.py::test_edge_scenario_not_computed_gives_a_greyed_column_with_the_reason
PASSED tests/unit/test_f9_tables.py::test_edge_no_baseline_shows_absolute_values_and_omits_npv_and_payback
PASSED tests/unit/test_f9_tables.py::test_edge_no_sensitivity_leaves_the_table_empty_with_a_note
PASSED tests/unit/test_f9_tables.py::test_edge_a_run_folder_without_the_profile_is_a_config_error
PASSED tests/unit/test_f9_tables.py::test_T9_2_every_euro_cell_carries_the_eur_unit
PASSED tests/unit/test_f9_tables.py::test_T9_2_cash_flow_without_baseline_scenario_keeps_every_cumulative_column
PASSED tests/unit/test_f9_tables.py::test_T9_2_cash_flow_baseline_scenario_has_no_cumulative_of_its_own_cost
PASSED tests/unit/test_f9_tables.py::test_T9_2_payback_not_reached_is_said_not_left_empty
PASSED tests/unit/test_f9_tables.py::test_T9_2_finance_notes_are_shown_in_capex_opex_and_in_the_limitations
PASSED tests/unit/test_f9_tables.py::test_T9_2_a_note_of_one_scenario_names_it
PASSED tests/unit/test_f9_tables.py::test_T9_2_flag_counts_show_as_integers
PASSED tests/unit/test_f9_tables.py::test_T9_2_the_data_quality_limit_is_translated_in_both_languages[usable]
PASSED tests/unit/test_f9_tables.py::test_T9_2_the_data_quality_limit_is_translated_in_both_languages[usable with caveats]
PASSED tests/unit/test_f9_tables.py::test_T9_2_the_data_quality_limit_is_translated_in_both_languages[remediation needed]
PASSED tests/unit/test_f9_tables.py::test_T9_2_no_baseline_at_all_is_not_the_clients_current_operation
PASSED tests/unit/test_f9_tables.py::test_edge_an_unsupported_language_is_a_config_error
PASSED tests/unit/test_f9_tables.py::test_edge_a_corrupt_run_file_is_a_config_error_naming_it[scenarios/S1/trace.jsonl-trace]
PASSED tests/unit/test_f9_tables.py::test_edge_a_corrupt_run_file_is_a_config_error_naming_it[design/design_day.json-DesignDay]
PASSED tests/unit/test_f9_tables.py::test_edge_a_corrupt_run_file_is_a_config_error_naming_it[dq/dq_report.json-DQReport]
PASSED tests/unit/test_f9_tables.py::test_edge_a_corrupt_run_file_is_a_config_error_naming_it[canonical/daily_series.parquet-daily series]
PASSED tests/unit/test_f9_tables.py::test_edge_n_warnings_node_recorded_upstream_is_kept
PASSED tests/unit/test_f9_tables.py::test_edge_payback_not_reached_leaves_out_the_payback_ranking_row
PASSED tests/unit/test_f9_integrity.py::test_T9_4_untampered_real_run_passes_all_checks
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic1_really_looks_at_hundreds_of_cells
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic1_fails_on_a_numeric_cell_without_a_trace_id
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic1_fails_when_the_trace_node_does_not_exist
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic1_fails_when_the_trace_node_holds_another_value
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic2_fails_on_an_input_that_resolves_to_nothing
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic2_fails_on_an_unknown_param_but_accepts_data_leaves
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic3_fails_on_a_used_param_without_a_source
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic3_fails_when_the_todo_count_of_section_8_is_wrong
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic4_fails_when_the_area_total_is_not_the_sum_of_the_zones
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic5_fails_when_the_fte_total_is_not_the_sum_of_the_activities
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic6_fails_when_the_cumulative_is_not_the_sum_of_the_flows
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic7_fails_on_a_negative_area_hours_or_cost
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic7_accepts_signed_flows_that_are_negative_by_nature
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic8_fails_on_a_missing_sentinel_in_the_rendered_html
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic8_without_html_fails_on_a_key_missing_in_a_language
PASSED tests/unit/test_f9_integrity.py::test_T9_4_a_flag_code_without_a_message_fails_ic8
PASSED tests/unit/test_f9_integrity.py::test_T9_4_assert_integrity_raises_with_exit_code_5_and_lists_the_issues
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic7_covers_the_opex_by_year_cells
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic7_reads_a_euro_cell_without_a_unit_as_euros
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic6_fails_when_a_cumulative_has_no_delta_column_to_sum
PASSED tests/unit/test_f9_integrity.py::test_T9_4_ic6_holds_with_a_scenario_as_the_baseline
PASSED tests/unit/test_f9_integrity.py::test_T9_4_every_cited_trace_id_resolves_in_the_exported_trace
PASSED tests/unit/test_f9_integrity.py::test_T9_4_the_exported_trace_is_reproducible_and_holds_every_scenario
PASSED tests/unit/test_f9_integrity.py::test_T9_4_export_trace_reports_an_unwritable_path_and_conflicting_nodes
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
PASSED tests/unit/test_f9_charts.py::test_charts_build_every_chart_as_a_png_named_by_id_and_language
PASSED tests/unit/test_f9_charts.py::test_charts_png_is_reproducible
PASSED tests/unit/test_f9_charts.py::test_charts_have_title_caption_and_source_note_from_i18n[fr]
PASSED tests/unit/test_f9_charts.py::test_charts_have_title_caption_and_source_note_from_i18n[en]
PASSED tests/unit/test_f9_charts.py::test_charts_labels_are_translated_and_numbers_use_the_language_format
PASSED tests/unit/test_f9_charts.py::test_charts_a_scenario_has_the_same_colour_in_every_chart
PASSED tests/unit/test_f9_charts.py::test_charts_plot_the_numbers_of_the_run
PASSED tests/unit/test_f9_charts.py::test_charts_without_sensitivity_leave_out_tornado_and_sweep
PASSED tests/unit/test_f9_charts.py::test_charts_use_the_spec_fonts
PASSED tests/unit/test_f9_charts.py::test_charts_the_data_charts_use_no_scenario_colour
PASSED tests/unit/test_f9_charts.py::test_charts_cash_flow_with_a_baseline_scenario_plots_cumulative_deltas_only
PASSED tests/unit/test_f9_charts.py::test_charts_an_unwritable_folder_is_a_whsizing_error
PASSED tests/unit/test_f9_charts.py::test_charts_title_caption_and_source_note_fit_inside_the_picture[fr]
PASSED tests/unit/test_f9_charts.py::test_charts_title_caption_and_source_note_fit_inside_the_picture[en]
PASSED tests/unit/test_f9_charts.py::test_charts_cash_caption_says_what_is_drawn[fr]
PASSED tests/unit/test_f9_charts.py::test_charts_cash_caption_says_what_is_drawn[en]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_drawn_area_equals_the_zone_sum[S0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_drawn_area_equals_the_zone_sum[S1]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_drawn_area_equals_the_zone_sum[S2]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_overflow_is_drawn_hatched_outside_with_the_deficit
PASSED tests/unit/test_f9_diagram.py::test_T9_6_layout_follows_the_spec_algorithm
PASSED tests/unit/test_f9_diagram.py::test_T9_6_scale_is_two_pixels_per_metre
PASSED tests/unit/test_f9_diagram.py::test_T9_6_labels_carry_the_zone_name_and_its_area[en-Storage-m\xb2]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_labels_carry_the_zone_name_and_its_area[fr-Stockage-m\xb2]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_the_svg_is_reproducible
PASSED tests/unit/test_f9_diagram.py::test_T9_6_build_diagrams_skips_a_scenario_not_computed
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_building_without_area_is_a_config_error
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[0.5]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[0.85]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[0.9]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[0.99]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[1.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[1.1]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_receiving_and_shipping_stay_on_the_dock_wall_at_any_utilisation[1.5]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_docks_larger_than_the_building_join_the_strips_and_keep_their_area
PASSED tests/unit/test_f9_diagram.py::test_T9_6_labels_of_a_narrow_building_stay_inside_the_picture[en]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_labels_of_a_narrow_building_stay_inside_the_picture[fr]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_the_svg_is_sized_in_px_so_that_one_metre_is_two_px
PASSED tests/unit/test_f9_diagram.py::test_T9_6_an_unwritable_folder_is_a_whsizing_error
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[en-300.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[en-600.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[en-1000.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[en-1500.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[fr-300.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[fr-600.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[fr-1000.0]
PASSED tests/unit/test_f9_diagram.py::test_T9_6_a_short_building_keeps_the_legend_clear_of_the_caption_and_source[fr-1500.0]
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_number_format_round_trips
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_fr_and_en_print_the_same_number
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_percent_format_round_trips
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_general_format_keeps_six_significant_digits
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_dates_round_trip_in_both_languages
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_fr_and_en_tables_hold_identical_raw_numbers
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_numbers_render_to_the_same_values_in_fr_and_en
PASSED tests/property/test_f9_formats.py::test_T9_5_prep_fr_text_uses_the_french_separators
PASSED tests/property/test_f9_layout.py::test_T9_6_property_drawn_area_is_the_zone_sum
PASSED tests/property/test_f9_layout.py::test_T9_6_property_no_overlap_and_the_envelope_is_respected
PASSED tests/property/test_f9_layout.py::test_T9_6_property_overflow_area_is_the_deficit
PASSED tests/property/test_f9_layout.py::test_T9_6_property_docks_are_on_the_south_wall_whenever_they_fit
PASSED tests/e2e/test_f9_core_e2e.py::test_F9a_core_builds_tables_charts_and_diagrams_within_budget[fr]
PASSED tests/e2e/test_f9_core_e2e.py::test_F9a_core_builds_tables_charts_and_diagrams_within_budget[en]
PASSED tests/e2e/test_f9_core_e2e.py::test_F9a_core_integrity_holds_with_a_scenario_as_the_baseline
PASSED tests/e2e/test_f9_core_e2e.py::test_F9a_core_every_summary_number_resolves_to_a_trace_tree_down_to_params
PASSED tests/e2e/test_f9_core_e2e.py::test_F9a_core_fr_and_en_models_are_identical
PASSED tests/unit/test_f0_schemas.py::test_T0_3_every_exported_model_has_an_example
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[Cell]
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[IntegrityIssue]
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[ReportTable]
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[TableBlock]
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[TableColumn]
PASSED tests/unit/test_f0_schemas.py::test_T0_3_schema_json_round_trip[TableRow]
...
205 passed in 36.09s
```
