# F3e audit: Profiling, zero-row frames regression

## Verdict: pass_with_issues

All 48 F3 unit and property tests pass. Both F3d open issues are closed: the 0-row receipts crash (HIGH) and the ABC exact-tie residual (LOW). Each fix has a regression test that fails against the old code.
One medium finding from the round-1 spec audit is still open because no fix round followed: if a receipts table has rows but none of them fall inside the shipped-date window, the `receipts_*` columns are all zero, and F4 `receipts` mode then sizes inbound at 0 with no flag. This was re-confirmed on 2026-11-09 (proof 5).

Scope: F3e owns `src/whsizing/profile/**`, `tests/unit/test_f3_*.py` and `tests/property/test_f3_*.py`. Spec: description.md l.708-741 (F3), §2.7 (errors) and the open issues of `docs/audit/F3d.md`. No schema change was made (`schema_changes: []`). No blocker was reported at build time. Fix round 1 reported three blockers outside the F3e paths (see Open issues).

Files changed in the build: `src/whsizing/profile/aggregate.py`, `src/whsizing/profile/abc.py`, `src/whsizing/profile/shipments.py`, `src/whsizing/profile/charts.py` and `tests/unit/test_f3_profile.py`. Fix round 1 changed `src/whsizing/profile/aggregate.py` (`daily_table` guard), `tests/unit/test_f3_profile.py` (rewritten 0-row receipts test, widened `order_ts` match) and `tests/unit/test_f3_ecom_mid.py` (T3.8 bar).

These checks were re-run on the F3e paths while writing this record (2026-11-09). `ruff check`: `All checks passed!`. `ruff format --check`: `14 files already formatted`. `pyright`: `0 errors, 0 warnings, 0 informations`. Largest files: `aggregate.py` has 238 lines and `tests/unit/test_f3_profile.py` has 634 lines, both under the 800-line limit.

## Acceptance tests

