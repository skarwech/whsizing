# DOC audit record: methodology, runbook, PILOT, README quickstart, assumptions regeneration

Feature DOC (spec §6 C1-C6, §3 tooling, Appendix B and E). Owned paths: `docs/methodology.md`,
`docs/runbook.md`, `docs/assumptions.md`, `docs/PILOT.md`, `README.md`. Record written 2026-11-09 from
the build report, two audit rounds, and a fresh test run made while writing this file.

## Final verdict: pass_with_issues

- The gating tests (`tests/unit/test_f0_*.py`, `tests/unit/test_f5_*.py`) pass in the fresh run (251 passed, 1 skipped for Docker, 0 failed), and `docs/assumptions.md` is byte-identical to the generator output. The two spec audits (round 0 and round 1) found no high-severity issue, and the doc content (numbers, commands, exit codes) reproduced when auditors ran it.
- It is not a clean pass. Two DOC-side low findings from round 1 (no `pre-commit install` in the README, incomplete `run-all` option list) and the deferred runbook-placement finding are still open, because no fix round followed round 1. The root causes of the Docker and `just demo` problems (F0/CI files) and one F8 test failure are outside DOC's paths and are only documented, not fixed.

DOC has no acceptance-test ids of its own (spec defines none for documentation). It is gated by the F0 and F5
tests that the docs quote or depend on, and by the manual and scripted checks under "Proofs". No test checks the
prose of methodology, runbook, PILOT or README. `tests/` is outside this feature's paths, so none was added.

## Tests and T-ids

DOC owns no T-ids. The rows below are the tests the task assigns to DOC (`test_f0_*`, `test_f5_*`), statuses from
the fresh run in this document. The first five rows are the ones the docs directly lean on.

| T-id | test function | status | what it proves |
|---|---|---|---|
| C4 (assumptions generated from the catalog) | `test_f5_loader.py::test_docs_assumptions_md_is_regenerated` | pass | `docs/assumptions.md` text equals `render_assumptions_md(catalog)` exactly, and contains the `cube_asrs.port_rate_lines_h` row `250 / 350 / 450 / min / TODO / L`. A real equality check: any catalog change without regeneration fails it. |
| C4 (catalog id rule cited in methodology §4, §11) | `test_f5_loader.py::test_shipped_ids_follow_the_readme_rule` | pass | The ids named in the spec (Appendix E overrides, §2.5 example, labor, finance, engine) exist in the shipped catalog, and the `max_levels`-style constants have the documented values. |
| T0.1 | `test_f0_tooling.py::test_T0_1_justfile_has_every_section_3_2_recipe` | pass | Every §3.2 recipe exists in the justfile; the README and runbook name them. |
| T0.1 | `test_f0_tooling.py::test_T0_1_ci_workflow_has_the_six_stages_in_order` | pass | The CI workflow has the six §3.3 stages in order. |
| T0.1 | `test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[ruff-check]`, `[ruff-format]`, `[pyright]` | pass (see note) | Project-wide ruff and pyright gates return 0. Note: `[pyright]` failed once during the build (see Open issues, item 6); it passes in the fresh run. |
| T0.2 | `test_f0_cli.py::test_T0_2_version_cli_runner`, `::test_T0_2_version_console_script` | pass | `whsizing --version` prints the version through the CliRunner and through the installed console script (README and runbook quote `whsizing 0.1.0`). |
| T0.3 | `test_f0_schemas.py::test_T0_3_schema_json_round_trip` (59 cases), `::test_T0_3_every_exported_model_has_an_example` | pass | Every exported schema model round-trips through JSON and has an example. |
| T0.4 | `test_f0_schemas.py::test_T0_4_param_min_greater_than_typ_raises` | pass | A `Param` with min > typ is rejected. |
| T0.5 | `test_f0_report.py::test_T0_5_mock_result_renders_one_page_pdf` | pass | A mock result renders a one-page PDF locally (WeasyPrint). |
| T0.5 (Docker form) | `test_f0_report.py::test_T0_5_docker_image_renders_one_page_pdf` | skipped | `skipif(docker is None)`: Docker is not installed here. |
| T5.1 | `test_f5_loader.py::test_T5_1_*` (25 cases: malformed fixtures, non-finite values, missing and unknown files, non-UTF8, `max_robots_per_m2` shape) | pass | The catalog loader rejects each malformed fixture with a `ConfigError`. |
| T5.2 | `test_f5_eligibility.py::test_T5_2_orientation_agnostic` | pass | Eligibility does not depend on the orientation of the item dimensions. |
| T5.3 | `test_f5_eligibility.py::test_T5_3_golden_eligibility_shares` | pass | Eligibility shares match the golden values; methodology §4 quotes 0.8974 and 0.7411 (checked against `golden_values.json`). |
| T5.4 | `test_f5_eligibility.py::test_T5_4_missing_dims_ineligible_unless_flag`, `::test_T5_4_missing_dims_ineligible_whatever_the_limits`, `::test_T5_4_assume_flag_never_overrides_a_known_violation` | pass | SKUs without dimensions are ineligible unless the assume flag is set, and the flag never overrides a known violation. |
| T5.5 | `test_f5_loader.py::test_T5_5_*` (36 cases) | pass | Pessimistic-end inference for an absent range end, a rejection when a unit has no rule, and a warning on contradiction. |
| (R6, I75j, paramset) | `test_f5_r6.py`, `test_f5_paramset.py`, rest of `test_f5_loader.py` and `test_f5_eligibility.py`, `test_f0_config.py`, `test_f0_trace_logging.py` | pass | Catalog validation reports every broken file; overrides and three-world resolution; config loading; Tracer JSONL and tree. Cited by the methodology. |

