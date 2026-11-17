# Methodology

Every formula with its rationale and the assumptions it hides (C4). The consolidated formulas are in spec
Appendix B (`description.md`); the rulings where the spec is ambiguous or silent are the **interpretations
register** `docs/INTERPRETATIONS.md` (cited here as `I<n>`; it is binding: the golden oracle, the engine and
this text follow it). Parameter values are in `catalog/` and are listed one per row in
[`assumptions.md`](assumptions.md) (generated, never edited by hand).

> **Status of the numbers.** Every default is a proposal `[P]`; `[EXPERT]` values need a logistics
> expert before a client sees them, `[VERIFY]` values a check against documentation or regulation.
> In the shipped catalog (`manual_p2p` 0.1.0, `amr_gtp` 0.2.0, `cube_asrs` 0.2.0; the manifest prints `manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0`) all 72 ranged parameters have `source: TODO` and `confidence: L`
> (`assumptions.md`). Nothing here is a sourced benchmark; every study is an *indicative study*.

## 0. Reading guide

### 0.1 Conventions

- Units (ADR-001): mm, kg, m, m², m³, hours; EUR excluding VAT; timestamps tz-aware (`Europe/Paris`
  by default), stored UTC. Rounding only at presentation; counts are `ceil`ed only where the spec
  says so (I39).
- Symbols: `g` growth rate, `T` sizing horizon (`projection.horizon_years`), `gf = (1 + g)^T`,
  `n_op` observed operating days, `lines*` design-day lines (after growth).
- **Worked numbers** use the golden case `tiny_golden` (100 SKUs, 968 orders, 31 days, seed 42,
  `tests/golden/tiny_golden/`) with the basis `tests/golden/golden_basis.yaml` (g = 4 %, T = 5, one
  shift of 7.5 h, 410 m², 8.5 m clear height, same-day share 0.6, cut-off 15:00, departure 18:30;
  the shipment thresholds are deliberately low, 12 kg / 0.1 m³ / 5 kg, so that pallet orders
  exist) and the scenarios `tests/golden/golden_scenarios.yaml` (S0 manual baseline, S2 cube with
  `extra_max_weight_kg: 2.0`). They are quoted with the **key** of
  `tests/golden/golden_values.json` (741 values). The oracle (`tests/golden/oracle.py`, written from
  the spec and the register without importing the engine) computes the typical world only; the
  engine matches it within the T1.5 tolerance of 0.5 % in `tests/golden/test_f*_golden.py`. A
  hundred lines a day is a *tiny* site: the figures are there to be recomputed by hand, not believed.

### 0.2 Where the code and the artifacts are

One directory of `src/whsizing/` per stage, named in its section below; the artifacts of each stage are
listed in `runbook.md` §3.8.

### 0.3 The three worlds (ADR-002)

Every output is computed three times. In the **pessimistic world** (`lo`) every catalog `Param` sits at its
`pessimistic_end`, in the **typical world** (`typ`) at `typ`, in the **optimistic world** (`hi`) at the other
bound (`ParamSet.value`, `src/whsizing/catalog/paramset.py`). The world names the *world*, not the value: a
pessimistic world gives a *higher* cost but a *lower* rate. A result `Range` is therefore built as `lo =
min(values over the 3 worlds)`, `typ` = the typical world, `hi = max(...)`.

Example: `cube_asrs.port_rate_lines_h` is 250 / 350 / 450 lines/h with `pessimistic_end: min`; the pessimistic
world sizes ports at 250 (more ports), the optimistic at 450. `cube_asrs.per_port_eur` (60 000 typ) has
`pessimistic_end: max`: the pessimistic world pays more.

What the ranges are **not**: they bound the result, they are not statistical intervals (Monte Carlo is backlog,
ADR-003). Hidden assumptions:

- All parameters move together. Worlds are the two corners of the box, not a sample; real
  parameters are not perfectly correlated, so the true extremes are less extreme and the interior
  is not uniform.
- `pessimistic_end` is a per-parameter claim. The loader infers it from the unit tokens when absent
  (`catalog/README.md`: `eur`, `€`, `kWh` → max; `x/h`, `x/m2`, `fill`, `availability`, `oee` →
  min; a duration `h`, `m2 per` → max; anything else must be written, else the file is rejected,
  T5.5) and warns when an explicit value contradicts the inference.
- Structural scalars (dimensions, shares, levels) are constants: the same in every world.
- An override (`basis.overrides`, `scenario.overrides`) replaces `typ` and **widens** the range to
  contain the value (`ParamSet`); it must be finite and `> 0` for a parameter whose catalog `min`
  is `> 0`, and `> 0` for the constants the engine divides by (I75 j, `DIVISOR_CONSTANTS`).
- Booleans, docks, queue pools, every flag and the bottleneck come from the **typical** world; the
  other worlds appear only in `Range` values (I62). A lo-world total area above the building is
  visible as `area.total.hi > area`, not as a flag. IRR and payback are typ-world values (no
  `Range` in `FinancialResult`, I73 h); NPV, TCO, capex, opex and cost per line are ranges, the
  baseline being evaluated in the same world as the scenario.
- The comparison never labels a scenario "recommended": it ranks at typ and prints which TCO ranges
  overlap (§7).

### 0.4 Glass-box trace (ADR-001, ADR-003, §2.6)

Every quantity the engine or finance computes is recorded with `Tracer.record(id, label, value, unit, formula,
inputs)` as a `TraceNode` keyed by `(id, world)`; `inputs` maps each symbol of the formula to another node id,
to `param:<catalog id>` or to `data:<dataset-derived value>`. `scenarios/<id>/trace.jsonl` holds the nodes,
`Tracer.tree(id)` expands one down to its parameters (the UI drill-down, `runbook.md` §5 shows a real tree).

- The tracer is deliberately **stateful** (one per scenario run); a node recorded twice with
  different content raises. Ids are stable across runs (snapshot tests).
- **All three worlds are traced in full**: I62 supersedes ADR-002's line "lo/hi worlds trace only
  leaf results", because IC2 (§8) needs a complete tree per world.
- The spec's example `S2.equipment.ports = ceil(lambda_e / (port_rate × oee))` is, in the engine,
  `ceil(port_load)` with `port_load = λ_e / (port_rate × oee) + decant_port_load_peak_h` (I23).
  The trace is the authority on what was computed.
- No simulation (ADR-003): sizing is closed-form plus an Erlang-C queue check, which is what makes
  three scenarios × three worlds fit in a second and every number traceable. Congestion and wave
  interaction are approximated by the flow efficiency `η_flow` and the queue check only.

### 0.5 Reproducibility (C1)

- **Seed.** `manifest.seed` is 42 (`SEED` in `scenarios/manifest.py`). *No step of the analysis
  pipeline is random*; the seed matters to the synthetic generator (`whsizing synth --seed`, default
  42, T1.1 same seed, same Parquet hash) and is recorded for the day a stochastic step is added.
- **Salt.** Identifiers are hashed `HMAC-SHA256(salt, id)[:16]` (§1.4). The salt is the project's,
  never per run, never written into the run; `rerun` needs none. The model is built so that the same
  data gives the same numbers under any salt: SKU ranking ties are broken by salt-independent
  attributes before the hashed id (I6), sums are exact (`math.fsum`, so the last digit does not
  move with the row or thread order, T3.7). `tests/golden/test_g1_abc_tiebreak.py` relabels every
  SKU id (another salt) and all 741 golden values stay equal. Known limit: two SKUs tied on all
  five ranking attributes but one with an unknown weight can swap their class label
  (class sizes and shares stay equal; `INTERPRETATIONS.md`, F3f note).
- **Manifest.** `manifest.json` (`RunManifest`): `engine_version` = `<package version>+<git describe
  --always --dirty>` (`-dirty` flags a modified tree), `git_sha`, `catalog_version`, the sha256 of
  every data and mapping file (data stays where it is, not copied), of `basis.yaml`,
  `scenarios.yaml` and each catalog file (copied under `inputs/`), `params_snapshot` (every
  parameter at typ after overrides, plus `<scenario id>:<param id>` for scenario overrides),
  `project_hash`, `seed`, Python, platform, package versions, stage timings (I75). A repository
  without a commit gives `git_sha: unknown` and `engine_version: 0.1.0`.
- **Run folder** = `<created_at UTC YYYY-MM-DDTHH-MM-SS>_<first 6 hex of the manifest hash>`
  (I75 a, b); runs are immutable, a name clash moves `created_at` by 1 µs. The staged flow
  (`ingest` → `profile` → `size`) names the folder from the dataset name and the input hashes
  instead, because no manifest exists yet; the name never changes (I78 a).
