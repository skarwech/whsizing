# G1g audit record: oracle ABC tie-break (I6 amendment) and register consistency I75-I77

Date of the record: 2026-11-09. Repo root `/Users/skarwech/saas_v1`. Feature G1g belongs to the T1.5 golden-case family (`tests/golden/test_g1_*.py`). Its own test files are `tests/golden/test_g1_abc_tiebreak.py` and `tests/golden/test_g1_finance_register.py` (split of the I48 degenerate-cube test); the rest of `test_g1_*.py` belongs to G1a to G1f and is only re-run here.

## Final verdict: pass_with_issues

- The oracle follows I6 as amended and is salt-independent (0 of 741 golden keys move under 4 other salts), and every G1g test passes except two strict xfails; both audits of both rounds returned pass_with_issues, and the fresh run is 75 passed, 2 xfailed, 0 failed, 0 skipped.
- The two xfails are a real, open defect of the engine (F3 `src/whsizing/profile/abc.py` still ties by sku only; it is outside G1g's paths and was deferred, not fixed), and one low-severity wording error in the golden note is still in `docs/INTERPRETATIONS.md`. Engine and golden agree within 0.314 % (T1.5 tolerance 0.5 %) but not at 1e-9.

## What G1g changed

- `tests/golden/demand.py`: `ABC_ORDER` / `ABC_DESC` constants used by `sku_table` (lines, units, avg_stock, unit cube, weight with null = 0, all descending, then sku ascending); `NotImplementedError("derived inbound only")` guard in `inbound()` for `inbound_mode != derived`. The oracle still never imports `whsizing`.
- `tests/golden/workbook.py`: the abc column comment carries the sort chain.
- `tests/golden/golden_values.json` and `tests/golden/golden_case.xlsx` rebuilt (`uv run python -m tests.golden.build_golden`): 55 of 741 keys change, none added or removed. Cause: 12 SKUs tie at 5 lines across the B/C boundary (the first 5 are B). Old order by sku put 73da1141072c60b3, 1853b525133fdf6b, 08d40036a7a6742f (and 2a7d19452a07904d, 7b8801b209320951) in B; the new order by units puts 87f4f13fa5f648b9, d924c41697680c3b, a11dc9f9aae82c3b (8 units each) in B. No `abc.*`, storage, area or capex key moves; the largest relative change is 0.314 % (S0 replenishment hours and heads).
- `docs/INTERPRETATIONS.md`: three bullets in "Golden case notes" (I6 key list, engine blocker, I75-I77 verdicts). The I6 register text itself was already amended and was not touched.
- Schema changes: none. No `pyproject.toml` / `uv.lock` change. No commits.

## Tests

All G1g tests are part of T1.5 (this feature has no other acceptance id).

| T-id | test function | status | what it proves |
|---|---|---|---|
| T1.5 | `test_g1_abc_tiebreak.py::test_T1_5_abc_order_ties_by_lines_units_stock_cube_weight_then_sku` | pass | One pair per rung (lines, units, avg_stock, unit cube, weight) on a synthetic RANKED copy of the tiny_golden master, plus the fully identical pair (sku ascending) and null weight = 0; the result does not depend on input row order. Mutation scratch checks: all 18 (round 0) and 17 (round 1) mutants of the order (drop, swap, flip a rung, weight without fill_null) were detected. |
| T1.5 | `test_T1_5_abc_order_is_not_the_old_sku_ascending_tie_break` | pass | The same data under the old (lines, sku) order ranks differently, so the rung test discriminates; the global order is restored in a `finally`. |
| T1.5 | `test_T1_5_golden_values_do_not_depend_on_the_sku_salt` | pass | Every sku id relabelled with a salted hash: all 741 golden values equal (1e-9 for floats, exact otherwise). |
| T1.5 | `test_T1_5_old_order_made_the_golden_values_depend_on_the_sku_salt` | pass | Control: under the old order the same relabel moves values (S0.labor.replenishment.workload, S0.storage.pallet_rack.pick_faces 16 -> 17), so the salt-independence test is not vacuous. |
| T1.5 | `test_T1_5_golden_class_boundary_inside_a_line_tie_follows_the_chain` | pass | The single 12-SKU tie at 5 lines across B/C is split by (units, avg_stock, cube, weight), never by sku: every better class outranks every worse class on the chain. |
| T1.5 | `test_T1_5_receipts_mode_is_not_silently_derived_in_the_oracle` | pass | I77: the golden basis is `derived` and no golden `.flags` value contains `F_INBOUND_SPARSE` / `F_RECEIPTS_NO_PALLETS`; the oracle raises `NotImplementedError` ("derived inbound only") for a receipts-mode basis instead of computing derived silently. |
| T1.5 | `test_g1_finance_register.py::test_T1_5_degenerate_cube_is_costed_as_the_manual_baseline_in_the_oracle_and_f7` | pass | Added in fix round 1. I48 degenerate cube: all 60 S2 keys oracle vs F7 within the 0.5 % T1.5 tolerance (0 mismatches), controls == 50 000 in oracle and F7, overflow == 0 in both, S2 capex == S0 capex, S2 npv == 0, F7 npv_vs_baseline == 0. |
| T1.5 | `test_g1_abc_tiebreak.py::test_T1_5_engine_abc_follows_the_same_tie_break_chain` | xfail (strict, `raises=AssertionError`), open engine defect | Intended property: `whsizing.profile.abc.classify` ranks the RANKED rows like the oracle. Fails today (index 1: `'a0' != 'z8'`) because F3 still sorts `[by, "sku"]`. Flips to XPASS (strict failure, remove the marker) when F3 follows I6. |
| T1.5 | `test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7` | xfail (strict, `raises=AssertionError`), open engine defect | Intended property: oracle vs F7 agree at 1e-9 on the I48 case. Fails today on 12 S2 keys (first `S2.opex.y1.labor`; S0 labor.y1 33985.46 oracle vs 33983.40 engine, 0.006 %), same root cause as above. |

Also in the fresh run (not G1g's, passing): `test_g1_oracle.py`, `test_g1_register.py`, `test_g1_remediation.py`, `test_g1_sync.py`, `test_g1_engine_parity.py`, `test_g1_expert_rulings.py` and the rest of `test_g1_finance_register.py`. That is 68 items, all passed; with the 9 G1g items (7 passed, 2 xfailed) the run has 77 items: 75 passed, 2 xfailed.

## Proofs

All captured by the auditors during the audit, in scratch scripts outside the repo (`audit_G1g/p*.py` in round 0, `audit_G1g/q*.py` in round 1). Excerpts are as recorded in the audit history (some were clipped there).

1. **The oracle's ABC ranking equals an independent plain-Python I6 implementation** (round 0 and round 1).
   - Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python audit_G1g/p1.py` (round 1: `q2.py`, re-ranking from the raw parquet).
   - Output: `same order as independent python sort: True; classes equal: True; Counter({'B': 37, 'C': 35, 'A': 28}); abc.lines.A.line_share 0.8054226`. Round 1: `n skus mine 100 oracle 100 / class diffs vs oracle: []`; tie group `lines= 5 12 [('2a7d19452a07904d','B',9), ('87f4f13fa5f648b9','B',8), ('d924c41697680c3b','B',8), ('a11dc9f9aae82c3b','B',8), ('7b8801b209320951','B',8), ('efa1dafb8b02f27b','C',7) ...]`.
2. **The change report is accurate: 55 of 741 keys change, max 0.314 %, nothing in abc / storage / area / capex moves.**
   - Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python audit_G1g/p2.py` (builds the golden with the old order and diffs it); round 1 `q3.py`.
   - Output: `keys 741 changed old->new: 55; max rel change 0.31410%; no abc/storage/area/capex key moved`; round 1: `keys changed by amendment (old->new): 55 / max rel change 0.00313 / added/removed set() / abc/storage/area/capex keys changed by the amendment: []`.
3. **Golden values are salt-independent under the amended order; the old order is not.**
   - Command: `PYTHONPATH=. uv run python audit_G1g/p3.py` and `q3.py`.
   - Output: salts s1, s2, s3: `differing golden keys = 0`; round 1 `s2 new-order keys moved vs golden: 0 / s3: 0 / x1: 0 / x2: 0` and `old order moved under relabel: 135 (16, 17)` (55 to 137 across salts).
4. **The rung test kills the mutants of the order.**
   - Command: `PYTHONPATH=/Users/skarwech/saas_v1 uv run python audit_G1g/p2.py` (round 0), `q5.py` (round 1).
   - Output: round 0 `mutants detected 18 of 18 missed: []`; round 1 `all 17 mutants (drop/swap/flip a rung, weight without fill_null) report 'survives mutation: False'; baseline True, restored True`. The two mutant sets differ in size (18 and 17); the audit history does not say how.
5. **The engine defect is real, and the oracle is not the one at fault.**
   - Command: `PYTHONPATH=. uv run python audit_G1g/q4.py`.
   - Output: `oracle vs engine class differences: 6 [('87f4f13fa5f648b9','B','C'), ('d924c41697680c3b','B','C'), ('a11dc9f9aae82c3b','B','C'), ('73da1141072c60b3','C','B'), ('1853b525133fdf6b','C','B'), ('08d40036a7a6742f','C','B')]`. With other salts the engine differs from the oracle by 8 classes (round 0 `p3.py`: `engine-vs-oracle class diffs = 8` for s2 and s3), so the engine ranking still depends on the salt.
   - With the I6 chain monkeypatched into `classify` and `build.classify` (repo untouched), both xfail test bodies pass and the F3, F6, F7 golden tests stay green: `12 passed, 1 warning in 0.73s` (round 0 `p4.py`), `q6.py`: "engine-chain test would XPASS with the fix / 1e-9 finance test would XPASS with the fix".
6. **The strict xfails are real guards, failing for the stated reason.**
   - Command: `uv run pytest tests/golden/test_g1_abc_tiebreak.py tests/golden/test_g1_finance_register.py -q --runxfail`.
   - Output (auditor, round 1): `AssertionError: assert ['z9','a0',...] == ['z9','z8',...]`; `AssertionError: assert ['S2.opex.y1....3.total',...] == []`; `2 failed, 16 passed`. Re-run in this record: same two assertion errors, index 1 `'a0' != 'z8'` and 12 extra S2 keys, first `S2.opex.y1.labor`.
7. **Fix-round finding 2 is resolved: the I48 structure is covered by a normal test, only the 1e-9 comparison is xfailed.**
   - Command: `PYTHONPATH=. uv run python audit_G1g/q7.py`.
   - Output: `S2.capex.controls golden/F7: 50000.0 50000.0 / S2.capex.overflow golden/F7: 0.0 0.0 / S2 capex total vs S0: 135173.85457490606 135173.85457490606 / S2 npv golden / F7 npv_vs_baseline: 0.0 0.0 / max rel mismatch: (6.07e-05, 'S2.opex.y3.labor') / keys mismatching at 1e-9: 12 at 5e-3: 0`.
8. **I42 holds by hand against the rebuilt golden.**
   - Command: inline hand computation from `golden_values.json` and `golden_basis.yaml` (`PYTHONPATH=. uv run python`).
   - Output: `dcf0 -282430.029; dcf y1 hand -28014.734872974877 golden -28014.734872974877; npv hand -391617.1338401684 golden -391617.1338401684`.
9. **Lint, type and test state of the G1g files at round 0 and round 1.**
   - Command: `uv run ruff check ... ; uv run ruff format --check ... ; uv run pyright ...` on `demand.py`, `workbook.py`, `tests/golden/test_g1_*.py`.
   - Output: `All checks passed!`, `2 files already formatted`, `0 errors, 0 warnings`; round 0 `74 passed, 2 xfailed in 2.55s`, round 1 audit state `75 passed`.
10. **I77 matches the engine's decision (fix-round finding 4).**
    - Command: `sed -n 223,241p src/whsizing/design/inbound.py`.
    - Output: `F_INBOUND_SPARSE ... The zero pallets of that case are not also called sparse`: `no_pallets` suppresses the pallets branch only. `np.percentile` over 26 days gives 0.0 for 1 receipt day, 3.75 for 2, 5.0 for 3.

## Audit rounds

Two rounds, each with a spec-compliance auditor and a runtime-proof auditor. The proof auditor returned `pass_with_issues` in both rounds but with no recorded tests, findings or proofs; every finding and proof above comes from the spec auditor. No round 2 is recorded.

### Round 0 (build): spec auditor pass_with_issues (74 passed, 0 failed), proof auditor pass_with_issues

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | medium | F3 `src/whsizing/profile/abc.py` `classify()` does not implement I6 as amended (sorts `[by, "sku"]`, called from `build.py:84`); engine S0/S2 values differ from golden by up to 0.314 %, engine ranking depends on the salt. | **Deferred.** Owned by F3, outside G1g's paths; reported as a blocker and guarded by two strict xfails. |
| 2 | medium | The blanket strict xfail on the I48 degenerate-cube test hides the non-ABC I48 assertions (controls, overflow, S2 capex == S0 capex, npv 0). | **Fixed** in the fix round: test split into a normal test (60 keys at 0.5 % plus the I48 assertions) and a strict xfail for the 1e-9 comparison. Confirmed in round 1 (proof 7). |
| 3 | low | The xfail markers lack `raises=AssertionError`, so another exception would also count as expected; the module-level engine import couples oracle-only tests to the engine. | **Fixed.** Both markers carry `raises=AssertionError`; the engine import is inside the engine test. Confirmed in round 1 (proof 6). |
| 4 | low | The golden note on I77 does not record that F4 already decided the `F_INBOUND_SPARSE` / `F_RECEIPTS_NO_PALLETS` question. | **Fixed.** The note now records it (proof 10). |

### Round 1 (after the fix round): spec auditor pass_with_issues (75 passed, 0 failed), proof auditor pass_with_issues

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | medium | Unresolved from round 0: F3 `abc.py:23` still sorts `[by, "sku"]`; 6 SKUs get another class than the oracle on tiny_golden (proof 5). | **Deferred** (F3 owns it; verified still unfixed in this record, see Open issues). |
| 2 | low | `docs/INTERPRETATIONS.md` golden note on I6 says the old order "moves 5x of them" (actual: 135 of 741 under the test's salt, 55 to 137 across salts) and omits `S0.labor.annual_hours.y1..y5` and `S0.labor.core_heads_day` (6 of the 55 changed keys) from the list of moved keys. The rest of the note checks out. | **Not fixed.** No round after round 1; the text "moves 5x of them" is still in the file (checked with grep in this record). |

Blockers reported by the engineer at the fix round, outside G1g and not re-checked in this record: `tests/unit/test_f0_cli.py` collection ImportError (`whsizing.cli` has no `app`) and 16 failures in `tests/unit/test_f8_sens_oat.py` (`TypeError: _run() missing 1 required positional argument: 'where'`), seen in the full suite.

## Open issues

1. **medium, F3 (not G1g):** `src/whsizing/profile/abc.py:23` (`ranked = skus.sort([by, "sku"], descending=[True, False])`, called from `src/whsizing/profile/build.py:84`) must sort by `lines, units, avg_stock, unit_cube_m3, weight_kg` descending (unknown weight as 0), then `sku` ascending (I6 as amended, `docs/INTERPRETATIONS.md:42`). Until then the engine's by-lines classes differ from the oracle for 6 SKUs, the engine depends on the anonymisation salt, and engine and golden differ by up to 0.314 % (inside the 0.5 % T1.5 tolerance; T3.1, T4.1, T6.1 to T6.3, T7.1 pass). Whoever fixes it must remove the two strict xfail markers in `test_g1_abc_tiebreak.py` and `test_g1_finance_register.py` (they will XPASS and fail strict).
2. **low, `docs/INTERPRETATIONS.md` (G1g's golden notes):** fix "moves 5x of them" (135 of 741 under the test's salt) and add `S0.labor.annual_hours.y1..y5` and `S0.labor.core_heads_day` to the list of moved keys.
3. **Outside G1g (round 1 report):** `tests/unit/test_f0_cli.py` ImportError and 16 failures in `tests/unit/test_f8_sens_oat.py`.
4. The proof auditor of both rounds recorded no detail, so the runtime proofs rest on the spec auditor's scratch runs.
5. Register gap from the build (I77 vs I56: whether `F_INBOUND_SPARSE` fires next to `F_RECEIPTS_NO_PALLETS`) is closed: F4 decided it and the golden note records it. The register text of I77 itself still does not say it.

## Not applicable here and why

- **Real client data:** the golden case is the synthetic tiny_golden; no client data was used or needed.
- **Receipts-mode oracle (I77 flags):** the oracle has no receipts mode (derived inbound only); the guard test shows it refuses instead of computing derived silently. No golden value depends on I77.
- **I75 (runner conventions) and I76 (sensitivity):** no oracle counterpart, so there is nothing to compare; no contradiction with the oracle was found.
- **Domain-expert review:** the I6 tie-break chain is taken verbatim from the register as amended; no expert sign-off was part of this audit.
- **Docker and GitHub CI:** not used by these tests and not run.

## Fresh test output

Command, run from `/Users/skarwech/saas_v1` while writing this record: `uv run pytest tests/golden/test_g1_*.py -q -rA` (captured-log noise trimmed; the G1g lines are the abc_tiebreak lines, the last 2 finance_register lines and the two XFAIL lines).

```
..x................................x.................................... [ 93%]
.....                                                                    [100%]
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_abc_order_ties_by_lines_units_stock_cube_weight_then_sku
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_abc_order_is_not_the_old_sku_ascending_tie_break
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_golden_values_do_not_depend_on_the_sku_salt
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_old_order_made_the_golden_values_depend_on_the_sku_salt
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_golden_class_boundary_inside_a_line_tie_follows_the_chain
PASSED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_receipts_mode_is_not_silently_derived_in_the_oracle
PASSED tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_is_costed_as_the_manual_baseline_in_the_oracle_and_f7
... (other G1a to G1f tests, all PASSED)
XFAIL tests/golden/test_g1_abc_tiebreak.py::test_T1_5_engine_abc_follows_the_same_tie_break_chain - F3 src/whsizing/profile/abc.py classify() still sorts [by, 'sku'] (descending=[True, False]); I6 amended needs lines, units, avg_stock, unit_cube_m3, weight_kg descending, then sku
XFAIL tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7 - G1g: the oracle ABC order follows I6 as amended, F3 abc.py classify() still ties by sku only (S0 labor differs by 0.006 %); see test_g1_abc_tiebreak.py
75 passed, 2 xfailed in 2.22s
```

Same two files under `--runxfail` (run in this record, relevant lines):

```
E       AssertionError: assert ['z9', 'a0', ...3', 'z5', ...] == ['z9', 'z8', ...5', 'a1', ...]
E         At index 1 diff: 'a0' != 'z8'
E       AssertionError: assert ['S2.opex.y1....3.total', ...] == []
E         Left contains 12 more items, first extra item: 'S2.opex.y1.labor'
FAILED tests/golden/test_g1_abc_tiebreak.py::test_T1_5_engine_abc_follows_the_same_tie_break_chain
FAILED tests/golden/test_g1_finance_register.py::test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7
```
