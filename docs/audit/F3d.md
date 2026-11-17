# F3d audit: Profiling remediation (thread-count determinism, canonical validation)

## Verdict: fail

All 41 F3 unit and property tests pass, and both F3c issues are closed: the profile no longer depends on the polars thread count or on row order, and bad canonical tables raise `WhsizingError`.
The verdict is **fail** because the round-1 spec audit found a new high regression and no fix round followed. The new `fsum_by` crashes with a raw `builtins.ValueError` when the canonical receipts table has 0 rows, and F2 can write such a table. Both round-1 auditors (spec and proof) returned fail. The crash was reproduced again while writing this record.

Scope: F3d owns `src/whsizing/profile/**`, `tests/unit/test_f3_*.py` and `tests/property/test_f3_*.py`. It does not own `tests/golden/test_f3_golden.py`, which G1d edits in this wave. Spec: description.md l.708-741 (F3), principle 5 and T3.7 (reproducibility), the open issues of `docs/audit/F3c.md`, and register entries I49-I52 in `docs/INTERPRETATIONS.md`. No schema change was made (`schema_changes: []`).

Files changed:
- Build: `src/whsizing/profile/aggregate.py`, `tests/unit/test_f3_ecom_mid.py`, `tests/unit/test_f3_profile.py`.
- Fix round 1 (from the fix report): `src/whsizing/profile/aggregate.py` (rechunk in `load_canonical`, validation one table at a time, new `fsum` helper), `src/whsizing/profile/abc.py` and `src/whsizing/profile/stock.py` (whole-column sums through `fsum`), `src/whsizing/profile/shipments.py` (parcel division in numpy), `tests/property/test_f3_properties.py` (`@example(seed=531)` and a new thread-count test), and `tests/unit/test_f3_profile.py`.

While writing this record (2026-11-08), these checks were re-run on the F3d paths. `ruff check`: `All checks passed!`. `ruff format --check`: `14 files already formatted`. `pyright`: `0 errors, 0 warnings, 0 informations`. Largest files: `aggregate.py` has 232 lines and `tests/unit/test_f3_profile.py` has 502 lines, both under the 800-line limit.

## Acceptance tests