Totals, fresh run: 251 passed, 0 failed, 1 skipped.

## Fresh test output

Command, run from `/Users/skarwech/saas_v1` while writing this record (2026-11-09):

```
uv run pytest tests/unit/test_f0_*.py tests/unit/test_f5_*.py -q -rA
```

Output, trimmed to the relevant lines (the full run lists 251 `PASSED` lines):

```
..................s..................................................... [ 28%]
........................................................................ [ 57%]
........................................................................ [ 85%]
....................................                                     [100%]
==================================== PASSES ====================================
PASSED tests/unit/test_f0_cli.py::test_T0_2_version_cli_runner
PASSED tests/unit/test_f0_cli.py::test_T0_2_version_console_script
PASSED tests/unit/test_f0_report.py::test_T0_5_mock_result_renders_one_page_pdf
PASSED tests/unit/test_f0_schemas.py::test_T0_4_param_min_greater_than_typ_raises
PASSED tests/unit/test_f0_tooling.py::test_T0_1_ci_workflow_has_the_six_stages_in_order
PASSED tests/unit/test_f0_tooling.py::test_T0_1_justfile_has_every_section_3_2_recipe
PASSED tests/unit/test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[ruff-check]
PASSED tests/unit/test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[ruff-format]
PASSED tests/unit/test_f0_tooling.py::test_T0_1_lint_and_typecheck_gates_pass[pyright]
PASSED tests/unit/test_f5_loader.py::test_shipped_ids_follow_the_readme_rule
PASSED tests/unit/test_f5_loader.py::test_docs_assumptions_md_is_regenerated
PASSED tests/unit/test_f5_r6.py::test_R6_3_a_missing_catalog_folder_is_one_error
SKIPPED [1] tests/unit/test_f0_report.py:28: Docker not installed
251 passed, 1 skipped in 12.27s
```

Other facts checked fresh in the same session:

- `uv run python -m whsizing.catalog.assumptions catalog <scratch>/assump_regen.md`, then `diff -q docs/assumptions.md <scratch>/assump_regen.md`: no difference (IDENTICAL).
- `grep -c 'TODO (F' docs/methodology.md docs/runbook.md docs/PILOT.md README.md`: 0 in each file. No stub remains.
- `uv run pytest tests/unit/test_f8_r5_runner.py -q`: `1 failed, 22 passed`. The failure is `test_I75_b_the_manifest_carries_the_sha256_of_the_normalised_project` (F8, see Open issues, item 5). It is not in DOC's gate and DOC did not touch it.
- Current size of the delivered files: methodology 800 lines, runbook 713, PILOT 327, README 64, assumptions 160.

