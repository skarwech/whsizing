# G1f audit record: T7.1 finance parity wiring and register check against F7

Date of the record: 2026-11-09. Repo root `/Users/skarwech/saas_v1`. Feature G1f belongs to the T1.5 golden-case family (`tests/golden/test_g1_*.py`) and wires the F7 golden test (T7.1) into the engine-parity check.

## Verdict: pass_with_issues

All 69 tests of `tests/golden/test_g1_*.py` pass (0 failed, 0 skipped), and both auditors of round 0 returned pass_with_issues: the T7.1 skip placeholder is gone, the 111 S0/S2 capex/opex/finance golden keys are reproduced at 1e-9 by register formulas written independently of the oracle, and oracle, register and F7 agree on every point except one register contradiction.
The issues are low severity and none changes a golden number: the I47/I48 contradiction needs an expert ruling, six register gaps need entries from the register owner, three small weaknesses of the new checks are unaddressed, and one failing test outside G1f (F4/F6) is open. The history records no fix round.

## What G1f changed

Files written by the build step (reported in the build record):

- `tests/golden/test_g1_engine_parity.py`: the "F7 not built" skip placeholder for T7.1 is removed. T7.1 is now a fourth row of the T6.x ownership table (`test_f7_golden.py`, groups capex/opex/finance, 111 keys). The T6.3 disabled-test mutants are kept. The same five mutants are applied to the F7 file. A narrowed-`KEYS` mutant is added. The owner test now also asserts that no group has two owners.
- `tests/golden/test_g1_finance_register.py` (new): independent I29-I37, I41, I42 formulas against all 111 golden keys; oracle versus `whsizing.finance` metrics on eight flow sets; I48 degenerate cube on both sides.
- `tests/golden/test_g1_expert_rulings.py` (new): every `[EXPERT]` / `[VERIFY]` marker of the register is listed once under "Open expert rulings".
- `docs/INTERPRETATIONS.md`: golden case notes (stale "wait for T7.1" line replaced, G1f verification bullet, bullet on what the register leaves unsaid, the I47/I48 tension) and a new final section "## Open expert rulings".

Not touched (build record; mtimes from the audit proof 5): `oracle.py`, `build_golden.py`, `golden_values.json`, `golden_case.xlsx`, `pyproject.toml`, `uv.lock`. `schema_changes`: none. The repo has no git history (all files untracked), so "not touched" rests on the mtime evidence and the engineer's report.

## Acceptance tests

Test files: `tests/golden/test_g1_engine_parity.py` (16 items), `test_g1_finance_register.py` (10), `test_g1_expert_rulings.py` (2) written or changed by G1f, plus `test_g1_oracle.py` (13), `test_g1_register.py` (5), `test_g1_remediation.py` (12), `test_g1_sync.py` (11) unchanged. Total 69 items, 69 passed.

