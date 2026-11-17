# F6d audit: Sizing engine, area budget, docks and ICPE (F6d) and queue / SLA check (F6e)

## Verdict: pass_with_issues

All F6d/F6e acceptance tests (T6.3 and T6.4) pass: 32 passed, 0 failed, 0 skipped. The golden T6.3 check compares 70 keys with 0 mismatches. The auditors' independent recomputation matched 231 values, and their mutants were all caught. The six files are clean under ruff, ruff format and pyright.
The verdict stays below `pass` because 7 low findings from round 0 are still open: no fix round followed round 0. One more gap was noted while writing this record: no F6d test covers the area/queue parts of T6.5, T6.7 or T6.8. Both round-0 auditors returned pass_with_issues.

Scope: F6d (zones, total, fit, docks, ICPE regime), F6e (Erlang-C pools for packing and GTP ports/stations) and the F6f trace for those nodes. Labor (F6c) and `size_scenario` (F6z) are out of scope. Schema changes: none (`schema_changes: []`). The build reported no blockers and no skipped tests.

Files: `src/whsizing/engine/area.py` (389 lines), `src/whsizing/engine/queue.py` (230 lines), `tests/unit/test_f6_area.py`, `tests/unit/test_f6_queue.py`, `tests/property/test_f6_queue_properties.py`, `tests/golden/test_f6_area_golden.py`. The builder did not edit `src/whsizing/engine/inputs.py`.