Each status reflects the current state: the fresh run below and the round-1 spec audit.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet` (+ dead-stock and trend tests) | pass (not owned by F3e) | Profile statistics match the G1 golden oracle. G1d owns this file, and it is not part of the 48 tests below. Re-run while writing this record: `3 passed in 0.96s`. The reference is the G1 Python oracle, not a spreadsheet reviewed by an expert. |
| T3.2 | `tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden\|small_synth]` | pass | For all three ABC views, the SKU, line and cube shares sum to 1 (abs 1e-12). The A line share is ≥ 0.8 − 1e-9 and A+B is ≥ 0.95. The Pareto curve has 100 monotone points ending at 1. |
| T3.3 | `tests/unit/test_f3_profile.py::test_T3_3_monthly_indices_average_to_one` | pass | The 12 monthly indices, weighted by operating days, average to 1 (abs 1e-12). December > August as a sanity check. |
| T3.4 | `tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[golden\|small_synth]` | pass | Each operating weekday has 24 non-negative hourly shares summing to 1. `peak_hour_share` is the largest share on the design weekday. |
| T3.5 | `tests/unit/test_f3_profile.py::test_T3_5_shipment_split_400kg_order_is_pallet`, `::test_parcels_use_true_division_whatever_the_chunk_layout` | pass | A 400 kg order is a pallet order. So is a 0.7 m3 order. A 31 kg order is 2 parcels. Hand-checkable shares (0.5, 4/7) and mean parcels (1.5). Parcel counts do not depend on the chunk layout. |
| T3.6 | `tests/unit/test_f3_ecom_mid.py::test_T3_6_operating_days_exclude_sundays_in_ecom_mid` | pass | No Sunday is an operating day in ecom_mid (≥ 100 Sundays), and more than 99 % of Mon-Fri non-holidays are operating days. The test is marked slow; it ran in the fresh run. |
| T3.7 | `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` | pass | Hypothesis row shuffle (with `@example(seed=531)`) gives an exactly equal profile. |
| T3.7 | `tests/property/test_f3_properties.py::test_T3_7_profile_identical_across_polars_thread_counts` | pass | tiny_golden gives the same profile at 1, 12 and 64 polars threads, each in a subprocess. |
| T3.7 | `tests/unit/test_f3_ecom_mid.py::test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile` | pass | Shuffled ecom_mid (about 1 M lines) gives a bit-identical profile. |
| T3.7 | `tests/unit/test_f3_ecom_mid.py::test_T3_7_profile_json_identical_across_polars_thread_counts` | pass | ecom_mid gives identical profile JSON bytes across thread counts, including 64. |
| T3.7 | `tests/unit/test_f3_profile.py::test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout` | pass | Whole-column float sums are equal for one chunk and for a [256, 256, 1] layout. |
| T3.8 | `tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s` | pass (CI-runner clause not checked here) | Since fix round 1, the test asserts ≥ 1,000,000 canonical input lines (1,030,012) and `build_profile` < 60 s. Measured 0.73 s in the fresh run (0.89 s in round 1). It was timed on this machine. Under a literal "lines profiled" reading, the 981,910 shipped lines are below 1 M; counting input lines is the engineer's reading, which the round-1 auditor called defensible. |
| F3d open 1 (HIGH) | `tests/unit/test_f3_profile.py::test_zero_row_receipts_profile_like_no_receipts` | pass | A 0-row receipts table now profiles exactly like no receipts table: no `receipts_*` column, and the daily frame and the profile both equal the no-receipts result. With the `daily_table` emptiness guard removed (in-memory mutation), it fails with `AssertionError` (proof 2). |
| F3d open 1 (HIGH) | `tests/unit/test_f3_profile.py::test_aggregation_helpers_accept_zero_row_frames` | pass | `fsum_by`, `orders_table`, `with_cube`, `sku_table` and `split_orders` return 0 rows for 0 rows. `shipment_split` and `series_stats` raise `WhsizingError`. With the old `zip(strict=True)` `fsum_by`, it fails with `ValueError: zip() argument 2 is shorter than argument 1` (proof 3). |
| F3d open 2 (LOW) | `tests/unit/test_f3_profile.py::test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines0-expected0\|lines1-expected1]` | pass | At an exact 80 % or 95 % cumulative tie, the next SKU gets the I6 class (B, resp. C), the same as the golden oracle. With the old polars `classify`, both cases fail: `['A','A'] != ['A','B']` and `['A','A','B'] != ['A','A','C']` (proof 3). |
| F3e edge | `tests/unit/test_f3_profile.py::test_zero_row_inventory_profiles_like_no_inventory` | pass | 0-row inventory takes the I49 path: 0 stock, cover 0.0, confidence L, growth None. |
| F3e edge | `tests/unit/test_f3_profile.py::test_zero_row_sku_master_makes_every_sku_an_orphan_without_dims` | pass | 0-row sku_master makes every SKU an orphan without dims. `write_profile` runs with `UserWarning` turned into an error. With the `charts.py` legend guard bypassed, the test fails with the matplotlib warning `No artists with labels found to put in legend`. |
| F3e edge | `tests/unit/test_f3_profile.py::test_a_single_line_dataset_profiles_and_writes_its_artifacts` | pass | A dataset of one order line gives one-value series stats and writes all 18 artifacts. |

The other F3 unit tests from F3c and F3d all pass (definitions, stock and dead stock, orphans, I49-I52, R10 and R14, receipts pallets, `write_profile`, the 8 malformed-canonical cases).

## Proofs (captured by the auditors during the audit)

The F3e spec auditors captured these proofs in round 0 or round 1. Both proof audits returned pass_with_issues and listed no T-ids, findings or proofs, so every proof below comes from a spec audit. Scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/`, shown as `<s>/` below. Every command runs from `/Users/skarwech/saas_v1`. Proofs 1, 2, 3, 5 and 6 were re-run while writing this record (2026-11-09), and the fresh output is quoted. Proof 4 comes from the audit record only. Where the audit record was truncated, only the visible text is quoted.

