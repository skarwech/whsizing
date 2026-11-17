# F8b audit record: one-at-a-time sensitivity, tornado, break-even and percentile sweep

Date of the fresh test run: 2026-11-09. Feature owner: F8b. Spec: `description.md` F8 (lines 1137-1163: Sensitivity, Break-even, Percentile sweep, tests T8.3-T8.4); contracts `schemas/comparison.py` (`TornadoBar`, `BreakEven`, `PercentileSweepRow`, `Sensitivity`); F8a scenarios API (`src/whsizing/scenarios/__init__.py`); `docs/INTERPRETATIONS.md`.

Owned code: `src/whsizing/scenarios/sensitivity.py` (378 lines), `breakeven.py` (149), `sweep.py` (58), and an export/docstring-only edit of `scenarios/__init__.py`.

## Final verdict: pass_with_issues

Both acceptance tests (T8.3, T8.4) pass, 65 passed / 0 failed / 0 skipped in the fresh run, and every auditor run in both rounds also passed (63, then 65 tests green).
Four low findings are still open after round 1 (no fix round followed it) and two of them need an F0 schema change that F8b may not make: a bad `delta` is rejected only late in the pipeline, and a skipped variant carries no "not computed" reason. Both round-1 audits returned pass_with_issues; nothing is upgraded beyond that.

## T-id table

