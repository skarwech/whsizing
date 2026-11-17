2026-11-08: Superseded in part by docs/audit/G1c.md (I30 floor prep, I47 counts S0=30/S2=50).

# G1b audit: Golden oracle remediation (W1 open findings)

## Verdict: pass_with_issues

All 4 round-0 medium findings were fixed in round 1, and both auditors re-checked them independently: the packing λ_s, the orphan denominators, the assume flag with Kleene logic, and the zero-eligible case that should degenerate to manual. The fresh run gives 24 passed, 0 failed and 6 skipped. The 6 skips are engine-parity placeholders, and the engine stages behind them are still 0-byte stubs.
The verdict stays below `pass` because the round-1 audit raised 10 low findings that were never fixed, since there was no round 2. Two [EXPERT] rulings are also still open (I46 robot density, I48 degenerate costing). Both round-1 auditors (spec and proof) returned `pass_with_issues`.

Schema changes: none (`schema_changes: []`). The oracle does not import `whsizing`. The new files `tests/golden/demand.py` and `tests/golden/workbook.py` sit outside G1b's owned paths (see Open issues).

## Acceptance tests

Statuses are from the final audit (round 1). "Weak" means one auditor showed that the test passes but does not pin part of the rule it claims to cover.

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_spreadsheet_equals_golden_json` | pass (weak, proof auditor) | The xlsx holds the same 737 keys as the JSON, and every stage value cell has a formula comment. It is weak because `workbook.write_json` and `write_xlsx` both write from the same `Out.rows`. The test therefore checks the writer round-trip and the comments, not whether the values are correct. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_build_is_deterministic_and_committed_files_are_current` | pass | Two builds give byte-identical JSON and xlsx, and the committed JSON equals a fresh build, so the golden is not stale after the fix round. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_anchors_match_tiny_golden_readme` | pass | The README anchors hold: 1881 lines, 26 operating days, 100 SKUs, 91 eligible and 90 in stock. |
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_golden_values_respect_spec_invariants` | pass | The hourly sum equals lines* (T4.3), lines* = P95 × gf, the ABC shares hold (T3.2), λ_e + λ_o = λ, and the T6.10 guard holds. Also S2 λ_e = λ × scenario share_lines, ports = ceil(λ_e/(350×0.85) + decant load), and NPV equals `numpy_financial.npv`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_missing_dims_hazmat_temperature_are_ineligible_and_case_fallbacks_hold` | pass (weak, spec auditor) | The full pipeline runs on a defect copy of tiny_golden. Missing dims, hazmat and frozen/chilled SKUs are ineligible, and the upc and unit-cube fallbacks hold. It kills the mutants missing_dims_pass, hazmat_ignored, temperature_ignored, fits_shelf_needs_weight, unit_cube_given_first and upc_fallback_6. It does not pin the I10 given-`unit_cube_m3` fallback or the I13 upp precedence (mutants `no_given_cube_fallback` and `upp_derived_first` survive). |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_assume_eligible_if_missing_dims_raises_F_ELIG_ASSUMED` | pass (weak, spec auditor) | When assume_eligible is on, the assumed share is reported and the `F_ELIG_ASSUMED:<share>` flag is raised. A known violation still means ineligible, so `assume_ignores_known_violation` and `orphan_assumable` are killed. It does not pin the Kleene direction, that is, that a missing dim sorts as the smallest: the mutant `kleene_missing_as_largest` survives. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_orphan_skus_are_kept_never_eligible_and_counted_in_every_share` | pass (weak, spec auditor) | Orphan SKUs are kept as rows and are never eligible. Σ SKU-row lines = profile.n_lines, share_lines counts orphan lines in its denominator, n_skus_total = 101, and λ.pallet_rack includes the orphan lines. The share_skus denominator is not asserted (mutant `share_skus_master_only` survives), although the oracle's value 77/101 is correct. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_sla_window_explicit_derived_midnight_and_equal_times` | pass | Explicit 7.0 h, derived 3.5 h, crossing midnight 4.0 h, equal times = 24 h, and 0 raises. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_explicit_sla_window_drives_lambda_and_dock_shortfall_flag` | pass | An explicit window drives λ_sla and raises `F_DOCK_SHORTFALL`. It kills `explicit_sla_ignored`, `lambda_sla_no_share`, `no_dock_shortfall` and `queue_t_full_window`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_decant_station_hours_add_to_the_ports` | pass | Decant (eligible SKUs only) loads the ports in the inbound peak hour (I23). It kills `decant_not_in_ports`, `decant_no_peak_factor` and `decant_all_skus`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_zero_eligible_lines_degenerate_to_manual` | pass (weak, spec auditor) | At share_lines = 0 the result has F_ELIG_LOW, ports = robots = 0 and 0 cube_bin positions. S2's area, capex, opex and TCO equal S0's, and NPV ≈ 0. It kills `no_degenerate_case` and `degenerate_keeps_cube_costs`. Two things are not pinned. First, the 0 < share < 0.5 band must not degenerate: `degenerate_when_elig_low` survives. Second, eligible SKUs without lines are not exercised: `degenerate_keeps_eligible_set` survives. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_three_inventory_snapshots_are_not_silently_flat` | pass | With ≥ 3 snapshots the oracle raises `NotImplementedError` (I12) and does not silently use Δstock = 0. Kills `snapshots_silent`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_flag_table_and_low_confidence_count` | pass | S0 and S2 flags appear in exact F6-table order. `F_LOW_CONFIDENCE:29` / `:45` and the parameter counts 19+9+1 and 18+17+9+1 hold, and robots_per_grid_m2 is checked. Kills `no_low_confidence`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_erlang_queue_and_sla_flags` | pass | M/M/1 closed forms, the unstable case with c_min, `F_SLA_RISK` and `F_UNSTABLE` hold. The test pins packing λ_s = max(peak_hour_orders, 0.6 × orders*/3.5) and checks that the SLA rate binds. It kills `packing_peak_hour_only`, `packing_sla_lines` and `tail_no_t`. In round 0 this test was weak. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_golden_basis_exercises_pallet_parcel_and_overflow_branches` | pass | Element-wise, pallet order == (weight > 12 kg OR cube > 0.1 m³). The data has multi-parcel orders, shipping_pallet hours and 2 overflow-shelving SKUs. It kills `pallet_weight_only` and `parcels_no_ceil`. |
| T1.5 | `tests/golden/test_g1_remediation.py::test_T1_5_workbook_headers_and_stage_cells_name_their_formula` | pass | Every SKUs/DailySeries column header has a comment (27/27 and 13/13), and every stage comment contains a formula operator. |
| T1.5 (engine parity, T3.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T3_1_profile_stats` | not_applicable (skip) | `src/whsizing/profile/__init__.py` is 0 bytes. |
| T1.5 (engine parity, T4.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T4_1_design_day` | not_applicable (skip) | `src/whsizing/design/__init__.py` is 0 bytes. |
| T1.5 (engine parity, T6.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_1_storage` | not_applicable (skip) | `src/whsizing/engine/__init__.py` is 0 bytes. |
| T1.5 (engine parity, T6.2) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_2_labor` | not_applicable (skip) | The engine stage is a stub. |
| T1.5 (engine parity, T6.3) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T6_3_area_and_docks` | not_applicable (skip) | The engine stage is a stub. |
| T1.5 (engine parity, T7.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T7_1_finance` | not_applicable (skip) | `src/whsizing/finance/__init__.py` is 0 bytes. |

The supporting helper tests in `test_g1_oracle.py` are not tied to a T-id, and all 8 pass: `test_erlang_c_values`, `test_erlang_wq_matches_mm1_closed_form`, `test_payback_interpolation_and_edge_cases`, `test_npv_irr_against_numpy_financial`, `test_levels_and_area_formulas`, `test_positions_formulas`, `test_classification_formulas` and `test_calendar_and_misc_formulas`.

## Proofs (captured by the auditors during the audit)

Scratch scripts live under `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/`, written `$SP/` below. Proofs 1 to 8 come from the round-1 audit, so they describe the files as they are now. Proof 9 was re-run while writing this record.

1. **The golden values were recomputed independently from the parquet files and the spec text, without importing the oracle or `whsizing`, and they still match after the fix round** (spec auditor, round 1).
   Command: `uv run python $SP/audit_G1b/indep.py`
   ```
   OK shipment.mean_parcels_per_order; OK design_day.lines 137.48177797120002; OK S2.eligibility.n_skus_eligible 86;
   OK S2.eligibility.share_lines 0.7410951621477937; OK S0.throughput.lambda_sla 23.568304795062858;
   OK S2.equipment.decant_port_load_peak_h 0.2225988265219796; OK S2.equipment.ports 1;
   OK S0.queue.packing.p_wait 0.3658394931045417 (no DIFF lines)
   ```
2. **The packing queue now uses the F6e SLA-window rate, and that rate binds** (proof auditor, round 1, recomputed from the committed JSON and `golden_basis.yaml` without the oracle).
   Command: `uv run python -I -c '<sla = same_day_share*design_day.orders/window; compare to S*.queue.packing.*>'`
   ```
   S0 window 3.5 sla_rate 11.577412881785264 pho 9.235543039600781 golden λ_s 11.577412881785264 a 0.3658394931045417 mine a 0.3658394931045417 servers 1
   S2 lambda_peak 22.118737531817 lambda_sla 23.568304795062858 lambda 23.568304795062858
   ```
3. **The round-0 divergence script, re-run unchanged, now shows the fixes**: orphan lines are in every denominator, a SKU with a missing dim and a known violation stays ineligible as in the engine, and a SKU with known dims and a null weight fits a shelf (proof auditor, round 1).
   Command: `uv run python $SP/audit_G1b/elig_div.py $SP/audit_G1b/proof_r2`
   ```
   victim A (length null, 40 kg): oracle zone_S2 = pallet_rack | B (weight null): zone_S2 = cube_bin
   victim B dims 120.3 85.0 18.1 fits_shelf True manual_class shelving
   engine eligible_mask A = False  B = True
   oracle S2.eligibility.n_skus_eligible = 90  engine = 90
   profile.n_lines 1901 Σ master-SKU lines 1901
   ```
4. **On defect data, the oracle's S2.eligibility.\* equal the built F5 engine on all 6 EligibilityResult fields, with assume both off and on** (proof auditor, round 1).
   Command: `uv run python $SP/audit_G1b/proof_r2/shares_parity.py $SP/audit_G1b/proof_r2/div`
   ```
   assume=False share_lines oracle=0.8600736454497633 engine=0.8600736454497633 OK ... n_skus_eligible 89/89 OK, n_skus_total 101/101 OK
   assume=True share_lines 0.8605996843766439/0.8605996843766439 OK; share_stock_cube 0.2864952549649766/0.2864952549649765 OK;
   n_skus_eligible 90/90 OK; assumed_share_lines 0.0005260389268805891/0.0005260389268805891 OK
   ```
5. **The oracle's `cube_eligible` (Kleene rule) agrees with the engine's `eligible_mask` on a grid of 500 SKUs with partial dims and weight × 4 configs** (proof auditor, round 1).
   Command: `uv run python $SP/audit_G1b/proof_r2/kleene_parity.py /Users/skarwech/saas_v1`
   ```
   2000 (SKU, cfg) pairs compared, 0 disagreements; first: []
   ```
6. **When nothing is eligible, S2 degenerates to manual (I48).** The manual WMS controls (50 000) and manual software (15 000) replace the cube costs. A never-shipped eligible SKU is not stored in cube bins, and S2 capex equals S0 (proof auditor, round 1). The spec auditor's key-by-key comparison found that only λ_e/λ_o, the flags and the low-confidence count differ, and that NPV = 0.
   Command: `uv run python $SP/audit_G1b/edges.py <dir>; uv run python $SP/audit_G1b/proof_r2/dead_stock.py /Users/skarwech/saas_v1`
   ```
   == zero eligible: S2.eligibility.share_lines 0.0; S2.equipment.ports 0; robots 0; S2.capex.controls 50000.0; S2.opex.y1.software 15000.0;
   S2.flags F_HEIGHT_LIMIT:pallet_rack,F_ELIG_LOW,F_SCALE_LOW,...,F_LOW_CONFIDENCE:45
   dead stock: S2.eligibility.n_skus_eligible 1; S2.storage.cube_bin.n_skus 0; positions 0.0; S2.capex.total 135488.52949750668 == S0.capex.total 135488.52949750668
   ```
7. **Mutation testing, with the golden rebuilt after each value-changing mutant: the fix-round mutants and the prior-audit mutants are killed, and the survivors are named** (both auditors, round 1).
   Commands: `uv run python $SP/G1b/r1/mutate_audit.py <dir>`, `uv run python $SP/audit_G1b/proof_r2/mutate_r2.py <dir>` and `uv run python $SP/audit_G1b/r2_spec/mutate_spec.py $SP/audit_G1b/r2_spec`
   ```
   E_pallet_weight_only KILLED; E_decant_all_skus KILLED; E_unit_cube_given_first KILLED; E_assume_ignores_known_violation KILLED;
   E_fits_shelf_needs_weight KILLED; E_orphans_dropped KILLED; E_orphan_assumable KILLED; E_packing_peak_hour_only KILLED;
   E_no_degenerate_case KILLED; A_missing_dims_pass KILLED; A_degenerate_keeps_cube_costs KILLED
   prior audit harness: 16 of 18 KILLED, 2 SKIPPED (pattern changed; replaced by A_missing_dims_pass and E_unit_cube_given_first, both KILLED)
   missing_dims_pass KILLED; no_given_cube_fallback SURVIVED; kleene_missing_as_largest SURVIVED; upp_derived_first SURVIVED;
   degenerate_when_elig_low SURVIVED; degenerate_keeps_elig SURVIVED; share_skus_master_only SURVIVED
   ```
8. **The build is deterministic across processes and hash seeds, and the committed golden files are byte-identical to a fresh build of 737 values** (proof auditor, round 1).
   Command: `PYTHONHASHSEED=1 uv run python -m tests.golden.build_golden <b1>; PYTHONHASHSEED=999 POLARS_MAX_THREADS=1 uv run python -m tests.golden.build_golden <b2>; shasum ...`
   ```
   de87a48e... b1/golden_case.xlsx = b2 = tests/golden/golden_case.xlsx
   b426d30e... b1/golden_values.json = b2 = tests/golden/golden_values.json
   ```
   Re-run while writing this record: `shasum tests/golden/golden_values.json tests/golden/golden_case.xlsx` gives `b426d30ebe61...` and `de87a48e1eeb...`. The committed files are therefore the ones the auditors proved.
9. **The G1 paths are clean under lint and type checks, and the oracle does not import `whsizing`.** The proof auditor captured this in round 0, and it was re-run while writing this record.
   Command: `uv run ruff check tests/golden/; uv run ruff format --check tests/golden/; uv run pyright tests/golden/`
   ```
   All checks passed!
   8 files already formatted
   0 errors, 0 warnings, 0 informations
   ```
   In round 0, `grep -n whsizing tests/golden/*.py` found only docstring and comment mentions, no import.

## Audit rounds

### Build (before round 0)

The builder addressed all eight W1 findings:

1. Missing dims or weight, hazmat and frozen/chilled SKUs are ineligible, and the case-data fallbacks hold (I13).
2. `sla_window_hours` uses the explicit, derived, midnight-crossing and equal-time (24 h) cases. A value ≤ 0 raises (I16).
3. Decant now loads the ports in the inbound peak hour (I23).
4. Flags follow the full F6 table order (I46). The queue check covers pack stations and ports (I45). `F_LOW_CONFIDENCE:n` gives S0 = 29 and S2 = 45 (I47). `F_PERCENTILE_CLIPPED` is raised.
5. `golden_basis.yaml` now exercises the pallet, multi-parcel and overflow-shelving branches: 39 pallet orders, of which 25 are triggered by weight only and 14 by cube only, plus 2 overflow-shelving SKUs. `golden_scenarios.yaml` sets S2 `extra_max_weight_kg` to 2.0.
6. The workbook's column headers and stage cells name their formula.
7. Six engine-parity skip placeholders were added.
8. The golden was rebuilt with 737 keys, 0 removed, 246 changed and 42 added.

Because of the 800-line cap, the F3 to F5 stages and the writers were split out into `tests/golden/demand.py` and `tests/golden/workbook.py`.

### Round 0: tests 21 passed, 0 failed, 6 skipped

Both the spec audit and the proof audit returned **pass_with_issues**.

| Audit | Severity | Finding | Resolution (round 1) |
|---|---|---|---|
| spec | medium | `build_golden.py:516`: the packing queue used λ_s = peak_hour_orders (9.2355/h), not the F6e SLA-window rate (11.577/h). The ports pool already used λ_sla, so the two pools were inconsistent, and the test did not pin λ_s. | **Fixed.** λ_s = max(peak_hour_orders, same_day_share × orders* / window). The golden arrival_rate_h is now 11.5774 and offered_load 0.3658, with no flag change. The queue test pins λ_s, and the mutant `packing_peak_hour_only` is killed. |
| spec + proof | medium | `demand.py:348/349`: lines of orphan SKUs were dropped from the eligibility share denominators and the zone split, so share_lines and λ_e came out too high. The engine contract says "orphan SKUs included with mask False". | **Fixed.** `demand.with_orphans()` keeps orphans as SKU rows (R2: has_dims = false, never eligible, pallet_rack). Every denominator and n_skus_total now includes them. New test `test_T1_5_orphan_skus_are_kept_never_eligible_and_counted_in_every_share`. The mutant `orphans_dropped` is killed. I6 and I10 were updated. |
| spec + proof | medium | `demand.py:293/303`: with `assume_eligible_if_missing_dims`, a SKU with a missing value was eligible even when a known dim or the weight already broke a limit. The engine's `eligible_mask` disagreed (for example, length null with 40 kg). | **Fixed.** Kleene rule as in the engine: the known dims, sorted descending, are checked against the largest limits, and the known weight against min(max_weight, extra_max_weight). Any known violation means ineligible. New victims were added, and the mutants `assume_ignores_known_violation` and `orphan_assumable` are killed. I10 was rewritten. |
| proof | medium | `build_golden.py:557`: with zero eligible lines, S2 still charged the cube controls (150 000) and the cube software (40 000/yr), against the F6 edge case "degenerates to manual". | **Fixed.** The scenario now degenerates to the manual family (new interpretation I48, still awaiting an [EXPERT] ruling on whether the manual WMS adaptation and software belong). New test `test_T1_5_zero_eligible_lines_degenerate_to_manual`. The mutant `no_degenerate_case` is killed. |
| spec + proof | low | `fits_shelf` required the weight, so a SKU with known dims that fit a shelf bin but a null weight was forced to pallet_rack. | **Fixed.** fits_shelf now depends on l, w and h only. The mutant `fits_shelf_needs_weight` is killed. |
| proof | low | Three mutants survived even after a rebuild: `pallet_weight_only`, `decant_all_skus` and swapped `unit_cube` coalesce order. | **Fixed.** Assertions were added: pallet orders are checked element-wise, decant workload = Σ cases_in of the S2 cube_bin SKUs, and the unit cube is derived first (l×w×h/1e9, as in F2), with a `bogus_cube` victim. All three are now killed. |
| spec + proof | low | Workbook: the SKUs and DailySeries data cells have no comment, there are no live Excel formulas, and 19 stage comments were in words. | **Partly fixed.** The header-carries-the-formula convention is now registered in the INTERPRETATIONS.md golden case notes. The word-only stage comments now give a formula, and the regex was tightened. The literal "every cell has a comment" is still not met for the data cells. This deviation is deliberate and registered. |
| proof | low | `demand.py:497`: Δstock was hard-coded to 0 for any number of inventory snapshots. | **Fixed (no longer silent).** With ≥ 3 snapshots the oracle raises `NotImplementedError` (I12). The OLS slope is still not computed. New test `test_T1_5_three_inventory_snapshots_are_not_silently_flat`. |
| spec + proof | low | Scope and size: `demand.py` and `workbook.py` are outside the owned paths, `build_golden.py` has 769 lines, and several functions have more than 50 lines. | **Deferred.** Folding the files back would break the 800-line cap. The builder asked for both files to be added to G1b's owned paths. |

In round 1 the builder recorded 8 entries as fixed (one of them only partly) and deferred 1. They also listed blockers: the owned-paths gap, `docs/audit/G1.md` describing the pre-fix state (that file is not owned by G1b), and the [EXPERT] ruling on I48.

### Round 1: tests 24 passed, 0 failed, 6 skipped

Both the spec audit and the proof audit returned **pass_with_issues**. Every finding is low. The spec auditor raised 6 and the proof auditor raised 4, with some overlap. There was no round 2, so none of them has been fixed.

| Audit | Severity | Finding | Resolution |
|---|---|---|---|
| proof | low | `demand.py:379`: `eligibility()` divides by the total stock cube without a guard. It crashes with a bare `ZeroDivisionError` when no SKU has dims or unit_cube_m3, or when the inventory is empty. The engine's `_share` returns 0.0 there, and the oracle's convention elsewhere is a `ValueError` with a message. | **Open** (no round-2 fix). |
| spec + proof | low | Test strength: the Kleene direction is not pinned. A mutant that compares the known dims with the smallest limits (`kleene_missing_as_largest`) passes every test, yet it disagrees with the engine on 105 of 2000 partial-dims pairs. The fixture that would catch it (length null, width 550, height 350) is missing. The proof auditor's finding has a second part, "(2) D …", which is clipped in the audit history. | **Open.** The oracle itself matches the engine (proof 5). |
| spec | low | `demand.py:70`: two latent oracle fallbacks act on inputs that F2 never produces, and no test pins them. The I13 `coalesce(units_per_pallet, upc × cpp, 400)` prefers a given upp, while F2 `canonical.derive` overwrites it. The I10 fallback to the given `unit_cube_m3` when a dim is missing is also unpinned (mutants `upp_derived_first` and `no_given_cube_fallback` survive). | **Open.** These fallbacks have no effect on tiny_golden (upp == upc×cpp for all 100 SKUs, max cube difference 2.2e-16), so no golden value is affected. |
| spec + proof | low | Test strength: the degenerate branch is pinned only at share_lines == 0. The 0 < share < 0.5 band (`degenerate_when_elig_low`) and the I48 rule for eligible SKUs without lines (`degenerate_keeps_elig` / `degenerate_keeps_eligible_set`) survive. On dead-stock data the second mutant would store a never-shipped SKU in cube bins. | **Open.** The oracle behaves correctly in the band (at extra 0.2, share 0.3355 with F_ELIG_LOW, ports = 1 and controls = 150 000) and on dead stock (proof 6). |
| spec | low | Test strength: the share_skus denominator with orphans is not asserted (mutant `share_skus_master_only` survives). | **Open.** The oracle value, 0.7624 = 77/101, equals the engine's. |
| spec | low | The workbook still has no comments on the data cells of SKUs and DailySeries, and no live Excel formulas. | **Accepted as a registered deviation** in the INTERPRETATIONS.md golden case notes. Still open against the literal F1 wording. |
| spec + proof | low | Scope and size, unresolved and slightly worse: `demand.py` (634 lines, edited again in round 1) and `workbook.py` are still outside the owned paths. `build_golden.py` has 775 lines. Functions over 50 lines: demand.profile 110, demand.design_day 94, build_golden.labor 83, and the test fixture defect_data 70 (was 55). | **Open / deferred.** Needs an owned-paths decision by the orchestrator. |

## Open issues

- **Round-1 lows, all unfixed:**
  - The `ZeroDivisionError` on a zero total stock cube.
  - Unpinned rules: the Kleene direction, the upp precedence, the given-unit_cube fallback, the 0 < share < 0.5 band, the I48 rule for eligible SKUs without lines, and the share_skus denominator.
  - The workbook data cells carry no comment.
  - Scope and size (see the round-1 table).
- **[EXPERT] rulings needed:**
  - I46 `F_ROBOT_DENSITY`: the spec gives no value for "max robots per m² of grid". The oracle writes `S2.equipment.robots_per_grid_m2` = 0.4747 and raises no flag. `catalog/families/cube_asrs.yaml:33` carries a 0.05 analog with no spec origin, and under that value the engine would flag S2 while the golden would not.
  - I48: whether a degenerate cube scenario carries the manual WMS adaptation (50 000) and the manual software (15 000/yr), or zero.
- **The engine (F3, F4, F6, F7) must adopt or contest these interpretations:**
  - (a) cutoff == departure gives a 24 h SLA window, and an explicit window ≤ 0 raises (I16);
  - (b) the units_per_case fallback chain (I13);
  - (c) decant at the ports in the inbound peak hour, without oee on the decant term (I23);
  - (d) the F_LOW_CONFIDENCE count S0 = 29, S2 = 45 (I47);
  - (e) `eligibility.cube_asrs.*` uses the default config, while `S2.eligibility.*` uses the scenario config (I44);
  - (f) the queue inputs per pool, including packing λ_s = max(peak hour, SLA rate) (I45);
  - plus I48, and the round-1 orphan and Kleene semantics in I6 and I10.
- **INTERPRETATIONS.md drift.** This file is owned by G1b. The G1b auditors did not raise these two points; they come from the F5b audit record and were confirmed while writing this record.
  - I47 (line 339) still quotes the catalog-wide TODO count as 68. The F5b record says the catalog now has 72 params, and 21 of them are cube params.
  - I30 (line 230) still takes cube floor prep = 0. Catalog 0.2.0 has `cube_asrs.floor_prep_per_m2_eur` 10/20/40, so T7.1 will diverge once F7 uses it.
- **Owned-paths gap:** `tests/golden/demand.py` and `tests/golden/workbook.py` are not on G1b's list.
- **Stale record:** `docs/audit/G1.md` still describes the pre-fix state. It is not owned by G1b.
- **Oracle scope limits:**
  - Typical world only, one shift (I19), and the S0/S2 families only. Any other family raises `NotImplementedError`.
  - With ≥ 3 inventory snapshots it raises instead of computing the OLS Δstock.
  - Because of the no-import rule it raises `ValueError` and `NotImplementedError` rather than the `whsizing.errors` classes.
- **Cosmetic:** the `robots_per_grid_m2` key sits on the Queue sheet rather than on Throughput. Its JSON value is unaffected.
- **Cleared since the build:** the build reported that the whole-repo gate `tests/unit/test_f0_tooling.py::test_T0_1` failed (ruff/pyright in F2 files). Re-run while writing this record, it gives `5 passed`.

## Not applicable here and why

- **Engine parity (6 skips):** `src/whsizing/{profile,design,engine,finance}/__init__.py` are 0-byte stubs (`wc -c` gives 0 for all four), so the engine side of T1.5 cannot run. Each comparison belongs to the owning feature's golden test (T3.1, T4.1, T6.1 to T6.3, T7.1).
- **[EXPERT] review:** I46 robot density, I48 degenerate costing, and the confidence-L parameters behind `F_LOW_CONFIDENCE` need a warehouse-automation domain expert.
- **Real client data:** none is available. The oracle was exercised on tiny_golden, on defect copies of it (null dims and weight, hazmat, frozen/chilled, orphans, bogus cube), and on the auditors' edge-case and 500-SKU parity grids.
- **Docker and GitHub CI:** the G1 golden tests depend on neither.
- **`whsizing.errors` classes:** the oracle must not import `whsizing`, so it cannot raise them. This is by design.

## Fresh test output (run while writing this record, 2026-11-08)

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/golden/test_g1_*.py -q -rA
ssssss........................                                           [100%]
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
SKIPPED [1] tests/golden/test_g1_engine_parity.py:15: engine stage not built yet; implemented in the feature's own golden test (T3.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:21: engine stage not built yet; implemented in the feature's own golden test (T4.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:27: engine stage not built yet; implemented in the feature's own golden test (T6.1)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:33: engine stage not built yet; implemented in the feature's own golden test (T6.2)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:39: engine stage not built yet; implemented in the feature's own golden test (T6.3)
SKIPPED [1] tests/golden/test_g1_engine_parity.py:45: engine stage not built yet; implemented in the feature's own golden test (T7.1)
24 passed, 6 skipped in 0.92s
```
