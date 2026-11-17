# F4c audit: Design basis, residual validation gaps

## Verdict: pass_with_issues

All 135 F4 tests pass (0 failed, 0 skipped). T4.1 to T4.6 and the four F4c items (I60 finite design values, real-number overrides, the overrides assumption row, the I55/I52 calendar-month wording) each have a passing test that was shown in round 0 or round 1 to fail when its fix was undone. Golden values are unchanged.
The verdict stays below `pass` because the last audit round (round 1) closed with both auditors at pass_with_issues and 2 low findings open (`basis.py` is 417 lines, deferred; `derive_inbound` is 51 lines, new), and no fix round followed.

Scope: F4c owns `src/whsizing/design/**`, `basis/*.yaml`, `tests/unit/test_f4_*.py` and `tests/golden/test_f4_*.py`. Spec: description.md l.745-776 (F4), the binding register entries I55-I61 in `docs/INTERPRETATIONS.md`, and the open issues of `docs/audit/F4b.md`. No schema change was made (`schema_changes: []`).

Files touched by the build and fix round: `src/whsizing/design/basis.py`, `assumptions.py`, `design_day.py`, `inbound.py`, `basis/template_en.yaml`, `basis/template_fr.yaml`, `tests/unit/test_f4_design.py`, `tests/unit/test_f4_register.py`.

Re-checked while writing this record (2026-11-09) on the F4 paths: `ruff check` gives `All checks passed!`, `ruff format --check` gives `8 files already formatted`, pyright gives `0 errors, 0 warnings, 0 informations`. File sizes: `basis.py` 417, `inbound.py` 203, `design_day.py` 160, `assumptions.py` 79, `test_f4_register.py` 556, `test_f4_design.py` 400 lines, all under the 800-line maximum. Function lengths (ast, def to end): `derive_inbound` 51, `select_design_day` 49, `basis_assumptions` 48.

## Acceptance and F4c tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T4.1 | `tests/golden/test_f4_golden.py::test_T4_1_design_day_and_inbound_equal_golden_spreadsheet` | pass | Every golden `design_day.*`, `inbound.*` and `stock.*` key matches the engine, and no golden F4 key is left uncompared. Golden values unchanged by F4c, including after the `select_design_day` refactor (fix 5a). |
| T4.2 | `tests/unit/test_f4_design.py::test_T4_2_design_percentile_moves_lines_monotonically` | pass | `lines*` never decreases over P50..P100, and each value equals `np.percentile(operating-day lines, q) × 1.04^5` at rel 1e-12. |
| T4.3 | `tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines` (2 cases) | pass | `\|Σ hourly − lines*\| < 1e-6` and `peak_hour_lines == max(hourly)`. |
| T4.4 | `tests/unit/test_f4_design.py::test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock` | pass | With 3 equal snapshots and g = 0, `units_in` equals the mean operating-day units out at rel 1e-12; a stock growth of 252 units/yr adds exactly 1 unit/day. |
| T4.5 | `tests/unit/test_f4_design.py::test_T4_5_assumptions_list_every_basis_field_exactly_once` | pass | Every leaf field, `overrides` included, appears exactly once on `golden_basis.yaml` (empty overrides row `('default', '{}')`) and on `basis/example_basis.yaml` (origin `client`). Rated weak in round 0, pass in round 1. |
| T4.5 | `tests/unit/test_f4_design.py::test_T4_5_template_basis_tells_placeholder_defaults_from_client_values` | pass | Added in fix round 1. A basis loaded from fresh `basis_template('en')` output gives `client` rows for exactly the 9 `[CLIENT]` fields, and a row is `default` if and only if its note starts with `[P]`. Changing `utilisation` from 0.85 to 0.9 turns only that field into `client`. |
| T4.6 | `tests/unit/test_f4_design.py::test_T4_6_basis_with_unknown_key_raises_config_error` (2 cases) | pass | An unknown key at the top level and one nested in `projection` each raise `ConfigError` matching "unknown key". |
| F4c-1 (I60 finite design values) | `tests/unit/test_f4_register.py::test_I60_finite_but_huge_basis_value_never_gives_inf` (3 cases), `test_I60_huge_growth_named_by_derive_inbound`, `test_I60_realistic_growth_gives_finite_design_values` | pass | `growth_rate = 1e308, T = 1`, `overrides.stock_growth_rate = 1e308` and `pallets_per_truck = 5e-324` each raise `ConfigError` naming the non-finite design value and its source fields. Realistic growth stays finite. Fails when `require_finite` is a no-op. |
| F4c-2 (overrides are real numbers) | `tests/unit/test_f4_register.py::test_I60_override_values_must_be_real_numbers` (4 cases), `test_I60_override_bool_rejected_on_a_model_too`, `test_I60_integer_and_float_overrides_accepted` | pass | YAML `true`/`false`, `.nan` and `.inf` in `overrides` raise `ConfigError` naming `overrides.<id>`; integers and floats are accepted. The quoted-text row was removed in fix round 1 (see round 1, finding 3). |
| F4c-2 (fix round 1, numeric text) | `tests/unit/test_f4_register.py::test_I60_override_numeric_text_accepted_like_typed_fields` (3 cases), `test_I60_non_numeric_override_text_rejected` | pass | `1e-2`, `1.0e-2` and `"0.5"` in `overrides` are coerced as in typed basis fields (0.01, 0.01, 0.5); `"abc"` raises `ConfigError`. |
| F4c-3 (overrides assumption row) | `tests/unit/test_f4_design.py::test_T4_5_assumptions_list_every_basis_field_exactly_once` | pass | The `overrides` field has its own row even when empty. Fails when that row is dropped. |
| F4c-4 (I55/I52 calendar-month wording) | `tests/unit/test_f4_register.py::test_I55_template_states_calendar_month_warning[en\|fr]`, `test_I55_short_window_warning_on_window_used` (6 cases) | pass | Both templates say "warns under 12 calendar months" / "alerte sous 12 mois calendaires". A 365-day history does not warn (I52 `calendar_months`). |
| I60 (fix round 1, inbound catalog values > 0) | `tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive` (6 cases) | pass | `engine.receipt_lines_per_pallet_full`, `engine.receipt_lines_per_pallet_mixed` and `storage.default_units_per_pallet` at −5 or 0 raise `ConfigError ... must be > 0` in `inbound_by_sku`. Failed before the fix. |
| I60 (fix round 1, overflow hint) | `tests/unit/test_f4_register.py::test_I60_inbound_overflow_names_the_catalog_override` | pass | When a catalog override causes an inf inbound value, the `ConfigError` hint lists the three catalog ids. Failed before the fix. |
| F4 Done-when: assumptions render in the report | none | not_applicable | The F9 report is not built yet. `write_design` writes `design/assumptions.json` (covered by `test_write_design_writes_design_day_and_assumptions`). |

