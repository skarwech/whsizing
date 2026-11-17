# G1e audit: Golden oracle level floor, engine-parity placeholders, register consistency I61-I67

## Verdict: pass_with_issues

In the final round (round 1), both auditors returned `pass_with_issues`, with 49 passed and 0 failed. All G1e-owned findings (the engine-parity skip check, the missing I63 (3) note, the whole-pitch test's flag check) were fixed and re-checked.
The issues still open sit outside G1e's paths: the F6 engine reads the wrong robot-parking Param (medium, pinned by a strict xfail), the register wording of I26 / I63 (12) belongs to the lead, the F6 floor tolerance differs from the register's literal form, and a low residual gap remains in the static skip check.

Schema changes: none (`schema_changes: []`). The oracle still does not import `whsizing`, and `test_g1_engine_parity.py` imports nothing from `whsizing`.

Files touched by the build: `tests/golden/oracle.py`, `tests/golden/build_golden.py`, `tests/golden/golden_case.xlsx`, `tests/golden/test_g1_oracle.py`, `tests/golden/test_g1_register.py`, `tests/golden/test_g1_engine_parity.py`, `docs/INTERPRETATIONS.md` (golden case notes only). `golden_values.json` is byte-identical before and after.

What changed:

1. **Level floor (I63 (11)).** `oracle.py` has `fit_levels(usable, pitch) = floor(usable/pitch + 1e-9)`, written independently of the engine. Both `levels()` and the I40 `height_limited` check in `build_golden.storage()` use it. At 7.8 m the cube's `(7.8 − 1.2)/0.33` is `19.999999999999996`. A bare floor gives 19, and the oracle now gives 20.
2. **I63 (6) cleanup.** Shelving bins read `STORAGE["shelf_bin_net_cube_m3"]`. The stray `MANUAL["shelf_bin_net_cube_m3"]` (not in Appendix C.1 or the catalog, same value 0.040) is removed. `golden_values.json` is unchanged. `golden_case.xlsx` loses exactly one Inputs row, `catalog.manual_p2p.shelf_bin_net_cube_m3`, and is regenerated.
3. **Engine parity.** The stale T6.1-T6.3 placeholders are gone. The file now checks that each F6 golden test exists, is not disabled, and that its `KEYS` pattern selects every S0/S2 key of its groups and nothing else. A second test checks that every `S*.<group>` golden key has exactly one owner (F6, F7, or the I46 `flags` / `low_confidence_params` pair).
4. **Register I61-I67 against the oracle.** These results are recorded in the golden case notes. I62 holds by construction. I63 (2), (4), (5), (8), (10), (11), (12) and I26 match. The I66 rule matches, and its figures are confirmed (S0 −0.91 % / +2.21 %, S2 −1.05 % / +3.89 %). The golden case cannot discriminate I63 (1), (3) (amr_gtp parts), (7), (9), I64, I65 or I61/I67.

## Acceptance tests

Statuses come from the fresh run below and the round-1 audit. G1e's tests all carry the T1.5 id (the golden case).

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T1.5 | `tests/golden/test_g1_oracle.py::test_T1_5_whole_pitch_clear_height_keeps_its_top_level` | pass | I63 (11) at 7.8 m: the float trap is real (`(7.8−1.2)/0.33 < 20`), `fit_levels = levels = 20`, and 1 µm lower gives 19. The full oracle run at 7.8 m gives cube_bin 20 levels with no `F_HEIGHT_LIMIT:cube_bin`, and pallet rack 4 levels with the flag. Mutation: it fails with a bare floor in `fit_levels`, and it also fails with a bare floor only in the I40 check. |
| T1.5 | `tests/golden/test_g1_register.py::test_T1_5_whole_pitch_clear_height_engine_equals_the_oracle` | pass | At 7.8 m every S0/S2 `storage.*` oracle key equals the engine's typ trace (rel 1e-9, levels exact). Since round 1 it asserts the flags of both the engine and the oracle's `S*.flags`: only `F_HEIGHT_LIMIT:pallet_rack`. It fails under a bare oracle floor, and since round 1 it also fails under a bare floor in the I40 check only. |
| T1.5 | `tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param` | xfail (strict, expected) | Added in round 1. This pins the F6 defect, not a G1e defect. On an inline amr_gtp scenario S1 on tiny_golden (robots > 0), I63 (12) / I26 require the equipment node to read `param:cube_asrs.m2_per_robot_parking`, and an `amr_gtp.m2_per_robot_parking = 10` override to change nothing. With `--runxfail` it fails at the ref assert. With area.py patched in scratch to read the cube Param, the body passes, so an F6 fix turns into XPASS(strict) and a failure. The marker must then be removed. |
| T1.5 | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_F6_golden_test_covers_its_keys[T6.1]`, `[T6.2]`, `[T6.3]` | pass | It reads each `test_f6_*_golden.py` with `ast`. The file must have `test_T6_n_*` functions, must not be disabled, and its `KEYS` must select every S0/S2 key of its groups and no other group. Counts on the real files: storage 2, labor 3, area 3. Mutation: dropping `queue` from the area `KEYS` misses 30 keys. |
| T1.5 | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[5 mutants]` | pass | Added in round 1. The mutants are module `pytestmark`, `pytest.skip` in a fixture, `xfail` on the comparison test, `skipif`, and `from pytest import skip`. Each mutant of `test_f6_area_golden.py` counts as 0 tests, and the unmodified file counts as 3. The auditor's extra scratch mutants (`unittest.skip`, `pytest.importorskip`, `marks=pytest.mark.skip` in parametrize) also give 0. |
| T1.5 | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_every_scenario_key_has_an_owner` | pass | The golden S* groups (area, bottleneck, capex, docks, equipment, finance, flags, labor, low_confidence_params, opex, queue, storage, throughput, utilisation, eligibility) are exactly the F6 groups, plus F7 {capex, opex, finance}, plus I46 {flags, low_confidence_params}, and the three sets do not overlap. A new group makes the test fail. |
| T1.5 (engine parity T7.1) | `tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_T7_1_finance` | not_applicable (skip) | Skipped on purpose with the reason `F7 not built: T7.1 compares compute_finance with the golden values`. `compute_finance` does not exist yet. |
| T1.5 | the other `test_T1_5_*` tests in `test_g1_oracle.py` (4), `test_g1_register.py` (3), `test_g1_remediation.py` (12), `test_g1_sync.py` (11) | pass | Not changed by G1e. They still pass after the oracle change and the xlsx rebuild, including `test_T1_5_build_is_deterministic_and_committed_files_are_current`. |

`test_g1_oracle.py` also has 8 helper tests with no T-id (Erlang C, M/M/1, payback, NPV/IRR, levels and area, positions, classification, calendar). All of them pass.

## Proofs (captured by the auditors during the audit)

The spec auditor captured all of these proofs. In both rounds the proof auditor's record holds only a verdict and test counts, with no proofs. `$SP` stands for `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad`. Commands that the audit history shows as clipped are reproduced up to the clip.

1. **A fresh oracle rebuild is byte-identical to the committed files, and the stray MANUAL copy is gone (I63 (6))** (round 0).
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/rebuild.py …`
   ```
   golden_values.json byte-identical: True
   golden_case.xlsx byte-identical: True
   Inputs rows mentioning shelf_bin_net_cube: ['catalog.storage_classes.shelf_bin_net_cube_m3']
   MANUAL has shelf_bin_net_cube_m3: False
   ```

2. **On a 1 mm grid the oracle floor equals the engine's, and it rescues 13 whole-pitch float traps** (round 0). Sweep of pallet_rack and cube_bin from 1 to 20 m.
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/sweep.py`
   ```
   oracle != engine at 1 mm grid: [] 0
   bare-floor traps (oracle rescued): 13
      ('cube_bin', 7.8, 19.999999999999996, 20, 19)
      ('pallet_rack', 2.15, 0.9999999999999999, 1, 0)
   x=20-7e-10: oracle 20 engine 19
   ```

3. **The whole-pitch tests discriminate** (round 0, before the round-1 fix).
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/mutate.py`
   ```
   (a) bare floor in oracle.fit_levels
     oracle test: FAIL
     register test: FAIL
   (b) tolerance in levels(), bare floor in the I40 check only
     oracle test: FAIL
     register test: PASS
   (c) unmutated
     oracle test: PASS
     register test: PASS
   ```
   Round 1 closed the gap in (b). Command `uv run python $SP/audit_G1e/mut_i40.py` now gives `register test: FAIL (mutant killed): S2`.

4. **The engine-parity skip check now rejects every common disable form** (round 1; in round 0 the `modskip` and `xfail` mutants still counted 3 tests).
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/more_mutants.py`
   ```
   orig tests counted: 3
   unittest.skip tests counted: 0
   pytest.importorskip tests counted: 0
   marks=skip in parametrize tests counted: 0
   getattr(pytest,'skip') tests counted: 3
   empty parametrize tests counted: 3
   test_f6_storage_golden.py 2
   test_f6_labor_golden.py 3
   ```
   The last two mutants (`getattr`, empty parametrize) are still counted as live tests. See Open issues.

5. **The engine reads the family's own robot-parking Param, which contradicts I63 (12) / I26** (round 0).
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/parking.py`
   ```
   cube_asrs {} robots 2.0 area.equipment 44.0 parking ref param:cube_asrs.m2_per_robot_parking
   amr_gtp {} robots 2.0 area.equipment 44.0 parking ref param:amr_gtp.m2_per_robot_parking
   amr_gtp {'amr_gtp.m2_per_robot_parking': 10.0} robots 2.0 area.equipment 60.0 parking ref param:amr_gtp.m2_per_robot_parking
   ```

6. **The strict-xfail pin fails for the right reason, and an F6 fix would flip it** (round 1).
   Command: `uv run pytest tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param --runxfail -q`
   ```
   E       AssertionError: assert 'param:amr_gt...robot_parking' == 'param:cube_a...robot_parking'
   E         - param:cube_asrs.m2_per_robot_parking
   E         + param:amr_gtp.m2_per_robot_parking
   1 failed
   ```
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/audit_G1e/fixed_parking.py`
   ```
   fixed engine: test body PASSES -> strict xfail would XPASS(strict) and fail
   ```

7. **The I66 figures and the hand checks on golden values are confirmed** (round 0).
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python $SP/G1e/i66.py; uv run python -c "print((10.111441770130636/(70*0.85)+13.456863024932222/(35*0.85))/2, 2*2.0+40)"`
   ```
   S0.labor.p50_day_hours 4.4727 4.4320 -0.91 %
   S0.labor.temp_hours.y1 141.26 144.39 +2.21 %
   S2.labor.p50_day_hours 3.8727 3.8319 -1.05 %
   S2.labor.temp_hours.y1 91.61 95.17 +3.89 %
   0.3111358640335721 44.0  (golden S0.utilisation.pickers 0.3111358640335721, S2.area.equipment 44.0, S0.area.equipment 40.0)
   ```

8. **The full default suite passes with no failure from G1e** (round 1).
   Command: `uv run pytest -q -m 'not bench and not slow'`
   ```
   694 passed, 2 skipped, 9 deselected, 1 xfailed in 25.89s
   ```

## Audit rounds

### Round 0 (spec: pass_with_issues, 44 passed, 0 failed; proof: pass_with_issues, 44 passed)

| # | Severity | Where | Finding | Resolution (round 1) |
|---|---|---|---|---|
| 1 | medium | `tests/golden/test_g1_engine_parity.py:55` | The "not skipped" check only searched function decorators for `skip`. A module `pytestmark`, `pytest.skip()` in a fixture, or `xfail` on the comparison test went unnoticed. | **Fixed.** `_disabled(tree)` walks the whole AST and rejects any Attribute or alias named `skip`, `skipif`, `xfail` or `importorskip`, and any `pytestmark` Name. Added `test_T1_5_engine_parity_rejects_a_disabled_golden_test` over 5 mutants. Re-checked in round 1 (proof 4), with a low residual. |
| 2 | medium | `src/whsizing/engine/area.py:263` (F6) | Robot parking reads `<family>.m2_per_robot_parking`, but I63 (12) / I26 (binding) say `cube_asrs.m2_per_robot_parking`. An amr_gtp override changes `area.equipment` from 44 to 60. | **Deferred** (outside G1e, F6 engine; also docs/audit/F6d.md finding 2). Pinned by the strict xfail `test_T1_5_amr_robot_parking_reads_the_cube_param`. |
| 3 | low | `docs/INTERPRETATIONS.md:520` | The register contradicts itself: I63 (12) / I26 say "for every scenario", but I47 counts no robot Param for S0 (S0 = 30). | **Deferred** to the lead (register text, not golden notes). The golden case note now says that S0 has 0 robots and reads no robot Param. |
| 4 | low | `docs/INTERPRETATIONS.md:616` | The I61-I67 golden note omitted I63 (3), which the golden case cannot exercise (no amr_gtp scenario). | **Fixed.** The "Not discriminated" list names the amr_gtp parts of I63 (3) and I63 (12) and points to the xfail pin. |
| 5 | low | `tests/golden/test_g1_register.py:127` | The whole-pitch register test asserted only the engine's flags, not the oracle's `S*.flags`. | **Fixed.** It now asserts that the oracle's `F_HEIGHT_LIMIT*` entries for S0 and S2 equal `['F_HEIGHT_LIMIT:pallet_rack']`. The I40-only mutant is killed (proof 3). |
| 6 | low | `src/whsizing/engine/storage.py:161` (F6) | The engine uses `floor(round(x, 9))`, and the oracle and the register use `floor(x + 1e-9)`. They differ only for x in `[k − 1e-9, k − 5e-10)`. | **Deferred** (outside G1e, F6). No clear height on a 1 mm grid from 1 to 20 m reaches the band (proof 2). |

### Round 1 (spec: pass_with_issues, 49 passed, 0 failed; proof: pass_with_issues, 49 passed)

| # | Severity | Where | Finding | Resolution |
|---|---|---|---|---|
| 1 | medium | `src/whsizing/engine/area.py:263` (F6) | Round-0 finding 2 is still unresolved. It is pinned by the strict xfail, whose marker must be removed when F6 fixes area.py. | **Deferred** to F6 (open). |
| 2 | low | `docs/INTERPRETATIONS.md:520` | Round-0 finding 3 is still unresolved. The register wording should say "every scenario with robots". | **Deferred** to the lead (open). |
| 3 | low | `src/whsizing/engine/storage.py:161` (F6) | Round-0 finding 6 is still unresolved. | **Deferred** to F6 (open). |
| 4 | low | `tests/golden/test_g1_engine_parity.py:38` | `_disabled` is a static check. An empty `@pytest.mark.parametrize('a', [])`, which pytest skips by default, `getattr(pytest, 'skip')`, and a collection hook in `tests/conftest.py` still count as live tests. | **Open.** No fix round followed. Round-0 finding 1 is otherwise resolved. |

## Open issues

1. **[medium, F6]** `src/whsizing/engine/area.py:263` reads `f"{family}.m2_per_robot_parking"`, but I63 (12) and I26 require `cube_asrs.m2_per_robot_parking`. In an amr_gtp scenario, an override of `amr_gtp.m2_per_robot_parking` changes `area.equipment`, and the trace leaf id is wrong. Today's golden values do not show it (equal catalog values, no amr_gtp scenario). The defect is pinned by the strict xfail `tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param`. Remove the marker when F6 fixes area.py.
2. **[low, lead]** The wording of register I26 / I63 (12), "for every scenario", contradicts I47 (S0 = 19 + 9 + 1 + 1 = 30). It should read "every scenario with robots". The oracle and `S0.flags` (`F_LOW_CONFIDENCE:30`) follow I47.
3. **[low, F6]** `src/whsizing/engine/storage.py:161` uses `floor(round(x, 9))` and the register uses `floor(x + 1e-9)`. They differ only in a sub-nanometre band that no realistic clear height reaches.
4. **[low, G1e]** The static disabled-file check in `test_g1_engine_parity.py` does not catch an empty parametrize, `getattr(pytest, 'skip')`, or a conftest collection hook.
5. **[gap, by design]** No T6 test compares `S*.flags` or `S*.low_confidence_params` (I46: "T6.x do not compare flag strings"). The owner test makes this explicit.
6. **[coverage]** The golden case does not discriminate I63 (1) (the stock_growth_rate override; the golden basis has no overrides), I63 (3) and the amr_gtp part of I63 (12) (no amr_gtp scenario; the xfail pin covers (12)), I63 (7) (height_utilisation has no golden key), I63 (9) (no A/B SKU has s_i = 0; all 10 zero-stock SKUs are class C), I64 (derived inbound mode), I65 (one shift), or I61 / I67 (engine signatures, F2 ingestion).
7. **[pending F7]** `test_T1_5_engine_parity_T7_1_finance` stays skipped until `compute_finance` exists.

## Not applicable here and why

- **T7.1 engine parity (finance).** F7 is not built, so there is no `compute_finance` to compare with the golden values. The test is skipped with an explicit reason and needs no Docker, client data or expert. It becomes applicable once F7 lands.
- **The amr_gtp robot-parking pin** is an expected failure (strict xfail). It documents an F6 defect and does not count as a G1e pass.
- No G1e test needs Docker, real client data, GitHub CI or a domain expert. The golden case runs on the synthetic `tiny_golden` data set only.

## Fresh test output

Run on 2026-11-09 from `/Users/skarwech/saas_v1` while writing this record. The log lines captured from the two engine-backed tests are trimmed, and the PASSED lines of two unchanged files are elided as marked. Counting: 49 passed, 0 failed, 1 skipped (T7.1 placeholder), and 1 strict xfail (the F6 parking pin), which is counted neither as a pass nor as a skip.

Command: `uv run pytest tests/golden/test_g1_*.py -q -rA`

```
.........s.................x.......................                      [100%]
=========================== short test summary info ============================
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_F6_golden_test_covers_its_keys[T6.1]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_F6_golden_test_covers_its_keys[T6.2]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_F6_golden_test_covers_its_keys[T6.3]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[imported skip]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[module pytestmark]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[pytest.skip in a fixture]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[skipif on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[xfail on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_every_scenario_key_has_an_owner
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_spreadsheet_equals_golden_json
PASSED tests/golden/test_g1_oracle.py::test_T1_5_build_is_deterministic_and_committed_files_are_current
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_anchors_match_tiny_golden_readme
PASSED tests/golden/test_g1_oracle.py::test_T1_5_golden_values_respect_spec_invariants
PASSED tests/golden/test_g1_oracle.py::test_erlang_c_values
PASSED tests/golden/test_g1_oracle.py::test_erlang_wq_matches_mm1_closed_form
PASSED tests/golden/test_g1_oracle.py::test_payback_interpolation_and_edge_cases
PASSED tests/golden/test_g1_oracle.py::test_npv_irr_against_numpy_financial
PASSED tests/golden/test_g1_oracle.py::test_levels_and_area_formulas
PASSED tests/golden/test_g1_oracle.py::test_T1_5_whole_pitch_clear_height_keeps_its_top_level
PASSED tests/golden/test_g1_oracle.py::test_positions_formulas
PASSED tests/golden/test_g1_oracle.py::test_classification_formulas
PASSED tests/golden/test_g1_oracle.py::test_calendar_and_misc_formulas
PASSED tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out0-True]
PASSED tests/golden/test_g1_register.py::test_T1_5_ratio_drift_at_zero_percentile[pallets_out1-False]
PASSED tests/golden/test_g1_register.py::test_T1_5_default_units_per_pallet_flag_matches_the_engine
PASSED tests/golden/test_g1_register.py::test_T1_5_whole_pitch_clear_height_engine_equals_the_oracle
[... 12 PASSED lines for tests/golden/test_g1_remediation.py::test_T1_5_* omitted ...]
[... 11 PASSED lines for tests/golden/test_g1_sync.py::test_T1_5_* omitted ...]
SKIPPED [1] tests/golden/test_g1_engine_parity.py:121: F7 not built: T7.1 compares compute_finance with the golden values
XFAIL tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param - F6 engine/area.py:263 reads <family>.m2_per_robot_parking (docs/audit/F6d.md finding 2); I63 (12) / I26 say cube_asrs.m2_per_robot_parking for every scenario
49 passed, 1 skipped, 1 xfailed in 2.05s
```
