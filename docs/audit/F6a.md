# F6a audit: Sizing engine core (inputs, storage, throughput and equipment, trace)

## Verdict: pass_with_issues

All F6a/F6b acceptance tests (T6.1, plus the F6a/F6b parts of T6.5, T6.7 and T6.8) pass: 37 passed, 0 failed, 0 skipped. The golden T6.1 check compares 74 keys with 0 mismatches. Engine files are clean under ruff and pyright.
The verdict stays below `pass` because 7 low findings from round 1 are still open (plus 4 further items in "Open issues"). Among them: lo/hi worlds are traced in full, two interpretations are missing from the register, one trace node lists too few inputs, and one T6.5 clause can never fail. Both round-1 auditors returned pass_with_issues.

Scope: F6a (inputs, classification, storage), F6b (throughput, equipment, utilisation, bottleneck) and the F6f trace for those nodes. Labor (F6c), area/docks/ICPE (F6d), queue (F6e) and `size_scenario` (F6z) are out of scope. No `labor.py`, `area.py`, `queue.py` or `size.py` was created. Schema changes: none (`schema_changes: []`).

Files: `src/whsizing/engine/{__init__,inputs,classify,storage,throughput}.py`, `tests/unit/test_f6_inputs.py`, `tests/unit/test_f6_storage.py`, `tests/unit/test_f6_throughput.py`, `tests/unit/test_f6_throughput_properties.py` (added in round 1), `tests/golden/test_f6_storage_golden.py`.

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T6.1 | `tests/golden/test_f6_storage_golden.py::test_T6_1_storage_throughput_equipment_equal_golden` | pass | Builds the S0 and S2 cases end to end from `tiny_golden`: F3 `build_tables`/`profile_from_tables`, I58 `sku_frame`, F4 `select_design_day(sku=...)`, then the engine in the typ world. It compares all 74 golden keys under `S0.`/`S2.` storage, throughput, equipment, utilisation, eligibility and bottleneck. Integers must match exactly and other values within 0.5 %. The assert `len(golden) == 74` is deliberate: if the golden file gains keys under these prefixes, the test fails until they are compared. |
| T6.1 | `tests/golden/test_f6_storage_golden.py::test_T6_1_trace_inputs_resolve` | pass | F6f trace integrity on S0 and S2: every input of every node is a catalog id (`param:`), a named datum (`data:`) or an existing node of the same tracer and world. Scope equals the scenario id. |
| T6.5 (F6b part) | `tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations_or_less_storage[manual_p2p\|cube_asrs\|amr_gtp]` | pass | Hypothesis test, 25 examples per family, checked in the lo, typ and hi worlds. Every design-day flow (lines, peak-hour lines, units, pallets_out, inbound units/pallets/receipt lines/trucks) is scaled by a factor in [1, 8]. No equipment count may go down: pickers per zone, pickers_peak, carts, forklifts, ports, gtp_stations and robots. Mutation testing showed the equipment clause is real. The storage-area clause can never fail (open issue 5). The FTE and area-budget parts of T6.5 belong to F6c/F6d. Added in round 1. |
| T6.7 (F6a/F6b part) | `tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[*]` | pass | Hypothesis test on generated SKU frames: 1-12 rows, dims random or None, pack data None or 1-500, hazmat, design-day scale k in [0.05, 20]. Asserts that every traced value is >= 0, that the `storage_result` Ranges validate, and the ADR-002 ordering (lo world >= typ >= hi world) for class positions and area, total area and every equipment count. The Range check (`lo <= typ <= hi`) holds by construction; the world ordering is the part that can fail. Moved from a single-fixture example test in round 1. |
| T6.8 (F6a/F6b part) | `tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[*]` | pass | Draws a permutation of the SKU rows and compares the full trace `{(id, world): value}` exactly, plus bottleneck and flags in every world. Moved from one fixed shuffle to a hypothesis permutation in round 1. |
| T6.2 | none | not_applicable | Labor golden. Belongs to F6c. |
| T6.3 | none | not_applicable | Area budget and docks golden. Belongs to F6d. |
| T6.4 | none | not_applicable | Erlang-C. Belongs to F6e. |
| T6.6 | none | not_applicable | FTE invariance under doubling. Belongs to F6c. |
| T6.9 | none | not_applicable | Rerun from manifest and result.json. Belongs to F6z/F8. The auditors checked engine determinism separately (thread counts and shuffles, see Proofs). |
| T6.10 | none | not_applicable | Annual hours. Belongs to F6c. |
| T6.11 | none | not_applicable | Every result.json number has a TraceNode. Belongs to F6z. `test_T6_1_trace_inputs_resolve` covers it in part for the F6a/F6b nodes. |