1. **F3d open issue 1 is closed end to end (round 0, confirmed again after the round-1 fix).** An F2 ingest whose receipts all fail REQ writes a 0-row `receipts.parquet`. `build_profile` now succeeds with the pre-F3d baseline of 562 operating days, writes all 18 artifacts, and the daily frame has no `receipts_*` column.
   Command: `uv run python <s>/audit_F3e/p1_f2_canonical.py <s>/audit_F3e/r2/f2e2e/run/canonical`
   ```
   order_lines (2055, 10)
   receipts (0, 7)
   inventory (5911, 5)
   sku_master (257, 15)
   operating_days 562 period 2024-01-01 2025-12-30
   daily.lines.p95 7.0 abcA line_share 0.8029456576942611
   daily receipt cols [] {}
   artifacts 18
   ```
   In round 0, before the fix-round-1 guard, the same script printed `daily receipt cols ['receipts_lines', 'receipts_units', 'receipts_pallets'] {... all 0.0}`. That was the round-0 medium finding. The round-1 auditor also ran F4 on this directory: `0-row receipts.parquet -> ConfigError flows.inbound_mode is 'receipts' but the daily frame has no ['receipts_units', 'receipts_pallets', 'receipts_lines']`, the same message as with no receipts file.

2. **The rewritten 0-row receipts test catches the removal of the `daily_table` guard (round 1).** The guard `if receipts is not None and receipts.is_empty(): receipts = None` is removed by an in-memory source mutation (`exec`), and the repo is not touched.
   Command: `uv run python <s>/audit_F3e/r2/p6_guard_mutation.py`
   ```
   with guard -> test PASS
   guard removed -> test FAIL AssertionError
   ```

3. **`fsum_by` and `classify` are exact, and the regression tests fail against the old code (round 0, re-run).** `classify` matches the golden oracle `abc_classes` on 20000 random cases, 208 of them with an exact 80/95 % tie.
   Command: `uv run python <s>/audit_F3e/p4_revert_and_oracle.py`
   ```
   fsum_by: [('a', 0.30000000000000004), ('b', 0.30000000000000004), ('c', 1e+16)] expected [('a', 0.30000000000000004), ('b', 0.30000000000000004), ('c', 1e+16)]
   classify vs oracle: 0 mismatches over 20000 random cases (208 with an exact 80/95 % tie)
   old fsum_by
     zero_row_receipts: PASS
     helpers_zero_rows: FAIL ValueError: zip() argument 2 is shorter than argument 1
     tie[28,7]: PASS
     tie[851,764,85]: PASS
   old classify
     zero_row_receipts: PASS
     helpers_zero_rows: PASS
     tie[28,7]: FAIL AssertionError:
     tie[851,764,85]: FAIL AssertionError:
   ```
   In round 0, `zero_row_receipts` also failed with the old `fsum_by`. It passes now, and that is expected: fix round 1 added the guard in `daily_table`, so a 0-row receipts frame no longer reaches `fsum_by`. Since then, `test_aggregation_helpers_accept_zero_row_frames` is the only test that guards the 0-row behaviour of `fsum_by` itself, and `test_zero_row_receipts_profile_like_no_receipts` guards the `daily_table` guard (proof 2).

