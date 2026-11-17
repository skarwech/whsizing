# F3f audit record: profiling, salt-independent ABC tie-break (I6 amended)

Date of the record: 2026-11-09. Repo root `/Users/skarwech/saas_v1`. Feature F3f belongs to F3 (demand profiling, `description.md` lines 708-741, tests T3.1 to T3.8). It owns `src/whsizing/profile/abc.py`, `tests/unit/test_f3_*.py` and `tests/property/test_f3_*.py`; `tests/golden/test_f3_golden.py` is only re-run. The binding rule is `docs/INTERPRETATIONS.md` I6 (amended). The defect it removes was found in `docs/audit/F8a.md` (sizing results moved with the anonymisation salt).

## Final verdict: pass_with_issues

- All 72 F3 tests pass in the fresh run, and both auditors in both rounds returned pass_with_issues with 0 failed tests; the ABC classes, the `abc` block of `demand_profile.json` and the S0/S1/S2 TCO no longer move with the salt (property test, end-to-end test and audit probes below).
- Not clean: the suite outside F3 is red. Two strict-xfail G1 golden tests now XPASS and fail (reproduced in this run: `2 failed, 16 passed`), and they sit in `tests/golden/**`, which F3f may not edit. Also open: ULP-level float noise across salts in `aggregate.py`, a null-weight versus 0.0 divergence from the oracle, and one new low finding (a hashed-id-dependent per-SKU label when SKUs tie on the five I6 attributes but differ in another) with no fix round after it.

## What F3f changed

- `src/whsizing/profile/abc.py` (82 lines): new `rank(skus, by)`, used by `classify`. Sort key: `by`, then `lines, units, avg_stock, unit_cube_m3, weight_kg` (those present in the frame, all descending, nulls last), then `sku` ascending. The hashed sku id only orders SKUs identical in every attribute. The same chain applies to the by-cube-movement and by-stock-cube classes. `classify` still works on frames that lack some tie columns. `build.py` is untouched and gets the new order through `classify`.
- New test files: `tests/unit/test_f3_abc_tiebreak.py` (114 lines, 8 tests), `tests/unit/test_f3_abc_salt_e2e.py` (79 lines, 1 test), `tests/property/test_f3_abc_salt.py` (61 lines, 1 test). The first build reported 9 new tests; the 10th (null versus zero weight) was added in fix round 1.
- Schema changes: none. `pyproject.toml` / `uv.lock`: untouched. No commits. No new package needed.
- Null weight: the engine ranks a null weight after every known weight, 0.0 included. The oracle (`tests/golden/demand.py` `ABC_ORDER`) fills null with 0.0 and then falls back to the hashed sku. See "Open issues".

## Tests