Supporting tests not tied to a T-id (all pass). They check hand-computed numbers:

- **Storage** (`tests/unit/test_f6_storage.py`):
  - shelf fit (orientation-agnostic, needs every dim) and the manual class rule;
  - pallet rack pallets, pick faces, positions, levels and area;
  - levels at 12, 8.5, 5 and 1.5 m (below one level gives levels = 1 and F_HEIGHT_LIMIT);
  - `test_levels_exact_at_heights_that_are_whole_pitches[pallet_rack|cube_bin]` (added in round 1; it failed before the fix);
  - shelving bins; cube mixed bins, empty-bin reserve, grid area and overflow; pod bins and pods;
  - StorageResult range mapping and the F_ELIG_LOW copy.
- **Throughput** (`tests/unit/test_f6_throughput.py`):
  - λ is the max of the peak and SLA flows;
  - manual pickers by zone, carts, replenishment and forklifts;
  - cube ports with decant, robots, F_SCALE_LOW and F_ROBOT_DENSITY;
  - the AMR worked example (hand computation in the docstring; 200 decant cases since round 1);
  - bottleneck tie order.
- **Inputs** (`tests/unit/test_f6_inputs.py`):
  - `sku_frame` joins pack, hazmat and temperature data, and gives null columns when there is no master;
  - missing required columns are rejected;
  - design stock is allocated in proportion to average stock;
  - the manual family takes every SKU;
  - the cube uses scenario eligibility and sends the rest to overflow;
  - I48: zero eligible lines falls back to manual;
  - `to_range` orders worlds by value.

## Proofs (captured by the auditors during the audit)

The auditors captured these proofs during rounds 0 and 1; they were not re-run for this record. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F6a/`, written `$S` below. All commands ran from `/Users/skarwech/saas_v1`. Some command lines were cut off in the audit history; they are marked "(clipped)".

1. **T6.1 parity, checked independently: 74 of 74 golden keys, none missing, max relative error 4.36e-16.** (Round-0 proof audit.)
   Command: `uv run python $S/golden_side.py`
   ```
   keys 74 missing [] max rel err 4.358713468611565e-16
     S0.storage.pallet_rack.positions: golden=67.76470588235294 engine=67.76470588235294
     S2.storage.cube_bin.positions: golden=252.78750000000002 engine=252.78750000000002
     S2.equipment.ports: golden=1 engine=1.0
     S2.equipment.robots: golden=2 engine=2.0
     S0.bottleneck: golden=pickers engine=pickers
     S2.bottleneck: golden=robots engine=robots
   ```

2. **A hand computation with catalog values typed in by hand matches the engine in every world and family.** It covers storage (positions, levels, grid, area, height utilisation), throughput (λ_e, pickers, replenishment, forklift moves), the cube (cases_in 680, decant, ports, robots, density) and AMR. (Round-1 spec audit.)
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/r2/hand2.py`
   ```
   lo cube ports 5 robots 19
   typ cube ports 3 robots 8
   hi cube ports 3 robots 4
   mismatches: 0
   ```

