# F6z audit: Sizing engine integration (size_scenario, worlds, flags, result.json + trace.jsonl, properties)

## Verdict: pass_with_issues

All F6 acceptance tests that can run here pass: 137 passed, 0 failed, 1 skipped (the T6.9 rerun-from-manifest half, which needs F8). Golden S0/S2 match through `size_scenario` with 0 mismatches over 405 keys, and every number in `result.json` has a trace node.
The verdict stays below `pass` because, after the last audit round (round 1), 3 low findings are deferred to the register owner or an expert (T6.5 pickers, F_UNSTABLE:packing, I47 amr figure / I5 severity wording) and 2 new low nits were not fixed. Both round-1 auditors returned pass_with_issues.

Scope: `size_scenario` (I61 signature) runs storage, throughput, labor, area and queue once per world. It merges the worlds into Ranges, builds the flags (I46 order and suffixes) and the F_LOW_CONFIDENCE count (I47), and `write_scenario` writes `scenarios/<id>/result.json` and `trace.jsonl`. The size-level property tests T6.5, T6.7 and T6.8 are new, and T6.9/T6.11 are covered. The fix closes most of the open issues inherited from F6a, F6c and F6d, but not all of them; "Inherited open issues" below lists each item. Schema changes: none (`schema_changes: []`). One comment in `src/whsizing/schemas/result.py:93` (an F0 path) was changed from `gtp_ports` to `ports` during the fix round. No field or behaviour changed, and the engineer disclosed the edit.

Main files: `src/whsizing/engine/size.py` (227 lines, new), `src/whsizing/engine/__init__.py` (re-exports the labor, area, queue and size APIs). Fixes were made in `area.py`, `labor.py`, `shifts.py`, `queue.py`, `storage.py`, `throughput.py` and `inputs.py`. New tests are in `tests/unit/test_f6_size.py`, `tests/golden/test_f6_size_golden.py`, `tests/property/test_f6_size_properties.py` and `tests/e2e/test_f6_size_e2e.py`. Existing F6 tests were adjusted: `test_f6_area.py`, `test_f6_throughput_properties.py`, `test_f6_inputs.py`, `test_f6_area_golden.py` and `test_f6_labor_golden.py`.