## Proofs

All proofs below except where marked were captured by the auditors during the audit rounds, not re-run for this
document. Where the audit data was clipped, the excerpt ends with an ellipsis. Scratch folders and run ids vary
by run; the figures are the ones quoted.

1. **README quickstart works from a clean mirror.** Captured in round 0 and again in round 1 (clean copy with no `data/generated`).
   Command: `whsizing synth data/synth/profiles/ecom_mid.yaml; WHSIZING_SALT=choose-a-secret whsizing run-all project/example_project.yaml; ls runs/*/report`.
   Output (round 0): `exit=0`, run-all 19.087 s total; comparison table S0/S1/S2; `Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2`; report folder holds `diagram_S0.svg diagram_S1.svg diagram_S2.svg report_fr.pdf report_fr.xlsx trace.jsonl`. Round 1: synth 2.57 s, run-all exit 0 in 18.7 s.
2. **The runbook's staged flow reproduces its pasted outputs.** Captured in round 0 and again in round 1.
   Commands: ingest x4, `profile`, `basis init`, `size`, `compare`, `report`, `run-all`, `env -u WHSIZING_SALT whsizing rerun`, `shasum -a 256 .../scenarios/S0/result.json`.
   Output (round 0): run folder suffix `35a39c`; `score 100.0 usable ... R4 order_lines info 3783`; `design_day lines 632.17`; S1 flags `['F_SCALE_LOW','F_ROBOT_DENSITY','F_LOW_CONFIDENCE:49']`; PDF pages 17; 12 workbook sheets (Summary ... Methodology); `result.json` sha256 `42ad3cbba26a2720b83aac8927238e36bbed95979b39e40ba5bf24f33dfe9bfe` for both the original run and the rerun without salt. Round 1: same suffix `2026-11-09T21-58-39_35a39c`, S0 TCO 1,093 [751-1,674], 17 pages, 12 sheets.
3. **Methodology worked numbers match `golden_values.json` and an independent recomputation.** Captured in round 0 and round 1 by separate scripts.
   Output (round 0): design day `137.48177797120002`, peak hour `18.80092690204445`; cost per line `6.632369061473322` vs golden `6.632369061473321`; NPV recompute `-391617.13384016836` vs golden `-391617.1338401684`; `erlang_c(1,.5)=0.5`, `erlang_c(2,1)=0.3333`; 70 golden keys cited in the methodology, all found. Round 1 (hand calculation script): `ALL OK` for growth 1.21665, lambda_sla 23.56830, rack positions 67.76471, S0 capex 135173.85498, delta_cf0 -282430.02926, `W_q(S0 packing)=0.01823 h`. One value differs beyond the last digits (`pack_rate 37.23159 vs golden 37.23077`, relative difference about 2e-5); the auditor still reported ALL OK, and the audit data does not state the tolerance used.
4. **Runbook failure modes reproduce with the documented exit codes.** Captured in round 0.
   Commands: tamper `scenarios/S0/trace.jsonl` then `whsizing report <run> --lang en --formats pdf`; `run-all` with no inventory and `options.strict true`; short history; missing salt; unmapped sku; salt file inside a git repo.
   Output: exit 5 on the tampered trace (`error: 2 integrity check(s) failed / IC1 summary/comparison/total_area/S0.typ: cell value 534.389926305071 differs from trace node S0.area.total: 584.389926305071`) and no `report/` folder created; strict exit 4 (`strict: required input(s) missing: inventory ...`); R9 exit 3 (`history 2024-01-01 -> 2024-02-29 (1.97 months); at least 3 months needed`); missing salt exit 2; unmapped column exit 2; salt in a git repo exit 2 (`is inside a git repository`); rerun with an edited project exit 2 ...
