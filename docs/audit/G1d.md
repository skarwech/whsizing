# G1d audit: Golden keys for F3 dead stock and trend, plus the register consistency check

## Verdict: pass_with_issues

In the final round (round 1), both auditors returned `pass_with_issues`. Both medium findings from round 0 (the oracle ignored I57 and I59) were fixed and re-checked. The fresh run gives 41 passed, 0 failed and 4 skipped, and the 4 skips are engine-parity placeholders.
Two low findings are still open: the I50/I52 register text is stale (deferred to the lead) and the engine-parity placeholder list is stale. Two register questions are also left for the lead: I56 against the spec, and the I59 wording.

Schema changes: none (`schema_changes: []`). The oracle still does not import `whsizing`.

Files touched by the build: `tests/golden/demand.py`, `tests/golden/workbook.py`, `tests/golden/golden_values.json`, `tests/golden/golden_case.xlsx`, `tests/golden/test_f3_golden.py`, `tests/golden/test_g1_sync.py`, `docs/INTERPRETATIONS.md` (golden case notes only), and a dated superseded note on line 1 of `docs/audit/G1b.md` and `docs/audit/F5b.md`. Round 1 also edited `tests/golden/demand.py` again (I57 and I59; the `design_day.flags` row is now written after the inbound rows), rebuilt `golden_values.json` and `golden_case.xlsx` (all 741 values identical; only the `design_day.flags` row moved), added `tests/golden/test_g1_register.py`, and removed the stale T4.1 placeholder from `tests/golden/test_g1_engine_parity.py`.

Golden keys added. The rebuild changed no existing value: 737 keys were identical and 4 were added, for 741 in total.

| Key | Golden value | Rule |
|---|---|---|
| `stock.dead_stock_skus` | `0` | SKUs with `last_stock > 0` and no shipped line after `period_end − 180 d` (I50) |
| `stock.dead_stock_cube_m3` | `0.0` | Sum over the dead SKUs of `last_stock × unit_cube_m3`. Neither the spec nor I50 says which stock quantity to use. The engineer chose `last_stock` and documented it in the golden case notes. |
| `seasonality.trend_cagr` | `null` | Only one calendar month of history (I52) |
| `seasonality.trend_confidence` | `"L"` | Less than 24 calendar months (I52) |

All four golden values are degenerate on tiny_golden (31 days, no dead stock). Parity between the engine and the oracle on non-degenerate values is therefore proven on modified copies of the data (see the T3.1 rows and the proofs).

## Acceptance tests