Static checks, re-run while writing this record: `uv run ruff check` gives "All checks passed!" and `uv run ruff format --check` gives "26 files already formatted". `uv run pyright` gives "0 errors, 0 warnings, 0 informations". All three ran on `src/whsizing/engine` and every `tests/*/test_f6_*` file. The full suite (`uv run pytest -q`) gives 776 passed and 3 skipped (F7 parity, Docker, T6.9 manifest).

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T6.1 | `tests/golden/test_f6_size_golden.py::test_T6_1_storage_throughput_equipment_through_size_scenario` | pass | 74 keys go through the real chain: F3 `build_tables`, I58 sku frame, F4 design day, then `size_scenario(lines=t.lines)` for S0/S2. The keys cover storage 28, throughput 14, equipment 18, utilisation 6, eligibility 6 and bottleneck 2. All 74 match the independent G1 golden within 0.5 %, with integers exact and 0 mismatches. The test asserts the key count, and ScenarioResult fields are checked too. |
| T6.1 | `tests/golden/test_f6_size_golden.py::test_T6_1_flags_and_low_confidence_count_equal_golden` | pass | The S0/S2 flag strings are compared in I46 order, and `low_confidence_params` S0 = 30 and S2 = 50 equal golden (I47). S0 reads no parking Param; S2 reads `cube_asrs.m2_per_robot_parking`. |
| T6.1 | `tests/golden/test_f6_storage_golden.py::test_T6_1_storage_throughput_equipment_equal_golden` (+ `test_T6_1_trace_inputs_resolve`) | pass | The F6a part-level golden test, kept and still green. |
| T6.2 | `tests/golden/test_f6_size_golden.py::test_T6_2_labor_through_size_scenario` | pass | 257 labor keys (S0 123, S2 134) through `size_scenario`, 0 mismatches. Daily zone lines and the packing split come from `lines=t.lines` (I61, I66), which closes F6c open issue 1. Roster and `temp_hours` y5 on the ScenarioResult also match. |
| T6.2 | `tests/golden/test_f6_labor_golden.py::test_T6_2_labor_hours_heads_equal_golden` (+ `test_T6_2_labor_result_typ_matches_trace`, `test_T6_2_labor_trace_inputs_resolve`) | pass | The F6c part-level golden test, kept. Its trace test now pins the derived decant leaves. |
| T6.3 | `tests/golden/test_f6_size_golden.py::test_T6_3_area_docks_queue_through_size_scenario` | pass | 70 area/docks/queue keys, 0 mismatches. Amenities use the real F6c roster from the same run, which closes F6d open issue 9. The pack_rate `s_S` input is `S*.labor.single_line_share`, so share_S has one source (closes F6d open issue 6). |
| T6.3 | `tests/golden/test_f6_area_golden.py::test_T6_3_area_docks_queue_equal_golden` (+ `test_T6_3_results_match_the_trace`, `test_T6_3_trace_inputs_resolve`) | pass | The F6d part-level golden test, kept. The trace-resolve exemption was widened to `labor.*` refs because labor is not run in that test. |
| T6.4 | `tests/unit/test_f6_queue.py::test_T6_4_erlang_c_values`, `test_T6_4_w_q_matches_mm1_closed_form`, `test_T6_4_w_q_matches_mm2_closed_form`; `tests/property/test_f6_queue_properties.py::test_T6_4_*` (3) | pass | `erlang_c(1, 0.5) == 0.5` and `erlang_c(2, 1.0) ≈ 1/3` (rel 1e-12). W_q and P(W>t) are checked against the M/M/1 and M/M/2 closed forms. Hypothesis checks that P_wait is a probability and decreases as servers are added. Kept from F6e. |
| T6.5 | `tests/property/test_f6_size_properties.py::test_T6_5_more_lines_never_fewer_fte_stations_or_less_area` | pass | Hypothesis, end to end over 3 families. Every order is shipped m times and the design stock is scaled by m. The test checks lo/typ/hi of FTE (hours, heads, roster, annual hours, core FTE, every activity), `gtp_stations`/`ports`/`robots`, every area zone, the storage total and the area total, and it asserts strict growth of hours and storage (closes F6a open issue 5). **Caveat:** pickers, carts and forklifts are left out on purpose, because the spec-literal engine has a counterexample. See open issue 1. |
| T6.5 | `tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations[*]` (3); `tests/property/test_f6_labor_properties.py::test_T6_5_more_lines_never_fewer_labor_hours_or_fte` | pass | Part level. Pickers, carts and forklifts are covered here with stock held constant. The storage clause could never fail at constant stock, so the fix round removed it and renamed the test. |
| T6.6 | `tests/property/test_f6_labor_properties.py::test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged` | pass | Doubling the flows and every productivity leaves hours, heads, roster, annual hours, shift heads, core FTE and temp hours unchanged (rel 1e-9). This runs at labor level (F6c), not through `size_scenario`. |
| T6.7 | `tests/property/test_f6_size_properties.py::test_T6_7_outputs_non_negative_and_ranges_ordered` (+ the F6a/F6c T6.7 variants) | pass | Random scale, clear height 1 to 14 m and shift count, over 3 families. Every number in the result is finite and ≥ 0, and every Range (more than 100 per run) has 0 ≤ lo ≤ typ ≤ hi. lo ≤ typ ≤ hi holds by construction, since `to_range` takes min/typ/max as ADR-002 defines a Range. The checks that can fail are these: some Range is non-degenerate, and the pessimistic-world trace is ≥ the optimistic world for hours, storage and area. Mutation M2 (raw lo/hi in place of min/max) makes the test fail. |
| T6.8 | `tests/property/test_f6_size_properties.py::test_T6_8_row_order_of_the_inputs_does_not_change_result_json` | pass | Shuffled sku, daily and lines frames give a byte-identical `result.json` for S0, S1 and S2. Mutation M1 (SKU sort removed in `world_inputs`) makes it fail. |
| T6.8 | `tests/property/test_f6_size_properties.py::test_T6_8_the_check_catches_a_missing_date_sort` | pass | A mutation check on the manual path, emulating `labor_days` without `.sort("date")`. The engineer also ran a real source mutation (sort removed in labor.py, then restored): T6.8 failed with sid='S0'. |
| T6.9 | `tests/unit/test_f6_size.py::test_T6_9_identical_inputs_give_byte_identical_result_json` | pass | Within one process, `result.json` and `trace.jsonl` are byte-identical for S0/S1/S2, and `trace_path` is relative. |
| T6.9 | `tests/unit/test_f6_size.py::test_T6_9_a_fresh_process_writes_the_same_result_json` | pass | A fresh `sys.executable` subprocess with `PYTHONHASHSEED=4242` writes identical bytes. Marked slow. |
| T6.9 (rerun from manifest) | `tests/unit/test_f6_size.py::test_T6_9_rerun_from_manifest_gives_identical_result_json` | not_applicable (skipped) | A skip-marked placeholder: it needs F8's `runs/<id>/manifest.json`. |
| T6.10 | `tests/golden/test_f6_labor_golden.py::test_T6_10_annual_hours_below_design_day_times_operating_days` | pass | For S0/S2 and years 1 to 5, 0 < annual_hours < design-day hours × 252, and y1 < 0.7 × that. The e2e test applies the same guard on ecom_mid for 3 families. |
| T6.11 | `tests/unit/test_f6_size.py::test_T6_11_every_number_in_result_json_has_a_trace_node[S0\|S1\|S2\|S9]` | pass | Walks the written `result.json` against `trace.jsonl`. A Range's typ must equal the typ-world node and lo/hi the min/max of that node over the 3 worlds; a scalar must equal the typ node. More than 150 numbers are checked, and every node input must resolve. Only `scenario.*` and `labor.shifts[].shift` are exempt. S9 raises F_ELIG_ASSUMED, F_DOCK_SHORTFALL and F_UNSTABLE. Mutations M2 and M4 (flag trace removed) both make it fail. |
| T1.5 (G1) | `tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param` | pass | This test failed on purpose before F6z. It now passes after the I26/I63(12) fix: AMR robot parking reads `cube_asrs.m2_per_robot_parking`. |
| F6 e2e | `tests/e2e/test_f6_size_e2e.py::test_F6_ecom_mid_three_families_end_to_end` | pass | ecom_mid over 730 days (981,910 lines): F1 generate, FR CSV, F2 ingest, F3, F4, then F6 for 3 families. Total 5.6 s, of which F6 ×3 takes 0.4 s. The test runs `assert_traced` and the T6.10 guard. Marked slow. |
| F6 edge cases | `tests/unit/test_f6_size.py::test_zero_eligible_lines_degenerate_to_manual`, `test_building_below_one_level_gives_one_level_and_height_limit`, `test_stock_larger_than_the_building_flags_no_fit_and_continues` | pass | I48: with zero eligible lines, ports, robots and cube bins are 0, F_ELIG_LOW is raised, only the packing queue remains, and storage, labor hours and area total equal S0's. A building lower than one level gives one level and F_HEIGHT_LIMIT. Stock larger than the building gives F_NO_FIT and the run continues. |
| F6 fixes (round 0 build) | `test_receipts_mode_without_design_receipts_keeps_decant_and_pallets`, `test_bad_daily_or_lines_raise_data_quality_errors`, `test_queue_resource_rejects_non_finite_rates[*]` (4), `test_decant_cases_in_lists_its_pack_data_and_amr_parks_on_the_cube_param` (all in `tests/unit/test_f6_size.py`) | pass | I64: in receipts mode with `units_in* = 0`, decant is not 0 (whole-history ratios are used, or DataQualityError if none can be derived). A duplicate date, a null is_operating or a non-numeric qty raises DataQualityError. Non-finite λ, μ or t is rejected. The decant trace lists upc/upp/cpp. |
| F6 fixes (round 1) | `test_design_day_flags_carry_the_f6_table_severity_info`, `test_no_low_confidence_param_gives_no_low_confidence_flag`, `test_scenario_id_must_be_one_safe_path_segment[*]` (5), `test_shift_end_is_start_plus_length_and_traced[*]` (3), `test_inconsistent_inputs_raise_data_quality_errors` (all in `tests/unit/test_f6_size.py`) | pass | Each test pins one round-0 finding (see Audit rounds): F6-table severity `info`, no `F_LOW_CONFIDENCE:0`, path-safe ids, end = start + length, and DataQualityError for inconsistent inputs. |