The task has no T-id of its own; the ABC tie-break tests are filed under T3.2 and the salt tests under T3.7. Files: U1 = `tests/unit/test_f3_abc_tiebreak.py`, U2 = `tests/unit/test_f3_abc_salt_e2e.py`, U3 = `tests/unit/test_f3_profile.py`, U4 = `tests/unit/test_f3_ecom_mid.py`, P1 = `tests/property/test_f3_abc_salt.py`, P2 = `tests/property/test_f3_properties.py`, G = `tests/golden/test_f3_golden.py`. All statuses are from the fresh run in this record. 0 skipped, 0 failed.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T3.1 | G `test_T3_1_profile_stats_equal_golden_spreadsheet` | pass | Profile stats on the golden data equal the spreadsheet values; the I6 change leaves the golden values unchanged. |
| T3.1 | G `test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock` | pass | Dead-stock numbers equal the oracle on a copy of the golden data that has dead stock. |
| T3.1 | G `test_T3_1_trend_equals_the_oracle_on_a_two_month_copy` | pass | The trend numbers equal the oracle on a two-month copy. |
| T3.2 | U1 `test_T3_2_ties_on_lines_only_are_broken_by_units_not_by_sku` | pass | Two SKUs tied on lines are ordered by units, not by id. Fails on the old `(lines, sku)` sort. |
| T3.2 | U1 `test_T3_2_ties_on_lines_and_units_follow_stock_then_cube_then_weight` | pass | Ties on lines and units are broken by avg_stock, then unit cube, then weight, one rung at a time. |
| T3.2 | U1 `test_T3_2_a_rung_only_counts_when_every_rung_above_ties` | pass | Rung order lines, units, avg_stock, cube, weight, sku: each row beats the next on one rung only, and a lower rung never overrides a higher one. |
| T3.2 | U1 `test_T3_2_unknown_weight_ranks_last_and_identical_skus_fall_back_to_sku_ascending` | pass | A null weight ranks last; SKUs identical in every attribute are ordered by sku ascending. |
| T3.2 | U1 `test_T3_2_class_of_tied_skus_follows_the_attributes_not_the_id` | pass | Lines 80/10/10/5: the tied SKU with more units is A and the other is B, whatever the ids. |
| T3.2 | U1 `test_T3_2_other_orderings_break_ties_by_the_same_chain` | pass | The by-cube-movement and by-stock-cube classes use the same tie chain. |
| T3.2 | U1 `test_T3_2_abc_result_is_unchanged_by_swapping_two_skus_ids_in_a_tie` | pass | `abc()` (shares and Pareto) is equal after the id labels of two tied SKUs are swapped. |
| T3.2 | U1 `test_T3_2_null_weight_vs_zero_weight_is_ordered_by_attribute_under_either_id_assignment` | pass | Added in fix round 1. A null-weight and a 0.0-weight SKU, identical otherwise, come out in the same order under both id assignments (`[c, zero_id, null_id]`). Fails if the weight is filled with 0.0. |
| T3.2 | U3 `test_T3_2_abc_shares_sum_to_one_and_class_A_line_share[golden]` and `[small_synth]` | pass | ABC shares sum to 1 and class A line share is at least 0.8 - eps (the spec T3.2), on two datasets. |
| T3.2 | U3 `test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines0-expected0]` and `[lines1-expected1]` | pass | The class after an exact 80 % or 95 % cumulative tie follows I6 (cum < 0.80 is A, cum < 0.95 is B). The name has no `test_T3_2_` prefix; it predates F3f. |
| T3.3 | U3 `test_T3_3_monthly_indices_average_to_one` | pass | Monthly indices average to 1. Untouched by F3f. |
| T3.4 | U3 `test_T3_4_intraday_shares_sum_to_one_per_weekday[golden]` and `[small_synth]` | pass | Intraday shares sum to 1 per weekday. Untouched by F3f. |
| T3.5 | U3 `test_T3_5_shipment_split_400kg_order_is_pallet` | pass | An order of 400 kg is a pallet order. Untouched by F3f. |
| T3.6 | U4 `test_T3_6_operating_days_exclude_sundays_in_ecom_mid` | pass | Operating-day detection excludes Sundays in `ecom_mid`. Untouched by F3f. |
| T3.7 | P1 `test_T3_7_abc_classes_do_not_depend_on_the_sku_ids` | pass | Hypothesis (200 examples, engineer-reported): random id bijections leave class sizes, line shares and the multiset of `(lines, units, avg_stock, cube, weight)` per class identical, for the three ABC orderings and the Pareto. Fails on the old order. |
| T3.7 | U2 `test_T3_7_profile_json_does_not_depend_on_the_anonymisation_salt` | pass | One synthetic ecom_mid (120 d, 250 SKUs) ingested with two salts gives equal `demand_profile.json` after removing `dataset_hash`: `abc` exact, other floats at rel 1e-12 (see Open issues). Fails on the old order (`abc.by_lines.B/C.cube_share` differ). |
| T3.7 | P2 `test_T3_7_shuffling_rows_leaves_profile_unchanged` | pass | Spec T3.7: shuffling rows leaves the profile unchanged. Untouched by F3f. |
| T3.7 | U4 `test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile` | pass | The same on `ecom_mid`, bit-identical. |
| T3.7 | P2 `test_T3_7_profile_identical_across_polars_thread_counts` and U4 `test_T3_7_profile_json_identical_across_polars_thread_counts` | pass | The profile does not change with the Polars thread count. |
| T3.7 | U3 `test_T3_7_whole_column_float_sums_do_not_depend_on_the_chunk_layout` | pass | Whole-column float sums do not depend on the chunk layout. |
| T3.8 | U4 `test_T3_8_one_million_lines_profiled_under_60_s` | pass | `build_profile` runs under 60 s; this run printed `T3.8 build_profile on ecom_mid: 1.08 s` (audits: 0.79 s and 0.84 s). Local machine, not the CI runner. |