4. **Edge cases and malformed inputs either profile cleanly or raise a §2.7 class, never a builtin error (rounds 0 and 1, from the audit record).**
   Command: `uv run python <s>/audit_F3e/p3_edges.py ; ONLY_EMPTY=1 uv run python <s>/audit_F3e/r2/p5_receipts_window.py <canonical>`
   ```
   all three side tables 0 rows: OK op_days=9 stock.n_snap=0 cover=0.0 dims_cov=0.000 artifacts=18
   0-row receipts, no pallets column: OK ... artifacts=18
   0-row order_lines: whsizing.errors.DataQualityError: no shipped order lines ...
   every line cancelled: whsizing.errors.DataQualityError ...
   only negative qty (returns): whsizing.errors.DataQualityError ...
   sku_master all dims null: OK ... dims_cov=0.000 artifacts=18
   sku_master weight NaN: whsizing.errors.WhsizingError: canonical sku_master failed s …[clipped]
   ```
   The 0-row receipts variants were re-run as part of proof 5. A malformed 0-row table is still validated before the emptiness guard runs, so it still raises: `WhsizingError: ... expected column 'receipt_ts' to have type Datetime(...), got String`, `WhsizingError: ... column 'receipt_ts' not in dataframe`, `DataQualityError: canonical receipts: cannot find column "sku", cannot find column "qty_units" (required by §4.1)`.

5. **Open finding (round 1, medium), re-confirmed: receipts that all fall outside the shipped-date window give F4 a silent zero inbound.** The data is the F2-ingested canonical directory with 2023-only or 2026-only receipts, and shipped dates from 2024-01-01 to 2025-12-30. Receipts that overlap the window work, so the defect is the window and not receipts in general.
   Command: `uv run python <s>/audit_F3e/r2/p5_receipts_window.py <s>/audit_F3e/r2/f2e2e/run/canonical`
   ```
   receipts 2023 only (before 2024-01-01 first shipped date): daily receipts sums {'receipts_lines': 0.0, 'receipts_units': 0.0, 'receipts_pallets': 0.0}
      F4 receipts mode -> units 0.0 pallets 0.0 lines 0.0 trucks 0.0 flags []
   receipts 2026 only (after 2025-12-30 last shipped date): daily receipts sums {'receipts_lines': 0.0, 'receipts_units': 0.0, 'receipts_pallets': 0.0}
      F4 receipts mode -> units 0.0 pallets 0.0 lines 0.0 trucks 0.0 flags []
   receipts overlapping (2025-06 .. ): daily receipts sums {'receipts_lines': 100.0, 'receipts_units': 10000.0, 'receipts_pallets': 200.0}
      F4 receipts mode -> units 121.66529024000002 pallets 2.4333058048000002 lines 1.2166529024000001 trucks 0.09358868480000002 flags []
   ```

6. **Hand check of the daily receipts columns (round 1, from the audit record).** It covers conversion to the local Paris date (22:30 UTC on 04-28 counts on 04-29), the exact pallet sum, null pallets when one receipt that day has no pallets, and 0 on days without a receipt.
   Command: `uv run python <s>/audit_F3e/r2/p7_hand_receipts.py`
   ```
   exact cells: [(2025-04-28, 0.0, 0.0, 0.0), (2025-04-29, 2.0, 30.0, 0.30000000000000004), (2025-04-30, 2.0, 70.0, None), (2025-05-01, 0.0, 0.0, 0.0)]; expected 04-29 (2,30,fsum[0.1,0.2]=0.30000000000000004), 04-30 (2,70,null)
   ```

7. **Lint, format and types are clean, and the full fast suite has no F3 failure (round 0; lint, format and types re-run).**
   Command: `uv run ruff check ...; uv run ruff format --check ...; uv run pyright ...; uv run pytest -q -m 'not bench and not slow'`
   ```
   All checks passed!
   14 files already formatted
   0 errors, 0 warnings, 0 informations
   FAILED tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param
   1 failed, 695 passed, 2 skipped, 9 deselected in 29.44s
   ```
   The one failure in round 0 was a G1 register test, outside F3. In round 1 the auditor reported no failure in the full fast suite.

## Audit rounds

### Build (before round 0)

The engineer addressed F3d open issues 1 and 2 and checked other zero-row edge cases.