- **`rerun`** builds a new folder from the manifest and the copies kept in the run (`inputs/`,
  `canonical/`; no salt needed): `result.json` is byte-identical (T6.9; `runbook.md` §3.9 shows equal sha256). An edited
  `inputs/project.yaml` is refused (`project_hash`, I75 b). `run-all` reuses `canonical/` only when
  the `ingest_key` (file and mapping hashes, specs, salt hash, units per pallet, engine version and
  git sha) matches (I75 c); a staged run's canonical tables are never reused by `run-all` (I78 c).

## 1. Ingestion and data quality (F2)

Purpose: turn messy files into the canonical tables of spec §4.1, and say plainly how good they are. Code:
`src/whsizing/io/`; the DQ report is `dq/dq_report.{json,html}`, the provenance is `dq/ingest_manifest.json`.

### 1.1 Reading and mapping

- **Sniffing** (spec F2): encoding (`charset_normalizer` on the first 1 MB, fallback utf-8-sig,
  cp1252, latin-1; a BOM-less UTF-16/32 file is recognised from its NUL bytes, I67), delimiter
  (`; , \t |` consistency on 50 lines), header row (first row with ≥ 3 non-empty cells, ≥ 60 %
  non-numeric; a date-shaped cell is a value, not a label, I67), decimal mark, date format
  (ISO, `%d/%m/%Y[ %H:%M[:%S]]`, `%d.%m.%Y`, `%d-%m-%Y`, `%Y%m%d`, Excel serial; ≥ 98 % of a
  sample; ambiguous day/month prefers `dd/mm`).
- **Decimal mark** (I54, `[VERIFY]`). The 80 % rule counts only values that contain a separator;
  ambiguous thousands shapes (`1.200`, `1,000`) say nothing; two shapes count as comma evidence
  beyond the spec regex (`1037,5`, `1 200,5`); with only integers the delimiter decides (`;` →
  comma). When the delimiter decided and a mapped column holds a thousands-only shape the DQ
  report carries a warning with up to 5 raw → parsed examples and the `decimal:` override (I67).
  **Open**: in a `;` file with comma decimals elsewhere a dot 3-decimal weight (`1.250`) is read
  × 1000 with no DQ signal (I67 `[VERIFY]`).
- **Mapping** (`mapping.py`): normalise (NFKD, no accents, lower case), score 1.0 on an exact
  synonym else `rapidfuzz.token_set_ratio / 100` over `synonyms_fr_en.yaml`, content check on 1 000
  rows (×0.5 when the type is incompatible), greedy assignment, a source column used once.
  Thresholds `[P]`: ≥ 0.85 auto-accept, 0.60 to 0.85 suggest (confirmation needed), < 0.60
  unmapped. Non-interactive, an unmapped or unconfirmed required target is `MappingError` (exit
  2). The decision is persisted as `mapping/<dataset>.yaml` and reused; with a tie-broken decimal
  the file keeps `decimal: null` so each ingest warns until the user sets it (I67 b).
- **Unit hints** (both need confirmation): dimensions whose P95 length is < 100 are taken as cm
  (× 10, `W_UNITS_DIMS`); a median weight > 500 as grams (÷ 1000, `W_UNITS_WEIGHT`).
  Non-interactive without a decision in the mapping file: exit 2.

### 1.2 Validation rules R1-R14

Rules are Polars expressions on eager frames (`io/rules.py`), one `RuleResult` per (rule, dataset), "ok" when
nothing fires, so the DQ report is a complete checklist. `REQ` is an F2 addition: a row with a required §4.1
value missing or out of range (negative stock, receipt quantity ≤ 0) cannot enter a canonical table and is
dropped, counted as a warning.

| Rule | Check | Severity as implemented | Action |
|---|---|---|---|
| R1 | `order_ts` null, unparseable or in the future | blocking if > 1 % of lines, else warning | rows dropped |
| R2 | ordered SKU absent from the master | info ≤ 1 %, warning > 1 %, blocking > 5 % | kept, `has_dims = false` |
| R3 | `qty_units = 0` | warning | rows dropped |
| R4 | `qty_units < 0` | info | `is_return = true` |
| R5 | exact duplicate rows (also across files) | warning | deduplicated; a repeated SKU in the master keeps its first row |
| R6 | same (order, SKU, status, direction) on several rows | info | summed if `merge_duplicate_sku_lines` (a return is never summed into a sale) |
| R7 | dims or weight missing on a SKU | warning if line coverage < 95 %, else info | counted; drives eligibility |
| R8 | dim ∉ [1, 3000) mm, weight ∉ [0.001, 1500) kg, pack quantity < 1 | warning | value set to null |
| R9 | history < 3 months | **blocking** | stop (exit 3) |
| R10 | history < 12 months | warning | seasonality flagged L |
| R11 | > 90 % of quantities are whole cases (SKUs with case > 1) | warning | asks whether quantities are units or cases |
| R12 | zero-order days on usual operating weekdays > 5 % | warning | calendar review |
| R13 | lines per order or units per line > median + 10 × max(MAD, 1) | warning | listed, never removed |
| R14 | latest snapshot > 6 months before the last order, or none | warning | stock flagged L |

Constants (`io/rules.py`, all `[P]` except where noted): `R1_BLOCKING_SHARE` 0.01, `R2_WARNING_SHARE`
0.01, `R2_BLOCKING_SHARE` 0.05, `R7_MIN_LINE_COVERAGE` 0.95, `R9_MIN_MONTHS` 3, `R10_MIN_MONTHS` 12,
`R11_MULTIPLE_SHARE` 0.90, `R12_MAX_ZERO_DAY_SHARE` 0.05, `R13_MAD_K` 10, `R13_MAD_FLOOR` 1 (`[EXPERT]`, I53),
`R14_MAX_AGE_MONTHS` 6. History is measured in calendar months (I52: whole months + leftover days / 30.4375). A
"usual operating weekday" is a weekday with orders in ≥ 50 % of its weeks (an F2 choice).

Hidden assumptions and rulings:

- **R13 MAD floor** (I53, `[EXPERT]`): with a MAD of 0 (most orders of one line, most lines of one
  unit) the verbatim `median + 10 × MAD` would list every multi-unit line; the floor of 1 unit
  avoids that. To confirm.
- **R6** merges only lines of the same status and direction; the merged line is one *line* in F3
  (a line is a distinct (order, SKU)).
- **R11** cannot know the unit; it asks. A client who sends cases as units inflates everything by
  `units_per_case`.
- A missing required column in a canonical table written by F2 is an integrity failure (exit 1),
  not a data defect (exit 3) (I72).

### 1.3 DQ score and band

`score = 100 − 25·min(blocking, 2) − 5·min(warnings, 5) − 20·(1 − dims_coverage_lines) − 10·[history < 12
months]`, clipped to [0, 100] (`io/dq.py`: `BLOCKING_POINTS` 25 cap 50, `WARNING_POINTS` 5 cap 25, `DIMS_POINTS`
20, `SHORT_HISTORY_POINTS` 10, all `[P]`). Bands: ≥ 80
*usable*, 60 to 79 *usable with caveats*, < 60 *remediation needed*, printed on the report cover.
`dims_coverage_lines` is the share of order lines whose SKU has dims and weight; `blocking` counts
`RuleResult`s, so one rule on two datasets counts twice. On the 13-month synthetic demo of `runbook.md` the score is
100 (only R4 informs); two warnings and a coverage of 0.90 would give 100 − 10 − 2 = 88.

### 1.4 Anonymisation (C2)

`HMAC-SHA256(salt, id)[:16]` on `order_id`, `sku`, `receipt_id` and `customer`; `description` and `customer`
columns are dropped unless `--keep-descriptions` (a kept customer column is still hashed). The salt comes from
`--salt-file` (refused if it lies inside a git repository) or `$WHSIZING_SALT`; none is exit 2. The
correspondence table is never written. The tool hashes identifiers, not free text: anything else in a kept
column leaves the machine only if you send it.

## 2. Demand profile (F3)

Purpose: quantify demand and its variability, the basis of every sizing decision. Code: `src/whsizing/profile/`;
output `profile/demand_profile.json` and `canonical/daily_series.parquet`. `[P]` values live in `ProfileCfg`
(`schemas/profile.py`, overridable in `project.yaml: profile_cfg`).

**Definitions (I1).** A *line* is a distinct (`order_id`, `sku`) after R6; shipped lines have status `shipped`
(or null) and `qty > 0`; cancelled and returned lines are out. Every line takes its order's first timestamp in
`basis.timezone` (multi-day orders), which gives its local date and hour. Golden: 968 orders, 1 881 lines, 2 682
units (`profile.n_orders`, `profile.n_lines`, `profile.n_units`).

