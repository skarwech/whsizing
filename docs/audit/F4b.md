# F4b audit: Design day remediation (register I55-I60, basis validation)

## Verdict: pass_with_issues

All 109 F4 tests pass (0 failed, 0 skipped). T4.1 to T4.6 and every register item I55 to I60 have a passing test, golden values are unchanged, and independent hand computations match the engine on tiny_golden and on the 730-day ecom_mid set.
The verdict stays below `pass` because the round-1 spec audit left 4 low findings open and marked T4.5 as weak, and no fix round followed. Both round-1 auditors (spec and proof) returned pass_with_issues.

Scope: F4b owns `src/whsizing/design/**` (`basis.py`, `design_day.py`, `inbound.py`, `assumptions.py`, `__init__.py`), `basis/*.yaml`, `tests/unit/test_f4_*.py` and `tests/golden/test_f4_*.py`. Spec: description.md l.745-776 (F4) and the binding register entries I55-I60 in `docs/INTERPRETATIONS.md` (l.430-479), plus the open issues of `docs/audit/F4.md`. No schema change was made (`schema_changes: []`).

Files changed by the build: `src/whsizing/design/basis.py`, `design_day.py`, `inbound.py`, `assumptions.py`, `basis/template_en.yaml`, `basis/template_fr.yaml`, `tests/unit/test_f4_register.py` (new), `tests/unit/test_f4_design.py`, `tests/golden/test_f4_golden.py`.

While writing this record (2026-11-08), ruff check, ruff format --check and pyright were re-run on the F4 paths: `All checks passed!`, `8 files already formatted`, `0 errors, 0 warnings, 0 informations`. File sizes: `basis.py` 384 lines, `test_f4_register.py` 413 lines, all under the 800-line limit.

