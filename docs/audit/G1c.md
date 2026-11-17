# G1c audit: Interpretations register and golden oracle sync (after F3 and F5b)

## Verdict: pass

Both final-round (round 1) auditors returned `pass`. All 7 round-0 findings (4 medium, 3 low) were fixed in round 1, and the spec auditor re-checked each fix with mutants and with oracle-vs-engine scratch runs. The fresh run gives 35 passed, 0 failed and 5 skipped. The 5 skips are engine-parity placeholders for stages that are still 0-byte stubs.
One round-1 low finding stays open, because there was no round 2. No committed test pins oracle-engine parity on I49-I52. The spec auditor judged this outside G1c's scope and still returned `pass`. It is listed under Open issues, with the [EXPERT] rulings and the cross-feature blockers.

Schema changes: none (`schema_changes: []`). The oracle still does not import `whsizing`.

Files touched by the build: `tests/golden/oracle.py`, `tests/golden/demand.py`, `tests/golden/build_golden.py`, `tests/golden/workbook.py`, `tests/golden/test_g1_sync.py` (new), `tests/golden/test_g1_remediation.py`, `tests/golden/golden_values.json`, `tests/golden/golden_case.xlsx` and `docs/INTERPRETATIONS.md`. In round 1 the fix also edited `tests/golden/test_g1_engine_parity.py`, which lost its T3.1 placeholder.

## Acceptance tests