| Step | Formula | Rationale and hidden assumption | Register / values |
|---|---|---|---|
| Operating day | `lines_d ≥ max(1, 0.10 × median(lines_d > 0))` | Sizing on a closed Sunday would drag every percentile down. The threshold is relative, so a site with a small Saturday shift counts it. The "holiday with no volume" clause adds nothing: no volume already fails the test | I2; `operating_day_threshold` 0.10 `[P]`. Golden: threshold 7.55 (= 0.10 × 75.5), 26 operating days of 31 (`profile.operating_threshold`, `profile.operating_days`) |
| Series stats | mean, P50/P90/P95/P98 (`np.percentile`, linear), max, `CV = std(ddof=0)/mean` over operating days | Linear interpolation is the numpy default; with 26 days P95 interpolates between the two largest | I3. Golden `daily.lines.p95` = 113.0, mean 72.35, CV 0.377 |
| EIQ | lines/order, units/line, units/order, cube and weight per order, single-line share, classes S (1 line), M (2-5), L (> 5) | Distributions are over all shipped orders or lines, not per day | I3; `order_class_bounds` (1, 5) `[P]`. Golden: single-line share 0.602, S/M/L = 0.602/0.372/0.026 (`eiq.order_class_share.*`) |
| ABC | SKUs sorted by lines (ties: units, avg stock, unit cube, weight, all descending, then `sku`); class from the cumulative share *before* the SKU: A < 0.80, B < 0.95, else C | A SKU that crosses 80 % is A, so `A.line_share ≥ 0.80` (T3.2). The tie-break chain makes the classes independent of the salt (§0.5) | I6; `abc_thresholds` (0.80, 0.95) `[P]`. Golden: A = 28 SKUs / 80.5 % of lines, B = 37 / 14.5 %, C = 35 / 4.9 % (`abc.lines.*`) |
| Stock | `avg_stock_i = Σ qty over snapshots / n snapshots` (absent from a snapshot = 0); `cover_days = Σ avg stock / mean daily units`; dead stock = in the last snapshot and no line in the last 180 days; growth = OLS slope if ≥ 3 snapshots | A SKU missing from a snapshot is taken as zero stock (WMS exports omit zero rows). Stock is the *average* of snapshots, not the peak (the peak factor is in F4) | I49, I50; `dead_stock_days` 180 `[P]`. Golden: avg 5 797 units, cover 56.2 days (`stock.avg_units`, `stock.cover_days`) |
| Seasonality | monthly index = mean daily lines in the month ÷ overall mean; weekday index; `peak_to_average = P95/mean`; `trend_cagr = exp(12 × slope(log monthly mean lines ~ month)) − 1`, confidence L < 24 months, M 24-36, H > 36 | Means, not totals, so partial boundary months do not bias the trend. Under 12 months the seasonality is flagged L (R10); the trend is L under 24 months | I52. Golden: `seasonality.peak_to_average` = 113 / 72.35 = 1.562; one calendar month so `trend_cagr` null, confidence L |
| Intraday | share of lines per (weekday, hour) on operating days; `peak_hour_share` = max share on the design weekday (highest mean lines, lowest index on ties) | Lines without a time (00:00:00) are left out of the shares; above 20 % of them every weekday takes the default profile (flat 08:00-17:00, 1/9 per hour) and the profile is flagged L. Exactly 20 % keeps the measured shares | I7, I51; `no_time_share_max` 0.20, `default_intraday` `[P]`. Golden: design weekday 0 (Monday, mean 93.6 lines), `design_day.peak_hour_share` 0.1368 |
| Shipment split | pallet order if weight > `pallet_order_weight_kg` or cube > `pallet_order_cube_m3`: 1 pallet, 0 parcels; else `max(1, ceil(weight / parcel_max_weight_kg))` parcels | The 300 kg / 0.6 m³ / 30 kg defaults come from the basis (`flows`) and `[P]`; a pallet order is one pallet whatever its weight | I8. Golden (low thresholds): 4.03 % pallet orders (39 of 968), 1.166 parcels per parcel order |
| Coverage | `dims_coverage_lines` = share of lines whose SKU has dims and weight | Feeds the DQ score and the eligibility caveat | I10 |

Edge cases honoured: a single inventory snapshot (growth n/a), one calendar month (trend n/a), no inventory
(zero stock per SKU, cover 0, R14 warning), orphan SKUs (shipped but not in the master, or in stock only) are
kept as SKU rows with no master data and are never eligible (I10, I50).

## 3. Design day and inbound (F4)

Purpose: capture the client's operating assumptions and define the demand level the site is sized for. Code:
`src/whsizing/design/`; `design/design_day.json`, `design/assumptions.json` (one `Assumption` per basis field,
origin `default | client | override | derived`; the report appendix prints it).

### 3.1 Design day

1. **Candidate days** = operating days in the trailing window. A `trailing_months` set in the basis
   is used as given; left at its default the window is 24 months when the history covers ≥ 23.9
   calendar months, else 12 (I55). Fewer than 12 months of window: a warning; fewer than 60
   candidate days: `F_SHORT_HISTORY` (I5, I70).
2. `P_m = percentile(candidates[m], p)` for `m ∈ {lines, orders, units, cube_m3, weight_kg,
   parcels, pallets_out}`; `p` = `projection.design_percentile` (default 95 `[P]`, clipped to 100
   with `F_PERCENTILE_CLIPPED`).
3. **Reference day** `r` = the actual day whose lines are nearest `P_lines` (the earliest on a
   tie, I7). Ratios `ρ_m = m_r / lines_r`.
4. Base values `lines* = P_lines`, `m* = lines* × ρ_m`; `F_RATIO_DRIFT:<m>` when `|m* − P_m| / P_m >
   15 %` (`RATIO_DRIFT_MAX`, `[P]`); with `P_m = 0 < m*` the drift is unbounded and the flag is
   raised too (I57).
5. **Growth**: every capacity metric × `gf = (1 + g)^T`. Capacity is sized for the **end of the
   horizon** (a conservative reading: the site must cope in year `T`); yearly costs use `(1 + g)^t`
   (§5.3, I41).
6. Design weekday = highest mean lines; `hourly_lines = intraday[weekday] × lines*` (sums to `lines*`,
   T4.3); `peak_hour_lines = max`.
7. Stock: `stock_units* = avg stock × peak_stock_factor × (1 + g_stock)^T` (default `g_stock = g`;
   override with `overrides["stock_growth_rate"]`, the only basis-level override key). The factor
   1.15 is `[P]`.

Rationale: a percentile of *actual days* keeps the demand structure coherent (the ratios come from one real day)
instead of stacking the P95 of every metric, which would describe a day that never happened; the drift flag says
when the two readings differ.

Hidden assumptions: demand history repeats (no promotion calendar is forecast); the design day is a
weekday-agnostic percentile while the hourly profile is that of the busiest weekday (a deliberate conservative
pairing); stock scales with demand unless overridden.

Worked numbers (golden, P95, g = 4 %, T = 5): `design_day.p.lines` = 113.0, reference day 2025-03-10
(`design_day.reference_date`), `design_day.ratio.orders` = 0.4912, so `design_day.base.orders` = 113 × 0.4912 =
55.51; `design_day.growth_factor` = 1.04⁵ = 1.21665, so `design_day.lines` = 113 × 1.21665 = **137.48** and
`design_day.orders` = 67.53. Drift: `design_day.base.weight_kg` 174.5 vs `design_day.p.weight_kg` 139.8 (+24.8
%) and `design_day.base.pallets_out` 1.98 vs 3.75 (−47 %) raise `F_RATIO_DRIFT:weight_kg` and `:pallets_out`
(the 15 % threshold; orders drift only 4.7 %). `design_day.peak_hour_lines` =
137.48 × 0.13675 = 18.80. `design_day.stock_units` = 5 797 × 1.15 × 1.21665 = 8 110.9.
31 days, 26 operating: `F_SHORT_HISTORY` (`design_day.flags`).

### 3.2 Inbound

- **Receipts mode**: the percentile `P_p` of the daily receipts (units, pallets, lines) over the
  candidate days × `gf` (I56); trucks = pallets / `pallets_per_truck`. `Inbound.peak_factor` is
  `flows.inbound_peak_factor` or **1.0** (the spec's "outbound peak-to-average" fallback is a
  derived-mode fallback: `P_p` is already a design-day value, so applying a second peak would
  double count, I56). Days with an unknown pallet count are left out of the pallet percentile only.
  Receipts mode without receipts in the window, or none on a candidate day, is a `ConfigError`,
  never an all-zero inbound (I71); `F_INBOUND_SPARSE` and `F_RECEIPTS_NO_PALLETS` (warnings) cover
  receipts that exist but size the inbound at 0 (I77).