The other F4/F4b tests in the two files (I55-I60 register tests, SLA window, percentile clipping, receipts mode, templates, `check_basis` ranges, missing columns, `catalog=` required) all pass. TDD: the fix-round-1 tests failed before their fixes, per the fix report, and the round-1 mutants below confirm it.

## Proofs (captured by the auditors during the audit)

The F4c spec auditors captured these proofs in round 0 or round 1. The round-0 and round-1 proof audits returned pass_with_issues with no findings and no proofs listed. All commands were re-run while writing this record (2026-11-09) with the same results, except where noted. Scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_F4c/`, written `<s>/` below. Every command runs from `/Users/skarwech/saas_v1`. `[warning]` log lines are trimmed.

1. **Independent hand computation on the 730-day ecom_mid set matches the engine for the template, example and golden bases** (rounds 0 and 1). Numpy percentile, reference-day ratios, (1+g)^T, stock and derived `units_in` all match; `sum(hourly) = lines*`; every leaf field has exactly one assumption row. The relative error was 1.38e-16 in round 0 and 0.00e+00 after the fix-5a refactor.
   Command: `uv run python <s>/probe.py` (section 1)
   ```
   t_en.yaml: window=24 lines=3267.7038 hand=3267.7038 max_rel_err(all m)=0.00e+00 stock=62099.76 hand=62099.76 in_units=2573.3145 hand=2573.3145 sum(hourly)-lines=0.00e+00
      leaf=51 rows=53 dup=0 missing=set() overrides row=(default, '{}', '[P] catalog parameter id → client value') override rows=[]
   example_basis.yaml: window=24 lines=3429.4404 hand=3429.4404 max_rel_err(all m)=0.00e+00 ...
      leaf=51 rows=54 dup=0 missing=set() overrides row=(client, '{"manual_p2p.pick_rate_shelving_lines_h": 62.0}', ...)
   golden_basis.yaml: window=12 lines=3492.5238 hand=3492.5238 max_rel_err(all m)=0.00e+00 ...
   ```

2. **I60 (F4c-1): a finite but huge basis value never produces an inf design value; a `ConfigError` names the design values and source fields, in derived and receipts mode** (rounds 0 and 1).
   Command: `uv run python <s>/probe.py` (section 2)
   ```
   growth 1e308 T=1: ConfigError: design value(s) not finite: design_day.orders = inf; design_day.lines = inf; ...
   peak_stock_factor 1e308: ConfigError: ... design_day.stock_units = inf; design_day.stock_cube_m3 = inf; check projection.peak_stock_factor, overrides.stock_growth_rate, projection.horizon_years
   pallets_per_truck 5e-324: ConfigError: ... inbound.trucks_per_day = inf; ...
   receipts growth 1e308 T=1: ConfigError: design value(s) not finite: ...
   growth 0.5 T=30 (realistic upper): NO ERROR -> lines=550440590.633917 ...
   ```

3. **Round-1 finding 1 resolved: a basis made from a fresh template (EN or FR) gives 9 `client` rows (exactly the `[CLIENT]` fields), 39 `default` rows (all tagged `[P]`) and 3 `derived` rows. Editing one `[P]` value, or uncommenting `trailing_months` (I55), makes only that field `client`.** Round 0 had shown `Counter({'client': 48, 'derived': 3})`, zero `default` rows.
   Command: `uv run python <s>/probe2.py` (section A)
   ```
   en untouched: {'client': 9, 'default': 39, 'derived': 3}
   en trailing uncommented 12: {'client': 10, 'default': 39, 'derived': 2} client(non-id)=[..., 'projection.trailing_months', ...]
   en growth 0.04 written as 4e-2: {'client': 10, 'default': 38, 'derived': 3} client(non-id)=[..., 'projection.growth_rate', ...]
   fr untouched: {'client': 9, 'default': 39, 'derived': 3}
   ```

4. **Round-1 findings 2 and 4 resolved: a negative or zero inbound catalog override raises `ConfigError` naming it, and an override that overflows names the catalog ids in the hint.** In round 0 the same `-5` override gave `rl=-39.08172087588776` with no error.
   Command: `uv run python <s>/probe.py` (section 2) and `uv run python <s>/probe2.py` (section D)
   ```
   override rl_mixed -5: ConfigError: inbound: engine.receipt_lines_per_pallet_mixed = -5.0 (catalog or basis overrides) must be > 0
   override rl_mixed 1e308: ConfigError: design value(s) not finite: inbound.receipt_lines_per_day = inf; check projection.growth_rate, projection.horizon_years, flows.pallets_per_truck, engine.receipt_lines_per_pallet_full, engine.receipt_lines_per_pallet_mixed, storage...
   derived storage.default_units_per_pallet=0.0: ConfigError: inbound: storage.default_units_per_pallet = 0.0 (catalog or basis overrides) must be > 0
   ```

5. **Round-1 finding 3 resolved: a dot-less exponent in `overrides` is coerced as in typed fields; quoted nan/inf/1e999 text, YAML bools and `stock_growth_rate <= -1` are still rejected.** In round 0, `1e-2` was rejected with `'1e-2' (must be a finite number)`.
   Command: `uv run python <s>/probe.py` (section 3) and `uv run python <s>/probe2.py` (section E)
   ```
   overrides {stock_growth_rate: 1e-2}: NO ERROR -> {'stock_growth_rate': 0.01}
   projection.growth_rate: 4e-2 (non-override field, same YAML shape): NO ERROR -> 0.04
   stock_growth_rate: "nan": ConfigError: basis: invalid value(s): overrides.stock_growth_rate = 'nan' (must be a finite number)
   stock_growth_rate: "1e999": ConfigError: ... = '1e999' (must be a finite number)
   stock_growth_rate: yes: ConfigError: ... = True (must be a finite number)
   stock_growth_rate: "-1": ConfigError: ... = -1.0 (must be finite and > -1)
   ```

6. **F4c-4: both templates are byte-equal to fresh `basis_template` output and carry the I52 calendar-month wording** (rounds 0 and 1).
   Command: `uv run python <s>/probe.py` (section 4)
   ```
   en byte-equal: True | # trailing_months: 12  # [P] design-day window (unset: 24 if the history covers 24 months, else 12; warns under 12 calendar months) (months)
   fr byte-equal: True | # trailing_months: 12  # [P] fenêtre du jour de conception (absente : 24 si l'historique couvre 24 mois, sinon 12 ; alerte sous 12 mois calendaires) (months)
   ```

7. **Derived inbound per SKU (I13) matches an independent hand computation**: pallets = Σ units_in_i / upp_i, receipt lines = pallets × (full 1.0 if units_in_i ≥ upp_i else mixed 4), trucks = pallets / pallets_per_truck, also with a mixed override of 2.0 (round 1).
   Command: `uv run python <s>/hand3.py`
   ```
   overrides={} full=1.0 mixed=4.0 | pallets engine=7.816344 hand=7.816344 | receipt_lines engine=31.265377 hand=31.265377 | trucks engine=0.300629 hand=0.300629
   overrides={'engine.receipt_lines_per_pallet_mixed': 2.0} full=1.0 mixed=2.0 | ... receipt_lines engine=15.632688 hand=15.632688 | ...
   ```

8. **Each fix is guarded by a test: runtime mutants (monkeypatched by a scratch pytest plugin, no repo edits) recreate the pre-fix behaviour and fail only the targeted tests.**
   Round-1 command: `MUT={origin|sign|text|hint} PYTHONPATH=<s> uv run pytest -p mut2_plugin tests/unit/test_f4_*.py tests/golden/test_f4_*.py -q`
   ```
   MUT=origin: FAILED test_T4_5_template_basis_tells_placeholder_defaults_from_client_values; 1 failed, 134 passed
   MUT=sign: 6 failed (test_I60_inbound_catalog_values_must_be_positive x6), 129 passed
   MUT=text: 2 failed (numeric_text 1e-2, "0.5"), 133 passed
   MUT=hint: 1 failed (test_I60_inbound_overflow_names_the_catalog_override), 134 passed
   ```
   Round-0 command: `MUT={finite|override|assump|label} PYTHONPATH=<s> uv run pytest -p mut_plugin tests/unit/test_f4_*.py tests/golden/test_f4_*.py -q`
   ```
   == MUT=finite  4 failed, 120 passed
   == MUT=override  8 failed, 116 passed
   == MUT=assump  FAILED test_T4_5_assumptions_list_every_basis_field_exactly_once  1 failed, 123 passed
   == MUT=label  FAILED test_basis_template_loads_and_marks_every_default[en]  1 failed, 123 passed
   ```
   Re-run on 2026-11-09: the round-1 mutants reproduce exactly. Of the round-0 mutants, `finite` now fails 5 tests and `assump` 2 (the round-1 tests also catch them), and `label` fails 1 as before. The `override` mutant now gives `16 failed, 14 passed, 105 errors`: it patches the pre-fix `_override_errors` signature, which fix round 1 changed to `(overrides, raw)`, so that re-run is not evidence either way. The round-1 `text` mutant covers the current override check.

## Audit rounds

### Round 0 (after the build)

Spec audit: pass_with_issues, 124 passed, 0 failed. T4.5 rated weak. Proof audit: pass_with_issues, no findings, no proofs listed.

| # | Severity | Finding | Resolution (fix round 1) |
|---|---|---|---|
| 1 | medium | `assumptions.py:45`: in the template workflow (basis_template, client edits, load_basis), every `[P]` default lands in `model_fields_set` and gets origin `client`, with its `[P]` tag dropped. A template basis gave `Counter({'client': 48, 'derived': 3})`, zero `default` rows. | **Fixed.** Origin is `client` only when the field is set in the file and its value differs from the schema default; fields the template leaves unset (`projection.trailing_months`) count as `client` once set; required fields are always `client`. New test `test_T4_5_template_basis_tells_placeholder_defaults_from_client_values`. Known limit: a client value equal to the `[P]` default shows as `default [P]` (open issue 3). |
| 2 | medium | `basis.py:264`: a negative catalog override (e.g. `engine.receipt_lines_per_pallet_mixed: -5`) reaches derived inbound and gives negative receipt lines (`rl=-39.08`) with no error. | **Fixed** at the point of use: `inbound_by_sku` requires the three catalog constants it reads to be > 0. New test `test_I60_inbound_catalog_values_must_be_positive` (6 cases). The missing sign rule in `ParamSet` itself (F1) is a blocker (open issue 1). |
| 3 | low | `basis.py:269`: regression from the raw-YAML override check: PyYAML reads `1e-2` as text, so it was rejected in `overrides` while accepted in typed fields. | **Fixed.** A value is rejected when the raw YAML value is a bool or the pydantic-coerced value is not a finite number. Deliberate change: quoted numeric text (`"0.5"`) is now accepted, as for typed fields. New tests `test_I60_override_numeric_text_accepted_like_typed_fields`, `test_I60_non_numeric_override_text_rejected`. |
| 4 | low | `inbound.py:127`: the `require_finite` hint in `derive_inbound` never names a catalog override that caused the inf. | **Fixed.** The hint now lists the three catalog ids. New test `test_I60_inbound_overflow_names_the_catalog_override`. |
| 5a | low | `design_day.py:35`: `select_design_day` is 75 lines. | **Fixed.** Extracted `_design_values`, `_stock`, `_factor_rows`; now 49 lines. No number changed (T4.1 unchanged, hand computation max_rel_err 0.00e+00). |
| 5b | low | `basis.py` is 414 lines (417 after the fix round). | **Deferred.** Under the 800-line maximum; about 140 lines are the `FIELDS` label table; splitting it would be churn in a shared tree. |

### Round 1 (after fix round 1)

Spec audit: pass_with_issues, 135 passed, 0 failed. T4.5 upgraded from weak to pass; findings 1-4 and 5a confirmed resolved. Proof audit: pass_with_issues, no findings, no proofs listed. No fix round followed, so both findings below stay open.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | low | `basis.py:33`: round-0 finding 5b still open, 417 lines (over "< 400 typical", under the 800 max). | Deferred (unchanged). Open issue 4. |
| 2 | low | `inbound.py:98`: new: `derive_inbound` is 51 lines, over the "< 50 lines" rule. The hint added by fix 4 brought it to 51. | Not fixed (no further round). Open issue 5. |

## Open issues

1. **Low, F1-owned (blocker from fix round 1): `ParamSet` has no sign or range rule for constant overrides.** F4 now rejects values ≤ 0 for the three constants it reads, but other readers (e.g. `engine/storage.py:216`, `storage.default_units_per_pallet`) still receive negative or zero overrides unchecked.
2. **Low, by design: in receipts mode with `sku=None`, the inbound catalog constants are never read, so `engine.receipt_lines_per_pallet_mixed: -5` raises nothing there** (probe2 section D: `receipts, sku=None, rl_mixed=-5: NO ERROR`). With `sku` given it raises. The guard is at the point of use, so an unused bad value passes; see issue 1 for the general fix.
3. **Low, accepted limit of the fix for round-0 finding 1:** a client value equal to the schema default is shown as `default [P]`. On `basis/example_basis.yaml`, several fields written in the file (`operations.hours_per_shift`, `operations.utilisation`, `operations.absenteeism`, ...) come out with origin `default` (probe2 section C). The YAML gives no other way to tell a confirmed value from a placeholder.
4. **Low, deferred: `src/whsizing/design/basis.py` is 417 lines** (round-1 finding 1).
5. **Low, open: `derive_inbound` in `src/whsizing/design/inbound.py` is 51 lines** (round-1 finding 2).
6. **Low, engine/F8-owned (blocker carried from F4b): `src/whsizing/engine/inputs.py:57` still documents the call as `select_design_day(..., sku=...)` without `catalog=`.** The requirement is documented in I61.
7. **Carried from F4b, not addressed by F4c:**
   - F4b issue 5: the derived-mode inbound peak-factor fallback uses `profile.seasonality.peak_to_average` over the whole history, not the candidate window.
   - F4b issue 6: the F4 round-0 spec audit text was clipped after its 9th finding; any later findings were never seen.
   - F4b issue 7: F2 fills `units_per_pallet` with its own 400, so a basis override of `storage.default_units_per_pallet` reaches F2-filled SKUs only if F8 passes it to `ingest`.
   - F4b issue 10: `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` was reported failing on F3 float noise; not re-run for this record.
8. **Contract change for F8/F9 (deliberate, not a defect):** quoted numeric text in `overrides` (`"0.5"`) is now accepted (round-0 finding 3 fix), and assumption origins follow the "set and different from the default" rule above.

F4b open issues resolved: issue 1 (finite growth overflow) by F4c-1; issue 2 (I55 register text) in the register itself, since `docs/INTERPRETATIONS.md:433-441` now states the I52 calendar-months rule ("a 365-day history counts as 12.0 and does not warn"), so the fix-round-1 blocker about "same 30.4375 convention" is stale; issue 4 (no row for empty `overrides`, T4.5 weak) by F4c-3 and the round-1 template test; issue 9 (YAML bool coerced to 1.0) by F4c-2.

Blockers reported during the build and fix round that **pass on re-run (2026-11-09)**, outside F4c:
- `tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param` (reported failing at build time): `1 passed`.
- `tests/unit/test_f6_throughput_properties.py::test_T6_8_row_order_does_not_change_the_result` (reported failing alone in fix round 1, `cube_asrs`): `3 passed` when run on its own. The full suite was not re-run for this record.

## Not applicable here and why

- **Done-when "the assumptions list renders in the report":** the report belongs to F9, which is not built. `write_design` writes `design/assumptions.json`.
- **Edits outside the F4 paths** (`ParamSet` sign rules in F1, the `engine/inputs.py` docstring, F8 wiring of `catalog=`, `sku=` and `ingest(default_units_per_pallet=...)`): owned by other features, listed as blockers.
- **Real client data:** none is available here, and client data must not leave the machine. F4c was exercised on tiny_golden and the synthetic ecom_mid set (730 days, 5000 SKUs).
- **Domain-expert review of the golden values:** T4.1 compares against `tests/golden/golden_values.json` (G1 oracle); an expert review of those values is outside this audit.
- **Docker, GitHub CI:** F4 does not depend on them. No F4 test is skipped.

## Fresh test output (run while writing this record, 2026-11-09)

The `design_day_short_window` warnings come from tiny_golden's 31-day history (2025-03-01..2025-03-31) and are expected. The `catalog_todo_sources` warning comes from the catalog load in the golden fixture. Repeated captured-stdout blocks are trimmed; the full short test summary is kept.

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f4_*.py tests/golden/test_f4_*.py -q -rA
........................................................................ [ 53%]
...............................................................          [100%]
==================================== PASSES ====================================
[... captured-stdout blocks trimmed; each shows one line like:
2026-11-09 08:42:17 [warning  ] design_day_short_window        history_end=2025-03-31 history_start=2025-03-01 trailing_months=12 ...]
__________ test_T4_1_design_day_and_inbound_equal_golden_spreadsheet ___________
---------------------------- Captured stdout setup -----------------------------
2026-11-09 08:42:17 [warning  ] catalog_todo_sources           count=72 total=72
2026-11-09 08:42:17 [warning  ] design_day_short_window        history_end=2025-03-31 history_start=2025-03-01 trailing_months=12
=========================== short test summary info ============================
PASSED tests/unit/test_f4_design.py::test_T4_2_design_percentile_moves_lines_monotonically
PASSED tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines[weekday_rate0]
PASSED tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines[weekday_rate1]
PASSED tests/unit/test_f4_design.py::test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock
PASSED tests/unit/test_f4_design.py::test_T4_5_assumptions_list_every_basis_field_exactly_once
PASSED tests/unit/test_f4_design.py::test_T4_5_template_basis_tells_placeholder_defaults_from_client_values
PASSED tests/unit/test_f4_design.py::test_T4_6_basis_with_unknown_key_raises_config_error[colour: blue\n]
PASSED tests/unit/test_f4_design.py::test_T4_6_basis_with_unknown_key_raises_config_error[projection: {horizon_years: 5, unknown_key: 1}\n]
PASSED tests/unit/test_f4_design.py::test_sla_window_derived_from_times_crossing_midnight[cutoff0-departure0-None-3.5]
PASSED tests/unit/test_f4_design.py::test_sla_window_derived_from_times_crossing_midnight[cutoff1-departure1-None-4.0]
PASSED tests/unit/test_f4_design.py::test_sla_window_derived_from_times_crossing_midnight[cutoff2-departure2-None-24.0]
PASSED tests/unit/test_f4_design.py::test_sla_window_derived_from_times_crossing_midnight[cutoff3-departure3-6.0-6.0]
PASSED tests/unit/test_f4_design.py::test_sla_window_given_must_be_positive
PASSED tests/unit/test_f4_design.py::test_percentile_above_100_clipped_to_max_and_flagged
PASSED tests/unit/test_f4_design.py::test_trailing_window_and_short_history
PASSED tests/unit/test_f4_design.py::test_stock_growth_rate_override_replaces_g_for_stock
PASSED tests/unit/test_f4_design.py::test_derived_inbound_falls_back_to_default_units_per_pallet
PASSED tests/unit/test_f4_design.py::test_receipts_mode_takes_percentile_of_daily_receipts
PASSED tests/unit/test_f4_design.py::test_basis_template_loads_and_marks_every_default[fr]
PASSED tests/unit/test_f4_design.py::test_basis_template_loads_and_marks_every_default[en]
PASSED tests/unit/test_f4_design.py::test_write_design_writes_design_day_and_assumptions
PASSED tests/unit/test_f4_design.py::test_default_upp_flagged_on_canonical_sku_master
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[flows-pallets_per_truck-0.0]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[operations-operating_days_per_year-0]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[projection-design_percentile-nan]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[projection-design_percentile--1.0]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[projection-horizon_years--1]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[projection-growth_rate--1.0]
PASSED tests/unit/test_f4_design.py::test_invalid_basis_values_raise_config_error[projection-trailing_months-0]
PASSED tests/unit/test_f4_design.py::test_no_operating_day_in_window_raises
PASSED tests/unit/test_f4_design.py::test_non_positive_pack_data_raises
PASSED tests/unit/test_f4_design.py::test_derived_inbound_without_sku_table_names_the_fix
PASSED tests/unit/test_f4_register.py::test_I55_default_window_is_24_months_when_history_covers_it[start0-end0-24]
PASSED tests/unit/test_f4_register.py::test_I55_default_window_is_24_months_when_history_covers_it[start1-end1-24]
PASSED tests/unit/test_f4_register.py::test_I55_default_window_is_24_months_when_history_covers_it[start2-end2-12]
PASSED tests/unit/test_f4_register.py::test_I55_default_window_is_24_months_when_history_covers_it[start3-end3-12]
PASSED tests/unit/test_f4_register.py::test_I55_default_window_drives_design_day_and_inbound
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start0-None-False]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start1-12-False]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start2-None-False]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start3-6-True]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start4-None-True]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start5-24-True]
PASSED tests/unit/test_f4_register.py::test_I55_template_leaves_window_unset
PASSED tests/unit/test_f4_register.py::test_I56_receipts_peak_factor_defaults_to_one
PASSED tests/unit/test_f4_register.py::test_I56_unknown_pallet_days_left_out_of_pallets_percentile_only
PASSED tests/unit/test_f4_register.py::test_I57_ratio_drift_raised_when_percentile_is_zero
PASSED tests/unit/test_f4_register.py::test_I57_no_ratio_drift_when_both_zero
PASSED tests/unit/test_f4_register.py::test_I59_default_upp_is_info_with_share_of_design_inbound_units
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[projection-peak_stock_factor-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[projection-peak_stock_factor--1.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[projection-peak_stock_factor-nan]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[projection-growth_rate-inf]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[projection-growth_rate--1.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-inbound_peak_factor-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-inbound_peak_factor--2.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-inbound_peak_factor-nan]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-utilisation-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-utilisation-1.01]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-dock_utilisation-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-dock_utilisation-1.5]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-absenteeism-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-absenteeism--0.01]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-pfd_allowance-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-returns_rate-1.01]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-returns_rate--0.01]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[service-same_day_share-1.5]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-shifts_per_day-0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-hours_per_shift-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-paid_hours_per_person_day--7.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[operations-annual_paid_hours_per_fte-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-truck_dwell_hours-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[building-area_m2-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[building-clear_height_m--1.0]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[building-rent_eur_m2_year-inf]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[finance-discount_rate-nan]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[finance-energy_price_eur_kwh--inf]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[service-sla_window_hours-nan]
PASSED tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values[flows-pallet_order_weight_kg-inf]
PASSED tests/unit/test_f4_register.py::test_I60_rejects_non_finite_labor_cost
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[operations-utilisation-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[operations-absenteeism-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[operations-pfd_allowance-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[flows-returns_rate-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[flows-dock_utilisation-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[service-same_day_share-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[flows-inbound_peak_factor-None]
PASSED tests/unit/test_f4_register.py::test_I60_boundary_values_accepted[projection-design_percentile-120.0]
PASSED tests/unit/test_f4_register.py::test_I60_load_basis_rejects_nan_and_inf_from_yaml[peak_stock_factor: 1.15-peak_stock_factor: .nan-projection.peak_stock_factor]
PASSED tests/unit/test_f4_register.py::test_I60_load_basis_rejects_nan_and_inf_from_yaml[growth_rate: 0.04-growth_rate: .inf-projection.growth_rate]
PASSED tests/unit/test_f4_register.py::test_I60_load_basis_rejects_nan_and_inf_from_yaml[area_m2: 410-area_m2: -.inf-building.area_m2]
PASSED tests/unit/test_f4_register.py::test_I60_load_basis_rejects_nan_and_inf_from_yaml[operator: 25.5-operator: .nan-finance.labor_cost_eur_h]
PASSED tests/unit/test_f4_register.py::test_daily_missing_column_raises_whsizing_error[cube_m3]
PASSED tests/unit/test_f4_register.py::test_daily_missing_column_raises_whsizing_error[pallets_out]
PASSED tests/unit/test_f4_register.py::test_daily_missing_column_raises_whsizing_error[is_operating]
PASSED tests/unit/test_f4_register.py::test_daily_missing_column_raises_whsizing_error[weekday]
PASSED tests/unit/test_f4_register.py::test_receipts_mode_missing_receipt_column_names_it
PASSED tests/unit/test_f4_register.py::test_catalog_is_required_whatever_the_working_directory
PASSED tests/unit/test_f4_register.py::test_explicit_catalog_gives_the_same_result_from_any_directory
PASSED tests/unit/test_f4_register.py::test_I58_engine_sku_frame_with_extra_columns_accepted
PASSED tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_must_exceed_minus_one[-1.0]
PASSED tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_must_exceed_minus_one[-5.0]
PASSED tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_must_exceed_minus_one[nan]
PASSED tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_must_exceed_minus_one[inf]
PASSED tests/unit/test_f4_register.py::test_I60_load_basis_rejects_stock_growth_rate_override_le_minus_one
PASSED tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_above_minus_one_accepted
PASSED tests/unit/test_f4_register.py::test_growth_factor_overflow_raises_config_error[1e+308-5]
PASSED tests/unit/test_f4_register.py::test_growth_factor_overflow_raises_config_error[0.5-5000]
PASSED tests/unit/test_f4_register.py::test_I56_template_label_states_both_inbound_modes[en]
PASSED tests/unit/test_f4_register.py::test_I56_template_label_states_both_inbound_modes[fr]
PASSED tests/unit/test_f4_register.py::test_I60_finite_but_huge_basis_value_never_gives_inf[update0-design_day\\.lines = inf]
PASSED tests/unit/test_f4_register.py::test_I60_finite_but_huge_basis_value_never_gives_inf[update1-design_day\\.stock_units = inf.*overrides\\.stock_growth_rate]
PASSED tests/unit/test_f4_register.py::test_I60_finite_but_huge_basis_value_never_gives_inf[update2-inbound\\.trucks_per_day = inf]
PASSED tests/unit/test_f4_register.py::test_I60_huge_growth_named_by_derive_inbound
PASSED tests/unit/test_f4_register.py::test_I60_realistic_growth_gives_finite_design_values
PASSED tests/unit/test_f4_register.py::test_I60_override_values_must_be_real_numbers[stock_growth_rate: true-True]
PASSED tests/unit/test_f4_register.py::test_I60_override_values_must_be_real_numbers[stock_growth_rate: false-False]
PASSED tests/unit/test_f4_register.py::test_I60_override_values_must_be_real_numbers[manual_p2p.pick_rate_shelving_lines_h: .nan-nan]
PASSED tests/unit/test_f4_register.py::test_I60_override_values_must_be_real_numbers[manual_p2p.pick_rate_shelving_lines_h: .inf-inf]
PASSED tests/unit/test_f4_register.py::test_I60_override_bool_rejected_on_a_model_too
PASSED tests/unit/test_f4_register.py::test_I60_integer_and_float_overrides_accepted
PASSED tests/unit/test_f4_register.py::test_I60_override_numeric_text_accepted_like_typed_fields[stock_growth_rate: 1e-2-0.01]
PASSED tests/unit/test_f4_register.py::test_I60_override_numeric_text_accepted_like_typed_fields[stock_growth_rate: 1.0e-2-0.01]
PASSED tests/unit/test_f4_register.py::test_I60_override_numeric_text_accepted_like_typed_fields[stock_growth_rate: "0.5"-0.5]
PASSED tests/unit/test_f4_register.py::test_I60_non_numeric_override_text_rejected
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[engine.receipt_lines_per_pallet_full--5.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[engine.receipt_lines_per_pallet_full-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[engine.receipt_lines_per_pallet_mixed--5.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[engine.receipt_lines_per_pallet_mixed-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[storage.default_units_per_pallet--5.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_catalog_values_must_be_positive[storage.default_units_per_pallet-0.0]
PASSED tests/unit/test_f4_register.py::test_I60_inbound_overflow_names_the_catalog_override
PASSED tests/unit/test_f4_register.py::test_I55_template_states_calendar_month_warning[en-12 calendar months]
PASSED tests/unit/test_f4_register.py::test_I55_template_states_calendar_month_warning[fr-12 mois calendaires]
PASSED tests/golden/test_f4_golden.py::test_T4_1_design_day_and_inbound_equal_golden_spreadsheet
135 passed in 1.22s
```
