# F3c audit: Demand profiling (re-audit after fix round 1)

## Verdict: pass_with_issues

All eight F3 acceptance tests (T3.1 to T3.8) and the regression tests for the fix round pass: 29 passed, 0 failed and 0 skipped. The engine matches the golden oracle on 148 keys, a hand recomputation on 26 metrics, and hand values on a small example. In fix round 1, five of the six round-0 findings were fixed and one was deferred.
The verdict stays below `pass` because the round-1 spec audit left 1 medium and 2 low findings open, and no fix round followed. The medium one: the profile is bit-identical across reruns and shuffled input, but not across polars thread counts. Both round-1 auditors (spec and proof) returned pass_with_issues.

Scope: F3c owns `src/whsizing/profile/**`, `tests/unit/test_f3_*.py`, `tests/property/test_f3_*.py` and `tests/golden/test_f3_*.py`. Spec: description.md l.708-741 (F3) and l.551-559 (§4.1 daily_series). The binding register is `docs/INTERPRETATIONS.md`, which G1c updated just before this audit together with the oracle and `tests/golden/golden_values.json`. Schema changes: none. ruff check, ruff format and pyright are clean on the F3 paths. This was re-run while writing this record (proof 8).

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet` | pass | Compares every engine key with `golden_values.json`: dates and counts exactly, floats at 0.5 % relative. It fails if any golden key in the `profile.`, `daily.`, `eiq.`, `abc.`, `stock.`, `shipment.` or `seasonality.` namespaces is left uncompared. It passes against the golden values that G1c updated. The auditor's own parity run on a modified tiny_golden matched the oracle on all 148 keys at rel 1e-9 (proof 2). |
| T3.2 | `tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden\|small_synth]` | pass | In all three rankings (lines, cube movement, stock cube), the SKU, line and cube shares each sum to 1 (1e-12). The class A share is ≥ 0.8 − 1e-9. The Pareto curve has 100 points, never decreases and ends at 1. |
| T3.3 | `tests/unit/test_f3_profile.py::test_T3_3_monthly_indices_average_to_one` | pass | The 12 monthly indices, weighted by operating days per month, average to 1.0 (abs 1e-12) on 2 years of data shaped like ecom_mid. December > August. |
| T3.4 | `tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[golden\|small_synth]` | pass | Each operating weekday has 24 non-negative shares that sum to 1 (1e-12). The keys are exactly the operating weekdays. `peak_hour_share` equals the max share on the design weekday. |
| T3.5 | `tests/unit/test_f3_profile.py::test_T3_5_shipment_split_400kg_order_is_pallet` | pass | A 400 kg order is a pallet order (1 pallet, 0 parcels). A 0.7 m³ order is a pallet order. A 31 kg order ships 2 parcels. The order and line shares and the mean parcels per order (I8) are checked exactly. |
| T3.6 | `tests/unit/test_f3_ecom_mid.py::test_T3_6_operating_days_exclude_sundays_in_ecom_mid` | pass | On the full ecom_mid dataset there are at least 100 Sundays and none is an operating day. More than 99 % of non-holiday Mon-Fri are operating days. The test is marked `slow`. Only `just`'s fast target (`-m "not slow and not bench"`) leaves it out. Plain `pytest`, `just test` and CI (`-m "not bench"`) run it, and it ran in the fresh run below. The round-1 auditor's note "out of the default run" is not accurate. |
| T3.7 | `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` and `tests/unit/test_f3_ecom_mid.py::test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile` | pass | The hypothesis test (8 seeds) shuffles all 4 tables of tiny_golden, multi-day orders included. Since fix round 1 it needs exact equality of the whole `model_dump`; the 1e-9 tolerance is gone. The slow ecom_mid test checks a shuffled build and a rerun bit for bit at 1 M lines. Neither test varies the polars thread count, and the result does depend on it (open issue 1, proof 6). |
| T3.8 | `tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s` | pass | `build_profile` on ecom_mid (1,030,012 order lines, 981,910 shipped) takes 0.41-0.47 s against a 60 s budget. It asserts more than 0.9 M lines and elapsed < 60 s. Measured on this machine, not on the CI runner the spec names. |

Regression tests added or extended for the round-0 findings (all pass): `test_R10_seasonality_confidence_on_calendar_months_like_F2[start0..start3]`, `test_receipts_pallets_null_when_unknown_never_an_undercount`, `test_sub_second_after_local_midnight_is_a_line_without_time` and `test_single_snapshot_has_no_growth_and_missing_inventory_is_low_confidence` (now asserts `cover_days == 0.0`). The builder reports that each one fails with the old code. The W2 fixes are covered by `test_stock_only_sku_is_an_orphan_counted_in_stock_and_dead_stock`, `test_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero`, `test_lines_without_time_below_the_switch_are_left_out_of_the_hourly_shares`, `test_two_full_calendar_years_give_trend_confidence_M_and_flat_demand_no_trend` and `test_stale_snapshot_uses_the_F2_R14_six_month_rule[*]`.

## Proofs

Proofs 1 to 8 were captured by the spec auditors during the audit (round 0 or round 1, as marked). Proofs 4 to 8 were also re-run while writing this record on 2026-11-08, with the same results. The round-0 and round-1 proof audits returned pass_with_issues with no findings and no proofs listed. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F3c/`, written `<audit>/` below. All commands were run from `/Users/skarwech/saas_v1`.

