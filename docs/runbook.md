# Runbook

How to run a study end to end (C4): install, environment, the command-line flow, the run folder,
exit codes, the Streamlit app, troubleshooting. For what the numbers mean read
[`methodology.md`](methodology.md); for the pilot (data request, data protection, reading the
report, calibration) read [`PILOT.md`](PILOT.md); every interpretation the engine follows is in
[`INTERPRETATIONS.md`](INTERPRETATIONS.md) (cited `I<n>`).

**How the outputs below were produced.** Every command was run on this repository (macOS, Python
3.12.13, uv 0.12.5) from the repository root on a small synthetic dataset (§3.1). Pasted outputs are
real; four things were changed: the scratch folder is written `$WORK`, the `run_id` and
`scenario` fields of the structlog lines (stderr) are removed, lines are cut at 175 characters, and
an `exit=N` line (`echo "exit=$?"`) is appended to show the exit code. A `…` marks lines left out. Timestamps, run folder names and the demo's data change on every run only in their
timestamp; the numbers repeat (seed 42, no random step in the pipeline).

## 1. Install

```bash
brew install uv just pango          # macOS; uv: https://docs.astral.sh/uv/, just: optional
uv sync --all-extras                # Python 3.12 (pinned by .python-version), the §3.1 dependencies, Streamlit, dev tools
uv run whsizing --version           # whsizing 0.1.0
```

`uv sync --frozen` installs exactly `uv.lock` (CI and Docker do). `uv sync --all-extras --frozen
--dry-run` on this checkout reports "Would make no changes" (104 packages). Do not use the system
Python (3.9 on macOS) or conda: the project requires Python ≥ 3.12. Always run `uv run ...` from the
repository root.

**WeasyPrint and Pango (PDF).** WeasyPrint loads Pango through `dlopen`. If a PDF step (or
`import weasyprint`) fails with `cannot load library 'libgobject-2.0-0'` on macOS, point the loader
to Homebrew:

```bash
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib      # Apple silicon; /usr/local/lib on Intel
```

The `justfile` exports it for every recipe and `tests/conftest.py` sets it before importing
WeasyPrint; tests marked `pdf` are *skipped with the reason*, never passed silently, when Pango is
still missing. (On the machine used for this runbook `import weasyprint` also works without the
variable; the demo script sets it anyway.) On Debian/Ubuntu install `libpango-1.0-0 libpangoft2-1.0-0
libharfbuzz0b fonts-dejavu fonts-liberation` (the `Dockerfile` does).

**Docker.** `just docker-demo` and the CI job `docker-smoke` generate the synthetic data inside the
container and pass a salt (the image has no `data/generated/`, `.dockerignore` excludes it):

```bash
docker build -t whsizing:dev . && mkdir -p runs
docker run --rm --entrypoint sh -e WHSIZING_SALT=choose-a-secret -v "$(pwd)/runs:/app/runs" whsizing:dev \
  -c 'whsizing synth data/synth/profiles/ecom_mid.yaml && whsizing run-all project/example_project.yaml'
```

Docker is not installed on the machine used for this runbook: the sequence ran with the local
`whsizing` (exit 0), the `docker run` form itself is untested here. `just demo` is the same flow
without Docker (synth, then `run-all`).

Quality gates (developers): `just test` (ruff, pyright, pytest without the `bench` marker),
`just test-fast` (unit tests), `just bench` (C5 budgets), `just --list`.

## 2. Environment: the salt

Identifiers are hashed at ingestion with `HMAC-SHA256(salt, id)[:16]` (C2); the tool will not
ingest without a salt.

- `export WHSIZING_SALT='<long random secret>'`, or
- a **salt file kept outside any git repository** (`~/.whsizing/salt_client_x`, mode 600):
  `whsizing ingest ... --salt-file`, `whsizing run-all --salt-file`, or `salt_file:` in `project.yaml`
  (project file first, then `$WHSIZING_SALT`). A salt file inside a git repository is refused.

Use **one salt per client**, the same for every file of the study and for a later refresh, so that
hashed SKUs stay joinable. The salt is never written into a run, `rerun` needs none, and the
correspondence table does not exist. Keep the salt with the data, not with the report: whoever has
both can re-identify. The demo uses `WHSIZING_SALT=demo-salt-not-a-secret`.

Useful variables: `WHSIZING_DEBUG=1` (or `--debug`) prints tracebacks on stderr;
`DYLD_FALLBACK_LIBRARY_PATH` (above); for the app `WHSIZING_RUNS`, `WHSIZING_CATALOG`,
`WHSIZING_LANG` (§6).

## 3. The command-line flow

### 3.0 Overview

```
synth → ingest (×4 datasets) → profile → basis init → size → compare → report
          └─────────────────────── run-all project.yaml ───────────────────────┘
rerun <run> · calibrate <run> · validate-catalog <dir>
```