## Acceptance and register tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T4.1 | `tests/golden/test_f4_golden.py::test_T4_1_design_day_and_inbound_equal_golden_spreadsheet` | pass | Every golden `design_day.*`, `inbound.*` and `stock.*` key matches the G1 oracle within 0.5 % (dates, flags and counts exactly). A coverage check fails if any golden F4 key is not compared. The keys `stock.dead_stock_skus` and `stock.dead_stock_cube_m3`, which G1d added after the F4 audit, are now compared (engine 0 and 0.0, equal to golden). No golden value changed. |
| T4.2 | `tests/unit/test_f4_design.py::test_T4_2_design_percentile_moves_lines_monotonically` | pass | Over P50..P100, `lines*` never decreases and is strictly higher at P100 than at P50. Each value equals `np.percentile(operating-day lines, q) × 1.04^5` at rel 1e-12, so the test is not tautological. |
| T4.3 | `tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines[weekday_rate0\|weekday_rate1]` | pass | 24 hourly values, `\|Σ hourly − lines*\| < 1e-6`, `peak_hour_lines == max(hourly)`. One case is g = 0 with only Saturdays operating (design weekday 5). |
| T4.4 | `tests/unit/test_f4_design.py::test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock` | pass | Real F3 path with 3 equal inventory snapshots (OLS stock growth 0, asserted). At g = 0, `units_in` equals the mean operating-day units out at rel 1e-12. A stock growth of 252 units/yr adds exactly 1 unit/day. |
| T4.5 | `tests/unit/test_f4_design.py::test_T4_5_assumptions_list_every_basis_field_exactly_once` | pass (weak, per round-1 spec audit) | On `golden_basis.yaml` and `basis/example_basis.yaml`, each leaf field appears exactly once, override rows match `basis.overrides` with origin `override`, and extra rows are `derived` only. Weak: test_f4_design.py:121 leaves the `overrides` field out of "every field", and with empty overrides that field has no row (51 leaf fields, 50 rows). Report rendering waits for F9. See open issue 4. |
| T4.6 | `tests/unit/test_f4_design.py::test_T4_6_basis_with_unknown_key_raises_config_error[...]` (2 cases) | pass | An unknown key at the top level and one nested in `projection` both raise `ConfigError` matching "unknown key" through `load_basis`. |
| I55 | `tests/unit/test_f4_register.py::test_I55_default_window_is_24_months_when_history_covers_it` (4 cases) | pass | With `trailing_months` unset, the window is 24 when the history covers ≥ 23.9 months (calendar days / 30.4375), else 12. Includes the 2024-01-01..2025-12-30 history (730 days, 23.98 months), which now gets 24. An explicit value is used as given. |
| I55 | `tests/unit/test_f4_register.py::test_I55_default_window_drives_design_day_and_inbound` | pass | P_lines and the derived inbound mean both use the 24-month window. The assumptions row `projection.trailing_months` is 24 with origin `derived` when unset, and 12 with origin `client` when the file sets it. |
| I55 | `tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used` (5 cases) | pass | The `design_day_short_window` warning fires when the window actually used covers less than 12 months, and not otherwise. |
| I55 | `tests/unit/test_f4_register.py::test_I55_template_leaves_window_unset` | pass | The FR and EN templates leave `projection.trailing_months` unset, so the I55 default applies to a basis started from a template. |
| I56 | `tests/unit/test_f4_register.py::test_I56_receipts_peak_factor_defaults_to_one` | pass | In receipts mode `Inbound.peak_factor` is 1.0 when `flows.inbound_peak_factor` is null. Derived mode is unchanged. |
| I56 | `tests/unit/test_f4_register.py::test_I56_unknown_pallet_days_left_out_of_pallets_percentile_only` | pass | Days with an unknown pallet count are left out of the pallets P95 only; units and lines keep them; each is × gf. |
| I56 | `tests/unit/test_f4_register.py::test_I56_template_label_states_both_inbound_modes[en\|fr]` | pass | Added in fix round 1. The template label of `inbound_peak_factor` states both the derived-mode and the receipts-mode default. |
| I57 | `tests/unit/test_f4_register.py::test_I57_ratio_drift_raised_when_percentile_is_zero` | pass | At P10 on golden, P_pallets_out = 0 and m* > 0 give `F_RATIO_DRIFT:pallets_out` with value None and severity warning. |
| I57 | `tests/unit/test_f4_register.py::test_I57_no_ratio_drift_when_both_zero` | pass | When P_m and m* are both 0, no drift flag is raised. |
| I58 | `tests/unit/test_f4_register.py::test_I58_engine_sku_frame_with_extra_columns_accepted` | pass | An engine-like frame (null `hazmat`/`temperature_class`, a stock-only orphan row) gives a result identical to the plain frame. Re-applying `with_pack_data` adds no `_right` columns. |
| I59 | `tests/unit/test_f4_register.py::test_I59_default_upp_is_info_with_share_of_design_inbound_units` | pass | Exactly one `F_DEFAULT_UPP`, severity info, value equal to the hand-computed share of design inbound units on the default, placed last. |
| I60 | `tests/unit/test_f4_register.py::test_I60_check_basis_rejects_invalid_values` (30 cases) | pass | Every range listed in I60, plus NaN and ±inf in each listed section, raises `ConfigError`. |
| I60 | `tests/unit/test_f4_register.py::test_I60_rejects_non_finite_labor_cost` | pass | NaN/inf in a mapping value (`finance.labor_cost_eur_h`) is rejected. |
| I60 | `tests/unit/test_f4_register.py::test_I60_boundary_values_accepted` (8 cases) | pass | Boundary values allowed by I60 (utilisation 1.0, absenteeism 0.0, null inbound_peak_factor, percentile 120, ...) are accepted. |
| I60 | `tests/unit/test_f4_register.py::test_I60_load_basis_rejects_nan_and_inf_from_yaml` (4 cases) | pass | YAML `.nan`, `.inf` and `-.inf` are rejected by `load_basis`, naming the field. |
| I60 (fix round 1) | `tests/unit/test_f4_register.py::test_I60_stock_growth_rate_override_must_exceed_minus_one[-1.0\|-5.0\|nan\|inf]`, `test_I60_load_basis_rejects_stock_growth_rate_override_le_minus_one`, `test_I60_stock_growth_rate_override_above_minus_one_accepted` | pass | `overrides.stock_growth_rate` must be finite and > −1, through both `check_basis` and `load_basis`; −0.5 is accepted. RED before the fix (8 failed, 1 passed, per the fix report). |
| (fix round 1) | `tests/unit/test_f4_register.py::test_growth_factor_overflow_raises_config_error[1e+308-5\|0.5-5000]` | pass | An overflowing `(1+g)^T` raises `ConfigError`, not `builtins.OverflowError`. RED before the fix. |
| F4b-6 | `tests/unit/test_f4_register.py::test_daily_missing_column_raises_whsizing_error` (4 cases), `test_receipts_mode_missing_receipt_column_names_it` | pass | A daily frame missing a column raises `WhsizingError` naming it (not a raw polars `ColumnNotFoundError`); a missing receipts column raises `ConfigError` naming it. |
| F4b-7 | `tests/unit/test_f4_register.py::test_catalog_is_required_whatever_the_working_directory`, `test_explicit_catalog_gives_the_same_result_from_any_directory` | pass | `catalog=None` raises `ConfigError` from any working directory; an explicit catalog gives the same result from any directory. |