1. **An independent pure-Python recomputation matches the engine on 26 metrics** (round 0). The metrics are counts, operating days, daily stats, EIQ, ABC (I6), shipment split, stock (I49/I50) with orphan and dead stock, OLS growth, intraday peak without untimed lines, monthly indices, returns and dims coverage.
   Command: `for s in 1 2 3; do uv run python <audit>/hand_check.py $s; done`
   ```
   OK  abc_A_line_share engine=0.8132407029015121 hand=0.8132407029015121
   OK  cover_days engine=28.656303568645793 hand=28.656303568645786
   OK  growth engine=-3670.531859931125 hand=-3670.531859931125
   OK  peak_hour_share engine=0.1479028697571744 hand=0.1479028697571744
   MISMATCHES: 0   (seeds 1, 2, 3: 0 each)
   ```

2. **The engine matches the golden oracle on a harder tiny_golden** (round 0). The data adds an inventory-only SKU, a SKU stocked only in an older snapshot, lines at period_end − 180 and − 179 (the dead-stock boundary) and about 15 % midnight orders.
   Command: `uv run python <audit>/parity.py <audit>`
   ```
   compared 148 keys; mismatches: {}
   dead oracle ['103a594ee860a26a', 'INV-ONLY'] | engine dead_stock_skus 2 ['103a594ee860a26a', 'INV-ONLY']
   n_skus oracle 101 engine 101 | no-time share 0.1545 conf H
   ```

3. **End to end on ecom_mid (1.03 M rows)** (round 0). The profile builds in under a second and no Sunday is an operating day. The seasonality shape is plausible. `write_profile` writes the JSON, `daily_series.parquet` (the 15 §4.1 columns) and the 8 charts as PNG and HTML.
   Command: `uv run python <audit>/e2e.py <audit>/ecom`
   ```
   order_lines rows: 1030012
   build_profile: 0.43 s
   period 2024-01-01..2025-12-30 calendar=730 op=626 lines=981910 sundays_operating=0
   monthly_index=[0.88, 0.822, ..., 1.441, 1.632]
   weekday_index=[1.218, 1.172, 1.121, 1.067, 1.042, 0.376, 0.0]
   write_profile: 18 files ... daily_series.parquet (730, 15)
   ```

