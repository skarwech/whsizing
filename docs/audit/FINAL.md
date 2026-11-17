# whsizing POC: final independent audit

## 1. Verdict

**Overall: `ready_with_conditions`**

1. No critical or high finding survived the skeptic (confirmed: 0 critical, 0 high, 6 medium, 6 low). The independent recomputation reproduced about 10,850 numbers with 0 mismatches (largest relative difference about 7e-14), every spec test id T0.1 to T11.4 has a passing test (only two legitimate skips), reruns are byte-identical, and exit codes 0 to 5 behave as specified on the real binary.
2. Definition-of-done items 6 and 8 (hold-out error on one real site; expert reviews #1 and #2) are not met and cannot be met in this environment, and item 1 is proven on synthetic files only. They are human and real-data preconditions whose mechanism is the pilot (`docs/PILOT.md` section 4.3), so the verdict is not `not_ready`, but they keep it below `ready_for_pilot`.
3. Conditions before any client-facing use: (a) the working tree was mid-remediation and still changing at the last check (sections 1.1 and 6.3), so once it settles re-run the whole suite, ruff, pyright and coverage on it and re-audit M2 to M5, L4 and L6, because every figure in this record except the targeted checks of 1.1 describes the audited tree; (b) M4 (`calibrate` overwrites an earlier calibration and has no observed-peak option) and the M6 snapshot gap were still open at the last check; (c) expert review #1, then a real-site T11.4 and review #2. M1 (Streamlit bound all interfaces) was confirmed at audit time and has since been fixed and verified live. M2 reproduced at the first check and no longer reproduced at the last one (one reproduction, not audited); code for M3, M5, L4 and L6 appeared in between and was not exercised.

### 1.1 Which tree each statement describes

The repository was not stable while this audit finished, and nothing is committed, so there is no revision to name. Times are local clock times of the final auditor's checks. Three states matter:

- **Audited tree.** The state at the lead's full run (`coverage_full.txt`, ends `DONE exit=0`). The dimension records, the skeptic verdicts and the test, coverage, ruff and pyright figures describe it. Every finding in section 6 was confirmed against it.
- **After the first check (01:03 to 01:10).** `find . -newer coverage_full.txt` (excluding `runs/`, `.venv`, caches) listed `.gitignore`, `.streamlit/config.toml`, `justfile`, `docs/INTERPRETATIONS.md`, `docs/PILOT.md`, `docs/adr/ADR-002-worlds-and-ranges.md` and `tests/unit/test_f10_app_static.py`: documentation, configuration and one test, no file under `src/`. The register had gained I83 to I89 (it ended at I82 at audit time) and described fixes the code did not yet have (section 6.3).
- **Moving tree (01:10 onwards).** Source edits began to land at 01:10 and kept arriving. At the last snapshot (01:15) the changed files included `io/rules.py`, `io/dq.py`, `io/ingest.py`, `io/readers.py`, `io/anonymize.py`, `units.py` (new), `schemas/params.py`, `catalog/models.py`, `catalog/engine_defaults.yaml`, `design/inbound.py`, `engine/area.py`, `engine/queue.py`, `engine/throughput.py`, `scenarios/runner.py`, `report/tables_data.py`, `report/pdf.py`, both report i18n files and about ten test files. The final auditor did not audit these edits.

Checks the final auditor ran (outputs under `scratchpad/final/finalaudit/`):
- About 01:06, the new static test: `uv run pytest tests/unit/test_f10_app_static.py -q` gave `10 passed in 1.33s`; `ruff check`, `ruff format --check` and `pyright` on that file gave `All checks passed!`, `1 file already formatted`, `0 errors, 0 warnings, 0 informations`.
- About 01:08, M1 live (section 6.1).
- About 01:09, before any source edit: every test file that reads an edited doc or config file (`test_g1_expert_rulings.py`, `test_g1_finance_register.py`, `test_f0_tooling.py`, `test_f10_app_static.py`, `test_f5_eligibility.py`, `test_f5_paramset.py`, `test_f6_area.py`, `test_f6_inputs.py`, `test_f8_r5_runner.py`) plus all of `tests/golden`, not slow, not bench: `218 passed, 3 deselected in 9.63s`.
- 01:13 to 01:15, on the moving tree: the test files touched by the new edits (`test_f5_units.py`, `test_f2_rules.py`, `test_f9_tables.py`, `test_f5_loader.py`, `test_f4_design.py`, `test_f9_excel.py`, `test_f9_pdf.py`, `test_f2_headers.py` and `tests/e2e/test_f2_ingest.py`), not slow, not bench: `329 passed, 1 deselected in 63.78s`. Several of these files were edited again while or after they ran (until 01:15), so this is a snapshot, not a verdict on the final state.
- Re-checks of M2 and of the register claims, each stamped with its time in 6.1 and 6.3.

Not re-run: the whole suite, whole-tree ruff and pyright, coverage, the slow and bench tests, and any end-to-end report build. The lead's figures (section 4) are for the audited tree and say nothing about the moving tree.

### 1.2 How this record was produced

It consolidates the eight dimension records (trace, sigs, e2e, numbers, expert, security, robust, quality), the skeptic verdicts and the lead's facts. Where an evidence string was clipped in the material supplied to the final auditor, the record says "excerpt" and uses only the visible text. The final auditor re-read these items directly: `coverage_full.txt`, spec 1.4, `.streamlit/config.toml`, the `justfile` `app` recipe, `_r1` in `src/whsizing/io/rules.py`, `grep -rniw pint src pyproject.toml`, register I73, I75, I78 and I83 to I89, the register's "Open expert rulings", and the stage timings in the e2e auditor's run manifests.

Process notes, stated so nobody has to find them:
- The security auditor ran `whsizing ingest` once without `--out-dir`, which wrote one folder under the repository `runs/` (`runs/2026-11-09T23-16-55_720808`); it deleted that folder, and the final auditor confirmed it is absent. This broke the read-only rule for one scratch-sized folder and changed nothing else.
- The numbers auditor read `engine/shifts.py`, `catalog/paramset.py` and `scenarios/sensitivity.py` after its first pass to align conventions, so those three parts of its recomputation check consistency with I65, I76 and the override rule and are not spec-blind.
- The repository `runs/` folder holds 16 run folders from earlier waves, `.uploads/` and `demo/`, all git-ignored (`/runs/` in `.gitignore`); unchanged by the audit.

Machine facts: macOS (Darwin 24.6), Python 3.12 via uv, Homebrew Pango present, Docker not installed, GitHub CI not runnable, no real client data, no domain-expert review, Excel and LibreOffice not installed, poppler absent, Liberation and DejaVu fonts not installed (Verdana is embedded in the PDFs). Nothing is committed: manifests show `git_sha` unknown.

## 2. Definition of done (spec 1.4)

Status vocabulary: proven / proven on synthetic data only / not provable here.

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | A messy real client file is ingested in < 15 min including mapping (T2.9) | proven on synthetic data only | `tests/e2e/test_f2_ingest.py::test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation` passed in 0.4 s against a 900 s budget, with the mapping confirmations scripted. e2e auditor: the messy FR export of the 1 M line ecom_mid (BOM, `;`, decimal comma, mixed dates, duplicates, orphans) ingested non-interactively in 5.19 s of ingest stage time, exit 0, DQ 73.25 "usable with caveats". No real client file exists here. |
| 2 | 1 M order lines profiled in < 60 s (T3.8) | proven on synthetic data only | T3.8: 1,030,012 lines profiled in 1.06 s. CLI: stage `profile` 2.03 to 2.10 s on 1,030,013 lines (2.55 to 2.57 s on the later, heavier-loaded runs). Local machine, not the CI runner. |
| 3 | Three scenarios sized in < 10 s (T8.5) | proven on synthetic data only | T8.5: 0.57 s (3 scenarios x 3 worlds, size + finance + write). CLI: stage `scenarios` 0.47 to 0.70 s. Local machine. |
| 4 | Excel + PDF generated in < 60 s with no manual edit (T9.7) | proven on synthetic data only | T9.7: Excel 0.5 s, PDF 3.2 to 4.4 s per language. CLI: report stage 8.0 to 10.5 s for 4 files (fr + en, pdf + xlsx), no manual step. PDF 17 pages, Excel 12 sheets, 0 error cells. |
| 5 | Every figure traces to a `TraceNode` and a `Param` (IC1, IC2) | proven | T6.11 (every numeric leaf of `result.json` maps to a trace node) and T9.4 (IC1 to IC8 each fail on a tampered fixture). Live: editing one trace node gives `report` exit 5 and no report file; untampered runs pass. Caveat: at audit time Annex A printed the base parameter value, not a scenario override (M3; code for a fix appeared after the first check and was not exercised). |
| 6 | Hold-out error <= 10 to 15 % on total daily FTE and peak lines/h for one real site, or the gap documented (T11.4) | not provable here | T11.4 is skipped by design (needs 12 months of real order lines and monthly hours per activity, plus expert acceptance). Synthetic e2e hold-out MAPE 0.6 % to 0.8 % proves the plumbing only (synthetic actuals come from the model's own predictor). `whsizing calibrate` has no option to supply the observed peak lines/h (section 6.2; I86 claims one, the CLI has none). No gap document exists because no real site was run. |
| 7 | Any run is reproducible from its manifest (T6.9) | proven | T6.9 (3 nodes). Live: `whsizing rerun` of a `run-all` run (with `WHSIZING_SALT` unset) and of a staged run give byte-identical `result.json`, `finance.json`, `trace.jsonl`, `comparison.json`, `sensitivity.json`, `design_day.json`. Determinism also held across thread counts, hash seeds, time zones, locales, cwd and out_dir on 1 M lines (section 5.7). |
| 8 | Expert reviews #1 and #2 completed with the section 8 checklists | not provable here (not done) | `docs/assumptions.md`: 72 ranged parameters, 72 with source TODO, 72 with confidence L, `validated_by` empty. The PDF section 8 prints the used-parameter TODO count. `docs/PILOT.md` holds the checklists; no signed review exists. Spec Appendix C ships the catalog as TODO / L by design. Human dependency, not a code defect, but the item is not met. |

## 3. C5 performance budgets

Measured by the e2e auditor on the real binary, on ecom_mid (1,030,013 order lines, 730 days), from `stage_done` log lines and `manifest.timings`, on a loaded machine (load average 9 to 16 on 12 cores). The final auditor re-read the timings in those run manifests: the values below match. The right-hand column is from the trace auditor's runs of the spec tests. These are upper bounds: `just bench` was not run and the CI runner was not available.

| C5 budget | Limit | CLI, e2e auditor | Spec test, trace auditor |
|---|---|---|---|
| ingest + validate, 1 M line CSV | < 2 min | staged ingest of 4 datasets 3.92 s (0.17 + 2.63 + 0.55 + 0.57); `run-all` stage `ingest` 3.34 s; messy FR export 5.19 s | 3.1 s (`test_C5_bench_ingest_and_validate_1m_line_csv`, 1,030,012 lines) |
| profile, 1 M lines | < 60 s | 2.03 s staged, 2.07 s staged on the messy run, 2.10 s `run-all` #1 (2.57 s and 2.55 s on runs #2 and #3) | 1.06 s (T3.8) |
| size, 3 scenarios x 3 worlds | < 10 s | 0.47 s staged, 0.50 s `run-all` #1, 0.70 s `run-all` #2; messy run 1.21 s | 0.57 s (T8.5) |
| sensitivity, 7 parameters x 2 | < 60 s | 8.64 s (staged `compare`), 10.33 s, 11.05 s, 11.95 s (`run-all`, `rerun`); 22.16 s on the messy run at peak load (24 s wall for `compare`) | 8.6 to 9.1 s; 12.9 s inside the T8.5 session |
| report, both formats | < 60 s | one language, pdf + xlsx 3.9 s; both languages (4 files) 8.0 s staged, 9.6 to 10.5 s `run-all`, 8.7 s on the messy run | Excel 0.5 s + PDF 3.2 to 4.4 s per language (T9.7) |
| whole `run-all`, 1 M line CSV to 4 report files | no budget | 27.6 s wall (stage times sum to about 26 s) | not measured |

Every budget passes by more than 5x. Caveats: only 2 of the 5 budgets (ingest, T8.5) carry the `bench` marker, so `just bench` and the CI `bench` job never measure profile, sensitivity or report (finding L1); the CI "exceeded by more than 50 %" tolerance is not implemented (the tests assert 1.0x, which is stricter).

## 4. Tests and coverage

Lead's full run on the audited tree (`pytest -m 'not bench' --cov=whsizing`), from `coverage_full.txt`. These figures do not cover the source edits that landed afterwards (section 1.1):

```
1802 passed, 2 skipped, 2 deselected in 837.52s (0:13:57)
SKIPPED [1] tests/e2e/test_f11_calibrate_e2e.py:80: T11.4 needs the real pilot data (12 months of order lines and monthly hours per activity); manual acceptance by the domain expert (review #2)
SKIPPED [1] tests/unit/test_f0_report.py:28: Docker not installed
TOTAL                                 10513    168   2140    106    98%
```

engine/ and finance/ block, verbatim (the spec gate and the CI gate are >= 80 %):

```
src/whsizing/engine/labor.py         201      1     64      1    99%   279
src/whsizing/engine/queue.py         100      2     28      2    97%   50, 123
src/whsizing/engine/shifts.py        130      1     12      1    99%   91
src/whsizing/engine/storage.py       131      1      6      2    98%   223, 297->301
src/whsizing/finance/baseline.py      54      1     18      1    97%   55
src/whsizing/finance/compute.py      133      1     38      1    99%   142
src/whsizing/finance/metrics.py       36      1     14      1    96%   36
src/whsizing/finance/opex.py         111      2     22      2    97%   68, 71
TOTAL                               1458     10    246     11    99%
```

Other numbers: `ruff check` all checks passed, `ruff format` 257 files already formatted, `pyright` 0 errors and 0 warnings (lead; the quality auditor reproduced them: `Found 256 source files`, `0 errors, 0 warnings, 0 informations`). The 2 deselected tests are the `bench` marker; the trace auditor ran both and they passed (C5 ingest 3.1 s, T8.5 0.57 s).

Reconciliation of the earlier figure "1747 passed, 3 skipped". 1806 tests are collected (`1802 + 2 + 2 = 1806`); 55 are marked `slow` and 2 `bench`, T8.5 is both, so 56 are excluded from a non-slow, non-bench run and `1806 - 56 = 1750 = 1747 + 3`. That earlier run therefore did not include any slow test. The trace auditor executed all 56 by node id (766 fast T-id nodes: 764 passed, 2 skipped; 34 slow T-id nodes plus the C5 bench: all passed; 22 further slow ecom_mid e2e tests: all passed). The full run above shows exactly 2 skips; the third skip of the earlier run was not identified by anyone.

Test-layer gaps against spec C3: no syrupy snapshot of any kind (M6); the golden workbook holds values with formula comments, not live Excel formulas (registered in the golden-case notes of the register); the back-test layer is the skipped T11.4.

## 5. Dimensions

All eight dimensions returned `pass_with_issues`. None returned a plain pass, and none returned a fail.

### 5.1 trace: Spec traceability matrix. Verdict: pass_with_issues

Every spec test id T0.1 to T11.4 has at least one named `test_T<f>_<n>_*` function (508 definitions, 799 node ids). All were run by node id and none fails. Issues are registration gaps, gate coverage and unmet human sign-offs, not wrong numbers.

Key checks and proofs:
- Fast nodes: `uv run pytest @<scratch>/fast_ids.txt -p no:cacheprovider -q -rs` gave `764 passed, 2 skipped in 128.37s`; the skips are T11.4 and the T0.5 Docker variant.
- Slow nodes: `34 passed in 184.21s` and `22 passed in 192.42s`; T3.8 1.06 s, C5 ingest 3.1 s, T8.5 0.57 s, F9 PDF 4.4 s FR.
- C1 on a real run folder: a probe on `write_manifest` saw 6 writes with `timings` keys growing load, ingest, profile, design, scenarios, comparison, sensitivity (the report stage is merged by `report`). Seed 42, Python and package versions recorded; the catalog snapshot is byte-identical to `catalog/`; `params_snapshot` holds the basis override (`manual_p2p.pick_rate_shelving_lines_h` 62.0 against catalog 70) and the scenario override (`S1:amr_gtp.station_rate_lines_h` 230.0). The `git describe` and dirty logic works in a scratch git copy (`0.1.0+f67442b`, `-dirty` after editing a tracked file); on this tree the manifest shows 0.1.0 and `git_sha` unknown because there is no commit.
- C2 (software-enforceable parts): ids re-hashed (HMAC-SHA256, 16 hex), description and customer dropped by default, the salt string is absent from every file of the run folders, no network module imported anywhere under `src/`. NDA, transfer, encrypted-disk and deletion steps are process steps, not checkable here.
- Live exit codes 2, 3, 4 and 5 confirmed.
- No syrupy snapshot: `find tests -type f ( -name '*.ambr' -o -name '*.snap' -o -name '*.json' )` returns only `tests/golden/golden_values.json`; `grep -rn -E 'SnapshotAssertion|\bsnapshot\.' tests --include='*.py'` is empty.
- `uv run pytest --collect-only -q -m bench | grep ::` lists 2 tests.

### 5.2 sigs: Signatures and contracts vs spec. Verdict: pass_with_issues

All spec signature lines, the 21 section 2.5 models, the 2.7 exit-code table and the F10 command and option table were compared with the code by introspection and spec-literal calls. 0 critical, 0 high, 1 medium (downgraded to low by the skeptic: L3), 9 low. Every spec field, type and default of the section 2.5 models is present (`cmp_models.py`: no "FIELD MISSING", no "ORDER DIFFERS"); the extra fields are optional (`DesignDay.percentile_values`, `DesignDay.flags`, `FinancialResult.delta_cash_flows_typ`, `FinancialResult.notes`, `RunManifest.timings`, `RunManifest.project_hash`). Exit codes 1 to 5 are each proven through the CLI. All 11 commands and options match the F10 table; extras are registered in I78. The section 2.4 run folder layout is produced.

Key proofs:
- `write_canonical(frames, out_dir)` as in the spec raises `TypeError write_canonical() missing 1 required positional argument: 'manifest'` (L3).
- Spec-literal calls to `select_design_day` (ConfigError `catalog is required`), `size_scenario` (missing keyword-only `lines`) and `compute_finance` (missing keyword-only `daily` and `tracer`) fail as the register says (I58, I61, I73).
- `sensitivity_oat(project)`, `breakeven(project)` and `percentile_sweep(project)` raise ConfigError for a `Project`; with a `RunContext` they give 14 tornado bars (sorted), a break-even and 8 sweep rows.
- `uv run whsizing run-all` on the 31-day tiny_golden: `error: 1 blocking data-quality issue(s): R9 (order_lines): history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed.` exit 3.
- The literal `cube_asrs` family example of the spec (section F5) no longer loads as written: three required parameters were added (registered in I46, I26, I30).

### 5.3 e2e: End-to-end, performance and layout. Verdict: pass_with_issues

The whole documented flow ran on the real binary with no traceback and no wrong exit code: synth, ingest, profile, basis init, size, compare, report, run-all (twice), rerun, calibrate, validate-catalog, on clean ecom_mid (1,030,013 lines) and on two messy variants (`--defects`: UTF-8 BOM FR export, cp1252 b2b_cases). Every run folder matches spec 2.4. Reruns and the second `run-all` are byte-identical; the second `run-all` reuses canonical (`canonical_reused`, ingest 0.059 s against 3.34 s). PDFs: 17 to 18 pages, run id and indicative-study banner present, no `{{`, None or nan (text layer only); Excel: 12 sheets, 2,102 numeric cells, 0 error cells. Streamlit health 200 and AppTest of page 6 clean in en and fr; the server was stopped afterwards. Findings: one medium confirmed (M4, calibrate), one medium refuted (cm-instead-of-mm rows), one low (corrupt `trace.jsonl`).

Key proofs:
- `env -u WHSIZING_SALT whsizing ingest ...`: `error: no anonymisation salt: set $WHSIZING_SALT or pass a salt file kept outside the repository`, exit 2.
- R9 on a 1.97-month history: `error: 1 blocking data-quality issue(s): R9 ... at least 3 months needed.`, exit 3.
- `size --strict` with a tiny building: `error: strict: no scenario fits the building`, exit 4.
- Tampered `scenarios/S0/trace.jsonl`: `error: 1 integrity check(s) failed ... IC1 ... cell value 141.58823529411765 differs from trace node S0.storage.pallet_rack.positions: 431.7647058823529`, exit 5, `report/` empty.
- Exit 1: a column dropped from a canonical parquet gives `error: canonical order_lines: cannot find column "qty_units" ... (traceback in .../logs/run.log)`, exit 1, `command_failed` line in `run.log`.
- Reports: `uv run python -I check_reports.py <run>` gave `PDF fr: pages=17 run_id=True banner=True '{{'=False None=0 nan=0`, `XLSX fr: sheets=12 ... numeric cells=2102 formula cells=0 error cells=0`.

Unverified by this dimension: Docker, T11.4, PDF visual rendering (poppler absent), interactive Streamlit pages 1 to 5, `just bench` on an unloaded runner.

### 5.4 numbers: Independent recomputation. Verdict: pass_with_issues

An independent implementation (polars, numpy and pyyaml only, nothing imported from `whsizing`) re-derived F3, F4, F6a to F6e and F7 for S0, S1 and S2 in the lo, typ and hi worlds on ecom_mid with the example basis and the client_current baseline. No difference above 0.5 % anywhere.

Key proofs:
- Base run: `TOTAL checks 604 pass 604 fail 0` (e.g. `S2.tco.typ claimed= 6457090.220572476 recomputed= 6457090.220572477`), largest relative difference about 7e-14.
- Sixteen more CLI-run variants (growth 0.02, 0.032, 0.048, 0.06; percentile 80, 90, 98; labor cost x0.8 and x1.2; horizon 3; finance horizon 12; baseline S0; rent_mode none; 1 and 3 shifts; the b2b_cases profile with pallet orders) and two more with their own recompute (rent_mode full_building with baseline S0, and the 3-year horizon): about 10,850 comparisons in total, 0 mismatches.
- Summary sheet: `numeric Summary cells compared to comparison.json: 126  mismatches: 0`; `comparison.json` equals the per-scenario `result.json` and `finance.json` (120 values compared, 0 bad). Tornado 54 + 24 values, percentile sweep 76 values and 2 break-even roots (payback 4.999987 and 4.999991) reproduce.
- 7,634 Range objects across 129 files: 0 `lo <= typ <= hi` violations, 0 negatives, 0 non-finite. The recomputation reads canonical tables that were confirmed equal to the raw CSV.
- Packing Erlang-C is not computable on this run (a = 9.15 >= c = 6 in all three scenarios, `F_UNSTABLE:packing`, I69); the stable pools (S1 gtp_stations c=3, S2 ports c=8) reproduce with the spec recursion.
- I33 sized (`rc4_i33.py`): S0 437,619 EUR (9.32 % of TCO), S1 235,221 EUR (4.11 %), S2 221,196 EUR (3.43 %).

Not verified by this dimension: the PDF figures beyond the headline numbers, the other Excel sheets, receipts-mode inbound, the S1 (amr_gtp) formulas against spec text (the spec gives none beyond the F7 table and no golden covers S1; checked against I73(d), I63(3), I32, I34, I35 only), and the I47 low-confidence counts.

Items raised: I4 annualisation with 252 days against 313 observed operating days and the I33 temp-hour double count were both refuted by the skeptic (section 7); I33 stays an open expert ruling (section 9).

### 5.5 expert: Domain-expert plausibility review. Verdict: pass_with_issues

Reviewed on ecom_mid, b2b_cases, a small-scale ecom, a b2b receipts-mode run and an S0-as-baseline rerun. The report is honest in structure: every headline table carries lo/typ/hi, the indicative-study banner and limitations box are present, the TODO / confidence-L count (71 of 71 used, 72 of 72 in the catalog) is printed in the summary, section 8 and the annexes, there is no "recommended" label, and the overlap note is printed. Orders of magnitude are mostly defensible for a placeholder catalog (about 11 AMR robots per station, about 580 EUR per cube bin of capex, labor about 73 % of manual opex, about 0.44 m2 per pallet-rack position). No arithmetic error: capex, TCO, NPV and cost per line recompute.

Check statuses: pass for "never recommends a scenario", "no TODO parameter hidden", "banner and limitations present", "headline arithmetic recomputes" and "F_UNSTABLE:packing appears for every scenario (I69)"; partial for order-of-magnitude plausibility, "never states a number without its range", French wording, `F_ROBOT_DENSITY` communication and `F_SCALE_LOW`; unverified for Excel sheet-level plausibility, catalog values against real-world benchmarks (every value is a `[P]` placeholder) and the EN report and ICPE thresholds. Three checks were reported as `fail` (receipts-mode temp hours, the I33 double count, the client-current baseline at 2.1x the modelled manual labor); the skeptic refuted all of them as spec-literal and registered (I64, I33, I73(b), I42), so they stand as open expert rulings and not as defects (section 7).

Key proofs:
- `uv run whsizing run-all <ecom_mid.yaml>`: `S0 capex 317 [169-707] TCO 4,696 [3,296-6,987] NPV 3,134 payback 0.4 | S1 1,849 / 5,718 [3,374-12,726] / NPV 2,148 [-4,321-4,149] payback 2.0 | S2 2,710 / 6,457 [3,675-14,184] / 1,376 payback 2.8`, and the overlap note `Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2`.
- With `baseline: S0`: `S1 NPV -1,022 [-5,739--78] payback -`, `S2 NPV -1,761 [-7,197--379] payback -`.
- Packing: `{'resource':'packing','servers':6,'arrival_rate_h':289.23,'service_rate_h':31.61,'offered_load':9.1508,'stable':False,'c_min':11}`; the flag message says `at least 11 needed`, the PDF text does not.
- Cube: `S2.equipment.decant_port_load_peak_h 5.212`, `port_load 7.158`, `robots 35`, `utilisation.robots 0.974`, `robots_per_grid_m2 0.448` (cap 0.05).
- Annual volume: 626 operating days in 730 (313 a year), 480,614 lines in 2024 and 501,296 in 2025, against `annual_lines_y1` 411,084.62 (1568.5 x 252 x 1.04).

The seven spec-literal items were refuted (section 7). One survived: Annex A prints the base value instead of the scenario override (M3). Further expert observations are in section 6.2.

### 5.6 security: Privacy, security and data protection (C2, C6). Verdict: pass_with_issues

No confirmed leak of identifiers, PII or the salt. All 69 files of a `run-all` folder were scanned (parquet values, PDF text, metadata and annotations, xlsx cells, comments and zip parts): no raw SKU, order or receipt id, no raw description or customer text (unless `--keep-descriptions` was requested), and no salt in plain, hex, base64, sha256 or md5 form. The tool made no outbound connection in `run-all` (two projects) or in AppTest across all 7 pages on a hostile project, measured with a socket-level harness. The one finding that changes the picture was M1 (the app listened on all interfaces with no authentication when started the documented way); the skeptic confirmed it as medium. It is fixed on the current tree (section 6).

Key proofs:
- `run-all` under a socket-denying harness: `exit=0 (12.6 s)`; the harness log holds only `harness-loaded pid=... argv=[...whsizing, run-all, ...]` and no `CONNECT`, `DNS` or `SENDTO` line; probe: `probe refused: dns denied: example.com`.
- Hashing: `all 300 raw SKUs hashed present in sku_master: True`, `first order-line order_id == hmac(ORD-0007000): True 2ee83a0011940c1b`, `with another salt differs: True`; scan: `scanned 69 files, 78 hit-kinds`, none raw_sku, raw_order, raw_rcpt, hostile text or salt.
- Failed runs: `error: unexpected RuntimeError: induced failure inside _hash_column ... exit=1`, `grep -c FAILCASE` on stdout, stderr and the run folder = 0, also with `--debug` and for a `BaseException` escape.
- A salt file inside a git repository is refused (`error: salt file .../saltrepo/salt.txt is inside a git repository; keep it outside`, symlink case the same); a 0644 salt file outside is accepted silently (low).
- Hostile client text (`<script>`, `{{ 7*7 }}`, `=`, `+`, `-`, `@` prefixes, CSS breakers) is inert: PDF shows `'{{ 7*7 }}'` literally, `<script>` is absent, xlsx has 0 formula elements and every such cell has `data_type 's'`.
- Default `streamlit run` (audited tree): `lsof` shows `TCP *:8595 (LISTEN)`, `/_stcore/health` 200 on `127.0.0.1` and on the LAN address; headless adds a DNS lookup of `checkip.amazonaws.com`, documented in `docs/PILOT.md`.

Hosted mode (C6) does not exist, as scoped (`docs/PILOT.md` states it is out of the POC; the Dockerfile has only `ENTRYPOINT ["whsizing"]`, no EXPOSE, no USER). Unverified: Docker behaviour, a real browser session and websocket content on the LAN, runtime network behaviour of `synth`, `profile`, `calibrate`, `rerun` and the 1 M line run (static grep only), `gatherUsageStats` when started outside the repo root, behaviour in real Excel and PDF viewers.

### 5.7 robust: Robustness, hostile inputs and determinism. Verdict: pass_with_issues

77 hostile cases through the real CLI (`run-all`, non-interactive): exit 0 x45, 2 x14, 3 x15, and the exceptions 1 (extreme inventory), 5 (extreme inventory with a manual-only scenario set) and one timeout (quantity 1e12); no stderr held a raw traceback and no JSON or JSONL held NaN or Infinity. Rows removed are counted wherever checked (`rows_in - sum(dropped_by_rule) == rows_out` for every ingested dataset), with one gap (duplicate header names). Determinism is clean: 10 result files are byte-identical on an 8k-line and the 1 M line ecom_mid dataset across 13 environment and location variants, plus `rerun`. Failure semantics are mostly sound: SIGTERM, parallel runs into one out_dir, read-only out_dir and an out_dir that is a file behave. Reported as two high findings, two medium and five low; the skeptic confirmed M2 (medium), M5 (medium), L4 (low) and L5 (low).

Key proofs:
- Stray epoch date: `history_1month exit=3: error: 1 blocking data-quality issue(s): R9 ... (1.02 months)` against `history_1month_stray1970 exit=0; dq_report: score 100.0 usable; R9 ok 'history 1970-01-01 -> 2025-03-31 (662.97 months)'`. Same real rows with the sentinel date versus the line deleted give different sizing (S0 0.4856 against 0.4533 in the first compared metric) with no DQ signal.
- Negative derived inbound: `inv_1e12 exit=1: error: queue ports: needs mu > 0, lambda >= 0, c >= 0 (mu=187.5, lambda=-9461382997.03309)`, `inv_1e12_s0 exit=5: error: 68 integrity check(s) failed / IC7 ... negative value`, staged `size` exit 0 with negative FTE.
- Quantity 1e12 on 50 lines: `stage_done scenarios 57.829642`, `sensitivity 784.073855`, `exit=TIMEOUT 600.0s`; `erlang_c(10**7, 5e6)` takes 0.331 s.
- Determinism: `=== ecom base2 / thr1 / thr2 / thr8 / hash1 / hash99 / tzny / tzjp / langc langfr / cwd / outdir: identical files: 10/10`. A different salt changes identifiers and float noise only (maximum relative difference 6.3e-15, no integer or string difference besides `dataset_hash`).
- Path too long: `error: unexpected OSError: [Errno 63] File name too long`, exit 1 (L5).

Unverified: quantity 1e12 on every line (it would have left long CPU-bound processes on a shared machine), the ambiguous dd/mm date warning path, hostile `.xlsx` inputs, `calibrate`, the Streamlit UI by hand, Docker, a whole-suite leak check. The check "Disk path too long gives a clean config error" was reported as `fail` (L5, low).

### 5.8 quality: Code quality and maintainability. Verdict: pass_with_issues

Measured code quality is good and the project rules hold at scale. Immutability: 0 mutable defaults, 0 in-place mutation of inputs in engine/finance/design (and src-wide), 41 of 42 dataclasses frozen. Errors: 0 bare `except`, 0 pass-only handlers, all 5 broad `except Exception` re-raise or turn the error into a user message. Typing: ruff 0 violations, pyright 0 errors, strict mode really applies to `schemas/`, `engine/` and `finance/`, 970 of 971 functions annotated. Test quality: 0 genuine tautologies and 0 tests without an assertion. One real finding: `pint` is declared and mandated by the spec but never imported (L6, confirmed low). Everything else is low.

Key proofs:
- `uv run python .../quality/size.py`: `src: nfiles 135, total_lines 22859, over400 13 (max 546 throughput.py), over800 [], nfuncs 971, funcs_over50 12, funcs_over100 0, deep 2. tests: nfiles 121, total_lines 28486, over400 19, over800 [907 f10_app_pages, 827 f10_cli_e2e, 810 f4_register]`.
- `uv run ruff check src tests --statistics` exit 0; `ruff format --check`: `257 files already formatted`; `pyright --stats`: `0 errors, 0 warnings, 0 informations`.
- Strictness probe in a scratch copy: appending a deliberately untyped function to the `__init__.py` of `engine`, `finance`, `schemas`, `design`, `io` gave 24 errors, 8 each in `engine/`, `finance/`, `schemas/` and none in `design/` or `io/` (spec 3.1 says strict on exactly those three).
- `grep -rniw pint src docs`: only a docstring (`schemas/params.py:23`, "Units are pint-parsable or -") and the package list in `scenarios/manifest.py:48`; `pintcheck.py`: `params 72 distinct units ok 3 not pint-parsable distinct 12 occurrences 50`.
- Dependencies: `src imports not declared in runtime/optional: ['click', 'markupsafe', 'pydantic_core']; declared runtime deps never imported in src: ['joblib', 'pint', 'pyarrow']`.
- Error handling: `total handlers 104; BROAD x5 (all re-raise or log and report); NARROW-SILENT x5 all continue with a comment`.

Not measured: cyclomatic complexity (radon is not a project dependency; length and nesting were measured instead); whole-package coverage (taken from the lead's run, section 4). The check `tests_files_over_800` (3 test files, none in `src/`) was reported `fail`; it is a project-rule nit (low).

## 6. Confirmed findings (survived the skeptic)

Totals: critical 0, high 0, medium 6, low 6. Severity is the skeptic's confirmed severity, which is lower than the reported one for eight items (M1, M2, L1 to L6). No confirmed finding changes an engine number on well-formed input; M3 is a report table that prints a different value from the one used. Each finding carries a "Current tree" line stating what the final auditor observed after the audit: at the first check (documentation edits only) and, where the code had started to change, at the last snapshot (section 1.1).

### 6.1 Confirmed

#### Medium

**M1. Streamlit app binds all interfaces, no authentication (security; reported high, confirmed medium, 2 of 2 votes).** At audit time `.streamlit/config.toml` had no `server.address` and the `justfile` `app` recipe was `uv run streamlit run src/whsizing/app/Home.py`; `docs/PILOT.md` gave `--server.address 127.0.0.1` only as a way to avoid the headless checkip lookup. Spec: hosting during the POC is local only; C2 limits access to the founders. Reproduction: `uv run streamlit run src/whsizing/app/Home.py --server.port 8731 --server.headless true` then `lsof -nP -iTCP:8731 -sTCP:LISTEN` showed `TCP *:8731 (LISTEN)`; the log printed `Network URL: http://10.188.159.210:8731`; `/_stcore/health` answered on the LAN address. With `--server.address 127.0.0.1` only loopback was bound (LAN address refused, curl rc 7). Skeptic reasoning: the exposure is real and no register entry covered it, but it needs a network peer and has a one-line fix, so medium, not high. Aggravators read in code, not run end to end: the salt entered in the UI is written to `os.environ` for the whole server process, and the typed-path field reads local paths (see `resolve_run` in 6.2).
**Current tree: fixed, verified by the final auditor.** `.streamlit/config.toml` has `address = "127.0.0.1"`, the `justfile` `app` recipe passes `--server.address 127.0.0.1`, `docs/PILOT.md` now says the app is loopback-only and why, and `tests/unit/test_f10_app_static.py` asserts both (10 passed). Live, with the shipped config and no extra flag: `lsof -nP -iTCP:8941 -sTCP:LISTEN` showed `TCP 127.0.0.1:8941 (LISTEN)`, `/_stcore/health` returned 200 on loopback and `curl` to the LAN address `10.188.159.210:8941` failed with rc 7 (refused); the server was stopped afterwards (0 listeners). The finding stays in the confirmed totals because it was real at audit time.

**M2. A stray 1970-01-01 `order_ts` defeats R1, R9, R10 and R12 (robust; reported high, confirmed medium, 2 of 2 votes).** Spec 4.1: `order_ts` "non-null, within [period - 1 d, today]". `_r1` in `src/whsizing/io/rules.py` tests only null and future. R9, R10 and R12 use the minimum and maximum of the dates, so the history becomes 662 to 675 months and R12 sees no operating days. Not in the register at audit time ("period" is only the whole loaded history, which makes the bound vacuous). Reproduction: the 31-day tiny_golden alone gives `run-all` exit 3 (`R9 ... 1.02 months`); the same CSVs plus one line `STRAY-ORDER-1,1970-01-01T10:00:00+01:00,...` give exit 0 with DQ 100 and shifted sizing numbers (probable mechanism: the 24-month trailing window then starts months before the real history). Skeptic reasoning: an unregistered deviation from a spec rule, on malformed input only, no wrong numbers on clean data, so medium.
**Current tree: reproduced at the first check, no longer reproducing at the last.** Register I83 describes a lower bound (0.5th percentile of the local order dates minus 90 days; R9, R10 and R12 on the kept lines). At the first check (before 01:10) `src/whsizing/io/rules.py` was unchanged and `whsizing run-all .../m1_stray/project.yaml --formats xlsx --lang en --non-interactive` produced a full report with `score 100.0 usable`, `R1 ok 0 ... 0 lines without a readable date`, `R9 ok 0 history 1970-01-01 -> 2025-03-31 (662.97 months)` and `R12 ok 0 0 usual operating days (0.0%) without any order`. At 01:13:50, after `io/rules.py` was edited (01:10), the same project exits 3: `error: 1 blocking data-quality issue(s): R9 (order_lines): history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed.` One reproduction only: no regression run on clean data and no suite on the edited tree.

**M3. Annex A prints the base parameter value, not the scenario override (expert; confirmed medium, 1 vote).** The PDF line is `amr_gtp.station_rate_lines_h 250 lines/h 150 250 350 TODO L Surcharge` while the manifest holds `"amr_gtp.station_rate_lines_h": 250.0` and `"S1:amr_gtp.station_rate_lines_h": 230.0`, and S1 was sized at 230 (service rate 195.5 = 230 x 0.85). Mechanism: `assumptions()` in `src/whsizing/report/tables_data.py` takes the value from `snap.get(pid, p.typ)`; the override survives only in the `note` column, which `templates/partials/appendix_a.html.j2` drops (`drop=["label","note"]`). Only the xlsx shows `S1=230`. A reader who recomputes the 3 stations from Annex A gets the wrong value. Reproduction: `uv run whsizing run-all <project.yaml>` with the example basis and scenarios, then search the PDF text for `230` and `S1=`: no hit. Skeptic reasoning: reproduced from scratch; not registered; it undermines the promise that a reader can reproduce a figure from the appendix.
**Current tree: code appeared after the first check, not exercised.** At the first check `report/tables_data.py` and `appendix_a.html.j2` were unchanged and no test pinned Annex A to `params_snapshot`. `report/tables_data.py` was edited at 01:11; at 01:13:50 it holds `scenario_overrides` and a `<scenario>: value used` column per scenario (register I88), with i18n and `test_f9_pdf.py` / `test_f9_tables.py` edits. The final auditor did not rebuild a PDF, so whether Annex A now prints 230 for S1 is unverified.

**M4. `calibrate` copies its inputs into `calibration/` before parsing them (e2e; confirmed medium, 1 vote).** `calibrate_cmd` in `src/whsizing/cli/sizing.py` does `shutil.copyfile` for `--actuals` and `--activity-map`, then calls `calibrate()`, which writes `fit.json`, `holdout.json` and the note only after `load_actuals` succeeds. Reproduction: a good `calibrate` (exit 0, `ACCEPTED`, MAPE 0.8 %), then `calibrate --actuals actuals_bad.csv` with hours `abc`: `error: .../calibration/actuals.csv: line 2: hours abc is not a number`, exit 3; `calibration/actuals.csv` now holds the bad file while `fit.json`, `holdout.json` and the note are from the earlier calibration. A re-calibration also silently overwrites the earlier one in an otherwise immutable run. Not registered at audit time.
**Current tree: NOT fixed at the last check (01:13:50).** Register I86 says the CLI parses first, copies only on success, refuses to overwrite without `--force` and offers `--observed-peak-lines-h`. `uv run whsizing calibrate --help | grep -- "--force\|--observed"` prints nothing, and `cli/sizing.py` had not been modified since the audited tree at 01:15.

**M5. Erlang-C is O(c) with c derived from unbounded data (robust; confirmed medium, 1 vote).** 50 lines with quantity 1e12 (R13 lists outliers and never removes them, as the spec says) give a derived inbound of 1.2e11 arrivals/h and 417,235,608 AS/RS ports; the loop `for k in range(1, c + 1)` in `src/whsizing/engine/queue.py` then runs for minutes. Robust auditor: scenarios stage 57.8 s, sensitivity 784 s, `run-all` TIMEOUT above 600 s, no progress message. Skeptic reproduction with sensitivity off: exit 0 in 46 s (the "not a clear exit code" part of the report came from the auditor's 600 s harness timeout). Skeptic reasoning: data handling follows the spec; what is missing is a runtime guard, which is an unregistered robustness gap on hostile input, so medium.
**Current tree: code appeared after the first check, not exercised.** At the first check `grep -rn max_equipment_count src catalog` returned nothing. At 01:13:50 `engine.max_equipment_count` (register I85 b, 100,000) is in `catalog/models.py:383`, `engine/throughput.py:25` and `engine/queue.py:43` (message: "(engine.max_equipment_count); check units and outliers (R13)"). The final auditor did not run a quantity-1e12 case.

**M6. No syrupy golden or comparison snapshot (trace; confirmed medium, 1 vote).** Spec C3 lists the golden layer as "pytest + syrupy" and the E2E layer as "run-all on ecom_mid; snapshot of comparison.json"; `just golden-update` is "regenerate snapshots". syrupy is a dev dependency only; no test takes a snapshot fixture; no `.ambr` or `.snap` file exists. The ecom_mid e2e tests assert sanity and rerun byte-identity (determinism within one tree), so numeric drift across code changes on ecom_mid is not caught. `just golden-update` runs `pytest tests/golden --snapshot-update`, which regenerates nothing; the real regeneration is `python -m tests.golden.build_golden`. Not registered; `docs/audit/F9b.md` records it as deferred. Reproduction: `find tests -name '*.ambr' -o -name '*.snap' -o -name '__snapshots__'` prints nothing.
**Current tree: NOT addressed** (at 01:15 `find tests -name '*.ambr' -o -name '*.snap'` returns nothing; no register entry).

#### Low

**L1. C5 `bench` marker covers 2 of 5 budgets (trace; reported medium, confirmed low).** `uv run pytest --collect-only -q -m bench | grep ::` lists only `test_C5_bench_ingest_and_validate_1m_line_csv` and `test_T8_5_*`. Profile (T3.8), sensitivity and report (T9.7) are `slow` and run in the normal test job, not under `just bench` or the CI `bench` job (`ci.yml` runs `pytest -m bench -q --junitxml=bench.xml`). The spec says C5 is measured by `just bench` and the CI bench stage fails on a budget exceeded by more than 50 %. Budgets are still enforced elsewhere, hence low. **Current tree: no change observed.**

**L2. T10.1 happy path on tiny_golden is replaced by a 243-day site, unregistered (trace; reported medium, confirmed low).** R9 (history under 3 months, blocking) stops the 31-day tiny_golden at ingest (`ingest ... --non-interactive` exit 3, "1.02 months"). The spec contradicts itself (31 days; R9 blocking; T10.1 on tiny_golden), so the substitution is forced; the `synth` happy path does use tiny_golden and T10.3 asserts exit 3 on it. **Current tree: registered** in I84 (documentation only; behaviour unchanged, and it could not change).

**L3. `write_canonical` signature deviates from the spec and is not registered (sigs; reported medium, confirmed low).** Spec: `write_canonical(frames, out_dir: Path) -> IngestManifest`; code (`src/whsizing/io/canonical.py`): `write_canonical(frames, out_dir, manifest, timezone='Europe/Paris')`. The spec-literal call raises `TypeError: write_canonical() missing 1 required positional argument: 'manifest'`. The only caller (`io/ingest.py`) passes it; no output is wrong. **Current tree: registered** in I84 (documentation only; the signature is unchanged).

**L4. Derived inbound has no non-negativity guard (robust; reported high, confirmed low; the two votes split low and medium).** `design/inbound.py` computes `mean_out x gf + delta_stock / operating_days` and only checks finiteness. A first inventory snapshot of 1e12 units gives `units_per_day -1.55e10`; staged `whsizing size` exits 0 and prints S0 FTE -3,300,149 and area 1.34e9 m2, while `run-all` exits 1 or 5 depending on the scenario set. The formula is the spec F4 formula, register I12 covers only fewer than 3 snapshots, and a milder decline gives a normal +24.65 units/day, so the trigger is an extreme destock. Not registered at audit time. **Current tree: guard appeared after the first check, not exercised.** `design/inbound.py` (edited 01:13) now raises `DataQualityError` at line 165, as I85(a) describes; at the first check it contained no such guard. The final auditor did not run a negative-inventory case.

**L5. An out_dir path that is too long gives exit 1 instead of exit 2 (robust; reported medium, confirmed low).** `uv run whsizing run-all p_long_name.yaml` with a 300-character `out_dir` component prints `error: unexpected OSError: [Errno 63] File name too long` and exits 1 (traceback: `runner.py` `find_canonical`, a glob before `_mkdir`, which wraps `OSError` as `ConfigError`). `ingest --out-dir` with the same condition exits 2. The message is clear. **Current tree: not re-checked** (`scenarios/runner.py` was edited at 01:14, after the first check; the long-path case was not re-run).

**L6. `pint` is declared, mandated by the spec, and never used (quality; reported medium, confirmed low).** Spec principle 3, section 3.1 and the risk table require unit checks at the parameter layer with pint. `pyproject.toml` declares it and `scenarios/manifest.py` lists it; `grep -rniw pint src pyproject.toml` finds only those and the docstring in `schemas/params.py` ("Units are pint-parsable or '-'"), which is false: `params 72 distinct units ok 3 not pint-parsable distinct 12 occurrences 50`. No register entry at audit time. No wrong output; the `Param` validator checks `min <= typ <= max` only. **Current tree: code appeared after the first check, not exercised.** At the first check `src/whsizing/units.py` did not exist. At 01:13:50 it exists and imports pint (`units.py:15`), `schemas/params.py` was edited, and the loader tests (`test_f5_loader.py`, `test_f5_units.py`) were among the 329 tests that passed in the 01:14 snapshot. The final auditor did not check that all 72 catalog units are accepted beyond those tests.

### 6.2 Reported by the dimensions, not put through the skeptic (low)

Listed so they are not lost; none is counted in the totals above. "Fixed" and "registered" mean what the final auditor read in the tree at the first check (01:03 to 01:10), not a test run of the behaviour.

Spec, register and contracts:
- C1 in the staged CLI (trace): `ingest` and `profile` write no `manifest.json` (it appears after `size`); spec C1 says a `RunManifest` is written at the end of every stage. I78 (a, b) used the missing manifest as a marker, and I89 now states the deviation openly. Registered after audit; behaviour unchanged; `run-all` and `rerun` follow C1.
- `whsizing calibrate` and the app never pass the observed peak lines/h to `calibrate(..., observed_peak_lines_h=...)` (trace): the peak half of the DoD item 6 error is never computed through the CLI. I86 claims an option; the CLI had none at the last check (see M4).
- F3 done-when "the eight charts render in the stub PDF" (trace): not proven; the real PDF and Excel use F9's own chart set, so four of the eight F3 charts (`intraday_heatmap`, `lines_per_order_hist`, `stock_cover_hist`, `cube_weight_scatter`) never appear in a report. Open.
- T5.3 (trace, quality): `test_T5_3_golden_eligibility_shares` has in-body `pytest.skip` branches (lines 224, 246, 260) that would silently turn the golden check into a skip; they did not fire (golden_values.json has 741 keys). Open.
- Register versus code (sigs): I73(a) said `client_baseline=None` while the code default is `True`, and a register note said the `compute_finance` extras "have no register entry". **Both fixed in the current tree** (I73(a) now reads `client_baseline=True`; the stale note is gone). `docs/adr/ADR-002-worlds-and-ranges.md` still stated the superseded "lo/hi trace leaf results only" rule; **fixed** (it now cites I62). I62 itself still contradicts spec 2.6 on purpose (all three worlds are traced in full, justified by IC2); it is acknowledged in the register and stays a documented register-versus-spec deviation.
- Signatures documented only in docstrings (sigs): `eligibility_shares` (`family`, `low_share`), `breakeven` (`scenario_id`), `build_profile` writing nothing, the file names `finance/build.py` and `engine/trace.py`, the `data/synth/generator.py` shim. **Registered in I84** after audit; code unchanged.
- Still open (sigs): the F8b functions are annotated `RunContext | Project` but a `Project` raises `ConfigError`; `select_design_day` and `derive_inbound` type `catalog` as optional but require it; the section 2.5.1 `pessimistic_end` inference differs from the spec wording (eur and kWh checked before `/h` and `/m2`, a missing value is inferred, a contradiction only warns) and is documented in the function docstring and `docs/audit/F5.md` but not in the register; `joblib` is declared and never imported (spec: "optional") with no register entry.
- T1.5 golden workbook (trace): values with formula comments, not live Excel formulas; registered (golden-case notes). The Dev B review of the workbook is a human step, not evidenced.

Numbers (not skeptic-tested): the Delta-stock term of F4 (OLS slope of 23 inventory snapshots, 19.45 units/day, +0.73 % inbound) is applied but the I12 register text describes only the fewer-than-3-snapshots case; labor is priced on productive hours (S0 y1 23,627.5 h against 17.2975 core FTE x 1607 = 27,798.7 paid hours), which understates paid time by 1 / utilisation; the I76 text lists pods among the `equipment_capex` sensitivity unit costs while the code excludes `per_pod_eur`; `peak_hour_share_inbound` 0.2 (5-hour window) is combined with a peak factor of 1.778 for equipment while labor spreads the same inbound over 8 hours; `seasonality.trend_cagr` is +17.7 %/yr (confidence L) on a series generated with 5 % growth, because the Appendix B OLS on raw monthly means is not de-seasonalised (I52).

Expert (domain judgement, not skeptic-tested): the summary shows three headcounts without definitions (32.4 design-day, 17.3 permanent FTE, 42.6 paid, the last dominated by the I65 floor); key messages quote TCO to the euro (4,696,269) next to a 3.30 to 6.99 MEUR range, and paybacks, heads and areas at typ only, with a payback shown at 0.1-year resolution while the S1 NPV range straddles zero; the Alerts table prints bare numbers (`9,15`, `0,45`, `655,17`) without unit, threshold or action; French wording ("Retour sur investissement (annees)" for payback, "Surcharge" for override, "Colis par commande colis"); capex omits packing benches, conveyors, dock equipment and a WMS licence while baseline capex is 0 (flatters S0 payback); the ICPE regime and the 1510 rubrique thresholds are `[VERIFY]`; on b2b the AMR scenario uses 2,240 m2 of storage (2.2x manual rack) because pods are single level, and replenishment is 6.0 heads.

Security (not skeptic-tested): the Streamlit `resolve_run` (`app/state.py`) accepts any absolute path or `../` path under cwd from `?run=`, not only folders under `WHSIZING_RUNS`; a CR or FF in a client or site name silently removes the PDF running header and footer (`_css_str` in `report/pdf.py` escapes `\`, `"`, `\n`, `<`, `>` but not `\r` or `\f`; `report/pdf.py` was edited at 01:15 and not re-checked); absolute client paths and file names are persisted in `inputs/project.yaml`, `inputs/mapping/*.yaml`, `manifest.json` and `dq/ingest_manifest.json`, and the basename in `source_file` of the parquet files and in `dq_report.*`; a group- or world-readable salt file is accepted silently (`docs/runbook.md` says mode 600) and there is no minimum salt length; the "too big, use the CLI" hint builds a shell command with naive single quoting; an uploaded file named `..` or empty raises an uncaught `IsADirectoryError` (no traversal: writes stay under `runs/.uploads/<sha8>/`); `.gitignore` did not cover salt files, `.env`, `.streamlit/secrets.toml`, `secrets.yaml` or real client data (**fixed in the current tree**: `*.salt`, `salt*`, `.env`, `.streamlit/secrets.toml`, `secrets.yaml`, `/client_data/`); `docs/PILOT.md` understated the non-headless network behaviour (a UDP `connect()` to 8.8.8.8, no data sent) (**updated in the current tree**, lines about `checkip.amazonaws.com` and `8.8.8.8`).

Robust: duplicate header names with conflicting values silently use the first column, with no DQ note; a different salt moves floats by up to 6.3e-15 relative (summation order over hashed SKU ids); a failed (exit 1, 2 or 3) or SIGTERM-killed run leaves a folder with `manifest.json` but no failure marker, and `is_run()` accepts it (it appears in the Streamlit run list); the repository `runs/` folder holds git-ignored leftovers from earlier waves.

e2e: a corrupt `scenarios/<id>/trace.jsonl` makes `report` exit 2 with a multi-line raw pydantic dump (no traceback); the PDF is 18 pages on messy runs, the top of the 12 to 18 page band.

Quality: 3 test files exceed the 800-line project maximum (`test_f10_app_pages.py` 907, `test_f10_cli_e2e.py` 827, `test_f4_register.py` 810; the largest `src` file is 546); 12 `src` functions exceed 50 lines (max `io/ingest.py` `ingest` 76) and 2 reach nesting depth 5; about 12 public callables are reachable only from tests; small duplicated helpers (`_pct` in `calibration/evaluate.py` and `calibration/note.py`, two SHA-256 loops, two parquet-read idioms); 37 `pyright: ignore` in `src` and 52 in tests carry a rule code but no reason, 6 of 20 `ponytail:` comments give no upgrade path; `design/design_day.py` keeps `RATIO_DRIFT_MAX = 0.15` and `SHORT_HISTORY_DAYS = 60` as module constants where sibling constants are in the catalog; `syrupy` is declared and unused (M6); `click`, `markupsafe` and `pydantic_core` are imported but not declared; `logging.py` keeps a module-level mutable `_timings` dict (recorded in `docs/audit/F0.md` as an open low).

### 6.3 Final-auditor observation: the register ran ahead of the code, and the tree moved (not skeptic-tested)

**P1. At the first source check the register described fixes the code did not contain; code then began to land (medium while any claim is unimplemented).** The entries I83 (R1 lower date bound), I85 (negative derived inbound; `engine.max_equipment_count`), I86 (`calibrate` parse-first, `--force`, `--observed-peak-lines-h`), I87 (pint at the parameter layer) and I88 (Annex A scenario values) state behaviour as fact, and the register is the binding record of interpretations. Observed, with local time:

```
01:05 to 01:09 (before any source edit)
$ ls src/whsizing/units.py                      -> No such file or directory
$ grep -rn "max_equipment_count" src catalog    -> (no output)
$ grep -rn "import pint\|from pint" src         -> (no output)
$ grep -n "force\|observed" src/whsizing/cli/sizing.py -> (no output)
$ grep -n -i "negative\|DataQualityError" src/whsizing/design/inbound.py -> unrelated percentile docstring only
$ whsizing run-all .../m1_stray/project.yaml    -> full report; R9 ok "history 1970-01-01 -> 2025-03-31 (662.97 months)", DQ 100.0 usable

01:13:50 (source edits landing since 01:10)
$ whsizing run-all .../m1_stray/project.yaml    -> exit=3, R9 "history 2025-03-01 -> 2025-03-31 (1.02 months); at least 3 months needed"
$ grep -n DataQualityError src/whsizing/design/inbound.py   -> :165 raise DataQualityError(
$ grep -rn max_equipment_count src catalog      -> catalog/models.py:383, engine/queue.py:43, engine/throughput.py:25
$ grep -rn "import pint" src                    -> src/whsizing/units.py:15
$ grep -n -i override src/whsizing/report/tables_data.py    -> :269 def scenario_overrides, :281 "<scenario>: value used" column
$ uv run whsizing calibrate --help | grep -- "--force\|--observed"   -> (no output)
```

By the last snapshot I83 (M2) holds on the one reproduction; the code for I85 (M5, L4), I87 (L6) and I88 (M3) exists but was not exercised by the final auditor (no quantity-1e12 run, no negative-inventory run, no PDF rebuild); I86 (M4) was still absent. Source files kept changing until the last check, and none of it has been through the whole suite. I84 and I89 are accurate: they document deviations that exist. Resolution: let the remediation settle, then re-run the whole suite, ruff, pyright and coverage, and re-audit M2, M3, M4, M5, L4 and L6 against the finished tree. Until then do not treat any of them as closed, and do not let the register claim more than the code does.

## 7. Findings refuted by the skeptic (do not re-report)

1. trace, "zero commits, no CI run, `git_sha` unknown": a property of the delivered working tree, not a defect; register I75 defines `engine_version` and `git_sha` as `unknown` without git or a commit; the `git describe` and dirty logic works in a scratch git copy. (Also robust G2.)
2. trace, "CLI report and exit-5 tests run on stubbed builders": the real `report_cmd` path is covered by `test_T10_4_page_6_builds_the_real_excel_and_pdf_and_offers_them` (no fakes, `1 passed`) and a live `run-all` and a live exit 5 behave; weak test strength is not a defect.
3. trace, "expert reviews and sign-offs not done" as a medium defect: the catalog ships TODO / L by design (spec Appendix C); validation is a human step (spec section 8, T11.4). Recorded instead as DoD item 8 and in section 9.
4. e2e, "cm-instead-of-mm on 30 % of rows passes ingest silently": the code follows spec F2 step 6 (P95 length below 100 means cm, with `W_UNITS_DIMS`); a mixed column keeps a normal P95; nothing in the spec or tests requires row-level detection. (Skeptic on b2b_cases: 31.2 % of canonical lengths below the clean minimum, no `W_UNITS_DIMS`, ingest exit 0, "usable with caveats".)
5. numbers, "annualisation uses `operating_days_per_year` 252 while the data has 313 operating days a year": prescribed by I4 and I36 and spec F6c, with an explicit client-supplied `[P]` basis parameter that is traced and printed on the Design basis sheet; a warning would be an enhancement, not a defect (skeptic: with only `operating_days_per_year` set to 313, TCO moves from 4,696,269 / 5,717,996 / 6,457,090 to 5,676,299 / 6,468,221 / 7,167,828). Same as expert TOP-6.
6. numbers, "temp hours are counted twice (I33)": the literal spec F7 formula (lines 1101 to 1102 with F6c lines 975 to 980), registered as I33 and listed as an open expert ruling. Size for the reader: S0 437.6 kEUR (9.3 % of typical TCO), S1 235.2 kEUR (4.1 %), S2 221.2 kEUR (3.4 %).
7. expert TOP-1, "headline paybacks are against a client-current baseline that is 2.1x the tool's optimised manual labor": the spec defines the baseline from the client's current operation and `actual_fte` (section 1.2, F7, Appendix E); registered in I73(b) and I42; the runbook says so. For the reader: client_current gives S0 NPV about 3,134 kEUR and S1 and S2 paybacks of 2.0 and 2.8 years; with `baseline: S0` S1 and S2 NPV are about -1,022 and -1,761 kEUR with no payback.
8. expert TOP-2, "I33 not disclosed in the client report": same as item 6; the spec section 8 limitations box lists fixed text and generated counts only. (Includes the receipts-mode amplification, I64: b2b S1 19.6 % of TCO.)
9. expert TOP-3, "`F_UNSTABLE:packing` in every scenario (I69)": the spec-literal sizing (pack stations on the peak hour, queue arrival on the SLA-bound rate) yields offered load 9.15 against 6 servers and `c_min` 11 and says so in the flag message; registered in I69 and an open expert ruling.
10. expert TOP-4, "cube AS/RS sized with 8 ports and 35 robots at 0.45 robots/m2": the robot and port formulas are the spec's; the density is flagged (`F_ROBOT_DENSITY`, I46) and the decant coincidence is I23; domain realism of the spec's own formulas is not an implementation defect.
11. expert TOP-5, "manual picking productivity and zone split overstate S0 labor": the class rule by stock cube (F6a), the pick rates and the catalog values are the spec's; the 1.5 to 2x estimate is the expert's own.
12. expert TOP-6, "annual volume 18 % below observed": same as item 5.
13. expert TOP-7, "percentile sweep shows TCO nearly flat while heads rise": spec-mandated (annual hours from the daily series, T6.10, peaks paid through temp hours; the sweep columns are the spec's).

## 8. Traceability matrix summary

- Spec ids with no test: none among T0.1 to T11.4 (508 named test definitions, 799 node ids, all executed).
- Spec items outside the T-ids with weak or no automated evidence: C3 syrupy golden and comparison snapshot (M6); C5 bench coverage (L1); C1 manifest at every stage in the staged CLI (6.2, now registered in I89); F3 eight charts in a PDF (6.2); pint unit check (L6); every human sign-off (DoD 8, F1 Dev B review, F2 business-lead readability, F5 initials, F6 worked examples, F9 human reproduction trial, F11 review #2).
- Weak tests (pass, but weaker than the spec wording): T0.1 (the workflow structure is checked; CI has never run); T0.5 (Docker variant skipped); T1.4 (run on a 120-day ecom_mid FR export, not tiny_golden, because R9 blocks it); T1.5 and G1 (the golden workbook holds values with formula comments, not live formulas; registered); T2.9 (synthetic messy fixtures); T5.3 (silent in-body skips); T6.6 (labor-stage scope, not the full `size_scenario`); T6.10 (31-day golden series); T9.2 (equality with `comparison.json`, no snapshot); T10.1 (243-day site, not tiny_golden; registered in I84 after audit); T10.3 exit 5 (the CLI tests stub the builders; the real exit 5 is proven live and by T9.4); T11.1 (synthetic actuals produced by the model's own predictor).
- Legitimate skips: T0.5 Docker-image variant (`Docker not installed`) and T11.4 real pilot (`@pytest.mark.skip`, needs real data and expert acceptance). The earlier run's third skip is unexplained (section 4).

## 9. Not provable here, and open rulings

### 9.1 Not provable here

- Docker: image build, `docker-smoke`, `just docker-demo` and the T0.5 in-image render (Docker not installed).
- GitHub CI: the six-stage workflow has the right structure (T0.1 structure tests pass) but has never run; there is no commit and no remote. "CI green on main" and CI-runner C5 timings are not observable.
- Real client data: T2.9 on a real file (DoD 1), T11.4 and the hold-out error on one real site (DoD 6). The synthetic hold-out proves plumbing only.
- Expert reviews #1 and #2 (DoD 8), the F5 expert initials, F6 worked-example review, F11 review #2, the Dev B review of the golden workbook, business-lead readability of the DQ report, a human trial of reproducing three summary numbers.
- Excel and LibreOffice rendering of the workbook (only structural openpyxl checks: 12 sheets, 0 error cells, numeric cells numeric) and PDF visual layout (poppler absent, text layer only).
- Spec fonts: Liberation and DejaVu are not installed; the PDFs embed Verdana, so pagination with the spec fonts is unverified (17 to 18 pages here, top of the 12 to 18 band).
- Hosted mode (C6): out of the POC (`docs/PILOT.md` states it); the app was only checked for no network use and, after M1, for loopback binding.
- Interactive Streamlit pages 1 to 5, `just bench` on an unloaded runner, quantity 1e12 on every line, hostile xlsx inputs and hostile calibrate inputs.
- Git provenance: `git_sha` is `unknown` on this tree; the dirty-flag logic was checked in a scratch git copy only.
- The behaviour claimed by I83 and I85 to I88 on the moving tree: partly implemented since 01:10 (6.3) and not audited; I86 was still absent at the last check.
- The third skip of the earlier suite run.

### 9.2 Open `[EXPERT]` / `[VERIFY]` rulings of the register (nothing here is a defect)

From the register's "Open expert rulings" (checked by `tests/golden/test_g1_expert_rulings.py`, which passed at the 01:09 check): I33, I46, I48, I53, I54, I64, I65, I67, I69, I76, I73.
- **I33**: labor cost counts temp hours twice (literal F7); golden S0 and S2 hold the literal value.
- **I46** `[EXPERT]`: value of `cube_asrs.max_robots_per_m2` (0.05, no spec value); S2 raises it at about 0.47 robots/m2.
- **I48** `[EXPERT]`: whether a degenerate cube scenario (zero eligible lines) carries the manual WMS adaptation and manual software.
- **I53** `[EXPERT]`: R13 outlier threshold `median + 10 x max(MAD, 1)` and the MAD floor.
- **I54** `[VERIFY]`: amendment W3 to the decimal sniff (thousands shapes, decimal-comma evidence, delimiter tie-break).
- **I64** `[EXPERT]`: with lumpy receipts, receipts-mode inbound hours sit above the P50 day and temp hours dominate (b2b S1 typ 9,903 of 14,519 h; the expert dimension measured 9,914 of 14,615 h).
- **I65** `[EXPERT]`: the floor of 1 head per staffed activity applies per shift (about +4 heads on ecom_mid S0 with 2 x 7 h).
- **I67** `[VERIFY]`: in a `;` file with comma decimals elsewhere, a dot 3-decimal weight (`1.250`) is read x 1000 with no DQ signal.
- **I69** `[EXPERT]`: whether F6d should size pack stations on the same arrival rate as the F6e queue check instead of reporting `F_UNSTABLE:packing` with `c_min`.
- **I76** `[EXPERT]`: the F8b parameter definitions (equipment_capex, picking_productivity) and the break-even bracket `[0.3, 3]`.
- **I73** `[EXPERT]`: the amr_gtp capex formulas and the `A_storage` choice for floor preparation; the client-current baseline (labor only, biased towards the current operation).

## 10. Prioritised fix list (confirmed findings and the observation)

Before any client-facing pilot:
1. **P1** Let the remediation settle, then re-run the whole suite, ruff, pyright and coverage on the finished tree and re-audit M2, M3, M4, M5, L4 and L6. Read the R1 change (I83) against clean data first: its claim "no clean dataset is affected" needs the ecom_mid and b2b_cases e2e tests. Land I86 (M4) or withdraw it: it was still absent at the last check, and the register must not claim more than the code does.
2. **M2** Keep the test with one 1970-01-01 line on a 31-day file that must stay exit 3 (the final auditor's one reproduction exits 3 at 01:13:50), and a test that a clean dataset is unchanged.
3. **M3** Rebuild a PDF and check that Annex A prints 230 for S1; keep the test that pins every Annex A value to the `params_snapshot` of the scenario it is quoted for (I88).
4. Expert review #1 (catalog and formulas) signed, then T11.4 on one real site and review #2 (DoD 6 and 8), per `docs/PILOT.md` section 4.3.

Next:
5. **M4** (open at the last check) Make `calibrate` parse first and copy to `calibration/` only on success; refuse to overwrite without `--force`; add `--observed-peak-lines-h` (I86). Keep the exit codes.
6. **M5** (cap appeared after the first check) Exercise it with the quantity-1e12 case: the run must stop with a clear `SizingInfeasibleError` (exit 4), not run for minutes (I85 b); log progress in long stages.
7. **M6 and L1** Freeze a syrupy snapshot of the ecom_mid `comparison.json` (and the tiny_golden golden layer), repoint `just golden-update` at the real regeneration, and put the profile, sensitivity and report budgets under the `bench` marker.

Then the lows:
8. **L4** (guard appeared after the first check) Exercise it with the 1e12 first-snapshot inventory case: `DataQualityError`, exit 3, on `run-all` and on staged `size` (I85 a).
9. **L5** Wrap `find_canonical` filesystem errors as `ConfigError` (exit 2).
10. **L6** (code appeared after the first check) Confirm that the pint registry accepts all 72 catalog units (50 of 72 were not parsable by default pint at audit time) and that a bad unit is rejected with a clear `ConfigError` (I87).
11. The remaining items of section 6.2, in this order: staged `manifest.json` per stage or accept I89 as is; the `RunContext | Project` annotations and the optional-but-required `catalog` arguments; a register entry for the 2.5.1 inference rule and for `joblib`; the three oversized test files; the silent `pytest.skip` branches in T5.3; the four F3 charts that never reach a report.

Done since the audit and verified by the final auditor (by reading or running, as stated above): **M1** loopback bind (config, `justfile`, `docs/PILOT.md`, static test, live check); `.gitignore` salt and secret patterns; the I73(a) default and the stale register note; the ADR-002 wording; registration of the T10.1 substitution, the `write_canonical` signature and the C1 staged-flow deviation (I84, I89). One reproduction of M2 now exits 3. Landed after the first check and not audited: the code for M3, M5, L4 and L6.

---

## 11. Resolution addendum (written by the lead after the fix wave W8; the body above describes the tree as audited)

**How to read this file.** Sections 1 to 10 are the independent audit of the tree as it stood at
audit time. Per-feature files in `docs/audit/*.md` are point-in-time records: later waves supersede
their open-issue lists. This addendum and the register (`docs/INTERPRETATIONS.md`, I1 to I90) are
current.

### 11.1 Final tree figures

- `uv run pytest --cov=whsizing` with no marker filter (bench, slow and snapshot tests included):
  **2017 passed, 2 skipped, 0 failed**, 18 min 1 s. The two skips are the Docker-image variant of
  T0.5 (Docker not installed) and T11.4 (real pilot data and expert acceptance).
- Coverage: **98 %** over `src/whsizing` (10 741 statements, 170 missed); `engine/` and `finance/`
  **99 %** (1 476 statements, 10 missed; the CI gate is 80 %).
- `ruff check`, `ruff format --check` and `pyright`: no findings (270 files formatted).
- Correction to section 4 and section 8: the earlier non-bench, non-slow run was **1747 passed,
  2 skipped, 1 failed** (a test that hashed `keep_descriptions` into the expected project hash after
  a manifest change); it was fixed before the audit started. The lead's facts string said "3
  skipped", which was wrong: there was no third, unexplained skip.
- Smoke after the fixes (scratch folder, no repo writes): `synth` then `run-all` on ecom_mid exit 0
  in 18.8 s; `rerun` with the salt unset gives byte-identical `result.json`, `finance.json`,
  `trace.jsonl`, `comparison.json`, `sensitivity.json` and `design_day.json`; PDF 17 pages with the
  run id, no `{{ missing` sentinel and the "indicative study" banner; workbook 12 sheets;
  `manifest.json` has `project_hash` and 145 `params_snapshot` values; `just demo` exit 0 in 22 s.

### 11.2 The "unaudited tree" observation (P1)

The record agent noted that the register entries I83 and I85 to I88 were ahead of the code at its
first check and that edits were still landing. The three lean audits of W8 are the re-audit it asked
for: `docs/audit/R8a.md`, `R8b.md`, `R8c.md` (each with an independent auditor and up to two fix
rounds), followed by the full run above. Headline proofs captured there: tiny_golden plus one
1970-01-01 line still exits 3 through R9 (it used to exit 0 with DQ 100); 50 lines of quantity 1e12
stop with exit 4 in 2.8 s (they ran for minutes); a failed re-calibration leaves `calibration/`
byte-identical (checksum unchanged); Annex A prints `Surcharge 230` for the S1 override; five tests
are collected under `bench`; a mutation of one catalog value fails the golden-layer snapshot.

### 11.3 Per-finding resolution

| Finding | Resolution |
|---|---|
| M1 Streamlit binds all interfaces | **Fixed.** `.streamlit/config.toml` and `just app` set `127.0.0.1`; a static test pins both; PILOT.md corrected (including Streamlit's UDP lookup). |
| M2 stray 1970 date defeats R1/R9/R10/R12 | **Fixed, with registered limits.** I83: gap rule on the earliest distinct dates. Limits (upgrade path: a per-client `history_start`): a junk cluster above 5 % of the distinct dates that is also isolated by more than 90 days stays; a real early block up to 5 % before a closure of more than 90 days is dropped; a stray date within 90 days before the first real date is kept. |
| M3 Annex A base value instead of override | **Fixed** (I88); a test pins every Annex A value to `params_snapshot`. |
| M4 calibrate copies inputs before parsing | **Fixed** (I86, I90 c): stage-and-swap, `--force`, `--observed-peak-lines-h`. |
| M5 unbounded Erlang-C loop | **Fixed** (I85 b): `engine.max_equipment_count` = 100 000; exit 4 naming the resource. The bound is not applied to docks. |
| M6 no syrupy snapshots | **Mostly fixed.** Two snapshots (ecom_mid `comparison.json`, golden-layer key table), `just golden-update` repointed, a mutant is caught. Not proven: independence of the snapshot from the salt (the fixture pins the salt). |
| L1 bench marker 2 of 5 | **Fixed**; the three budgets now run under `just bench` and the CI bench job only, not under `just test`. |
| L2 T10.1 on a 243-day site | **Registered** (I84). |
| L3 `write_canonical` signature | **Registered** (I84). |
| L4 negative derived inbound | **Fixed** (I85 a): `DataQualityError`, exit 3. |
| L5 too-long out_dir exits 1 | **Fixed** (exit 2). |
| L6 pint unused | **Fixed** (I87): `whsizing.units`, `Param.unit` validated; every catalog unit parses; `lines/0` and `m ** m` are rejected with exit 2 naming file, id and unit (probe and test added by the lead). |
| Unconfirmed lows of 6.2 | Mostly fixed or registered (I83 to I90); see the list below for what remains. |

### 11.4 Open items W8 introduced or left (none changes a number on well-formed input)

- R1 gap-rule false negative and false positive (the limits in I83, above).
- `app/state.py resolve_run` and `restore` still accept an arbitrary path from `?run=`; the seven pages
  are guarded by `app/entry.py`, a direct caller of the functions is not.
- Scenario names reach the Excel report unsanitised (control and bidi characters show); some Unicode
  format characters in a scenario name still garble the PDF text layer; a lone surrogate in a name
  fails in the scenarios stage with exit 1.
- `report/data.py`, `Tracer.load_jsonl` and the app still surface a raw pydantic error for a corrupt
  `trace.jsonl`; only the CLI has a pre-check.
- i18n `dq.rule.R1` text (`en.yaml`, `fr.yaml`) still says "not in the future" only.
- `calibrate` into an unwritable run folder ends as exit 1; staged `compare` and `report` after an
  all-not-computed run still exit 0 and build an all-not-computed output; progress logging in long
  stages (sensitivity sweep) was not added.
- Two test files are above the 800-line maximum (`tests/e2e/test_f10_cli_e2e.py` 827,
  `tests/unit/test_f4_register.py` 810).
- **I90 (b) is a deviation from §2.7** (exit 4 without `--strict` when no scenario is computed). It is
  registered and listed as an open `[VERIFY]` ruling; revert it to exit 0 plus a not-computed report if
  the spec owner prefers.

### 11.5 Verdict

**`ready_with_conditions`, unchanged.** The code, tests and documents are consistent on the tree
above. The conditions are human steps and cannot be closed by this repository: the catalog is 72 of
72 parameters with source TODO and confidence L (`validated_by` empty); expert review #1 (catalog and
formulas), a back-test on one real site (T11.4, DoD item 6) and review #2 (DoD item 8) are not done;
the open `[EXPERT]` and `[VERIFY]` rulings (I33, I46, I48, I53, I54, I64, I65, I67, I69, I73, I76,
I90) need a decision. Not provable here: Docker and the container form of `just docker-demo`, GitHub
CI (no commit, no remote, `git_sha` unknown), real client data, Excel and LibreOffice rendering, the
spec fonts (Verdana is embedded), hosted mode (C6).