Two ways to the same run folder: the **staged flow** (`ingest` → `profile` → `size` → `compare` →
`report`, one command per stage, §3.2-3.8, good for a first look at a client's files) and
**`run-all project.yaml`** (§3.9, one command, reproducible, what the pilot uses). Log lines go to
stderr and to `logs/run.log` of the run; **the run folder is the last line a command prints on
stdout** (I78 g), so `RUN=$(whsizing ingest ... 2>/dev/null)` captures it.

### 3.1 A demo dataset (synthetic, 13 months)

```bash
export WORK=/tmp/whsizing-demo && mkdir -p $WORK
export WHSIZING_SALT=demo-salt-not-a-secret
sed -e 's/^name: ecom_mid/name: small_demo/' -e 's/^n_skus: 5000/n_skus: 1500/' -e 's/^n_days: 730/n_days: 400/' \
    -e 's/^orders_per_day_mean: 800 .*/orders_per_day_mean: 150/' data/synth/profiles/ecom_mid.yaml > $WORK/small_demo.yaml
uv run whsizing synth $WORK/small_demo.yaml --out $WORK/data --seed 42
```

```text
$WORK/data/order_lines.parquet
$WORK/data/sku_master.parquet
$WORK/data/inventory.parquet
$WORK/data/receipts.parquet
$WORK/data/csv_en/order_lines.csv
$WORK/data/csv_en/sku_master.csv
$WORK/data/csv_en/inventory.csv
$WORK/data/csv_en/receipts.csv
$WORK/data/csv_fr/order_lines.csv
$WORK/data/csv_fr/sku_master.csv
$WORK/data/csv_fr/inventory.csv
$WORK/data/csv_fr/receipts.csv
exit=0
```

1 500 SKUs, 150 orders a day for 400 days from 2024-01-01 (the profile of the repository's
`ecom_mid`, scaled down). `whsizing synth --defects` injects the profile's data defects into the CSV
exports (BOM, mixed date formats, missing dimensions, orphan SKUs, duplicates, cm instead of mm, ...)
for testing the ingestion. The repository's full-size `ecom_mid` is generated by
`uv run whsizing synth data/synth/profiles/ecom_mid.yaml` (default output `data/generated/ecom_mid`,
the folder `project/example_project.yaml` reads).

### 3.2 Ingest: map, anonymise, validate

Ingest **`sku_master` first** (the other datasets are checked against it: R2, R7, R11), then the
others into the same run folder with `--run`:

```bash
RUN=$(uv run whsizing ingest $WORK/data/csv_en/sku_master.csv --dataset sku_master \
        --out-dir $WORK/runs --non-interactive 2>/dev/null)
echo $RUN
for ds in order_lines inventory receipts; do
  uv run whsizing ingest $WORK/data/csv_en/$ds.csv --dataset $ds --run $RUN --non-interactive
done
```

```text
2026-11-09T20:29:12.196586Z [info     ] ingest_start                   dataset=sku_master run_dir=$WORK/runs/2026-11-09T20-29-12_35a39c
2026-11-09T20:29:12.295202Z [info     ] ingest_done                    band=usable datasets=['sku_master'] dq_score=85.0 stage=ingest
2026-11-09T20:29:12.336902Z [info     ] stage_done                     duration_s=0.140101 stage=ingest
$WORK/runs/2026-11-09T20-29-12_35a39c
exit=0
```

(The three structlog lines go to stderr, the run folder is the only stdout line. The other three
ingests print the same lines and the same folder; their `ingest_done` reports `dq_score` 95.0, 100.0
and 100.0 as each dataset is added: the last one is the study's.) Options: `--mapping <yaml>` reuses a saved mapping, `--salt-file`,
`--keep-descriptions` (keeps `description` and `customer` columns; a kept customer column is still
hashed), `--out-dir` (default `runs`), `--non-interactive` (never ask: an unclear mapping or unit
hint is exit 2). Several files of one dataset: `files…` or a glob (`data/stock_*.csv`).

What ingest decides, and where it writes (all under the run): `canonical/*.parquet` (the typed,
hashed tables), `dq/dq_report.{json,html}` (score, band, one line per rule), `dq/ingest_manifest.json`
(sha256, sizes, row counts per file; rows in / out / dropped per rule), and
`inputs/mapping/<dataset>.yaml` (sniff results and the column mapping, reused on the next ingest;
edit it to fix a mapping). Mapping scores: ≥ 0.85 auto-accepted, 0.60-0.85 asks (§7.2), < 0.60 is
unmapped.

**Read the DQ report before anything else.** `dq/dq_report.html` is for people (score, band, rules
in plain words, sample rows); the same facts from the JSON:

```bash
python3 - $RUN <<'EOF'
import json, sys
d = json.load(open(sys.argv[1] + "/dq/dq_report.json"))
print("score", d["score"], d["band"], d["coverage"])
for r in d["rules"]:
    if r["severity"] != "ok":
        print(r["rule"], r["dataset"], r["severity"], r["count"], "-", r["message"])
EOF
```

```text
score 100.0 usable {'dims_coverage_lines': 1.0, 'order_ts_with_time_share': 0.999766, 'history_months': 13.14, 'units_per_pallet_default_share': 0.0}
R4 order_lines info 3783 - 3783 negative lines treated as returns
```

Bands: ≥ 80 *usable*, 60-79 *usable with caveats*, < 60 *remediation needed* (methodology §1.3). A
blocking rule stops the ingest (exit 3, §7.3). The rules R1-R14 and their severities are tabulated
in methodology §1.2; a warning is a question for the client, not a stop.

### 3.3 Demand profile

```bash
uv run whsizing profile $RUN
```

```text
2026-11-09T20:29:17.595656Z [info     ] stage_done                     duration_s=0.884864 stage=profile
profile: 2024-01-01 to 2025-02-03, 343 operating days, dataset 3c3a78457f65db07
$WORK/runs/2026-11-09T20-29-12_35a39c/profile
exit=0
```

`profile/demand_profile.json` (statistics, EIQ, ABC, stock, seasonality, intraday, shipment split) and
`profile/charts/*.png` + `*.html` (daily lines, monthly and weekday index, intraday heat map, lines
per order, Pareto, stock cover, cube-weight scatter). Options: `--cfg <ProfileCfg yaml>` (ABC
thresholds, dead-stock window, holiday overrides), `--basis` (time zone, flows). `size` redoes the
profile with the design basis, so this step is for looking.

### 3.4 Design basis

```bash
uv run whsizing basis init --lang en --out $WORK/basis_template.yaml     # or --lang fr
```

```text
$WORK/basis_template.yaml
exit=0
```

writes a commented `basis.yaml`: `[P]` = placeholder default to confirm with the client, `[CLIENT]` =
value the client must give (cut-off and departure times, building area and height, dock doors,
loaded hourly cost per role), `[VERIFY]` = check against current rules. It refuses to overwrite an
existing file (exit 2). Unknown keys are rejected (exit 2); **times are quoted strings**
(`"15:00"`: YAML reads an unquoted `15:00` as a base-60 number). Fill it with the client; keep the
file under version control with the study. For the demo use the repository's `basis/example_basis.yaml`
(Appendix E; a 12 000 m² site with a documented 40-FTE current operation).

Scenarios (`scenarios/example_scenarios.yaml`, Appendix E) are the three generic families: S0
`manual_p2p`, S1 `amr_gtp`, S2 `cube_asrs`. The example compares against the client's current
operation (`baseline: client_current`); the demo site is five times smaller than the example
client, so it compares against S0 instead (`is_baseline: true` must agree with `baseline:`):

```bash
cat > $WORK/scenarios.yaml <<'EOF'
scenarios:
  - {id: S0, name: "Manual picker-to-parts", family: manual_p2p, is_baseline: true}
  - {id: S1, name: "AMR goods-to-person", family: amr_gtp}
  - {id: S2, name: "Cube AS/RS", family: cube_asrs}
baseline: S0
EOF
```

### 3.5 Size

```bash
uv run whsizing size $RUN --basis basis/example_basis.yaml --scenarios $WORK/scenarios.yaml --catalog catalog
```

```text
2026-11-09T20:29:19.464619Z [warning  ] catalog_todo_sources           count=72 total=72
2026-11-09T20:29:19.468270Z [info     ] stage_done                     duration_s=0.00288 stage=inputs
2026-11-09T20:29:19.545898Z [warning  ] catalog_todo_sources           count=72 stage=profile total=72
2026-11-09T20:29:20.432728Z [info     ] stage_done                     duration_s=0.910148 stage=profile
2026-11-09T20:29:20.433310Z [info     ] stage_done                     duration_s=0.000452 stage=design
2026-11-09T20:29:20.464290Z [info     ] scenario_done                  fit=True scenario=S0 stage=scenarios tco_typ=1092813.0369600216
2026-11-09T20:29:20.519390Z [info     ] scenario_done                  fit=True scenario=S1 stage=scenarios tco_typ=1531381.3040322305
2026-11-09T20:29:20.575825Z [info     ] scenario_done                  fit=True scenario=S2 stage=scenarios tco_typ=1685211.9028611956
2026-11-09T20:29:20.575946Z [info     ] stage_done                     duration_s=0.142558 stage=scenarios
                                                     Comparison, baseline: S0                                                     
┏━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Scenario ┃ Family     ┃ Fit ┃       Area m2 ┃       FTE day ┃        Capex k€ ┃          TCO k€ ┃           NPV k€ ┃ Payback y ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ S0       │ manual_p2p │ yes │ 534 [494-580] │ 5.9 [4.2-8.2] │    172 [92-338] │           1,093 │                - │         - │
│          │            │     │               │               │                 │     [751-1,674] │                  │           │
│ S1       │ amr_gtp    │ yes │ 581 [504-712] │ 3.9 [3.0-5.7] │ 597 [282-1,505] │           1,531 │             -439 │         - │
│          │            │     │               │               │                 │     [921-3,082] │    [-1,407--170] │           │
│ S2       │ cube_asrs  │ yes │ 550 [483-613] │ 3.7 [2.8-5.2] │ 769 [339-1,759] │           1,685 │             -592 │         - │
│          │            │     │               │               │                 │     [956-3,295] │    [-1,621--205] │           │
└──────────┴────────────┴─────┴───────────────┴───────────────┴─────────────────┴─────────────────┴──────────────────┴───────────┘
Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
$WORK/runs/2026-11-09T20-29-12_35a39c
exit=0
```

Reading the table (details in `PILOT.md` §3): each cell is `typ [lo-hi]` over the three worlds
(methodology §0.3); FTE is design-day heads with one decimal; `-` under NPV and payback means "no
payback within the horizon" or "this is the baseline". **Here the automated scenarios lose to the
manual one**: the design day is 632 lines, below the minimum scale of the catalog (S1 800, S2 1 500
lines a day), so S1 and S2 carry `F_SCALE_LOW` (and `F_ROBOT_DENSITY`; read the flags in
`scenarios/<id>/result.json`), and the model says what it should. The `catalog_todo_sources` warning
(72) is the count of placeholder parameters (methodology §10.2).

`size` writes `design/design_day.json`, `design/assumptions.json`, `scenarios/<id>/{result,finance}.json`
and `trace.jsonl`, `manifest.json` and the input copies. It refuses a run that is already sized
(runs are immutable, exit 2). `--strict` makes missing inputs, a scenario that cannot be computed, no
fit anywhere, or an eligibility assumed for SKUs without dimensions exit 4 (§4); `--worlds typ` shows
only the typical values (the three worlds are always computed).

### 3.6 Compare and sensitivity

```bash
uv run whsizing compare $RUN                    # --no-sensitivity, --delta 0.2
```

```text
2026-11-09T20:29:21.546065Z [warning  ] catalog_todo_sources           count=72 total=72
2026-11-09T20:29:21.765919Z [info     ] stage_done                     duration_s=0.00042 stage=comparison
2026-11-09T20:29:24.575759Z [info     ] stage_done                     duration_s=2.809649 stage=sensitivity
… (the comparison table of §3.5)
Ranking at typical values; ranges overlap for scenarios S0 and S1; S0 and S2; S1 and S2
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
$WORK/runs/2026-11-09T20-29-12_35a39c/comparison
exit=0
```

prints the same table and writes `comparison/comparison.json` and `comparison/sensitivity.json`
(tornado, break-even labor-cost multiplier, percentile sweep P80/P90/P95/P98). 3.9 s on the demo
(2.8 s of it sensitivity). The ranking is at typical values and always carries the overlap note;
there is no "recommended" label.

### 3.7 Report

```bash
uv run whsizing report $RUN --lang en           # --lang fr|en|both, --formats pdf|xlsx|both
```

```text
2026-11-09T20:29:25.545674Z [warning  ] catalog_todo_sources           count=72 total=72
2026-11-09T20:29:25.653701Z [warning  ] catalog_todo_sources           count=72 stage=report total=72
2026-11-09T20:29:26.054323Z [warning  ] catalog_todo_sources           count=72 stage=report total=72
2026-11-09T20:29:28.757829Z [info     ] stage_done                     duration_s=3.128991 stage=report
$WORK/runs/2026-11-09T20-29-12_35a39c/report/report_en.xlsx
$WORK/runs/2026-11-09T20-29-12_35a39c/report/report_en.pdf
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
exit=0
```

Integrity checks IC1-IC8 run *first*; any failure is exit 5 and no file is written (methodology §8).
The demo PDF has 17 pages (the budget is 12-18) and the workbook the 12 sheets Summary, Design
basis, Demand profile, Design day, Scenarios, FTE, Capex - Opex, Cash flow, Sensitivity,
Assumptions, Data quality, Methodology. `report/trace.jsonl` lists every trace id the report cites,
`report/diagram_<id>.svg` the block diagrams. Language defaults to the project's `language`.

### 3.8 The run folder

condensed from `find $RUN -maxdepth 2` after the stages above:

```text
canonical/{order_lines,sku_master,inventory,receipts,daily_series}.parquet  .ingest_key  .sha256.json
comparison/{comparison,sensitivity}.json
design/{design_day,assumptions}.json
dq/{dq_report.html,dq_report.json,ingest_manifest.json}
inputs/{basis.yaml,scenarios.yaml,project.yaml}  inputs/catalog/  inputs/mapping/<dataset>.yaml
logs/run.log                         # JSON lines: run_id, stage, scenario, duration_s; tracebacks of exit 1
manifest.json                        # RunManifest, written by `size`; each later stage adds its timings
profile/{demand_profile.json,charts/}
report/{report_en.pdf,report_en.xlsx,diagram_S0.svg,...,trace.jsonl}
scenarios/S0 S1 S2/{result.json,finance.json,trace.jsonl}
calibration/                         # after `whsizing calibrate`
```

`manifest.json` (head, this run):

```text
run_id: 2026-11-09T20-29-12_35a39c
created_at: 2026-11-09T20:29:19.468448Z
engine_version: 0.1.0
git_sha: unknown
catalog_version: manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0 sha256:6282174cc512
basis_hash: 7212ffa7900c538debed25b34655a4c4c746a00c4db7dd9681403011826fa543
scenarios_hash: 985d101961c12619b629e087b005623e74269f09555e170fa3d8d94106d70d82
seed: 42
python: 3.12.13
platform: darwin-arm64
project_hash: 50a5be9e38ff550b19a4229698327ac468faa950698fb1d47393ae714e95bd8f
inputs: 18 files hashed; params_snapshot: 145 values; packages: 23
timings: {'ingest': 0.8, 'inputs': 0.0, 'profile': 0.91, 'design': 0.0, 'scenarios': 0.14, 'comparison': 0.0, 'sensitivity': 2.81, 'report': 3.13}
```

This checkout has no git commit, hence `git_sha: unknown` and an `engine_version` without a
`+<git describe>` suffix; with commits it reads `0.1.0+<describe>[-dirty]` (C1). Folder name =
UTC timestamp + 6 hex characters; runs are never overwritten (I75, I78 a for the staged flow).
`params_snapshot` holds the 72 catalog parameters and the 72 structural constants at typ after
overrides, plus one `<scenario>:<id>` entry per scenario override (145 values for the example
scenarios, whose S1 overrides `amr_gtp.station_rate_lines_h`).

### 3.9 `run-all`, `rerun`

`project.yaml` (Appendix E) lists the files, mappings, basis, scenarios, catalog, salt file, language
and options; paths resolve against the YAML's folder (absolute paths below):

```bash
cat > $WORK/project.yaml <<EOF
name: small_demo
language: [en]
out_dir: $WORK/runs_all
catalog: $PWD/catalog
salt_file: null
inputs:
  order_lines: {files: [$WORK/data/csv_en/order_lines.csv]}
  sku_master:  {files: [$WORK/data/csv_en/sku_master.csv]}
  inventory:   {files: [$WORK/data/csv_en/inventory.csv]}
  receipts:    {files: [$WORK/data/csv_en/receipts.csv]}
basis: $PWD/basis/example_basis.yaml
scenarios: $WORK/scenarios.yaml
options: {worlds: all, sensitivity: true, delta: 0.2, strict: false}
EOF
/usr/bin/time -p uv run whsizing run-all $WORK/project.yaml
```

```text
…
$WORK/runs_all/2026-11-09T20-29-30_8b1bda/report/report_en.xlsx
$WORK/runs_all/2026-11-09T20-29-30_8b1bda/report/report_en.pdf
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
$WORK/runs_all/2026-11-09T20-29-30_8b1bda
real 8.94
user 10.19
sys 7.67
exit=0
```

(9 s from CSV files to PDF and Excel on this machine.) Options override the project: `--strict`,
`--worlds`, `--sensitivity/--no-sensitivity`, `--delta`, `--lang`, `--formats`, `--salt-file`,
`--basis`, `--scenarios`, `--catalog`, `--keep-descriptions`. `run-all` reuses `canonical/` of an
earlier run when the input hashes, the mapping, the salt and the engine version are unchanged
(opt-in by the command, I75 c). The salt is checked before any folder is made (exit 2).

**Reproduce a run** (C1, T6.9). `rerun` builds a new folder from the manifest and the copies kept
in the run: no salt, no client file needed. The report is not rebuilt by `rerun`:

```bash
env -u WHSIZING_SALT uv run whsizing rerun $WORK/runs_all/2026-11-09T20-29-30_8b1bda
uv run whsizing report $WORK/runs_all/2026-11-09T20-29-39_a1fbb1 --lang en --formats xlsx
shasum -a 256 $WORK/runs_all/*/scenarios/S0/result.json
```

```text
2026-11-09T20:29:39.190253Z [warning  ] catalog_todo_sources           count=72 stage=load total=72
2026-11-09T20:29:39.227554Z [info     ] stage_done                     duration_s=0.059862 stage=load
2026-11-09T20:29:39.228548Z [info     ] run_start                      rerun_of=2026-11-09T20-29-30_8b1bda run_dir=$WORK/runs_all/2026-11-09T20-29-39_a1fbb1
2026-11-09T20:29:39.231999Z [info     ] stage_done                     duration_s=0.003181 stage=inputs
2026-11-09T20:29:39.233383Z [info     ] canonical_reused               source=$WORK/runs_all/2026-11-09T20-29-30_8b1bda stage=ingest
…
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
$WORK/runs_all/2026-11-09T20-29-39_a1fbb1
exit=0
42ad3cbba26a2720b83aac8927238e36bbed95979b39e40ba5bf24f33dfe9bfe  $WORK/runs_all/2026-11-09T20-29-30_8b1bda/scenarios/S0/result.json
42ad3cbba26a2720b83aac8927238e36bbed95979b39e40ba5bf24f33dfe9bfe  $WORK/runs_all/2026-11-09T20-29-39_a1fbb1/scenarios/S0/result.json
```

Same `result.json` byte for byte. An edited `inputs/project.yaml` makes `rerun` refuse with a `ConfigError`, exit 2 (I75 b; not tried here).

### 3.10 Calibrate (back-test)

Needs a sized run, a monthly hours file and an activity map (formats and how to collect them:
`PILOT.md` §4). The demo uses **synthetic actuals**: the model's own monthly baseline hours times
known factors (0.90 to 1.15) with 2 % noise, so it proves the plumbing, not the model:

```bash
cat > $WORK/make_actuals.py <<'EOF'
"""Synthetic actuals for the demo: the model's own monthly hours x known multipliers x 2 % noise."""
import csv
import sys
from pathlib import Path

import numpy as np

from whsizing.calibration.inputs import inputs_from_run
from whsizing.calibration.predict import baseline_monthly
from whsizing.catalog import load_catalog
from whsizing.design import load_basis

run, out = Path(sys.argv[1]), Path(sys.argv[2])
b = baseline_monthly(
    inputs_from_run(run, load_basis(run / "inputs/basis.yaml"), load_catalog(run / "inputs/catalog"))
)
LABEL = {"receiving": "Reception", "put_away": "Mise en stock", "replenishment": "Reappro",
         "picking": "Preparation", "packing": "Emballage", "shipping": "Expedition",
         "returns": "Retours", "indirect": "Encadrement"}
FACTOR = {"receiving": 1.10, "put_away": 0.95, "picking": 1.15, "packing": 0.90, "shipping": 1.05}
rng = np.random.default_rng(42)
months = [m for m in b.months if b.coverage[m] >= 0.9]  # complete months only
with (out / "actuals.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["month", "activity_client", "hours"])
    for activity, hours in b.hours.items():
        for month, h in zip(b.months, hours, strict=True):
            if month in months:
                w.writerow([month, LABEL[activity], round(float(h) * FACTOR.get(activity, 1.0) * rng.normal(1, 0.02), 1)])
amap = "activities:\n" + "".join(f"  {label}: {activity}\n" for activity, label in LABEL.items())
(out / "activity_map.yaml").write_text(amap + "client_activities: []\n")
print(len(months), "months:", months[0], "to", months[-1])
EOF
uv run python $WORK/make_actuals.py $RUN $WORK
uv run whsizing calibrate $RUN --actuals $WORK/actuals.csv --activity-map $WORK/activity_map.yaml
```

```text
13 months: 2024-01 to 2025-01
2026-11-09T20:29:46.714312Z [warning  ] catalog_todo_sources           count=72 total=72
2026-11-09T20:29:47.346726Z [info     ] stage_done                     duration_s=0.40688 stage=calibration
calibration accepted: hold-out MAPE 0.8 %, peak-month error -0.5 %
  I_TEMPS_COMBINED: temp hours are not separated: the hours combine permanent staff, temps and overtime, and the model's temp hours cannot be back-tested
INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as ingested. Not a quotation, a commitment or a validated design.
$WORK/runs/2026-11-09T20-29-12_35a39c/calibration
exit=0
```

`actuals.csv` is `month,activity_client,hours` (`2024-01,Reception,5.6`), the map is
`activity_map.yaml`: `activities: {client label: model activity}` plus `client_activities: []`.
Outputs in `calibration/`: `fit.json`, `holdout.json`, `plots/{predicted_vs_actual,residuals_by_month,
multipliers}.png`, `calibration_note.md`, copies of both inputs (copied only when the calibration
succeeded). `--holdout-months` (default 3); `--observed-peak-lines-h <number>` adds the client's observed
peak (lines per hour) to the hold-out report (a non-finite or non-positive value is exit 2); an existing
`calibration/` is refused (exit 2) unless `--force`, and a failed calibration leaves the earlier one
untouched (I86, I90 c). The catalog update (methodology §9 step 8) is **not** a CLI step.

### 3.11 Validate the catalog

```bash
uv run whsizing validate-catalog catalog
```

```text
2026-11-09T20:29:48.336775Z [warning  ] catalog_todo_sources           count=72 total=72
catalog: valid, catalog manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0 sha256:6282174cc512
72 parameters, 3 families
72 parameter(s) with source TODO
  TODO amr_gtp.bins_per_pod
  TODO amr_gtp.charging_per_robot_eur
exit=0
```

Every file error is listed together, then exit 2. After any catalog change regenerate the
assumptions table: `uv run python -m whsizing.catalog.assumptions` (writes `docs/assumptions.md`:
72 ranged parameters and 72 structural constants; `tests/unit/test_f5_loader.py` fails when it is
stale).

## 4. Exit codes (§2.7)

| Code | Class | Meaning | Reproduced above |
|---|---|---|---|
| 0 | none | success | everywhere |
| 1 | `WhsizingError` and anything unexpected | unhandled failure; traceback in `logs/run.log` of the run, or on stderr with `--debug`; a canonical table missing a column (I72) | not triggered |
| 2 | `ConfigError`, `MappingError` | invalid YAML or unknown key or parameter id, missing salt, required column unmapped or unit hint undecided in non-interactive mode, a run that is already sized | §7.1, §7.2 |
| 3 | `DataQualityError` | at least one blocking DQ rule (R1 > 1 %, R2 > 5 %, R9); also `calibrate` on an unusable actuals file: unreadable, no data row, a malformed line, or an activity with no row for a month of the grid (`actuals: 'reception' has no row for ['2024-05']: add a row with hours 0 for none`) | §7.3 (calibrate: not reproduced above, reproduced separately) |
| 4 | `SizingInfeasibleError` | `--strict`: a required input missing (SKU master, inventory), a scenario not computed, no scenario fits, eligibility assumed for SKUs without dimensions. Also without `--strict` when NO scenario is computed (I90 b), and when a sized equipment count exceeds `engine.max_equipment_count` (100 000; units or outliers, R13: I85 b) | §7.4 |
| 5 | `ReportIntegrityError` | an IC check failed; the message lists `IC<n> location: message` (20 at most) | not triggered here (tests T9.4 tamper fixtures) |
| 143 | SIGTERM | the run was terminated; `<run>/logs/FAILED` and a `run_failed` record in `logs/run.log` say so (I90 a); such a run is not listed by the app | tests only |

Typer usage errors (unknown option, missing argument) are exit 2 too.

## 5. Reading a trace ("why this number?")

Each scenario's `trace.jsonl` holds every intermediate quantity with its formula and inputs; the
Streamlit results page expands a cell the same way. From the library:

```bash
cat > $WORK/tree.py <<'EOF'
import sys
from pathlib import Path
from whsizing.schemas import Tracer

t = Tracer.load_jsonl(Path(sys.argv[1]) / "scenarios" / "S2" / "trace.jsonl")

def show(node, depth=0, maxdepth=3):
    pad = "  " * depth
    if node["kind"] == "node":
        print(f'{pad}{node["id"]} = {node["value"]:.4g} {node["unit"]}   [{node["formula"]}]')
        if depth < maxdepth:
            for child in node["inputs"].values():
                show(child, depth + 1, maxdepth)
    else:
        print(f'{pad}{node["id"]}')

show(t.tree(sys.argv[2]))
EOF
uv run python $WORK/tree.py $RUN S2.equipment.ports
```

```text
S2.equipment.ports = 2 -   [ceil(port_load)]
  S2.equipment.port_load = 1.157 ports   [lambda_e / (port_rate × oee) + decant_port_load_peak_h]
    S2.throughput.lambda_e = 106.6 lines/h   [lambda × share_lines_eligible]
      S2.throughput.lambda = 108.4 lines/h   [max(lambda_peak, lambda_sla)]
      S2.eligibility.share_lines = 0.9836 -   [Σ_elig lines / Σ lines]
    param:cube_asrs.port_rate_lines_h
    param:cube_asrs.oee
    S2.equipment.decant_port_load_peak_h = 0.7987 ports   [decant_station_hours × inbound_peak_factor × peak_hour_share_inbound]
      S2.equipment.decant_station_hours = 2.194 h   [cases_in / decant_cases_per_h]
      data:design_day.inbound.peak_factor
      param:area.peak_hour_share_inbound
```

`param:<id>` leaves are catalog parameters (`docs/assumptions.md`), `data:` leaves come from the
dataset or the basis. Nodes exist per world (`lo`, `typ`, `hi`); the tree above is the typical world.

## 6. The Streamlit app

```bash
export WHSIZING_SALT=<secret>        # or type the salt on page 1
just app                             # = uv run streamlit run src/whsizing/app/Home.py --server.address 127.0.0.1 --server.maxUploadSize 1024
just demo-app                        # the public demo: synthetic data only, no upload (streamlit_app.py)
```

Run it **from the repository root** so `.streamlit/config.toml` applies (usage statistics off; the
recipe passes `--server.maxUploadSize 1024`, the config itself keeps a 1 MB cap for the hosted demo;
larger files: use the CLI). The full app has no authentication: unless
Streamlit's `server.address` is `127.0.0.1` (`just app` sets it) or `WHSIZING_ALLOW_REMOTE=1` is
set, every page answers with an error instead of the app. `streamlit_app.py` is the demo that is deployed on Streamlit
Community Cloud: see `docs/DEPLOY_STREAMLIT.md`. Six pages: 1 Upload & mapping, 2 Data quality,
3 Demand profile, 4 Design basis, 5 Scenarios, 6 Results (comparison, FTE chart, block diagrams,
business case, the "why this number?" drill-down, export buttons). The UI has no logic of its own:
it calls the library and writes the same run folders as the CLI (`WHSIZING_RUNS`, default `runs/`;
`WHSIZING_CATALOG`, default `catalog/`; `WHSIZING_LANG` `fr` or `en`). Every results page carries the
"indicative study" banner. **Not exercised interactively for this runbook**: only
`import streamlit` was checked (`streamlit 1.67.0`, `weasyprint 70.0`); the page logic is covered by
`tests/e2e/test_f10_app_pages.py`.

## 7. Troubleshooting

### 7.1 Missing salt (exit 2)

```text
error: no anonymisation salt: set $WHSIZING_SALT or pass a salt file kept outside the repository
exit=2
```

Export `WHSIZING_SALT` or pass `--salt-file`. Nothing is created before this check. "salt file ... is
inside a git repository": move it out.

### 7.2 Mapping prompts (exit 2 when non-interactive)

A required column that cannot be mapped, with the best candidate (here the header `SKU` was renamed
`zzz`):

```text
error: order_lines (order_lines.csv): required column(s) not mapped: sku (best candidate 'Order Number' scored 0.42: close to 'code article' (0.42)). Provide a mapping file (m
exit=2
```

A suggestion between 0.60 and 0.85 needs a yes (header renamed `Stock keeping code`):

```text
error: order_lines (order_lines.csv): required column(s) not mapped: sku (needs confirmation: close to 'item code' (0.62)). Provide a mapping file (mapping/order_lines.yaml) o
exit=2
```

Interactive (drop `--non-interactive`), the tool asks and records the answer in
`inputs/mapping/order_lines.yaml`:

```text
2026-11-09T20:29:52.166247Z [info     ] ingest_start                   dataset=order_lines run_dir=$WORK/runs_fail/2026-11-09T20-29-52_9ced9d
Use column 'Stock keeping code' as sku? (score 0.62: close to 'item code' (0.62)) [y/N]: 2026-11-09T20:29:52.428568Z [info     ] ingest_done                    band='usable wi
2026-11-09T20:29:52.472426Z [info     ] stage_done                     duration_s=0.305971 stage=ingest
$WORK/runs_fail/2026-11-09T20-29-52_9ced9d
exit=0
```

Non-interactive, give the mapping file instead (`--mapping`, or `mapping:` in `project.yaml`): copy
the one `ingest` saved, fix the `columns:` entry (`sku: "Stock keeping code"`), re-run. A failed
`ingest` that wrote nothing removes its run folder. Unit hints (dimensions that look like cm,
weights that look like grams, `W_UNITS_DIMS`, `W_UNITS_WEIGHT`) also need an answer: confirm
interactively or set `unit_hints: {dims: cm}` (convert) or `{dims: mm}` (keep) in
`mapping/sku_master.yaml`. French files (`;`, decimal comma, `dd/mm/yyyy HH:MM`, "N° commande",
"Référence", "Qté") map without a file: `csv_fr/order_lines.csv` of the demo ingests as is. A
decimal mark decided only by the delimiter produces a DQ warning with examples; set `decimal: ","`
or `"."` in the mapping to settle it (I54, I67).

### 7.3 Blocking data-quality rules (exit 3) and short history (R9)

A history under 3 months is blocking (R9). Demo: the same profile with `n_days: 60`:

```text
error: 1 blocking data-quality issue(s): R9 (order_lines): history 2024-01-01 → 2024-02-29 (1.97 months); at least 3 months needed. See $WORK/runs_short/2026-11-09T20-29-54_35
exit=3
```

The run folder is kept (its `dq/` explains); `canonical/` holds only what was written before. Other
blocking rules: R1 (more than 1 % of lines without a readable date, or dated in the future) and R2
(more than 5 % of ordered SKUs missing from the SKU master: send a complete master). What to do:
ask the client for more history (6 months is the pilot minimum, 12 to 24 preferred: PILOT.md), or
fix the extract (date format, wrong file). Never edit the canonical tables. Under 12 months is a
*warning* (R10: seasonality and trend flagged L, `F_SHORT_HISTORY` under 60 operating days) and costs
10 DQ points.

### 7.4 `--strict` (exit 4)

```text
error: strict: required input(s) missing: inventory (a SKU master with dimensions and weight and a stock snapshot are needed; run without --strict to size with the flags and w
exit=4
```

Raised before any folder is made when `inputs` lacks `sku_master` or `inventory`; after sizing when a
scenario is not computed, none fits the building, or an automated scenario assumes eligibility
(`F_ELIG_ASSUMED`). Everything is written first, so the run can be read.

### 7.5 Other symptoms

| Symptom | Cause and fix |
|---|---|
| `already sized and runs are immutable` (exit 2) | `size`, `profile` and `ingest --run` refuse a run that has `design/` or `manifest.json`. Ingest into a new run, or `rerun`. |
| `not sized yet; run whsizing size first` (`compare`, `report`) or `no inputs/project.yaml (run whsizing size first)` (`calibrate`) | These commands need a sized run (I78 b): run `size` or `run-all` first. |
| `flows.inbound_mode is 'receipts' but ...` (exit 2) | receipts mode with no receipts in the history window or none on a candidate day: load receipts for the window or use `derived` (I71). |
| `<file>: nothing to read from header row N on` (exit 2), or for an Excel file `sheet ... has N row(s), fewer than the mapping's header_row` | an empty export, or a saved mapping whose `header_row` is past the last line of this file: check the file, or ingest it without `--mapping` so that the header row is sniffed again. |
| `<file>: header cell N starts with ^ and ends with $` (exit 2) | polars reads such a name as a regular expression, so no column can carry it: the file is not a text export (a binary file does this now and then), or that column needs another name. |
| `unknown parameter id` in overrides | the id is `<family>.<name>` of `docs/assumptions.md` (message suggests close ids). |
| basis `ConfigError` naming a field | unknown key, NaN, a divisor ≤ 0, a share out of range (I60); fix the YAML (times quoted). |
| `F_NO_FIT` on a scenario | total area above the building: read the area table; not an error. |
| `F_UNSTABLE:packing`, `c_min` | the SLA-window arrival rate exceeds the pack stations sized on the peak hour; `c_min` is the number of stations the SLA window needs (I69, open `[EXPERT]` ruling). |
| PDF step fails at import | Pango: §1 `DYLD_FALLBACK_LIBRARY_PATH`. |
| Report shows English text in the French PDF | DQ messages, F7 notes and raw flag codes are not translated (I79 h). |
| An exit 1 | open `logs/run.log` of the run (JSON line `command_failed` with the traceback) or repeat with `--debug`; report it with the run folder name. |

## 8. A study, in order

1. Data request (spec Appendix A) and legal terms (C2): [`PILOT.md`](PILOT.md) §1 and §2.
2. Install and salt (§1, §2). One salt per client, kept outside the repository.
3. Ingest and read the DQ report with the client (§3.2); fix what is blocking, note what is a caveat.
4. Design basis with the client (`basis init`, §3.4): fill every `[CLIENT]`, confirm every `[P]` you
   can; record client values in the file, overrides in `overrides:` (they appear as *override* in the
   assumptions list).
5. `run-all project.yaml` (§3.9); keep the run folder name in the study notes.
6. Review: expert review #1 (catalog and formulas) and #2 (real-data results and calibration), spec
   §8.1 and §8.2, summarised in `PILOT.md` §4. Read the report with `PILOT.md` §3.
7. Deliver the PDF/Excel with a verbal walkthrough; the report is an *indicative study*.
8. Retention and deletion (C2): delete client files and canonical tables 90 days `[P]` after
   delivery, send a deletion confirmation, keep only the anonymised calibration note and aggregated
   statistics (`PILOT.md` §2).