The other 44 passed items of the run (`test_f3_profile.py` edge cases, I71, I72, R10, zero-row frames and so on) are listed in the fresh output below.

## Proofs

All captured by the auditors during the audit, in scratch scripts outside the repo (`audit_F3f/` in the session scratchpad), except where marked engineer-reported. Excerpts are as recorded in the audit history; some were clipped there and are not completed here.

1. **End to end, 3 salts give an identical `abc` block; the old order does not (round 0).**
   - Command: `uv run python <scratchpad>/audit_F3f/p3.py` (ecom_mid, seed 11, 400 SKUs, 120 days, ingest to profile).
   - Output: `abc blocks identical across 3 salts (exact): True` / `A/B/C n_skus: {'A': 75, 'B': 162, 'C': 163} line_share A: 0.8004` / `per-class attribute multisets identical: True` / `OLD order: abc blocks identical across salts: False`.
2. **The sizing result no longer moves with the salt (round 0).**
   - Command: `uv run python <scratchpad>/audit_F3f/salt_run.py` (F8 small ecom_mid project, 4 salts).
   - Output: `RESULT saltA {'S0': 479408.17, 'S1': 825102.81, 'S2': 860530.06}` (same for saltB, C, D); `all TCO bit-identical across salts: True`. Before the fix, S0 moved from 479399.93 to 479634.33 (`docs/audit/F8a.md`).
3. **Hand-computed ABC example agrees with the code (round 0).**
   - Command: `p1.py` and `p3.py`.
   - Output: lines 50/30/10/5/5 give classes `[('a',50,'A'),('b',30,'A'),('c',10,'B'),('d',5,'B'),('e',5,'C')]` (cumulative before: 0, .5, .8, .9, .95, so 80 % is B and 95 % is C); `pareto hand check: True 0.5 1.0` (points at 1/2/3 % are 0.025/0.05/0.075, at 20 % and 100 % they are 0.5 and 1.0).
4. **Tie-break chain hand-computed (round 1).**
   - Command: `uv run python <scratchpad>/audit_F3f/p1.py`.
   - Output: lines 40 and 10x7 (total 110), tied SKUs ordered by units descending; cumulative before .364, .455, .545, .636, .727 are A, .818 and .909 are B: `[('s0',5,'A'),('s7',7,'A'),('s6',6,'A'),('s5',5,'A'),('s4',4,'A'),('s3',3,'A'),('s2',2,'B'),('s1',1,'B')]`; the assert against the hand-computed dict passed.