Fresh run: 65 passed, 0 failed, 0 skipped (61 test functions; some are parametrized). Rows without a T-id are F8b feature tests (not spec ids) and are listed so that every function of the run appears. `tests/unit/test_f8_sens_fixtures.py` has no tests; it only builds the tiny_golden `RunContext`.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T8.3 | `unit/test_f8_sens_oat.py::test_T8_3_tornado_is_sorted_by_abs_delta_tco_one_bar_per_scenario_and_parameter` (2 cases: S0, client_current baseline) | pass | tiny_golden: 14 bars, exactly one per scenario x parameter, sorted by `delta_tco` descending, not all equal, base TCO equals independently financed values, each `delta_tco` recomputed from the bar's own `tco_low`/`tco_high` |
| T8.3 | `unit/test_f8_sens_oat.py::test_T8_3_the_seven_parameters_are_documented_and_every_bar_uses_one` | pass | `PARAMS` documents the 7 spec parameters (each doc says what the input is) and every bar's `param` is in `PARAMS` |
| T8.3 | `unit/test_f8_sens_oat.py::test_T8_3_delta_zero_gives_zero_delta_tco` (2 cases) | pass | delta = 0 gives `delta_tco` = 0 for every parameter except `design_percentile` (fixed 90/98 by the spec) |
| T8.3 | `unit/test_f8_sens_runner.py::test_T8_3_the_runs_tornado_has_a_sorted_bar_per_scenario_and_parameter` | pass | same property through F8a's runner hook on the small synthetic site |
| T8.3 | `e2e/test_f8_sens_e2e.py::test_T8_3_ecom_mid_tornado_is_sorted_with_a_bar_per_scenario_and_parameter` | pass | ecom_mid, both baselines: sorted, one bar per scenario x parameter |
| T8.3 | `property/test_f8_sens_properties.py::test_T8_3_tornado_is_sorted_with_one_bar_per_pair_for_any_delta` | pass | hypothesis over delta in [0, 0.6]: sorted, one bar per pair |
| T8.3 | `property/test_f8_sens_properties.py::test_T8_3_labor_cost_bar_grows_with_delta_and_is_zero_at_zero` | pass | hypothesis: labor-cost bar grows with delta and is 0 at 0 (TCO is linear in labor cost) |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_known_root_of_a_synthetic_case_within_1e_3` | pass | closed-form linear payback 2.5/k: root 2.5/target within 1e-3 for several targets, and a F7-style re-run at k* returns the target |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_break_even_rows_with_a_linear_payback_model` | pass | `break_even_rows` on the golden structure with F7 replaced by a linear payback model: root 1.25 for target 2 |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_real_tiny_golden_the_returned_k_reproduces_the_target_when_rerun` | pass | real tiny_golden (client_current baseline): k* re-run through real F7 gives the target payback within 1e-3 |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_the_default_target_equals_the_horizon_and_still_reproduces_within_1e_3` | pass | default target = T = 5 edge (root sits on the reached/unreached edge, 1e-6 step to the reached side) still reproduces within 1e-3 |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_no_root_in_the_bracket_or_beyond_the_horizon_is_none` | pass | no sign change in the bracket, or target beyond the horizon, returns None |
| T8.4 | `unit/test_f8_breakeven.py::test_T8_4_a_jump_of_the_payback_is_not_a_root` | pass | discontinuous payback: brentq lands on the jump, F7 does not reproduce the target, result is None and not a wrong k |
| T8.4 | `property/test_f8_sens_properties.py::test_T8_4_solver_finds_the_known_root_of_a_linear_payback_or_none` | pass | hypothesis over investment, saving, horizon and target: known root k* = I/(a target) or None |
| none | `unit/test_f8_breakeven.py::test_none_when_the_scenario_never_pays_back_or_the_target_is_out_of_reach` | pass | None when a scenario never pays back or the target is out of reach |
| none | `unit/test_f8_breakeven.py::test_one_row_per_automated_scenario_never_the_manual_or_the_baseline_one` | pass | `break_even_rows` has one row per automated scenario, never the manual or the baseline one |
| none | `unit/test_f8_breakeven.py::test_the_bracketing_function_is_continuous_at_the_horizon_and_monotone` | pass | the extended payback used for bracketing is continuous at the horizon and monotone |
| none | `unit/test_f8_breakeven.py::test_extended_payback_equals_f7_payback_where_it_is_reached` | pass | extended payback equals F7's payback wherever F7 reaches one |
| none | `unit/test_f8_breakeven.py::test_config_errors` | pass | target 0 (`target_payback`), a manual scenario id (no break-even row) and a `Project` instead of a `RunContext` each raise `ConfigError` |
| none | `unit/test_f8_sweep.py::test_percentile_sweep_has_one_row_per_scenario_and_percentile_monotone_in_design_lines` (2 cases) | pass | one row per scenario x percentile; design lines strictly increasing in the percentile; FTE non-decreasing |
| none | `property/test_f8_sens_properties.py::test_percentile_sweep_is_monotone_in_design_lines` | pass | hypothesis over percentile lists: design lines monotone |
| none | `unit/test_f8_sweep.py::test_design_lines_are_the_f4_design_day_of_that_percentile` | pass | sweep design lines equal the F4 design day of that percentile |
| none | `unit/test_f8_sweep.py::test_the_row_at_the_basis_percentile_is_the_runs_own_result` | pass | the row at the basis percentile equals the run's own result |
| none | `unit/test_f8_sweep.py::test_default_percentiles_are_the_spec_list` | pass | default percentile list is the spec list |
| none | `unit/test_f8_sweep.py::test_percentiles_in_any_order_keep_the_order_given` | pass | percentiles given in any order keep that order |
| none | `unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors` (5 cases) | pass | invalid percentiles raise `ConfigError` |
| none | `unit/test_f8_sweep.py::test_a_project_is_not_a_context` | pass | a `Project` instead of a `RunContext` raises `ConfigError` |
| none | `unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs` (14 cases: 7 params x 2 baselines) | pass | the sized-once, deep-copied-Tracer variant path equals F8a's `evaluate_scenario` result for result and finance, low and high |
| none | `unit/test_f8_sens_oat.py::test_the_base_run_equals_evaluate_scenario_and_sizing_can_be_financed_twice` | pass | base run equals `evaluate_scenario`; financing one sizing twice gives the same answer |
| none | `unit/test_f8_sens_oat.py::test_catalog_variants_go_through_scenario_overrides_on_the_effective_typ` | pass | catalog parameters are written to `ScenarioDef.overrides` (never `basis.overrides`) as 1.2 x the effective typ |
| none | `unit/test_f8_sens_oat.py::test_equipment_capex_moves_the_equipment_item_not_storage_controls_or_works` (2 cases: -1, +1) | pass | added after audit round 0: storage, controls and building works are unchanged; equipment and integration scale exactly by 1 -/+ delta; S2 overflow moves |
| none | `unit/test_f8_sens_oat.py::test_fill_factor_and_oee_are_fractions_kept_inside_the_catalog_range` | pass | fill factor and OEE variants are clipped to the catalog range |
| none | `unit/test_f8_sens_oat.py::test_directions_labor_up_costs_more_productivity_up_costs_less` | pass | sign sanity on tiny_golden: labor bar inputs are 0.8/1.2 and dearer labor raises TCO without changing FTE; lower productivity raises TCO; higher growth and higher equipment capex raise TCO |
| none | `unit/test_f8_sens_oat.py::test_a_variant_that_is_infeasible_leaves_out_its_bars_and_the_others_go_on` | pass | a variant raising `SizingInfeasibleError` drops only its bars, others continue (pins the behaviour behind open issue 3) |
| none | `unit/test_f8_sens_oat.py::test_unknown_parameter_bad_delta_and_a_project_are_config_errors` | pass | unknown parameter, bad delta, empty parameter list ("no parameter"), and a `Project` raise `ConfigError` |
| none | `unit/test_f8_sens_oat.py::test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds` | pass | same inputs give byte-identical JSON; tiny_golden tornado about 0.8 s |
| none | `unit/test_f8_sens_oat.py::test_the_hook_returns_tornado_break_even_and_sweep_with_the_runs_own_base_values` | pass | `run_sensitivity` returns tornado, break-even and sweep with the run's own base values |
| none | `unit/test_f8_sens_runner.py::test_the_option_runs_the_hook_and_writes_sensitivity_json` | pass | `options.sensitivity` calls `run_sensitivity`, writes `comparison/sensitivity.json`, stage timed |
| none | `unit/test_f8_sens_runner.py::test_break_even_and_sweep_are_part_of_the_runs_sensitivity` | pass | the run's `Sensitivity` has break-even rows for S1 and S2 with target 5.0, and a 3 x 4 sweep with design lines non-decreasing per scenario |
| none | `unit/test_f8_sens_runner.py::test_two_fresh_runs_write_byte_identical_sensitivity_json` | pass | determinism: two fresh runs write byte-identical `sensitivity.json` |
| none | `unit/test_f8_sens_runner.py::test_without_the_option_nothing_is_written` | pass | without the option no `sensitivity.json` is written |
| none | `e2e/test_f8_sens_e2e.py::test_ecom_mid_sensitivity_stage_takes_seconds` | pass | ecom_mid sensitivity stage takes seconds (7.2-8.3 s observed by the engineer) |
| none | `e2e/test_f8_sens_e2e.py::test_ecom_mid_break_even_rows_reproduce_the_target_and_the_sweep_is_monotone` | pass | ecom_mid: break-even rows reproduce the target payback; the sweep is monotone |
| none | `e2e/test_f8_sens_e2e.py::test_ecom_mid_rerun_writes_a_byte_identical_sensitivity_json` | pass | ecom_mid rerun writes byte-identical `sensitivity.json` |

## Proofs

All proofs below were captured by the auditors during the audit rounds (scripts live in the session scratchpad `audit_F8b/`), not re-run by the author of this record. The only thing re-run for this record is the pytest command in "Fresh test output".

1. **Labor-cost bar equals an independent hand computation (round 0 and round 1).** Claim: `delta_tco` = delta x PV(labor opex at 8 %), for both baselines.
   Command: `cd /Users/skarwech/saas_v1 && PYTHONPATH=/Users/skarwech/saas_v1 uv run python .../scratchpad/audit_F8b/hand.py` (round 0), `.../proofA.py` (round 1).
   Output excerpt: `S0 hand 0.2*PV(labor)=30660.8256 delta_tco=30660.8256 tco_high-base=30660.8256 base-tco_low=30660.8256` and `S2 hand 0.2*PV(labor)=25757.6367 delta_tco=25757.6367 ...`.

2. **Break-even k* matches an independent closed form and an independent bisection (round 0).** Delta cash flow is linear in k (checked at k = 0.3, 0.77, 3).
   Command: same `hand.py`, tiny_golden S2, client_current baseline.
   Output excerpt: `closed-form k* for payback=T: 0.3209546528730741  breakeven(): 0.32095565274818216  diff 9.998751080431134e-07` (exactly the 1e-6 edge step); `target 2.5: bisection k=0.559495  breakeven=0.559494761123653`; `target 4.0: bisection k=0.382403  breakeven=0.38240325772717654`.

3. **Break-even against an independent scipy brentq and an independent cumulative-sum payback on real F7 flows (round 1).**
   Command: `.../proofA.py` (second half).
   Output excerpt: `target 1.0 k*=1.260611 F7 payback at k*=1.000000 independent=1.000000 flows [-417604, 417604, 448509, 481459, 516589, 554043]`, `independent brentq k=1.260611`; same agreement for targets 2.0 (k*=0.678901) and 3.5 (k*=0.424474).

4. **Round-0 finding "equipment_capex scales every capex item" is fixed (round 1).** Hand check on tiny_golden S2, equipment_capex +20 % vs base.
   Command: `.../proofC.py`.
   Output excerpt: `{'storage': (12850, 12850), 'equipment': (130000, 156000), 'controls': (150000, 150000), 'building_works': (25336, 25336), 'overflow': (41954, 49554), 'integration_commissioning': (19500, 23400), 'contingency': (37964, 41714)}`. Auditor's hand check: equipment +26000, integration +3900, overflow +7600, contingency +3750; storage, controls and works unchanged.

5. **End to end through `run_scenarios` on synthetic ecom_mid with `options.sensitivity` (round 1).** 21 bars (3 scenarios x 7 parameters) sorted, break-even rows for S1 and S2, 4-percentile sweep, `comparison/sensitivity.json` written.
   Command: `uv run python .../scratchpad/audit_F8b/proofB.py`.
   Output excerpt: `run s 12.6 sens stage s 7.3`; `base_tco {'S0': 4696277, 'S1': 5717996, 'S2': 6457090}`; `n bars 21 sorted True`; `BE S1 5.0 0.43376532437241155 (0.3, 3.0) | BE S2 5.0 0.5808214807045332 (0.3, 3.0)`; `file True 12328`. The S2 equipment_capex bar fell from 611152 (round 0) to 508637 after the fix.

6. **Percentile sweep is monotone and consistent with the run (round 0 and round 1).**
   Command: `.../e2e.py` (round 0), `.../proofB.py` (round 1).
   Output excerpt (round 0, S0): `sweep S0 80.0 2224 {'pickers_peak': 12.0} ...`, `90.0 3119 ... 16.0`, `95.0 3393 ... 18.0`, `98.0 3745 ... 19.0`; round 1, S2: design lines `2224/3119/3393/3745`, robots `23/32/35/38`, TCO `5702085/6295646/6457090/6625082`. The P95 sweep TCO of S2 (6457090) equals the run's base TCO.

7. **Edge cases and malformed inputs give clean `ConfigError` or None, never a crash or a wrong number (round 0 and round 1).**
   Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python .../scratchpad/audit_F8b/edgeB.py`.
   Output excerpt: `oat delta nan -> RAISES ConfigError: sensitivity delta must be in [0, 1): got nan`; `be target nan -> RAISES ConfigError: break-even: target_payback must be > 0 years, got nan`; `be target inf -> OK None`; `sweep [nan] -> RAISES ConfigError`; `sweep [100] -> OK [145, 145]`; `all infeasible: oat -> OK {... 'tornado': [], 'break_even': [], 'percentile_sweep': []}`. Round 0 `edge.py` also showed `be target 5.0000001 -> None (beyond horizon)` and `be scenario S9 -> RAISES ConfigError`.