4. **The round-0 R10 finding is fixed** (round 1, re-run while writing this record). `seasonality.confidence` agrees with F2's `io.rules._shorter(start, end, 12)` on every span tested, and a non-leap calendar year gives H. In round 0 the same year gave `F3 seasonality.confidence= L | F2 R10 history<12m: False`.
   Command: `uv run python <audit>/fixes.py`
   ```
   [R10] 1955 spans, 0 disagreements; 2025-01-01..2025-12-31 -> H
   ```

5. **The three round-0 low findings on values are fixed** (round 1, re-run while writing this record). A receipt day with any null or missing pallets gives `receipts_pallets` null, and a day without receipts gives 0.0. `cover_days` is 0.0 without inventory. Times under one second after local midnight count as no_time.
   Command: `uv run python <audit>/fixes.py`
   ```
   [receipts partial null] [(2025-03-03, 2.0, None), (2025-03-04, 1.0, 2.0), (2025-03-05, 0.0, 0.0)]
   [no inventory] cover_days = 0.0 avg_units = 0.0 stock conf = L
   [receipts all null] [(2025-03-03, 2.0, None), (2025-03-04, 1.0, None), (2025-03-05, 0.0, 0.0)]
   [receipts no col] [(2025-03-03, 2.0, None), (2025-03-04, 1.0, None), (2025-03-05, 0.0, 0.0)]
   [no_time] [('x', True, 0), ('y', True, 0), ('z', True, 0), ('w', False, 0)]
   ```

6. **Reruns and shuffled input are bit-identical at 1 M lines, but a change of polars thread count is not** (round 1, re-run while writing this record). In round 0, two identical runs differed in 0 to 3 values (for example `.eiq.lines_per_order.cv: 0.7443759633579607 vs 0.7443759633579606`).
   Command: `uv run python <audit>/dump.py <audit>/ecom/base out.json` (3 runs), the same on `<audit>/ecom/shuf` (2 runs), then `POLARS_MAX_THREADS={1,2,3,4,8} uv run python <audit>/dump.py <audit>/ecom/base ...` and `uv run python <audit>/jdiff.py base1.json th1.json`
   ```
   base run1-3: 36c90d21244e394c | shuf run1-2: 36c90d21244e394c | base threads=1/2/3/4/8: 6137249b86623bf6
   1 diffs
   .eiq.weight_per_order_kg.p95: 6.281000000000001 vs 6.281 rel=1.4e-16
   ```
   Re-run on 2026-11-08: two default runs gave `36c90d21244e394c`, and `POLARS_MAX_THREADS=1/4/8` gave `6137249b86623bf6` with the same single diff.

7. **Hand values and spec edge cases** (round 1, re-run while writing this record). Steps 2, 3, 5, 6, 7, 8 and 9 equal hand-computed values on a 3-day, 6-order example: daily P95 4.8 with linear interpolation, CV with ddof=0, EIQ classes, cover 7.5 days, a 350 kg pallet order, 3 parcels for 73 kg, the weekday index, intraday shares and peak/avg. The DST hours, empty inventory and receipts, a single day (trend None, L) and the strict I51 20 % rule also behave as required. Exactly 20 % midnight lines keeps the measured shares (H). 33 % switches to the flat default (L).
   Command: `uv run python <audit>/edges.py`
   ```
   [hand] all hand values match
   [DST] [('d1', 2025-03-30, 3), ('d2', 2025-10-26, 2), ('d3', 2025-10-26, 2)]
   [empty inv+rcpt] (0, 0.0, 'L', [0.0, 0.0, 0.0])
   [single day] (1, None, 'L', 'L', 0.0)
   [20% midnight] ('H', 1.0)
   [33% midnight] ('L', 0.1111)
   ```
   The same script shows open issue 2. A missing `order_ts` column raises `polars.exceptions.ColumnNotFoundError`, string `qty_units` raises `polars.exceptions.ComputeError`, and a null sku is accepted: `[null sku] (3, ['a', 'b', 'c', None])`.