3. **The level-floor fix is exact.** `storage._fit` equals the exact rational floor for pallet rack and cube bin at every clear height from 0.001 to 40 m in 1 mm steps, and from 0.01 to 60 m in 1 cm steps. The 7.8 m cube case that gave 19 levels in round 0 now gives 20, with no false flag. (Round-1 spec and proof audits.)
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/r2/fit_sweep.py` ; `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/levels_float.py`
   ```
   shelving 5
   mismatches (1 cm sweep): 0 []
   mismatches (1 mm sweep): 0 []
   levels(-0.5) (1, True)
   ...
   H=4.5: cube levels=10 ... H=7.8: cube levels=20 (... expected 20), flags=['F_HEIGHT_LIMIT:pallet_rack']
   ```

4. **The property tests catch planted defects** (mutation testing on shadow copies of the package). m1 (equipment count made non-monotone) fails T6.5 in all 3 families. m2 (pick-rate world swapped) fails T6.7 in all 3. m3 (sort by sku removed) fails T6.8 for cube and AMR. (Round-1 proof audit.)
   Command: `for m in m1 m2 m3; do PYTHONPATH=$S/r2/$m:/Users/skarwech/saas_v1 uv run pytest tests/unit/test_f6_throughput_properties.py -q -p no:cacheprovider | tail -1; don…` (clipped)
   ```
   m1: FAILED ...test_T6_5_...[manual_p2p] [cube_asrs] [amr_gtp] -> 6 failed, 3 passed
   m2: FAILED ...test_T6_7_...[manual_p2p] [cube_asrs] [amr_gtp] -> 3 failed, 6 passed
   m3: FAILED ...test_T6_8_...[cube_asrs] [amr_gtp] -> 2 failed, 7 passed
   ```
   The round-1 spec audit found the same with its own mutants: M1 (replenishment inverse to flow) caught by T6.5, M2 (pallet_rack fill pessimistic end swapped) caught by T6.7 (`positions [2.11, 2.18, 2.25]`), and M4 (sort removed) caught for amr_gtp only.

5. **The property tests are not flaky.** With `max_examples` raised from 25 to 400, all 9 parametrized tests pass. (Round-1 proof audit. A second run at 150 examples per family also passed: "150 passing, 0 failing ... 9 passed in 31.39s".)
   Command: `cd $S/r2/stress && PYTHONPATH=/Users/skarwech/saas_v1 uv run --project /Users/skarwech/saas_v1 pytest test_stress_props.py -q -p no:cacheprovider`
   ```
   9 passed in 80.20s (0:01:20)
   ```

6. **Every trace input resolves, for 3 families x 3 worlds.** Since round 1, equipment counts use unit `-`, every typ node has inputs, and `max_robots_per_m2`, `pallet_threshold`, the shelf constants and `default_units_per_pallet` are traced. (Round-0 and round-1 proof audits.)
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/trace_refs.py` ; `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/r2/trace_check.py`
   ```
   manual_p2p nodes 120 unresolved []
   cube_asrs nodes 171 unresolved []
   amr_gtp nodes 159 unresolved []
   ...
   cube_asrs read-not-traced: [('cube_asrs.min_scale_lines_day','const'), ('engine.elig_low_line_share','const'), ('engine.receipt_lines_per_pallet_full','const'), ('engine.receipt_lines_per_pallet_mixed','const')]
     unresolved: []  per-world: {'lo': 57, 'typ': 57, 'hi': 57}
     equipment units: {... 'ports': '-', 'robots': '-'}
   ```

7. **End to end on synthetic ecom_mid (5000 SKUs, about 1 M lines).** The chain F1 → F3 → I58 → F4 → F6a/F6b runs in 3 families x 3 worlds with no negative or NaN node, equipment ordered lo >= typ >= hi, and each scenario under 0.1 s. (Rounds 0 and 1.)
   Command: `uv run python $S/e2e_synth.py data/synth/profiles/ecom_mid.yaml $S/ecom`
   ```
   S2 cube_asrs: 171 nodes in 0.09s; negative/NaN nodes=[]
     main cube_bin n= 4414 lv=20 pos=4572.2/4691.9/4989.1 area=72.6/84.5/103.6
     lam=581.6 lam_e=578.8 equipment(lo/typ/hi)={... 'ports': (11, 8, 6), 'robots': (86, 35, 15)}
     bottleneck=robots flags=['F_ROBOT_DENSITY']
     equipment not monotone lo>=typ>=hi: {}
   ```

