# F6c audit: Sizing engine, labor, FTE by activity, shifts and annual series

## Verdict: pass_with_issues

All F6c acceptance tests (T6.2, T6.5, T6.6, T6.7, T6.8 and T6.10) pass: 26 passed, 0 failed, 0 skipped. All 257 golden S0/S2 labor keys match to 7.3e-16, and the auditors' independent recomputations match in both inbound modes, on two synthetic datasets, in all 3 families and 3 worlds.
The verdict stays below `pass` because no fix round followed the round-2 audits. One new medium finding (receipts mode with `units_in* = 0` silently drops decant labor) and four new low findings are open. Two medium integration/expert items and five low register items were deferred because they are outside F6c's paths. Both round-2 auditors returned pass_with_issues.

Scope: F6c (design-day hours and heads per activity, shift split and roster, annual series, core FTE, P50 core heads and temp hours, `LaborResult`). Storage/throughput (F6a/F6b), area (F6d), queue (F6e) and `size_scenario` (F6z) are out of scope. Schema changes: none (`schema_changes: []`). `src/whsizing/engine/inputs.py` was not edited. No package was needed.

Files: `src/whsizing/engine/labor.py` (351 lines now; 281 at build), `src/whsizing/engine/shifts.py` (291 lines now; 283 at build; split out because labor.py went over 400 lines), `tests/unit/test_f6_labor.py`, `tests/property/test_f6_labor_properties.py`, `tests/golden/test_f6_labor_golden.py`.