| T-id | test function | status | what it proves |
|---|---|---|---|
| T1.5 (T6.1, T6.2, T6.3) | `test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T6.1]`, `[T6.2]`, `[T6.3]` | pass | Each F6 golden file has its `test_T6_<n>_*` functions, no skip/xfail/importorskip/`pytestmark`, and a `KEYS` pattern that selects every S*.<group> golden key of its stage and no other group. |
| T1.5 (T7.1) | `test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T7.1]` | pass | The T7.1 skip placeholder is gone. `test_f7_golden.py` has three `test_T7_1_*` functions, nothing that can skip or xfail, and its `KEYS` selects exactly the 111 S0/S2 capex/opex/finance golden keys (8 capex + 40 opex each, 3 finance for S0, 12 for S2) and nothing else. |
| T1.5 | `test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[5 mutants]` | pass | Five disabling mutants on the T6.3 file (module `pytestmark`, `pytest.skip` in the fixture, xfail, skipif, imported skip) each make the check count 0 tests; the unmodified file counts 3. |
| T1.5 | `test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[5 mutants]` | pass | The same five mutants on `test_f7_golden.py` each count 0 tests; unmodified counts 3. |
| T1.5 | `test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_narrowed_f7_keys_pattern` | pass | Dropping `finance` from the F7 `KEYS` leaves the S*.finance.* golden keys unselected, so the check would catch it. |
| T1.5 | `test_g1_engine_parity.py::test_T1_5_engine_parity_every_scenario_key_has_an_owner` | pass | Every S*.<group> golden group is owned by exactly one F6/F7 golden test or is a flag string (I46). A new group fails until someone claims it. |
| T1.5 | `test_g1_finance_register.py::test_T1_5_register_finance_formulas_reproduce_every_golden_key` | pass | I29-I37, I41, I42 formulas written from the register and the catalog YAML alone (no oracle constants, no `whsizing`) reproduce all 111 golden keys at 1e-9. The I33 roles equal `catalog/labor_standards.yaml`. |
| T1.5 | `test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[8 flow sets]` | pass | On eight flow sets (all negative = golden S2, all positive, capex delta <= 0, never repaid, one change, payback inside a year, two changes, zeros ignored), I37 (IRR only with exactly one sign change), the I42 NPV and payback agree between `oracle.py` and `whsizing.finance`, and the IRR is a root of the NPV. |
| T1.5 | `test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7` | pass | I48 on a degenerate copy (S2 with `extra_max_weight_kg` about 0): oracle and F7 agree on all 60 S2 keys; overflow 0, controls 50 000, S2 costs what S0 costs, NPV 0. |
| T1.5 | `test_g1_expert_rulings.py::test_T1_5_open_expert_rulings_list_every_marker_once` | pass | Every `[EXPERT]` / `[VERIFY]` entry of the register (I46, I48, I53, I54, I64, I65, I67, I69) is listed exactly once under "Open expert rulings"; I33 is allowed without a marker; nothing else is listed. |
| T1.5 | `test_g1_expert_rulings.py::test_T1_5_open_expert_rulings_check_rejects_a_missing_a_duplicate_and_a_stale_entry` | pass | The checker itself: a dropped I69, a repeated I46 and a stale I1 are each detected. |
| T7.1 (not owned by G1f) | `tests/golden/test_f7_golden.py::test_T7_1_golden_finance_equals_the_spreadsheet`, `test_T7_1_financial_result_carries_the_golden_values`, `test_T7_1_golden_figures_discriminate_the_documented_rules` | pass | Owned by F7. Run at record time together with the G1f files (31 passed) to confirm the wiring is real: the parity check ties these three tests to the 111 keys. |
| T1.5 (unchanged files) | `test_g1_oracle.py` (13), `test_g1_register.py` (5), `test_g1_remediation.py` (12), `test_g1_sync.py` (11) | pass | Not changed by G1f; they still pass. By their names and the golden case notes: the oracle build is deterministic and equals the committed workbook and JSON, and earlier register rules (G1b-G1e) are pinned oracle = register = engine on modified copies of the data. Not re-audited for this record. |

## Proofs

The excerpts below were captured by the auditors during the audit (round 0, spec and proof audits), not re-run for this record. Scripts live in the audit scratchpad `/private/tmp/claude-501/-Users-skarwech-saas-v1/3254fba1-1e74-44c5-a28d-ac3e429f74d3/scratchpad/audit_G1f/`. Where the audit history clipped a claim or an output, the clipping is kept (marked `[clipped]`). Proof 7 was captured at record time.

1. **Golden finance numbers follow the Appendix B formulas.**
   Claim: recomputed independently from the golden opex and capex items, contingency = 0.10 x subtotal, capex total, TCO, cost_per_line = TCO x r/(1-(1+r)^-5)/annual_lines, the I42 delta cash flows and the NPV (also equal to `numpy_financial.npv`) match the golden values. [clipped]
   Command: `cd /Users/skarwech/saas_v1 && uv run python .../audit_G1f/hand.py`
   Output excerpt: `S0 tco 502085.55640707567 502085.55640707567 cpl 6.632246037385842 6.632246037385842 | S2 tco 893712.0036257082 893712.0036257082 cpl 11.80539415837144 11.80539415837144 | npv -391626.4472186325 -391626.4472186325 -391626.44721863256 | irr (all neg): None payback None | S0 energy y1 4165.0 4165.0 forklifts 1 | renewals all 0.0`