## Proofs (captured by the auditors during the audit)

The auditors captured these proofs during rounds 0 and 1. They were not re-run for this record. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F6z/`, written `$S` below. All commands ran from `/Users/skarwech/saas_v1`, with `PYTHONPATH=/Users/skarwech/saas_v1` where needed. Excerpts marked "(clipped)" were cut off in the audit history.

1. **An independent hand computation of AMR S1 matches the engine in all three worlds, and the Ranges are min/max over the worlds.** The hand computation covers λ, λ_e, stations, robots with charging reserve, pod bins with 1/4 mixed bins and a 5 % reserve, pods, pod area, robots per m², and parking on the cube Param. (Round 0, spec audit.)
   Command: `uv run python $S/amr_hand.py`
   ```
   lo {'stations': 1, 'robots': 3, 'bins_total': 607.6875, 'pods': 16, 'A': 51.2, 'dens': 0.0586}
      engine {... 'equipment.robots': 3.0, 'storage.pod_bin.positions': 607.6875, 'storage.pod_bin.pods': 16.0,
              'storage.pod_bin.area_m2': 51.2, 'equipment.robots_per_storage_m2': 0.0586}
   typ robots 2, bins 537.3375, pods 9, A 23.4, dens 0.0855 = engine
   hi robots 1, bins 485.8875, pods 6, A 12.0 = engine
   robots Range (1.0, 2.0, 3.0)
   ```

2. **Erlang-C and the S2 queue pools match a textbook closed form and the I24/I45 inputs computed by hand.** In round 1 an independent recompute of the F6d/F6c formulas from the result also matched. (Round 0 and round 1, spec audit.)
   Commands: `uv run python $S/queue_hand.py` ; `uv run python $S/r2_formulas.py`
   ```
   erlang 5 4.332 0.6890753044 0.6890753044
   packing c 1 lam 11.5774 mu 31.6462 a 0.365839 P 0.36584 = 0.36584 Wq 0.018229319604756388 = 0.018229319604756388
   ports c 1 lam 83.6895 mu 297.5 Wq 0.0013156944070919138 = same
   S0 circulation hand 71.675202 engine 71.675202; total hand 398.641647 engine 398.641647; amenities hand 196.64 engine 196.64
   roster hand 11.66 engine 11.66; core fte y1 hand 0.825685711 engine 0.825685711
   ```

3. **The T6.7, T6.8 and T6.11 tests each catch a deliberate mutation of a scratch copy of `src/whsizing`.** The mutations are M1 (no SKU sort), M2 (unsorted Range) and M4 (no flag trace). (Round 0, spec audit.)
   Command: `PYTHONPATH=<scratch>/m{1,2,4} uv run --project /Users/skarwech/saas_v1 pytest -c /Users/skarwech/saas_v1/pyproject.toml --rootdir /Users/skarwech/saas_v1 -p no:cacheprovider <T6.8 | T6.7+T6.11 | T6.11>`
   ```
   M1: FAILED test_T6_8_row_order_of_the_inputs_does_not_change_result_json, 1 failed
   M2: FAILED test_T6_7_... and test_T6_11_...[S0|S1|S2|S9], 5 failed
   M4: FAILED test_T6_11_...[S0|S1|S2|S9], 4 failed
   ```
   The proof audit's probe5 adds that an emulated missing SKU sort is caught in 10/10 shuffles for S1 and S2, and in 0/10 for S0, whose output is genuinely order-invariant at these sizes.

4. **`result.json` and `trace.jsonl` are byte-identical across fresh interpreters with different hash seeds (T6.9).** (Round 0, proof audit.)
   Command: `for s in 1 99; do PYTHONHASHSEED=$s PYTHONPATH=. uv run python -c "import sys; from tests.unit.test_f6_size import write_all; write_all(sys.argv[1])" $D/h$s; done`, then `cmp` of result.json and trace.jsonl per sid.
   ```
   S0 identical (result.json + trace.jsonl) / S1 identical / S2 identical
   sha1 S0 30b669c7ac61…, S1 49058ea05374…, S2 782fc17320b8… identical in h1 and h99; trace lines 704/818/827
   ```

5. **T6.5 holds over a 486-pair grid with stock held constant, pickers, carts and forklifts included. With stock × m, the only violation is the documented S2 picker counterexample.** The grid is S0/S1/S2 × m 1-3 × extra 1-3 × 6 clear heights × 1-3 shifts. (Round 0, proof audit; the counterexample was re-confirmed in round 1.)
   Commands: `uv run python $S/probe4.py` ; `uv run python $S/t65.py`
   ```
   stock x m violations: ('S2','eq.carts') (1, 4, 1.0, 1, 'lo', 2.0, 1.0); ('S2','eq.pickers.shelving') (…1.0, 0.0); ('S2','eq.pickers_peak') (…2.0, 1.0)
   const stock violations: (none)
   S2 1 pickers_peak 2.0; S2 2 2.0; S2 4 1.0; S2 6 2.0 (hours 6.34, 12.75, 25.77, 38.66)
   const-stock S2 1..6: 2.0, 2.0, 2.0, 3.0; const-stock S0: 2.0, 2.0, 3.0, 5.0
   ```

6. **Ranges equal (min, typ, max) over the traced worlds (ADR-002), with 0 mismatches. The I47 counts reproduce: S0 30, AMR 49, S2 50. Flag order follows I46, and no severity mismatches the F6 table.** The severity check ran on S0, S1, S2, S9, a low-building variant and a short-SLA variant. (Round 1, spec audit; the counts were also checked in round 0.)
   Command: `uv run python $S/r2_hand.py`
   ```
   S0 low conf 30 {'engine': 1, 'finance': 1, 'labor': 9, 'manual_p2p': 19}; S1 low conf 49 {...};
   S2 low conf 50 {'cube_asrs': 21, 'engine': 1, 'finance': 2, 'labor': 9, 'manual_p2p': 17}; (no RANGE MISMATCH lines);
   S9 severity mismatches [] ['F_NO_FIT', 'F_HEIGHT_LIMIT:pallet_rack', 'F_ELIG_ASSUMED:0.083998', 'F_SCALE_LOW', 'F_ROBOT_DENSITY',
   'F_DOCK_SHORTFALL', 'F_UNSTABLE:packing', 'F_SHORT_HISTORY', 'F_RATIO_DRIFT:weight_kg', 'F_RATIO_DRIFT:pallets_out', 'F_LOW_CONFIDENCE:50']
   ```

7. **T6.11 holds beyond the test's own four parametrisations.** In round 0, 5 more variants passed: a degenerate cube, 3 shifts, S1 with a 1 h SLA window (unstable), a 1 m clear height and a port-rate override. The b2b_cases end-to-end run (445,690 lines; derived and receipts mode; 1, 2 and 3 shifts × 3 families) also passes, reruns are byte-identical, and receipts-mode decant is non-zero (I64). (Round 0, spec audit; rounds 0 and 1, proof audit.)
   Commands: `uv run python $S/t611.py` ; `uv run python $S/e2e_b2b.py b2b_cases $S`
   ```
   S3_degenerate OK [...'F_ELIG_LOW','F_SCALE_LOW',...'F_LOW_CONFIDENCE:50'] mism []; S2_3shift OK;
   S1_slarisk OK [...'F_UNSTABLE:packing'...] mism []; S0_lowheight OK; S2_override OK ... mism []
   == b2b_cases derived 2x7.0: lines 445690, dd lines 1729, inbound mode derived
     manual_p2p: area 1738 fit True roster 33.4 ... flags ['F_UNSTABLE:packing', 'F_LOW_CONFIDENCE:30']
     cube_asrs: area 1451 ... eq {... 'ports': 8.0, 'robots': 18.0} flags ['F_UNSTABLE:packing', 'F_LOW_CONFIDENCE:50']
   total 4.6 s
   ```

8. **The round-1 fixes work.** Design-day flags are `info` in result.json while F4's design_day keeps `warning` and is not mutated. No `F_LOW_CONFIDENCE:0` is emitted. A `../escaped` id is rejected before anything is written. A shift ends at start + length. Inconsistent inputs raise DataQualityError. (Round 1, spec and proof audits.)
   Commands: `uv run python $S/r2_adv.py` ; `$S/lc0.py` ; `$S/probe3.py` ; `$S/probe1.py`
   ```
   S0 flags [('F_HEIGHT_LIMIT:pallet_rack', 'info', None), ('F_SHORT_HISTORY', 'info', 26.0), ..., ('F_LOW_CONFIDENCE:30', 'info', 30.0)]
   design_day flags [('F_SHORT_HISTORY', 'warning'), ('F_RATIO_DRIFT:weight_kg', 'warning'), ('F_RATIO_DRIFT:pallets_out', 'warning')]
   F_RATIO_DRIFT:pallets_out info pallets_out: reference-day ratio gives 1.982, P_m = 3.75   (round 1 printed 'F_LOW_CONFIDENCE:0 info ...')
   whsizing.errors.ConfigError: scenario id '../escaped': use letters, digits, '_' or '-' only
   2x10.0: windows [(1, 6.0, 16.0), (2, 16.0, 26.0)] ... sum 7.925 vs total.hours 7.925
   [EXC] dup sku S2: DataQualityError: engine: the SKU frame repeats sku(s) ['020708b3cf573cf4']
   [EXC] unknown sku in lines: DataQualityError: labor: shipped lines reference SKUs missing from the SKU frame
   ```
   Note on the quoted excerpt: in the auditor's parenthetical, "round 1" means the earlier capture, which is round 0 in this record's numbering (finding spec-2).

9. **I62 is implemented: all three worlds are fully traced, and the only extra typ-world nodes are flags and low_confidence. Worlds are oriented correctly, and computing labor_days once is safe because SKU classes are identical across worlds.** (Round 0, proof audit.)
   Commands: `uv run python $S/probe2.py` ; `$S/probe1.py`
   ```
   S0 nodes per world {'lo': 233, 'typ': 238, 'hi': 233}; S1 270/278/270; S2 273/281/273.
   storage_class identical across worlds: True (S0,S1,S2). lo<hi nodes only area.fit and area.pack_rate.
   ```

## Audit rounds

### Round 0 (after the build)

The spec audit returned pass_with_issues (127 passed, 0 failed), as did the proof audit (127 passed, 0 failed).

| # | Auditor | Severity | Finding | Resolution (round 1 fix) |
|---|---|---|---|---|
| spec-1 | spec | medium | `size.py:157`: result.json carried F_SHORT_HISTORY, F_RATIO_DRIFT:<m> and F_PERCENTILE_CLIPPED with severity `warning`, while the F6 flags table says `info`. | **Fixed.** `_flags` copies each design-day flag with `severity="info"`. F4's `design_day.py` and `test_f4_register.py:189` are F4 paths, so they keep `warning`. New test: `test_design_day_flags_carry_the_f6_table_severity_info`. No separate RED run was done, but the test asserts `info` where the old code gave `warning`. |
| spec-2 | spec | low | `size.py:141`: `F_LOW_CONFIDENCE:0` was added even when no confidence-L Param is read. | **Fixed.** The flag is appended only when n ≥ 1; the trace node is still recorded with value 0. New test: `test_no_low_confidence_param_gives_no_low_confidence_flag`. |
| spec-3 | spec | low | T6.5 at size level leaves pickers, carts and forklifts out, because pickers are not monotone when stock grows with demand. | **Deferred** to the register (I17 per-zone ceil combined with the F6a class rule on the design stock cube). The F6a part-level test covers pickers at constant stock. |
| spec-4 | spec | low | F_UNSTABLE:packing is raised for every family on ecom_mid: pack stations are sized on peak-hour orders (I24), but the queue λ_s takes the SLA-window term (I45). | **Deferred.** The code follows the register literally; this is a register or expert question. |
| spec-5 | spec | low | Open items: (a) I47 gives no amr_gtp figure; (b) the AreaResult.zones comment says `gtp_ports`; (c) a tautological lo ≤ typ ≤ hi assertion in `test_f6_area.py`; (d) `.gitignore` lacks `.hypothesis/`. | (b) **Fixed**: one-word comment fix in `schemas/result.py:93` (an F0 path, disclosed). (c) **Fixed**: the test now asserts a strict world order and Range == (hi-world, typ, lo-world). (a) **Deferred**: register, outside the F6z paths. (d) Outside the F6z paths. The round-1 audit found `.gitignore:12` already ignores `.hypothesis/`, so this blocker is stale; re-checked while writing this record. |
| runtime-1 | proof | low | F_UNSTABLE:packing for every family on realistic profiles; b2b_cases shows it in all 9 runs. | **Deferred.** Same issue as spec-4. |
| runtime-2 | proof | low | `size.py:125`: `write_scenario` used the unvalidated `ScenarioDef.id` as a path segment. With `'../escaped'` it wrote outside `scenarios/`. | **Fixed.** `_check_id` requires `[A-Za-z0-9_-]+` and raises ConfigError, called in both `size_scenario` and `write_scenario`. New test: `test_scenario_id_must_be_one_safe_path_segment[*]` (5 cases). |
| runtime-3 | proof | low | `shifts.py` mixed conventions: a midnight end was written as 24.0, but a wrapping shift ended at clock time (16.0, 2.0). | **Fixed.** end_hour = start_hour + hours_per_shift, so it can exceed 24; the end_hour trace node takes start_hour as an input. New test: `test_shift_end_is_start_plus_length_and_traced[*]`. |
| runtime-4 | proof | low | `labor.py:95`: a duplicate SKU row surfaced as a misleading labor error, and several input-consistency failures raised WhsizingError (exit 1) instead of DataQualityError (exit 3). | **Fixed.** `world_inputs` rejects repeated SKUs, and labor raises DataQualityError for five data cases; programming errors stay WhsizingError. New test: `test_inconsistent_inputs_raise_data_quality_errors`. |
| runtime-5 | proof | low | Inherited test-strength items: the `test_f6_area.py:130` tautology, a throughput T6.5 storage clause that can never fail, and the `gtp_ports` schema comment. | **Fixed.** See spec-5. The storage clause was removed and the test renamed `test_T6_5_more_lines_never_fewer_stations`. |

### Round 1 (after the fix round)

The spec audit returned pass_with_issues (137 passed, 0 failed), as did the proof audit (137 passed, 0 failed). Both audits verified spec-1, spec-2, spec-5(b, c), runtime-2, runtime-3, runtime-4 and runtime-5 as resolved (Proof 8). No fix round followed round 1.

| # | Auditor | Severity | Finding | Resolution |
|---|---|---|---|---|
| R1-a | spec + proof | low | Carried over (spec-3): the size-level T6.5 leaves pickers, carts and forklifts out. | **Deferred** to the register (I17 ruling). Open issue 1. |
| R1-b | spec + proof | low | Carried over (spec-4, runtime-1): F_UNSTABLE:packing for every family (I24 vs I45). I45 is unchanged in the register. | **Deferred** to the register or an expert. Open issue 2. |
| R1-c | spec + proof | low | Carried over (spec-5a), plus a new register gap. I47 gives no amr_gtp figure (the engine gives 49), and I5 (`INTERPRETATIONS.md:38`) still says "warning F_SHORT_HISTORY", while result.json now carries `info`. | **Deferred.** `docs/INTERPRETATIONS.md` is outside the F6z paths. Open issue 3. |
| R1-d | spec | low (nit) | NEW: `size.py:162-164` remaps **every** design-day flag to `info`, not only the three codes the F6 table lists. A future F4 warning-class flag would be silently downgraded. This is harmless today: the only other F4 flag, F_DEFAULT_UPP, is already `info` (I59). | **Not fixed** (no round 2). Open issue 4. |
| R1-e | proof | low (nit) | NEW: `_check_id` (`size.py:135`) has no length limit. A 300-character id passes the guard, then `mkdir` raises a raw OSError (Errno 63, File name too long) instead of ConfigError. This is not normal input. | **Not fixed** (no round 2). Open issue 5. |

## Open issues

1. **T6.5 and pickers (register, I17).** When design stock grows with demand, `pickers_peak` is not monotone. On S2, m = 1 to 4 takes it from 2 to 1 while picking hours grow from 6.34 to 25.77. Overflow SKUs move from shelving to pallet_rack under the F6a class rule on the design stock cube, and the per-zone ceil (I17) then collapses (1+1 → 0+1). The engine is spec-literal. The size-level T6.5 test leaves pickers, carts and forklifts out, and its docstring says why. Pickers are covered only at constant stock (`test_f6_throughput_properties.py`). This needs a ruling on whether the spec's T6.5 applies to pickers.
2. **F_UNSTABLE:packing on every family with the example basis (register/expert, I24 vs I45).** Pack stations are sized on `peak_hour_orders`, but the queue arrival rate takes `same_day_share × orders / sla_window_hours`. With same-day 0.6 and a 3.5 h window, the SLA term binds, so the pool is unstable by construction. It shows on ecom_mid (all 3 families, in the fresh e2e output below) and on b2b_cases (all 9 runs).
3. **Register gaps in `docs/INTERPRETATIONS.md` (outside the F6z paths).** (a) I47 gives no amr_gtp F_LOW_CONFIDENCE figure. The engine gives 49: amr_gtp 19 (without `amr_gtp.m2_per_robot_parking`, per I26) + `cube_asrs.m2_per_robot_parking` + manual overflow 17 + labor 9 + finance 2 + engine 1. A family-prefix reading would give 50. (b) I5 still says "warning F_SHORT_HISTORY". result.json now carries `info` per the F6 table, while F4's `design_day.json` and `test_f4_register.py:189` keep `warning`. The register owner should record the split, or F4 should emit `info`.
4. **Severity remap too broad (`size.py:164`, nit).** Every design-day flag is remapped to `info`, not only F_SHORT_HISTORY, F_RATIO_DRIFT:<m> and F_PERCENTILE_CLIPPED. No output is wrong today.
5. **No length limit in `_check_id` (`size.py:135`, nit).** A very long scenario id gives a raw OSError instead of ConfigError.
6. **`ScenarioDef.id` has no pattern in the schema (F0).** The `[A-Za-z0-9_-]+` guard lives only in `engine/size.py`. F8 should validate project YAML ids at load time. A schema pattern would be a non-additive F0 change.
7. **Shift `end_hour` can exceed 24** for a shift that wraps past midnight (e.g. 26.0 means 02:00 the next day; end − start always equals hours_per_shift). The F9 report should show `end_hour mod 24` as clock time.
8. **Register check still owed (from F6a/F6c).** The F6c open items 8-11 and 13 (receipts-mode daily inbound, multi-shift conventions, floor-1 per shift, non-operating-day receipts, I15 daily split) are assumed to be covered by I64/I65/I66; the register owner should confirm they are complete. Also open from F6a: AMR A_storage = pod area, and F_SCALE_LOW raised for every family.
9. **Float fragility (F6a open issue 7).** A design day 1 ULP different can flip a ceil (1918 vs 1919 pallets). The test harness `tests/unit/test_f6_inputs.py::build` now sums `stock_units` in SKU order, which stops the stored Hypothesis example from failing. The engine is unchanged.
10. **`profile` is unused** in `size_scenario`. It is kept only for the I61 signature.
11. **Inherited items that are still open or whose status is unknown.** See the next subsection: F6a #2, #3, #6 (partly), #7, #10 and #11; F6c #2, #8-11, #13 and #14 (partly).

### Inherited open issues (from `docs/audit/F6a.md`, `F6c.md` and `F6d.md`)

Each item below was checked against the audit history and the code while writing this record. "Unknown" means the F6z audit history does not mention the item; it is carried forward, not dropped.

| Source | Item | Status after F6z |
|---|---|---|
| F6a #1 | lo/hi worlds traced in full, against ADR-002 | **Closed by register.** I62 (`INTERPRETATIONS.md:494-501`) says all three worlds are traced in full, which supersedes ADR-002. No code changed. Proof 9 shows the node counts. |
| F6a #2 | AMR `A_storage` = pod_bin area, with no register entry | **Open** (register; listed in the blockers). |
| F6a #3 | F_SCALE_LOW raised for every family, against I46's "cube" | **Open** (register; listed in the blockers). |
| F6a #4 | the `decant_cases_in` trace lacks pack-data inputs | **Closed.** It now lists upc/upp/cpp, pinned by `test_decant_cases_in_lists_its_pack_data_and_amr_parks_on_the_cube_param`. |
| F6a #5 | the T6.5 storage clause can never fail | **Closed.** The size-level T6.5 scales stock and asserts strict storage growth. The dead clause was removed from `test_f6_throughput_properties.py`. |
| F6a #6 | T6.8 is blind to a missing SKU sort on the manual path | **Mitigated.** The size-level T6.8 catches it through S1/S2 (probe5: 10/10). For S0 it is still not caught (0/10), because S0's output is order-invariant at these sizes. The date sort on the manual path has its own mutation test. |
| F6a #7 | design-stock 1-ULP fragility | **Open** (open issue 9). Only the test harness changed. |
| F6a #8 | oracle bare floor (G1 owner) | **Closed** (not in the history; re-checked while writing this record). `tests/golden/oracle.py:299` now reads `math.floor(usable_height_m / pitch_m + 1e-9)`. |
| F6a #9 | `.gitignore` lacks `.hypothesis/` | **Closed.** `.gitignore:12` now has it, so the engineer's blocker is stale. |
| F6a #10 | for AMR/cube, an SKU table with zero shipped units raises WhsizingError in derived inbound | **Unknown.** It is not in the F6z history and was not re-checked. |
| F6a #11 | 12 build-time interpretations are not in the register | **Unknown**, except #2 and #3 above, which the blockers name. |
| F6c #1 | `size_scenario` must pass the shipped lines to labor | **Closed.** `lines=t.lines` (I61, I66); T6.2 matches 257 keys through `size_scenario`. |
| F6c #2 | receipts mode with lumpy receipts puts most inbound hours above the P50 day | **Unknown / open.** It is not in the F6z history. The b2b receipts 3×8 run still shows a large temp share (cube: temp_y1 9276 of annual_y1 13550). Needs an expert or register decision before F7. |
| F6c #3 | `units_in* = 0` in receipts mode drops decant | **Closed** (I64). `test_receipts_mode_without_design_receipts_keeps_decant_and_pallets`. |
| F6c #4-6 | duplicate daily dates, null `is_operating`, non-numeric `qty_units` | **Closed.** They raise DataQualityError (`test_bad_daily_or_lines_raise_data_quality_errors`). |
| F6c #7 | ShiftRow start/end hours are untraced | **Closed.** They are traced and checked by T6.11; end = start + length (runtime-3). |
| F6c #8-11, #13 | register entries: receipts-mode daily inbound, multi-shift conventions, floor 1 per shift, non-operating-day receipts, I15 daily split | **Open** (a register completeness check against I64/I65/I66 is owed; open issue 8). |
| F6c #12 | `engine/__init__.py` does not re-export the labor API | **Closed.** It re-exports the labor, area, queue and size APIs. |
| F6c #14 | test-strength caveats (T6.5 exemptions, T6.6 indirect share, T6.7 by construction) | **Partly open.** T6.7 now has a size-level world-order check that can fail. T6.6 still cannot catch a mis-scaled indirect share; the round-0 spec audit says that caveat still applies. |
| F6d #1 | `queue_resource` raises builtin errors for NaN/inf | **Closed.** It raises WhsizingError (`test_queue_resource_rejects_non_finite_rates[*]`). |
| F6d #2 | robot parking does not use `cube_asrs.m2_per_robot_parking` (I26) | **Closed.** `test_T1_5_amr_robot_parking_reads_the_cube_param` passes. |
| F6d #3 | lo/hi-only flags are dropped | **Closed by register.** I62: flags come from the typ world. |
| F6d #4 | area/queue are not exported from `whsizing.engine` | **Closed.** |
| F6d #5 | the schema comment says `gtp_ports` | **Closed** (comment fix in an F0 path, disclosed). |
| F6d #6 | share_S comes from two sources | **Closed.** One source, `LaborDays.single_line_share`. |
| F6d #7 | tautological Range assertion | **Closed.** The test now asserts a strict world order. |
| F6d #8 | no area/queue coverage for T6.5, T6.7 or T6.8 | **Closed.** The size-level T6.5 checks every area zone, T6.7 checks every result number including queue, and T6.8 checks the full `result.json`. |
| F6d #9 | the T6.3 golden test injects the golden roster | **Closed.** `test_T6_3_area_docks_queue_through_size_scenario` uses the real F6c roster. |

## Not applicable here and why

- **T6.9 rerun from manifest.** Needs F8 (`runs/<id>/manifest.json` and `runs/<id>/inputs`), which is not built. A skip-marked placeholder test exists.
- **F6 "Done when" expert review #1** (one worked example per family). No domain expert is available here. The auditors' hand recomputations (Proofs 1, 2 and 6) are not a substitute for it.
- **Real client data.** All end-to-end evidence uses synthetic profiles (ecom_mid, b2b_cases) and the golden S0/S1/S2 cases.
- **Register edits.** `docs/INTERPRETATIONS.md` is not an F6 path, so the register items above are reported, not fixed.

## Fresh test output (re-run while writing this record)

Command: `uv run pytest tests/unit/test_f6_*.py tests/property/test_f6_*.py tests/golden/test_f6_*.py tests/e2e/test_f6_*.py tests/golden/test_g1_register.py -q -rA` (trimmed to the F6z-relevant PASSED lines, the skip and the summary). The lines left out also passed: the other `tests/golden/test_g1_register.py` tests, `tests/unit/test_f6_inputs.py`, `tests/unit/test_f6_labor.py`, `tests/unit/test_f6_area.py`, the remaining `tests/unit/test_f6_queue.py` tests, and the F6a unit/property tests not listed. 137 passed and 0 failed in total.

```
PASSED tests/unit/test_f6_queue.py::test_T6_4_erlang_c_values
PASSED tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm1_closed_form
PASSED tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm2_closed_form
PASSED tests/unit/test_f6_size.py::test_T6_9_identical_inputs_give_byte_identical_result_json
PASSED tests/unit/test_f6_size.py::test_T6_9_a_fresh_process_writes_the_same_result_json
PASSED tests/unit/test_f6_size.py::test_T6_11_every_number_in_result_json_has_a_trace_node[S0]
PASSED tests/unit/test_f6_size.py::test_T6_11_every_number_in_result_json_has_a_trace_node[S1]
PASSED tests/unit/test_f6_size.py::test_T6_11_every_number_in_result_json_has_a_trace_node[S2]
PASSED tests/unit/test_f6_size.py::test_T6_11_every_number_in_result_json_has_a_trace_node[S9]
PASSED tests/unit/test_f6_size.py::test_zero_eligible_lines_degenerate_to_manual
PASSED tests/unit/test_f6_size.py::test_design_day_flags_carry_the_f6_table_severity_info
PASSED tests/unit/test_f6_size.py::test_no_low_confidence_param_gives_no_low_confidence_flag
PASSED tests/unit/test_f6_size.py::test_scenario_id_must_be_one_safe_path_segment[../escaped]
PASSED tests/unit/test_f6_size.py::test_scenario_id_must_be_one_safe_path_segment[a/b]
PASSED tests/unit/test_f6_size.py::test_scenario_id_must_be_one_safe_path_segment[]
PASSED tests/unit/test_f6_size.py::test_scenario_id_must_be_one_safe_path_segment[.]
PASSED tests/unit/test_f6_size.py::test_scenario_id_must_be_one_safe_path_segment[S 0]
PASSED tests/unit/test_f6_size.py::test_building_below_one_level_gives_one_level_and_height_limit
PASSED tests/unit/test_f6_size.py::test_stock_larger_than_the_building_flags_no_fit_and_continues
PASSED tests/unit/test_f6_size.py::test_shift_end_is_start_plus_length_and_traced[3-6.0-expected0]
PASSED tests/unit/test_f6_size.py::test_shift_end_is_start_plus_length_and_traced[2-10.0-expected1]
PASSED tests/unit/test_f6_size.py::test_shift_end_is_start_plus_length_and_traced[3-8.0-expected2]
PASSED tests/unit/test_f6_size.py::test_decant_cases_in_lists_its_pack_data_and_amr_parks_on_the_cube_param
PASSED tests/unit/test_f6_size.py::test_bad_daily_or_lines_raise_data_quality_errors
PASSED tests/unit/test_f6_size.py::test_inconsistent_inputs_raise_data_quality_errors
PASSED tests/unit/test_f6_size.py::test_queue_resource_rejects_non_finite_rates[nan-10.0-1.0]
PASSED tests/unit/test_f6_size.py::test_queue_resource_rejects_non_finite_rates[inf-10.0-1.0]
PASSED tests/unit/test_f6_size.py::test_queue_resource_rejects_non_finite_rates[5.0-nan-1.0]
PASSED tests/unit/test_f6_size.py::test_queue_resource_rejects_non_finite_rates[5.0-10.0-inf]
PASSED tests/unit/test_f6_size.py::test_receipts_mode_without_design_receipts_keeps_decant_and_pallets
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations[amr_gtp]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[amr_gtp]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[amr_gtp]
PASSED tests/property/test_f6_labor_properties.py::test_T6_6_doubling_lines_and_productivity_leaves_fte_unchanged
PASSED tests/property/test_f6_labor_properties.py::test_T6_5_more_lines_never_fewer_labor_hours_or_fte
PASSED tests/property/test_f6_labor_properties.py::test_T6_7_labor_outputs_non_negative_and_worlds_ordered
PASSED tests/property/test_f6_labor_properties.py::test_T6_8_row_order_does_not_change_labor
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_is_a_probability
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_decreases_with_servers
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_stable_pool_outputs_are_consistent
PASSED tests/property/test_f6_size_properties.py::test_T6_5_more_lines_never_fewer_fte_stations_or_less_area
PASSED tests/property/test_f6_size_properties.py::test_T6_7_outputs_non_negative_and_ranges_ordered
PASSED tests/property/test_f6_size_properties.py::test_T6_8_row_order_of_the_inputs_does_not_change_result_json
PASSED tests/property/test_f6_size_properties.py::test_T6_8_the_check_catches_a_missing_date_sort
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_area_docks_queue_equal_golden
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_results_match_the_trace
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_trace_inputs_resolve
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_hours_heads_equal_golden
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_result_typ_matches_trace
PASSED tests/golden/test_f6_labor_golden.py::test_T6_10_annual_hours_below_design_day_times_operating_days
PASSED tests/golden/test_f6_labor_golden.py::test_T6_2_labor_trace_inputs_resolve
PASSED tests/golden/test_f6_size_golden.py::test_T6_1_storage_throughput_equipment_through_size_scenario
PASSED tests/golden/test_f6_size_golden.py::test_T6_2_labor_through_size_scenario
PASSED tests/golden/test_f6_size_golden.py::test_T6_3_area_docks_queue_through_size_scenario
PASSED tests/golden/test_f6_size_golden.py::test_T6_1_flags_and_low_confidence_count_equal_golden
PASSED tests/golden/test_f6_storage_golden.py::test_T6_1_storage_throughput_equipment_equal_golden
PASSED tests/golden/test_f6_storage_golden.py::test_T6_1_trace_inputs_resolve
PASSED tests/e2e/test_f6_size_e2e.py::test_F6_ecom_mid_three_families_end_to_end
PASSED tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param
SKIPPED [1] tests/unit/test_f6_size.py:150: T6.9 'rerun from manifest' needs F8 (runs/<id>/manifest.json, inputs)
137 passed, 1 skipped in 19.19s
```

The e2e test's printed summary, from a separate re-run of `tests/e2e/test_f6_size_e2e.py -q -rA` (1 passed in 6.23 s):

```
F6 e2e ecom_mid: F1+F2 4.2 s, F3+F4 1.0 s, F6 x3 0.4 s, total 5.6 s
  981,910 shipped lines, design day 3393 lines
  manual_p2p: storage 363 m², area 1049 m² (fit True), roster 42.6, core FTE y1 17.3, ... bottleneck pickers, flags ['F_UNSTABLE:packing', 'F_LOW_CONFIDENCE:30']
  amr_gtp: storage 424 m², area 1199 m² (fit True), roster 32.0, core FTE y1 12.6, ... 'gtp_stations': 3.0, 'robots': 33.0}, bottleneck robots, flags ['F_ROBOT_DENSITY', 'F_UNSTABLE:packing', 'F_LOW_CONFIDENCE:49']
  cube_asrs: storage 145 m², area 1059 m² (fit True), roster 30.9, core FTE y1 11.8, ... 'ports': 8.0, 'robots': 35.0}, bottleneck robots, flags ['F_ROBOT_DENSITY', 'F_UNSTABLE:packing', 'F_LOW_CONFIDENCE:50']
```

Full suite, also re-run while writing this record: `uv run pytest -q` gives `776 passed, 3 skipped in 55.32s` (skips: F7 parity "F7 not built", Docker "Docker not installed", T6.9 manifest).