Public API (from `whsizing.engine.labor`, not from `whsizing.engine`; see open issue 12): `labor_days(inp, daily, lines) -> LaborDays` once per scenario (it does not depend on the world), `size_labor(inp, tp, days) -> LaborWorld` once per world, and `labor_result({w: LaborWorld}) -> LaborResult`. `LaborWorld` carries the roster, total hours, per-activity annual hours with roles, and temp hours for F6d (amenities) and F7 (opex).

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T6.2 | `tests/golden/test_f6_labor_golden.py::test_T6_2_labor_hours_heads_equal_golden` | pass | Built end to end from `tiny_golden` (F3 build_tables, F4 design day, storage, throughput, `labor_days`, `size_labor`) for S0 and S2 in every world. Asserts that there are exactly 257 golden keys matching `^(S0\|S2)\.labor\.` (S0 123, S2 134), that none is missing and that each is within 0.5 %. Worst relative error 7.3e-16 (`S2.labor.put_away.annual_hours.y1`). The golden values come from the independent oracle (`build_golden.py` / `oracle.py`), not from engine code. Mutations killed: no floor-1 (M3), growth exponent t-1 (M4), derived inbound without /gf (M5), annual = design-day hours x n_op (mut_plugin2). |
| T6.2 | `tests/golden/test_f6_labor_golden.py::test_T6_2_labor_result_typ_matches_trace` | pass | `LaborResult` typ values equal golden (total hours, roster, core_fte.y3, temp_hours.y5, hours per activity), lo < typ < hi, the 12 roles come from `labor_standards.yaml` (I33), S0 has no decant, and the single shift is 06:00-13:30. Also fails under mut_plugin2. |
| T6.2 | `tests/golden/test_f6_labor_golden.py::test_T6_2_labor_trace_inputs_resolve` | pass | Every input of every `*.labor.*` trace node in all 3 worlds is a catalog param or constant, a node of the same tracer and world, or a `data:` leaf that `bad_data_refs` resolves against the real frames and objects (a `daily`, `lines` or `sku` root must name exactly one real column; a `design_day`, `basis` or catalog root must be a real attribute path). Also asserts that returns uses `daily.lines` + `returns_rate`, not `daily.return_lines` (I9), and that derived receiving lists `growth_rate` and `horizon_years` (I22). Until round 2 it only checked the `data:` prefix; it now fails on the old code with exactly the leaves the auditors listed. |
| T6.5 | `tests/property/test_f6_labor_properties.py::test_T6_5_more_lines_never_fewer_labor_hours_or_fte` | pass | Hypothesis (40 examples, 3 families). Design flows x k (k in [1, 3]), history orders repeated m times, an extra line on some orders. Per-activity hours, heads, shift heads, roster and annual hours, and total hours, heads, annual hours, core FTE and core heads never fall. Mutation `fte_inv` (core_fte inverted) is killed. **Caveat:** packing_S is exempt when an extra line turns S orders into ML orders (I15 class shift), and the roster through the I19 floor; the round-1 spec auditor noted the exemption applies whenever `extra` is non-empty, not only when packing_S actually loses its floor head. core_fte and total heads (the spec's "FTE") are always checked. Added in round 1. |
| T6.6 | `tests/property/test_f6_labor_properties.py::test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged` | pass | Hypothesis (40 examples over manual_p2p, cube_asrs, amr_gtp). Doubles every workload (design day, inbound, hourly lines, history orders duplicated under new ids, daily parcels and pallets) and every rate F6c divides by (9 labor standards, pick, port, station and decant rates). Hours, heads, roster, annual hours, shift heads, total heads, core FTE, temp hours and core heads stay equal at rel 1e-9, and each workload doubles. Killed by mut_plugin (shelving picking at an un-doubled rate) and `pick_daily_const`. **Caveat (round-0 spec audit):** a mis-scaled indirect share would also pass, because the ratio cancels. |
| T6.7 | `tests/property/test_f6_labor_properties.py::test_T6_7_labor_outputs_non_negative_and_worlds_ordered` | pass | Every `LaborResult` Range is finite, >= 0 and lo <= typ <= hi; workloads and shift rows are >= 0; total hours in the lo (pessimistic) world >= typ >= hi. Killed by `neg_floor` / M6 (an unstaffed shift gets negative heads) and `temp_nomax` (temp hours without max(0, ...)). **Caveat (round-1 proof audit):** lo <= typ <= hi holds by construction through `to_range` (min/max), so only the non-negativity and world-ordering checks can fail. Added in round 1. |
| T6.8 | `tests/property/test_f6_labor_properties.py::test_T6_8_row_order_does_not_change_labor` | pass | Shuffles the SKU frame, the daily series and the shipped lines (order ids repeat across days, so some orders span two dates) and asserts an exactly equal `LaborWorld`. Killed by `.min()` -> `.first()` (M1). The round-2 proof auditor checked that the generator's days stay inside the daily series, so the new absent-date check does not mask the test. Added in round 1. |
| T6.10 | `tests/golden/test_f6_labor_golden.py::test_T6_10_annual_hours_below_design_day_times_operating_days` | pass | Golden S0 and S2, years 1-5: 0 < annual_hours.y_t < design-day total hours x 252, and y1 < 0.7 x that bound (S0: 1128 vs 1997). Catches both D* x 365 and D* x 252 x (1+g)^t. Killed by mut_plugin2. Golden is single-shift only; on synthetic data the bound held in all 12 runs (2 datasets x 2 modes x 3 families), e.g. b2b S1 derived 14489 < 20677. |
| T6.1, T6.3, T6.4 | none | not_applicable | Storage (F6a), area and docks (F6d), Erlang-C (F6e). |
| T6.9, T6.11 | none | not_applicable | Manifest rerun and "every result.json number has a TraceNode" belong to F6z/F8; `size_scenario` and `result.json` do not exist yet. F6c's part (trace resolution of labor nodes) is covered by `test_T6_2_labor_trace_inputs_resolve`, but `ShiftRow.start_hour/end_hour` are untraced (open issue 7). |

Supporting tests not tied to a T-id (`tests/unit/test_f6_labor.py`, 13 functions, 18 cases, all pass):

- **Formulas:** `test_design_day_hours_and_heads_per_activity`, `test_annual_series_from_daily_workloads`, `test_core_heads_and_temp_hours`, `test_cube_decant_and_picking_zones`, `test_amr_picking_at_station_rate`, `test_labor_result_ranges_and_shift_table`.
- **Shifts:** `test_two_shift_split_and_roster` (receiving 1.6 h -> shift hours (1.4, 0.2) -> heads (1, 1) -> roster 2.12), `test_one_shift_reduces_to_I19`, `test_fractional_outbound_lag_splits_each_hour` (lag 0.5 = mean of lag-0 and lag-1 profiles; 2.5 = mean of lag 2 and 3; profile sums to 1).
- **Receipts mode:** `test_receipts_mode_uses_the_daily_receipts` (receiving 12/14 x PFD, put_away 12/13, receipt_check 35/45, cube decant 150/90, null-pallet fallback 7/14, missing-column error; also runs the trace resolver). It replaced the build's `test_receipts_mode_scales_inbound_by_daily_receipts` in round 1.
- **Errors and boundaries:** `test_errors`; `test_invalid_shift_config_is_a_config_error[*]` (5 cases: shifts_per_day 0, hours_per_shift 0 and -7, utilisation 0, paid_hours_per_person_day 0); `test_inconsistent_inputs_are_rejected` (bad hourly profile, empty or mismatched lines, lines on an absent date, NaN/negative/null daily counts, qty_units 0/-2/None/nan/inf, Datetime date); `test_an_order_over_two_dates_counts_on_its_first_date` (I1).

## Proofs (captured by the auditors during the audit)

These proofs were captured by the auditors during rounds 0-2. `golden_err.py` (Proof 1) and `adv3.py` (Proof 10) were also re-run while writing this record (2026-11-09) with the same output; the others were not re-run. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F6c/`, written `$S` below. All commands ran from `/Users/skarwech/saas_v1`, with `PYTHONPATH=/Users/skarwech/saas_v1` where shown. Parts of the audit history are cut off; they are marked "(clipped)".

1. **The engine equals the independent golden oracle on all 257 S0/S2 labor keys, and the auditor's hand formulas equal the engine.** Hand formulas: hours = workload/std x 1.12, heads = h/(7 x 0.85), roster = max(1, h/(7.5 x 0.85)) x 1.06, indirect = 0.12 x direct, core_fte = annual/(1607 x 0.85). (Round-0 spec audit; golden_err.py in rounds 1-2 and re-run for this record.)
   Command: `uv run python $S/check_golden.py; uv run python $S/golden_err.py`
   ```
   S0 roster hand 11.660000000000004 engine 11.66 golden 11.660000000000004
   S0 keys 123 max rel err 7.302785504769097e-16
   S2 keys 134 max rel err 7.302785504769097e-16
   worst hand-vs-engine rel err 5.712849128728169e-16
   n keys 257 max rel err (7.302785504769097e-16, 'S2.labor.put_away.annual_hours.y1', 9.729749494847939, 9.729749494847946)
   ```

2. **An independent recompute of every daily workload, base hours, shift split, roster, annual series, P50, core heads, temp hours and core FTE matches the engine on synthetic data**, in 3 families x 3 worlds, in derived and receipts mode, on b2b and ecom_mid (981,910 lines, example_basis 2 x 7 h). (Round-0 proof audit with `e2e.py`; rounds 1-2 with `e2e_v2.py` / `e2e2.py`.)
   Command: `for d in b2b ecom_mid; do for m in derived receipts; do uv run python $S/e2e_v2.py $S/$d $m; done; done`
   ```
   b2b derived: worst rel err 5.11e-16; b2b receipts: 2.18e-16 (S1 typ p50=18.97 temp_y1=9903 ann_y1=14519 roster=56.44)
   ecom_mid derived: 3.83e-16 (S0 typ roster=42.64); ecom_mid receipts: 2.03e-16 (S1 typ temp_y1=7606 ann_y1=18311)
   ```
   The round-0 proof audit also ran `e2e.py $S/b2b derived 3` with finance.horizon_years=3 and projection.horizon_years=5: the annual, core_fte and temp lists had 3 entries and derived daily inbound still divided by (1.04)^5 (I41/I22). Golden cannot check this because both horizons are 5 there.

3. **The multi-shift split matches an independent hand computation** (lagged intraday profile, flat inbound window, floor 1 per staffed shift, roster x 1.06). (Round-0 spec audit, 3 x 8 h; round-2 spec audit, fresh toy with 3 x 6 h, lag 1.5 h, 3 operating days + 1 non-operating, odd median.)
   Command: `uv run python $S/check_shifts.py; uv run python $S/r3/hand.py`
   ```
   windows ((6.0, 14.0), (14.0, 22.0), (22.0, 6.0))
   picking shift hours engine (11.856000000000002, 8.944000000000003, 0.0) hand [11.856, 8.944, 0.0]
   picking roster engine 3.2423529411764713 hand 3.242352941176471
   days hours [3.88594745 3.74081581 4.04095545] p50 3.8859474486664762 sS 0.6666666666666666 windows ((6.0, 12.0), (12.0, 18.0), (18.0, 0.0)) / worst rel err 2.910770986800668e-15
   ```

4. **Round-0 receipts finding fixed: receipts mode now uses each day's receipts_pallets and receipts_lines** (12 pallets and 35 lines on the toy, where the round-0 code counted 15 and 16.5). (Round-1 spec and proof audits; round-0 output for comparison.)
   Command: `uv run python -W ignore $S/check_receipts.py`
   ```
   round 0: engine receiving base hours 1.2000000000000002 = pallets 15.0
            from daily receipts_pallets (2 + 10) -> hours 0.9600000000000001
            engine receipt_check base hours 0.4106666666666667 = lines 16.5 ; from receipts_lines (5+30): 35
   round 1: engine receiving base hours 0.9600000000000001 = pallets 12.0
            engine receipt_check base hours 0.8711111111111112 = lines 35.0 ; from receipts_lines (5+30): 35
   ```

5. **The tests are not tautological: every injected fault is caught by a named test.** Mutants were injected through pytest plugins in the scratchpad; the repository was not changed. (Round-0 and round-1 proof audits, round-1 spec audit.)
   Command: `MUT=<m> PYTHONPATH=$S:/Users/skarwech/saas_v1 uv run pytest -p mutplug -q tests/property/test_f6_labor_properties.py tests/unit/test_f6_labor.py` (and `-p mut_env`, `-p mut_plugin`, `-p mut_plugin2`)
   ```
   first (.min() -> .first()) -> FAILED test_T6_8_row_order_does_not_change_labor, test_an_order_over_two_dates_counts_on_its_first_date
   fte_inv -> FAILED test_T6_5_...; neg_floor -> FAILED test_T6_7_...; temp_nomax -> FAILED test_T6_7_...
   pick_daily_const -> FAILED test_T6_6_..., test_T6_5_...
   M2 (receipts_lines prorated again): FAILED test_receipts_mode_uses_the_daily_receipts; M3 (no floor-1): 4 failed (incl. T6_2 golden); M4 (growth t-1): 4 failed; M5 (derived inbound without /gf): 4 failed; M6: FAILED test_T6_7_...
   mut_plugin: FAILED test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged (1 failed)
   mut_plugin2 (annual = D* x n_op): FAILED test_T6_2_labor_hours_heads_equal_golden, test_T6_2_labor_result_typ_matches_trace, test_T6_10_... (3 failed, 1 passed)
   ```

6. **The T6.5-T6.8 labor properties hold with 300 Hypothesis examples each** (no example database). (Round-1 proof audit.)
   Command: `uv run python $S/stress_props.py`
   ```
   test_T6_5_more_lines_never_fewer_labor_hours_or_fte OK x300
   test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged OK x300
   test_T6_7_labor_outputs_non_negative_and_worlds_ordered OK x300
   test_T6_8_row_order_does_not_change_labor OK x300
   ```

7. **Deterministic and row-order independent on 982k lines:** two runs, and runs with lines and daily shuffled (2 seeds), give bit-identical `LaborWorld` values in all 3 families. (Round-0 proof audit; round-0 spec audit's `check_order.py` gave 0 diffs over 990 labor nodes and 5 shuffles.)
   Command: `uv run python $S/shuffle.py $S/ecom_mid`
   ```
   manual_p2p rerun identical: True / shuffle seed 1: 0 differing values ... cube_asrs rerun identical: True / shuffle seed 2: 0 differing values, max rel diff 0.00e+00
   ```

8. **Round-1 trace finding fixed: every base_hours trace leaf names a real datum.** Before the round-2 fix, 6 leaves named columns the F3 daily frame does not have and `data:daily.return_lines` named a real column whose values the engine did not use. (Round-1 proof audit before; round-2 spec and proof audits after.)
   Command: `uv run python $S/trace_refs.py`
   ```
   before: MISSING data:daily.cases_in <- S2.labor.decant.base_hours / MISSING data:daily.orders_S <- S2.labor.packing_S.base_hours
           ok data:daily.return_lines <- S2.labor.returns.base_hours / daily.return_lines sum (ops): 45.0  returns_rate x lines sum: 75.24
   after:  S2.labor.returns.base_hours {'lines': 'data:daily.lines', 'returns_rate': 'data:basis.flows.returns_rate', ...}  []
           S2.labor.receiving.base_hours {'pallets_in*': 'data:design_day.inbound.pallets_per_day', 'growth_rate': 'data:design_day.growth_rate', 'horizon_years': 'data:design_day.horizon_years', ...}  [] (no NOT A DAILY COLUMN anywhere)
   ```

9. **Bad inputs now raise whsizing errors instead of raw exceptions or silent results.** Before round 1, `shifts_per_day=0` silently gave roster 0, `hours_per_shift=0` raised a raw ZeroDivisionError, NaN daily lines gave p50=nan and negative parcels gave ann_y1=-2011.383. (Round-0 proof audit before; rounds 1-2 after.)
   Command: `uv run python $S/edges_nowarn.py; uv run python $S/edges2.py`
   ```
   [hours_per_shift=0] ConfigError (whsizing): basis: invalid value(s): operations.hours_per_shift = 0.0 (must be > 0)
   [shifts_per_day=0] ConfigError ... (must be ≥ 1) / [utilisation=0] ConfigError ... (must be in (0, 1])
   [hourly_lines 23 values] WhsizingError (whsizing): labor: design_day.hourly_lines must be 24 finite values ≥ 0
   [empty shipped lines] WhsizingError (whsizing): labor: the daily lines differ from the shipped lines of the day
   [lines on a date absent from daily] WhsizingError: labor: shipped lines on a date absent from the daily series
   [qty_units negative] WhsizingError: labor: shipped lines hold a null or non-positive qty_units
   ```

10. **The round-2 edge-case findings are real and still present.** (Round-2 proof audit; re-run while writing this record with the same output.)
    Command: `uv run python -W ignore $S/adv3.py`
    ```
    [determinism LaborWorld equal] ok True
    [receipts units*=0 with daily receipts] ok {'receiving_base': 0.9600000000000001, 'decant_base': 0.0, 'receiving_design': 0.0, 'decant_design': 0.0, 'daily_receipts_units': [1000.0, 500.0, 0.0]}
    [duplicate date in daily] ok {'n_op': 3.0, 'pick_base': 0.17600000000000005, 'ann_y1': 995.9785403646919, 'ann_y1_baseline': 984.7532568737829}
    [qty_units Utf8] InvalidOperationError: `sum` operation not supported for dtype `str`
    [3x8 shifts] ok {'windows': ((6.0, 14.0), (14.0, 22.0), (22.0, 6.0)), 'worst': 0.0, ...}
    [null is_operating] ok 89.19640873970475
    ```

The round-2 proof audit also ran the full suite: `671 passed, 5 skipped in 45.14s` (skips: `test_g1_engine_parity` x4 and the F0 Docker report test; none in F6c files). This was not re-run for this record.

## Audit rounds

### Build (before round 0)

The engineer reported T6.2 (3 functions), T6.6 and T6.10 as passing, plus 10 unit tests: 15 tests in all. Choices where the register is silent (disclosed in the build notes and docstrings):

- shift 1 starts at the inbound window start (06:00), shifts run back to back, hours after the last shift go to the next day's shift 1, and more than 24 h of shifts raises ConfigError;
- profiles at one-hour resolution: outbound activities follow `design_day.hourly_lines` shifted by `labor.outbound_lag_hours`; inbound activities (receiving, receipt_check, put_away, decant, returns) are flat over 06:00-14:00; indirect follows direct;
- `heads_shift = max(1, h_s/(hours_per_shift x utilisation))` when h_s > 0, else 0, which is exactly I19 with one shift;
- annual lists cover years 1..finance.horizon_years (I41);
- receipts-mode daily inbound `x_d = x* x receipts_units_d / units_in*` (changed in round 1); derived mode x*/gf (I22);
- `single_line_share` over all shipped orders in `lines`; decant skipped for manual_p2p; replenishment for every family (I21); zero-workload activities emitted with roster 0 (I39);
- I15 daily split: `orders_S_d` is the actual count of one-line orders on day d and `orders_ML_d` the rest. The golden oracle uses this; `orders_d x share_S` would miss p50_day_hours by 0.9 % and temp_hours by 2.2 %.

Build blockers: `size_scenario` passes only `daily`, but `labor_days` needs the F3 shipped `lines`; `engine/__init__.py` does not re-export the labor API; the I15 daily split, the multi-shift rule and the receipts-mode daily inbound need register entries.

### Round 0: tests 15 passed, 0 failed. Both auditors: pass_with_issues

| # | Severity | Finding | Raised by | Resolution (round 1) |
|---|---|---|---|---|
| 1 | medium | Receipts-mode daily inbound ignored the daily `receipts_pallets` and `receipts_lines`; every driver was prorated by receipts_units_d/units_in* (toy: 15 pallets and 16.5 lines counted where the data has 12 and 35). | spec | **fixed**: each day uses its own receipts_pallets and receipts_lines; a null pallet count falls back to receipts_units_d x pallets*/units_in*; decant cases follow the units share (no per-SKU case mix in the daily series). Receipts mode now requires all three receipts columns. New test `test_receipts_mode_uses_the_daily_receipts`. Derived-mode numbers unchanged. |
| 2 | medium (spec) / low (proof) | No labor test for T6.5, T6.7 or T6.8; the existing tests are scoped "F6a/F6b part". The properties held in scratch checks. | spec, proof | **fixed**: three Hypothesis tests added. Hypothesis found the packing_S/roster case where an extra line makes an order multi-line; it is documented in the test docstring. |
| 3 | medium | `labor_days(inp, daily, lines)` needs the F3 shipped lines, but the spec's `size_scenario(..., daily, tracer)` passes only `daily`. I15, I17, I21 cannot be computed from `daily`. | spec, proof | **deferred**: integration item for F6z/F8; `engine/size.py` does not exist and is outside F6c's paths. |
| 4 | low | Multi-shift conventions are not in the spec or the register (shift 1 at inbound_window[0], back to back, wrap to shift 1, returns as inbound, hour-level edges). | spec | **deferred**: disclosed in the shifts.py docstring, reduces to I19 with one shift; register is outside F6c's paths. |
| 5 | low | `engine/__init__.py` does not re-export the labor API. | spec, proof | **deferred**: file owned by F6a. |
| 6 | medium | `shifts()`/`profiles()` did not validate the shift config or the 24 hourly values: `shifts_per_day=0` silently gave roster 0; other bad values raised raw ZeroDivisionError/ValueError. | proof | **fixed**: `size_labor` calls the existing I60 `check_basis`; `profiles()` requires 24 finite values >= 0. Tests `test_invalid_shift_config_is_a_config_error`, `test_inconsistent_inputs_are_rejected`. |
| 7 | medium | Receipts mode books all inbound work on receipt days; with lumpy receipts temp hours dominate (b2b S1: temp_y1 9962 of 14578 h, 68 %, vs 717 of 14489 h derived). Spec-literal I25 under the engineer's choice. | proof | **deferred**: smoothing would need a register entry and an expert decision before F7 prices temp hours. |
| 8 | low | Orders dated by `pl.col('date').first()`: per-day orders_S/ML depend on row order when an order spans two dates. | proof | **fixed**: `pl.col('date').min()` (I1). Covered by `test_an_order_over_two_dates_counts_on_its_first_date` and T6.8; both fail against `.first()`. |
| 9 | low | An empty shipped-lines frame was accepted silently (total_h 120.287 vs 89.196, +35 %). | proof | **fixed**: on every operating day, the zone lines must sum to daily.lines, else WhsizingError. |
| 10 | low | Daily values not validated: NaN propagated, negative counts gave negative hours, nulls filled with 0, a Datetime date raised a raw SchemaError. | proof | **fixed**: `_check_counts` (finite, >= 0; null only for an unknown receipts_pallets) and a date-dtype check. |
| 11 | low | With more than one shift, floor 1 per staffed activity per shift inflates the roster (about 4.0 of the 42.64 ecom_mid S0 roster, about 9.5 %). Spec-literal. | proof | **deferred**: expert/register decision; I19 covers one shift only. |
| 12 | low | The outbound lag was rounded half to even (0.5 h -> 0 h, 2.5 h -> 2 h). No effect at the default 1.0. | proof | **fixed**: exact split (share 1-f from hour h-n, f from h-n-1); bit-identical at lag 1.0. Test `test_fractional_outbound_lag_splits_each_hour`. |
| 13 | low | In receipts mode, receipts on a non-operating day drop out of inbound hours (I4-literal). | proof | **deferred**: register decision (I4). |

### Round 1 fix: tests 15 -> 26

Fixes for findings 1, 2, 6, 8, 9, 10 and 12 above. One leftover was disclosed: in receipts mode the base_hours trace leaf still read `data:daily.pallets_in`.

### Round 1: tests 26 passed, 0 failed. Both auditors: pass_with_issues

The auditors confirmed the round-0 fixes (Proofs 4, 5, 6, 9) and the new property tests. The round-1 spec auditor noted that T6.5's packing_S/roster exemption applies whenever `extra` is non-empty (test-strength caveat, not a finding).

| # | Severity | Finding | Raised by | Resolution (round 2) |
|---|---|---|---|---|
| 1 | medium (spec) / low (proof) | Base_hours trace leaves named daily columns that do not exist (pallets_in, receipt_lines, cases_in, replen_moves, orders_S, orders_ML); `data:daily.return_lines` named a real F3 column the engine did not use (I9: it uses returns_rate x lines); derived inbound omitted the design value and gf. The trace test only checked the `data:` prefix. | spec, proof | **fixed**: `_daily_workload` returns the values and their trace leaves together; `_inbound_refs` gives mode-dependent leaves. The same resolver found two more bad leaves (picking `data:lines.storage_class`, `data:lines.single_line_share`), also fixed. The trace test now resolves every leaf (`bad_data_refs`). No traced value changed. |
| 2 | low | Shipped lines on a date absent from `daily` were accepted silently and changed single_line_share (total_h 87.9010 vs 89.1964). | proof | **fixed**: WhsizingError "shipped lines on a date absent from the daily series"; a null date counts as absent. |
| 3 | low | `qty_units` not validated (negative or null silently changed replenishment). | proof | **fixed**: null, NaN, inf or <= 0 raises WhsizingError (cast to Float64 because NaN > 0 is True in polars). |
| 4 | medium | Integration: `labor_days` needs `lines` (round-0 #3). | spec, proof | **deferred** (F6z/F8). |
| 5 | medium | Receipts-mode temp hours dominate (round-0 #7). After the fix: ecom_mid S1 typ temp_y1 7606 of 18311 (receipts) vs 1753 of 17234 (derived). | spec, proof | **deferred** (expert/register). |
| 6 | low | The receipts-mode daily inbound rule is not in the register (I22 is derived-only, I56 covers F4 design values only). | spec, proof | **deferred** (register outside F6c paths). |
| 7 | low | Multi-shift conventions (round-0 #4). | spec, proof | **deferred**. |
| 8 | low | Floor 1 per shift (round-0 #11). | spec, proof | **deferred**. |
| 9 | low | Non-operating-day receipts dropped (round-0 #13). | spec, proof | **deferred**. |
| 10 | low | No labor re-exports in `engine/__init__.py` (round-0 #5). | spec, proof | **deferred**. |

### Round 2 fix: tests stay at 26

Fixes for findings 1-3 above (new cases inside existing tests). Golden still 257/257; `e2e_v2.py` on b2b: worst rel err 5e-16 (derived) and 2e-16 (receipts).

### Round 2: tests 26 passed, 0 failed. Both auditors: pass_with_issues

The auditors confirmed the round-1 fixes (Proofs 8, 9) and recomputed everything again (Proofs 1-3). **No fix round followed, so every finding below is open.**

| # | Severity | Finding | Raised by | Status |
|---|---|---|---|---|
| 1 | medium | NEW. Receipts mode with `units_in* = 0`: `share = receipts_units/u if u > 0 else 0` (labor.py:329) zeroes daily decant cases and the null-pallet fallback, while receiving and put_away still count each day's receipts_pallets. Decant labor disappears though cases arrive; receiving gets annual hours with 0 design-day hours and heads. (Evidence partly clipped.) | proof | open (confirmed by Proof 10) |
| 2 | low | NEW. A duplicated daily date is accepted silently: the join copies the day's aggregates, the zone-lines check still passes, the day counts twice and n_op grows (ann_y1 995.98 vs 984.75; spec auditor: temp_y1 16.84 -> 0). | spec, proof | open (confirmed by Proof 10) |
| 3 | low | NEW. A null `is_operating` is silently treated as non-operating (`daily.filter("is_operating")` drops it). On an operating day (spec auditor, D2) ann_y1 became 1018.43 and temp_y1 0, with no error. | spec, proof | open (confirmed by Proof 10) |
| 4 | low | NEW. A Utf8 `qty_units` passes the Float64-cast check, then the sum on the original column raises a raw polars `InvalidOperationError` instead of a whsizing error. | proof | open (confirmed by Proof 10) |
| 5 | low | NEW (forward-looking). `ShiftRow.start_hour`/`end_hour` are result numbers without a TraceNode (only `labor.<a>.shift<s>.{hours,heads}` are traced), so T6.11 would fail on them unless F6z exempts them. A 3-shift window ending at midnight is written (18.0, 0.0). | spec | open |
| 6 | medium | Integration: `labor_days` needs `lines`; no `size.py` and no caller yet. | spec, proof | deferred (F6z/F8) |
| 7 | medium | Receipts-mode temp hours dominate. The proof auditor added that the receipts-mode design-day roster also doubles (b2b S1 56.44 vs 28.32) because the F4 P95 receipts design values are about 5x the mean (pallets* 287.8 vs 56.6; receipts on 20 % of operating days): an F4/I56 effect, not an F6c formula error. | spec, proof | deferred (expert/register) |
| 8 | low | Receipts-mode daily inbound rule not in the register. | spec, proof | deferred |
| 9 | low | Multi-shift conventions not in the register (INTERPRETATIONS.md:160, I19, still says multi-shift splitting is not covered). | spec, proof | deferred |
| 10 | low | Floor 1 per staffed activity per shift. | spec, proof | deferred |
| 11 | low | Non-operating-day receipts dropped (nonop2.py: 0 or 50 pallets on D3 -> receiving base_hours 0.96 both times). | spec, proof | deferred |
| 12 | low | No labor re-exports in `engine/__init__.py`. | spec, proof | deferred |

## Open issues

1. **[medium] Integration (F6z/F8):** `size_scenario` must pass the F3 shipped lines (`ProfileTables.lines`: order_id, sku, date, qty_units) to `labor_days(inp, daily, lines)`. The spec signature passes only `daily`; the I15, I17 and I21 daily workloads cannot be computed from it. Without them `p50_day_hours`, `temp_hours.y*` and several `annual_hours.y*` keys cannot match golden.
2. **[medium] Receipts mode with lumpy receipts** (labor.py `_inbound`): literal I25 puts most inbound hours above the P50 day (b2b S1 typ: temp_y1 9903 of 14519 h in receipts mode, 717 of 14489 h in derived mode). Needs an expert or register decision before F7 prices temp hours with temp_premium.
3. **[medium] `units_in* = 0` in receipts mode** (labor.py:329) silently drops decant labor and the null-pallet fallback. Round 2, no fix round. Should raise or use a defined rule.
4. **[low] Duplicate daily dates** accepted silently (labor.py:106). F3 builds unique dates, so real impact is low.
5. **[low] Null `is_operating`** silently treated as non-operating (labor.py:106).
6. **[low] Non-numeric `qty_units`** escapes as a raw polars error (labor.py:91).
7. **[low] `ShiftRow.start_hour/end_hour` untraced** (shifts.py:103); F6z must trace or exempt them for T6.11.
8. **[low] Register entry needed:** receipts-mode daily inbound (each day's receipts_pallets and receipts_lines; null pallets -> receipts_units_d x pallets*/units_in*; decant cases = cases_in* x receipts_units_d/units_in*).
9. **[low] Register entry needed:** multi-shift conventions (shift 1 at inbound_window[0], back-to-back shifts, leftover hours to shift 1, returns as inbound, hour-midpoint edges, exact fractional lag split).
10. **[low] Expert decision:** floor 1 head per staffed activity applied per shift (about 4 extra heads on ecom_mid S0 with 2 x 7 h).
11. **[low] Register decision (I4):** receipts booked on non-operating days are not counted in inbound annual hours.
12. **[low] `engine/__init__.py`** (F6a owner) does not re-export `size_labor`, `labor_days`, `labor_result`, `LaborDays`, `LaborWorld`, `ActivityWorld`; they are in `whsizing.engine.labor.__all__`.
13. **[low] Register entry needed for the I15 daily split** (`orders_S_d` = actual one-line orders on day d). I15 (INTERPRETATIONS.md:125) defines only the design-day split. This was a build blocker and dropped out of the later blocker lists; checked while writing this record, the register still does not cover it.
14. **[low] Test-strength caveats:** T6.5 exempts packing_S and the total roster more broadly than needed; T6.6 cannot catch a mis-scaled indirect share; T6.7's lo <= typ <= hi holds by construction.

## Not applicable here and why

- **T6.1, T6.3, T6.4:** storage, area/docks and Erlang-C belong to F6a, F6d and F6e. No F6c code computes them.
- **T6.9, T6.11:** need `size_scenario`, the manifest and `result.json` (F6z/F8), none of which exist yet. F6c determinism (Proofs 7 and 10) and labor trace resolution (`test_T6_2_labor_trace_inputs_resolve`) were checked in their place.
- **Register and package-API edits:** `docs/INTERPRETATIONS.md` and `src/whsizing/engine/__init__.py` are outside F6c's paths, so open issues 8-13 can only be reported.
- **Domain-expert review:** the multi-shift conventions, floor 1 per shift, receipts-mode temp hours and non-operating-day receipts need a warehouse-operations expert or the register owner. That cannot be done here. All catalog values are still `source: TODO` with confidence L (F5).
- **Real client data:** none was used. Only `tiny_golden` (T6.2, T6.10) and the synthetic b2b and ecom_mid datasets (auditor runs) were used.
- **Docker / CI:** not relevant to F6c; no F6c test is skipped.

## Fresh test output (run while writing this record, 2026-11-09)

Command: `cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f6_labor*.py tests/property/test_f6_labor*.py tests/golden/test_f6_labor_golden.py -q -rA`

The two captured-stdout warning lines of the golden setup (`catalog_todo_sources count=72 total=72` and `design_day_short_window`) are removed below.

```
..........................                                               [100%]
==================================== PASSES ====================================
=========================== short test summary info ============================
PASSED tests/unit/test_f6_labor.py::test_design_day_hours_and_heads_per_activity
PASSED tests/unit/test_f6_labor.py::test_two_shift_split_and_roster
PASSED tests/unit/test_f6_labor.py::test_one_shift_reduces_to_I19
PASSED tests/unit/test_f6_labor.py::test_annual_series_from_daily_workloads
PASSED tests/unit/test_f6_labor.py::test_core_heads_and_temp_hours
PASSED tests/unit/test_f6_labor.py::test_cube_decant_and_picking_zones
PASSED tests/unit/test_f6_labor.py::test_amr_picking_at_station_rate
PASSED tests/unit/test_f6_labor.py::test_receipts_mode_uses_the_daily_receipts
PASSED tests/unit/test_f6_labor.py::test_fractional_outbound_lag_splits_each_hour
PASSED tests/unit/test_f6_labor.py::test_labor_result_ranges_and_shift_table
PASSED tests/unit/test_f6_labor.py::test_errors
PASSED tests/unit/test_f6_labor.py::test_invalid_shift_config_is_a_config_error[shifts_per_day-0]
PASSED tests/unit/test_f6_labor.py::test_invalid_shift_config_is_a_config_error[hours_per_shift-0.0]
PASSED tests/unit/test_f6_labor.py::test_invalid_shift_config_is_a_config_error[hours_per_shift--7.0]
PASSED tests/unit/test_f6_labor.py::test_invalid_shift_config_is_a_config_error[utilisation-0.0]
PASSED tests/unit/test_f6_labor.py::test_invalid_shift_config_is_a_config_error[paid_hours_per_person_day-0.0]
PASSED tests/unit/test_f6_labor.py::test_inconsistent_inputs_are_rejected
PASSED tests/unit/test_f6_labor.py::test_an_order_over_two_dates_counts_on_its_first_date
PASSED tests/property/test_f6_labor_properties.py::test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged
PASSED tests/property/test_f6_labor_properties.py::test_T6_5_more_lines_never_fewer_labor_hours_or_fte
PASSED tests/property/test_f6_labor_properties.py::test_T6_7_labor_outputs_non_negative_and_worlds_ordered
PASSED tests/property/test_f6_labor_properties.py::test_T6_8_row_order_does_not_change_labor
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_hours_heads_equal_golden
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_result_typ_matches_trace
PASSED tests/golden/test_f6_labor_golden.py::test_T6_10_annual_hours_below_design_day_times_operating_days
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_trace_inputs_resolve
26 passed in 3.77s
```