The other F4 unit tests carried over from F4 (SLA window across midnight, percentile clipping, trailing window, stock growth override, upp fallback, receipts mode, templates, `write_design`, `check_basis` named fields, empty window, non-positive pack data, missing `sku=`) all pass. The F4 test `test_warns_when_24_months_available_but_window_shorter` and its warning `design_day_window_below_24_months` were removed, because I55 supersedes them.

TDD caveat (from the build report): `test_f4_register.py` first failed at collection (`window_months` did not exist), so there was no per-test RED run for the build. The old behaviour each test catches is documented in `docs/audit/F4.md` (proofs 6 and 7, open issues 1, 4, 7, 8, 10). The fix-round-1 tests did have a per-test RED run.

## Proofs (captured by the auditors during the audit)

The F4b spec auditors captured these proofs in round 0 or round 1. All were re-run while writing this record on 2026-11-08 with the same results. The round-0 and round-1 proof audits returned pass_with_issues with no findings and no proofs listed. Scripts are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/`, written `<s>/` below. Every command runs from `/Users/skarwech/saas_v1`. `[warning]` log lines are trimmed.

1. **I55 end to end on ecom_mid (730 days, 5000 SKUs): the template basis (window unset) uses 24 months with origin `derived`; `golden_basis.yaml` (12 in the file) uses 12 with origin `client`. P_m, m*, the reference day, derived inbound units and pallets equal an independent hand computation exactly** (rounds 0 and 1). The template case also shows I57's both-zero rule on real data (pallets_out P = m* = 0, no flag), and the golden-basis case a normal drift flag.
   Command: `uv run python <s>/audit_F4b/hand.py`
   ```
   --- basis/template_en.yaml: history 2024-01-01..2025-12-30 window=24.0 origin=derived cand=626
     events: []
     ref engine/hand: 2025-12-10 2025-12-10
     lines: engine P=2818.750000 hand P=2818.750000 | engine m*=3267.703797 hand m*=3267.703797
     pallets_out: engine P=0.000000 hand P=0.000000 | engine m*=0.000000 hand m*=0.000000
     inbound units engine=2573.314533 hand=2573.314533; pallets engine=7.270452 hand=7.270452; pf=1.7941
     flags: []
   --- tests/golden/golden_basis.yaml: history 2024-01-01..2025-12-30 window=12.0 origin=client cand=313
     lines: engine P=2870.600000 hand P=2870.600000 | engine m*=3492.523822 hand m*=3492.523822
     flags: [('F_RATIO_DRIFT:pallets_out', 'warning', 0.5705908750934929)]
   ```

2. **I56 on realistic receipts data: units, pallets and trucks equal P95 of receipts over the candidate days × (1+g)^T; peak_factor defaults to 1.0 with origin `derived`; `catalog=None` from another working directory raises `ConfigError`** (rounds 0 and 1).
   Command: `uv run python <s>/audit_F4b/receipts.py`
   ```
   engine units=14928.8417 hand=14928.8417
   engine pallets=42.9360 hand=42.9360 trucks engine=1.6514 hand=1.6514
   peak_factor 1.0 row [(1.0, 'derived')]
   catalog=None from /private/var/folders/.../tmp5h59m9an -> catalog is required: pass catalog=load_catalog(Project.catalog)
   ```

3. **Edge cases: the I55 threshold falls between 727 and 728 days (23.9 × 30.4375 = 727.46); I57 raises `F_RATIO_DRIFT` with value None at P10; I60 names every bad field in one `ConfigError`; all-null receipt pallets raise `ConfigError`; an empty daily frame or a missing column raises `WhsizingError`** (round 0).
   Command: `uv run python <s>/audit_F4b/edge.py`
   ```
     727 days -> window 12
     728 days -> window 24
     multi: basis: invalid value(s): projection.growth_rate = nan (must be finite); projection.peak_stock_factor = -1.0 (must be > 0)
      [('F_SHORT_HISTORY', 26.0), ('F_RATIO_DRIFT:pallets_out', None)] 0.0 1.2166529024000001
     ConfigError: flows.inbound_mode 'receipts': no pallet count in the receipts; use 'derived'
     WhsizingError: daily frame: no day, no design day can be chosen
     WhsizingError: daily frame: missing column(s) ['lines'] (F3 build_tables output)
     None master keeps pack: 0 nulls; equal: True
   ```

4. **Round-0 medium finding resolved: `overrides.stock_growth_rate` ≤ −1, NaN and ±inf are rejected by `check_basis` and `load_basis`; values just above −1 are accepted and give positive stock** (round 0 found the gap, round 1 confirmed the fix).
   Round 0 before the fix (auditor output): `stock_growth_rate=-5.0: load_basis ACCEPTED ... design stock_units=-6826547.199999999 stock_cube_m3=-32782.26824927437`.
   Command (after the fix): `uv run python <s>/audit_F4b/round2.py` (finding 1 section)
   ```
     stock_growth_rate=-1.0: whsizing.errors.ConfigError: basis: invalid value(s): overrides.stock_growth_rate = -1.0 (must be finite and > -1)
     stock_growth_rate=-5.0: whsizing.errors.ConfigError: basis: invalid value(s): overrides.stock_growth_rate = -5.0 (must be finite and > -1)
     stock_growth_rate=-0.9999999: OK lines=137.482 stock=6.66655e-32 in=125.502 finite=True
     yaml .nan: ConfigError basis: invalid value(s): overrides.stock_growth_rate = nan (must be finite and > -1)
     yaml -.inf: ConfigError basis: invalid value(s): overrides.stock_growth_rate = -inf (must be finite and > -1)
     yaml 1e999: ConfigError basis: invalid value(s): overrides.stock_growth_rate = inf (must be finite and > -1)
   ```

5. **Round-0 finding 2 partly resolved: an overflowing growth factor now raises `ConfigError`, but a finite growth factor can still overflow downstream to inf** (round 1; the residual is open issue 1).
   Command: `uv run python <s>/audit_F4b/round2.py` (finding 2 section)
   ```
     g=1e+308 T=5: whsizing.errors.ConfigError: growth factor (1 + 1e+308)^5 overflows: check projection.growth_rate, projection.horizon_years and overrides.s...
     g=0.5 T=5000: whsizing.errors.ConfigError: growth factor (1 + 0.5)^5000 overflows: ...
     g=1e+308 T=1: OK lines=inf stock=inf in=inf finite=False
     stock_growth_rate=1e308 T=1: OK lines=117.52 stock=inf in=107.28 finite=False
   ```

6. **Round-0 finding 3 resolved, and I55 template behaviour: both templates state the I56 receipts-mode default, leave `trailing_months` commented out, and equal fresh `basis_template` output byte for byte** (rounds 0 and 1).
   Commands: `sed -n 35p basis/template_en.yaml; sed -n 35p basis/template_fr.yaml; grep -n trailing_months basis/template_*.yaml`, then `basis_template` into a scratch folder, compare bytes, `load_basis` and check `model_fields_set`.
   ```
   inbound_peak_factor: null  # [P] inbound peak factor (null = outbound peak-to-average in derived mode, 1.0 in receipts mode)
   inbound_peak_factor: null  # [P] facteur de pointe réception (null = pointe/moyenne sortie en mode dérivé, 1,0 en mode réceptions)
   basis/template_en.yaml:30:  # trailing_months: 12  # [P] design-day window (unset: 24 if the history covers 24 months, else 12) (months)
   fr identical to repo: True trailing set: False
   en identical to repo: True trailing set: False
   ```

7. **An independent hand computation of the golden design day, stock and derived inbound (numpy percentile, reference-day ratios, 1.04^5, I13 per SKU) still matches the engine after F4b and its fix round** (round 1, F4 script).
   Command: `uv run python <s>/audit_F4/hand.py`
   ```
   n_op 26 P95 lines 113.0 ref 2025-03-10 engine ref 2025-03-10
   units        hand=188.132959 engine=188.132959 rel=1.51e-16
   lines        hand=137.481778 engine=137.481778 rel=0.00e+00
   sum hourly - lines 0.0 peak 18.80092690204445 18.80092690204445
   stock hand 8110.87740649472 engine 8110.877406494719
   inbound units hand 125.50242631680003 engine 125.50242631680003
   flags ['F_SHORT_HISTORY', 'F_RATIO_DRIFT:weight_kg', 'F_RATIO_DRIFT:pallets_out']
   golden lines 137.48177797120002 ref 2025-03-10 flags F_SHORT_HISTORY,F_RATIO_DRIFT:weight_kg,F_RATIO_DRIFT:pallets_out
   ```

8. **The I55 "< 12" warning uses the I52 calendar-month convention, not raw days / 30.4375** (round 0; the basis of open issue 2). A 365-day history reads 11.99 months by days / 30.4375 but does not warn.
   Command: `uv run python <s>/audit_F4b/edge.py` (I55 short-window section)
   ```
     364 days (11.9589 months by days/30.4375): warn=True
     365 days (11.9918 months by days/30.4375): warn=False
     366 days (12.0246 months by days/30.4375): warn=False
   ```

## Audit rounds

### Build (before round 0)

The build addressed the eight F4b items: I55 (`window_months`), I56 (receipts peak factor 1.0, named missing receipts columns), I57 (drift flag at P_m = 0), I59 (`F_DEFAULT_UPP` severity info with a units share), I60 (table-driven `check_basis` with a finiteness scan), `history_span` errors as `WhsizingError`, no package-default catalog, and I58 (`with_pack_data` idempotent, extra columns accepted). It also fixed T4.1's coverage check after G1d added two `stock.*` golden keys.

### Round 0: tests 99 passed, 0 failed

The spec audit returned **pass_with_issues** with every T-id and I-id pass. The proof audit returned **pass_with_issues** with no findings listed. Some finding texts in the audit history are cut off ("…[clipped]"); they are transcribed as far as they are visible.

| Severity | Finding | Resolution (fix round 1) |
|---|---|---|
| medium | `overrides['stock_growth_rate']` is raised to a power in F4 step 7 with no range check. A value ≤ −1 loads silently and gives negative design stock. I60 rejects `projection.growth_rate ≤ −1` for the same hazard, but the override replaces g in that formula (design_day.py:59). | **Fixed.** `check_basis` (called by `load_basis`, `select_design_day` and `derive_inbound`) rejects `overrides.stock_growth_rate` unless it is finite and > −1. RED run: 8 failed, 1 passed. Confirmed in round 1 (proof 4). |
| low | Extreme but finite growth inputs raise a raw `builtins.OverflowError` from `growth_factor` (basis.py:268). | **Fixed (partly, per round 1).** `growth_factor` catches `OverflowError` and raises `ConfigError` naming the three fields. Round 1 found that a finite growth factor can still overflow downstream (proof 5, open issue 1). |
| low | The client-facing label of `flows.inbound_peak_factor` still says "null = outbound peak-to-average", which is wrong in receipts mode after I56 (basis.py:110, template_en.yaml:35, template_fr.yaml:35). | **Fixed.** EN and FR labels updated in `FIELDS`; templates regenerated with `basis_template`, not edited by hand. New test `test_I56_template_label_states_both_inbound_modes`, RED before the fix (proof 6). |
| low | Mixed month conventions: `window_months` uses (days+1)/30.4375 (I55 literal), `warn_short_window` uses the I52 `calendar_months` helper. I55 says the "< 12" warning uses "the same 30.4375 convention" (basis.py:312). The auditor judged the code sensible and the register text in need of amendment. | **Deferred.** Code kept: a 365-day history or a 12-month window must not warn. The text amendment belongs to `docs/INTERPRETATIONS.md`, which F4b does not own; exact wording filed as a blocker. Still open (open issue 2). |
| low | `select_design_day` and `derive_inbound` now require `catalog=` (`ConfigError` when None). The spec signature is `select_design_day(profile, basis, daily)` and the register does not record the requirement (inbound.py:21). | **Deferred.** Behaviour kept: there is no package default catalog (`Project.catalog` resolves against project.yaml) and derived inbound needs catalog parameters. Register and engine docstring are not F4b paths; filed as a blocker. Still open (open issue 3). |

Fix-round-1 totals: 3 fixed (one only partly, per round 1), 2 deferred, 0 rejected.

Blockers reported by fix round 1:

- `docs/INTERPRETATIONS.md` I55 (register owner): replace "(same 30.4375 convention)" with a statement that the "< 12" warning uses the I52 `calendar_months` convention, so a 365-day history or a 12-month window on a longer history counts as 12.0 and does not warn.
- `docs/INTERPRETATIONS.md` and F8: add an entry stating that `select_design_day(profile, basis, daily, *, sku, catalog)` and `derive_inbound(profile, basis, daily, sku, *, catalog)` require `catalog=load_catalog(Project.catalog)` and raise `ConfigError` without it. `src/whsizing/engine/inputs.py:57` documents the call as `select_design_day(..., sku=...)` with no `catalog=`.
- Pre-existing, not caused by F4b: `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` fails on F3 float-summation noise (`cube_per_order_m3.p50 0.003281593932 != 0.0032815939320000004`). It does not import `whsizing.design`. Not re-checked while writing this record.

### Round 1: tests 109 passed, 0 failed

The spec audit returned **pass_with_issues**: T4.1-T4.4 and T4.6 pass, T4.5 **weak**. The proof audit returned **pass_with_issues** with no findings listed. No fix round followed, so all four findings are open.

| Severity | Finding | Status |
|---|---|---|
| low (residual of round-0 finding 2) | A finite growth factor can still overflow in `design = base * gf` (design_day.py:54) and `stock_units = avg_units * stock_k` (design_day.py:92), so inf design values reach `DesignDay` silently. This conflicts with I60 "Client inputs never reach the engine as NaN or ±inf". The inputs are absurd (growth rate 1e308). | **Open** (open issue 1, proof 5). |
| low (carried, register-owned) | Round-0 finding 4: I55 still says the "< 12" warning uses "the same 30.4375 convention"; the code uses I52 `calendar_months` (docs/INTERPRETATIONS.md:435). | **Open** (open issue 2, proof 8). Re-checked while writing this record: the register text is unchanged. |
| low (carried, register-owned) | Round-0 finding 5: the `catalog=` requirement is not in the register, and `engine/inputs.py:57` still documents the call without it. Existing callers (`tests/golden/test_f6_storage_golden.py:50`, `tests/golden/test_g1_register.py:92`) already pass `catalog=`, so nothing breaks today. | **Open** (open issue 3). Re-checked while writing this record: same callers, same docstring. |
| low (carried from F4 open issue 6) | No Assumption row for the `overrides` field when the basis has no overrides; F4 step 9 and T4.5 say "one Assumption per basis field ... exactly once". T4.5 leaves `overrides` out explicitly (test_f4_design.py:121), so it does not check this case (assumptions.py:42). Auditor output: `overrides empty: {} \| rows with key starting overrides: []`, `leaf fields 51 rows 50`. | **Open** (open issue 4, T4.5 weak). |

### F4 open issues scorecard (docs/audit/F4.md)

| F4 open issue | F4b outcome |
|---|---|
| 1. "Use 24 months when available" not applied | **Fixed** by I55 (`window_months`; proofs 1 and 3). |
| 2. Basis validation incomplete | **Fixed** by I60 (`check_basis`; 30 + 4 + 8 test cases), extended in fix round 1 to `overrides.stock_growth_rate`. |
| 3. `select_design_day` needs `sku=` | **Partly resolved.** `sku=` is now registered (I58). The added `catalog=` requirement is not registered (open issue 3). |
| 4. No `F_RATIO_DRIFT` at P_m = 0 | **Fixed** by I57. |
| 5. `F_DEFAULT_UPP` unregistered and in both flag lists | **Registered** by I59 (severity info, units share). It stays in both `Inbound.flags` and `DesignDay.flags` deliberately (I59 places it in the I46 order, which F6 reads from `DesignDay.flags`). |
| 6. No `overrides` row in the assumptions | **Unchanged** (open issue 4). |
| 7. Receipts-mode choices unregistered | **Fixed** by I56 (peak factor 1.0; proof 2). |
| 8. `catalog=None` depends on the working directory | **Fixed**: `catalog=None` now raises `ConfigError` (proof 2). |
| 9. Inbound peak-factor fallback uses the whole history | **Unchanged.** Spec silent, not in the F4b task list, derived mode unchanged per I56 (open issue 5). |
| 10. Raw polars `ColumnNotFoundError` | **Fixed**: `WhsizingError` naming the columns (proof 3). |
| 11. Round-0 F4 audit text clipped | **Unchanged** (open issue 6). |
| 12. F2 400 units-per-pallet vs basis override | **Unchanged**, cross-feature (open issue 7). |

## Open issues

1. **Low, F4b-owned: finite growth factors can still overflow to inf downstream.** `growth_rate = 1e308, horizon 1` or `overrides.stock_growth_rate = 1e308` give `lines=inf` or `stock=inf` without error (proof 5), against I60's "never NaN or ±inf". Absurd inputs only.
2. **Low, register-owned: I55 warning convention text.** `docs/INTERPRETATIONS.md:435` says "same 30.4375 convention"; the code uses I52 `calendar_months` (a 365-day history does not warn). The code is considered correct; the register text needs the amendment filed as a blocker.
3. **Low, register-owned, contract change for F8: `catalog=` is required.** `select_design_day` and `derive_inbound` raise `ConfigError` without `catalog=`. Not in the register; `src/whsizing/engine/inputs.py:57` documents the call without it.
4. **Low: no Assumption row for an empty `overrides` field; T4.5 is weak on this point.** "Renders in the report" cannot be checked until F9 exists.
5. **Low (nit), F4b-owned, carried from F4 issue 9:** the derived-mode inbound peak-factor fallback uses `profile.seasonality.peak_to_average` over the whole history, not the candidate window.
6. **Unaddressed, carried from F4 issue 11:** the F4 round-0 spec audit text was clipped after its 9th finding; any later findings were never seen.
7. **Cross-feature, carried from F4 issue 12:** F2 fills `units_per_pallet` with its own 400, so a basis override of `storage.default_units_per_pallet` reaches F2-filled SKUs only if F8 passes it to `ingest`.
8. **Contract changes other features must follow (from the build blockers, deliberate, not defects):**
   - F6 (I18, I28): in receipts mode `Inbound.peak_factor` now defaults to 1.0 when `flows.inbound_peak_factor` is null (I56); it used to be the outbound peak-to-average. Derived mode is unchanged.
   - `F_DEFAULT_UPP` severity changed from warning to info (I59), still in both `Inbound.flags` and `DesignDay.flags`.
   - The FR and EN templates now write `trailing_months` commented out (I55), a step beyond "update the comment" so the I55 default can apply.
9. **Observed while writing this record, not an auditor finding:** the auditor's `round2.py` output includes `yaml true: ACCEPTED overrides={'stock_growth_rate': 1.0}`. A YAML boolean is coerced to a 100 % stock growth rate instead of being rejected. Low impact, but it is a silent type coercion on a client input.
10. **Pre-existing, outside F4b:** `tests/property/test_f3_properties.py::test_T3_7_shuffling_rows_leaves_profile_unchanged` was reported failing in fix round 1 on F3 float noise. Not re-run for this record.

## Not applicable here and why

- **Edits to `docs/INTERPRETATIONS.md` and `src/whsizing/engine/`:** outside the F4b paths. The proposed amendments (I55 warning convention, `catalog=` contract) are listed as fix-round blockers.
- **F8 wiring (`catalog=`, `sku=`, `ingest(default_units_per_pallet=...)`):** F8 owns the call site.
- **Done-when "the assumptions list renders in the report":** the report belongs to F9. `write_design` writes `design/assumptions.json`, covered by `test_write_design_writes_design_day_and_assumptions`.
- **Real client data:** none is available here, and client data must not leave the machine. F4b was exercised on tiny_golden and the synthetic ecom_mid set (730 days, 5000 SKUs).
- **Domain-expert review of the golden values:** T4.1 compares against the G1 Python oracle and `tests/golden/golden_values.json`; an expert review of those values is outside this audit.
- **Docker, GitHub CI:** F4 does not depend on them. No F4 test is skipped.

## Fresh test output (run while writing this record, 2026-11-08)

The `design_day_short_window` warnings come from tiny_golden's one-month history (2025-03-01..2025-03-31) and are expected. Repeated captured-log blocks are trimmed.

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f4_*.py tests/golden/test_f4_*.py -q -rA
...
_______ test_I56_unknown_pallet_days_left_out_of_pallets_percentile_only _______
----------------------------- Captured stdout call -----------------------------
2026-11-08 21:53:51 [warning  ] receipts_pallets_unknown       days_left_out=8
...
__________ test_T4_1_design_day_and_inbound_equal_golden_spreadsheet ___________
---------------------------- Captured stdout setup -----------------------------
2026-11-08 21:53:51 [warning  ] catalog_todo_sources           count=72 total=72
2026-11-08 21:53:51 [warning  ] design_day_short_window        history_end=2025-03-31 history_start=2025-03-01 trailing_months=12
=========================== short test summary info ============================
PASSED tests/unit/test_f4_design.py::test_T4_2_design_percentile_moves_lines_monotonically
PASSED tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines[weekday_rate0]
PASSED tests/unit/test_f4_design.py::test_T4_3_hourly_lines_sum_to_design_lines[weekday_rate1]
PASSED tests/unit/test_f4_design.py::test_T4_4_derived_inbound_equals_outbound_units_at_zero_growth_constant_stock
PASSED tests/unit/test_f4_design.py::test_T4_5_assumptions_list_every_basis_field_exactly_once
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
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start2-6-True]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start3-None-True]
PASSED tests/unit/test_f4_register.py::test_I55_short_window_warning_on_window_used[start4-24-True]
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
PASSED tests/golden/test_f4_golden.py::test_T4_1_design_day_and_inbound_equal_golden_spreadsheet
109 passed in 0.90s
```