5. **The new tests detect the old behaviour and rung-level mutants (round 0 and round 1).**
   - Command: `PYTHONPATH=<scratchpad>/audit_F3f uv run pytest -p oldrank tests/unit/test_f3_abc_tiebreak.py tests/unit/test_f3_abc_salt_e2e.py tests/property/test_f3_abc_salt.py -q` (round 0); `MUT=<name> ... -p mutplug` (round 1).
   - Output: round 0 `9 failed in 15.49s` (7 tiebreak, 1 e2e, 1 hypothesis) under the old `[by, sku]` sort. Round 1: `MUT=old: 9 failed` on tiebreak + property, e2e under the old order `1 failed`; `noweight: 4 failed, 5 passed`; `swap` (unit cube and avg_stock): `1 failed, 8 passed`; `asc_units: 3 failed`; `nonulls: 2 failed`; `noavgstock: 2 failed`. Round 0 single-rung mutants: units and avg_stock swapped 1 failed, weight dropped 3 failed, nulls first 1 failed, sku descending 1 failed.
6. **The engine order equals the golden oracle's `ABC_ORDER` on 300 random tie-heavy frames, up to the id order inside a null/0 weight pair (round 1).**
   - Command: `uv run python <scratchpad>/audit_F3f/p1.py`.
   - Output: `attr-order mismatches engine vs oracle: 0`; the auditor's probe on frames with null/0/1 weights agreed on `(lines, units, avg_stock, unit_cube)` in 300 of 300 cases.
7. **Per-SKU class, keyed by every non-id attribute, is identical across 4 salts on three synthetic projects (round 1).**
   - Command: `uv run python <scratchpad>/audit_F3f/p3.py ecom_mid 120 400 ...`, then `b2b_cases 100 600` and `ecom_mid 100 1500`.
   - Output: `0..3 400 {'A': 75, 'B': 162, 'C': 163}`; `per-SKU (all-attribute signature, abc) multiset identical across 4 salts: True; differing signature rows vs salt 0: 0`; same True / 0 for b2b_cases (`{'A':112,'B':236,'C':252}`) and ecom_mid 1500 SKUs (`{'A':181,'B':582,'C':737}`). The check found 0 differing rows on these projects; the case of open issue 4 was shown by a separate probe (`p2.py`, round 1).
8. **Edge cases (round 0 and round 1).**
   - Command: `p1.py`, `p4.py`.
   - Output: an empty SKU frame and a single all-zero SKU work (zero movement is C, `n_skus=1`, A/B 0); a frame with only the 4 contract columns classifies by lines then sku (`['a','b','c']`); nulls in avg_stock / unit cube / units rank last; a 1-SKU frame gives `A stats n_skus=1 line_share=1.0`.
9. **Static checks clean on the four F3f files (round 0).**
   - Command: `uv run ruff check <4 files> && uv run ruff format --check <4 files> && uv run pyright <4 files>`.
   - Output: `All checks passed!` / `4 files already formatted` / `0 errors, 0 warnings, 0 informations`. Round 1: `7 files already formatted`, pyright `0 errors, 0 warnings`.
10. **The suite is red only through the G1 hand-off tests (round 1).**
    - Command: `uv run pytest -q -m 'not bench and not slow'`.
    - Output: `2 failed, 1326 passed, 2 skipped, 37 deselected in 195.28s`; both failures `[XPASS(strict)]`.

Not auditor proofs, engineer-reported at build: old-code check by a scratch plugin patching `rank` to the old sort (e2e diff `abc.by_lines.B.cube_share 0.15410 vs 0.15415`, plus the C class); the hypothesis test was checked with 3 hypothesis seeds; a wider run `1240 passed, 3 failed` (tests/unit, golden, property).

## Audit rounds

Two audit rounds with one fix round between them. Each round had a spec auditor and a proof auditor. The proof auditor returned `pass_with_issues`, 71 passed (round 0) and 72 passed (round 1), 0 failed, and recorded no findings and no proofs, so everything below comes from the spec auditor. Some finding texts and evidence strings were clipped in the audit history.

**Round 0 (spec: pass_with_issues, 71 passed, 0 failed; T3.1 to T3.8 all pass)**