- **F3d issue 1 (HIGH, 0-row receipts crash).** `fsum_by` (aggregate.py) now uses `itertools.pairwise` and `accumulate`. On 0 rows it finds no bounds and returns a 0-row Float64 frame, so this one shared fix covers all three callers: `orders_table`, `daily_table` and `_receipts_daily`. The F3d real-data case (F2 canonical, 0 receipt rows) profiles again with 562 operating days. Empty-table checks on tiny_golden (0-row receipts, inventory and sku_master, separately and all at once) each write all 18 artifacts.
- **F3d issue 2 (LOW, ABC tie).** This issue was not benign. With polars arithmetic, 28 × (1/35) < 0.80 made the SKU after an exact 80 % tie class A, where I6 and the oracle give B. The 95 % case is the same (851/1700 + 764/1700 gave B instead of C). `abc.classify` now computes the share and the running sum in numpy, with true division and a left-to-right cumsum, as the oracle does. This also removes the length-1-chunk half of the issue, because no polars arithmetic runs on the shares any more.
- **charts.py.** It is inside the F3e paths but outside the "aggregation helper" wording. With a 0-row sku_master, `write_profile` raised a real matplotlib `UserWarning` from an empty legend. The legend is now drawn only when there are handles. The test depends on the locked matplotlib version.
- **shipments.py.** `split_orders` works on 0 rows. The previous attempt's edits were kept.
- **Checks.** ruff and pyright were clean. The T3.1 golden file and the G1 engine parity file gave 12 passed and 1 skipped (F7 not built).

### Round 0: tests 48 passed, 0 failed

The spec audit returned **pass_with_issues**. The proof audit returned **pass_with_issues** and listed no T-ids, findings or proofs.

| Severity | Finding | Resolution (fix round 1) |
|---|---|---|
| medium | aggregate.py:201: a 0-row canonical `receipts.parquet` gave all-zero `receipts_lines`/`units`/`pallets` columns. F4 `inbound_mode: receipts` then sized inbound at 0 units, pallets, lines and trucks with no flag, whereas an absent table raises `ConfigError`. The new F3e test locked in the zero columns. This was not an F3e regression; it was already the behaviour before F3d. | **Fixed.** `daily_table` treats a 0-row receipts frame as absent (`if receipts is not None and receipts.is_empty(): receipts = None`), per §4.1 "receipts_* if receipts present" and F3 step 1 "join receipts if present". The test was rewritten: no `receipts_*` column, and the daily frame and profile equal the no-receipts ones. RED check: with the guard disabled, the test fails. Confirmed in round 1 (proofs 1 and 2). |
| low | test_f3_ecom_mid.py:47: T3.8 asserted > 0.9 M lines on operating days, not the spec's 1 M lines, and was timed locally, not on the CI runner. | **Fixed (CI part not checkable here).** The test now asserts `scan_parquet(order_lines).len() >= 1_000_000` (1,030,012) before timing `build_profile` under 60 s. The old profiled-lines check stays as a sanity check (> 0.9 × n_in; 95.3 % here). `.github/workflows/ci.yml` line 37 runs `pytest -m "not bench"`, which includes this slow test, so CI checks the budget, but no CI run was available. Confirmed in round 1. |
| (collateral, not a finding) | `test_invalid_canonical_table_raises_whsizing_error[order_lines drop order_ts]` failed during the round. `src/whsizing/io/canonical.py` (not owned by F3e) changed twice (08:23 and 08:24), and the message alternated between `cannot find column "order_ts"` (DataQualityError) and `column 'order_ts' not in dataframe` (WhsizingError). | **Fixed in the test.** The match was widened to `canonical order_lines.*column .order_ts.`. It still requires the table and column names. The F3 code is unchanged. Reported as a blocker for the owner of `io/canonical.py`. |

Fix-round-1 totals: 3 fixed, 0 rejected, 0 deferred. Three blockers outside the F3e paths were reported:
- the `io/canonical.py` wording churn (open issue 2);
- transient failures of `test_f6_area_golden.py::test_T6_3_trace_inputs_resolve` and `test_g1_register` during concurrent edits by other features, both of which passed on re-run;
- the T3.8 budget on the CI runner, which only a CI run can confirm (see Not applicable).