8. **The F3 code is lint-, format- and type-clean** (round 1, re-run while writing this record).
   Command: `uv run ruff check <F3 paths> && uv run ruff format --check <F3 paths> && uv run pyright <F3 paths>`
   ```
   All checks passed!
   15 files already formatted
   0 errors, 0 warnings, 0 informations
   ```

## Audit rounds

### Before this audit (W2 build and W2 fix round, as claimed in the build notes)

F3 was built in W2. The W2 round-0 audit found 1 high and 6 medium findings. The W2 fix round reported these as fixed:

- The per-SKU average stock is taken over all snapshots, and a missing SKU counts as 0.
- Inventory-only (orphan) SKUs are counted in the stock stats and in dead stock.
- Lines without a time (< 20 %) are left out of the intraday shares instead of landing in hour 0.
- `trend_confidence` is correct for exactly 24 months.
- `receipts_pallets` is null when there is no pallets column.
- The R14 staleness rule matches F2.

Two items were deferred. `trend_cagr` on the log of mean daily lines per month is now registered as I52 in `docs/INTERPRETATIONS.md`. Artifact writing from `build_profile` is the second; see open issue 3. The F3c round-0 parity runs (proofs 1 and 2) cover the W2 stock, orphan, dead-stock and untimed-line fixes.

### Round 0: tests 23 passed, 0 failed

The spec audit returned **pass_with_issues** with every T-id pass. The proof audit returned **pass_with_issues** with no findings listed.

| Severity | Finding | Resolution (fix round 1) |
|---|---|---|
| medium | R10 seasonality confidence used `daily.height / 30.4375 < 12`, so a non-leap 12-month history was flagged L while F2 R10 gave no warning (seasonality.py:51). The comment "R10 agrees with DQ" was wrong. | **Fixed.** `confidence = 'L' if calendar_months(start, end) < 12` (the I52 helper). The builder's brute-force check found 263,040 spans with 0 disagreements against `_shorter`. New test `test_R10_seasonality_confidence_on_calendar_months_like_F2`. Confirmed in round 1 (proof 4). |
| medium | The profile was not bit-reproducible between identical runs. Float stats came from polars group_by output in arbitrary order (aggregate.py:105). | **Fixed in part.** `with_cube` sorts by (order_id, sku, qty_units). The float-summing group_bys use `maintain_order=True`. orders, receipts and daily tables are sorted. T3.7 now needs exact equality, and the new slow ecom_mid T3.7 test was added. The round-1 audit found that a change of thread count still changes the result (open issue 1). |
| low | A receipts `pallets` column that is null on some or all rows gave `receipts_pallets` 0.0 or an undercount instead of null (aggregate.py:115, :150). | **Fixed.** The sum is taken only when `null_count == 0`, otherwise null. 0.0 is used only on days without receipts. Side effect: with no pallets column, days without receipts now get 0.0 instead of null. Test `test_receipts_pallets_null_when_unknown_never_an_undercount`. Confirmed in round 1 (proof 5). |
| low | Untimed-line detection differed from the oracle for sub-second times: the engine tested local time == 00:00:00.000000 (aggregate.py:56). | **Fixed.** no_time is now local time < 00:00:01, the same as the oracle and I51. Test `test_sub_second_after_local_midnight_is_a_line_without_time`. Confirmed in round 1 (proof 5). |
| low | Without inventory, `stock.cover_days` was None while the oracle gives 0.0 (stock.py:71). | **Fixed.** Under I49 ("no inventory → 0 for every SKU"), `cover_days = avg_units / mean_units_day` when `mean_units_day > 0`, so it is 0.0. Stock confidence stays L through R14. Confirmed in round 1 (proof 5). |
| low | `build_profile` writes none of the F3 artifacts, and nothing in `src/` calls `write_profile` (build.py:115). | **Deferred.** The F10 CLI command `whsizing profile <run>` (cli.py, outside the F3 paths) is meant to call it. The spec signature of `build_profile` has no run directory. `write_profile` works and is tested by `test_write_profile_artifacts`. Still open (open issue 3). |