- **Derived mode** (default): `units_in/day = mean outbound units/day × gf + Δstock_per_year /
  operating_days_per_year`; Δstock is the OLS slope of the snapshot totals with ≥ 3 snapshots, else
  0 (I12; the oracle raises `NotImplementedError` with ≥ 3 snapshots, the golden case has one). Per SKU
  `units_in_i = units_in × U_i / Σ U` (`U_i` shipped units over the period), `pallets_in_i =
  units_in_i / units_per_pallet_i` (fractional), `receipt_lines = Σ pallets_in_i × k_i`, `k_i = 1`
  when at least a full pallet a day else 4, `cases_in_i = units_in_i / units_per_case_i` (I13).
  Fallbacks, never a division by zero: `units_per_pallet` = given, else `units_per_case ×
  cases_per_pallet`, else `storage.default_units_per_pallet` (400, flagged `F_DEFAULT_UPP`, I59);
  `units_per_case` = given, else `units_per_pallet / cases_per_pallet`, else 1 (each unit decanted
  as a case: the largest decant workload). `peak_factor` = `flows.inbound_peak_factor` or the
  outbound peak-to-average.
- Hidden assumptions: inbound is the same SKU mix as outbound; one pallet per 400 units is a
  default, not a fact; a site whose stock grows or shrinks fast needs `receipts` mode.

Worked numbers: `inbound.units_per_day` = mean `daily.units.mean` 103.15 × 1.21665 = 125.50;
`inbound.peak_factor` = `seasonality.peak_to_average` = 1.562; `inbound.pallets_per_day` 0.524,
`inbound.trucks_per_day` = 0.524 / 26 = 0.0202.

`[P]` values: `engine.receipt_lines_per_pallet_full` 1.0 and `_mixed` 4 (`catalog/engine_defaults.yaml`),
`storage.default_units_per_pallet` 400 (`catalog/storage_classes.yaml`), `pallets_per_truck` 26,
`peak_stock_factor` 1.15 (basis). Basis checks (`check_basis`, I60): NaN or infinite values, non-positive
divisors and out-of-range shares are `ConfigError` before the engine sees them.

## 4. Catalog and eligibility (F5)

Purpose: neutral, traceable equipment data and the share of the range each family can handle. Code:
`src/whsizing/catalog/`; data: `catalog/` (`catalog/README.md` explains ids, the strict loader and governance).

- **Catalog**: three families (`manual_p2p`, `amr_gtp`, `cube_asrs`), `labor_standards.yaml`,
  `finance_defaults.yaml`, `storage_classes.yaml`, `area_factors.yaml`, `icpe_1510.yaml`,
  `engine_defaults.yaml`. A ranged value is a full `Param` (`min ≤ typ ≤ max`, unit, `source`,
  `confidence`, `pessimistic_end`, `date`); scalars are structural constants. The loader is strict
  (`ConfigError`, exit 2, names file and key) and warns for `source: TODO`
  (`Catalog.todo_count`). 72 Param blocks: manual_p2p 19, amr_gtp 20, cube_asrs 21, labor 9, finance
  2, engine 1 (I47); `docs/assumptions.md` lists them. `whsizing validate-catalog catalog` checks a
  folder and lists the TODOs.
- **Governance**: a change is a pull request reviewed by the `[EXPERT]`; `validated_by` and `date`
  are updated, `catalog/CHANGELOG.md` gets an entry; no brand name, quotation or client data;
  ranges come from public documentation and expert judgment only. A single-site calibration may
  change `typ` only within the current range (§9).
- **Eligibility** (`eligibility.py`, I10): per SKU sort `(l, w, h)` descending against the sorted
  `max_item_mm` (orientation-agnostic); weight ≤ `max_weight_kg` (and ≤ `extra_max_weight_kg`);
  hazmat excluded when the family says so; temperature class in the family's list. Logic is
  three-valued (Kleene): any *known* violation is **ineligible whatever the flag**; otherwise a
  SKU with a missing dim or weight is ineligible unless `assume_eligible_if_missing_dims`, then
  eligible by assumption and reported as `assumed_share_lines` (`F_ELIG_ASSUMED`). A null `hazmat`
  is not hazmat, a null temperature class is ambient. Orphan SKUs are never eligible. Shares
  (F5 step 4): by lines (`Σ lines of eligible SKUs / Σ shipped lines`, orphans included), by stock
  cube (0 when there is no stock cube) and by SKU count; the complement is the **overflow**, routed
  to the manual family with its own storage, labor and capex. `F_ELIG_LOW` when < 50 % of lines
  (`engine.elig_low_line_share`).
- Hidden assumptions: eligibility is purely geometric and by weight; no nesting, stackability or
  fragility. `units_per_bin = floor(bin_net_cube × fill / unit_cube)` is volumetric (a nesting
  factor is backlog). Missing dimensions are treated as unknown, not as small.

Worked numbers (golden): `eligibility.cube_asrs.share_lines` = 0.8974 with 91 of 100 SKUs eligible
(`n_skus_eligible`, family default, T5.3); the scenario S2 adds `extra_max_weight_kg: 2.0`, which removes 5
SKUs: `S2.eligibility.share_lines` = 0.7411, 86 SKUs, `S2.eligibility.share_stock_cube` = 0.2547 (I44). The cube
family limits `[600, 400, 300]` mm and 25 kg are in `catalog/families/cube_asrs.yaml`.

## 5. Sizing engine (F6)

Order: eligibility → storage → throughput and equipment → labor → area → queue → flags, once per world
(`engine/size.py`). Inputs: the per-SKU frame (I58, `sku_frame`), the F3 `daily` series and the shipped `lines`
(I61). Constants come from `catalog/` (ids in brackets).

### 5.1 Storage (F6a)

**Storage class** per SKU (design stock `s_i = avg_stock_i × stock_units* / Σ avg_stock`, I14, I63):

```
cube_asrs and eligible → cube_bin        amr_gtp and eligible → pod_bin
otherwise (manual family and overflow):
  not fits_shelf or s_i × v_i ≥ 0.6 m³   → pallet_rack           [storage.pallet_threshold_m3]
  s_i × v_i ≤ 0.04 × 6 m³                → shelving              [storage.shelf_bin_net_cube_m3, max_bins_per_sku_shelf]
  else                                   → pallet_rack
```

`fits_shelf` tests the dims only against `[500, 400, 350]` mm (`storage.shelf_item_max_mm`); a SKU with an
unknown dim does not verifiably fit and goes to the rack (I10). SKUs with `s_i = 0` take no position (I14).

**Positions and footprint** (density includes aisles):

```
pallet_rack: positions = Σ ceil(s_i/upp_i) / fill_pallet + n_A/B_SKUs   (pick faces, I11)
             levels = min(max_levels, floor((H − top_clearance)/(load_height + beam_pitch)))
             A = positions / (levels × positions_per_m2_per_level)
shelving:    positions = Σ max(1, ceil(sc_i /(bin_net_cube × fill)))        levels = min(ergonomic, floor(shelf_max_height/bin_pitch))
cube_bin:    bins_i = max(1, ceil(sc_i/(bin_net_cube × fill))),   1/4 when sc_i < 0.2 × bin_net_cube (mixed bins)
             bins_total = Σ bins_i × (1 + empty_bin_reserve)     levels = min(max_levels, floor((H − grid_overhead)/level_height))
             A_grid = bins_total/(levels × bins_per_m2_per_level)  A = A_grid × (1 + service_aisle_share)
pod_bin:     pods = ceil(bins_total / bins_per_pod)    A = pods × pod_footprint_m2
```

Rationale: pallet rack for anything that does not fit a shelf bin or would fill 0.6 m³; shelving for slow small
SKUs; the **pick face** policy gives every A or B SKU in the rack one extra position (the whole design stock
still counts in `pallets`, I11). Levels are floored with a 1e-9 tolerance (I63 11) and are ≥ 1; a pallet-rack or
cube class whose levels are capped by the *building* (not the catalog) raises `F_HEIGHT_LIMIT:<class>` (I40).
Nothing is rounded unless the spec writes ceil/floor (I39), so positions, bins and areas are fractional.

Hidden assumptions: one SKU per shelf bin; fill factors average honeycombing and half-empty bins; pallets are
not shared between SKUs; the stock of an eligible SKU sits entirely in the automated store; the pick face is a
*position*, not a separate area.