8. **Hook is wired into the F8a runner and is deterministic.**
   Command: `uv run pytest tests/e2e/test_f8_sens_e2e.py tests/unit/test_f8_sens_runner.py -q -rA`.
   Output excerpt: `PASSED tests/e2e/test_f8_sens_e2e.py::test_ecom_mid_rerun_writes_a_byte_identical_sensitivity_json`, `PASSED tests/unit/test_f8_sens_runner.py::test_two_fresh_runs_write_byte_identical_sensitivity_json`, `PASSED tests/unit/test_f8_sens_runner.py::test_the_option_runs_the_hook_and_writes_sensitivity_json`.

9. **Whole-suite regression and coverage (round 1).**
   Commands: `uv run pytest -q -m 'not bench and not slow' -p no:cacheprovider`; `uv run pytest tests/unit/test_f8_sens*.py tests/unit/test_f8_break*.py tests/unit/test_f8_sweep*.py tests/property/test_f8_sens*.py --cov=whsizing.scenarios --cov-report=term-missing`.
   Output excerpt: `1123 passed, 2 skipped, 24 deselected in 122.10s (0:02:02)` (the 2 skipped and 24 deselected are outside F8b); `61 passed in 63.00s`; coverage table reported `4 files skipped due to complete coverage` (sensitivity, breakeven, sweep, `__init__`), TOTAL 84 % for the `whsizing.scenarios` package (compare.py 76 %, runner.py 72 %, F8a files). The auditor reported ruff, format and type checks clean.