The status is the current one (fresh run below and round-1 spec audit).

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T3.1 | `tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet` | pass (not owned by F3d) | Profile statistics match the G1 golden oracle within 0.5 %. G1d owns this test, so F3d did not edit it. The round-1 auditor ran it with the F4 golden and design tests (35 passed). Re-run while writing this record: `3 passed`. The per-order and per-day sums now use `math.fsum`, the same as the oracle (`tests/golden/demand.py::fsum_lists`). |
| T3.2 | `tests/unit/test_f3_profile.py::test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden\|small_synth]` | pass | For all 3 rankings, the ABC shares sum to 1 and the class A line share is ≥ 0.8 − ε. The Pareto curve is monotone and has 100 points. |
| T3.3 | `tests/unit/test_f3_profile.py::test_T3_3_monthly_indices_average_to_one` | pass | The monthly indices, weighted by operating days, average to 1. |
| T3.4 | `tests/unit/test_f3_profile.py::test_T3_4_intraday_shares_sum_to_one_per_weekday[golden\|small_synth]` | pass | For each weekday, the 24 hourly shares sum to 1. |
| T3.5 | `tests/unit/test_f3_profile.py::test_T3_5_shipment_split_400kg_order_is_pallet`, `::test_parcels_use_true_division_whatever_the_chunk_layout` | pass | A 400 kg order is a pallet order. The new parcel division (in numpy) matches a hand computation of max(1, ceil(w/30)) on 11 orders, on 1 chunk and on 3 chunks. Edge values: 30.000000000000004 kg gives 2 parcels; exactly 300 kg stays a parcel order with 10 parcels; 300 + 1e-9 kg is a pallet order. |
| T3.6 | `tests/unit/test_f3_ecom_mid.py::test_T3_6_operating_days_exclude_sundays_in_ecom_mid` | pass | No Sunday is an operating day in ecom_mid. The test is marked slow; it ran in the F3 runs and in the fresh run. In the round-0 auditor's own run, op_days was 626. |
| T3.7 | `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` | pass (failed in round 0) | Shuffling the rows gives an exactly equal profile. In round 0 it failed at seed 531, a regression caused by F3d's `validate()` call. Seed 531 is now pinned with `@example(seed=531)`. |
| T3.7 | `tests/property/test_f3_properties.py::test_T3_7_profile_identical_across_polars_thread_counts` | pass (new in round 1) | tiny_golden, shuffled with seed 531 (sku_master seed 532), gives the same profile JSON at `POLARS_MAX_THREADS` 1, 12 and 64. Each count runs in a subprocess, so the test does not depend on the machine. It is not marked slow and takes about 3 s. With the rechunk reverted it fails (`assert 2 == 1`). |
| T3.7 | `tests/unit/test_f3_profile.py::test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout` | pass (new in round 1) | Whole-column float sums are equal for one chunk and for a [256, 256, 1] layout. It fails with the old stock `Series.sum`. |
| T3.7 | `tests/unit/test_f3_ecom_mid.py::test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile` | pass | Shuffled ecom_mid (about 1 M lines) gives a bit-identical profile. Round 0 rated this test weak: it uses one thread count and 5000 SKUs, so it cannot reach the length-1-chunk path. |
| T3.7 | `tests/unit/test_f3_ecom_mid.py::test_T3_7_profile_json_identical_across_polars_thread_counts` | pass | ecom_mid gives identical JSON bytes in subprocesses at 1 and 2 threads, the default and, since round 1, 64 threads. It failed before the build fix (diff at byte 1707). Round 0 rated it weak because a 5000-SKU master never forms a length-1 chunk. The 64-thread case added in round 1 fails with the old stock `Series.sum`. |
| T3.8 | `tests/unit/test_f3_ecom_mid.py::test_T3_8_one_million_lines_profiled_under_60_s` | pass | `build_profile` on ecom_mid (1,030,012 order lines), including canonical validation, took 0.74 s in the fresh run and 0.75 s in round 1. The budget is 60 s. F3c measured 0.41-0.47 s; the extra time comes from the exact sums. Measured on this machine, not on the CI runner. |
| F3c issue 1 | `tests/unit/test_f3_profile.py::test_per_group_float_sums_are_exact_so_independent_of_the_adding_order` | pass | `fsum_by` returns exactly 1.0 for ten 0.1 values and for [1e16, 1.0, −1e16]. An ordinary left-to-right sum gets both wrong. This test is fast (not marked slow). |
| F3c issue 2 | `tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[...]` (8 cases) | pass | Each case must raise `WhsizingError` matching `canonical {table}.*{column}`: order_ts, sku, qty_units or sku_master.weight_kg missing; a qty_units that cannot be converted; a naive order_ts; a null sku in order_lines; a null sku in inventory. The build report gives the RED check: the old `load_canonical` raised `ColumnNotFoundError` or `ComputeError`, and it accepted the naive timestamp and both null skus. |

The other F3 unit tests from F3c (definitions, stock and dead stock, orphan SKUs, I49 average stock, I51 lines without a time, I52 trend, R10 and R14 rules, receipts pallets, `write_profile`) all pass. None of them covers a canonical receipts table with 0 rows (open issue 1).

## Proofs (captured by the auditors during the audit)