| # | severity | finding | resolution |
|---|---|---|---|
| 0.1 | medium | `tests/golden/test_g1_abc_tiebreak.py:111` and `tests/golden/test_g1_finance_register.py:301`: two strict xfails now XPASS(strict) and count as failures. The XPASS confirms the engine follows the oracle's I6 chain. | deferred (hand-off to the G1 owner: remove the two `xfail` decorators); F3f may not edit `tests/golden/**`. |
| 0.2 | low | `abc.py:23`: the engine ranks a null weight after 0.0, the oracle fills null with 0.0 and falls to the salt-dependent sku. Class sizes and shares are unaffected. | deferred as intentional; see fix round. |
| 0.3 | low | `aggregate.py` `series_stats` (`np.mean` / `np.std` over arrays in hashed `order_id` order) leaves ULP-level differences across salts; max relative difference 1.69e-15 across `result.json` / `finance.json`, no non-float difference. Outside F3f paths. | deferred (F3 aggregate owner: sort or `math.fsum` before the reduction). |

**Fix round 1:** no finding was fixed in code. 0.1 and 0.3 were deferred as out of the F3f paths. For 0.2 the engineer kept the engine behaviour and added `test_T3_2_null_weight_vs_zero_weight_is_ordered_by_attribute_under_either_id_assignment`; with `weight_kg.fill_null(0.0)` patched in it fails (`1 failed, 7 passed`), with `abc.py` restored it passes (`8 passed`).

**Round 1 (spec: pass_with_issues, 72 passed, 0 failed; T3.1 to T3.8 all pass)**

| # | severity | finding | resolution |
|---|---|---|---|
| 1.1 | medium | Same as 0.1, still unresolved. Also the stale bullet "Engine and I6 (G1g): classify still ties by sku only" is still at `docs/INTERPRETATIONS.md:871` (verified in this record). | open, G1 owner. |
| 1.2 | low | Same as 0.2, unresolved and intentional; pinned by the new test. Probe of 300 random frames: engine and oracle agree on the attribute order, they differ only in the id order inside the null/0 pair. | open, deferred (optional alignment of the oracle). |
| 1.3 | low | Same as 0.3. The auditor did not re-measure 1.69e-15 and only confirmed `aggregate.py:267-269` is unchanged. | open, F3 aggregate owner. |
| 1.4 | low (new) | I6 says SKUs identical in the five attributes are "interchangeable", but the per-SKU `abc` label is read downstream together with `storage_class` (`engine/labor.py:105-108`, `throughput.py:259`, `storage.py:241`). Two SKUs tied on the five attributes but different in another attribute (hazmat, dimensions with the same volume, temperature class, units_per_pallet, last_stock) still get a hashed-id-dependent label when a class boundary falls between them. Probe: ids `(a,b)` gives `[('a', hazmat=True, 'A'), ('b', hazmat=False, 'B')]`, ids `(b,a)` gives `[('a', False, 'A'), ('b', True, 'B')]`. Class sizes and shares are unaffected. | open; no fix round followed round 1. |

## Open issues