2. **The register-formula test is a real check (mutation by perturbation).**
   Claim: perturbing a golden value by 1e-7 to 1e-3 relative on seven keys is detected on every non-trivial key, so the 1e-9 claim is real. The only "NOT DETECTED" line is a x1.0 no-op on a zero value, which is not a real mutation.
   Command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python .../audit_G1f/mut.py`
   Output excerpt: `S2.opex.y3.rent 1.0000001 detected | S2.capex.contingency 1.001 detected | S0.opex.y4.energy 1.01 detected | S2.opex.y2.labor 1.0000001 detected | S2.finance.cost_per_line 1.00001 detected | S0.capex.building_works 0.999 detected | S2.finance.npv 1.0000002 detected | add marker I29 -> ({29}, set(), []) | dup I48 -> (set(), set(), [48])`

3. **The I47 / I48 tension is real, and the degenerate case agrees across oracle and engine.**
   Claim: on S2 with `extra_max_weight_kg` about 0, oracle and engine both flag `F_LOW_CONFIDENCE:50`, while F7 reads `manual_p2p.wms_adaptation_fixed_eur` and `manual_p2p.software_eur_year` (excluded from the cube count) and no cube capex Param. [clipped]
   Command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python .../audit_G1f/i48.py.2`
   Output excerpt: `oracle S2.flags: F_HEIGHT_LIMIT:pallet_rack,F_ELIG_LOW,F_SCALE_LOW,F_SHORT_HISTORY,F_RATIO_DRIFT:weight_kg,F_RATIO_DRIFT:pallets_out,F_LOW_CONFIDENCE:50 | engine S2 flags: [..., 'F_LOW_CONFIDENCE:50'] | F7 params read by S2 degenerate: [... 'manual_p2p.software_eur_year', ..., 'manual_p2p.wms_adaptation_fixed_eur'] (16 manual/finance params, no cube params) | capex {'storage': 8306.82, 'equipment': 38000.0, 'controls': 50000.0, 'building_works': 23918.5, 'overflow': 0.0, ...} npv 0.0 payback 0.0` [clipped]

