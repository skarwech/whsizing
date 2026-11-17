2026-11-08: Superseded in part by docs/audit/G1c.md (I30 floor prep, I47 counts S0=30/S2=50).

# F5b audit: Catalog remediation (W1 open findings)

## Verdict: pass_with_issues

All five F5 acceptance tests (T5.1 to T5.5) pass: 103 passed, 0 failed and 0 skipped. T5.3 now runs against the G1 golden file, and the auditors showed by mutation that the tests catch the W1 bugs. F5 paths are clean under ruff, ruff format and pyright.
The verdict stays below `pass` because low findings are still open (inf values in `eligibility_shares`, I30 and I47 drift in G1 files, and the deferred W1 findings 6 to 9). The expert initialling of the family files also cannot be done here. Both round-2 auditors returned pass_with_issues.

Schema changes: none (`schema_changes: []`). The audit history given to this record is cut off during the round-2 proof audit. See "Audit rounds".

## Acceptance tests

| T-id | Test function | Status | What it proves |
|---|---|---|---|
| T5.1 | `tests/unit/test_f5_loader.py::test_T5_1_loader_rejects_malformed_fixture[*]` (13 cases) | pass | There are 13 fixtures under `tests/fixtures/catalog_bad/`. Each is a copy of a shipped file with exactly one defect plus a comment line (all auditors checked this with diff). They include the four spec cases (missing unit, min>typ, unknown key, bad semver) and two new ones for W1 finding 2: `missing_family_param` (cube `port_rate_lines_h` deleted) and `cross_family_key` (a cube key added to `manual_p2p`). Each case asserts `ConfigError` with exit code 2 and checks that the message names the file, the key and the reason. |
| T5.1 | `test_T5_1_every_fixture_has_a_case` | pass | The set of fixture folders equals the set of expected-message cases (13 = 13), so no fixture goes untested. |
| T5.1 | `test_T5_1_missing_and_unknown_catalog_files` | pass | An unknown `extra.yaml` and a missing `icpe_1510.yaml` both raise `ConfigError`, and the message names both files. |
| T5.1 | `test_T5_1_loader_rejects_non_finite_values[*]` (7 cases) | pass | `.nan`, `.inf`, `-.inf` and the quoted string `"nan"` are rejected in a constant, a Param bound, a tuple item (`max_item_mm[0]`) and a list item (icpe `max_m3`). Each raises `ConfigError` with exit code 2, naming the file and the key ("finite number"). Added in round 2. |
| T5.1 | `test_T5_1_non_utf8_file_is_a_config_error` | pass | A cp1252-encoded family file raises `ConfigError` with exit code 2 instead of a raw `UnicodeDecodeError`. Added in round 2. |
| T5.1 | `test_T5_1_max_robots_per_m2_shape_is_pinned_per_family[*]` (2 cases) | pass | `max_robots_per_m2` must be a number in `amr_gtp` (Appendix C.2) and a Param block in `cube_asrs`. The wrong shape is rejected in both directions. Added in round 2. |
| T5.2 | `tests/unit/test_f5_eligibility.py::test_T5_2_orientation_agnostic` | pass | With cube limits [600, 400, 300], 300x600x400 and 400x300x600 are eligible, and 610x100x100 and 350x350x350 are not. This is the spec case verbatim. The auditors also compared the mask with independent plain-Python references: 0 mismatches every time (see Proofs). |
| T5.3 | `tests/unit/test_f5_eligibility.py::test_T5_3_golden_eligibility_shares` | pass | This test was skipped in W1. It now runs against `tests/golden/golden_values.json`, which is produced by the G1 oracle (which never imports whsizing). It checks 12 keys: `eligibility.cube_asrs.*` with the default config and `S2.eligibility.*` with the S2 scenario config (`extra_max_weight_kg` 2.0, which gives 86 eligible SKUs instead of 91). It asserts that both key shapes were checked. Mutation: scaling any non-zero golden key by 1.01 or 1.02 makes it fail (10 of 10 in round 2). |
| T5.4 | `test_T5_4_missing_dims_ineligible_unless_flag` | pass | A missing dim or weight gives `[True, False, False]` by default and `[True, True, True]` with `assume_eligible_if_missing_dims`. `assumed_mask`, `assumed_share_lines` and the F_ELIG_ASSUMED value are all 0.4. |
| T5.4 | `test_T5_4_assume_flag_never_overrides_a_known_violation` | pass | This covers W1 finding 1. With the flag on, (null dim, 500 kg), (2000³ mm, null weight), (null dims, 40 kg) and (null, 500, 450 mm) stay ineligible, while (null, 550, 250 mm) and (fitting dims, null weight) are eligible. Restoring the W1 rule `when(missing).then(flag)` makes it fail. |
| T5.4 | `test_T5_4_missing_dims_ineligible_whatever_the_limits` | pass | A missing or NaN dim or weight is ineligible by default and assumed with the flag, with `use_catalog_limits` both True and False. Added in round 1. Replacing the presence check with `lit(True)`, or dropping `fill_nan`, makes it fail. |
| T5.5 | `tests/unit/test_f5_loader.py::test_T5_5_pessimistic_end_inference[*]` (34 cases) | pass | This covers W1 finding 5. Units are matched as tokens: `/h`, `/m2`, fill, availability and OEE give min; eur, `€`, kWh, `h` and `m2 per` give max. `pallets/shift`, `units/month`, `share`, `lines/day`, `hours`, `1/shift` with the name `refill`, and the `*_per_m2_*` density names give None. `europallets/h` gives min. Restoring the substring `eur` match, or dropping the `per_m2` exclusion, makes it fail. |
| T5.5 | `test_T5_5_loader_infers_absent_end_and_warns_on_contradiction` | pass | A missing `pessimistic_end` on an eur unit is inferred as max. An explicit value that contradicts the inference wins, and the loader adds one "contradicts" warning. |
| T5.5 | `test_T5_5_loader_rejects_absent_end_for_unit_with_no_rule` | pass | A labor standard with unit `pallets/shift` and no `pessimistic_end` raises `ConfigError` naming `receiving.standard`. |
| F5 Done-when | expert initialling of the family files (review #1) | not_applicable | This needs a warehouse-automation domain expert. All 72 of 72 params are still `source: TODO` with confidence L, and none has `validated_by` set. |

Supporting F5 tests that are not tied to a T-id (all pass):

- **Catalog:**
  - `test_shipped_catalog_loads_cleanly_and_counts_todos`: 72 params, 71 constants, todo_count 72 and 0 warnings.
  - `test_family_schemas_cover_exactly_the_section_models`: the union section models equal the union of `FAMILY_KEYS`.
  - `test_f6_f7_placeholders_are_in_the_catalog`.
  - `test_shipped_ranges_are_verbatim_from_the_spec`: the 66 spec ranges are unchanged.
  - `test_shipped_ids_follow_the_readme_rule`, `test_catalog_version_is_stable_and_snapshot_reproduces_it`, `test_icpe_regime_lookup` and `test_docs_assumptions_md_is_regenerated`.
- **Eligibility:**
  - `test_eligible_mask_missing_column_is_a_whsizing_error`.
  - `test_shares_reject_misaligned_or_invalid_series[*]` (5 cases): mismatched lengths, and NaN or negative values.
  - `test_shares_on_an_empty_sku_set[Boolean|Null]`.
  - `test_units_per_bin`: 0.04×0.7/0.007 gives 4, and 1/3.9999999995 gives 3.
  - `test_units_per_bin_rejects_non_positive_unit_cube[0.0|-0.01|nan]`.
  - `test_weight_limits_and_use_catalog_limits`, `test_hazmat_and_temperature`, `test_shares_by_lines_cube_and_count_and_elig_low` and `test_tiny_golden_cube_envelope_matches_f1_readme`.
- **ParamSet:**
  - `test_non_finite_override_is_a_config_error[nan|inf|-inf]`.
  - `test_basis_level_keys_are_accepted_and_exposed`: `stock_growth_rate` is in `BASIS_KEYS`, which fixes the W1 cross-feature hazard.
  - The pessimistic world is the min for a rate and the max for a cost. Every param resolves in all three worlds. Override rules hold, and so does the snapshot.

## Proofs (captured by the auditors during the audit)

The scripts named below are in `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/`, written `audit_F5b/` and `audit_F5/` below. All commands were run from `/Users/skarwech/saas_v1`.

1. **Eligibility matches an independent reading of F5 steps 1-3.** In the reference, a null or NaN value is unknown, any known violation gives False, and otherwise an unknown value takes the flag. This holds in every config, including `use_catalog_limits=False`. (Round-2 spec audit.)
   Command: `uv run python audit_F5b/r3/elig_ref3.py`
   ```
   configs 24, rows 4000 TOTAL MISMATCHES 0
   ```
   An earlier round-1 run checked the same against a literal step-3 reference: `mismatch_vs_spec_literal_step3 0 ... assumed mismatch 0 | all-null SKU, use_catalog_limits=False, flag off: [False] assumed: [True]`.

2. **The per-family schema is enforced (W1 finding 2).** Deleted, null, wrong-type and other-family keys are all rejected with `ConfigError` exit 2, and the message names the file and the key. (Round-0 and round-1 proof audits.)
   Command: `uv run python audit_F5b/loader_probe.py`
   ```
   cube port_rate explicit null: ConfigError exit=2 ... throughput.port_rate_lines_h: missing (required for cube_asrs)
   amr gets cube dig_factor: ... throughput.dig_factor: not a amr_gtp parameter
   cube floor_prep deleted: ... capex.floor_prep_per_m2_eur: missing (required for cube_asrs)
   cube range params deleted one at a time: 21/21 rejected
   ```

3. **T5.3 agrees with the independent oracle on all 12 keys and can catch a wrong value.** (Round-0/1 proof audits and round-2 spec audit.)
   Command: `uv run python audit_F5b/golden_s2.py; uv run python audit_F5b/r3/t53_mut.py`
   ```
   eligibility.cube_asrs.share_lines golden 0.8973950026581605 engine 0.8973950026581605 OK
   S2.eligibility.n_skus_eligible golden 86 engine 86 OK
   S2.eligibility.share_stock_cube golden 0.2547134682332789 engine 0.2547134682332789 OK (12/12 OK)
   unmutated: PASS | mutations caught 10/10
   ```
   The round-1 proof audit also checked that the golden JSON equals the `Eligibility` sheet of `golden_case.xlsx`: `S2.eligibility.share_lines json 0.7410951621477937 xlsx 0.7410951621477937`.

4. **The tests catch the regressions they target.** The mutants were built in memory, and the repository was left unchanged. (Round-1 proof audit.)
   Command: `uv run python audit_F5b/r2/mutate.py && uv run python audit_F5b/r2/mutate_m1.py`
   ```
   M2 W1 assume rule -> ..._never_overrides_a_known_violation: caught | M3 NaN dims not missing: caught
   M4 default assumed list -> test_shares_on_an_empty_sku_set: caught (SchemaError) | M5 no isfinite: caught
   M6 substring eur: caught | M7 no per_m2 exclusion: caught
   test_T5_4_missing_dims_ineligible_whatever_the_limits caught AssertionError (presence check -> lit(True))
   ```

5. **Non-finite catalog values are rejected everywhere, beyond the 7 test cases.** (Round-2 spec audit.)
   Command: `uv run python audit_F5b/r3/reprobe.py`
   ```
   cube_asrs.yaml [max_weight_kg: .nan]: ConfigError exit=2 ... constraints.max_weight_kg: Inp...
   [typ: 350, max: .inf] ... throughput.port_rate_lines_h.m...
   [empty_bin_reserve: 1.0e+400] / [1e400] ConfigError
   finance_defaults.yaml [operator: .nan] ConfigError | labor_standards.yaml [outbound_lag_hours: .inf] ConfigError
   engine_defaults.yaml [eta_flow: .nan] ConfigError | storage_classes.yaml [shelf_item_max_mm: [.inf] ConfigError
   ```

6. **A misaligned `assumed` series raises a catchable `WhsizingError`, not a polars Rust panic. A non-UTF-8 file and a scalar cube `max_robots_per_m2` raise `ConfigError`.** (Round-2 spec audit.)
   Command: `uv run python audit_F5b/r3/reprobe.py`
   ```
   assumed len2: RAISES whsizing.errors.WhsizingError [Exception] eligibility_shares: series lengths differ (mask, lines, stock, assumed: [3, 3, 3, 2])
   cp1252 file: RAISES whsizing.errors.ConfigError ... cube_asrs.yaml: not UTF-8 (byte 9); save the file as UTF-8
   cube robots scalar: RAISES whsizing.errors.ConfigError ... Value error, throughput.max_robo...
   ```
   Before the fix (round-1 spec audit, `audit_F5b/edge_r2.py`), the same input gave `pyo3_runtime PanicException ... MRO ['PanicException', 'BaseException', 'object']`.

7. **`units_per_bin` and shares match hand calculations, and the W1 1e-9 epsilon is gone.** (Round-2 spec audit.)
   Command: `uv run python audit_F5b/r3/reprobe.py`
   ```
   upb [48, 4, 0, 7, None] expect [48, 4, 0, 7, None] | eps 1/3.9999999995 -> [3] true floor 3
   upb cube 0.0 / -1.0 / nan / int 0: RAISES WhsizingError unit_cube_m3 must be > 0
   shares 0.4 0.3 0.6 expect 0.4 0.3 0.6 ['F_ELIG_LOW'] | exactly 0.5 -> flags []
   ```

8. **Catalog values are still verbatim from the spec.** The only differences are the two 0.2.0 version bumps and the four placeholders recorded in the CHANGELOG, plus the W1-era analog `finance.kwh_per_station_year`. (Round-0 and round-1 spec audits.)
   Command: `uv run python audit_F5/spec_vs_catalog.py`
   ```
   DIFF families/cube_asrs.yaml version spec= 0.1.0 catalog= 0.2.0
   EXTRA ... cube_asrs max_robots_per_m2 / m2_per_robot_parking / floor_prep_per_m2_eur
   DIFF families/amr_gtp.yaml version ... 0.2.0 | EXTRA ... charging_per_robot_eur | problems: 2
   ```

9. **End to end on synthetic data, eligibility is fast and deterministic, and the assumed share is consistent.** The data was 5,000 ecom_mid SKUs, 391 of them with a missing dim or weight. For every family, `assumed_share_lines` equals the line share with the flag on minus the share with it off. (Round-0 proof audit.)
   Command: `uv run python audit_F5b/e2e_synth.py`
   ```
   ('cube_asrs', False) (0.925034, 0.913845, 4556, 0.0, [], 0.019) | ('cube_asrs', True) (0.99705, 0.990035, 4947, 0.072016, ['F_ELIG_ASSUMED'], 0.019)
   deterministic (same seed twice): True | cube_asrs on>=off True assumed == on-off: True
   ```

## Audit rounds

### Build (before round 0)

The builder addressed W1 findings 1 to 5:

- **Finding 1:** eligibility now uses Kleene logic, `pl.all_horizontal(checks).fill_null(flag)`, so the flag only fills unknown values.
- **Finding 2:** a per-family `FAMILY_KEYS` validator rejects missing keys and keys from another family.
- **Finding 3:** T5.3 runs against the G1 golden file.
- **Finding 4:** four `[P]` placeholders were added, all source TODO with confidence L: `cube_asrs.floor_prep_per_m2_eur` 10/20/40, `cube_asrs.max_robots_per_m2` 0.05/0.05/0.05, `cube_asrs.m2_per_robot_parking` 1.5/2.0/2.5 and `amr_gtp.charging_per_robot_eur` 0/0/0. `amr_gtp` and `cube_asrs` were bumped to 0.2.0.
- **Finding 5:** `infer_pessimistic_end` now matches unit tokens.

The builder also added `BASIS_KEYS = {'stock_growth_rate'}` to ParamSet, which fixes the W1 cross-feature hazard. The build reported 0 schema changes.

### Round 0: tests 74 passed, 0 failed

Both the spec audit and the proof audit returned **pass_with_issues**.

| Audit | Severity | Finding | Resolution (round 1) |
|---|---|---|---|
| spec | medium | With `use_catalog_limits=False`, a SKU with missing dims or weight was eligible under the default flag and was never marked as assumed. This broke F5 step 3. | **Fixed.** A presence check that is null when a value is missing was added in every config. New test `test_T5_4_missing_dims_ineligible_whatever_the_limits`. |
| proof | medium | `eligibility_shares` raised a polars `SchemaError` on an empty SKU set when `assumed=None`. | **Fixed.** The mask is cast to Boolean, and the default assumed is `m & False`. New test `test_shares_on_an_empty_sku_set`. |
| proof | low | The same `use_catalog_limits=False` gap, seen from the runtime side. | **Fixed** by the same presence check. |
| proof | low | Inference: the `m2_per` name rule gave max for densities, the substring `eur` matched `europallets`, and `€` was not treated as a cost. | **Fixed.** Inference matches an eur token or `€`, and the `m2_per` rule skips `per_m2` names. Four T5.5 cases were added. |
| proof | low | A NaN ParamSet override escaped as a pydantic `ValidationError`, and an inf override was accepted. | **Fixed.** `math.isfinite` is checked on every override and raises `ConfigError`. |
| proof | low | T5.3 checked only the `eligibility.cube_asrs.*` keys, not `S2.eligibility.*`. | **Fixed.** T5.3 now checks all 12 keys. |
| proof | low | A NaN dim or weight was treated as a known violation, not as missing. | **Fixed** with `fill_nan(None)` before the checks. |
| proof | low | A missing `weight_kg` column raised a polars `ColumnNotFoundError`. | **Fixed.** A `WhsizingError` names the missing columns. |
| spec | low | `cube_asrs.floor_prep_per_m2_eur` conflicts with INTERPRETATIONS.md I30 (floor prep = 0) and with the golden. | **Deferred to G1.** These files are outside F5b's paths, and the catalog value follows F7 l.1091. |
| spec | low | The golden oracle `demand.py` still used the W1 assume rule. | **Deferred to G1.** G1 later fixed it (see the re-probe below). |
| spec/proof | low | A missing `pessimistic_end` is inferred, not rejected (W1 #7). | **Deferred.** This is a spec conflict between the F5 loader rules and §2.5.1. It is documented in `catalog/README.md`. |
| spec | low | The inference is stricter than §2.5.1: `hours`, `orders/hour`, `lines/h/station` and `m2/robot` give None and are rejected. | **Deferred.** This is conservative and never gives a wrong end. All 72 shipped params are explicit. |
| spec | low | The type of `max_robots_per_m2` was not pinned per family. | **Deferred** in round 1, **fixed** in round 2. |
| spec | low | Some F5 family-table parameters are absent (S0 cart capacity and walking share, S1 robots-per-station cap and pod replenishment). | **Deferred (YAGNI).** No F6 or F7 formula uses them, and Appendix C gives no values. |
| spec/proof | low | W1 findings 6 to 10 are still open. | **Deferred.** #6 matches the spec's own `grid_structure_per_m2_eur: max`. #7 is a spec conflict. #8 to #10 are documented deviations. (#10 was fixed in round 2.) |

Round-1 fix totals: 8 fixed and 8 deferred.

### Round 1: tests 85 passed, 0 failed

Both the spec audit and the proof audit returned **pass_with_issues**. The spec audit raised 1 medium and 7 low findings, and the proof audit raised 2 medium and 9 low. The lows that repeat the deferred round-0 items are not listed again.

| Audit | Severity | Finding | Resolution (round 2) |
|---|---|---|---|
| spec | medium | An `assumed` series of a mismatched length caused a polars `PanicException`, which subclasses `BaseException`, so `except Exception` cannot catch it. A length-1 series broadcast silently. | **Fixed.** The `_aligned()` helper checks all four lengths and raises `WhsizingError`. New test `test_shares_reject_misaligned_or_invalid_series`. |
| proof | medium | The loader accepted non-finite catalog values. With `max_weight_kg: .nan`, a 500 kg SKU became eligible. | **Fixed at the root.** A `CatalogModel` base class sets `allow_inf_nan=False`, and every catalog model inherits it. New test `test_T5_1_loader_rejects_non_finite_values` (7 cases). |
| proof | medium | A catalog file that is not UTF-8 raised a raw `UnicodeDecodeError`. | **Fixed.** It now raises `ConfigError("<file>: not UTF-8 (byte N) ...")`. New test `test_T5_1_non_utf8_file_is_a_config_error`. |
| proof | low | NaN or negative lines or stock were accepted, giving shares of 0.0 or 5.0. | **Fixed.** `_aligned()` raises `WhsizingError`. |
| proof | low | `units_per_bin` raised a polars `InvalidOperationError` when unit_cube was 0 or NaN. | **Fixed.** It raises `WhsizingError("unit_cube_m3 must be > 0")`. New test with 3 cases. |
| proof | low | W1 #10: the absolute +1e-9 gave 4 for 1/3.9999999995. | **Fixed.** The tolerance is now relative, `floor(ratio * (1 + 1e-12))`. `test_units_per_bin` asserts that the result is 3. |
| spec/proof | low | The type of `max_robots_per_m2` is not pinned per family. | **Fixed.** The family validator requires a number in amr and a Param in cube. New test with 2 cases. |
| proof | low | Cross-feature drift: I30 and `build_golden.py:66` say cube floor prep = 0, and I47 counts 68 TODOs and 18 cube params, against a catalog with 72 params. | **Deferred to G1.** These are G1 paths. |
| spec/proof | low | The oracle W1 assume rule, the inferred `pessimistic_end`, the strict inference, the missing family-table params, and W1 #8-9. | **Deferred**, with the same reasons as in round 0. |

The round-2 fix also reported a blocker outside F5's paths: `tests/golden/test_g1_remediation.py:74` E501, which broke the F0 ruff gate. Round-2 fix totals: 7 fixed and 6 deferred.

### Round 2: tests 103 passed, 0 failed

The spec audit returned **pass_with_issues** with 0 medium and 7 low findings:

| Severity | Finding | Status |
|---|---|---|
| low (new) | `_aligned()` rejects NaN and negative lines or stock but not ±inf. An inf value on an ineligible SKU gives share 0.0 and a spurious F_ELIG_LOW. On an eligible SKU it gives a NaN share with no flag. Normal input cannot reach this, because lines are counts and stock comes from validated data. | **Open.** It was found in the last round, and no fix round followed. Reproduced below. |
| low | I30 and I47 in INTERPRETATIONS.md, `build_golden.py:66` and `golden_values.json` `S2.capex.building_works` assume cube floor prep = 0 and 68 TODOs. | **Open, G1-owned.** |
| low | `eligibility_shares` takes the extra required kwargs `family` and `low_share` (W1 #8). | **Open, accepted deviation.** |
| low | A null hazmat counts as not hazmat (W1 #9). | **Open, spec silent.** |
| low | A missing `pessimistic_end` is inferred (W1 #7). The inference is stricter than the wording. `eur/m2` → max (W1 #6). | **Open, spec conflict / documented.** |
| low | The F5 family-table parameters are absent. | **Open, YAGNI, accepted.** |
| low | The F5 tasks include a "PR template", but `.github/` holds only `workflows/`. | **Open, outside F5b paths.** |

The spec auditor also confirmed that G1 had fixed the oracle assume rule: `audit_F5b/r3/oracle_probe.py` gives `(None, 200, 100) 500.0 (False, False) | (None, 550, 250) 1.0 (True, True)`.

The proof audit returned **pass_with_issues** with 103 passed and 0 failed, and rated T5.1 and T5.2 as pass. **The audit history given to this record is cut off during this audit, partway through its T5.2 evidence.** Its remaining T-id ratings, findings and proofs are not visible, so they are not reported here and none are reconstructed.

### W1 open findings scorecard

| W1 # | Finding | Outcome |
|---|---|---|
| 1 | The assume flag overrides a known violation. | **Fixed** (build). Kleene `fill_null`, plus the round-1 presence check for `use_catalog_limits=False`. Covered by two T5.4 tests. |
| 2 | The per-family schema was not enforced. | **Fixed** (build). `FAMILY_KEYS` validator and 2 new fixtures. The type was pinned in round 2. |
| 3 | T5.3 read a golden file that nothing produced. | **Fixed.** G1 produces `golden_values.json`. T5.3 runs and checks 12 keys. |
| 4 | Constants needed by F6 and F7 were missing. | **Fixed** (build). 4 `[P]` placeholders with source TODO and confidence L. Values await the expert. |
| 5 | The `h` substring inference. | **Fixed** (build). Token-based inference, refined in round 1. |
| 6 | `eur/m2` → max. | **Kept on purpose.** It matches the spec's own `cube_asrs.grid_structure_per_m2_eur: max`. |
| 7 | A missing `pessimistic_end` is inferred, not rejected. | **Deferred.** This is a spec conflict between the F5 loader rules and §2.5.1. It is documented. |
| 8 | Extra kwargs on `eligibility_shares`. | **Deferred.** `EligibilityResult.family` is required, and `low_share` comes from `engine.elig_low_line_share`. |
| 9 | A null hazmat counts as not hazmat. | **Deferred.** The spec is silent, and the rule is documented in the docstring. |
| 10 | The absolute 1e-9 epsilon in `units_per_bin`. | **Fixed** (round 2). The tolerance is now relative. |
| hazard | `stock_growth_rate` was rejected by ParamSet. | **Fixed** (build). `BASIS_KEYS` / `basis_value()`. |

### Re-probe while writing this record (2026-11-08)

These checks were captured by the record writer, not by the auditors.

```
$ uv run ruff check src/whsizing/catalog tests/unit/test_f5_*.py        -> All checks passed!
$ uv run ruff format --check (same paths)                              -> 9 files already formatted
$ uv run pyright (same paths)                                          -> 0 errors, 0 warnings, 0 informations
$ uv run pytest -q                                                     -> 368 passed, 7 skipped in 16.45s
  (skips: 6 G1 engine-parity stubs, 1 Docker; the round-2 F0 ruff-gate blocker no longer reproduces)
$ sed -n 315,317p tests/golden/demand.py                               -> the oracle now uses `ok and assume_flag` (resolved by G1)
$ eligibility_shares(mask [F,T], lines [inf,1], stock [1,1])           -> share_lines 0.0 ['F_ELIG_LOW']   (still open)
$ eligibility_shares(mask [T,T], lines [1,1], stock [inf,1])           -> share_stock_cube nan             (still open)
$ grep docs/INTERPRETATIONS.md                                         -> :230 "...floor-prep parameter, so floor prep = 0" ; :339 "catalog-wide TODO count (68)"   (unchanged)
$ grep tests/golden/build_golden.py:66                                 -> "area.total × 60, floor prep = 0 (I30)"   (unchanged)
$ ls .github                                                           -> workflows   (no PR template)
docs/assumptions.md                                                    -> Catalog version manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0 sha256:6282174cc512; 72 params, 72 TODO, 72 L
```

## Open issues

- **Low (new in round 2, F5b-owned):** `eligibility_shares` does not reject ±inf in `lines_by_sku` or `stock_by_sku`. It returns share 0.0 with a spurious F_ELIG_LOW, or a NaN share with no flag. Normal input cannot reach this. The fix is to use `~v.is_finite()` in place of `v.is_nan()` in `_aligned()`, `src/whsizing/catalog/eligibility.py`.
- **Low, G1 action needed (cross-feature):**
  - `docs/INTERPRETATIONS.md` I30 (l.230), `tests/golden/build_golden.py:66` and `golden_values.json` `S2.capex.building_works` (25251.25) take cube floor prep = 0.
  - Catalog 0.2.0 has `cube_asrs.floor_prep_per_m2_eur` 10/20/40 eur/m2, as F7 l.1091 asks. Once F7 uses the parameter, T7.1 will diverge until G1 updates I30 and the oracle.
  - I47 (l.339) still quotes 68 TODOs and 18 cube params. The catalog now has 72 params and 21 cube params.
- **Low, F7 decision:** `amr_gtp.charging_per_robot_eur` is 0/0/0, which treats charging as included in `per_robot_eur`. The expert must set the real value.
- **Low, deferred / accepted:**
  - W1 #6 to #9: `eur/m2` → max, the inferred `pessimistic_end`, the extra kwargs, and null hazmat.
  - The token inference is stricter than the §2.5.1 wording (`hours`, `lines/h/station`, `m2/robot`, `h/day` → None, so they are rejected).
  - The F5 family-table parameters are absent (S0 cart capacity and walking share, S1 robots-per-station cap and pod replenishment).
  - There is no PR template (`.github/` is outside F5b's paths).
- **Incomplete audit record:** the round-2 proof audit is cut off in the history this record was built from. Any findings it raised beyond T5.1 and T5.2 are unknown.
- **Pinned counts:** the tests pin 72 params, 71 constants and 66 verbatim spec ranges. After any catalog edit, `docs/assumptions.md` must be regenerated with `uv run python -m whsizing.catalog.assumptions`.

## Not applicable here and why

- **F5 "Done when" expert initialling of the family files (review #1):** this needs a warehouse-automation domain expert. All 72 params are `source: TODO` with confidence L, and none has `validated_by` set. The 4 new placeholders are the most urgent for expert review.
- **Real client data:** none is available here. Eligibility was exercised on tiny_golden, on tiny_golden with every 7th length set to null (builder: cube 76/91 eligible with the flag off/on, 15 assumed), and on synthetic ecom_mid with 5,000 SKUs (proof 9).
- **Docker and GitHub CI:** F5 does not depend on either. The one Docker skip in the whole suite is F0's `test_f0_report.py`. The 6 G1 engine-parity skips belong to F3, F4, F6 and F7, not F5.
- **`whsizing validate-catalog` CLI:** the command is still a placeholder in `src/whsizing/cli.py`, which belongs to F0 and F10. `load_catalog`, `Catalog.warnings` and `Catalog.todo_count` are ready for it.
- **Oracle cross-check for `use_catalog_limits=False`:** the G1 oracle raises `NotImplementedError` for that config. The step-3 fix there is checked only against the auditors' independent references (proof 1), not against the golden.

## Fresh test output (run while writing this record, 2026-11-08)

The repeated `catalog_todo_sources count=72 total=72` lines in the captured stdout have been removed, and parametrized cases are collapsed.

```
$ cd /Users/skarwech/saas_v1 && uv run pytest tests/unit/test_f5_*.py -q -rA
........................................................................ [ 69%]
...............................                                          [100%]
==================================== PASSES ====================================
________ test_T5_5_loader_infers_absent_end_and_warns_on_contradiction _________
[warning  ] catalog_warning  detail=".../b/catalog/finance_defaults.yaml: packaging_eur_per_order: pessimistic_end 'min' contradicts the §2.5.1 inference 'max' from unit 'eur'"
=========================== short test summary info ============================
PASSED tests/unit/test_f5_eligibility.py::test_T5_2_orientation_agnostic
PASSED tests/unit/test_f5_eligibility.py::test_T5_4_missing_dims_ineligible_unless_flag
PASSED tests/unit/test_f5_eligibility.py::test_T5_4_assume_flag_never_overrides_a_known_violation
PASSED tests/unit/test_f5_eligibility.py::test_T5_4_missing_dims_ineligible_whatever_the_limits
PASSED tests/unit/test_f5_eligibility.py::test_eligible_mask_missing_column_is_a_whsizing_error
PASSED tests/unit/test_f5_eligibility.py::test_weight_limits_and_use_catalog_limits
PASSED tests/unit/test_f5_eligibility.py::test_hazmat_and_temperature
PASSED tests/unit/test_f5_eligibility.py::test_shares_by_lines_cube_and_count_and_elig_low
PASSED tests/unit/test_f5_eligibility.py::test_shares_reject_misaligned_or_invalid_series[lengths differ x2 | stock NaN/negative x2 | lines NaN/negative]   (5)
PASSED tests/unit/test_f5_eligibility.py::test_shares_on_an_empty_sku_set[Boolean | Null]   (2)
PASSED tests/unit/test_f5_eligibility.py::test_units_per_bin
PASSED tests/unit/test_f5_eligibility.py::test_units_per_bin_rejects_non_positive_unit_cube[0.0 | -0.01 | nan]   (3)
PASSED tests/unit/test_f5_eligibility.py::test_tiny_golden_cube_envelope_matches_f1_readme
PASSED tests/unit/test_f5_eligibility.py::test_T5_3_golden_eligibility_shares
PASSED tests/unit/test_f5_loader.py::test_T5_1_every_fixture_has_a_case
PASSED tests/unit/test_f5_loader.py::test_T5_1_loader_rejects_malformed_fixture[bad_semver | cross_family_key | duplicate_family_id | duplicate_key | id_mismatch | min_gt_typ | missing_confidence | missing_family_param | missing_source | missing_unit | not_inferable | r_shorthand | unknown_key]   (13)
PASSED tests/unit/test_f5_loader.py::test_T5_1_missing_and_unknown_catalog_files
PASSED tests/unit/test_f5_loader.py::test_T5_1_loader_rejects_non_finite_values[max_weight_kg .nan | max_item_mm[0] .inf | port_rate max .inf | empty_bin_reserve .inf | empty_bin_reserve "nan" | staging_days -.inf | icpe max_m3 .inf]   (7)
PASSED tests/unit/test_f5_loader.py::test_T5_1_non_utf8_file_is_a_config_error
PASSED tests/unit/test_f5_loader.py::test_T5_1_max_robots_per_m2_shape_is_pinned_per_family[cube_asrs scalar | amr_gtp Param]   (2)
PASSED tests/unit/test_f5_loader.py::test_T5_5_pessimistic_end_inference[lines/h-port_rate_lines_h-min ... --bins_per_m2_per_level-None]   (34)
PASSED tests/unit/test_f5_loader.py::test_T5_5_loader_infers_absent_end_and_warns_on_contradiction
PASSED tests/unit/test_f5_loader.py::test_T5_5_loader_rejects_absent_end_for_unit_with_no_rule
PASSED tests/unit/test_f5_loader.py::test_shipped_catalog_loads_cleanly_and_counts_todos
PASSED tests/unit/test_f5_loader.py::test_family_schemas_cover_exactly_the_section_models
PASSED tests/unit/test_f5_loader.py::test_f6_f7_placeholders_are_in_the_catalog
PASSED tests/unit/test_f5_loader.py::test_shipped_ids_follow_the_readme_rule
PASSED tests/unit/test_f5_loader.py::test_shipped_ranges_are_verbatim_from_the_spec
PASSED tests/unit/test_f5_loader.py::test_catalog_version_is_stable_and_snapshot_reproduces_it
PASSED tests/unit/test_f5_loader.py::test_icpe_regime_lookup
PASSED tests/unit/test_f5_loader.py::test_docs_assumptions_md_is_regenerated
PASSED tests/unit/test_f5_paramset.py::test_rate_param_pessimistic_world_is_its_min
PASSED tests/unit/test_f5_paramset.py::test_cost_param_pessimistic_world_is_its_max
PASSED tests/unit/test_f5_paramset.py::test_every_param_resolves_in_three_worlds
PASSED tests/unit/test_f5_paramset.py::test_override_inside_range_replaces_typ_only
PASSED tests/unit/test_f5_paramset.py::test_scenario_overrides_win_over_basis
PASSED tests/unit/test_f5_paramset.py::test_out_of_range_override_widens_the_range[500.0 | 100.0]   (2)
PASSED tests/unit/test_f5_paramset.py::test_unknown_override_id_is_a_config_error
PASSED tests/unit/test_f5_paramset.py::test_non_finite_override_is_a_config_error[nan | inf | -inf]   (3)
PASSED tests/unit/test_f5_paramset.py::test_basis_level_keys_are_accepted_and_exposed
PASSED tests/unit/test_f5_paramset.py::test_snapshot_has_every_value_at_typ
103 passed in 1.25s
```