Fix-round-1 totals: 5 fixed (1 of them in part, as found in round 1), 1 deferred, 0 rejected. No blockers were reported.

### Round 1: tests 29 passed, 0 failed

The spec audit returned **pass_with_issues** with every T-id pass. The proof audit returned **pass_with_issues** with no findings listed. No fix round followed, so all three findings are open.

| Severity | Finding | Status |
|---|---|---|
| medium (carried from round 0, partly resolved) | `maintain_order=True` fixes the order of the group output rows, but not the order in which each group's floats are added. Per-order `cube_m3` and `weight_kg` sums therefore differ in the last ULP between polars thread-pool sizes, which means between machines with different core counts (aggregate.py:115). | **Open.** Reproduced on 2026-11-08 (proof 6). The diff seen is rel 1.4e-16, far inside T3.1's 0.5 % tolerance, but `demand_profile.json` and any downstream `result.json` hash differently across machines. |
| low (new) | F3 does not validate the canonical tables it loads. `load_canonical` only checks that `order_lines.parquet` exists and does not call `io.canonical.validate` (aggregate.py:25, canonical.py:59). Bad canonical data raises raw polars exceptions instead of `whsizing.errors` classes, or is accepted: a null sku becomes an orphan SKU `None` that is counted in ABC. Mitigation: F2 writes validated canonical tables. | **Open.** Reproduced on 2026-11-08 (proof 7). |
| low (carried from round 0) | `build_profile` writes no F3 artifact. Nothing in `src/` calls `build_profile`, `profile_from_tables`, `build_tables` or `write_profile`. `whsizing profile` is still `_placeholder`, which raises `WhsizingError('`whsizing profile` is not implemented yet')` (cli.py:53, :64). | **Open, deferred to F10** (outside the F3 paths). Re-checked on 2026-11-08: the grep still finds no caller outside `src/whsizing/profile/`. |

## Open issues

1. **Medium, F3-owned: the profile depends on the polars thread count.** Reruns and shuffled input give a bit-identical profile on one machine. With a different `POLARS_MAX_THREADS` (1, 2, 3, 4 and 8 give one hash, the default gives another), a float can differ in the last ULP, for example `.eiq.weight_per_order_kg.p95` 6.281000000000001 vs 6.281. Reproducible manifests or result hashes compared across machines would differ. A possible fix is exact per-group sums: sort inside the group and use `math.fsum`, as the oracle does, or sum in integer units. A T3.7 variant that varies the thread count would catch it.
2. **Low, F3-owned: no validation of the canonical input.** Missing columns or wrong dtypes surface as raw polars errors, not `whsizing.errors` classes (§2.7), and a null sku is counted as an SKU. Calling `io.canonical.validate` in `load_canonical` would close it. F2 output is validated upstream, so this only matters for canonical files written by hand or by another tool.
3. **Low, deferred to F10: `build_profile` writes no artifact, and the CLI `profile` command is a placeholder.** The F3 Artifacts list (`profile/demand_profile.json`, `canonical/daily_series.parquet`, `profile/charts/*`) is only met through `write_profile`, which nothing in `src/` calls yet. The work belongs to the owner of `src/whsizing/cli.py` (F10).
4. **Behaviour change to note:** since the round-1 receipts fix, a dataset with no pallets column gives `receipts_pallets` 0.0 on days without receipts and null on receipt days. Before, every day was null. No `src` consumer outside `profile` reads this column yet.

## Not applicable here and why