1. **Suite red from the G1 hand-off (medium, G1 owner).** Re-run in this record: `uv run pytest tests/golden/test_g1_abc_tiebreak.py tests/golden/test_g1_finance_register.py -q` gives `2 failed, 16 passed in 1.36s`; the failures are `test_T1_5_engine_abc_follows_the_same_tie_break_chain` (decorator at line 111) and `test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7` (decorator at line 301 of `test_g1_finance_register.py`), both `[XPASS(strict)]`. Fix: drop the two `@pytest.mark.xfail(strict=True, ...)` decorators and the stale `docs/INTERPRETATIONS.md:871` bullet. Not done by F3f (not its files).
2. **Salt noise in `aggregate.py` (low, F3 aggregate owner).** `demand_profile.json` is not bit-identical across salts. Seen by the engineer on ecom_mid 120 d, 600 SKUs, seed 7: `eiq.cube_per_order_m3.cv = 1.091043437182274` versus `1.0910434371822737` (1 ULP). The e2e test T3.7 compares floats outside `abc` at rel 1e-12 and `abc` exactly, so it does not cover bit-identity.
3. **Null weight versus 0.0 weight (low).** Engine: null after 0.0. Oracle `tests/golden/demand.py` `ABC_ORDER`: null filled with 0.0, then the hashed sku. Class sizes and shares are the same; only the per-SKU label of that pair can differ. Optional fix on the G1 side.
4. **Label depends on the id when SKUs tie on the five attributes but differ in another (low, new in round 1, unresolved).** The `abc.py` comment and the I6 text say such SKUs are interchangeable, which is true for class sizes and shares but not for the downstream per-SKU label. A possible fix would add a further salt-independent rung (not designed or tested here), or I6 would state the limit.
5. **Not reproduced here, recorded in the round-1 fix blockers as seen by the runtime auditor (not F3f).** `tests/e2e/test_f10_cli_e2e.py::test_T10_1_rerun_of_a_staged_run_is_a_config_error` and `::test_T10_3_exit_5_failed_integrity_check_builds_nothing` failed only in a full-suite run (`AttributeError: 'str' object has no attribute 'id'`) and passed alone; an F10 isolation matter. The later round-1 auditor full run showed only the 2 XPASS failures.
6. **Build-time failures outside F3f, not re-checked in this record.** The engineer listed `tests/unit/test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[ruff-check]` (E501 at `tests/property/test_f9_formats.py:116`) and `tests/unit/test_f9_diagram.py::test_T9_6_scale_is_two_pixels_per_metre` (ValueError). The round-1 full run (`2 failed, 1326 passed`) did not show them, so they were probably fixed since; this record did not verify that.

## Not applicable here and why

- **Docker / container run:** F3f is a pure-Python change; no image was built or run.
- **Real client data:** none used and it must not leave the machine. All evidence is on the golden case, `small_synth` and synthetic `ecom_mid` / `b2b_cases` projects. Whether real exports contain the tie patterns of open issue 4 is unknown.
- **CI runner for T3.8:** the 60 s limit is stated for the CI runner; it was measured on this machine only (1.08 s here, 0.79 s and 0.84 s in the audits). GitHub CI was not run.
- **Domain expert / business lead review:** the amended I6 rule is binding from `docs/INTERPRETATIONS.md`; no expert sign-off was part of this feature, and the "eight charts render in the stub PDF" part of the F3 done-when belongs to the charts feature, not to F3f.
- **Skipped tests:** none; `pytest.mark.skip` is not used by any F3f test (0 skipped in the fresh run).

## Fresh test output

Command, run from `/Users/skarwech/saas_v1` on 2026-11-09 at the time of writing:

```
uv run pytest tests/unit/test_f3_*.py tests/property/test_f3_*.py tests/golden/test_f3_golden.py -q -rA
```

Trimmed: the captured log lines (ingest warnings, I71 receipts warnings) are omitted; the full `PASSED` list and the summary line are kept.