Statuses come from the fresh run below and the round-1 audit.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet` | pass | All 152 F3 engine keys equal `golden_values.json`, including the 4 new keys. A coverage guard fails if any golden key in `profile.`, `daily.`, `eiq.`, `abc.`, `stock.`, `shipment.` or `seasonality.` is left uncompared. `same()` handles a `None` golden value as an exact match. Because the new values are degenerate, this test alone cannot catch an engine that returns constants. |
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock` | pass | The copy has a SKU last shipped exactly 180 d before the end (dead), a SKU last shipped 179 d before (not dead) and an inventory-only orphan. Engine and oracle both give `dead_stock_skus == 2` with dead cube > 0, and all 152 keys match. A count of 2 rejects an off-by-one in either direction (1 or 3). |
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_trend_equals_the_oracle_on_a_two_month_copy` | pass | Added in round 1. Orders dated on or before 2025-03-15 are moved back 28 days, which gives two months. The oracle's `trend_cagr` is a float, confidence is L, and every F3 engine key equals the oracle. |
| T1.5 | `tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out0-True]` | pass | Added in round 1 (I57). With P95 `pallets_out` = 0 and a reference day of 1, the oracle raises `F_RATIO_DRIFT:pallets_out`. Its flag list equals the codes from the engine's `_flags`. Restoring the old condition makes the test fail. |
| T1.5 | `tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out1-False]` | pass | Added in round 1 (I57). With every value at 0, no drift flag is raised, and the oracle equals the engine. |
| T1.5 | `tests/golden/test_g1_register.py::test_T1_5_default_units_per_pallet_flag_matches_the_engine` | pass | Added in round 1 (I59). The committed golden case has no `F_DEFAULT_UPP`. On a copy where the most-shipped SKU has no units_per_case and no cases_per_pallet, the oracle's `design_day.flags` gains `,F_DEFAULT_UPP`, and S0.flags ends with `F_DEFAULT_UPP` then `F_LOW_CONFIDENCE:30`. The share equals that SKU's units over total units. All F4 engine keys equal the oracle, and the engine Flag has severity `info`. Removing the append makes the test fail. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window` | pass | Extended. A SKU stocked only in the older snapshot is not dead. A line at −180 d is outside the window and a line at −179 d is inside it. The dead SKU list is exactly `[edge]`, `dead_stock_skus == 1`, and the dead cube is `300 × unit_cube`, which uses `last_stock`, not `avg_stock`. |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_inventory_only_skus_are_orphans_in_stock_and_dead_stock` | pass | Extended. `dead_stock_skus == 2`, the orphan's `unit_cube_m3` is 0, and the dead cube is `300 ×` the idle SKU's unit cube (I50). |
| T1.5 | `tests/golden/test_g1_sync.py::test_T1_5_trend_cagr_from_monthly_mean_daily_lines` | pass | Extended. A synthetic 24-month series growing 1 %/month gives `trend_cagr == 1.01^12 − 1` (rel 1e-9). The L/M/H boundary table covers leap years. The committed golden values are `(None, "L")`. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_build_is_deterministic_and_committed_files_are_current` | pass | A fresh build equals the committed `golden_values.json` (741 keys) and `golden_case.xlsx`. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_spreadsheet_equals_golden_json` | pass | The 4 new keys sit on Profile rows A124-A127. Each value cell carries its formula comment, and B126 (`trend_cagr`) is empty, which means `None`. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_anchors_match_tiny_golden_readme`, `::test_T1_5_golden_values_respect_spec_invariants` | pass | Unchanged by G1d. |
| T1.5 | `tests/golden/test_g1_sync.py`, 8 other `test_T1_5_*` tests (avg_stock, lines without time ×4, cube floor prep, catalog param ids, share_stock_cube) | pass | Unchanged by G1d. They still pass after the rebuild. |
| T1.5 | `tests/golden/test_g1_remediation.py`, 12 `test_T1_5_*` tests | pass | Unchanged by G1d. They still pass after the rebuild. |
| T1.5 (engine parity T6.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_1_storage` | not_applicable (skip) | The placeholder is stale: `tests/golden/test_f6_storage_golden.py` exists and passes (see Open issues). |
| T1.5 (engine parity T6.2) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_2_labor` | not_applicable (skip) | Placeholder until the F6 labor golden test exists. |
| T1.5 (engine parity T6.3) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_3_area_and_docks` | not_applicable (skip) | Placeholder until the F6 area and docks golden test exists. |
| T1.5 (engine parity T7.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T7_1_finance` | not_applicable (skip) | Placeholder until the F7 golden test exists. |

`test_g1_oracle.py` also has 8 helper tests with no T-id (Erlang C, M/M/1, payback, NPV/IRR, levels, positions, classification, calendar). All 8 pass.

## Proofs (captured by the auditors during the audit)

The spec auditor captured all of these proofs. In both rounds the proof auditor's record holds only a verdict and test counts, with no proofs. `$SP` stands for `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad`. Text marked `…[clipped]` was already cut off in the audit history and is reproduced as given.

1. **An independent hand computation reproduces the 4 golden values** (round 0). It works from the raw tiny_golden parquet and uses neither the oracle nor the engine.
   Command: `uv run python $SP/audit_G1d/hand.py`
   ```
   period 2025-03-01 2025-03-31 cutoff 2024-10-02 last_snapshot 2025-03-31
   in stock (last): 90 never shipped in stock: 0
   dead_stock_skus 0
   dead_stock_cube_m3 0
   months_with_op 1 trend_cagr None calendar_months 1.0 conf L
   ```
2. **The rebuild only added keys** (round 0). It was diffed against the engineer's backup of the previous `golden_values.json`.
   Command: `uv run python -c "import json; old=json.load(open('<scratchpad>/G1d/golden_values.json')); new=json.load(open('tests/golden/golden_values.json')); ..."`
   ```
   737 741 changed: [] added: ['seasonality.trend_cagr', 'seasonality.trend_confidence', 'stock.dead_stock_cube_m3', 'stock.dead_stock_skus'] removed: []
   ```
3. **Non-degenerate dead stock: oracle = engine = hand** (rounds 0 and 1). The copy has 2 snapshots, duplicate rows of one SKU in the last snapshot, a dead SKU with a missing dimension, a SKU stocked only in the old snapshot, and a zero-stock SKU.
   Command: `uv run python $SP/audit_G1d/parity.py dead_multi`
   ```
   dead_multi | oracle: {'stock.dead_stock_skus': 2, 'stock.dead_stock_cube_m3': 0.63768188352, ...}
   dead_multi | engine: {'stock.dead_stock_skus': 2, 'stock.dead_stock_cube_m3': 0.63768188352, ...}
   dead_multi | mismatches: 0 of 152
   dead_stock_skus 2
   dead_stock_cube_m3 0.63768188352
   ```
4. **Non-degenerate trend: oracle = engine = hand on two copies** (round 1, re-run of the round-0 scripts).
   Command: `for c in two_months two_years dead_multi; do uv run python $SP/audit_G1d/parity.py $c; done`
   ```
   two_months | oracle/engine trend_cagr -0.13094813952246143 L | mismatches: 0 of 152 | hand trend_cagr -0.1309481395232981 conf L
   two_years | oracle/engine trend_cagr 0.26531250565145204 M | mismatches: 0 of 152 | hand 0.2653125056513801 calendar_months 24.92 conf M
   dead_multi | oracle/engine dead_stock_skus 2, dead_stock_cube_m3 0.63768188352 | mismatches: 0 of 152 | hand dead_stock_skus 2 dead_stock_cube_m3 0.63768188352
   ```
5. **I57, before and after the fix** (round 0, then round 1).
   Command: `uv run python $SP/audit_G1d/i57.py` (round 0), then `$SP/audit_G1d/i57b.py` (round 1)
   ```
   # round 0
   P_pallets_out = 0.0 base = 1.0
   oracle design_day.flags = 'F_SHORT_HISTORY'
   I57 expects F_RATIO_DRIFT:pallets_out in flags: False
   # round 1
   P_pallets_out = 0.0 base = 1.0
   oracle design_day.flags = ['F_SHORT_HISTORY', 'F_RATIO_DRIFT:pallets_out']
   I57 expects F_RATIO_DRIFT:pallets_out in flags: True
   engine flags = [('F_SHORT_HISTORY', 30.0), ('F_RATIO_DRIFT:pallets_out', None)]
   ```
6. **I59 holds on edge cases the committed test does not cover** (round 1). A shipped orphan and a SKU with null cases_per_pallet each raise `F_DEFAULT_UPP` in both the oracle and the engine, with severity `info`. The F4 keys show 0 mismatches. For a never-shipped SKU on the default, the oracle raises no flag (share 0.0). The engine line for that case was clipped in the audit history, so this record cannot confirm it.
   Command: `uv run python $SP/audit_G1d/upp.py $SP/audit_G1d/upp`
   ```
   orphan: oracle dd.flags='F_SHORT_HISTORY,F_RATIO_DRIFT:weight_kg,F_RATIO_DRIFT:pallets_out,F_DEFAULT_UPP' share=0.21812080536912754
   orphan: engine F_DEFAULT_UPP=[('F_DEFAULT_UPP', 'info', 0.21812080536912742)] | F4 mismatches 0/99
   orphan: S0.flags tail=['F_RATIO_DRIFT:pallets_out', 'F_DEFAULT_UPP', 'F_LOW_CONFIDENCE:30']
   cpp_null: ... F4 mismatches 0/99
   never_shipped: oracle dd.flags='F_SHORT_HISTORY,F_RATIO_DRIFT:weight_kg,F_RATIO_DRIFT:pallets_out' share=0.0
   never_shipped: engine F_DEFAULT_UPP …[clipped]
   ```
7. **The I59 share, computed by hand from the raw order lines, equals the oracle and engine values** (round 1).
   Command: `uv run python -c "import polars as pl; l=pl.read_parquet('tests/golden/tiny_golden/order_lines.parquet'); ..."`
   ```
   top c30f71d0561a5cb3 share by hand = 0.2181208053691275 585 2682
   ```
8. **The full fast suite is green** (round 0, then round 1). This includes T4.1, which the engineer had reported as failing.
   Command: `uv run pytest -q -m 'not bench and not slow'`
   ```
   # round 0
   545 passed, 6 skipped, 9 deselected in 13.89s
   # round 1
   593 passed, 5 skipped, 9 deselected in 15.86s
   ```

## Audit rounds

### Round 0

Spec auditor: `pass_with_issues`, 37 passed, 0 failed, with 2 medium and 3 low findings. Proof auditor: `pass_with_issues`, 37 passed, 0 failed, with no findings or proofs recorded.

| # | Severity | Finding | Resolution (round 1) |
|---|---|---|---|
| 1 | medium | `tests/golden/demand.py:488`: the oracle never raises `F_RATIO_DRIFT:<m>` when P_m = 0 and m* > 0, which contradicts I57. The engine raises it. The engineer had deferred this to the lead. | **Fixed.** `demand.design_day` now uses the engine's rule: `drift = \|base − P_m\| / P_m` if P_m > 0, else None, and the flag is raised when (drift is None and base > 0) or drift > 0.15. A new parametrized test in `test_g1_register.py` covers it, and restoring the old condition makes it fail. All 741 golden values are unchanged. |
| 2 | medium | `tests/golden/demand.py:77`: the oracle never emits `F_DEFAULT_UPP` (I59). `prepare_sku` silently coalesces to 400. | **Fixed.** `prepare_sku` adds `default_upp = (units_per_case × cases_per_pallet).is_null()`. `inbound()` appends `F_DEFAULT_UPP` when a SKU with inbound units is on the default, and the `design_day.flags` row is now written after inbound, so the flag reaches S*.flags just before `F_LOW_CONFIDENCE`. The share is kept in `c['inb']['default_upp_share']` and is not a golden key, because a new `inbound.*` key would trip T4.1's uncovered-key check. All 741 values are unchanged; only the position of the `design_day.flags` row moved. A new test in `test_g1_register.py` covers it, and removing the append makes it fail. |
| 3 | low | `tests/golden/test_f3_golden.py:109`: no committed parity test between the engine and the oracle where `trend_cagr` is defined. The auditor found no defect in scratch runs. | **Fixed.** Added `test_T3_1_trend_equals_the_oracle_on_a_two_month_copy`. The golden case notes name it. |
| 4 | low | `docs/INTERPRETATIONS.md:384`: the I50 and I52 body text still says "No golden key". | **Deferred to the lead.** The I-entry bodies are outside G1d's editable scope. The exact replacement wording was supplied (see Open issues). |
| 5 | low | Parts of the engineer's round-0 report were wrong or stale: (1) T4.1 "NOW FAILS" (it passes; the F4 owner had already added both dead-stock keys to `STOCK`), (2) the `test_f4_register.py` ImportError does not reproduce, and (3) the claim that the engine uses severity `warning` for `F_DEFAULT_UPP` (it uses `info`). | **Fixed (report corrected, no code change).** T4.1 passes, `test_f4_register.py` imports and runs, and the new I59 test asserts severity `info`. As a related clean-up, the stale T4.1 placeholder was removed from `test_g1_engine_parity.py`. |

### Round 1

Spec auditor: `pass_with_issues`, 41 passed, 0 failed, with 0 medium and 2 low findings. It re-verified findings 1-3 with scratch scripts (proofs 4-7). Proof auditor: `pass_with_issues`, 41 passed, 0 failed, with no findings or proofs recorded.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | low | `docs/INTERPRETATIONS.md:526`: the golden case notes still say the engine-parity placeholders are "T4.1, T6.1, T6.2, T6.3, T7.1", but T4.1 was removed and runs in `test_f4_golden.py`. The T6.1 placeholder is still skipped with "engine stage not built yet", although `tests/golden/test_f6_storage_golden.py::test_T6_1_storage_throughput_equipment_equal_golden` exists and passes. | **Open.** There was no round 2. Both files are in G1d's owned paths. |
| 2 | low | `docs/INTERPRETATIONS.md:384`: round-0 finding 4 is still unresolved. | **Open, deferred to the lead** (outside G1d's scope). |

## Open issues

1. **[low, deferred to the lead] The I50 and I52 body text is stale.** `docs/INTERPRETATIONS.md:384-385` (I50) still says "No golden key (golden case notes)." and `:408-409` (I52) still says "No golden key (see the golden case notes)." I confirmed both are still present at the time of writing. The engineer supplied this wording:
   - I50: replace with "Golden keys `stock.dead_stock_skus`, `stock.dead_stock_cube_m3` (T3.1, golden case notes)."
   - I52: replace with "Golden keys `seasonality.trend_cagr`, `seasonality.trend_confidence` (T3.1, golden case notes)."
2. **[low, G1d's own paths] The engine-parity placeholder list is stale.** `docs/INTERPRETATIONS.md:526-528` still lists T4.1 as a skipped placeholder. `tests/golden/test_g1_engine_parity.py:16` still skips T6.1 with "engine stage not built yet", but `tests/golden/test_f6_storage_golden.py` exists and passed in a fresh check at the time of writing. The fresh G1 run therefore reports 4 skips where 3 would be accurate.
3. **[register, lead to decide] I56 conflicts with the spec.** `description.md` l.252 sets the default on the field itself, whatever the inbound mode: `inbound_peak_factor: float | None = None  # None → outbound peak-to-average`. I56 says the default in receipts mode is 1.0, which matches the reading of l.766. The spec contradicts itself, and I56 picks one side. The golden case uses `inbound_mode: derived`, so no golden value is affected.
4. **[register, lead to decide] The I59 condition is ambiguous.** The phrase "has neither `units_per_case × cases_per_pallet`" says nothing about `units_per_pallet`. It also does not say whether shipped orphans count (I50 gives them `upp` 400). The round-1 oracle and the engine both apply the rule "`units_per_case × cases_per_pallet` is null", which counts shipped orphans. The auditor confirmed they agree (proof 6), but the register wording still needs the lead's confirmation. The engineer's other I59 point, severity `warning` against `info`, was wrong: the engine uses `info`.
5. **[outside G1d, not reproduced] The T3.7 property failure.** In round 1 the engineer reported that `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` failed on hypothesis seed 531 with a last-digit difference in `eiq.cube_per_order_m3.p50`. The suggested cause was an engine sum that depends on row order. The round-1 auditor's full fast suite showed no failure (593 passed). A fresh run of that file at the time of writing gives `1 passed`. The F3 owner may still want to check whether the engine's order-cube sum depends on row order.

Engineer choices left as is (not findings): `dead_stock_cube_m3` uses `last_stock`, because the spec and I50 do not say which stock quantity to use. The I59 share is not a golden key, because adding one would trip T4.1's coverage check.

## Not applicable here and why

- **Engine-parity placeholders T6.2, T6.3 and T7.1** (`tests/golden/test_g1_engine_parity.py`) stay skipped until the F6 labor, F6 area/docks and F7 finance golden tests exist. The T6.1 placeholder is stale (open issue 2).
- **Real client data:** the golden case is the synthetic tiny_golden dataset (31 days, no dead stock). Its dead-stock and trend values are degenerate by construction. Non-degenerate behaviour is proven on modified copies, not on client history.
- **Expert review:** the `[P]` value `dead_stock_days = 180` and the register rulings on I56 and I59 need the lead's or a domain expert's sign-off. No test can provide that.
- **Docker / GitHub CI:** G1d has no tests that need them.

## Fresh test output

Run at the time of writing this record (2026-11-08):

```
$ uv run pytest tests/golden/test_g1_*.py tests/golden/test_f3_golden.py -q -rA
ssss.........................................                            [100%]
...
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
PASSED tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out0-True]
PASSED tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out1-False]
PASSED tests/golden/test_g1_register.py::test_T1_5_default_units_per_pallet_flag_matches_the_engine
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
PASSED tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet
PASSED tests/golden/test_f3_golden.py::test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock
PASSED tests/golden/test_f3_golden.py::test_T3_1_trend_equals_the_oracle_on_a_two_month_copy
SKIPPED [1] tests/golden/test_g1_engine_parity.py:16: engine stage not built yet; implemented in the feature's own golden test (T6.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:22: engine stage not built yet; implemented in the feature's own golden test (T6.2)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:28: engine stage not built yet; implemented in the feature's own golden test (T6.3)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:34: engine stage not built yet; implemented in the feature's own golden test (T7.1)
41 passed, 4 skipped in 1.51s
```

Other checks run at the time of writing: `uv run pytest tests/golden/test_f4_golden.py tests/golden/test_f6_storage_golden.py tests/property/test_f3_properties.py -q` gives `4 passed`. The committed `golden_values.json` has 741 keys, holds `stock.dead_stock_skus=0`, `stock.dead_stock_cube_m3=0.0`, `seasonality.trend_cagr=None` and `seasonality.trend_confidence='L'`, and contains no `F_DEFAULT_UPP`.