Worked numbers (golden, S0): rack `pallets` = 44, fill 0.85: 44 / 0.85 + 16 pick faces = 67.76
(`S0.storage.pallet_rack.positions`); levels = floor((8.5 − 0.6) / (1.40 + 0.15)) = 5, capped by the building
(`F_HEIGHT_LIMIT:pallet_rack`); `A` = 67.76 / (5 × 0.38) = 35.67 m² (`S0.storage.pallet_rack.area_m2`).
Shelving: 184 bins / (5 × 8) = 4.6 m². S2: `cube_bin.bins_raw`
240.75 × 1.05 = 252.79 bins; levels = min(20, floor((8.5 − 1.2) / 0.33) = 22) = 20; `A_grid` =
252.79 / (20 × 3.0) = 4.21 m², `A` = 4.21 × 1.08 = 4.55 m² (`S2.storage.cube_bin.area_m2`); the
overflow zone (9 rack SKUs, 2 shelving SKUs) adds 22.35 + 0.275 m² (`S2.storage.overflow.*`, I43).

`[P]` / `[EXPERT]` values: `catalog/families/*.yaml` (densities, fills, levels, bin cubes, pitches),
`catalog/storage_classes.yaml`.

### 5.2 Throughput and equipment (F6b)

```
λ      = max(peak_hour_lines / η_flow,  same_day_share × lines* / sla_window_hours)     (I16)
λ_e    = λ × share_lines_eligible ;  λ_o = λ − λ_e        (manual family: share = 1)
manual: pickers_peak = Σ_zone ceil(λ_zone / (pick_rate_zone × η_pick))                  (I17)
        forklifts = ceil((pallets_in × peak_factor × 0.2 + (pallets_out + replen_moves) × peak_hour_share) / forklift_moves_h)   (I18)
amr:    stations = ceil(λ_e/(station_rate × oee)); robots = ceil(λ_e/lines_per_pod_visit / (robot_moves_h × availability) × (1 + charging_reserve))
cube:   ports = ceil(λ_e/(port_rate × oee) + decant_port_load_peak_h)                  (I23)
        robots = ceil(λ_e/lines_per_bin_presentation × dig_factor / (robot_bins_h × availability))
bottleneck = resource with the highest utilisation at typ (load before ceil / count, I20)
```

- `sla_window_hours` = `service.sla_window_hours`, else `carrier_departure − cutoff` modulo 24 h
  (equal times give 24 h, never 0, I16). The SLA term is the "wave-driven" alternative: lines that
  must ship today arrive between cut-off and departure.
- `η_flow` 0.85 `[P]` (`engine.eta_flow`), `peak_hour_share_inbound` 0.2 (`area.peak_hour_share_inbound`,
  the spec writes it for a 5-hour receiving window while `receiving_window_hours` is 8: kept
  verbatim). `η_pick` only enters `pickers_peak`, `oee` only enters stations and ports; the labor
  hours use the bare rate (I38).
- Cube **decant** is done *at the ports* in the inbound peak hour: `decant_station_hours =
  cases_in / decant_cases_per_h`, `decant_port_load_peak_h = decant_station_hours × inbound_peak_factor
  × 0.2`, conservatively coincident with the outbound peak (I23).
- Replenishment (manual and overflow): `replen_moves = units* × (period units of A/B SKUs in manual
  zones / period units) / replen_units_per_move` (I21). In S2 only the overflow counts.
- `F_SCALE_LOW` when `lines* <` `<family>.min_scale_lines_day` (cube 1 500, amr 800, manual 0);
  `F_ROBOT_DENSITY` when robots per grid m² (cube) or per pod m² (amr) exceed
  `max_robots_per_m2` (0.05 `[P]`, `[EXPERT]` I46).

Hidden assumptions: peak-hour flow is the design-day lines times the busiest-weekday hourly share (coincidence
of all peaks); `ceil` per zone, then summed, can overstate pickers (I17) or, when stock grows with demand,
*understate* them (I68); the robot formulas are throughput-only (no traffic or battery model beyond
`charging_reserve`).

Worked numbers (golden): `S0.throughput.lambda_peak` = 18.80 / 0.85 = 22.12 lines/h; `S0.throughput.lambda_sla`
= 0.6 × 137.48 / 3.5 h = 23.57 (window 18:30 − 15:00): **the SLA term binds**, `S0.throughput.lambda` = 23.57.
S2: `S2.throughput.lambda_e` = 23.57 × 0.7411 = 17.47 and `lambda_o` = 6.10. `S2.equipment.decant_station_hours`
0.713, `decant_port_load_peak_h` = 0.713 ×
1.562 × 0.2 = 0.2226; ports load = 17.47 / (350 × 0.85) + 0.2226 = 0.0587 + 0.2226 = 0.2813 →
`S2.equipment.ports` = 1 (`S2.utilisation.ports` 0.281). Robots: `bin_presentations_h` = 17.47 / 1.3 =
13.44; load = 13.44 × 1.6 / (22 × 0.95) = 1.029 → `S2.equipment.robots` = 2, `S2.utilisation.robots`
= 0.514, bottleneck `robots`; robots per grid m² = 2 / 4.21 = 0.475 > 0.05: `F_ROBOT_DENSITY` (open value, I46).
S0: one picker per zone (`S0.equipment.pickers_peak` 2), utilisation 0.311.

### 5.3 Labor (F6c)

```
hours_a      = workload_a / productivity_a × (1 + PF&D)                         (design day)
heads_a      = hours_a / (paid_hours_per_person_day × utilisation)
heads_shift  = max(1, hours_shift / (hours_per_shift × utilisation))  if staffed else 0   (I19)
roster       = Σ_a Σ_shift heads_shift × (1 + absenteeism)
annual_hours_{a,t} = Σ_{operating days d} workload_{a,d} × operating_days_per_year / n_op × (1 + g)^t / productivity_a × (1 + PF&D)
core_fte_t   = annual_hours_t / (annual_paid_hours_per_fte × utilisation)
core capacity = P50 of the daily hours (core heads = P50 / (paid_hours × utilisation)); temp_hours_t = Σ_d max(0, hours_d − P50) × 252/n_op × (1 + g)^t   (I25)
```

- Activities, drivers and standards: `catalog/labor_standards.yaml` (Appendix D table): receiving
  (pallets_in), receipt_check (receipt lines), put_away, decant (cases, cube and AMR),
  replenishment, picking (per zone at the family rate), packing_S / packing_ML (orders by class,
  I15, I66), shipping_parcel / shipping_pallet, returns, indirect = 0.12 × direct hours (no second
  PF&D, I38). Each maps to a role (forklift driver, operator, team leader) priced in F7.
- **Annual hours come from the daily series, never `D* × 365`** (I4): any annual total from a short
  series is `Σ_d x_d × operating_days_per_year / n_op` (`× 252 / 26` on 31 days). T6.10 guards it.
- Returns workload is `returns_rate × lines` on every day (I9); the returned lines in the data are
  informational.
- Multi-shift (I65): shift 1 starts at the inbound window start (06:00), shifts run back to back,
  outbound hours follow the intraday profile lagged 1 h, inbound is flat over 06:00-14:00; the floor
  of 1 head applies per shift (`[EXPERT]`: about +4 heads on ecom_mid S0 with 2 × 7 h). The golden
  case has one shift.
- Receipts mode (I64): daily inbound workloads are the day's receipts; with lumpy receipts most
  inbound hours sit above the P50 day and temp hours dominate (`[EXPERT]`).

Hidden assumptions: productivity is constant across the day and the volume (no learning curve, no congestion);
PF&D and utilisation are separate haircuts; the **floor of one head per staffed activity** makes a tiny site
look heavy (11.7 heads for 7.9 hours, which is what pushes S2 over the area, §5.4); temp hours are the hours
above the median day, i.e. the core team is sized for a typical day, which is a labour-policy choice.

Worked numbers (golden S0): picking hours = 78.50 rack lines / 35 × 1.12 + 58.98 shelving lines / 70 × 1.12 =
2.512 + 0.944 = 3.456 h (`S0.labor.picking.hours`); heads = 3.456 / (7.0 × 0.85) = 0.581; shift heads = max(1,
3.456 / (7.5 × 0.85)) = 1; 11 staffed activities × 1 × 1.06 = 11.66 (`S0.labor.total.roster`) for
`S0.labor.total.hours` 7.93 h. Annual: `S0.labor.annual_hours.y1` = 1 128 h against 7.93 h × 252 = 1 997 h,
because the series average day is far below the design day (T6.10); `S0.labor.core_fte.y1` = 1 128 / (1 607 ×
0.85) = 0.826; `S0.labor.p50_day_hours` 4.47, `S0.labor.temp_hours.y1` 141 h.

`[VERIFY]`: `annual_paid_hours_per_fte` 1 607 (French 35 h basis, `basis` template). `[EXPERT]`: every standard
in `labor_standards.yaml`, `outbound_lag_hours`, `inbound_window`, the indirect share.

### 5.4 Area budget and docks (F6d)