## Audit rounds

Two rounds, each with a spec auditor and a proof auditor. The proof auditors returned pass_with_issues in both rounds, but their records contain no findings and no proofs, so there is nothing further to report from them. There was one fix round (after round 0). No fix round followed round 1.

### Round 0 (spec audit: pass_with_issues, 63 passed / 0 failed)

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | medium | `equipment_capex` scaled every capex unit cost (storage, controls, building works, overflow, integration, contingency), so the bar was effectively "total capex +/- delta" and ranked #2 on ecom_mid (S2 611k EUR), while F7's "equipment capex" is the single `equipment` item (I34) | fixed in round 1: selector now varies only the equipment-item unit costs of the scenario family plus `manual_p2p` per_cart/per_forklift (`EQUIPMENT_COSTS` in `sensitivity.py`); tightened override-set test and added `test_equipment_capex_moves_the_equipment_item_not_storage_controls_or_works`; S2 bar dropped to 509k EUR; verified by round-1 auditor (proof 4) |
| 2 | low | public functions take the run's `RunContext`, not the spec's `project: Project`; `breakeven` not exported from `whsizing.scenarios` (would shadow the module); `breakeven(ctx)` raises `ConfigError` with 2+ automated scenarios unless `scenario_id` is given | deferred (documented contract deviation; F8a API fixes `RunContext` as the carrier; a `Project` would force ingest, profile, design and a run folder into a pure function) |
| 3 | low | `ProjectOptions.delta` unconstrained in the F0 schema; a bad delta is rejected only after ingest, profile, design, scenarios and comparison ran (clean `ConfigError`, `run_failed` logged, no `sensitivity.json`) | deferred (F0 file, outside F8b paths; F8b validates delta in `run_sensitivity`/`sensitivity_oat`); recommended `Field(ge=0, lt=1)` in F0 |
| 4 | low | a variant raising `SizingInfeasibleError` drops its bars with only a log warning (no "not computed" marker); `sensitivity_oat(ctx, params=[])` silently returned an empty tornado | second half fixed (empty list raises `ConfigError`, asserted in a test); first half deferred (`TornadoBar` cannot carry a reason, an F0 contract change) |
| 5 | low | `low_input`/`high_input` have a different unit per parameter (multiplier, absolute rate, percentile, mean clipped fraction) | deferred (documented in `PARAMS`, enforced by the T8.3 parameter test; unifying would change the `sensitivity.json` contract) |