### Round 1: tests 48 passed, 0 failed

The spec audit returned **pass_with_issues**. The proof audit returned **pass_with_issues** and listed no T-ids, findings or proofs. No fix round followed, so the finding below is open.

| Severity | Finding | Status |
|---|---|---|
| medium | aggregate.py:200: the round-0 medium, as worded (a 0-row receipts table), is resolved. The same defect is still reachable another way: a receipts table that has rows, none of them inside the shipped-date calendar (first to last shipped local date, I2), still gives all-zero `receipts_lines`/`units`/`pallets` on every day. F4 `receipts` mode then sizes inbound at 0 units, pallets, lines and trucks with no flag. | **Open (deferred by default, no fix round).** Re-confirmed while writing this record (proof 5). See open issue 1. |

The round-1 auditor also confirmed: the round-0 medium is fixed end to end (proof 1), the guard mutation fails the test (proof 2), the old `fsum_by` and the old `classify` still fail their tests (proof 3), malformed 0-row receipts still raise §2.7 classes (proof 4), the receipts hand check (proof 6), and the T3.8 rewrite.

## Open issues

1. **Medium, inside the F3e paths, unfixed: receipts entirely outside the shipped-date window give a silent zero inbound.** `daily_table` (src/whsizing/profile/aggregate.py, around line 193-213) builds the calendar from the first to the last shipped date. Receipts dated entirely before or after it join to nothing, and the `receipts_*` columns become 0.0 on every day. `design/inbound._receipts` only rejects missing columns or all-null pallets, so F4 `receipts` mode returns 0 units, pallets, lines and trucks with `flags []` (proof 5, 2026-11-09). Suggested fix, not applied because this record may only edit `docs/audit/F3e.md`: in `daily_table`, treat receipts with no row in [start, end] as absent, the same as the 0-row guard, or flag them. Add a test with receipts only outside the window.
2. **Blocker outside the F3e paths (F2, `src/whsizing/io/canonical.py`).** Its missing-`order_ts` message changed twice during fix round 1 (`DataQualityError ... cannot find column "order_ts"` vs `WhsizingError ... column 'order_ts' not in dataframe`). The owner should settle on one wording. Carried from F3d: `validate()` leaks `polars ColumnNotFoundError` for columns that pandera coerces. F3 wraps this in `load_canonical`.
3. **Outside the F3e paths (F2).** The REQ rule on receipts only warns, even when it drops every row. That is how a 0-row receipts table reaches F3. F3 now handles it like an absent table.
4. **Low, outside the F3e paths: `docs/audit/F3c.md` still lists F3c issues 1 and 2 as open,** although F3d closed them. This is for the owner of that file.
5. **Deferred to F10 (carried from F3c issue 3).** `build_profile` writes no artifact, and the CLI `profile` command is still a placeholder. `write_profile` works and is tested.
6. **Note on T3.8.** The test counts input lines (1,030,012). Under a literal "lines profiled" reading, the 981,910 shipped lines are below 1 M. The 60 s budget on the CI runner is unconfirmed until a CI run (see below).

## Not applicable here and why