4. **T7.1 is a real fourth row of the ownership check, not a skip.**
   Claim: disabling mutants on `test_f7_golden.py` make the check count 0 tests, the unmodified file counts 3, and dropping `finance` from `KEYS` leaves the finance keys unselected. The whole file set passes. [clipped]
   Command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/golden/test_f7_golden.py tests/golden/test_g1_engine_parity.py tests/golden/test_g1_expert_rulings.py tests/golden/test_g1_finance_register.py -q; uv run python .../audit_G1f/parity_mut.py` [clipped]
   Output excerpt: `31 passed in 1.51s | baseline tests 3 | early return in comparison test -> tests counted: 3 | TOL widened to 50% -> tests counted: 3 | test renamed -> tests counted: 2 | importorskip call -> tests counted: 0`
   Note: the same excerpt shows the limit of the check (see finding 2 of round 0): an early `return` or a widened `TOL` in the F7 file is not detected.

5. **G1f edits are confined to the owned files.**
   Claim: `oracle.py`, `build_golden.py`, `golden_values.json` and `golden_case.xlsx` carry mtimes of 07:42-07:44, before the G1f work, and `test_T1_5_build_is_deterministic_and_committed_files_are_current` passes. In `tests/golden` only the three `test_g1_*` files are newer than `test_f7_golden.py`. [clipped]
   Command: `cd /Users/skarwech/saas_v1 && ls -la tests/golden/ && find . -type f -newer tests/golden/test_f7_golden.py -not -path './.venv/*' -not -path '*/__pycache__/*' | grep tests/golden`
   Output excerpt: `golden_values.json Nov 9 07:42, oracle.py 07:42, golden_case.xlsx 07:42, build_golden.py 07:44 | newer: ./tests/golden/test_g1_finance_register.py, ./tests/golden/test_g1_engine_parity.py, ./tests/golden/test_g1_expert_rulings.py`

6. **The expert-rulings checker catches an added marker, a duplicate and a stale entry; the markers found are the expected eight.**
   Claim (spec audit): adding a marker to I29 reports it missing, a duplicate I48 is reported twice, a stale entry is reported; the markers found are I46, I48, I53, I54, I64, I65, I67, I69, and I33 is the only unmarked entry that mentions a pending expert decision. Edge-case probes of the checker (`audit_G1f/edge.py`) show it fails loudly but with raw exceptions (finding 3).
   Output excerpt (edge.py): `no KEYS -> StopIteration`, `KEYS non-literal -> ValueError malformed node`, `section removed -> IndexError list index out of range`, `heading renamed -> IndexErro...` [clipped]

7. **Full-suite state at audit time and quality gates at record time.**
   Spec audit full suite: `1 failed, 960 passed, 3 skipped` (`AssertionError: assert {'info', 'warning'} == {'warning'}` at `tests/unit/test_f6_size.py:310`, not attributed to G1f). Re-checked for this record:
   `uv run pytest tests/unit/test_f6_size.py -q` gives `1 failed, 27 passed, 1 skipped` (`FAILED ...::test_design_day_flags_carry_the_f6_table_severity_info`).
   `uv run ruff check tests/golden/test_g1_*.py` gives `All checks passed!`; `uv run ruff format --check tests/golden/test_g1_*.py` gives `7 files already formatted`; `uv run pyright` on the three G1f-written test files gives `0 errors, 0 warnings, 0 informations`.

## Audit rounds

The history holds one round (round 0): the build step, a spec audit and a proof audit. No fix round and no round 1 are recorded. The proof audit returned pass_with_issues with no findings, 69 passed, 0 failed. "Status at record time" below is what I could verify by reading the current files; I changed no code (this step may only write this file).

### Round 0, spec audit: pass_with_issues, 69 passed / 0 failed, 5 findings (all low)

| # | severity | finding | status at record time |
|---|---|---|---|
| 1 | low | `docs/INTERPRETATIONS.md:717`: the new H2 "## Open expert rulings" sits outside "## Golden case notes", which is all G1f may edit; `test_g1_expert_rulings.py` depends on that exact heading. The closing paragraph (lines 742-744) is also outside the notes. Additive, changes no number. The repo has no git history, so the auditor could not diff-check that register entries I1-I72 were untouched. | Open, not changed. Accepted by the build step as additive. The lead should confirm the placement. |
| 2 | low | `test_g1_engine_parity.py:51`: the T7.1 check guarantees only "exists, not skipped, KEYS covers the keys". It does not pin the 0.5 % tolerance and does not detect a neutralised test body: an early `return` and `TOL = 0.5` in `test_f7_golden.py` both still count 3 tests. | Open, not fixed. Confirmed at record time: the parity file has no reference to `TOL`; `test_f7_golden.py` has `TOL = 0.005` and nothing guards it. The same blind spot existed for the T6.x rows. |
| 3 | low | `test_g1_expert_rulings.py:30`: the checker helpers raise raw exceptions on a malformed target (`StopIteration`, `ValueError`, `IndexError`) instead of a clear assertion; `re.compile(..., flags=)` drops its flags silently. Failures stay loud, so correctness is unaffected. | Open, not fixed. |
| 4 | low | `docs/INTERPRETATIONS.md:696`: F7 behaviours with no register entry (amr_gtp capex and the `A_storage` choice, the client_current baseline rules, the `compute_finance` signature extras, whole-year equipment lives) are still not in the register body; the I32 forklift energy term is not literally in the spec text. Correctly escalated in the golden notes. | Deferred to the lead / register owner (outside G1f's edit scope). Still true at record time: the closing paragraph of the notes says "Not in the register yet". |
| 5 | low | Outside G1f: `tests/unit/test_f6_size.py::test_design_day_flags_carry_the_f6_table_severity_info` fails; the test asserts F4 flag severities are `{'warning'}`, F4 now emits `info` (I70). | Deferred to F4/F6 (same as F7 audit open issue 3). Still failing at record time (1 failed). |

### Round 0, build blockers (engineer's record)

| # | severity | item | resolution |
|---|---|---|---|
| B1 | low | Register contradiction I47 vs I48: the cube count includes 17 manual Params of the overflow zone but I48 says a degenerate cube scenario keeps the cube's F_LOW_CONFIDENCE count (50), while F7 reads two manual Params the count excludes and none of the cube capex Params. Oracle = engine = I48 literal. | Deferred: needs the I48 `[EXPERT]` ruling. Recorded in the golden case notes and in "Open expert rulings". |
| B2 | low | Six register gaps (client-current baseline missing from I42; no amr_gtp capex entry and no golden scenario; `compute_finance` signature extras; I35 states only the `footprint` rent mode; I35 renewal on the family equipment item only plus F7 `ConfigError` for a life <= 0 or fractional; I32 forklift energy term). None changes a golden number. | Deferred to the lead / register owner; written into the golden case notes. |
| B3 | info | `docs/audit/F7.md` was absent when the build began and appeared at 10:21; it was read in full afterwards. | Resolved. F7 open issue 2 (stale T7.1 skip placeholder and stale "wait for T7.1" sentence) is fixed by this feature. |
| B4 | info | The F7 audit's `test_f6_size` failure (F4/F6) was not re-run by the build step. | Same as finding 5. |

### Round 0, proof audit: pass_with_issues, 69 passed / 0 failed, no findings recorded.

## Open issues

1. **I47 / I48 contradiction (low, needs an expert ruling).** The F_LOW_CONFIDENCE count of a degenerate cube scenario is 50 in oracle, F6 and I48 literal, but by the I47 rule ("Param blocks the formulas read") it would not include the two manual Params F7 reads and would include cube capex Params F7 does not read. No golden number changes.
2. **Six register gaps (low, deferred to the register owner).** Client-current baseline in I42, amr_gtp capex, `compute_finance` signature extras, I35 `full_building` and `none` rent modes, I35 renewal scope and `ConfigError`, I32 forklift energy term. The amr_gtp capex and client-current baseline rules are not confirmed by a domain expert (F7 audit open issue 9); no golden scenario covers amr_gtp.
3. **Parity check does not pin the 0.5 % tolerance or detect a neutralised test body (low, not fixed).** An early `return` in `test_T7_1_golden_finance_equals_the_spreadsheet` or `TOL = 0.5` in `test_f7_golden.py` passes the parity check.
4. **Checker helpers raise raw exceptions on a malformed target (low, not fixed).** Failures are loud but the messages do not say what is wrong.
5. **"## Open expert rulings" placement (low).** It is a new H2 outside the golden case notes that G1f owns, and the test depends on its heading. The lead should confirm or move it. The register body I1-I72 could not be diff-checked (no git history).
6. **Stale sentence in the golden case notes (low, found for this record, not fixed here).** `docs/INTERPRETATIONS.md:680` still says `test_T1_5_amr_robot_parking_reads_the_cube_param` is "a strict xfail while F6 reads `amr_gtp.m2_per_robot_parking`". The test now has no xfail marker and passes (F6 `src/whsizing/engine/area.py` reads `cube_asrs.m2_per_robot_parking`), so the sentence and the "open" medium finding in `docs/audit/G1e.md` are out of date. The golden case notes are G1f's to edit; this step could only write this file.
7. **Outside G1f: `tests/unit/test_f6_size.py::test_design_day_flags_carry_the_f6_table_severity_info` fails** (stale assertion on F4 flag severity, I70). Owner: F4/F6.
8. **Coverage limits that the golden case cannot lift (from the F7 audit, unchanged):** golden values cover the typ world and S0/S2 only; lo/hi worlds and amr_gtp are covered by independent recomputation, not by a golden. `S*.flags` and `S*.low_confidence_params` are compared by no T6/T7 test (I46).

## Not applicable here and why

- **Real client data:** none is available and none is needed. The golden case is the synthetic `tiny_golden` dataset with the golden basis; client data never leaves the machine.
- **Domain expert review:** not possible in this environment. The rulings that need an expert are listed under "Open expert rulings" in the interpretations (I33, I46, I48, I53, I54, I64, I65, I67, I69) plus the two F7-only items without an I-number (amr_gtp capex, client baseline). The I47/I48 contradiction is one of them.
- **Docker and GitHub CI:** nothing in G1f needs them; nothing was run in a container or in CI.
- **Skipped tests:** none. G1f has no `pytest.mark.skip`; the earlier T7.1 skip placeholder was removed.
- **Git state:** no commits were made; the tree has no history, so a diff against an earlier state was not possible.
- **Dependencies:** no new package; `pyproject.toml` and `uv.lock` are G1f-untouched (no git history to prove it; see the mtime evidence in proof 5 for the golden files).

## Fresh test output

Run at record time, 2026-11-09 about 10:34, from `/Users/skarwech/saas_v1`:

```
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/golden/test_g1_*.py -q -rA
```

Trimmed. The four engine-backed tests (`test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7`, `test_T1_5_default_units_per_pallet_flag_matches_the_engine`, `test_T1_5_whole_pitch_clear_height_engine_equals_the_oracle`, `test_T1_5_amr_robot_parking_reads_the_cube_param`) each captured two structlog warnings on stdout (`catalog_todo_sources count=72 total=72` and `design_day_short_window history_end=2025-03-31 history_start=2025-03-01 trailing_months=12`); those lines are omitted below.

```
.....................................................................    [100%]
==================================== PASSES ====================================
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T6.1]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T6.2]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T6.3]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_golden_test_covers_its_keys[T7.1]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[imported skip]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[module pytestmark]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[pytest.skip in a fixture]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[skipif on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_golden_test[xfail on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[imported skip]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[module pytestmark]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[pytest.skip in a fixture]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[skipif on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_disabled_f7_golden_test[xfail on the comparison test]
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_rejects_a_narrowed_f7_keys_pattern
PASSED tests/golden/test_g1_engine_parity.py::test_T1_5_engine_parity_every_scenario_key_has_an_owner
PASSED tests/golden/test_g1_expert_rulings.py::test_T1_5_open_expert_rulings_list_every_marker_once
PASSED tests/golden/test_g1_expert_rulings.py::test_T1_5_open_expert_rulings_check_rejects_a_missing_a_duplicate_and_a_stale_entry
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_register_finance_formulas_reproduce_every_golden_key
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[all negative (golden S2)]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[all positive]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[capex delta <= 0]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[never repaid]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[one change]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[payback inside a year]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[two changes]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows[zeros ignored]
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7
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
PASSED tests/golden/test_g1_register.py::test_T1_5_amr_robot_parking_reads_the_cube_param
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
PASSED tests/golden/test_g1_sync.py::test_T1_5_avg_stock_counts_a_sku_absent_from_a_snapshot_as_zero
PASSED tests/golden/test_g1_sync.py::test_T1_5_inventory_only_skus_are_orphans_in_stock_and_dead_stock
PASSED tests/golden/test_g1_sync.py::test_T1_5_dead_stock_reads_the_last_snapshot_and_a_180_day_window
PASSED tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_are_left_out_of_intraday_shares
PASSED tests/golden/test_g1_sync.py::test_T1_5_lines_without_time_above_20_percent_use_the_default_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_exactly_20_percent_lines_without_time_keep_the_measured_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_design_weekday_without_timed_lines_takes_the_default_profile
PASSED tests/golden/test_g1_sync.py::test_T1_5_trend_cagr_from_monthly_mean_daily_lines
PASSED tests/golden/test_g1_sync.py::test_T1_5_cube_building_works_add_floor_prep_on_the_grid
PASSED tests/golden/test_g1_sync.py::test_T1_5_oracle_param_ids_and_values_match_the_catalog
PASSED tests/golden/test_g1_sync.py::test_T1_5_share_stock_cube_is_zero_without_stock
69 passed in 2.69s
```

Wiring cross-check run at record time (`uv run pytest tests/golden/test_f7_golden.py tests/golden/test_g1_engine_parity.py tests/golden/test_g1_expert_rulings.py tests/golden/test_g1_finance_register.py -q`): `31 passed in 1.56s`.