5. **Calibration demo and Tracer tree script run unchanged; `assumptions.md` is byte-identical to the generator.** Captured in round 0.
   Commands: `python make_actuals.py` (extracted verbatim from the runbook); `whsizing calibrate <run> --actuals actuals.csv --activity-map activity_map.yaml`; `python tree.py <run> S2.equipment.ports`; generator to scratch then `diff`.
   Output: `calibration accepted: hold-out MAPE 0.8 %, peak-month error -0.5 %`; `S2.equipment.ports = 2 - [ceil(port_load)] / S2.equipment.port_load = 1.157 ports [lambda_e / (port_rate x oee) + decant_port_load_peak_h]`; `IDENTICAL`; raw ids (`CMD-`, `ART-`) absent from `dq/` and `ingest_manifest.json`.
6. **The Docker gap is real and the runbook describes it accurately.** Captured in round 1 on a copy without `data/generated`.
   Commands: `env -u WHSIZING_SALT whsizing run-all project/example_project.yaml`, then with `WHSIZING_SALT=x`, then `ls runs`.
   Output: `error: no anonymisation salt: set $WHSIZING_SALT or pass a salt file kept outside the repository` (exit 2); with a salt, `error: .../data/generated/ecom_mid/csv_en/order_lines.csv: cannot read file (No such file or directory)`; `ls: runs: No such file or directory`. The replacement command in the runbook (`synth` then `run-all` in one shell) was run by the DOC engineer with the local `whsizing` (exit 0, PDF and xlsx produced); the `docker run` form itself was not run.
7. **Runbook behaviours checked against the CLI.** Captured in round 1.
   Output: `rerun` without salt exit 0; after editing `inputs/project.yaml`, `error: rerun: inputs/project.yaml differs from the run's manifest (project_hash)` exit 2; `size` twice: `already sized and runs are immutable` exit 2; `basis init` twice: `exists: remove it or choose another --out` exit 2; `compare` on an unsized run exit 2; `calibrate` (24 months): `calibration accepted: hold-out MAPE 0.8 %, peak-month error +1.4 %`.
8. **Round 0 fixes verified.** Captured in round 1. `calibrate` with a missing month row exits 3 (`actuals: 'reception' has no row for ['2024-05']: add a row with hours 0 for none`), header-only file exit 3, non-numeric hours exit 3, nonexistent file exit 2; the headless Streamlit lookup claim in PILOT §2.1 agrees with `streamlit/web/bootstrap.py` (the external-IP lookup runs only in the headless branch when no server address is set); no single "catalog 0.2.0" remains in the docs.
9. **Build-time end-to-end run, twice from clean scratch folders.** Captured by the DOC engineer. The whole runbook flow ran on a small synthetic dataset (1500 SKUs, 400 days, 150 orders/day). Outputs diff to zero after normalising timestamps and hashes; exit codes were 17 x 0, 3 x 2, 1 x 3, 1 x 4. About 60 worked numbers were recomputed from `golden_values.json` by an independent script. The runbook heredoc scripts (`make_actuals.py`, `tree.py`, `scenarios.yaml`) are byte-identical to the ones the demo script ran.
10. **`docs/assumptions.md` equals the generator output.** Captured in rounds 0 and 1 and re-checked in this session (`diff -q`: no difference). 72 ranged parameters (manual_p2p 19, amr_gtp 20, cube_asrs 21, labor 9, finance 2, engine 1) and 71 structural constants; `whsizing validate-catalog catalog` reports `72 parameters, 3 families, 72 with source TODO`.

## Audit rounds

Each round had two audits: a spec audit (checks against the spec and the code) and a proof audit. In both rounds
the proof audit returned `pass_with_issues` with no findings and no proofs recorded; all findings below come from
the spec audits. The build itself (before round 0) delivered the five files and recorded two blockers (item 6 of
Open issues and the absence of any missing dependency).

### Round 0 (spec audit: pass_with_issues, 251 passed, 0 failed)