Every test below belongs to T1.5. Statuses come from the fresh run and the final audit (round 1). In round 0 the spec auditor rated three tests "weak": the above-20 % no-time test, the trend test and the catalog test. Round 1 tightened, re-pinned or replaced all three (see Audit rounds), and the round-1 audit rates them pass.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero` | pass | I49: with 2 snapshots and one SKU missing from the older one, that SKU's average is q/2, not the mean of the rows present. The mutant `n_snap = 1` fails it. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_inventory_only_skus_are_orphans_in_stock_and_dead_stock` | pass | I50: an inventory-only SKU is an orphan. It is never eligible, it goes to pallet_rack in class C, and it counts as dead stock. n_skus_total = 101 and share_skus = 91/101. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window` | pass | I50 (new in round 1): dead stock reads the **last** snapshot, so a SKU stocked only in the older snapshot (avg 150, last 0) is not dead. A line on period_end − 180 is outside the window and a line on period_end − 179 is inside it. It kills `dead_avg` and `window_ge` (proof 2). |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_are_left_out_of_intraday_shares` | pass | I51 below 20 %: lines at local midnight are left out of the intraday shares but still count in the daily totals, so h00 gains nothing. A no-exclusion mutant is killed. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_above_20_percent_use_the_default_profile` | pass | I51 above 20 %: the flat 08-17 default profile is used, confidence is L and peak_hour_share = 1/9. In round 1 the guard was tightened to a strict `0.20 < share`. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile` | pass | I51 boundary (new in round 1): with 1 untimed line out of 5 (exactly 20 %), the measured shares are kept with confidence H. With 2 out of 6 the default profile is used with L. This pins the spec's strict "more than 20 %", and the `>=` mutant is killed. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile` | pass | I51 (new in round 1): when the design weekday has no timed line and the overall untimed share is ≤ 20 %, the oracle uses the default profile with H instead of raising ZeroDivisionError. Other weekdays keep their measured shares. It kills `zero_total` (proof 2). |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_trend_cagr_from_monthly_mean_daily_lines` | pass | I52: a 737-day synthetic series gives CAGR = 1.01^12 − 1 (rel 1e-9). Confidence is pinned on calendar spans: 2022-01-01..2024-12-31 (36.0 months) gives M and 2023-01-01..2024-12-28 gives L. tiny_golden gives (None, L). The mutants `conf_days`, `lt24`, `lt36`, `cm30` and `cm_noplus1` are killed by a `test_T1_5_` test whose name is clipped in the audit history (proof 2). |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_cube_building_works_add_floor_prep_on_the_grid` | pass | I30: S2 building works = area.total × 60 + A_grid × 20. S0 has no floor prep, and contingency is 10 % of the other items. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_oracle_param_ids_and_values_match_the_catalog` | pass | I47 drift guard, renamed in round 1 (the build name was `..._param_counts_and_cube_values_match_the_catalog`). The catalog has 72 Param blocks. Taken together, the ids that S0 and S2 read equal all 52 non-amr_gtp catalog ids, and each oracle typ equals the catalog typ. It kills `lowconf_name`, `station` and `labor_typ`. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_share_stock_cube_is_zero_without_stock` | pass | I10: with an empty inventory the whole pipeline runs, and share_stock_cube = 0.0 for both prefixes. This fixes the G1b ZeroDivisionError. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_flag_table_and_low_confidence_count` | pass | The flags follow the F6 table order. S0 ends with `F_LOW_CONFIDENCE:30`. S2 has `F_SCALE_LOW` then `F_ROBOT_DENSITY` (robots/A_grid = 0.4747 > 0.05) and `F_LOW_CONFIDENCE:50`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_missing_dims_hazmat_temperature_are_ineligible_and_case_fallbacks_hold` | pass | Unchanged from G1b. Missing dims, hazmat and frozen/chilled SKUs are ineligible, and the case fallbacks hold. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_assume_eligible_if_missing_dims_raises_F_ELIG_ASSUMED` | pass | Unchanged. With assume on, the share is reported and `F_ELIG_ASSUMED` is raised. A known violation still means ineligible. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_orphan_skus_are_kept_never_eligible_and_counted_in_every_share` | pass | Unchanged. Orphans are kept, never eligible and counted in every share denominator. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_sla_window_explicit_derived_midnight_and_equal_times` | pass | Unchanged. I16 SLA window cases. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_explicit_sla_window_drives_lambda_and_dock_shortfall_flag` | pass | Unchanged. An explicit window drives λ_sla and raises `F_DOCK_SHORTFALL`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_decant_station_hours_add_to_the_ports` | pass | Unchanged. I23 decant load on the ports. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_zero_eligible_lines_degenerate_to_manual` | pass | Unchanged. I48: at share_lines = 0 the cube scenario degenerates to manual. There is no floor prep and no density flag when A_grid is 0. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_three_inventory_snapshots_are_not_silently_flat` | pass | Unchanged. With 3 or more snapshots the oracle raises `NotImplementedError` (I12). |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_erlang_queue_and_sla_flags` | pass | Unchanged. The Erlang queue, SLA risk and unstable flags. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_golden_basis_exercises_pallet_parcel_and_overflow_branches` | pass | Unchanged. The golden data exercises the pallet, multi-parcel and overflow branches. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_workbook_headers_and_stage_cells_name_their_formula` | pass | Unchanged. Every header and stage cell names its formula, now including the new `last_stock` and `dead_stock` SKU columns. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_spreadsheet_equals_golden_json` | pass | The xlsx and the JSON hold the same keys, and every stage value cell has a formula comment. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_build_is_deterministic_and_committed_files_are_current` | pass | Two builds are byte-identical, and the committed golden files equal a fresh build. The `labor_typ` mutant also fails this test. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_anchors_match_tiny_golden_readme` | pass | The tiny_golden README anchors hold. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_values_respect_spec_invariants` | pass | The spec invariants hold on the golden values (T4.3, T3.2, λ split, T6.10, ports, NPV). |
| T1.5 (engine parity T4.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T4_1_design_day` | not_applicable (skip) | `src/whsizing/design/__init__.py` is 0 bytes. |
| T1.5 (engine parity T6.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_1_storage` | not_applicable (skip) | `src/whsizing/engine/__init__.py` is 0 bytes. |
| T1.5 (engine parity T6.2) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_2_labor` | not_applicable (skip) | The engine stage is a stub. |
| T1.5 (engine parity T6.3) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_3_area_and_docks` | not_applicable (skip) | The engine stage is a stub. |
| T1.5 (engine parity T7.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T7_1_finance` | not_applicable (skip) | `src/whsizing/finance/__init__.py` is 0 bytes. |
| T1.5 (engine parity T3.1) | `tests/golden/test_f3_golden.py` (owned by F3) | pass (not a G1 file) | Round 1 deleted the stale T3.1 placeholder, so the G1 skips went from 6 to 5. T3.1 runs and passes in F3's own golden test. |

There are 8 supporting helper tests in `test_g1_oracle.py` with no T-id, and all 8 pass: `test_erlang_c_values`, `test_erlang_wq_matches_mm1_closed_form`, `test_payback_interpolation_and_edge_cases`, `test_npv_irr_against_numpy_financial`, `test_levels_and_area_formulas`, `test_positions_formulas`, `test_classification_formulas` and `test_calendar_and_misc_formulas`.

## Proofs (captured by the auditors during the audit)

The spec auditor captured all of these proofs. In both rounds the proof auditor's record has only a verdict and test counts, with no proofs. Scratch scripts live under `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/`, written `$SP/` below. Text marked `…[clipped]` was already cut off in the audit history and is reproduced as given.

1. **Fix round, before and after: oracle and engine diverged in round 0 and agree in round 1** (round 0, then round 1).
   Command: `uv run python $SP/audit_G1c/parity.py` (and `$SP/audit_G1c/design_wd_no_time.py` in round 1)
   ```
   round 0:
   A dead stock, idle SKU only in older snapshot: oracle dead_stock = True avg 150.0 | engine dead_stock_skus = 0
   B no-time share exactly 0.20: oracle conf L peak 0.111 | engine conf H peak 0.5
   D 2022-01-01 2024-12-31 1096 days: oracle H | engine M 36.0
   D 2023-01-01 2024-12-28 728 days: oracle M | engine L 23.9199
   round 1:
   A dead stock, idle SKU only in older snapshot: oracle dead_stock = False avg 150.0 | engine dead_stock_skus = 0 oracle n dead = 0
   B no-time share exactly 0.20: oracle conf H peak 0.5 | engine conf H peak 0.5
   ... oracle ([0.0 x8, 0.111 x9, 0.0 x7], 'H') / engine peak_hour_share 0.1111111111111111 conf H
   ```
   In round 1, case D of this script is stale: it passes days to `trend_confidence`, which now takes months. Proof 4 covers the trend agreement instead.
2. **The fixes are pinned: all 14 named round-1 mutants (the audit record's claim says 15) of the oracle are killed by the G1 tests, and the unmutated baseline passes 35/35** (round 1).
   Command: `$SP/audit_G1c/mutate.sh <name> <file> <old> <new>` for r2_dead_avg, r2_in_last_min, r2_strict_ge, r2_zero_total, r2_zero_conf_L, r2_window_ge, r2_conf_days, r2_lt36, r2_lt24, r2_cm30, r2_cm_noplus1, r2_lowconf_name, r2_station and r2_labor_typ
   ```
   [r2_baseline] 35 passed
   [r2_dead_avg] FAILED ...test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window 1 failed, 34 passed
   [r2_strict_ge] FAILED ...test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile
   [r2_zero_total] FAILED ...test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile
   [r2_window_ge] FAILED ...dead_stock_reads_the_last_snapshot_and_a_180_day_window
   [r2_conf_days] / [r2_lt24] / [r2_lt36] / [r2_cm30] / [r2_cm_noplus1] FAILED ...test_T1_5_ …[clipped]
   ```
3. **On the datasets of the G1c tests, the oracle equals the built F3 engine exactly** (round 0).
   Command: `uv run python $SP/audit_G1c/i49_i51_parity.py; uv run python $SP/audit_G1c/i50_parity.py`
   ```
   I49 avg_units oracle 5009.5 engine 5009.5 | dead oracle 0 engine 0
   I51 max |oracle-engine| share 0.0 peak oracle 0.13366336633663367 engine 0.13366336633663367 conf H H
   oracle dead ['0eb2fa35fbcbfdd2', 'INV-ONLY'] | engine dead_stock_skus 2; avg_units 6597.0/6597.0; cover_days 63.953/63.953; trend (None,'L') / None L
   ```
4. **End to end on realistic multi-year histories, `build_golden.run` and the F3 engine agree.** The data has about 10-17k lines, 2 inventory snapshots, untimed lines and dead-stock SKUs at the window boundary. The two sides agree on trend CAGR and confidence, on the intraday shares, peak and confidence, on the dead-stock count and on the stock totals (round 1).
   Command: `uv run python $SP/audit_G1c/e2e_r2.py`
   ```
   1 three-years: period 2022-01-01..2024-12-31 lines 17061
     trend  oracle M 0.270393 | engine M 0.270393
     intraday oracle H peak 0.109022 wd 0 | engine H peak 0.109022 | max |Δshare| = 0.0
     dead   oracle [12 skus] | engine n 12
     stock  oracle avg_units 3212.0 n_in_stock 74 | engine 3212.0 74
   3 36m+1d, 25% untimed: trend oracle H | engine H; intraday oracle L peak 0.111111 | engine L peak 0.111111
   4 23m30d, Mon all untimed: trend oracle L | engine L; intraday oracle H peak 0.111111 | engine H p …[clipped]
   ```
5. **On edge inputs the oracle and the engine also agree on period_end, the dead-stock count and avg_units.** The cases: a return dated after the last shipment, duplicate rows in the last snapshot, a cancelled-only line and inventory-only orphans (round 1).
   Command: `uv run python $SP/audit_G1c/edge_r2.py`
   ```
   E1 return after last ship | oracle ('2025-03-31', 0, 5797.0) | engine ('2025-03-31', 0, 5797.0)
   E2 duplicate rows in last snapshot | oracle ('2025-03-31', 1, 5809.0) | engine ('2025-03-31', 1, 5809.0)
   E4 cancelled line only | oracle ('2025-03-31', 1, 5802.0) | engine ('2025-03-31', 1, 5802.0)
   E5 inventory-only orphans | oracle ('2025-03-31', 1, 3348.5) | engine ('2025-03-31', 1, 3348.5)
   ```
6. **The F7 capex rows for S2 recompute by hand from the golden values and the catalog typ values (I30, I31, I46)** (rounds 0 and 1).
   Command: `uv run python -c '... g[S2.storage.cube_bin.positions]*per_bin_eur + grid_area*grid_structure_per_m2_eur ...'` (round 1) and `uv run python -I -c '<S2.area.total*60 + grid_area*20; 0.1*Σ items; robots/grid_area>'` (round 0)
   ```
   252.78750000000002 12850.03125 12850.03125
   equip hand 130000.0 golden 130000.0
   works hand 25335.510201504792 golden 25335.510201504792
   integ hand 19500.000000000004 19500.000000000004
   S2 contingency hand 37963.98943926812 golden 37963.98943926812 total hand 417603.8838319494 golden 417603.8838319494
   robots/A_grid hand 0.47470701676309146 > 0.05 -> True
   ```
7. **The catalog holds 72 Param blocks with the stated per-file split, and S0 reads 30 low-confidence Params while S2 reads 50** (round 0).
   Command: `uv run python $SP/audit_G1c/catalog_sync.py`
   ```
   {'engine_defaults.yaml': 1, 'amr_gtp.yaml': 20, 'cube_asrs.yaml': 21, 'manual_p2p.yaml': 19, 'finance_defaults.yaml': 2, 'labor_standards.yaml': 9} total 72
   ... DIFF manual_p2p.pallet_rack_positions_per_m2_per_level catalog typ 0.38 oracle None (+3 similar) ... S0 30 S2 50
   ```
   The 4 manual name differences were fixed in round 1 (the oracle now uses the catalog ids). Since that rename, this scratch script raises KeyError, and `test_T1_5_oracle_param_ids_and_values_match_the_catalog` replaces it.
8. **The committed golden files are current: an independent rebuild was byte-identical to both committed files** (round 0).
   Command: `uv run python -c "from tests.golden import build_golden; build_golden.build(Path('$SP/audit_G1c/rebuild'))"; shasum $SP/audit_G1c/rebuild/golden_* tests/golden/golden_*`
   ```
   910ec3ca95e6...  rebuild/golden_values.json == tests/golden/golden_values.json
   3acd79ce3ad4...  rebuild/golden_case.xlsx == tests/golden/golden_case.xlsx
   ```
   These hashes date from round 0. Round 1 changed the oracle again (new `last_stock` column, key renames). Currency after round 1 rests on `test_T1_5_build_is_deterministic_and_committed_files_are_current`, which passes in the fresh run below.
9. **The G1c files pass lint, format and type checks, and the whole suite has no failures** (round 1).
   Command: `uv run ruff check tests/golden/{oracle,demand,build_golden,workbook}.py tests/golden/test_g1_*.py; uv run ruff format --check ...; uv run pyright ...; uv run pytest -q -m 'not bench and not slow'`
   ```
   All checks passed!
   8 files already formatted
   0 errors, 0 warnings, 0 informations
   427 passed, 6 skipped, 7 deselected in 14.56s
   ```

## Audit rounds

Each round had two audits, spec and proof. The proof auditor returned only a verdict and test counts in both rounds (`pass_with_issues` with 32 passed in round 0, `pass` with 35 passed in round 1). Its `t_ids`, `findings` and `proofs` lists were empty. Every finding below comes from the spec auditor.

### Build (before round 0)

The builder changed the golden behaviour in four places:

- The oracle was synced with catalog 0.2.0. Floor prep adds 20 × A_grid to S2 building works (I30). `F_ROBOT_DENSITY` is evaluated over A_grid against 0.05 (I46). Robot parking now reads `cube_asrs.m2_per_robot_parking`, with the same 2.0 value (I26).
- I47 was redefined as "catalog Param blocks the scenario reads". There are 72 in all, which gives S0 = 30 and S2 = 50.
- The F3 decisions I49-I54 were registered and implemented in the oracle.
- The G1b ZeroDivisionError on a zero stock cube was guarded.

The golden was rebuilt with 737 keys: 0 added, 0 removed and 11 changed. The changed keys are S0/S2 flags and low_confidence_params, and the S2 capex, finance and TCO values. No key in the F3 namespaces, design_day, eligibility, storage, labor or area changed. The builder ran 6 mutants on the new rules, and all 6 were killed.

### Round 0: tests 32 passed, 0 failed, 6 skipped

Spec audit: **pass_with_issues**. Proof audit: **pass_with_issues** (no findings listed).

| Severity | Finding | Resolution (round 1) |
|---|---|---|
| medium | `demand.py:305`: the I50 dead-stock basis used `avg_stock > 0`, while the F3 engine (`src/whsizing/profile/stock.py:57`) uses last-snapshot stock > 0. The register says each rule is "the one the engine follows". | **Fixed.** The oracle now follows the engine, which is unchanged. `sku_table` computes `last_stock`, and dead_stock = last_stock > 0 and lines_window == 0. The SKUs sheet gets a `last_stock` column, and I50 was rewritten. New test `test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window`. The mutant `dead_avg` is killed, and parity case A now agrees. |
| medium | `demand.py:525`: I51 read the no-time threshold inclusively (>= 20 %), while the spec says "more than 20 %" and the engine uses a strict `>`. At exactly 20 % the two disagreed (L/0.111 against H/0.5), and no test pinned the reading. | **Fixed.** The oracle now uses `no_time > NO_TIME_SHARE_MAX`, and I51 and the comments were updated. New test `test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile`, and the above-20 % guard was tightened. The mutant `strict_threshold` (>=) is killed, and parity case B now agrees. |
| medium | `oracle.py:429`: I52 trend confidence used days/30.4375 with a 23.9 → 24 fudge, while the engine counts calendar months. The two disagreed at 1096 days (oracle H, engine M) and at 728 days (oracle M, engine L). The test pinned the oracle rule. | **Fixed.** The oracle now follows the engine. The new `oracle.calendar_months` uses relativedelta(end + 1 day, start), and confidence is L below 24, M from 24 to 36 and H above 36. The fudge is gone, and I52 was rewritten. The test now pins date spans and runs `demand.trend` on a 1096-day calendar. The mutants `months_fudge` and `conf_days` are killed. |
| medium | `demand.py:531`: the oracle intraday stage raised a bare ZeroDivisionError when the design weekday had no timed line and the untimed share was under 20 %. The engine falls back to the default profile. | **Fixed.** When the total is 0, the oracle now returns the default profile with confidence H, matching the engine, and I51 got one sentence. New test `test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile`. The mutant `zero_total` is killed. |
| low | `test_g1_sync.py:207`: the I47 drift guard checked only the count for manual_p2p. 4 oracle manual names were not catalog ids, and the labor, finance and engine typ values were unchecked. | **Fixed.** The oracle names are now the catalog ids, and the labor., finance. and engine. prefixes are aligned, including the string in `test_g1_remediation.py`. The test was renamed `test_T1_5_oracle_param_ids_and_values_match_the_catalog` and now checks all 52 non-amr_gtp ids and their typ values. The mutant `lowconf_name` is killed, and the counts are unchanged (30 and 50). |
| low | `test_g1_sync.py:77`: the 180-day dead-stock window boundary was not pinned, so the `date >= since` mutant survived. | **Fixed.** The new dead-stock test puts single lines on period_end − 180 and on period_end − 179. `dead_window_ge` now gives 1 failed, 34 passed. |
| low | `test_g1_engine_parity.py:15`: the T3.1 placeholder still said "engine stage not built yet", though F3 is built and `test_f3_golden.py` passes. | **Fixed.** The T3.1 placeholder was deleted, and the docstring and the INTERPRETATIONS golden notes point to `test_f3_golden.py`. The skips went from 6 to 5. |

All 7 findings were fixed, and none was rejected or deferred. The fix step listed two blockers: the F3-owned golden-key gap, and the engine stages for T4.1, T6.x and T7.1, which are still stubs.

### Round 1: tests 35 passed, 0 failed, 5 skipped

Spec audit: **pass**. Proof audit: **pass** (no findings listed). The spec auditor confirmed every round-0 fix with 14 named mutants (the audit record's claim says 15) and with oracle-vs-engine runs on multi-year and edge-case data (proofs 1, 2, 4 and 5).

| Severity | Finding | Resolution |
|---|---|---|
| low | `docs/INTERPRETATIONS.md:432`: no committed test checks oracle-engine parity for the F3 decisions I49-I52 (dead stock, the no-time threshold, trend confidence). They agree today on the auditor's scratch runs, but a later engine change could drift with no failing test. The auditor judged this outside G1c's scope. | **Open.** There was no round 2. Closing it needs F3 to compare `stock.dead_stock_*` and `seasonality.trend_*` in `tests/golden/test_f3_golden.py::engine_values`. G1 can then emit those keys without breaking the T3.1 coverage check. The INTERPRETATIONS.md golden case notes record this. |

## Open issues

- **Round-1 low, unfixed:** oracle-engine parity on I49-I52 rests only on each side's own tests and on the auditors' scratch scripts. G1 cannot emit `stock.dead_stock_skus`, `stock.dead_stock_cube_m3`, `seasonality.trend_cagr` or `seasonality.trend_confidence` until F3 extends `engine_values` in `tests/golden/test_f3_golden.py`. That file is owned by F3.
- **[EXPERT] rulings needed:**
  - I46: the 0.05 robots per m² cap on the cube grid.
  - I48: the degenerate costing, that is, whether the manual WMS adaptation and software belong.
  - I53: the MAD floor of 1 unit in the R13 outlier threshold.
- **Cross-feature contract changes that F6 and F7 (engine) must adopt or contest:**
  - `F_ROBOT_DENSITY` on cube_asrs = robots / A_grid > `cube_asrs.max_robots_per_m2` (0.05), placed after `F_SCALE_LOW` (I46).
  - I47 now counts the catalog Param blocks a scenario reads, which gives S0 `F_LOW_CONFIDENCE:30` and S2 `:50`. The count includes `engine.pack_station_oee` for both scenarios and `finance.kwh_per_station_year` for S2 only.
  - S2 building works add floor_prep 20 × A_grid (I30).
- **F3 to confirm:** that its engine applies the I51 "no time component" test to the order's first local timestamp (I1), not to the line's own timestamp, and that it uses I49-I52 as registered. The auditors' runs show agreement, but F3 has not confirmed this itself.
- **Deliberate drift guard:** `test_T1_5_oracle_param_ids_and_values_match_the_catalog` will fail on any later `catalog/*.yaml` edit that adds or removes a Param block or changes a typ the oracle reads, until I47 and the oracle are re-synced. That is a G1 change, not a catalog bug.
- **Stale records (not G1c paths, not edited):**
  - `docs/audit/G1b.md` still gives `F_LOW_CONFIDENCE:29` / `:45` (lines 28, 122 and 176) and describes I47 and I30 as drifted (line 181: 68 TODOs, floor prep = 0).
  - `docs/audit/F5b.md` describes the same drift.
- **Oracle scope limits, carried over:**
  - With 3 or more inventory snapshots the oracle raises `NotImplementedError` (I12, OLS Δstock). The I49 average itself works with any number of snapshots.
  - The monthly index (F3 step 6) is not in the oracle. It was not asked for.
  - The new F3 quantities (dead stock, trend, intraday_confidence) are computed by the oracle but emit no golden key (see the first item).
- **Size:** `build_golden.py` has 780 lines and `demand.py` 690 (fresh `wc -l`). Both are under the 800 cap but close to it. The functions over 50 lines that the G1b audit listed are unchanged.

## Not applicable here and why

- **Engine parity (5 skips):** `src/whsizing/{design,engine,finance}/__init__.py` are 0 bytes (`wc -c` gives 0 for all three), so the engine side of T1.5 for T4.1, T6.1, T6.2, T6.3 and T7.1 cannot run. Each comparison belongs to the owning feature's golden test. T3.1 is no longer here, because it runs in `tests/golden/test_f3_golden.py`.
- **[EXPERT] review:** I46, I48 and I53 need a warehouse-automation domain expert.
- **Real client data:** none is available. The rules were exercised on tiny_golden, on modified copies of it, and on the auditors' synthetic multi-year and edge-case datasets.
- **Docker and GitHub CI:** the G1 golden tests depend on neither.
- **`whsizing.errors` classes:** the oracle must not import `whsizing`, so it raises `ValueError` and `NotImplementedError` instead. This is by design.

## Fresh test output (run while writing this record, 2026-11-08)

Command: `uv run pytest tests/golden/test_g1_*.py -q -rA`

```
sssss...................................                                 [100%]
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_spreadsheet_equals_golden_json
PASSED tests/golden/test_g1_oracle.py::test_T1_5_build_is_deterministic_and_committed_files_are_current
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_anchors_match_tiny_golden_readme
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_values_respect_spec_invariants
PASSED tests/golden/test_g1_oracle.py::test_erlang_c_values
PASSED tests/golden/test_g1_oracle.py::test_erlang_wq_matches_mm1_closed_form
PASSED tests/golden/test_g1_oracle.py::test_payback_interpolation_and_edge_cases
PASSED tests/golden/test_g1_oracle.py::test_npv_irr_against_numpy_financial
PASSED tests/golden/test_g1_oracle.py::test_levels_and_area_formulas
PASSED tests/golden/test_g1_oracle.py::test_positions_formulas
PASSED tests/golden/test_g1_oracle.py::test_classification_formulas
PASSED tests/golden/test_g1_oracle.py::test_calendar_and_misc_formulas
PASSED tests/golden/test_g1_remediation.py::test_T1_5_missing_dims_hazmat_temperature_are_ineligible_and_case_fallbacks_hold
PASSED tests/golden/test_g1_remediation.py::test_T1_5_assume_eligible_if_missing_dims_raises_F_ELIG_ASSUMED
PASSED tests/golden/test_g1_remediation.py::test_T1_5_orphan_skus_are_kept_never_eligible_and_counted_in_every_share
PASSED tests/golden/test_g1_remediation.py::test_T1_5_sla_window_explicit_derived_midnight_and_equal_times
PASSED tests/golden/test_g1_remediation.py::test_T1_5_explicit_sla_window_drives_lambda_and_dock_shortfall_flag
PASSED tests/golden/test_g1_remediation.py::test_T1_5_decant_station_hours_add_to_the_ports
PASSED tests/golden/test_g1_remediation.py::test_T1_5_zero_eligible_lines_degenerate_to_manual
PASSED tests/golden/test_g1_remediation.py::test_T1_5_three_inventory_snapshots_are_not_silently_flat
PASSED tests/golden/test_g1_remediation.py::test_T1_5_flag_table_and_low_confidence_count
PASSED tests/golden/test_g1_remediation.py::test_T1_5_erlang_queue_and_sla_flags
PASSED tests/golden/test_g1_remediation.py::test_T1_5_golden_basis_exercises_pallet_parcel_and_overflow_branches
PASSED tests/golden/test_g1_remediation.py::test_T1_5_workbook_headers_and_stage_cells_name_their_formula
PASSED tests/golden/test_g1_sync.py::test_T1_5_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero
PASSED tests/golden/test_g1_sync.py::test_T1_5_inventory_only_skus_are_orphans_in_stock_and_dead_stock
PASSED tests/golden/test_g1_sync.py::test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window
PASSED tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_are_left_out_of_intraday_shares
PASSED tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_above_20_percent_use_the_default_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_trend_cagr_from_monthly_mean_daily_lines
PASSED tests/golden/test_g1_sync.py::test_T1_5_cube_building_works_add_floor_prep_on_the_grid
PASSED tests/golden/test_g1_sync.py::test_T1_5_oracle_param_ids_and_values_match_the_catalog
PASSED tests/golden/test_g1_sync.py::test_T1_5_share_stock_cube_is_zero_without_stock
SKIPPED [1] tests/golden/test_g1_engine_parity.py:16: engine stage not built yet; implemented in the feature's own golden test (T4.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:22: engine stage not built yet; implemented in the feature's own golden test (T6.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:28: engine stage not built yet; implemented in the feature's own golden test (T6.2)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:34: engine stage not built yet; implemented in the feature's own golden test (T6.3)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:40: engine stage not built yet; implemented in the feature's own golden test (T7.1)
35 passed, 5 skipped in 1.00s
```

The whole golden folder, F3's `test_f3_golden.py` included, was also re-run: `uv run pytest tests/golden -q` gives `36 passed, 5 skipped in 1.38s`.