- **T3.8 "on the CI runner":** the budget was measured on this machine (0.73 s fresh, 0.89 s in round 1). `ci.yml` runs this slow test through `-m "not bench"`, but no GitHub CI run was available to this audit.
- **Done-when "the eight charts render in the stub PDF":** the stub PDF belongs to F9. `write_profile` writes the 8 charts, and the zero-row and single-line tests check that all 18 artifacts are written.
- **Real client data:** none is available here, and client data must not leave the machine. F3e was exercised on tiny_golden, small synthetic sets, the F1 ecom_mid set (1.03 M lines) and an F2 ingest of synthetic CSVs.
- **T3.1 "equal the spreadsheet":** the reference is the G1 Python oracle and `golden_values.json`. A domain-expert review of the golden values is outside this audit, and G1d owns the test file.
- **Docker:** F3 does not depend on it. No F3 test is skipped.
- **Edits outside the F3e paths** (`io/canonical.py`, F2's REQ rule, `cli.py`, `docs/audit/F3c.md`): not part of F3e.

## Fresh test output (run while writing this record, 2026-11-09)

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f3_*.py tests/property/test_f3_*.py -q -rA
................................................                         [100%]
==================================== PASSES ====================================
_______________ test_T3_8_one_million_lines_profiled_under_60_s ________________
----------------------------- Captured stdout call -----------------------------
T3.8 build_profile on ecom_mid: 0.73 s
=========================== short test summary info ============================
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_6_operating_days_exclude_sundays_in_ecom_mid
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile
PASSED tests/unit/test_f3_ecom_mid.py::test_T3_7_profile_json_identical_across_polars_thread_counts
PASSED tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden]
PASSED tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[small_synth]
PASSED tests/unit/test_f3_profile.py::test_T3_3_monthly_indices_average_to_one
PASSED tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[golden]
PASSED tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[small_synth]
PASSED tests/unit/test_f3_profile.py::test_T3_5_shipment_split_400kg_order_is_pallet
PASSED tests/unit/test_f3_profile.py::test_parcels_use_true_division_whatever_the_chunk_layout
PASSED tests/unit/test_f3_profile.py::test_definitions_orders_lines_returns_and_calendar
PASSED tests/unit/test_f3_profile.py::test_stock_cover_dead_stock_and_growth
PASSED tests/unit/test_f3_profile.py::test_single_snapshot_has_no_growth_and_missing_inventory_is_low_confidence
PASSED tests/unit/test_f3_profile.py::test_lines_without_time_fall_back_to_default_intraday
PASSED tests/unit/test_f3_profile.py::test_no_shipped_lines_and_unknown_country_raise
PASSED tests/unit/test_f3_profile.py::test_per_group_float_sums_are_exact_so_independent_of_the_adding_order
PASSED tests/unit/test_f3_profile.py::test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-column .order_ts.]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-find column "sku"]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-find column "qty_units"]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-coerce 'qty_units']
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-'order_ts' to have type]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-'sku' contains null]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[inventory-<lambda>-'sku' contains null]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[sku_master-<lambda>-find column "weight_kg"]
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
PASSED tests/unit/test_f3_profile.py::test_zero_row_receipts_profile_like_no_receipts
PASSED tests/unit/test_f3_profile.py::test_zero_row_inventory_profiles_like_no_inventory
PASSED tests/unit/test_f3_profile.py::test_a_single_line_dataset_profiles_and_writes_its_artifacts
PASSED tests/unit/test_f3_profile.py::test_zero_row_sku_master_makes_every_sku_an_orphan_without_dims
PASSED tests/unit/test_f3_profile.py::test_aggregation_helpers_accept_zero_row_frames
PASSED tests/unit/test_f3_profile.py::test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines0-expected0]
PASSED tests/unit/test_f3_profile.py::test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines1-expected1]
PASSED tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged
PASSED tests/property/test_f3_properties.py::test_T3_7_profile_identical_across_polars_thread_counts
48 passed in 16.49s

$ uv run ruff check src/whsizing/profile tests/unit/test_f3_*.py tests/property/test_f3_*.py
All checks passed!
$ uv run ruff format --check src/whsizing/profile tests/unit/test_f3_*.py tests/property/test_f3_*.py
14 files already formatted
$ uv run pyright src/whsizing/profile tests/unit/test_f3_*.py tests/property/test_f3_*.py
0 errors, 0 warnings, 0 informations
$ uv run pytest tests/golden/test_f3_golden.py -q        # T3.1, owned by G1d, run for reference
3 passed in 0.96s
```

The test suite passes, but no test covers open issue 1. It only shows with receipts entirely outside the shipped-date window (proof 5).