Public API (from the submodules, not from `whsizing.engine`): `size_area(inp, storage, tp, *, roster, share_s) -> AreaWorld`, `area_result(worlds) -> AreaResult`, `erlang_c(c, a)`, `queue_resource(resource, c, lam_s, mu, t_h) -> QueueResource`, `size_queue(inp, tp, area) -> QueueWorld`, `queue_result(worlds) -> QueueResult`. The order within a world is storage, throughput, area (using F6c's roster for that world), then queue.

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T6.3 | `tests/golden/test_f6_area_golden.py::test_T6_3_area_docks_queue_equal_golden` | pass | Compares all 70 golden keys under `S0.`/`S2.` `area`, `docks` and `queue` (16 area, 4 docks and 10 `queue.packing` keys per scenario, plus 10 `S2.queue.ports` keys). Integers and booleans must match exactly and floats within 0.5 %. The largest relative error is about 4.1e-16. For the three `c_min` golden keys that are None, the test checks that there is no trace node and that the QueueResource field is None. The golden values come from the independent `tests/golden/oracle.py` / `build_golden.py`, not from engine code. **Caveat:** roster is injected from the golden `S*.labor.total.roster` (11.66 for S0, 12.72 for S2), not computed by F6c. So amenities, circulation, total and fit are checked given the golden roster. The proof audit's `adv.py` and `e2e.py` close this gap with the real F6c `size_labor` roster (see Proofs 4 and 5). `share_s` is `profile.eiq.single_line_share`. |
| T6.3 | `tests/golden/test_f6_area_golden.py::test_T6_3_results_match_the_trace` | pass | The returned AreaWorld and QueueWorld equal the traced values. S2 raises F_NO_FIT and S0 raises nothing. No dock or queue flags are raised. Docks equal the golden values. The ICPE volume is 410 m² × 8.5 m = 3485 m³, which gives regime None. `area_result` for S2 has fit False and the golden deficit. |
| T6.3 | `tests/golden/test_f6_area_golden.py::test_T6_3_trace_inputs_resolve` | pass | F6f integrity: every input of an area, docks or queue node is a catalog param, a `data:` leaf or a node of the same tracer. The one exception is `S*.labor.total.roster`, which F6c records. |
| T6.4 | `tests/unit/test_f6_queue.py::test_T6_4_erlang_c_values` | pass | `erlang_c(1, 0.5) == 0.5` exactly and `erlang_c(2, 1.0) == 1/3` (rel 1e-12). These are the spec values. |
| T6.4 | `tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm1_closed_form` | pass | M/M/1 closed form: P_wait = ρ, W_q = ρ/(μ−λ) and P(W>t) = ρ·e^{−(μ−λ)t}, all at rel 1e-12. |
| T6.4 | `tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm2_closed_form` | pass | M/M/2 closed form: P_wait = 2ρ²/(1+ρ) and W_q = 2ρ³/(λ(1−ρ²)). The expected values come from the closed form, not from `erlang_c`, so the test is not a tautology. |
| T6.4 | `tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_is_a_probability` | pass | Hypothesis: 0 ≤ P_wait ≤ 1 for any stable load, with c from 1 to 60. |
| T6.4 | `tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_decreases_with_servers` | pass | Hypothesis: `erlang_c(c+1, a) <= erlang_c(c, a) + 1e-12`. |
| T6.4 | `tests/property/test_f6_queue_properties.py::test_T6_4_stable_pool_outputs_are_consistent` | pass | Hypothesis: on stable pools, W_q ≥ 0 and 0 ≤ P(W>t) ≤ P_wait ≤ 1. |
| T6.5 (F6d part) | none | not covered | "More lines means area is non-decreasing." `docs/audit/F6a.md` assigns the area clause to F6d. No F6d test covers it: the only T6.5 test is `tests/unit/test_f6_throughput_properties.py`, and it checks F6a/F6b nodes only. Neither auditor raised this; it was noted while writing this record. |
| T6.7 / T6.8 (F6d/F6e part) | none | not covered | Non-negativity, lo/typ/hi world ordering and row-order invariance are tested only for F6a/F6b nodes (`test_f6_throughput_properties.py`). No property test covers area, docks or queue nodes. Noted while writing this record. The proof audit's ecom_mid e2e run showed ordered totals for S0 (lo 1375.2, typ 1083.6, hi 919.3 m²), but that is not a test. |
| T6.1, T6.2, T6.6, T6.9, T6.10, T6.11 | none | not_applicable | These belong to F6a (T6.1), F6c (T6.2, T6.6, T6.10) and F6z/F8 (T6.9, T6.11). |

Supporting tests not tied to a T-id (all pass). They check values computed by hand on the F6a/F6b toy case:

- **Area** (`tests/unit/test_f6_area.py`, 10 tests):
  - `test_manual_zones_by_hand` and `test_docks_and_icpe_by_hand`;
  - `test_dock_shortfall_with_receipts_peak_factor`: I56 receipts mode, where F4 already sets `Inbound.peak_factor` to 1.0, so area.py needs no branch for the mode;
  - `test_no_fit_flags_deficit` (F_NO_FIT and deficit);
  - `test_cube_ports_and_robot_parking` and `test_amr_stations_and_robot_parking`;
  - `test_area_result_ranges_over_worlds`: checks `packing.typ == 96` and the lo-world pack rate. Its `lo <= typ <= hi` assertions always hold (see open issue 7);
  - `test_rejects_bad_labor_inputs[*]` (3 cases: roster −1, roster NaN, share_s 1.2).
- **Queue** (`tests/unit/test_f6_queue.py`, 13 tests that are not T6.4):
  - `test_unstable_pool_has_no_wait_and_suggests_c_min[*]` (2 cases): a ≥ c gives `c_min = ceil(a)+1` and None for the wait fields;
  - `test_erlang_c_rejects_unstable_or_invalid[*]` (4 cases);
  - `test_manual_packing_pool_unstable_when_sla_rate_binds`: λ_s = 243.43 and a = 8.33 ≥ 8 stations give F_UNSTABLE and c_min = 10;
  - `test_packing_sla_risk` and `test_packing_stable_without_risk`;
  - `test_cube_ports_offered_load_equals_sizing_load` (I23);
  - `test_amr_gtp_station_pool`;
  - `test_degenerate_cube_skips_the_ports_pool` (I48);
  - `test_queue_result_is_the_typical_world`.

## Proofs (captured by the auditors during the audit)

The auditors captured these proofs during round 0. They were not re-run for this record, except the NaN/inf repro in Proof 9, which was re-run while writing it. The scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F6d/`, written `$S` below. All commands ran from `/Users/skarwech/saas_v1`. Some claims and command lines were cut off in the audit history; they are marked "(clipped)".

1. **An independent recomputation of every F6d/F6e value matches: 231 checked, 0 mismatches.** The recomputation covers every zone, total, trucks, docks and ICPE volume, and every F6e pool field (servers, a, P_wait, W_q, P(W>t), c_min, t). It hard-codes the spec [P] constants (1.5, 1.0, 40, 0.05, 30, 40, 4, 150, 0.25, 0.2, 0.5), the I24/I26/I28/I45 formulas and a direct-sum Erlang-C, over S0 manual (clipped). (Spec audit.)
   Command: `uv run python $S/recompute.py`
   ```
   S0 manual_p2p typ total 398.6416 mine 398.6416
   S2 cube_asrs typ total 420.8541 mine 420.8541 flags area ['F_NO_FIT']
   S1 amr_gtp typ total 428.5379 mine 428.5379
   S0 manual_p2p lo total 416.2593 ... flags area ['F_NO_FIT']
   checked 231, mismatches 0
   ```

2. **`erlang_c` (Erlang-B recursion) agrees with the exact rational Erlang-C formula, up to c = 120. Unstable and degenerate pools give `c_min = ceil(a)+1` and None for the wait fields.** (Spec audit.)
   Command: `uv run python $S/edge.py`
   ```
   1 0.5 0.5 0.5
   2 1.0 0.33333333333333337 0.3333333333333333
   30 29.0 0.7959516637486967 0.7959516637486966
   120 110.25 0.2662647278502591 0.26626472785025923
   servers=0 arrival_rate_h=5.0 ... stable=False p_wait=None ... c_min=4
   servers=3 arrival_rate_h=6.0 ... offered_load=3.0 stable=False ... c_min=4
   ```
   The proof audit also checked `erlang_c` against the direct factorial formula at (5, 4.2), (20, 17.3) and (50, 45.0). The results agree to about 1e-16: `5 4.2 0.633773192708685 0.6337731927086849`, `50 45.0 0.3638644672069884 0.36386446720698834`. It also checked a large case, `erlang_c(1000, 999.5) = 0.9804842961888178`.

3. **The tests catch formula mutations.** Each of four mutants, injected by a pytest plugin outside the repo, makes tests fail: Erlang-B in place of Erlang-C, W_q × c, circulation without amenities, and floor in place of ceil on docks. (Proof audit.)
   Command: `for m in erlang_b wq circ docks; do MUT=$m PYTHONPATH=$S/mut uv run pytest -p mutant_plugin tests/unit/test_f6_area.py tests/unit/test_f6_queue.py tests/property/test_f6_queue_properties.py t…` (clipped)
   ```
   == erlang_b 9 failed, 23 passed
   == wq 2 failed, 30 passed
   == circ 3 failed, 29 passed
   == docks 5 failed, 27 passed
   ```

4. **End to end on synthetic ecom_mid data (5000 SKUs, 730 days), the engine matches an independent recomputation.** The run covers manual_p2p, amr_gtp and cube_asrs in all 3 worlds, with the real F6c roster. The checked values are pack_stations, packing λ_s/μ, P_wait, P(W>t), c_min, circulation, total and docks_in. F_UNSTABLE:packing is raised (clipped). (Proof audit.)
   Command: `uv run python data/synth/generator.py data/synth/profiles/ecom_mid.yaml --out $S/ecom_mid && uv run python $S/e2e.py $S/ecom_mid 12000`
   ```
   S2 typ: zones=receiving_staging=16.4, shipping_staging=65.9, packing=84.0, ports=160.0, storage=156.7, returns=37.1, equipment=112.0, amenities=246.6, circulation=180.5 | total=1059.2 fit=True docks=1/1 icpe=Enregistrement (E) flags=[]
       queue packing: c=7 lam=301.05 mu=31.61 a=9.525 stable=False ... c_min=11
       queue ports: c=8 lam=2199.90 mu=297.50 a=7.395 stable=True Pw=0.769...
   OK: independent recomputation matched
   ```

5. **The results are deterministic, and every area, docks and queue trace input resolves, including the real F6c `labor.total.roster`.** Two runs give identical results for all 3 families and 3 worlds. (Proof audit.)
   Command: `uv run python $S/adv.py $S/ecom_mid`
   ```
   manual_p2p deterministic; dangling trace refs: []
   amr_gtp deterministic; dangling trace refs: []
   cube_asrs deterministic; dangling trace refs: []
   ```

6. **On the B2B dataset (pallets_out > 0, 3000 m² building), F_NO_FIT is raised for the AMR scenario and the recomputation matches.** (Proof audit.)
   Command: `uv run python data/synth/generator.py data/synth/profiles/b2b_cases.yaml --out $S/b2b && uv run python $S/e2e.py $S/b2b 3000`
   ```
   S1 typ: ... total=3050.6 fit=False docks=2/1 icpe=Déclaration (D/DC) flags=['F_NO_FIT']
   S1 AreaResult total=1808.3/3050.6/5659.2 flags=['F_NO_FIT'] queue flags=['F_UNSTABLE:packing']
   OK: independent recomputation matched
   ```

7. **Receipts inbound mode (I56) works.** peak_factor is 1.0, so receiving staging = 290.79 × 1.0 × 1.5 = 436.2 m², and docks_in = ceil(11.18 × 0.2 / 0.7) = 4. (Proof audit.)
   Command: `uv run python $S/e2e_receipts.py $S/b2b 3000`
   ```
   design day: ... pallets_in=290.79 trucks_in=11.18 pf=1.000 ...
   S0 typ: zones=receiving_staging=436.2, ... docks=4/1 ...
   OK: independent recomputation matched
   ```

8. **The I15 share_S that area uses (`profile.eiq.single_line_share`) equals F6c's `LaborDays.single_line_share`.** It is 0.6022727 on golden and 0.6007679 on ecom_mid. The proof audit reports equality on all three datasets. (Spec and proof audits.)
   Command: `uv run python $S/share.py $S/ecom_mid`
   ```
   profile.eiq.single_line_share 0.6007679408977132
   LaborDays.share 0.6007679408977132
   ```

9. **`queue_resource` raises a builtin exception, not a `WhsizingError`, for NaN or infinite rates** (open issue 1). This was captured by the proof audit and re-run while writing this record, with the same result:
   Command: `uv run python -c "from whsizing.engine.queue import queue_resource; queue_resource('x',2,float('nan'),1.0,1.0)"` (and the inf and μ = NaN variants)
   ```
   ('x', 2, nan, 1.0, 1.0) builtins ValueError cannot convert float NaN to integer
   ('x', 2, inf, 1.0, 1.0) builtins OverflowError cannot convert float infinity to integer
   ('x', 2, 1.0, nan, 1.0) builtins ValueError cannot convert float NaN to integer
   ```

10. **The property tests pass with several hypothesis seeds, and the gates are clean.** (Proof audit and spec audit.)
    Command: `for s in 1 2 3 4; do uv run pytest tests/property/test_f6_queue_properties.py -q --hypothesis-seed=$s | tail -1; done`, then ruff, ruff format and pyright on the 6 files
    ```
    3 passed in 0.58s (x4)
    32 passed in 0.80s
    All checks passed!
    6 files already formatted
    0 errors, 0 warnings, 0 informations
    ```

## Audit rounds

### Build (before round 0)

The builder delivered the six files, 32 tests, no schema changes and no blockers. Decisions it disclosed:

1. `share_s` (I15/I24) is an explicit argument, like `roster`. F6z passes `profile.eiq.single_line_share`. The builder made no edit to `inputs.py`.
2. Zone and trace keys follow the golden names: `ports` (not `gtp_ports` as in the AreaResult comment) and `amenities`. `AreaResult.zones` includes `circulation`.
3. The AMR queue pool is `gtp_stations`, with λ_s = λ_e (no decant load). The AMR station area goes under the same `ports` key.
4. Robot parking reads the scenario family's own `m2_per_robot_parking`, not `cube_asrs.` as I26 says. The values are the same (1.5/2.0/2.5). The manual family's equipment area is `maintenance_fixed` only.
5. There is no ICPE flag (I46). AreaResult carries `icpe_volume_m3` and `icpe_regime` [VERIFY] only.
6. F_AMENITIES_EXTERNAL is never raised (I27).
7. One trace node is not in the golden: `area.icpe_volume_m3`.
8. Flags carry pool suffixes: `F_UNSTABLE:<pool>` and `F_SLA_RISK:<pool>`.
9. `t = sla_window_hours × engine.sla_wait_threshold_share`. The risk threshold `engine.sla_risk_max_probability` and the pack OEE `engine.pack_station_oee` are both read from the catalog.
10. A pool with no servers and no arrivals is skipped (I45, I48).
11. Receipts mode (I56) needs no branch.

Limitations it disclosed:

- `queue_result` and the scalar AreaResult fields (fit, docks, ICPE, flags) come from the typ world only.
- None fields and booleans: a None field gets no trace node, and booleans are traced as 1.0/0.0.

### Round 0: tests 32 passed, 0 failed

Both the spec audit and the proof audit returned **pass_with_issues**. They raised no critical, high or medium findings: the spec audit raised 3 low and the proof audit 4 low. Two findings overlap, which leaves 7 distinct findings. **No fix round followed round 0, so every finding is still open.**

| # | Audit | Severity | Finding | Status |
|---|---|---|---|---|
| 1 | proof | low | `queue_resource` (queue.py:46) lets `ValueError`/`OverflowError` escape for NaN or infinite λ_s or μ: `math.ceil(a)` runs on a non-finite value when computing c_min. The guard `mu <= 0 or lam_s < 0 or c < 0` lets NaN and inf through. `erlang_c` itself does reject them with `WhsizingError`. | **Open.** Re-run while writing this record (Proof 9). Normal input cannot reach it, because the rates come from validated throughput. |
| 2 | spec + proof | low | Robot parking reads `<family>.m2_per_robot_parking` (area.py:263), so it uses `amr_gtp.m2_per_robot_parking` for AMR. Binding I26 says `cube_asrs.m2_per_robot_parking` "for every scenario". | **Open, disclosed deviation (build decision 4).** Both Params are 1.5/2.0/2.5 with pessimistic_end max. The spec audit's recompute applied the cube Param and matched in lo, typ and hi. The two values could drift apart if an expert edits only one. The golden case has no AMR scenario. |
| 3 | spec + proof | low | `area_result` (area.py:117-134) and `queue_result` (queue.py:107-111) take fit, docks, ICPE, flags and the whole QueueResult from the typ world. So F_NO_FIT, F_UNSTABLE or F_SLA_RISK raised only in lo or hi is dropped. On golden, S0 lo has total 416.26 m² > 410 m² and raises F_NO_FIT in its AreaWorld, but `AreaResult.flags` is `[]`. `AreaResult.deficit_m2.hi` can be > 0 while flags is empty. | **Open, disclosed; F6z to decide.** This matches the schema comment (`fit: bool # total.typ ≤ building area`), the engine convention (`storage_result` also uses `typ.flags`) and QueueResource's scalar fields. The spec says nothing about merging flags across worlds. |
| 4 | spec | low | `size_area`, `area_result`, `size_queue` and `queue_result` are not exported from `whsizing.engine`: its `__all__` has no area or queue symbols. | **Open.** `engine/__init__.py` is outside F6d's paths. F6z can import from the submodules, or the F6a owner can add the exports. |
| 5 | spec | low | `AreaResult.zones` uses the key `ports` (the golden key `S*.area.ports`). The schema comment at `schemas/result.py:93` says `gtp_ports`. | **Open, disclosed (build decision 2).** Only the comment disagrees. The code follows the golden. |
| 6 | spec | low | The I15 share_S is computed in two places. Area takes `profile.eiq.single_line_share` (area.py:193); F6c computes `LaborDays.single_line_share` from the lines (labor.py:293). | **Open.** The two values are equal on golden, ecom_mid and the other datasets (Proof 8). F6z must pass the same value. |
| 7 | proof | low | In `tests/unit/test_f6_area.py::test_area_result_ranges_over_worlds`, the `lo <= typ <= hi` assertions always pass, because `to_range` builds lo and hi as the min and max over the worlds. | **Open.** The test's other assertions do real checks (`packing.typ == 96` and the lo-world pack_rate). |

## Open issues

1. `queue_resource` raises a builtin `ValueError`/`OverflowError` instead of a `whsizing.errors` class for NaN or inf rates (finding 1).
2. Robot parking uses the family Param, not `cube_asrs.m2_per_robot_parking` as binding I26 says. The values are the same today (finding 2).
3. F_NO_FIT, F_UNSTABLE or F_SLA_RISK raised only in the lo or hi world is dropped from AreaResult and QueueResult. F6z must decide whether to merge flags (finding 3).
4. The area and queue functions are not exported from `whsizing.engine` (finding 4).
5. The schema comment says `gtp_ports`, while the code key is `ports` (finding 5).
6. share_S comes from two sources (profile and LaborDays). They are equal on every dataset checked, and F6z must keep them in sync (finding 6).
7. `test_area_result_ranges_over_worlds` has a tautological Range assertion (finding 7).
8. No F6d or F6e test covers the area part of T6.5 (more lines means non-decreasing area), or T6.7/T6.8 (non-negativity, world ordering, row-order invariance) for area, docks and queue nodes. `docs/audit/F6a.md` assigns the area clause of T6.5 to F6d. Neither auditor raised this; it was noted while writing this record.
9. The T6.3 golden test injects the roster from the golden labor key. It does not run F6c in the same test. The auditors' e2e scripts with the real F6c roster cover this gap (Proofs 4 and 5), but no repository test does. F6z owns the end-to-end check.

## Not applicable here and why

- **Expert review #1 (F6 "Done when"):** a domain expert must review one worked example per family. This includes the [P] area factors in `area_factors.yaml` and the ICPE regime lookup, which the spec marks [VERIFY]: the regime depends on the stored combustible volume and the cell design, not on the building volume alone. No expert is available here.
- **Real client data:** all checks used `tiny_golden` and the synthetic `ecom_mid` and `b2b_cases` profiles.
- **Docker / GitHub CI:** not run here. The feature tests, ruff, ruff format and pyright were run locally.
- **T6.9 and T6.11 (rerun from the manifest, a TraceNode for every number in result.json):** these belong to F6z/F8. `test_T6_3_trace_inputs_resolve` and the auditors' `adv.py` cover trace integrity for the F6d/F6e nodes in part.

## Fresh test output

Re-run for this record on 2026-11-08 from `/Users/skarwech/saas_v1`:

`uv run pytest tests/unit/test_f6_area*.py tests/unit/test_f6_queue*.py tests/property/test_f6_queue*.py tests/golden/test_f6_area_golden.py -q -rA`

```
................................                                         [100%]
==================================== PASSES ====================================
___________________ test_T6_3_area_docks_queue_equal_golden ____________________
---------------------------- Captured stdout setup -----------------------------
2026-11-08 22:54:39 [warning  ] catalog_todo_sources           count=72 total=72
2026-11-08 22:54:39 [warning  ] design_day_short_window        history_end=2025-03-31 history_start=2025-03-01 trailing_months=12
=========================== short test summary info ============================
PASSED tests/unit/test_f6_area.py::test_manual_zones_by_hand
PASSED tests/unit/test_f6_area.py::test_docks_and_icpe_by_hand
PASSED tests/unit/test_f6_area.py::test_dock_shortfall_with_receipts_peak_factor
PASSED tests/unit/test_f6_area.py::test_no_fit_flags_deficit
PASSED tests/unit/test_f6_area.py::test_cube_ports_and_robot_parking
PASSED tests/unit/test_f6_area.py::test_amr_stations_and_robot_parking
PASSED tests/unit/test_f6_area.py::test_area_result_ranges_over_worlds
PASSED tests/unit/test_f6_area.py::test_rejects_bad_labor_inputs[-1.0-0.5]
PASSED tests/unit/test_f6_area.py::test_rejects_bad_labor_inputs[nan-0.5]
PASSED tests/unit/test_f6_area.py::test_rejects_bad_labor_inputs[5.0-1.2]
PASSED tests/unit/test_f6_queue.py::test_T6_4_erlang_c_values
PASSED tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm1_closed_form
PASSED tests/unit/test_f6_queue.py::test_T6_4_w_q_matches_mm2_closed_form
PASSED tests/unit/test_f6_queue.py::test_unstable_pool_has_no_wait_and_suggests_c_min[1-10.0-6.0-3]
PASSED tests/unit/test_f6_queue.py::test_unstable_pool_has_no_wait_and_suggests_c_min[2-8.0-4.0-3]
PASSED tests/unit/test_f6_queue.py::test_erlang_c_rejects_unstable_or_invalid[0-0.0]
PASSED tests/unit/test_f6_queue.py::test_erlang_c_rejects_unstable_or_invalid[1-1.0]
PASSED tests/unit/test_f6_queue.py::test_erlang_c_rejects_unstable_or_invalid[2-2.5]
PASSED tests/unit/test_f6_queue.py::test_erlang_c_rejects_unstable_or_invalid[2--0.1]
PASSED tests/unit/test_f6_queue.py::test_manual_packing_pool_unstable_when_sla_rate_binds
PASSED tests/unit/test_f6_queue.py::test_packing_sla_risk
PASSED tests/unit/test_f6_queue.py::test_packing_stable_without_risk
PASSED tests/unit/test_f6_queue.py::test_cube_ports_offered_load_equals_sizing_load
PASSED tests/unit/test_f6_queue.py::test_amr_gtp_station_pool
PASSED tests/unit/test_f6_queue.py::test_degenerate_cube_skips_the_ports_pool
PASSED tests/unit/test_f6_queue.py::test_queue_result_is_the_typical_world
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_is_a_probability
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_p_wait_decreases_with_servers
PASSED tests/property/test_f6_queue_properties.py::test_T6_4_stable_pool_outputs_are_consistent
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_area_docks_queue_equal_golden
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_results_match_the_trace
PASSED tests/golden/test_f6_area_golden.py::test_T6_3_trace_inputs_resolve
32 passed in 0.87s
```

The gates were re-run on the same six files:

```
$ uv run ruff check <6 files>          -> All checks passed!
$ uv run ruff format --check <6 files> -> 6 files already formatted
$ uv run pyright <6 files>             -> 0 errors, 0 warnings, 0 informations
```