The F3d spec auditors captured these proofs in round 0 or round 1. The proof audits of both rounds returned fail and listed no findings and no proofs. Scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F3d/`, shown as `<s>/` below. Every command runs from `/Users/skarwech/saas_v1`. Where the audit record was truncated, only the visible text is quoted. Proof 1 and the fixed state in proof 2 were re-run while writing this record. The other proofs come from the audit record only.

1. **Open regression (round 1, high): an F2 ingest that ends with 0 receipt rows makes `build_profile` crash with a raw `ValueError` in `fsum_by`.** Before F3d, the aggregate built the same canonical directory.
   Command: `uv run python <s>/f2_empty_receipts.py <s>/f2e2e ; PYTHONPATH=<s>/rev2 uv run python -c '...build_profile(<s>/f2e2e/run/canonical)...'`
   ```
   ingest_done band=usable dq_score=90.0
   ingest ok; receipts rows_out: [0]
   canonical receipts.parquet rows: 0
   build_profile RAISED builtins.ValueError: zip() argument 2 is shorter than argument 1
   pre-F3d aggregate: rev2/whsizing/__init__.py OK operating_days 562
   ```
   Re-run while writing this record, on a fresh copy of the inputs (`.../scratchpad/F3d_doc/e2e`): the same four engine lines, the same `ValueError`. A direct call `fsum_by(<0-row date/pallets frame>, "date", ("pallets",))` also gives `RAISED builtins.ValueError: zip() argument 2 is shorter than argument 1`.

2. **Thread-count dependence found in round 0, and fixed in round 1.** Input: tiny_golden with a shuffled sku_master (seed 532). Before the fix, validation split the table into one chunk per thread, and a length-1 chunk computed the unit cube with a different rounding.
   Command: `for t in 1 2 4 8 12 16; do POLARS_MAX_THREADS=$t uv run python <s>/golden_threads.py tests/golden/tiny_golden 532; done; for t in 1 2 4 12; do POLARS_MAX_THREADS=$t uv run python <s>/kernel2.py; done`
   ```
   round 0:
   threads= 1 hash=206183beee3ce984 cube_p50=0.0032815939320000004
   threads= 8 hash=206183beee3ce984
   threads=12 hash=3ab653c42845259c cube_p50=0.003281593932
   threads=16 hash=206183beee3ce984
   ---
   threads 12 n_chunks 12 chunk lengths [9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 1]
   round 1 (1 2 3 4 8 12 13 16 24 64 threads):
   threads= 1 hash=722f19aaa83bd1cf cube_p50=0.0032815939320000004 ... threads=12 hash=722f19aaa83bd1cf ... threads=64 hash=722f19aaa83bd1cf  (10/10 identical)
   ```
   Re-run while writing this record at 1, 2, 12, 24 and 64 threads: every run gives `hash=722f19aaa83bd1cf cube_p50=0.0032815939320000004`.

3. **The T3.7 property test failed reproducibly in round 0.** Shuffling the rows changed one SKU's unit cube by one ULP. That changed 31 per-order cubes and `eiq.cube_per_order_m3.p50`.
   Command: `uv run python <s>/seed531.py 531 && uv run python <s>/seed531b.py ...`
   ```
   per-order cube diffs: 31
   col differs: unit_cube_m3
   col differs: line_cube_m3
   p50: 0.0032815939320000004 0.003281593932 sorted equal: False
   skus with different unit_cube_m3: 1  (7d6ce6825abd1097, 117.4 x 61.6 x 187.5)
   engine base = 0.0013559700000000002  engine shuffled = 0.00135597
   ```

4. **The round-0 drift was caused by F3d's `validate()` call.** The loader before F3d is stable, and rechunking the validated frames removes the drift.
   Command: `uv run python <s>/rate.py 100; POLARS_MAX_THREADS=4 uv run python <s>/rate.py 100; uv run python <s>/rate_old.py 100; uv run python <s>/rate_rechunk.py 100`
   ```
   threads=12 seeds=100 failing=4  (7: .abc.by_cube_movement.B.cube_share ...; 90: .abc.by_stock_cube.C.cube_share ...)
   threads=4 seeds=100 failing=0
   [old loader] threads=12 seeds=100 failing=0
   [rechunk] threads=12 seeds=100 failing=0
   ```

5. **After round 1, the shuffle property holds at high thread counts.** In round 0, 4 of 100 seeds failed at 12 threads.
   Command: `for t in 12 24 64; do POLARS_MAX_THREADS=$t uv run python <s>/rate.py 200; done`
   ```
   threads=12 seeds=200 failing=0
   threads=24 seeds=200 failing=0
   threads=64 seeds=200 failing=0
   ```

6. **Round 1: thread-count and row-order independence hold beyond tiny_golden.** The datasets are 8 shuffled ecom_mid subsets (130-2049 SKUs, 3 stock-only orphans, 23 snapshots, 513-20000 orders, including sizes of 256k+1) and the full ecom_mid. Each gives one hash over 10 thread counts. Two reshuffles of each subset give the same hash.
   Command: `uv run python <s>/sweep.py 1,2,3,5,7,12,13,24,32,64 <s>/subs/* <s>/ecom ; uv run python <s>/sweep.py 1,12,64 <s>/subs_r/*`
   ```
   k513_m513_s2 distinct=1 f1c66603141c | k257_m2000_s1 distinct=1 571a9fdbebde | ecom distinct=1 0144ee6e2faa | ... k513_m513_s2_r11 distinct=1 f1c66603141c | k513_m513_s2_r12 distinct=1 f1c66603141c
   ```
   The ecom_mid hash here (`0144ee6e2faa…`) differs from the round-0 hash `4bb79cdb811b31b6` (proof 7). Both are right for their time: the round-1 fixes (stock and ABC sums through `fsum`, parcel division in numpy) changed the values. Each state gives a single hash at every thread count.

7. **Round 0, before the round-1 fixes: ecom_mid (1.03 M lines, 5000 SKUs) is identical across thread counts and shuffles, and builds in under 2 s.** This matched the engineer's hash.
   Command: `for t in 1 3 7 12; do POLARS_MAX_THREADS=$t uv run python <s>/ecom_hash.py <s>/ecom; done; uv run python <s>/ecom_hash.py <s>/ecom 5`
   ```
   threads= 1 shuffle=  - hash=4bb79cdb811b31b6 build=1.55s op_days=626 wpo_p95=6.281 lines_mean=1568.5
   threads=12 shuffle=  - hash=4bb79cdb811b31b6 build=0.79s
   threads=12 shuffle=  5 hash=4bb79cdb811b31b6 build=0.81s
   threads= 3 shuffle=  9 hash=4bb79cdb811b31b6 build=1.05s
   ```

8. **`fsum_by` gives exactly the plain-Python `math.fsum` result** for the per-order and per-day cube and weight, and for receipt pallets (null when a pallets value is unknown, 0.0 on days without receipts). Round 0.
   Command: `uv run python <s>/hand_fsum.py <s>/ecom`
   ```
   orders=493788 order mismatches=0 | days with lines=626 day mismatches=0
   receipt days=104 receipts_pallets mismatches=0
   fsum_by null key: [(None, 0.30000000000000004), ('a', 0.30000000000000004)] expected [...same...]
   ```

9. **The new tests catch their fixes (round 1).** Each fix was reverted in a scratch copy of `src` (`PYTHONPATH`), and the matching tests failed.
   Command: `PYTHONPATH=<s>/rev uv run pytest tests/property/test_f3_properties.py -q ; PYTHONPATH=<s>/rev uv run pytest tests/unit/test_f3_profile.py -q -k chunk_layout`
   ```
   rechunk reverted: FAILED test_T3_7_shuffling_rows_leaves_profile_unchanged, FAILED test_T3_7_profile_identical_across_polars_thread_counts (assert 2 == 1) | fsum/numpy reverted: FAILED test_parcels_use_true_division_whatever_the_chunk_layout (assert [1, 1, 1] == [1, 1, 2]), FAILED test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout
   ```

10. **Canonical validation (F3c issue 2): 16 of 16 malformed inputs raise `WhsizingError`, and since round 1 the message names the table.** The inputs include missing columns, ns, non-UTC and string timestamps, qty 0, a bad line_status, a null order_id, a duplicate sku, out-of-range dims, a type that cannot be converted and negative stock. None is accepted.
    Command: `uv run python <s>/malformed.py`
    ```
    round 0: receipts drop receipt_id -> WhsizingError: canonical table in /var/folders/.../tmps145p0oy failed validation: unable to f...
    round 1: receipts drop receipt_id -> WhsizingError: canonical receipts in /var/folders/.../tmpq2p19hw7 failed validation: unable t... | inventory drop snapshot_date -> WhsizingError: canonical inventory in ... failed validation | sku_master weight as list -> WhsizingError: canonical sku_master failed schema validation (16/16 cases raise WhsizingError, none ACCEPTED)
    ```

## Audit rounds

### Build (before round 0)

The engineer addressed F3c open issues 1 and 2.

- **Issue 1 (medium, thread-count drift).** New helper `fsum_by(df, key, cols)`: sort by key, find each key's run of rows, and sum each run with `math.fsum`. It is used for the per-order cube and weight, the per-day cube and weight, and the per-day receipt pallets.
  - Whole-column `Series.sum()` and `.mean()` calls were deliberately left unchanged.
  - Value change: `eiq.weight_per_order_kg.p95` is now 6.281, and `eiq.cube_per_order_m3.max` moved by about 1e-16 relative. Both are far inside T3.1's 0.5 % tolerance.
- **Issue 2 (low, no validation).** `load_canonical` now calls `io.canonical.validate` and uses the type-converted frames it returns. A `ColumnNotFoundError` that escapes `validate` is wrapped as `WhsizingError`.
- **Blocker reported.** In `io.canonical.validate` (F2-owned), a missing column that pandera coerces leaks a raw `ColumnNotFoundError`.
- **Test fixtures.** The test helper `write_frames` now adds the §4.1 provenance columns (`source_file`, `source_row`) to hand-built order_lines.

### Round 0: tests 37 passed, 1 failed

The spec audit returned **fail**. The proof audit returned **fail** and listed no findings and no proofs.

| Severity | Finding | Resolution (fix round 1) |
|---|---|---|
| high | Regression introduced by F3d (aggregate.py:38): the profile depended on the polars thread count and on row order again, which broke T3.7 and principle 5. `validate()` returned frames split into `thread_pool_size` chunks. A length-1 last chunk (for example 100 rows at 12 threads gives 11 × 9 + 1) computed the unit cube `l×w×h/1e9` with a different rounding from the other chunks. The T3.7 property test failed at seed 531; over 100 seeds, 4 failed at 12 threads (proofs 2-4). | **Fixed.** Three fixes. (1) `load_canonical` returns `df.rechunk()` for each validated table. (2) A wider sweep found [256, 256, 1] sort layouts at 24 and 64 threads that moved `stock.avg_units` and cover days by one ULP, so a new `fsum` helper now takes the whole-column sums in `stock_stats` and in `abc` (classify total, class_stats cube sums). (3) Parcels for 30.000000000000004 kg came out as 2 on a length-1 chunk, so `split_orders` now divides in numpy. New tests: `@example(seed=531)`, `test_T3_7_profile_identical_across_polars_thread_counts`, `test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout`, `test_parcels_use_true_division_whatever_the_chunk_layout`, and 64 threads in the slow ecom_mid test. The fix report says each test failed with its fix reverted. Confirmed in round 1 (proofs 2, 5, 6, 9). |
| medium | The new thread-count test (test_f3_ecom_mid.py:70) could not detect the dependence it targets. It only varied 1, 2 and the default on ecom_mid, whose 5000-SKU master never forms a length-1 chunk for t ≤ 64. It was also marked slow. | **Fixed.** Added the unmarked, subprocess-based `test_T3_7_profile_identical_across_polars_thread_counts` (tiny_golden shuffled, 1/12/64 threads, about 3 s). It fails with the rechunk removed. The slow ecom_mid test also runs 64 threads now. Confirmed in round 1 (proof 9). |
| low | The `ColumnNotFoundError` wrapper in `load_canonical` (aggregate.py:42) named the directory and the column but not the table. | **Fixed.** Validation runs one table at a time, and the message is `canonical <table> in <dir> failed validation: ...`. The 8-case test now matches `canonical {table}.*{column}`. Confirmed in round 1 (proof 10). |

Fix-round-1 totals: 3 fixed, 0 rejected, 0 deferred, no blockers. The fixer added one declared residual: in `abc.classify`, `share = col / total` and the cumulative sum can differ by one ULP on a length-1 last chunk or at an exact 0.80/0.95 threshold tie. No test covers this residual (see round 1, low).

### Round 1: tests 41 passed, 0 failed

The spec audit returned **fail**: every T-id passed, but a new high finding was raised. The proof audit returned **fail** and listed no findings and no proofs. No fix round followed, so all three findings are open.

| Severity | Finding | Status |
|---|---|---|
| high (new, regression from F3d) | `fsum_by` (aggregate.py:132) crashes on a 0-row frame: `bounds = list(zip([0, *ends[:-1]], ends, strict=True))` becomes `zip([0], [], strict=True)`. `build_profile` then raises a raw `builtins.ValueError` instead of a `whsizing.errors` class (§2.7). The only caller that can receive an empty frame is `_receipts_daily` (aggregate.py:164). F2 does produce such a table: its REQ rule on receipts is only a warning, even when it removes every row, and the ingest still reports `band=usable dq_score=90.0`. Before F3d, the aggregate built the same input (operating_days 562). | **Open, no fix round.** Reproduced while writing this record, end to end and with a direct call (proof 1). See open issue 1. |
| low (informational) | Declared residual in abc.py:24: `share = col / total` runs on the sorted frame, and polars divides by a reciprocal multiply except on a length-1 chunk. A probe (`sort_chunks.py`, n = 2..1399 plus 2049/4097/5000 at 1/4/12/24/64 threads) found that a length-1 chunk only ever appears last (`len1_not_last = []`), that the last row's own share is discarded by `shift(1)`, and that `cum_sum_chunked_equal = True`. No class can move. | **Open.** It is benign in every probed case, but no test covers it. |
| low (outside the F3d paths) | `docs/audit/F3c.md` still lists open issue 1 (thread-count dependence) and open issue 2 (no canonical validation) as open, although F3d closes both. | **Open, for the owner of F3c.md.** F3d may not edit that file. |

## Open issues

1. **High, inside the F3d paths, unfixed: `build_profile` crashes when canonical `receipts.parquet` has 0 rows.** `fsum_by` (src/whsizing/profile/aggregate.py:132) raises `builtins.ValueError: zip() argument 2 is shorter than argument 1` on a zero-row frame. That breaks §2.7, and it turns a dataset F2 accepts as usable (dq_score 90) into a crash. F3d introduced it; the code before F3d handled the same input. Re-confirmed on 2026-11-08 (proof 1). Suggested fix, not applied because this record may only edit `docs/audit/F3d.md`: return the empty per-key frame from `fsum_by` when `df.height == 0`. One guard in the shared helper covers all three callers. Add a test that profiles a canonical directory with an empty receipts table.
2. **Low, not covered by a test: ABC share residual (src/whsizing/profile/abc.py:24).** The share in `classify` may differ by one ULP on a length-1 last chunk, or at an exact 0.80/0.95 threshold tie. The round-1 probe found no case where a class moves at 1-64 threads.
3. **Low, outside the F3d paths: `docs/audit/F3c.md` still lists F3c issues 1 and 2 as open.** F3d closes both (proofs 2, 5, 6, 10). This is for the owner of that file.
4. **Blocker outside the F3d paths (F2, `src/whsizing/io/canonical.py`).** `validate()` leaks `polars.exceptions.ColumnNotFoundError` when the missing column is one that pandera coerces, such as `sku`, `qty_units`, `source_file` or `sku_master.weight_kg`. A missing `order_ts`, which is not coerced, is wrapped correctly. F3 works around it in `load_canonical`, but the real fix belongs in `io.canonical.validate`.
5. **Low, carried from F3c issue 3, deferred to F10.** `build_profile` writes no F3 artifact, and the CLI `profile` command is still a placeholder. `write_profile` works and is tested (`test_write_profile_artifacts`).
6. **Changes to note (not defects).**
   - Values: `eiq.weight_per_order_kg.p95` is now 6.281, and `demand_profile.json` and downstream hashes differ from F3c's, because the sums are now exact. T3.1 golden parity is intact.
   - T3.8 time: 0.74-0.75 s against 0.41-0.47 s in F3c, still far under 60 s.
   - Receipts: F3c issue 4 still applies. Without a pallets column, `receipts_pallets` is 0.0 on days without receipts and null on receipt days.

## Not applicable here and why

- **T3.8 "on the CI runner":** the 60 s budget was measured on this machine (0.74 s fresh, 0.75 s in round 1). No GitHub CI run was available to this audit.
- **Done-when "the eight charts render in the stub PDF":** the stub PDF belongs to F9. `write_profile` writes the 8 charts (`test_write_profile_artifacts`); F3d did not change the charts.
- **Real client data:** none is available here, and client data must not leave the machine. F3d was exercised on tiny_golden, small synthetic sets, the F1 ecom_mid set (1.03 M lines), ecom_mid subsets and an F2 ingest of synthetic CSVs.
- **T3.1 "equal the spreadsheet":** the reference is the G1 Python oracle and `golden_values.json`. A review of the golden values by a domain expert is outside this audit. G1d owns the test file.
- **Docker:** F3 does not depend on it. No F3 test is skipped.
- **Edits outside the F3d paths** (`io/canonical.py` for open issue 4, `cli.py` for open issue 5, `docs/audit/F3c.md` for open issue 3): not part of F3d.

## Fresh test output (run while writing this record, 2026-11-08)

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f3_*.py tests/property/test_f3_*.py -q -rA
.........................................                                [100%]
==================================== PASSES ====================================
_______________ test_T3_8_one_million_lines_profiled_under_60_s ________________
----------------------------- Captured stdout call -----------------------------
T3.8 build_profile on ecom_mid: 0.74 s
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
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-'order_ts' not in dataframe]
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
PASSED tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged
PASSED tests/property/test_f3_properties.py::test_T3_7_profile_identical_across_polars_thread_counts
41 passed in 15.60s

$ uv run pytest tests/golden/test_f3_golden.py -q        # T3.1, owned by G1d, run for reference
3 passed in 0.75s
```

The test suite passes, but no test covers open issue 1. The crash shows only on a canonical directory with 0 receipt rows:

```
$ uv run python <s>/f2_empty_receipts.py <scratchpad>/F3d_doc/e2e
ingest ok; receipts rows_out: [0]
canonical receipts.parquet rows: 0
build_profile RAISED builtins.ValueError: zip() argument 2 is shorter than argument 1
```