8. **Deterministic.** All 450 trace values are bit-identical across Polars thread counts (1, 3, default), and shuffling the 5000-row SKU frame gives identical output. (Round-0 and round-1 proof audits.)
   Command: `POLARS_MAX_THREADS=1 uv run python $S/dump_trace.py $S/ecom $S/t1.json; uv run python $S/dump_trace.py $S/ecom $S/tN.json; POLARS_MAX_THREADS=3 uv run python $S/…` (clipped) ; `for s in '' --shuffle; do PYTHONPATH=. uv run python $S/e2e_synth.py data/synth/profiles/ecom_mid.yaml $S/ecom $s | …` (clipped)
   ```
   450 nodes
   450 nodes
   450 nodes
   IDENTICAL_ACROSS_THREADS
   ...
   IDENTICAL
   ```

9. **Hazmat and frozen SKUs are kept out of the automated classes.** The master carries `hazmat` (Boolean) and `temperature_class` (Categorical). The cube keeps ambient and chilled SKUs; AMR keeps ambient only. (Round-0 proof audit.)
   Command: `uv run python $S/hazmat_check2.py $S/ecom`
   ```
   frame dtypes: {'hazmat': 'Boolean', 'temperature_class': 'Categorical'}
   cube_asrs share_lines 0.7909 hazmat eligible: 0 | temp of eligible: ['ambient', 'chilled']
   amr_gtp share_lines 0.7114 hazmat eligible: 0 | temp of eligible: ['ambient']
   ```