```
........................................................................ [100%]
T3.8 build_profile on ecom_mid: 1.08 s
=========================== short test summary info ============================
PASSED tests/unit/test_f3_abc_salt_e2e.py::test_T3_7_profile_json_does_not_depend_on_the_anonymisation_salt
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_ties_on_lines_only_are_broken_by_units_not_by_sku
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_ties_on_lines_and_units_follow_stock_then_cube_then_weight
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_a_rung_only_counts_when_every_rung_above_ties
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_unknown_weight_ranks_last_and_identical_skus_fall_back_to_sku_ascending
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_class_of_tied_skus_follows_the_attributes_not_the_id
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_other_orderings_break_ties_by_the_same_chain
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_abc_result_is_unchanged_by_swapping_two_skus_ids_in_a_tie
PASSED tests/unit/test_f3_abc_tiebreak.py::test_T3_2_null_weight_vs_zero_weight_is_ordered_by_attribute_under_either_id_assignment
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
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-find column "order_ts"]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-find column "sku"]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-find column "qty_units"]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-coerce 'qty_units']
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-'order_ts' to have type]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[order_lines-<lambda>-'sku' contains null]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[inventory-<lambda>-'sku' contains null]
PASSED tests/unit/test_f3_profile.py::test_invalid_canonical_table_raises_whsizing_error[sku_master-<lambda>-find column "weight_kg"]
PASSED tests/unit/test_f3_profile.py::test_I72_missing_required_column_has_one_wording_in_both_layers[order_lines-order_ts]
PASSED tests/unit/test_f3_profile.py::test_I72_missing_required_column_has_one_wording_in_both_layers[order_lines-sku]
PASSED tests/unit/test_f3_profile.py::test_I72_missing_required_column_has_one_wording_in_both_layers[order_lines-qty_units]
PASSED tests/unit/test_f3_profile.py::test_I72_missing_required_column_has_one_wording_in_both_layers[sku_master-weight_kg]
PASSED tests/unit/test_f3_profile.py::test_I72_missing_required_column_has_one_wording_in_both_layers[inventory-snapshot_date]
PASSED tests/unit/test_f3_profile.py::test_load_canonical_corrupt_parquet_is_a_whsizing_error
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
PASSED tests/unit/test_f3_profile.py::test_I71_receipts_outside_the_shipped_window_are_absent[stamps0-period0]
PASSED tests/unit/test_f3_profile.py::test_I71_receipts_outside_the_shipped_window_are_absent[stamps1-period1]
PASSED tests/unit/test_f3_profile.py::test_I71_receipts_outside_the_shipped_window_are_absent[stamps2-period2]
PASSED tests/unit/test_f3_profile.py::test_I71_receipts_outside_the_shipped_window_are_absent[stamps3-period3]
PASSED tests/unit/test_f3_profile.py::test_I71_receipts_touching_the_window_keep_their_columns
PASSED tests/unit/test_f3_profile.py::test_zero_row_inventory_profiles_like_no_inventory
PASSED tests/unit/test_f3_profile.py::test_a_single_line_dataset_profiles_and_writes_its_artifacts
PASSED tests/unit/test_f3_profile.py::test_zero_row_sku_master_makes_every_sku_an_orphan_without_dims
PASSED tests/unit/test_f3_profile.py::test_aggregation_helpers_accept_zero_row_frames
PASSED tests/unit/test_f3_profile.py::test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines0-expected0]
PASSED tests/unit/test_f3_profile.py::test_abc_class_after_an_exact_80_or_95_percent_tie_follows_I6[lines1-expected1]
PASSED tests/property/test_f3_abc_salt.py::test_T3_7_abc_classes_do_not_depend_on_the_sku_ids
PASSED tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged
PASSED tests/property/test_f3_properties.py::test_T3_7_profile_identical_across_polars_thread_counts
PASSED tests/golden/test_f3_golden.py::test_T3_1_profile_stats_equal_golden_spreadsheet
PASSED tests/golden/test_f3_golden.py::test_T3_1_dead_stock_equals_the_oracle_on_a_copy_with_dead_stock
PASSED tests/golden/test_f3_golden.py::test_T3_1_trend_equals_the_oracle_on_a_two_month_copy
72 passed in 28.49s
```

Companion run for open issue 1 (same day, the G1 files that hold the two XPASS tests):

```
uv run pytest tests/golden/test_g1_abc_tiebreak.py tests/golden/test_g1_finance_register.py -q
[XPASS(strict)] G1g: the oracle ABC order follows I6 as amended, F3 abc.py classify() still ties by sku only (S0 labor differs by 0.006 %); see test_g1_abc_tiebreak.py
FAILED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_engine_abc_follows_the_same_tie_break_chain
FAILED tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7
2 failed, 16 passed in 1.36s
```