```
receiving_staging = pallets_in × peak_factor × 1.5 m² × 1.0 day        [area.m2_per_pallet_staged, staging_days]
shipping_staging  = (pallets_out + parcels/40) × 1.5
packing           = pack_stations × m2_per_pack_station (12)        pack_stations = ceil(peak_hour_orders / (pack_rate × 0.85))
                    peak_hour_orders = orders* × peak_hour_share ;  pack_rate = order-weighted harmonic mean of packing_S, packing_ML (I24)
gtp / ports       = stations_or_ports × m²                                                  (I26)
storage           = F6a total
returns           = returns_rate × lines* × 0.05 + 30
equipment         = robots × cube_asrs.m2_per_robot_parking + 40                           (I26, I63 12)
amenities         = roster × 4 + 150      (inside the footprint, I27)
circulation       = 0.25 × Σ zones except storage
total = Σ ; fit = total ≤ building.area_m2 ; F_NO_FIT with deficit_m2
docks = ceil(trucks_peak_h × dwell / dock_utilisation) ; F_DOCK_SHORTFALL if > doors   (I28)
icpe  = lookup(area × clear height) in icpe_1510.yaml : informational label only [VERIFY]
```

All constants are `[P]` in `catalog/area_factors.yaml`; `pack_station_oee` 0.85 is `engine.pack_station_oee` (no
spec value: analog of `amr_gtp.oee`, a Param). Hidden assumptions: amenities scale with the *roster* (not the
design-day heads), so the floor of 1 head per activity feeds the area; circulation is a flat 25 % of everything
but storage; ICPE 1510 depends on stored combustible volume and cell design, not building volume, so the label
is a prompt to ask an ICPE office, never a classification (`[VERIFY]`, `icpe_1510.yaml`). `F_AMENITIES_EXTERNAL`
is never raised (I27).

Worked numbers (golden): `S0.area.peak_hour_orders` = 67.53 × 0.13675 = 9.236; pack rate = 1 / (0.6023 / 55 +
0.3977 / 25) = 37.23 orders/h (`S0.area.pack_rate`); `pack_stations` = ceil(9.236 / (37.23 × 0.85)) = 1. S0
amenities = 150 + 4 × 11.66 = 196.64 m²; circulation 71.68; `S0.area.total` = **398.64 m²** of 410 (utilisation
0.972, fits). S2: robots 2 × 2.0 + 40 = 44 m², ports 1 × 20, `S2.area.total` = 420.85 m² > 410: `F_NO_FIT`,
`S2.area.deficit_m2` = 10.85. The margins (2.7 %) exceed the 0.5 % test tolerance so `fit` cannot flip within
tolerance.

### 5.5 Queue / SLA check (F6e)

Erlang-C on the pack stations and, for the cube, the ports (I45):

```
B_0 = 1 ; B_k = a B_{k−1} / (k + a B_{k−1})          P_wait = B_c / (1 − ρ + ρ B_c), ρ = a/c, a = λ_s/μ < c
W_q = P_wait / (cμ − λ_s) ;   P(W > t) = P_wait × exp(−(cμ − λ_s) t),  t = sla_window_hours × 0.5
F_SLA_RISK if P(W > t) > 5 % ; F_UNSTABLE if a ≥ c  (then c_min = ceil(a) + 1)
```

Pools: packing `c = pack_stations`, `μ = pack_rate × 0.85`, `λ_s = max(peak_hour_orders, same_day_share ×
orders* / sla_window_hours)`; ports `c = ports`, `μ = port_rate × oee`, `λ_s = λ_e + decant_port_load_peak_h ×
μ`. Hidden assumptions: Poisson arrivals and exponential service (M/M/c), steady state, no balking; it is a
*check* on a sizing, not a sizing: there is no feedback from F6e to F6d. With a short SLA window and a high
same-day share the check can report `F_UNSTABLE:packing` and `c_min` while the budget keeps `pack_stations`
(I69, `[EXPERT]`). `erlang_c(1, 0.5) = 0.5` and `erlang_c(2, 1.0) = 1/3` are tested (T6.4).

Worked numbers (golden S0 packing): `λ_s` = max(9.236, 0.6 × 67.53 / 3.5 = 11.577) = 11.577 orders/h
(`S0.queue.packing.arrival_rate_h`, the SLA term binds), `μ` = 37.23 × 0.85 = 31.65 (`service_rate_h`), `a` =
0.3658 (`offered_load`); for one station `P_wait = a = 0.3658` (`p_wait`), `W_q` = 0.3658 / (31.65 − 11.58) =
0.0182 h (`w_q_h`), `t` = 1.75 h, `P(W > t)` ≈ 2e-16: no flag. Constants: `engine.sla_wait_threshold_share` 0.5,
`engine.sla_risk_max_probability` 0.05.

### 5.6 Flags

`F_NO_FIT`, `F_HEIGHT_LIMIT:<class>`, `F_ELIG_LOW`, `F_ELIG_ASSUMED:<share>`, `F_SCALE_LOW`, `F_ROBOT_DENSITY`,
`F_DOCK_SHORTFALL`, `F_UNSTABLE:<pool>` / `F_SLA_RISK:<pool>`, the design-day flags (`F_SHORT_HISTORY`,
`F_RATIO_DRIFT:<m>`, `F_PERCENTILE_CLIPPED`, `F_INBOUND_SPARSE`, `F_RECEIPTS_NO_PALLETS`, `F_DEFAULT_UPP`), then
`F_LOW_CONFIDENCE:<n>`, in this order (I46, I77). `n` is the number of distinct confidence-L catalog Params the
scenario's formulas read in F6 and F7 (I47; golden S0 = 30, S2 = 50). F9 translates them. `F_NO_FIT` is a
warning; with `--strict` a run where no scenario fits exits 4 (I75 f).

## 6. Finance (F7)

Code: `src/whsizing/finance/`; `scenarios/<id>/finance.json`. Costs are computed in each world (F6 quantities of
that world × cost Params of that world).

**Capex (year 0)** (I29-I31): `storage + equipment + controls + building works + overflow + (integration +
commissioning) × equipment + contingency × (all others)`.

| Item | S0 manual | S2 cube |
|---|---|---|
| storage | pallet positions × `per_pallet_position_eur` + shelving bins × `per_shelf_bin_eur` | bins_total × `per_bin_eur` + A_grid × `grid_structure_per_m2_eur` |
| equipment | carts × `per_cart_eur` + forklifts × `per_forklift_eur` | robots × `per_robot_eur` + ports × `per_port_eur` |
| controls | `manual_p2p.wms_adaptation_fixed_eur` (50 000; not `wms_adaptation_default_eur`) | `controls_fixed_eur` |
| building works | `area.total × building_works_per_m2_eur` | same + A_grid × `cube_asrs.floor_prep_per_m2_eur` |
| overflow | 0 | overflow positions × 90 + bins × 12 + carts × 1 500 + forklifts × 35 000 |

AMR (`amr_gtp`): pods × `per_pod_eur`, robots × (`per_robot_eur` + `charging_per_robot_eur`) + stations ×
`per_station_eur`, floor prep × pod storage area; **no golden case, `[EXPERT]`** (I73 d). A degenerate cube
scenario (zero eligible lines) costs what the manual family costs (I48).

**Opex (years 1..T)**: `labor_t + maintenance + energy_t + software + consumables_t + rent + renewal_t`.

- `labor_t = [Σ_a annual_hours_{a,t} × cost(role_a) × (1 + shift_premium) + temp_hours_t ×
  cost_operator × (1 + temp_premium)] × (1 + wage_inflation)^(t−1)`. **I33**: temp hours are part of
  the annual hours, so this counts them twice; kept literal for the expert to rule on (open).
- `maintenance = share × equipment item` (storage, controls, works excluded), flat; `energy_t =
  (robots × kWh_robot + stations × `finance.kwh_per_station_year` (1 500 typ) + forklifts × `kwh_per_forklift_year` + 20 000 fixed) × price × (1 +
  energy_inflation)^(t−1)` (I32); `software` flat; `consumables_t = annual orders_t × packaging_eur_per_order`
  with `annual orders_t = Σ_d orders_d × 252 / n_op × (1 + g)^t` (I35); `rent = area.total ×
  rent_eur_m2_year` (`footprint`), `building.area × rent` (`full_building`, equal across scenarios,
  cancels in deltas) or 0 (I73 f); `renewal = renewal_share × equipment item` in year
  `equipment_life_years` only (never for the overflow items).
- Growth exponent: capacity uses `(1 + g)^T`, year `t` of labor and orders uses `(1 + g)^t`, `t`
  from 1, so year 1 already carries one year of growth; finance years use `finance.horizon_years`
  (I41).