10. **Edge cases fail cleanly or follow the spec's edge-case rules.** upp = 0 and negative stock raise `WhsizingError`. A 1.0 m building gives levels = 1 with F_HEIGHT_LIMIT. Zero eligible lines in AMR falls back to manual. A cube run with zero shipped units raises. (Rounds 0 and 1.)
    Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $S/edges.py`
    ```
    [RAISE] upp=0 pallet SKU: WhsizingError: S9: units_per_pallet ≤ 0 for a pallet-rack SKU
    [RAISE] negative avg_stock manual: WhsizingError: eligibility_shares: stock_by_sku has NaN or negative values
    [OK]   clear height 1.0 m cube: ([('cube_bin', 1), ('pallet_rack', 1), ('shelving', 5)], 1.55, ['F_HEIGHT_LIMIT:cube_bin', 'F_HEIGHT_LIMIT:pallet_rack'])
    [OK]   amr zero eligible lines: (['shelving', 'pallet_rack'], {... 'gtp_stations': 0, 'robots': 0}, [])
    [RAISE] cube with zero shipped units: WhsizingError: derived inbound: no shipped units in the SKU table
    ```

## Audit rounds

### Build (before round 0)

The engineer reported T6.1 (2 functions), T6.7 and T6.8 as passing, with T6.7 and T6.8 limited to their F6a/F6b part. No T6.5 test was written. The build notes list 12 interpretations that are not in the register (for F6z and the reviewer):

- design stock is allocated by an average-stock ratio;
- manual eligibility is all-true;
- AMR density uses the pod_bin area;
- F_HEIGHT_LIMIT is raised on empty overflow classes;
- shelf bins use `storage.shelf_bin_net_cube_m3`;
- the height_utilisation definition;
- utilisation is computed before ceil;
- replenishment counts only manual-zone A/B SKUs;
- lo/hi worlds are traced in full;
- the equipment key names;
- F_SCALE_LOW is checked for every family;
- levels use plain floor and counts plain ceil (floor changed in round 1).

Build-time blocker: `tests/property/test_f3_properties.py::test_T3_7_*` failed on a last-digit float equality (F3). Re-checked while writing this record (2026-11-08): it now passes (`2 passed`).

### Round 0: tests 32 passed, 0 failed. Both auditors: fail

| # | Severity | Finding | Raised by | Resolution |
|---|---|---|---|---|
| 1 | high | No T6.5 test for its F6b clause (stations, ports, robots and pickers must not decrease when lines grow). The behaviour itself held in scratch runs (×1 to ×8, and 60 random scales x 3 families x 3 worlds: 0 violations). | spec, proof | **fixed**: hypothesis test `test_T6_5_more_lines_never_fewer_stations_or_less_storage`. |
| 2 | medium | `storage.py:144` used a plain float `math.floor`. It gave one level too few at clear heights that are a whole number of pitches above the overhead: the cube got 19 levels at 7.8 m instead of 20, a false F_HEIGHT_LIMIT:cube_bin and a grid about 5 % too large. Also at 4.5 m and 7.47 m. | spec, proof | **fixed**: `storage._fit = math.floor(round(height/pitch, 9))` for rack, cube and shelving. The new test `test_levels_exact_at_heights_that_are_whole_pitches` failed before the fix and passes after it. |
| 3 | medium (spec) / low (proof) | T6.7 and T6.8 were example tests on one 5-SKU fixture with one fixed shuffle, not hypothesis property tests; `lo <= typ <= hi` holds by construction. | spec, proof | **fixed**: moved to hypothesis tests in `tests/unit/test_f6_throughput_properties.py` (`tests/property/` is not an F6a path). The old fixture tests were removed. |
| 4 | low | lo/hi worlds are traced in full; ADR-002 and §2.6 say lo/hi trace only leaf results. | spec, proof | **deferred** to F6z: the leaf set is whatever the `size_scenario` world merge writes. Pruning now would drop nodes that F6c/F6d chain on. Still open. |
| 5 | low | Equipment-count nodes used the resource name as unit, not `-`; `storage.<class>.n_skus` nodes had no inputs. | spec | **fixed**: unit `-`; n_skus nodes now list the class-rule inputs. |
| 6 | low | AMR F_ROBOT_DENSITY divides robots by the pod_bin area only; the spec's `A_storage` is undefined. | spec | **deferred**: interpretation kept, with a ponytail comment. The register entry belongs in `docs/INTERPRETATIONS.md`, which is not an F6a path (reported as a blocker). Still open. |
| 7 | low | `cube_asrs.max_robots_per_m2` (an L-confidence Param) and the class and pallet constants were read but not traced. | proof | **fixed**: now inputs of the density, pallets and n_skus nodes. |
| 8 | low | `ThroughputWorld.cases_in` was always 0 for amr_gtp, but the F6c labor table applies decant to AMR. | proof | **fixed**: `_cases_in` records `throughput.decant_cases_in` for cube and AMR; `decant_port_load_peak_h` stays cube-only. Side effect (disclosed): an AMR run with zero shipped units now raises `WhsizingError`, as cube already did. |
| 9 | low | height_utilisation exceeds 1 when levels are forced to 1 in a building that is too low (1.55 at 1.0 m). | proof | **rejected**: this follows the spec literally (F6 edge case l.1052: levels = 1 with F_HEIGHT_LIMIT; F6a defines utilisation as used height / clear height). A value above 1 next to the flag is a true signal. The round-1 spec auditor accepted this and noted that F8/F6z may want to label it. |
| 10 | low | Design stock is allocated as `avg_i × stock_units / Σ avg`, not I14's literal `avg_i × psf × gf`. The two differ by 1 ULP (k = 0.9999999999999999). | proof | **deferred**: the ratio form keeps Σ s_i exact. T6.1 matches to 4e-16, and no impact has been observed. A fix would need the stock factor from F4. Still open. |

### Round 1: tests 37 passed, 0 failed. Both auditors: pass_with_issues

The round-0 fixes were confirmed (Proofs 2-6). No fix round followed, so every round-1 finding below is still open.

| # | Severity | Finding | Raised by | Status |
|---|---|---|---|---|
| 1 | low | lo/hi worlds still traced in full (round-0 #4). Node counts per world: manual 40/40/40, cube 57/57/57, AMR 54/54/54. | spec, proof | open (deferred to F6z) |
| 2 | low | The AMR F_ROBOT_DENSITY area reading (round-0 #6) is still not in the register. I46 (l.335) defines the density only for the cube (`A_grid`). | spec, proof | open (needs a register owner) |
| 3 | low | T6.5's storage-area clause can never fail: `day(k)` scales only flows and stock is constant, so `total_area_m2` is identical in both runs (manual 10.433436532507741 at k=1 and k=8). The equipment clause is the real assertion. | spec, proof | open |
| 4 | low | Design-stock 1-ULP difference from I14 (round-0 #10). | spec, proof | open (deferred) |
| 5 | low | Outside F6a: `tests/golden/oracle.py:299` `levels()` still uses a bare `math.floor`, so at 7.8 m the oracle gives 19 cube levels and the fixed engine gives 20. The golden case at 8.5 m is unaffected. | spec | open (G1 owner) |
| 6 | low | `F_SCALE_LOW` is checked for every family through `<fam>.min_scale_lines_day`, so an AMR scenario under 800 lines/day raises it. F6b (l.948) and the binding I46 (l.325) list it for the cube only. The F6 flags table and the AMR catalog value of 800 support the engine's reading, but the divergence from I46 is not recorded. | proof | open |
| 7 | low | The new node `S*.throughput.decant_cases_in` (the F6c decant driver) lists no pack-data inputs, although its formula divides by `units_per_case_i` (fallback to upp/cpp, then 1). | proof | open |

## Open issues

1. **lo/hi worlds traced in full** (`src/whsizing/engine/inputs.py:96`), contrary to ADR-002/§2.6. Deferred to F6z, which should prune lo/hi after the world merge, for example by keeping only the ids that the Ranges in result.json refer to.
2. **AMR `A_storage` = pod_bin area** (`throughput.py` `_amr`, ponytail comment) has no register entry. Re-checked while writing this record: `docs/INTERPRETATIONS.md` still mentions `A_storage` only at l.335 (I46), with no AMR definition.
3. **F_SCALE_LOW for every family vs I46 "cube"**: the reading is defensible, but the register does not record it.
4. **`decant_cases_in` trace node lacks pack-data inputs** (`data:sku.units_per_case`, `units_per_pallet`, `cases_per_pallet`).
5. **T6.5 storage-area clause can never fail.** Area monotonicity as T6.5 means it effectively belongs to F6d.
6. **T6.8 is blind to order dependence on the manual path.** In both auditors' mutation runs, removing the sort by sku was not caught for manual_p2p, because its sums did not change at the generated sizes. It was caught for AMR (both runs) and for the cube in one of the two.
7. **Design-stock 1-ULP difference from I14** (`inputs.py:165`). Theoretical; no observed impact.
8. **Oracle bare floor** (`tests/golden/oracle.py:299`, G1 owner). Re-checked while writing this record: still `math.floor(usable_height_m / pitch_m)`. Suggested fix: `math.floor(round(x, 9))`, as in the engine.
9. **`.gitignore` does not ignore `.hypothesis/`** (F0 owner). The F6 hypothesis tests write to it. Re-checked: still absent.
10. **Behaviour change for F6c/F6z:** `ThroughputWorld.cases_in` is now filled for AMR. An AMR or cube scenario whose SKU table has zero shipped units raises `WhsizingError('derived inbound: no shipped units in the SKU table')`. This needs incoherent input (lines > 0 with units = 0).
11. **12 build-time interpretations not in the register** (see "Build"). Each needs a register owner or F6z/reviewer sign-off.

## Not applicable here and why

- **T6.2, T6.3, T6.4, T6.6, T6.10**: labor, area/docks, Erlang-C and annual hours belong to F6c, F6d and F6e. No F6a code computes them.
- **T6.9, T6.11**: these need `result.json`, the manifest and `size_scenario` (F6z/F8). Engine determinism and trace resolution for the F6a/F6b nodes were checked in their place (Proofs 6 and 8).
- **Real client data**: none was used. Only the synthetic `tiny_golden` (T6.1) and the synthetic `ecom_mid` profile (auditor end-to-end runs) were used.
- **Domain-expert review**: the engine reads catalog values verbatim, and all of them are still `source: TODO` with confidence L (F5). Interpretations such as the AMR `A_storage`, F_SCALE_LOW scope and height_utilisation above 1 need an expert or the register owner. That review cannot be done here.

## Fresh test output (run while writing this record, 2026-11-08)

Command: `uv run pytest tests/unit/test_f6_storage*.py tests/unit/test_f6_throughput*.py tests/unit/test_f6_inputs*.py tests/golden/test_f6_storage_golden.py -q -rA`

```
.....................................                                    [100%]
==================================== PASSES ====================================
_____________ test_T6_1_storage_throughput_equipment_equal_golden ______________
---------------------------- Captured stdout setup -----------------------------
2026-11-08 22:32:26 [warning  ] catalog_todo_sources           count=72 total=72
2026-11-08 22:32:26 [warning  ] design_day_short_window        history_end=2025-03-31 history_start=2025-03-01 trailing_months=12
=========================== short test summary info ============================
PASSED tests/unit/test_f6_storage.py::test_fits_shelf_is_orientation_agnostic_and_needs_every_dim
PASSED tests/unit/test_f6_storage.py::test_manual_class_rule
PASSED tests/unit/test_f6_storage.py::test_pallet_rack_positions_pick_faces_levels_area
PASSED tests/unit/test_f6_storage.py::test_levels_capped_by_building_or_catalog[12.0-6-20-flags0]
PASSED tests/unit/test_f6_storage.py::test_levels_capped_by_building_or_catalog[8.5-5-20-flags1]
PASSED tests/unit/test_f6_storage.py::test_levels_capped_by_building_or_catalog[5.0-2-11-flags2]
PASSED tests/unit/test_f6_storage.py::test_levels_capped_by_building_or_catalog[1.5-1-1-flags3]
PASSED tests/unit/test_f6_storage.py::test_levels_exact_at_heights_that_are_whole_pitches[pallet_rack-0.6-1.55-6]
PASSED tests/unit/test_f6_storage.py::test_levels_exact_at_heights_that_are_whole_pitches[cube_bin-1.2-0.33-20]
PASSED tests/unit/test_f6_storage.py::test_shelving_bins_levels_area
PASSED tests/unit/test_f6_storage.py::test_cube_bins_mixed_reserve_grid_and_overflow
PASSED tests/unit/test_f6_storage.py::test_pod_bins_and_pods
PASSED tests/unit/test_f6_storage.py::test_storage_result_maps_worlds_to_ranges_and_copies_elig_low
PASSED tests/unit/test_f6_throughput.py::test_lambda_is_max_of_peak_and_sla_flow
PASSED tests/unit/test_f6_throughput.py::test_manual_pickers_by_zone_carts_forklifts
PASSED tests/unit/test_f6_throughput.py::test_cube_ports_with_decant_robots_and_flags
PASSED tests/unit/test_f6_throughput.py::test_amr_gtp_worked_example
PASSED tests/unit/test_f6_throughput.py::test_bottleneck_tie_goes_to_the_first_resource
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations_or_less_storage[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations_or_less_storage[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_5_more_lines_never_fewer_stations_or_less_storage[amr_gtp]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_7_outputs_non_negative_and_worlds_ordered[amr_gtp]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[manual_p2p]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[cube_asrs]
PASSED tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result[amr_gtp]
PASSED tests/unit/test_f6_inputs.py::test_sku_frame_joins_pack_hazmat_and_temperature
PASSED tests/unit/test_f6_inputs.py::test_sku_frame_without_master_has_null_columns
PASSED tests/unit/test_f6_inputs.py::test_world_inputs_rejects_frame_without_required_columns
PASSED tests/unit/test_f6_inputs.py::test_design_stock_is_allocated_in_proportion_to_average_stock
PASSED tests/unit/test_f6_inputs.py::test_manual_family_takes_every_sku
PASSED tests/unit/test_f6_inputs.py::test_cube_uses_the_scenario_eligibility_and_routes_the_rest_to_overflow
PASSED tests/unit/test_f6_inputs.py::test_zero_eligible_lines_degenerates_to_manual
PASSED tests/unit/test_f6_inputs.py::test_to_range_orders_worlds_by_value
PASSED tests/golden/test_f6_storage_golden.py::test_T6_1_storage_throughput_equipment_equal_golden
PASSED tests/golden/test_f6_storage_golden.py::test_T6_1_trace_inputs_resolve
37 passed in 5.90s
```

Also re-run while writing this record: `uv run ruff check` on the 5 engine files and 5 test files gives `All checks passed!`. `uv run pyright` on the 5 engine files gives `0 errors, 0 warnings, 0 informations`.