| # | severity | finding | resolution (round 1 fix) |
|---|---|---|---|
| 1 | medium | `just docker-demo` cannot succeed: the image has no `data/generated` (`.dockerignore`), and the recipe passes no salt. Root cause in F0/CI files. | Fixed on the DOC side: runbook §1 and README now state that the recipe does not work as written, name both causes and the CI `docker-smoke` gap, and give a replacement command. Root cause not fixed (not DOC's files); carried to Open issues. |
| 2 | low | `just demo` is still the F0 walking skeleton (stub PDF), not the §3.2 demo. | Fixed on the DOC side: runbook §1 and README say so and point to the quickstart. The justfile is F0's; carried to Open issues. |
| 3 | low | PILOT §2.1 said only `uv` needs the network; headless Streamlit calls `checkip.amazonaws.com`. | Fixed: PILOT §2.1 documents the exception, the mitigation (`--server.address 127.0.0.1`) and that `just app` is not headless. Verified against the Streamlit source with a stub probe; a live headless start was not repeated. |
| 4 | low | C4 says the runbook includes the data request and review checklists; they are in PILOT.md, the runbook cross-references them. | Deferred: placement only, the content is complete and faithful in PILOT §1, §2, §4. Duplicating would create two copies to keep in sync. |
| 5 | low | `calibrate` with a missing month row exits 3, undocumented. | Fixed: runbook §4 exit-3 row lists the calibrate cases. |
| 6 | low | "at catalog 0.2.0" is wrong: the shipped versions are `manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0`. | Fixed in methodology and PILOT §3.5; `docs/assumptions.md` regenerated and the F5 equality test passes. |

### Round 1 (spec audit: pass_with_issues, 251 passed, 0 failed)

The audit confirmed findings 1 (DOC side), 2 (DOC side), 3, 5 and 6 as resolved. New or remaining findings:

| # | severity | finding | resolution |
|---|---|---|---|
| 1 | low | Round 0 finding 4 still open (runbook cross-references PILOT instead of containing the data request and checklists). | Deferred (unchanged). |
| 2 | low | README setup omits `uv run pre-commit install` listed in §3.2 "Local setup". | Open: no fix round after round 1. Still absent in README and docs at the time of writing. |
| 3 | low | Runbook list of `run-all` options is incomplete: `--non-interactive`, `--no-strict` and `rerun --out-dir` are not listed. | Open. At the time of writing `--non-interactive` appears only in the `ingest` section. |
| 4 | medium, not a DOC defect | `just docker-demo` and CI `docker-smoke` still cannot succeed (no salt, no synth step, `data/generated` excluded). | Not fixable by DOC (justfile, Dockerfile, `.dockerignore`, workflow belong to F0/CI). Documented. |
| 5 | low, not a DOC defect | `just demo` is still the walking skeleton. | Not fixable by DOC (F0). Documented. |
| 6 | medium, not a DOC defect | `tests/unit/test_f8_r5_runner.py::test_I75_b_the_manifest_carries_the_sha256_of_the_normalised_project` fails: `project_hash()` now drops `options.keep_descriptions` when False, the test's expected digest still includes it. | Not fixable by DOC (F8 owner; DOC may not edit `src/` or `tests/`). Reproduced again in this session (`1 failed, 22 passed`). |

Totals: round 0 had 1 medium and 5 low (6 findings); round 1 had 2 medium and 4 low (6 findings, 3 of them in other
features' files, 1 a repeat of the deferred round 0 item 4). No high or critical finding in either round. Round 0
outcome: 5 fixed on the DOC side (items 1, 2, 3, 5, 6; the root causes of items 1 and 2 stay with F0/CI) and 1
deferred with a reason (item 4). Round 1 outcome: nothing fixed, because no fix round followed it; round-1 items 2
and 3 (DOC) and items 4 to 6 (other owners) remain open, and item 1 stays deferred.

## Open issues

1. **Docker path (F0/CI, medium).** `just docker-demo` and the CI `docker-smoke` job cannot succeed: no `WHSIZING_SALT`, no synth step, `data/generated` excluded from the image. DOC only documents it. Needs a synth step plus `-e WHSIZING_SALT` in the recipe and the job. The `docker run` replacement in the runbook is untested (Docker not installed).
2. **`just demo` (F0, low).** Still renders a stub PDF from a mock result, not the §3.2 demo. Documented in README and runbook §1.
3. **README lacks `uv run pre-commit install` (DOC, low).** Open since round 1.
4. **Runbook `run-all` options incomplete (DOC, low).** `--non-interactive`, `--no-strict`, `rerun --out-dir` not listed. Open since round 1.
5. **F8 test failure (F8, medium).** `test_I75_b_the_manifest_carries_the_sha256_of_the_normalised_project` fails because the test and `src/whsizing/scenarios/manifest.py` disagree on hashing `keep_descriptions`. Still failing at the time of this record. It is not in DOC's gate.
6. **Project-wide gate fragility.** `test_T0_1_lint_and_typecheck_gates_pass[pyright]` failed once during the build (2 pyright errors in `tests/unit/test_f10_app_*.py`, one at `test_f10_app_state.py:153` where `os.utime` got `tuple[int, ...]` instead of `tuple[int, int]`, edited concurrently by another engineer). The same command passed earlier and in both audits and in the fresh run here, so DOC's gate result is a pass, but the gate depends on other features' files.
7. **Deferred placement (DOC, low).** Data request and review checklists live in PILOT.md, with cross-references from the runbook (round 0 finding 4, round 1 finding 1).
8. **Catalog status.** All 72 parameters are `TODO` source with confidence `L`. The methodology says so; this is a content state of the catalog, not a documentation defect, and expert review is needed to change it.
9. **Open rulings and known limits** are listed in methodology (I33, I46, I48, I53, I54, I64, I65, I67, I69, I73, I76 open; I68, I75i, I79h, I82b, I81c known limits). They are decisions for the owner of `docs/INTERPRETATIONS.md`, not for DOC.
10. **Repository state.** No git commit exists, so the manifest in the documented runs shows `engine_version 0.1.0` and `git_sha unknown`; the docs say so as observed.

Blockers reported by the build: none about dependencies. `pyproject.toml` and `uv.lock` are unchanged (md5 identical before and after); schema changes: none.

## Not applicable here and why

- **Docker:** not installed. Not exercised: the image build, `just docker-demo`, the Docker form of T0.5 (skipped with a reason), the CI `docker-smoke` job, and the `docker run` replacement command in the runbook.
- **GitHub CI:** the workflow was checked only through `test_T0_1_ci_workflow_has_the_six_stages_in_order`; no CI run exists without a remote repository.
- **Real client data:** none is available. All documented runs use synthetic data (`ecom_mid`, and a small derived profile). The calibration demo uses actuals derived from the model itself, so it proves the plumbing only (the runbook says so). The pilot procedure in PILOT.md was not exercised with a client.
- **Domain-expert review:** the catalog ranges are all `TODO`/`L`, and the methodology's open rulings need expert and owner decisions. The docs describe this and do not claim validation.
- **Own T-ids and own tests:** the spec defines none for DOC, and `tests/` is outside this feature's paths.
- **ruff and pyright on DOC paths:** DOC owns no Python file, so there was nothing to lint or type-check.
- **Not run by DOC:** `brew install uv just pango`; a live Streamlit start (only an import check: streamlit 1.67.0, weasyprint 70.0; page behaviour is covered by `tests/e2e/test_f10_app_pages.py`, which DOC did not run); `just test`, `just bench`, `just app`; exit code 1 (documented from code and tests); exit code 5 was triggered by an auditor in round 0 but not by the DOC engineer; `calibrate` on an unsized run (the runbook quotes `context_from_run`'s `ConfigError` text from the source). On the build machine `import weasyprint` also worked without `DYLD_FALLBACK_LIBRARY_PATH`; the docs keep the variable as the documented fix and say so.
- **Network claim:** "the source imports no network client" rests on a grep of `src/`; third-party packages were not audited (PILOT says so).