- **T3.8 "on the CI runner":** the 60 s budget was measured on this machine (0.41-0.47 s). CI runs the test (`-m "not bench"`, ci.yml:37), but no GitHub CI run was available to this audit.
- **Done-when "the eight charts render in the stub PDF":** the stub PDF belongs to F9, so this audit could not check it. `write_profile` writes all 8 charts as PNG and HTML (proof 3, `test_write_profile_artifacts`).
- **Real client data:** none is available here, and client data must not leave the machine. F3 was exercised on tiny_golden, small synthetic sets and the F1 ecom_mid set (1.03 M lines).
- **T3.1 "equal the spreadsheet":** the reference is the G1c Python oracle (`tests/golden/demand.py`) and `golden_values.json`. A review of the golden values by a domain expert is outside this audit.
- **Docker:** F3 does not depend on it. No F3 test is skipped.
- **Edits outside the F3 paths** (cli.py for open issue 3, `docs/INTERPRETATIONS.md`): not part of F3c.

## Fresh test output (run while writing this record, 2026-11-08)

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f3_*.py tests/property/test_f3_*.py tests/golden/test_f3_*.py -q -rA
.............................                                            [100%]
==================================== PASSES ====================================
_______________ test_T3_8_one_million_lines_profiled_under_60_s ________________
----------------------------- Captured stdout call -----------------------------
T3.8 build_profile on ecom_mid: 0.41 s
=========================== short test summary info ============================
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_6_operating_days_exclude_sundays_in_ecom_mid
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile
PASSED tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden]
PASSED tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[small_synth]
PASSED tests/unit/test_f3_profile.py::test_T3_3_monthly_indices_average_to_one
PASSED tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[golden]
PASSED tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[small_synth]
PASSED tests/unit/test_f3_profile.py::test_T3_5_shipment_split_400kg_order_is_pallet
PASSED tests/unit/test_f3_profile.py::test_definitions_orders_lines_returns_and_calendar
PASSED tests/unit/test_f3_profile.py::test_stock_cover_dead_stock_and_growth
PASSED tests/unit/test_f3_profile.py::test_single_snapshot_has_no_growth_and_missing_inventory_is_low_confidence
PASSED tests/unit/test_f3_profile.py::test_lines_without_time_fall_back_to_default_intraday
PASSED tests/unit/test_f3_profile.py::test_no_shipped_lines_and_unknown_country_raise
PASSED tests/unit/test_f3_profile.py::test_write_profile_artifacts
PASSED tests/unit/test_f3_profile.py::test_stock_only_sku_is_an_orphan_counted_in_stock_and_dead_stock
PASSED tests/unit/test_f3_profile.py::test_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero
PASSED tests/unit/test_f3_profile.py::test_stale_snapshot_uses_the_F2_R14_six_month_rule[snapshot0-H]
PASSED tests/unit/test_f3_profile.py::test_stale_snapshot_uses_the_F2_R14_six_month_rule[snapshot1-L]
PASSED tests/unit/test_f3_profile.py::test_receipts_pallets_null_when_unknown_never_an_undercount
PASSED tests/unit/test_f3_profile.py::test_lines_without_time_below_the_switch_are_left_out_of_the_hourly_shares
PASSED tests/unit/test_f3_profile.py::test_sub_second_after_local_midnight_is_a_line_without_time
PASSED tests/unit/test_f3_profile.py::test_two_full_calendar_years_give_trend_confidence_M_and_flat_demand_no_trend
PASSED tests/unit/test_f3_profile.py::test_R10_seasonality_confidence_on_calendar_months_like_F2[start0-end0-H]
PASSED tests/unit/test_f3_profile.py::test_R10_seasonality_confidence_on_calendar_months_like_F2[start1-end1-H]
PASSED tests/unit/test_f3_profile.py::test_R10_seasonality_confidence_on_calendar_months_like_F2[start2-end2-L]
PASSED tests/unit/test_f3_profile.py::test_R10_seasonality_confidence_on_calendar_months_like_F2[start3-end3-H]
PASSED tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged
PASSED tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet
29 passed in 5.15s
```