### Round 1 (spec audit: pass_with_issues, 65 passed / 0 failed; T8.3 and T8.4 pass; T8.1, T8.2, T8.5, T8.6 not applicable, owned by F8a)

No new defects in code the fix touched; the finding on `equipment_capex` is closed. Four low findings remain, all carry-overs:

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | low | public functions take `RunContext`, not `Project` (round-0 #2) | deferred, unchanged |
| 2 | low | `ProjectOptions.delta` unconstrained at project load (round-0 #3) | deferred, unchanged (F0 file) |
| 3 | low | an infeasible variant drops its bars without a reason (round-0 #4, first half); new observation: when the baseline scenario is the infeasible one in a variant, the other scenarios are financed without a baseline and their bar shows payback None, which a reader cannot tell from "not reached within the horizon" (reproduced: `sensitivity_oat(golden_ctx('S0'), ['design_percentile'])` with S0 failing at P98 gives only `('S2', 'design_percentile', None, None, 893791)`) | deferred, open |
| 4 | low | per-parameter units of `low_input`/`high_input` (round-0 #5) | deferred, unchanged |

## Open issues

1. Low, outside F8b paths (F0): `ProjectOptions.delta` in `src/whsizing/schemas/project.py` has no range constraint, so a bad delta (for example 1.5 or -0.2) fails with `ConfigError` only after the whole pipeline ran, leaving `comparison.json` but no `sensitivity.json`. Suggested fix: `Field(ge=0, lt=1)`.
2. Low, outside F8b paths (F0): `TornadoBar`/`Sensitivity` in `src/whsizing/schemas/comparison.py` cannot express a "not computed" variant with its reason. F8b logs `sensitivity_not_computed` / `sensitivity_bar_skipped` and omits the bar. Related: a baseline-infeasible variant yields bars with payback None that look like "never pays back".
3. Low, deliberate deviation: public functions take a `RunContext` instead of the spec's `project: Project`; `breakeven` is importable only as `from whsizing.scenarios.breakeven import breakeven`; `breakeven(ctx)` needs `scenario_id` when a run has 2+ automated scenarios (`break_even_rows` gives all rows). Documented in `scenarios/__init__.py` and the module docstrings.
4. Low, documentation-only: `low_input`/`high_input` units differ per parameter; read `PARAMS` to interpret `sensitivity.json`.
5. Engineer interpretations a reviewer should know (not audit findings, recorded in the F8b build notes and module docstrings): `design_percentile` is fixed at 90/98 so delta does not apply; the "or at the catalog min/max" option is implemented only as clipping of fill factor and OEE; `picking_productivity` scales the pick, station and port rates of the family plus the manual pick rates; break-even k* searches [0.3, 3], and the default target equals the horizon, so the root is nudged 1e-6 toward the reached side before verification; a root is accepted only if F7 re-run at k* gives a payback within 1e-3 years of the target. On the golden project (S0 baseline) S2 never pays back in the bracket, so its row is None.
6. Test-data note: the client_current golden tests use a made-up `basis.baseline.actual_fte` (picking 6, packing 3, receiving 1, shipping 1) so that S2 has a payback to solve for. The build report lists no blockers and no schema changes; `pyproject.toml` and `uv.lock` untouched.

## Not applicable here and why

- Real client data: nothing was run on a client site; all runs use `tiny_golden` and the synthetic `ecom_mid` project, and the client_current baseline FTE is invented. Client data never leaves the machine.
- Docker, GitHub CI, pre-commit as a gate: not exercised in this environment; no commit was made.
- Domain-expert review: the choice of the seven parameters' definitions (what counts as "equipment capex", how "picking productivity" is scaled) and the break-even bracket [0.3, 3] are engineer interpretations; no domain expert has reviewed them.
- Spec ids T8.1, T8.2, T8.5, T8.6 belong to F8a (see `docs/audit/F8a.md`); F8b only noted for information that its sensitivity stage on ecom_mid took about 7.3 s.
- No skipped tests: F8b has no test that needs to be skipped, so 0 skipped.

## Fresh test output

Command: `cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f8_sens*.py tests/unit/test_f8_break*.py tests/unit/test_f8_sweep*.py tests/property/test_f8_sens*.py tests/e2e/test_f8_sens*.py -q -rA`, run 2026-11-09 for this record (trimmed to the PASSED lines and the summary).

```
PASSED tests/unit/test_f8_sens_oat.py::test_T8_3_tornado_is_sorted_by_abs_delta_tco_one_bar_per_scenario_and_parameter[S0]
PASSED tests/unit/test_f8_sens_oat.py::test_T8_3_tornado_is_sorted_by_abs_delta_tco_one_bar_per_scenario_and_parameter[client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_T8_3_the_seven_parameters_are_documented_and_every_bar_uses_one
PASSED tests/unit/test_f8_sens_oat.py::test_T8_3_delta_zero_gives_zero_delta_tco[S0]
PASSED tests/unit/test_f8_sens_oat.py::test_T8_3_delta_zero_gives_zero_delta_tco[client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_directions_labor_up_costs_more_productivity_up_costs_less
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[design_percentile-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[design_percentile-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[equipment_capex-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[equipment_capex-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[fill_factor-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[fill_factor-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[growth_rate-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[growth_rate-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[labor_cost-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[labor_cost-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[oee-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[oee-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[picking_productivity-S0]
PASSED tests/unit/test_f8_sens_oat.py::test_every_variant_equals_evaluate_scenario_on_the_same_inputs[picking_productivity-client_current]
PASSED tests/unit/test_f8_sens_oat.py::test_the_base_run_equals_evaluate_scenario_and_sizing_can_be_financed_twice
PASSED tests/unit/test_f8_sens_oat.py::test_catalog_variants_go_through_scenario_overrides_on_the_effective_typ
PASSED tests/unit/test_f8_sens_oat.py::test_equipment_capex_moves_the_equipment_item_not_storage_controls_or_works[-1]
PASSED tests/unit/test_f8_sens_oat.py::test_equipment_capex_moves_the_equipment_item_not_storage_controls_or_works[1]
PASSED tests/unit/test_f8_sens_oat.py::test_fill_factor_and_oee_are_fractions_kept_inside_the_catalog_range
PASSED tests/unit/test_f8_sens_oat.py::test_a_variant_that_is_infeasible_leaves_out_its_bars_and_the_others_go_on
PASSED tests/unit/test_f8_sens_oat.py::test_unknown_parameter_bad_delta_and_a_project_are_config_errors
PASSED tests/unit/test_f8_sens_oat.py::test_same_inputs_give_byte_identical_json_and_the_run_time_is_seconds
PASSED tests/unit/test_f8_sens_oat.py::test_the_hook_returns_tornado_break_even_and_sweep_with_the_runs_own_base_values
PASSED tests/unit/test_f8_sens_runner.py::test_the_option_runs_the_hook_and_writes_sensitivity_json
PASSED tests/unit/test_f8_sens_runner.py::test_T8_3_the_runs_tornado_has_a_sorted_bar_per_scenario_and_parameter
PASSED tests/unit/test_f8_sens_runner.py::test_break_even_and_sweep_are_part_of_the_runs_sensitivity
PASSED tests/unit/test_f8_sens_runner.py::test_two_fresh_runs_write_byte_identical_sensitivity_json
PASSED tests/unit/test_f8_sens_runner.py::test_without_the_option_nothing_is_written
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_known_root_of_a_synthetic_case_within_1e_3
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_no_root_in_the_bracket_or_beyond_the_horizon_is_none
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_a_jump_of_the_payback_is_not_a_root
PASSED tests/unit/test_f8_breakeven.py::test_the_bracketing_function_is_continuous_at_the_horizon_and_monotone
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_break_even_rows_with_a_linear_payback_model
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_real_tiny_golden_the_returned_k_reproduces_the_target_when_rerun
PASSED tests/unit/test_f8_breakeven.py::test_T8_4_the_default_target_equals_the_horizon_and_still_reproduces_within_1e_3
PASSED tests/unit/test_f8_breakeven.py::test_none_when_the_scenario_never_pays_back_or_the_target_is_out_of_reach
PASSED tests/unit/test_f8_breakeven.py::test_one_row_per_automated_scenario_never_the_manual_or_the_baseline_one
PASSED tests/unit/test_f8_breakeven.py::test_config_errors
PASSED tests/unit/test_f8_breakeven.py::test_extended_payback_equals_f7_payback_where_it_is_reached
PASSED tests/unit/test_f8_sweep.py::test_default_percentiles_are_the_spec_list
PASSED tests/unit/test_f8_sweep.py::test_percentile_sweep_has_one_row_per_scenario_and_percentile_monotone_in_design_lines[S0]
PASSED tests/unit/test_f8_sweep.py::test_percentile_sweep_has_one_row_per_scenario_and_percentile_monotone_in_design_lines[client_current]
PASSED tests/unit/test_f8_sweep.py::test_design_lines_are_the_f4_design_day_of_that_percentile
PASSED tests/unit/test_f8_sweep.py::test_the_row_at_the_basis_percentile_is_the_runs_own_result
PASSED tests/unit/test_f8_sweep.py::test_percentiles_in_any_order_keep_the_order_given
PASSED tests/unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors[bad0]
PASSED tests/unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors[bad1]
PASSED tests/unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors[bad2]
PASSED tests/unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors[bad3]
PASSED tests/unit/test_f8_sweep.py::test_bad_percentiles_are_config_errors[bad4]
PASSED tests/unit/test_f8_sweep.py::test_a_project_is_not_a_context
PASSED tests/property/test_f8_sens_properties.py::test_T8_4_solver_finds_the_known_root_of_a_linear_payback_or_none
PASSED tests/property/test_f8_sens_properties.py::test_T8_3_labor_cost_bar_grows_with_delta_and_is_zero_at_zero
PASSED tests/property/test_f8_sens_properties.py::test_T8_3_tornado_is_sorted_with_one_bar_per_pair_for_any_delta
PASSED tests/property/test_f8_sens_properties.py::test_percentile_sweep_is_monotone_in_design_lines
PASSED tests/e2e/test_f8_sens_e2e.py::test_T8_3_ecom_mid_tornado_is_sorted_with_a_bar_per_scenario_and_parameter
PASSED tests/e2e/test_f8_sens_e2e.py::test_ecom_mid_sensitivity_stage_takes_seconds
PASSED tests/e2e/test_f8_sens_e2e.py::test_ecom_mid_break_even_rows_reproduce_the_target_and_the_sweep_is_monotone
PASSED tests/e2e/test_f8_sens_e2e.py::test_ecom_mid_rerun_writes_a_byte_identical_sensitivity_json
65 passed in 72.53s (0:01:12)
```

Result: 65 passed, 0 failed, 0 skipped.