**Metrics**: `TCO = capex + Σ_t opex_t / (1 + r)^t`; `Δcf_0 = −(capex_s − capex_b)`, `Δcf_t = opex_b,t −
opex_s,t`; `NPV = Σ_t Δcf_t / (1 + r)^t` with `Δcf_0` undiscounted (I42; equals `numpy_financial.npv`); IRR only
with exactly one sign change in `Δcf` (zeros ignored), else `None` (I37); payback = first year with a cumulative
undiscounted `Δcf ≥ 0`, interpolated, `None` if not reached, 0 when the capex delta ≤ 0; `cost_per_line = TCO ×
r / (1 − (1 + r)^−T) / annual_lines_1`, `annual_lines_1 = Σ_d lines_d × 252 / n_op × (1 + g)` (I36).

**Baseline**: a scenario id (`baseline: S0`, capex is that scenario's computed capex, I42) or `client_current`
(capex 0, sunk; labor from `basis.baseline` as `actual_fte × annual_paid_hours_per_fte × utilisation`, or
`actual_hours_month` annualised; maintenance, energy and software of the existing equipment are **not
modelled**, so the NPV versus client current is biased towards the current operation and `FinancialResult.notes`
says so; I73 b, `[EXPERT]`).

Hidden assumptions: only wages and energy inflate; capex, maintenance, software and rent are flat (I35); no tax,
depreciation, leasing or salvage (backlog); equipment lives and renewal shares are placeholders; the discount
rate 8 % is a `[P]` basis input.

Worked numbers (golden): S0 capex: storage = 67.76 × 90 + 184 × 12 = 8 306.82; equipment = 2 × 1 500 + 35 000 =
38 000; controls 50 000; works = 398.64 × 60 = 23 918.50; integration + commissioning = (0.05 + 0.02) × 38 000 =
2 660; contingency = 0.10 × 122 885.32 = 12 288.53; total `S0.capex.total` = **135 173.85** (`S0.capex.*`).
`S0.opex.y1.maintenance` = 0.04 × 38 000 = 1 520; rent = 398.64 × 58 = 23 121. `S0.finance.tco` = 502 094.87;
`S0.finance.annual_lines_y1` = 1 881 × 252 / 26 × 1.04 = 18 960.48; `S0.finance.cost_per_line` = 502 094.87 ×
0.2505 / 18 960.48 = 6.63 €. S2 against S0: `S2.finance.delta_cf.y0` = −(417 603.88 − 135 173.85) = **−282
430.03** (`S2.capex.total`, `S0.capex.total`), `delta_cf.y1` = 86 573.37 − 114 588.11 = −28 014.73, so S2 never
pays back (`S2.finance.payback_years` and `irr` null) and `S2.finance.npv` = −391 617: the cube loses on this
site (`F_SCALE_LOW`: 137 lines a day is below its 1 500-line minimum scale).

`[P]`: `catalog/families/*.yaml` (capex, opex, life), `catalog/finance_defaults.yaml`
(`finance.packaging_eur_per_order`, `finance.kwh_per_station_year`, default role costs, fixed energy), basis
`finance` (discount 0.08, wage 0.025, energy 0.03, 0.18 €/kWh, temp premium 0.15, client role costs).

## 7. Comparison and sensitivity (F8)

Code: `src/whsizing/scenarios/`; `comparison/comparison.json`, `comparison/sensitivity.json`.

- **Runner** (I75): project → ingest (or reuse `canonical/`) → profile → design day → for each
  scenario `size_scenario` × 3 worlds → finance → comparison → sensitivity. A scenario raising
  `SizingInfeasibleError` becomes a `not_computed` stub with its reason and the others continue;
  `--strict` exits 4 after writing everything when a scenario is not computed or none fits, and
  before ingest when a SKU master or an inventory is missing (I80; also on `F_ELIG_ASSUMED`).
  `is_baseline` must agree with `baseline:` (`ConfigError`).
- **Comparison**: one row per scenario (eligible share, areas, fit, equipment, FTE, capex, opex,
  TCO, NPV, payback, cost per line, warnings, confidence-L count). Rankings by TCO and payback at
  **typ** only; the note "Ranking at typical values; ranges overlap for scenarios X and Y" is
  printed whenever two TCO `[lo, hi]` intervals touch or intersect. **No automatic "recommended"
  label**: with `[P]` ranges on every parameter, a point ranking is not a finding.
- **Sensitivity** (one at a time, I76, `[EXPERT]` for the definitions): labor cost (every role),
  picking productivity (catalog picking standards), growth rate (absolute ± δ × typ), equipment capex
  (the equipment item's unit costs), design percentile (90 / 95 / 98), fill factor, OEE; each at
  `typ × (1 ± δ)`, δ = 0.2 (`--delta`, `options.delta`, 0 ≤ δ < 1); sizing is redone per variant,
  the labor-cost variants only rerun F7. The tornado is sorted by `max |ΔTCO|`. Catalog values are
  varied through scenario overrides, never the basis.
- **Break-even**: the labor-cost multiplier `k ∈ [0.3, 3]` at which an automated scenario's
  payback equals the target (5 years): `scipy.optimize.brentq` on a monotone extension of the payback
  (an unreached payback becomes the horizon plus the remaining shortfall), root re-verified within
  1e-3; `None` if there is no root.
- **Percentile sweep**: P80 / P90 / P95 / P98 re-run F4, F6 and F7: design lines, equipment, FTE,
  capex, TCO, the service-level trade-off.

Hidden assumptions: one-at-a-time ignores interactions; ±20 % is a convention, not a probability; the bracket
`[0.3, 3]` caps what "break-even" can say.

## 8. Report integrity (F9)

Code: `src/whsizing/report/`. The report is built from a typed model (`ReportData`): every number printed in the
PDF is a `Cell` of that model (I81 a) and the numeric cells of the four IC1 tables cite a trace node.
`check_integrity(run)` runs before any file is written; **any issue is `ReportIntegrityError`, exit 5**, listing
`IC<n> location: message` (20 at most, I78 g). It reads the report tables and the scenario traces, not
`result.json`, so a tampered table or trace is caught.

| Check | Fails when |
|---|---|
| IC1 | a numeric cell in the scenario columns of Summary, Scenarios, FTE or Capex/Opex has no trace id, or `(id, world)` is not a node holding the cell's value |
| IC2 | a trace node input is not `param:<id>`, a `data:` node or a node of the same tracer and world |
| IC3 | a Param used by a trace has no source; the count of `source: TODO` printed in the limitations box must equal the recount |
| IC4 | an area budget total differs from the sum of its zones by more than 0.5 m² |
| IC5 | FTE hours, heads or roster totals differ from the sum of the activities |
| IC6 | a cumulative cash flow is not the running sum of the Δ cash flows |
| IC7 | a quantity in m², h or eur (or shown as euros) is negative; cells marked `signed` (NPV, deltas) are exempt |
| IC8 | a `{{ missing:<key> }}` sentinel reaches the rendered HTML (untranslated key) |

Conventions (I79, I81, I82): value-only workbook with the 12 sheets (`Capex / Opex` is written
`Capex - Opex`: Excel forbids `/`), every traced cell carries a comment with the node id, world, formula and inputs;
the PDF has a trace index of depth 1 (Appendix C) from which total area, design-day heads and TCO can be
reproduced; the 12-18 page budget is loosened for studies with more than four scenarios; free texts the pipeline
writes (DQ messages, F7 notes, raw flag codes) stay in English in the French PDF (I79 h); a lo or hi cell cites
the world whose node holds the value. Numbers in FR and EN renders are identical (T9.5); number formats follow
the report language in the PDF, the viewer's locale in Excel (I82 j). Every report carries the "indicative
study" banner and the limitations box (fixed texts plus the count of TODO-sourced and confidence-L parameters,
the data-quality band and each scenario's flags).

## 9. Calibration (F11)

Purpose: show that the model reproduces a real site, or document the gap. Code: `src/whsizing/calibration/`;
`whsizing calibrate <run> --actuals actuals.csv --activity-map activity_map.yaml [--holdout-months 3]`.

1. **Map** client activities to model activities (many-to-one); unmapped labels go to `indirect`
   (`W_UNMAPPED_ACTIVITY`); a target that is not a model activity must be declared under
   `client_activities` (kitting, VAS): it becomes a client-specific activity driven by orders
   (`F_CLIENT_ACTIVITY`), reported, never fed into the catalog or sizing (I74 i).
2. **Predict** monthly hours per activity from the daily series with the catalog values (F6c, typ
   world, baseline family, labor only). Hours are linear in `1/productivity` and in `(1 + PF&D)`
   (I38), so the engine runs once and θ is evaluated in closed form.
3. **θ** = one productivity multiplier `m_a ∈ [0.5, 2.0]` per activity (receiving + receipt_check,
   put_away, decant, replenishment, picking, packing, shipping, returns, indirect), `η ∈ [0.6, 1.0]`,
   `PF&D ∈ [0.05, 0.25]` (`calibration/models.py`, `[P]`). Priors = catalog typ, σ = half the
   catalog range.
4. **Objective**: `Σ_i w_i (pred_i − actual_i)² + λ Σ_j ((θ_j − prior_j)/σ_j)²`, `w_i ∝ actual_i`,
   `λ = 1`, `scipy.optimize.least_squares` (bounds, `soft_l1`). The data term is scaled so a residual
   of 0.3 % of the mean point weighs 1 (`NOISE_REL`): the prior is a tie-breaker, not a shrinkage
   (I74 c). η does not enter the monthly hours, so it stays at its prior; PF&D is confounded with the
   multipliers, so the identified **effective multiplier** is `m × (1 + pfd_basis) / (1 + pfd)`, the
   quantity tested within 5 % (T11.1) and the one the catalog update uses (I74 b).
5. **Split**: fit on the earlier months, hold out the last `--holdout-months` (default 3); the
   hold-out must contain the peak month (highest total actual hours), else it is shifted and
   `W_HOLDOUT_SHIFTED` is raised. Fewer than 12 months of actuals is a warning (`W_SHORT_HISTORY`), not an error. A month is *partial* (left out) only when the daily series covers
   < 90 % of it (I74 d, e).
6. **Metrics** on the hold-out: MAPE per activity, MAPE on total monthly hours, bias (signed),
   peak-month error, peak lines/h error. **Acceptance**: total MAPE and |peak-month error| both
   ≤ 15 % `[P]` (spec: 10-15 %); per-activity errors are reported, not gated.
7. **Outputs** (`calibration/`): `fit.json`, `holdout.json`, `plots/*.png`, `calibration_note.md`
   ("calibrated on N site(s)", quoted in report §8), the copies of the two input files.
8. **Catalog update** is a library function, not a CLI command (`whsizing.calibration.update_catalog`), to be run by hand on a *copy* of the catalog: `typ` changes only if the new value stays
   within the current `[min, max]` (a single site never widens a range); confidence becomes M and
   `validated_by` is set only with a reviewer name; the change is logged in `CHANGELOG.md`.

Hidden assumptions: the baseline family is manual unless the baseline scenario names another; the activity
labels of the client mean what the map says; one site does not identify a catalog (hence confidence M at most).
Headcount-only actuals use `annual_paid_hours_per_fte / 12` per head and month; `temp_hours` is informational
and, absent, `I_TEMPS_COMBINED` is raised. Flag codes: I74 j. Not measured on real data yet: T11.4 is a manual
acceptance by the expert (skipped in CI).

## 10. Known limits and open rulings

### 10.1 Open `[EXPERT]` / `[VERIFY]` rulings (register, section "Open expert rulings")

Nothing below changes a golden value unless said. The register is the source of truth
(`tests/golden/test_g1_expert_rulings.py` fails when a marked entry is missing from its list).

- **I33** (named in review #1): labor cost counts the temp hours twice (literal F7); the expert
  decides. Golden S0 and S2 hold the literal value.
- **I46** `[EXPERT]`: the value of `cube_asrs.max_robots_per_m2` (0.05, no spec value), not the
  `F_ROBOT_DENSITY` flag; S2 raises it at about 0.47 robots/m².
- **I48** `[EXPERT]`: whether a degenerate cube scenario (zero eligible lines) carries the manual WMS
  adaptation and manual software; to settle together with the I47 count.
- **I53** `[EXPERT]`: R13 outlier threshold `median + 10 × max(MAD, 1)`, the MAD floor of 1.
- **I54** `[VERIFY]`: amendment W3 to the decimal sniff (thousands shapes left out of the 80 %
  share, decimal-comma evidence beyond the verbatim regex, delimiter tie-break).
- **I64** `[EXPERT]`: with lumpy receipts, receipts-mode inbound hours sit above the P50 day and temp
  hours dominate (b2b S1 typ 9 903 of 14 519 h); literal spec kept.
- **I65** `[EXPERT]`: the floor of 1 head per staffed activity applies per shift (about +4 heads on
  ecom_mid S0 with 2 × 7 h).
- **I67** `[VERIFY]`: in a `;` file with comma decimals elsewhere, a dot 3-decimal weight (`1.250`) is
  read × 1000 with no DQ signal; confirm with the spec owner.
- **I69** `[EXPERT]`: whether F6d should size the pack stations on the same `λ_s` as the F6e queue
  check, instead of reporting `F_UNSTABLE:packing` with `c_min`.
- **I76** `[EXPERT]`: the F8b parameter definitions (`equipment_capex`, `picking_productivity`) and the
  break-even bracket `[0.3, 3]`.
- **I73** `[EXPERT]`: the amr_gtp capex formulas and the `A_storage` choice for its floor preparation
  (no golden); the client-current baseline (labor only, biased towards the current operation).

Also `[VERIFY]` in the spec: the French 1 607 h paid hours per FTE, the ICPE 1510 thresholds
(`catalog/icpe_1510.yaml`), the WeasyPrint/Pango install requirements.

### 10.2 Known limits (not rulings)

- **Placeholders**: 72 of 72 parameters are `source: TODO`, confidence L (`assumptions.md`); the report
  prints the count. Ranges are corner worlds, not intervals (§0.3).
- **No simulation** (ADR-003): steady-state design day plus Erlang-C; no dynamic congestion, wave
  planning, slotting, building geometry (the diagram is a square of side `sqrt(area)`, I79 b), fire
  cells, taxes, leasing, labour-law constraints.
- **Pickers vs stock** (I68): with stock scaled with demand, the per-zone ceil can lower
  `pickers_peak` while picking hours grow; spec-literal, kept. T6.5 holds stock constant.
- **Short histories**: under 12 months seasonality and trend are flagged L; under 60 operating days
  `F_SHORT_HISTORY`; annual totals extrapolate the average day (`× operating_days_per_year / n_op`).
- **Paths with glob characters** (`[`, `]`, `*`, `?`) work as plain paths; a wildcard pattern that must
  also contain a literal glob character in another path component has to escape it (`[[]`, I75 i).
- **Report**: the French PDF shows pipeline free texts (DQ messages, F7 notes, raw flag codes, formulas
  block) in English (I79 h, I81 g); the workbook is value-only, no live formulas (I82 b); the 12-18 page
  budget holds up to four scenarios (I81 c).
- **F11** has no real-site result yet (T11.4 manual), and the oracle does not cover `receipts` mode
  or ≥ 3 inventory snapshots (I12, I77).

## 11. Where each value lives

| Value | Where | Id form |
|---|---|---|
| Family capacities, rates, costs, lives | `catalog/families/{manual_p2p,amr_gtp,cube_asrs}.yaml` | `<family>.<name>` |
| Labor standards, indirect share, shift lag, inbound window | `catalog/labor_standards.yaml` | `labor.<activity>` |
| Storage class thresholds, default units per pallet | `catalog/storage_classes.yaml` | `storage.<name>` |
| Area factors, circulation, peak-hour inbound share | `catalog/area_factors.yaml` | `area.<name>` |
| Packaging, energy, default role costs | `catalog/finance_defaults.yaml` | `finance.<name>` |
| `η_flow`, receipt lines per pallet, SLA thresholds, pack-station OEE | `catalog/engine_defaults.yaml` | `engine.<name>` |
| ICPE 1510 regimes | `catalog/icpe_1510.yaml` | none (informational) |
| Operating assumptions of one client | `basis.yaml` (`whsizing basis init`; model `schemas/basis.py`) | `operations.*`, `projection.*`, ... |
| Parameter overrides | `basis.overrides`, `scenario.overrides` | catalog id (+ `stock_growth_rate`) |
| DQ thresholds, mapping thresholds, DQ score points | constants in `src/whsizing/io/{rules,mapping,dq}.py` (not overridable) | |
| Design-day drift 15 %, short history 60 days | `src/whsizing/design/design_day.py` | |
| F11 bounds, λ, acceptance 15 % | `src/whsizing/calibration/models.py` | |
| Sweep percentiles, break-even bracket, δ | `src/whsizing/scenarios/` (δ also `options.delta`) | |

Changing a catalog file: edit it, `whsizing validate-catalog catalog`, regenerate `docs/assumptions.md` (`uv run
python -m whsizing.catalog.assumptions`; `tests/unit/test_f5_loader.py` fails when it is stale), add a
`catalog/CHANGELOG.md` entry, and rebuild the golden case if the change reaches it (`uv run python -m
tests.golden.build_golden`).
