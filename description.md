# Warehouse Sizing POC — Detailed Engineering Specification

| | |
|---|---|
| **Version** | 0.2 (detailed) — supersedes v0.1 "Feature Specification & Work Plan" |
| **Date** | 7 November 2026 |
| **Phase** | Step 1: proof of concept — 4 weeks, 20 working days |
| **Team** | Dev A (engine) · Dev B (product: ingestion, reports, UI, infrastructure) · Business lead (pilot, data access, domain expert, reviews) |

> **Reading note.** Every numeric target, default value, threshold and catalog range in this document is a **proposal or a placeholder**, marked `[P]`. Items marked `[EXPERT]` need validation by a logistics expert before a client sees them; items marked `[VERIFY]` need checking against current documentation or regulation. Nothing in this document is a sourced industry benchmark.

---

## 0. How to read this document

- v0.1 listed the features. v0.2 adds, for each feature: artifacts, module layout and function signatures, step-by-step algorithms, configuration, edge cases, acceptance tests, a task breakdown with estimates, and a day-by-day plan.
- Every feature section follows the same template: **Purpose · Artifacts · Modules · Algorithm · Configuration · Edge cases · Tests · Tasks · Done when**.
- Identifiers: tests are `T<feature>.<n>` (e.g. `T6.4`); engine flags are `F_<CODE>`; data-quality rules are `R<n>`; report integrity checks are `IC<n>`.
- Appendices hold the consolidated formulas, the full YAML examples, the synonym dictionary and the glossary.

---

## 1. Goal, scope and definition of done

### 1.1 Goal

Turn a prospect's raw operational files into a defensible sizing and business case within hours: three generic automation scenarios compared on equipment, FTE by activity, area fit, capex, opex and TCO, delivered as a PDF + Excel report in which every number is traceable to a formula and a parameter.

### 1.2 Principles and where they show

| Principle | Where it shows |
|---|---|
| Neutral | Generic equipment families (F5); no brand names, no vendor quotes |
| Brownfield-first | Baseline = the client's current operation; scenarios are deltas against it (F6, F7, F11) |
| Glass-box | Calculation trace on every number (F6f), assumptions sheet (F9), drill-down (F10) |
| Fast | Ingest < 15 min, scenario run < 10 s, report < 60 s (C5) |
| FR/EU-calibrated | Loaded labor cost by role, annual paid-hours basis `[VERIFY]`, ICPE 1510 informational flag (F4, F6d) |
| Honest | lo/typ/hi ranges, confidence tags, limitations box, "indicative" banners (F8, F9, F10) |

### 1.3 In scope / out of scope

**In:** ingestion of order lines, SKU master, stock and optional receipts · demand profile and design day with growth · scenarios S0 manual picker-to-parts, S1 AMR goods-to-person, S2 cube AS/RS with ports · sizing (storage, throughput and equipment, labor, area, queue check) · finance (capex, opex, TCO, NPV, IRR, payback) · comparison and one-at-a-time sensitivity · Excel + PDF · CLI, optional Streamlit · back-test on one real site.

**Out (backlog, §10):** discrete-event simulation, Monte Carlo, 3D, live WMS/ERP connectors, authentication and workspaces, LLM-assisted mapping, slotting, multi-site network design, brand-specific equipment data, leasing/RaaS and tax effects.

### 1.4 Definition of done

- [ ] A messy real client file is ingested in < 15 min including mapping (T2.9)
- [ ] 1 M order lines profiled in < 60 s (T3.8)
- [ ] Three scenarios sized in < 10 s (T8.5)
- [ ] Excel + PDF generated in < 60 s with no manual edit (T9.7)
- [ ] Every figure in the report traces to a `TraceNode` and a `Param` (IC1, IC2)
- [ ] Hold-out error ≤ 10–15 % `[P]` on total daily FTE and on peak lines/h for one real site, or the gap and its correction are documented (T11.4)
- [ ] Any run is reproducible from its manifest (T6.9)
- [ ] Expert reviews #1 and #2 completed with the §8 checklists

### 1.5 Decisions required before day 1

| Decision | Owner | Default if undecided |
|---|---|---|
| Pilot client, NDA, anonymisation and retention terms | Business lead | No real data → F11 slips (critical path) |
| Domain expert, two booked half-days (days 15 and 19) | Business lead | Reviews slip |
| Report languages | Business lead | French first, English template second |
| Default design percentile and horizon | All | P95, 5 years `[P]` |
| Baseline definition | All | Client's current operation if documented, else S0 |
| Hosting during the POC | Dev B | Local only |
| Product and report name, logo | Business lead | Placeholder |

---

## 2. Architecture

### 2.1 Pipeline and artifacts

```
client files ──► ingest / map ──► validate + DQ ──► canonical/*.parquet + dq/dq_report.{json,html}
                                                           │
catalog/*.yaml ──┐                                         ▼
basis.yaml ──────┼──► profile/demand_profile.json ──► design/design_day.json + assumptions.json
scenarios.yaml ──┘                                         │
                                                           ▼
                 storage ─► throughput / equipment ─► labor ─► area ─► queue check
                                                           ▼
                        finance ─► comparison/comparison.json + sensitivity.json
                                                           ▼
                                  report/report_{fr,en}.{pdf,xlsx} + manifest.json + trace.jsonl
```

### 2.2 Design principles

1. **Library-first.** All logic lives in the `whsizing` package. CLI and Streamlit are thin wrappers; a future FastAPI service calls the same functions.
2. **Contract-first.** Pydantic and Pandera contracts are frozen on day 2 so both developers work against mocks.
3. **Pure functions, explicit units.** No hidden state. Units are checked at the parameter layer (pint); the engine works in SI floats.
4. **Glass-box trace.** Every computed quantity is recorded as a `TraceNode` with formula and inputs.
5. **Deterministic and reproducible.** Explicit seeds; every run writes a manifest; never overwrite a run.
6. **Local-first data handling.** Client data stays on controlled machines; no external API calls.

### 2.3 Repository layout (file level)

```
whsizing/
├─ pyproject.toml · uv.lock · justfile · Dockerfile · .pre-commit-config.yaml · .github/workflows/ci.yml
├─ src/whsizing/
│  ├─ __init__.py          # __version__ via importlib.metadata
│  ├─ cli.py               # Typer app (see F10)
│  ├─ config.py            # YAML → Pydantic loaders (extra="forbid"), path resolution
│  ├─ errors.py            # exception hierarchy and exit codes (§2.7)
│  ├─ logging.py           # structlog setup, run_id binding
│  ├─ schemas/
│  │  ├─ params.py         # Param, Range, Confidence
│  │  ├─ basis.py          # DesignBasis + sub-models
│  │  ├─ profile.py        # DemandProfile, EIQ, ABC, Seasonality, ShipmentSplit, StockStats
│  │  ├─ design.py         # DesignDay, Inbound, Assumption
│  │  ├─ scenario.py       # ScenarioDef, EligibilityCfg
│  │  ├─ result.py         # ScenarioResult, StorageResult, LaborResult, AreaResult, QueueResult, Flag
│  │  ├─ finance.py        # FinancialResult
│  │  ├─ manifest.py       # RunManifest, IngestManifest
│  │  ├─ trace.py          # TraceNode, Tracer
│  │  └─ frames.py         # Pandera: OrderLines, SkuMaster, Inventory, Receipts, DailySeries
│  ├─ io/
│  │  ├─ readers.py        # read_any(path, sheet) → raw string DataFrame
│  │  ├─ sniff.py          # encoding, delimiter, header row, decimal, date format
│  │  ├─ parse.py          # typed parsing
│  │  ├─ mapping.py        # synonyms, scoring, suggest(), apply()
│  │  ├─ rules.py          # R1..R14
│  │  ├─ dq.py             # DQReport, score, renderers
│  │  ├─ anonymize.py      # HMAC hashing, PII drop
│  │  ├─ canonical.py      # write parquet + ingest manifest
│  │  └─ synonyms_fr_en.yaml
│  ├─ profile/
│  │  ├─ aggregate.py · eiq.py · abc.py · stock.py · calendar.py · seasonality.py
│  │  ├─ intraday.py · shipments.py · charts.py
│  │  └─ build.py          # build_profile(canonical_dir) → DemandProfile
│  ├─ design/
│  │  ├─ basis.py          # load, validate, template generator
│  │  ├─ design_day.py     # select_design_day(profile, basis) → DesignDay
│  │  ├─ inbound.py        # receipts or derived inbound
│  │  └─ assumptions.py
│  ├─ catalog/
│  │  ├─ models.py         # Family, CatalogParam, LaborStandards, FinanceDefaults, IcpeTable
│  │  ├─ loader.py         # load_catalog(dir) strict, versioned
│  │  └─ eligibility.py    # eligible_mask(), eligibility_shares()
│  ├─ engine/
│  │  ├─ classify.py       # storage class per SKU
│  │  ├─ storage.py · throughput.py · labor.py · area.py · queue.py · trace.py
│  │  └─ size.py           # size_scenario(...) → ScenarioResult
│  ├─ finance/
│  │  ├─ capex.py · opex.py · metrics.py
│  │  └─ build.py          # compute_finance(...) → FinancialResult
│  ├─ scenarios/
│  │  ├─ runner.py · compare.py · sensitivity.py
│  ├─ calibration/
│  │  ├─ actuals.py · fit.py · evaluate.py
│  ├─ report/
│  │  ├─ excel.py · pdf.py · charts.py · diagram.py · integrity.py
│  │  ├─ i18n/fr.yaml · i18n/en.yaml
│  │  └─ templates/*.html.j2 · styles.css
│  └─ app/
│     ├─ Home.py · state.py · drilldown.py
│     └─ pages/1_Upload.py … 6_Results.py
├─ catalog/
│  ├─ families/manual_p2p.yaml · amr_gtp.yaml · cube_asrs.yaml
│  ├─ labor_standards.yaml · finance_defaults.yaml · storage_classes.yaml · area_factors.yaml · icpe_1510.yaml
├─ basis/example_basis.yaml · scenarios/example_scenarios.yaml · project/example_project.yaml
├─ data/synth/generator.py · data/synth/profiles/*.yaml
├─ tests/unit · tests/golden · tests/property · tests/e2e · tests/fixtures
└─ docs/methodology.md · docs/assumptions.md · docs/adr/
```

### 2.4 Run folder

```
runs/2026-11-18T14-02-11_3f9a1c/
  manifest.json             # RunManifest
  inputs/                   # copies of project.yaml, basis.yaml, scenarios.yaml, mapping/*.yaml, catalog snapshot
  canonical/                # order_lines.parquet, sku_master.parquet, inventory.parquet, receipts.parquet, daily_series.parquet
  dq/                       # dq_report.json, dq_report.html, ingest_manifest.json
  profile/                  # demand_profile.json, charts/*.png, charts/*.html
  design/                   # design_day.json, assumptions.json
  scenarios/<id>/           # result.json, finance.json, trace.jsonl
  comparison/               # comparison.json, sensitivity.json
  report/                   # report_fr.pdf, report_fr.xlsx (+ _en)
  logs/run.log
```

Folder name = ISO timestamp + first 6 hex characters of the manifest hash. Runs are immutable; `whsizing rerun <run>` creates a new folder.

### 2.5 Core contracts (Pydantic v2)

```python
from __future__ import annotations
from datetime import date, datetime, time
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Confidence = Literal["H", "M", "L"]
FamilyId = Literal["manual_p2p", "amr_gtp", "cube_asrs"]

class Param(BaseModel, frozen=True):
    """A catalog or basis parameter with provenance. Units are pint-parsable or '-'."""
    id: str                       # e.g. "cube_asrs.port_rate_lines_h"
    unit: str
    min: float
    typ: float
    max: float
    source: str                   # citation, "expert:<name>:<yyyy-mm>", or "TODO"
    confidence: Confidence
    pessimistic_end: Literal["min", "max"]   # which bound is the pessimistic world (see 2.5.1)
    validated_by: str | None = None
    date: date
    note: str | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if not (self.min <= self.typ <= self.max):
            raise ValueError(f"{self.id}: min ≤ typ ≤ max violated")
        return self

class Range(BaseModel, frozen=True):
    """A computed quantity: lo ≤ typ ≤ hi, value-ordered."""
    lo: float
    typ: float
    hi: float
    unit: str

class Operations(BaseModel):
    operating_days_per_year: int = 250            # [P]
    shifts_per_day: int = 1
    hours_per_shift: float = 7.0                  # [P]
    paid_hours_per_person_day: float = 7.0        # [P]
    annual_paid_hours_per_fte: float = 1607.0     # [VERIFY] French 35 h basis
    utilisation: float = 0.85                     # [P] share of paid time on direct work
    absenteeism: float = 0.06                     # [P]
    pfd_allowance: float = 0.12                   # [P] personal, fatigue, delay

class Service(BaseModel):
    cutoff_time: time
    carrier_departure_time: time
    same_day_share: float = 0.0                   # share of lines that must ship the same day
    sla_window_hours: float | None = None         # derived from the two times if None

class Projection(BaseModel):
    horizon_years: int = 5
    growth_rate: float = 0.03
    design_percentile: float = 95.0
    peak_stock_factor: float = 1.15               # [P]
    trailing_months: int = 12                     # 24 if available

class Flows(BaseModel):
    returns_rate: float = 0.03
    inbound_mode: Literal["receipts", "derived"] = "derived"
    inbound_peak_factor: float | None = None      # None → outbound peak-to-average
    pallets_per_truck: float = 26                 # [P]
    truck_dwell_hours: float = 1.0                # [P]
    dock_utilisation: float = 0.7                 # [P]
    pallet_order_weight_kg: float = 300           # [P] heavier orders ship as pallets
    pallet_order_cube_m3: float = 0.6             # [P]
    parcel_max_weight_kg: float = 30              # [P]

class Building(BaseModel):
    area_m2: float
    clear_height_m: float
    dock_doors_in: int
    dock_doors_out: int
    floor_load_t_m2: float | None = None
    sprinklered: bool | None = None
    rent_eur_m2_year: float = 60.0                # [P]
    rent_mode: Literal["footprint", "full_building", "none"] = "footprint"

class FinanceBasis(BaseModel):
    discount_rate: float = 0.08                   # [P]
    horizon_years: int = 5
    wage_inflation: float = 0.025                 # [P]
    energy_inflation: float = 0.03                # [P]
    energy_price_eur_kwh: float = 0.18            # [P]
    labor_cost_eur_h: dict[str, float]            # role → loaded hourly cost (client-provided)
    temp_premium: float = 0.15                    # [P] premium on temporary labour hours
    shift_premium: float = 0.0

class Baseline(BaseModel):
    description: str = ""
    actual_fte: dict[str, float] | None = None    # activity → FTE
    actual_hours_month: dict[str, list[float]] | None = None
    equipment: dict[str, int] | None = None

class DesignBasis(BaseModel):
    client: str
    site: str
    currency: Literal["EUR"] = "EUR"
    timezone: str = "Europe/Paris"
    operations: Operations
    service: Service
    projection: Projection
    flows: Flows
    building: Building
    finance: FinanceBasis
    baseline: Baseline = Baseline()
    overrides: dict[str, float] = {}              # param id → value, documented as "client override"

class SeriesStats(BaseModel):
    mean: float; p50: float; p90: float; p95: float; p98: float; max: float; cv: float

class DemandProfile(BaseModel):
    dataset_hash: str
    period_start: date
    period_end: date
    operating_days: int
    daily: dict[str, SeriesStats]                 # orders, lines, units, cube_m3, weight_kg
    eiq: "EIQ"
    abc: "ABC"
    stock: "StockStats"
    seasonality: "Seasonality"
    intraday: dict[int, list[float]]              # weekday (0=Mon) → 24 shares summing to 1
    peak_hour_share: float
    shipment_split: "ShipmentSplit"
    dims_coverage_lines: float                    # share of lines whose SKU has dims and weight
    daily_series_path: str

class Inbound(BaseModel):
    mode: Literal["receipts", "derived"]
    units_per_day: float; pallets_per_day: float; receipt_lines_per_day: float; trucks_per_day: float
    peak_factor: float

class Assumption(BaseModel):
    key: str; value: float | str; unit: str; origin: Literal["default", "client", "override", "derived"]; note: str = ""

class DesignDay(BaseModel):
    percentile: float; growth_rate: float; horizon_years: int
    reference_date: date                          # actual day nearest the percentile
    lines: float; orders: float; units: float; cube_m3: float; weight_kg: float
    design_weekday: int
    hourly_lines: list[float]                     # 24 values, sum == lines
    peak_hour_lines: float
    parcels: float; pallets_out: float
    stock_units: float; stock_cube_m3: float
    inbound: Inbound
    assumptions: list[Assumption]

class EligibilityCfg(BaseModel):
    use_catalog_limits: bool = True
    assume_eligible_if_missing_dims: bool = False # conservative default
    extra_max_weight_kg: float | None = None

class ScenarioDef(BaseModel):
    id: str; name: str; family: FamilyId
    is_baseline: bool = False
    overrides: dict[str, float] = {}
    eligibility: EligibilityCfg = EligibilityCfg()
    overflow_family: Literal["manual_p2p"] = "manual_p2p"
    notes: str = ""

class Flag(BaseModel):
    code: str                                     # F_NO_FIT, F_DOCK_SHORTFALL, F_SLA_RISK, F_LOW_CONFIDENCE, ...
    severity: Literal["info", "warning", "blocking"]
    message: str
    value: float | None = None

class ScenarioResult(BaseModel):
    scenario: ScenarioDef
    eligibility: "EligibilityResult"
    storage: "StorageResult"
    equipment: dict[str, Range]                   # "gtp_stations", "robots", "ports", "pickers_peak", ...
    bottleneck: str
    labor: "LaborResult"
    area: "AreaResult"
    queue: "QueueResult"
    flags: list[Flag]
    trace_path: str

class FinancialResult(BaseModel):
    scenario_id: str
    capex: dict[str, Range]; capex_total: Range
    opex_by_year: list[dict[str, float]]          # index = year 1..T, item → typ value
    opex_year1: Range
    tco: Range
    npv_vs_baseline: Range | None
    irr_vs_baseline: float | None
    payback_years: float | None                   # None = not reached within horizon
    cost_per_line: Range
    cash_flows_typ: list[float]                   # year 0..T

class RunManifest(BaseModel):
    run_id: str; created_at: datetime
    engine_version: str; git_sha: str; catalog_version: str
    inputs: dict[str, str]                        # path → sha256
    basis_hash: str; scenarios_hash: str; mapping_hashes: dict[str, str]
    params_snapshot: dict[str, float]             # every param value used (typ after overrides)
    seed: int
    python: str; platform: str; packages: dict[str, str]
```

#### 2.5.1 Range convention

- Each parameter declares `pessimistic_end`. Inference rule in the loader: units containing `/h`, `/m2`, `fill`, `availability`, `OEE` → `min`; units containing `eur`, `h` (durations), `m2 per` → `max`; anything else must be explicit, otherwise the loader rejects the file.
- The engine evaluates every output three times: the **pessimistic world** (all parameters at their pessimistic end), the **typical world** (all at `typ`), the **optimistic world**. `Range.lo/hi` are the sorted extremes; `Range.typ` is always the typical world. Ranges therefore bound the result, they are not statistical intervals (Monte Carlo is backlog).

### 2.6 Trace model

```python
class TraceNode(BaseModel, frozen=True):
    id: str                 # "S1.labor.picking.hours_design_day"
    label: str              # "Picking hours on design day"
    value: float
    unit: str
    formula: str            # "workload / productivity * (1 + pfd)"
    inputs: dict[str, str]  # symbol → TraceNode id or Param id ("param:amr_gtp.station_rate_lines_h")
    scope: str              # scenario id or "global"
    world: Literal["lo", "typ", "hi"] = "typ"

class Tracer:
    def record(self, id, label, value, unit, formula, inputs) -> float: ...   # returns value for chaining
    def export_jsonl(self, path) -> None: ...
    def tree(self, id) -> dict: ...                                          # recursive expansion for the UI
```

Rules: every number that appears in a report must exist as a `TraceNode` (checked by IC1). Node ids are stable across runs (used by snapshot tests). The typical world is traced in full; lo/hi worlds trace only leaf results.

### 2.7 Errors and exit codes

| Exit code | Exception class | Meaning |
|---|---|---|
| 0 | — | Success |
| 1 | `WhsizingError` (unexpected) | Unhandled failure; traceback in `logs/run.log` |
| 2 | `ConfigError`, `MappingError` | Invalid YAML, unknown parameter id, required column unmapped in non-interactive mode |
| 3 | `DataQualityError` | At least one blocking DQ issue (R-rules) |
| 4 | `SizingInfeasibleError` | Only in `--strict`: no scenario fits the building, or a required input is missing |
| 5 | `ReportIntegrityError` | An IC check failed |

### 2.8 Logging

structlog, JSON lines to `logs/run.log` plus a human console renderer. Every record carries `run_id`, `stage`, `scenario`. Timing of each stage is logged (`duration_s`) and copied into `manifest.json` for the performance budget (C5).

---

## 3. Technology stack and development environment

### 3.1 Dependencies

| Layer | Package(s) | Notes |
|---|---|---|
| Runtime | Python ≥ 3.12 | Match the Docker base image |
| Packaging | uv (`uv.lock` committed) | `uv sync --frozen` in CI and Docker |
| Quality | ruff (lint + format), pyright (strict on `schemas/`, `engine/`, `finance/`), pre-commit | |
| Tests | pytest, pytest-cov, hypothesis, syrupy (snapshots) | |
| Data | polars, pyarrow | DuckDB only if a file exceeds memory `[P]` |
| Validation | pandera (Polars extra), pydantic ≥ 2 | Row-level rules run on eager `pl.DataFrame` (see 4.3) |
| Ingestion | charset-normalizer, rapidfuzz, fastexcel or calamine via Polars, python-dateutil, holidays | |
| Numerics | numpy, scipy, numpy-financial, pint | pint at the parameter layer only |
| Config | pyyaml (safe_load), pydantic | `extra="forbid"` on every model |
| CLI | typer, rich | |
| Charts | matplotlib (reports), plotly (UI) | No Kaleido in the POC: Kaleido ≥ 1 needs a Chrome install for static export |
| Reports | jinja2, weasyprint, xlsxwriter | WeasyPrint needs Pango and fonts in the image `[VERIFY]` current install docs |
| UI | streamlit | Optional (F10) |
| Logging | structlog | |

Pin exact versions in `uv.lock`; record them in `RunManifest.packages`.

### 3.2 Local setup

```bash
uv sync --all-extras
uv run pre-commit install
just test            # lint, typecheck, unit + golden + property tests
just demo            # synth → ingest → profile → size → report on data/synth/profiles/ecom_mid.yaml
```

`justfile` recipes: `lint`, `typecheck`, `test`, `test-fast` (unit only), `golden-update` (regenerate snapshots, requires explicit confirmation), `demo`, `docker-build`, `docker-demo`, `bench` (C5 budget), `docs`.

### 3.3 Docker image (sketch)

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENTRYPOINT ["uv", "run", "whsizing"]
```

The CI job `docker-smoke` runs `whsizing run-all project/example_project.yaml` inside the image and asserts that the PDF and Excel files exist and open.

### 3.4 CI pipeline (GitHub Actions)

`lint` → `typecheck` → `test` (with coverage ≥ 80 % on `engine/` and `finance/` `[P]`) → `docker-build` → `docker-smoke` → `bench` (fails if any C5 budget is exceeded by > 50 %). Artifacts: coverage report, demo PDF/Excel, bench JSON.

### 3.5 Conventions (ADR-001)

- Units: mm, kg, m, m², m³, hours. Currency EUR excluding VAT. Timestamps tz-aware (`Europe/Paris`), stored as UTC in Parquet with the zone in metadata.
- IDs are strings; hashed IDs are 16 hex characters.
- Rounding only at presentation. Engine keeps floats; counts are `ceil`ed where stated.
- Random processes take an explicit `seed`; default seed 42 in tests.
- YAML keys are `snake_case`; parameter ids are `<family>.<name>` or `<file>.<name>` (e.g. `labor.pick_rate_manual_lines_h`).

---

## 4. Data contracts and dictionary

### 4.1 Canonical tables (Parquet)

**order_lines**

| Field | Polars dtype | Required | Validation | Notes |
|---|---|---|---|---|
| order_id | Utf8 | yes | non-null, hashed | |
| order_ts | Datetime(µs, UTC) | yes | non-null, within [period − 1 d, today] | local date derived with tz |
| sku | Utf8 | yes | non-null, hashed | |
| qty_units | Int64 | yes | ≠ 0 | negative → `is_return=true` |
| channel | Utf8 | no | | B2B / B2C / retail / other |
| line_status | Categorical | no | ∈ {shipped, cancelled, returned, unknown} | default `shipped` |
| source_file | Utf8 | yes | | provenance |
| source_row | Int64 | yes | | provenance |

**sku_master**

| Field | Polars dtype | Required | Validation |
|---|---|---|---|
| sku | Utf8 | yes | unique, hashed |
| length_mm, width_mm, height_mm | Float64 | yes* | > 0, < 3000 `[P]`; *null allowed but counted in coverage |
| weight_kg | Float64 | yes* | > 0, < 1500 `[P]` |
| units_per_case | Int64 | recommended | ≥ 1 |
| cases_per_pallet | Int64 | recommended | ≥ 1 |
| units_per_pallet | Int64 | derived | units_per_case × cases_per_pallet, else default `[P]` |
| category | Utf8 | no | |
| stackable | Boolean | no | |
| temperature_class | Categorical | no | ∈ {ambient, chilled, frozen} |
| hazmat | Boolean | no | |
| unit_cube_m3 | Float64 | derived | l × w × h / 1e9 |

**inventory**

| Field | Polars dtype | Required | Validation |
|---|---|---|---|
| sku | Utf8 | yes | |
| qty_units | Int64 | yes | ≥ 0 |
| snapshot_date | Date | yes | ≥ 1 distinct date; monthly preferred |

**receipts** (optional)

| Field | Polars dtype | Required | Validation |
|---|---|---|---|
| receipt_id | Utf8 | yes | |
| receipt_ts | Datetime(µs, UTC) | yes | |
| sku | Utf8 | yes | |
| qty_units | Int64 | yes | > 0 |
| pallets | Float64 | no | ≥ 0 |

**daily_series** (derived in F3)

| Field | Notes |
|---|---|
| date, weekday, is_operating, is_holiday | calendar |
| orders, lines, units, cube_m3, weight_kg | outbound per local date |
| parcels, pallets_out | from F3 shipment split |
| return_lines | negative or returned lines |
| receipts_lines, receipts_units, receipts_pallets | if receipts present |

### 4.2 Derived fields on order lines

`order_date` (local), `weekday`, `hour`, `is_return`, `is_cancelled`, `line_cube_m3 = qty × unit_cube`, `line_weight_kg = qty × weight`, `has_dims` (join flag), `storage_class` (F6a, per scenario).

### 4.3 Validation mechanics

- Pandera `DataFrameModel` per table with dtype coercion and column-level checks (`ge`, `isin`, `unique`).
- Row-level business rules (R-rules, F2) are implemented as Polars expressions on eager frames and produce a `RuleResult(rule, severity, count, share, sample_rows)`.
- Pandera's Polars backend has historically validated `LazyFrame`s at schema level only (columns and dtypes); row-level checks run on `DataFrame`s. Check the Pandera docs for the current opt-in backend before relying on lazy row checks.

---

## 5. Feature specifications

### F0 — Foundations and contracts

**Purpose.** Remove integration friction between the two developers and enforce quality from day 1.

**Artifacts.** Repository skeleton, `pyproject.toml`, `justfile`, Dockerfile, CI, `schemas/*.py` (§2.5), `errors.py`, `logging.py`, ADR-001, walking skeleton (`just demo` producing a stub PDF from a mock result).

**Modules.** `schemas/`, `config.py`, `errors.py`, `logging.py`, `cli.py` (skeleton), `report/pdf.py` (stub).

**Tasks (both devs, days 1–2)**
- [ ] Repo init, `src/` layout, uv, ruff, pyright, pytest, pre-commit (0.5 d, B)
- [ ] CI workflow with the §3.4 stages (0.5 d, B)
- [ ] Dockerfile and `docker-smoke` job (0.5 d, B)
- [ ] Contracts session: walk through §2.5 together, freeze field names (0.5 d, A + B)
- [ ] Implement `schemas/*.py`, `errors.py`, `logging.py`, `config.py` (1 d, A)
- [ ] ADR-001 conventions, `docs/` skeleton (0.25 d, A)
- [ ] Walking skeleton: `mock_result()` fixture → Jinja2 template → WeasyPrint PDF (0.5 d, B)

**Tests.** T0.1 CI green on `main`. T0.2 `whsizing --version` prints the package version. T0.3 every schema round-trips through JSON (`model_dump_json` → `model_validate_json`). T0.4 `Param` with `min > typ` raises. T0.5 the mock result renders a one-page PDF in the Docker image.

**Done when.** T0.1–T0.5 pass and both developers can build against the frozen contracts.

---

### F1 — Synthetic data generator and golden cases

**Purpose.** Develop and test without waiting for client data; produce hand-verified reference results for every formula.

**Artifacts.** `data/synth/generator.py`, profile YAMLs (`ecom_mid.yaml`, `b2b_cases.yaml`, `tiny_golden.yaml`), generated files in Parquet and CSV (EN and FR variants), `tests/golden/golden_case.xlsx` with a cell-by-cell explanation sheet.

**Generator parameters (profile YAML)**

| Group | Parameters (defaults are `[P]`) |
|---|---|
| Scale | `n_skus` 5,000 · `start_date` · `n_days` 730 · `orders_per_day_mean` 800 |
| SKU master | dims lognormal (`mu_log_mm`: 5.3 / 4.9 / 4.4 for L/W/H, `sigma` 0.5); weight lognormal (`mu_log_kg` −0.7, `sigma` 0.9); `units_per_case` ∈ {1, 6, 12, 24} weighted; `cases_per_pallet` from cube with pallet 1.2 × 0.8 × 1.2 m; categories 8 |
| Popularity | Zipf exponent `s` 1.1; 10 % of SKUs inactive |
| Order structure | lines per order: 1 with prob 0.55, else 1 + Poisson(2.2); units per line: 1 + Poisson(0.4) (B2C) or multiples of case (B2B) |
| Calendar | weekday weights [1.15, 1.10, 1.05, 1.00, 0.95, 0.35, 0.0]; monthly index with Q4 peak 1.6; promo events (date, multiplier 2.0, duration 3 d); annual growth 0.05 |
| Intraday | hourly shares peaking 10:00–12:00 and 14:00–16:00; cut-off effect at 15:00 |
| Flows | `returns_rate` 0.04 · `cancel_rate` 0.01 · `days_of_cover` 25 · receipts weekly per SKU |

**Algorithm**
1. Draw SKU attributes; compute `unit_cube`, `units_per_pallet`.
2. Popularity weights `w_i ∝ i^(−s)` on a random permutation of SKUs.
3. For each day `d`: `λ_d = base × weekday[d] × month[d] × (1+g)^(d/365) × promo[d]`; `n_orders_d ~ Poisson(λ_d)`.
4. For each order: number of lines, SKUs sampled without replacement by `w`, quantities, timestamp from the intraday distribution (minute resolution), channel.
5. Returns: sample `returns_rate` of shipped lines, create negative lines 3–20 days later; cancellations flagged.
6. Inventory snapshots at month-end: `stock_i = demand_i(30 d) × days_of_cover / 30 × noise`.
7. Receipts: weekly replenishment per SKU to keep cover; pallets from `units_per_pallet`.
8. Export: Parquet (canonical names) + CSV EN + CSV FR (headers from the synonym dictionary, `;` delimiter, decimal comma, `dd/mm/yyyy HH:MM`).
9. Defect injector (optional, per profile): BOM, cp1252 encoding, mixed date formats, missing dims (8 %), orphan SKUs (2 %), duplicate rows (0.5 %), negative quantities, trailing spaces, thousand separators, a second header row, cm instead of mm for 30 % of rows.

**Golden case (`tiny_golden`).** 100 SKUs, ≈ 1,000 orders over 31 days, no defects. The spreadsheet computes by hand: daily series, P95 design day, storage positions per class, pick hours, FTE, area budget for S0 and S2, capex/opex/TCO/payback for S0 vs S2. Every cell has a comment naming the formula in Appendix B.

**Tests.** T1.1 same seed → identical Parquet hash. T1.2 generated order count within ±5 % of expected mean. T1.3 Zipf: top 20 % SKUs ≥ 70 % of lines `[P]`. T1.4 FR CSV re-ingests through F2 with zero blocking issues. T1.5 golden spreadsheet values equal engine outputs within 0.5 % (used by F6, F7).

**Tasks (Dev A, days 2–5).** Generator core (1.5 d) · exporters and defect injector (0.75 d) · golden dataset and spreadsheet (1 d) · tests (0.5 d).

**Done when.** T1.1–T1.4 pass and the golden spreadsheet is reviewed by Dev B.

---

### F2 — Ingestion, mapping and data quality

**Purpose.** Turn messy client files into a clean canonical dataset in minutes, and build trust with a readable data-quality report.

**Artifacts.** `canonical/*.parquet`, `dq/dq_report.{json,html}`, `dq/ingest_manifest.json`, `mapping/<dataset>.yaml` per client.

**Modules and signatures**

```python
def read_any(path: Path, sheet: str | int | None = None) -> RawTable          # raw strings + sniff results
def sniff(path: Path) -> SniffResult      # encoding, delimiter, header_row, decimal, date_format, n_rows
def suggest_mapping(raw: RawTable, dataset: DatasetKind) -> MappingSuggestion  # per target: column, score, reason
def apply_mapping(raw: RawTable, mapping: Mapping) -> pl.DataFrame           # typed canonical columns
def run_rules(frames: CanonicalFrames) -> list[RuleResult]
def build_dq_report(rules: list[RuleResult], frames) -> DQReport
def anonymize(frames, salt: bytes) -> CanonicalFrames
def write_canonical(frames, out_dir: Path) -> IngestManifest
```

**Algorithm — sniffing**
1. Encoding: `charset_normalizer` on the first 1 MB; fallback order utf-8-sig, cp1252, latin-1.
2. Delimiter: count `; , \t |` on the first 50 non-empty lines; choose the one with the most consistent count per line; fallback `csv.Sniffer`.
3. Header row: first row with ≥ 3 non-empty cells where ≥ 60 % of cells are non-numeric `[P]`; rows above are skipped and logged.
4. Decimal: if a sampled numeric column matches `^\d{1,3}(\.\d{3})*,\d+$` in ≥ 80 % of cases → decimal comma; else dot.
5. Dates: try in order ISO 8601, `%d/%m/%Y[ %H:%M[:%S]]`, `%d.%m.%Y`, `%d-%m-%Y`, `%Y%m%d`, Excel serial (numeric 20000–60000); choose the format that parses ≥ 98 % of a 2,000-row sample; ambiguous day/month (both ≤ 12) → prefer `dd/mm` for FR, log a warning.
6. Excel: choose the sheet with the most rows unless specified; headers may be on row 2–5 (same rule as step 3).

**Algorithm — mapping**
1. `normalize(h)`: NFKD, strip accents, lower-case, non-alphanumerics → space, collapse spaces.
2. Score per (target, column): 1.0 on exact synonym match; else `max over synonyms` of `rapidfuzz.fuzz.token_set_ratio / 100`.
3. Content check on a 1,000-row sample: inferred type (datetime / number / string) must be compatible with the target, else `score × 0.5`; `sku` prefers high cardinality, `qty_units` prefers small integers, `order_id` prefers repeated values with grouped timestamps.
4. Greedy assignment by descending score; a source column is used once. Thresholds `[P]`: ≥ 0.85 auto-accept, 0.60–0.85 suggest (requires confirmation), < 0.60 unmapped.
5. Required targets unmapped → interactive prompt (CLI/UI) or `MappingError` (exit 2) in `--non-interactive` mode unless a mapping file is provided.
6. Unit hints: dims → if P95 of length < 100 → assume cm, ×10, warning W_UNITS_DIMS; weight → if median > 500 → assume grams, ÷1000, warning W_UNITS_WEIGHT. Both require confirmation.
7. Persist `mapping/<dataset>.yaml` (Appendix E) with the sniff results; reuse on the next ingest of the same client.

**Validation rules**

| Rule | Check | Severity `[P]` | Action |
|---|---|---|---|
| R1 | `order_ts` null or unparseable | blocking if > 1 % of lines, else warning | rows dropped, counted |
| R2 | `sku` absent from master | warning if > 1 %, blocking if > 5 % | kept; `has_dims=false` |
| R3 | `qty_units` = 0 | warning | rows dropped |
| R4 | `qty_units` < 0 | info | `is_return=true` |
| R5 | exact duplicate rows | warning | deduplicated, counted |
| R6 | same (order_id, sku) on several rows | info | merged (sum qty) if `merge_duplicate_sku_lines` |
| R7 | dims or weight missing on SKU | warning if line coverage < 95 % | counted; affects eligibility |
| R8 | dims or weight implausible (> 3,000 mm, > 1,500 kg, < 1 mm, < 1 g) | warning | set to null |
| R9 | history < 3 months | blocking | stop |
| R10 | history < 12 months | warning | seasonality flagged L |
| R11 | quantities multiples of `units_per_case` on > 90 % of lines (SKUs with case > 1) | warning | ask whether qty is units or cases |
| R12 | zero-order days on expected operating days > 5 % | warning | calendar review |
| R13 | outliers: lines per order or units per line > median + 10 × MAD | warning | listed, never removed automatically |
| R14 | inventory snapshot older than 6 months or missing | warning | stock stats flagged L |

**DQ score `[P]`.** `score = 100 − 25·blocking (cap 50) − 5·warnings (cap 25) − 20·(1 − dims_coverage_lines) − 10·[history < 12 months]`, clipped to [0, 100]. Bands: ≥ 80 usable; 60–79 usable with caveats; < 60 remediation needed. The band is printed on the report cover.

**Anonymisation.** `HMAC-SHA256(salt, id)[:16]`; salt read from `WHSIZING_SALT` or a file outside the repo; the correspondence table is never written by the tool. Description and customer columns are dropped unless `--keep-descriptions`. The ingest manifest records `anonymized: true`.

**Ingest manifest.** Source files with sha256, sizes and row counts; sniff results; mapping hash; rows in / rows out / dropped per rule; coverage metrics; DQ score; tool version; timestamp.

**Edge cases.** Several files per dataset (append, dedup across files) · order lines with a date but no time (hour = unknown → intraday profile flagged L) · a warehouse/site column (filter in mapping YAML) · order timestamps in the future (R1) · SKUs in master but never ordered (fine) · inventory in cases (R11 logic applies) · receipts without pallets (derived from `units_per_pallet`).

**Tests.** T2.1 encoding and delimiter detection on 6 fixtures. T2.2 header on row 3. T2.3 decimal comma and thousand separators. T2.4 each date format. T2.5 mapping accuracy ≥ 95 % of targets on the FR synthetic CSV without a mapping file. T2.6 each R-rule triggers on its fixture with the right severity. T2.7 DQ score reproduces the formula. T2.8 hashing is stable with the same salt and differs with another. T2.9 end-to-end: three messy files → canonical in < 15 min including a scripted mapping confirmation.

**Tasks (Dev B, days 3–8).** readers + sniff (1 d) · parse (0.5 d) · mapping + synonyms (1.5 d) · rules + DQ report (1.5 d) · anonymise + canonical + manifest (0.5 d) · CLI `ingest` (0.5 d) · tests (0.5 d).

**Done when.** T2.1–T2.9 pass and the DQ report is readable by a non-technical reader (reviewed by the business lead).

---

### F3 — Demand profiling

**Purpose.** Quantify demand and its variability: the basis of every sizing decision.

**Artifacts.** `profile/demand_profile.json`, `canonical/daily_series.parquet`, `profile/charts/*.png` (reports) and `*.html` (UI).

**Signature.** `build_profile(canonical_dir: Path, basis: DesignBasis | None, cfg: ProfileCfg) -> DemandProfile`

**Definitions**
- *Order* = distinct `order_id`. *Line* = distinct (`order_id`, `sku`) after R6 merge. *Unit* = `qty_units`. Cancelled lines are excluded; returns are counted separately.
- *Local date* = `order_ts` converted to `basis.timezone`.
- *Operating day* `[P]` = a date with lines ≥ max(1, 0.10 × median of positive daily lines), unless it is a French public holiday with no volume. Non-operating days are excluded from percentiles and indices. The `holidays` package supplies the calendar (`FR`), with an override list in `ProfileCfg`.

**Algorithm**
1. **Daily and hourly series.** Group by local date (and hour): orders, lines, units, `cube_m3`, `weight_kg`, `return_lines`; join receipts if present. Write `daily_series.parquet`.
2. **Series stats.** For each metric on operating days: mean, P50, P90, P95, P98, max, CV (NumPy percentile, linear interpolation).
3. **EIQ.** Lines per order (mean, P50, P90, P95, max), units per line, units per order, cube and weight per order, single-line share, order classes S (1 line), M (2–5), L (> 5) `[P]`.
4. **ABC / Pareto.** Sort SKUs by lines descending; cumulative share; class A up to 80 %, B up to 95 %, C the rest `[P]`; also by cube movement (units × unit cube) and by stock cube. Output class sizes (SKU share, line share, cube share) and the Pareto curve (100 points).
5. **Stock.** Average over snapshots: units and cube per SKU; `cover_days = Σ stock units / mean daily units shipped`; dead stock = stock > 0 and zero lines in the last 180 days `[P]`; inventory growth = OLS slope on snapshot totals (if ≥ 3 snapshots).
6. **Seasonality.** Monthly index = mean daily lines in month ÷ overall mean daily lines (operating days only), 12 values; weekday index, 7 values; peak-to-average = P95 ÷ mean; trend CAGR = annualised OLS slope of log monthly lines; trend confidence L if < 24 months, M if 24–36, H if > 36 `[P]`.
7. **Intraday.** Share of lines per (weekday, hour) on operating days; `peak_hour_share` = max hourly share on the design weekday (the weekday with the highest mean lines); if more than 20 % of lines have no time component → profile flagged L and replaced by a default profile from `ProfileCfg`.
8. **Shipment split.** Per order: pallet if weight > `pallet_order_weight_kg` or cube > `pallet_order_cube_m3`; otherwise parcel; parcels per order = ceil(weight ÷ `parcel_max_weight_kg`), minimum 1. Output parcel and pallet shares by orders and lines, and mean parcels per order.
9. **Coverage.** `dims_coverage_lines` = share of lines whose SKU has dims and weight.
10. **Charts** (file names): `daily_lines.png` (with P50/P95 lines), `monthly_index.png`, `weekday_index.png`, `intraday_heatmap.png`, `lines_per_order_hist.png`, `pareto.png`, `stock_cover_hist.png`, `cube_weight_scatter.png`.

**Configuration (`ProfileCfg`).** Operating-day threshold, holiday country and overrides, ABC thresholds, dead-stock window, default intraday profile, class boundaries.

**Edge cases.** Multi-day orders (take first timestamp) · a single inventory snapshot (growth = n/a) · a year of data with the peak at the boundary (trailing-window selection in F4 handles it) · daylight-saving changes (use tz-aware conversion; hour 2 missing/duplicated is acceptable).

**Tests.** T3.1 stats on golden data equal the spreadsheet. T3.2 ABC shares sum to 1 and class A line share ≥ 0.8 − ε. T3.3 monthly indices average to 1 (weighted by operating days). T3.4 intraday shares sum to 1 per weekday. T3.5 shipment split: an order of 400 kg → pallet. T3.6 operating-day detection excludes Sundays in `ecom_mid`. T3.7 property: shuffling rows leaves the profile unchanged. T3.8 1 M lines profiled in < 60 s on the CI runner.

**Tasks (Dev A: steps 1–9, days 5–10; Dev B: charts, days 6–9).** aggregate + stats (1 d) · EIQ + ABC + stock (1 d) · calendar + seasonality + intraday (1 d) · shipments + coverage + JSON (0.5 d) · charts (1 d, B) · tests (0.5 d).

**Done when.** T3.1–T3.8 pass and the eight charts render in the stub PDF.

---

### F4 — Design basis and design day

**Purpose.** Capture the client's operating assumptions and define the demand level the site is sized for.

**Artifacts.** `basis.yaml` (Appendix E), `design/design_day.json`, `design/assumptions.json`.

**Signatures.** `load_basis(path) -> DesignBasis` · `basis_template(out: Path, lang) -> None` · `select_design_day(profile, basis, daily: pl.DataFrame) -> DesignDay` · `derive_inbound(profile, basis, daily, sku) -> Inbound`

**Algorithm — design day**
1. Candidate days = operating days in the trailing window (`projection.trailing_months`; use 24 months when available so two peaks are covered; warn if < 12).
2. For each metric `m ∈ {lines, orders, units, cube_m3, weight_kg, parcels, pallets_out}`: `P_m = percentile(candidates[m], p)`.
3. Reference day `r` = actual day with lines nearest `P_lines`. Ratios `ρ_m = m_r / lines_r` give coherent order structure (lines per order, units per line) on the design day.
4. Base design values: `lines* = P_lines`, `m* = lines* × ρ_m`. Report `P_m` alongside; flag `F_RATIO_DRIFT` if `|m* − P_m| / P_m > 15 %` `[P]`.
5. Growth: multiply all by `(1 + g)^T`, `T = projection.horizon_years` (capacity sized for end of horizon). Labor cost per year `t` uses `(1 + g)^t` (F6c).
6. Design weekday = weekday with the highest mean lines; `hourly_lines = intraday[weekday] × lines*`; `peak_hour_lines = max(hourly_lines)`.
7. Stock: `stock_units* = avg stock units × peak_stock_factor × (1 + g)^T`; same for cube (assumes stock scales with demand; override via `overrides["stock_growth_rate"]`).
8. Inbound (see below).
9. Assumptions list: one `Assumption` per basis field with `origin` ∈ {default, client, override, derived}; appears in the report appendix.

**Algorithm — inbound**
- `receipts` mode: daily receipts series → P_p of pallets, receipt lines, units; trucks = pallets ÷ `pallets_per_truck`.
- `derived` mode: `units_in/day = mean units out/day × (1 + g)^T + Δstock_per_year ÷ operating_days`; `pallets_in = Σ_sku units_in_sku ÷ units_per_pallet_sku` (fallback default `[P]` 400 units per pallet, flagged); `receipt_lines = pallets_in × receipt_lines_per_pallet` (`[P]` 1.0 for full pallets, 4 for mixed); `trucks = pallets_in ÷ pallets_per_truck`; `peak_factor = flows.inbound_peak_factor or outbound peak-to-average`.

**Configuration.** All `DesignBasis` fields (§2.5). `basis_template` writes a commented YAML in FR or EN with every default marked `[P]`.

**Edge cases.** `sla_window_hours` derived from the two times, crossing midnight allowed · percentile above the max → clipped to max with `F_PERCENTILE_CLIPPED` · fewer than 60 candidate days → `F_SHORT_HISTORY`.

**Tests.** T4.1 golden design day equals the spreadsheet (P95, ratios). T4.2 changing `design_percentile` changes `lines*` monotonically. T4.3 `sum(hourly_lines) == lines*` within 1e-6. T4.4 derived inbound equals outbound units at g = 0 and constant stock. T4.5 assumptions list contains every basis field exactly once. T4.6 basis YAML with an unknown key → `ConfigError`.

**Tasks (Dev A, days 8–11).** basis loader + template (0.5 d) · design day (1 d) · inbound (0.5 d) · assumptions (0.25 d) · tests (0.5 d).

**Done when.** T4.1–T4.6 pass and the assumptions list renders in the report.

---

### F5 — Automation catalog v0 and eligibility

**Purpose.** Provide neutral, traceable equipment data and determine which part of the SKU range each family can handle.

**Artifacts.** `catalog/families/*.yaml`, `labor_standards.yaml`, `finance_defaults.yaml`, `storage_classes.yaml`, `area_factors.yaml`, `icpe_1510.yaml` (Appendix C and D), `catalog/CHANGELOG.md`.

**Signatures.** `load_catalog(dir: Path) -> Catalog` · `eligible_mask(sku: pl.DataFrame, family: Family, cfg: EligibilityCfg) -> pl.Series` · `eligibility_shares(mask, lines_by_sku, stock_by_sku) -> EligibilityResult`

**Catalog file schema (per family)**

```yaml
id: cube_asrs                      # FamilyId
title: {fr: "AS/RS cube à ports", en: "Cube AS/RS with ports"}
version: 0.1.0
description: {fr: "...", en: "..."}
constraints:
  max_item_mm: [600, 400, 300]     # [P] sorted L ≥ W ≥ H, compared orientation-agnostic
  max_weight_kg: 25                # [P]
  excludes_hazmat: true
  temperature_classes: [ambient, chilled]
  min_scale_lines_day: 1500        # [P] below this the family is flagged F_SCALE_LOW
storage:
  bin_dims_mm: [600, 400, 330]     # [P] external
  bin_net_cube_m3: 0.055           # [P]
  bins_per_m2_per_level: {min: 2.6, typ: 3.0, max: 3.4, unit: "1/m2", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  level_height_mm: 330
  grid_overhead_m: 1.2             # [P] structure + robots on top
  max_levels: 20
  fill_factor: {min: 0.80, typ: 0.88, max: 0.92, unit: "-", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  empty_bin_reserve: 0.05
throughput:
  port_rate_lines_h: {min: 250, typ: 350, max: 450, unit: "lines/h", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  oee: {min: 0.75, typ: 0.85, max: 0.9, unit: "-", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  lines_per_bin_presentation: {min: 1.0, typ: 1.3, max: 1.8, unit: "-", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  dig_factor: {min: 1.3, typ: 1.6, max: 2.0, unit: "-", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  robot_bins_per_h: {min: 15, typ: 22, max: 30, unit: "bins/h", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  robot_availability: {min: 0.9, typ: 0.95, max: 0.98, unit: "-", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
  decant_cases_per_h: {min: 60, typ: 90, max: 120, unit: "cases/h", source: "TODO", confidence: L, pessimistic_end: min, date: 2026-11}
area:
  m2_per_port: {min: 15, typ: 20, max: 25, unit: "m2", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  service_aisle_share: 0.08
capex:
  per_bin_eur: {min: 25, typ: 40, max: 60, unit: "eur", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  grid_structure_per_m2_eur: {min: 400, typ: 650, max: 900, unit: "eur/m2", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  per_robot_eur: {min: 25000, typ: 35000, max: 50000, unit: "eur", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  per_port_eur: {min: 40000, typ: 60000, max: 90000, unit: "eur", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  controls_fixed_eur: {min: 100000, typ: 150000, max: 250000, unit: "eur", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  integration_share: 0.10
  commissioning_share: 0.05
  contingency_share: 0.10
opex:
  maintenance_share_of_equipment_capex: {min: 0.03, typ: 0.05, max: 0.07, unit: "-", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  kwh_per_robot_year: {min: 800, typ: 1200, max: 1800, unit: "kWh", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
  software_eur_year: {min: 20000, typ: 40000, max: 80000, unit: "eur", source: "TODO", confidence: L, pessimistic_end: max, date: 2026-11}
life:
  equipment_life_years: 12
  renewal_share: 0.6
```

Every ranged value **must** be a full `Param` block; scalars are allowed only for structural constants (dims, levels, shares marked `[P]` in `storage_classes.yaml`). All placeholder values above are `[EXPERT]`.

**Family parameter groups (summary; full files in Appendix C)**

| Family | Storage | Throughput | Specific parameters |
|---|---|---|---|
| S0 `manual_p2p` | pallet rack density, levels, pallet load height, shelving bins per m² per level, shelf levels (ergonomic cap), fill factors | pick rate lines/h by zone (shelving, pallet pick), walking share, forklift moves/h | pick-face policy (A/B SKUs), replenishment units per move, cart capacity |
| S1 `amr_gtp` | pod capacity (bins), pod footprint incl. robot aisles, bins per m² (derived) | station rate lines/h, lines per pod visit, robot pod moves/h, availability, charging reserve | robots per station cap, pod replenishment rate |
| S2 `cube_asrs` | see schema above | see schema above | min scale, max robots per m² of grid `[P]` |

**Loader rules.** Reject: missing `unit`/`source`/`confidence`/`pessimistic_end`, `min > typ`, unknown keys, duplicate ids, version not semver. Warn: `source == "TODO"` (counted; the report prints the count of TODO-sourced parameters used). Snapshot the catalog into `runs/.../inputs/catalog/` and record `catalog_version` in the manifest.

**Algorithm — eligibility**
1. Per SKU: sort (l, w, h) descending → (d1, d2, d3); sort `max_item_mm` descending → (L1, L2, L3).
2. `fits = d1 ≤ L1 and d2 ≤ L2 and d3 ≤ L3 and weight ≤ max_weight` (also ≤ `extra_max_weight_kg` if set); `hazmat` and temperature constraints applied.
3. Missing dims or weight → ineligible unless `assume_eligible_if_missing_dims` (then flagged `F_ELIG_ASSUMED` with the share).
4. Shares: by lines (join `lines_by_sku` over the trailing window), by stock cube, by SKU count. Overflow = complement, routed to `overflow_family` (manual) with its own storage, labor and capex.
5. Bin fit for eligible SKUs: `units_per_bin = floor(bin_net_cube × fill / unit_cube)` (volumetric; a nesting factor is backlog).

**Governance.** Changes by pull request with the `[EXPERT]` reviewer; `validated_by` and `date` updated on review; `CHANGELOG.md` entry per change; no brand names, quotes or client data in the catalog; ranges derived from public documentation and expert judgment only.

**Edge cases.** A family where fewer than 50 % of lines are eligible → `F_ELIG_LOW` (the scenario is still computed, with a large overflow zone). A SKU master with dims in cm already converted in F2.

**Tests.** T5.1 loader rejects each malformed fixture (missing unit, min > typ, unknown key, bad semver). T5.2 orientation-agnostic eligibility: a 300×600×400 item is eligible for limits [600, 400, 300]. T5.3 shares: golden dataset eligibility equals the spreadsheet. T5.4 missing dims → ineligible by default, eligible with the flag set. T5.5 `pessimistic_end` inference rule unit tests.

**Tasks (Dev A + expert, days 8–14).** models + loader (1 d) · three family files + supporting files (1.5 d, drafted by A, reviewed by expert) · eligibility (0.75 d) · governance docs and PR template (0.25 d) · tests (0.5 d).

**Done when.** T5.1–T5.5 pass and the expert has initialled every family file (review #1, day 15).

---

### F6 — Sizing engine

**Purpose.** Convert the design day and a scenario definition into storage, equipment, FTE by activity, area and flags, with a full calculation trace.

**Artifacts.** `scenarios/<id>/result.json`, `scenarios/<id>/trace.jsonl`.

**Signature.** `size_scenario(profile, basis, design_day, scenario, catalog, sku: pl.DataFrame, daily: pl.DataFrame, tracer) -> ScenarioResult`

Evaluation order: eligibility → storage → throughput and equipment → labor → area → queue → flags. The function is run once per world (pessimistic, typical, optimistic) by `engine/size.py`; results are merged into `Range`s.

#### F6a — Storage sizing

**Inputs per SKU.** design stock units `s_i` (F4 step 7, allocated per SKU in proportion to average stock), unit cube `v_i`, weight, `units_per_pallet`, `units_per_case`, velocity (lines/day), ABC class, eligibility mask.

**Storage class assignment (`storage_classes.yaml`, `[P]`)**

```
stock_cube_i = s_i × v_i
if family == cube_asrs and eligible_i:      class = cube_bin
elif family == amr_gtp and eligible_i:      class = pod_bin
else (manual family or overflow):
    if not fits_shelf_bin(dims_i) or stock_cube_i ≥ pallet_threshold_m3 (0.6):   class = pallet_rack
    elif stock_cube_i ≤ shelf_bin_net_cube (0.04) × max_bins_per_sku_shelf (6): class = shelving
    else:                                                                        class = pallet_rack
manual pick-face policy: A and B SKUs stored in pallet_rack get one pick face on level 1
    (positions += 1 per such SKU); reserve = remaining pallets
```

**Positions**

```
pallet_rack:  pallets_i   = ceil(s_i / units_per_pallet_i)
              positions   = Σ pallets_i / fill_pallet                 (fill_pallet [P] 0.85, honeycombing)
shelving:     bins_i      = max(1, ceil(stock_cube_i / (shelf_bin_net_cube × fill_shelf)))
              positions   = Σ bins_i                                 (one SKU per bin)
cube_bin:     bins_i      = max(1, ceil(stock_cube_i / (bin_net_cube × fill)))
              if stock_cube_i < 0.2 × bin_net_cube and mixed_bins_allowed: bins_i = 1/skus_per_mixed_bin (4)
              bins_total  = Σ bins_i × (1 + empty_bin_reserve)
pod_bin:      bins as cube_bin with the pod bin size; pods = ceil(bins_total / bins_per_pod)
```

**Levels and footprint**

```
pallet_rack:  levels = min(max_levels, floor((H_clear − top_clearance) / (pallet_load_height + beam_pitch)))
              A = positions / (levels × pallet_positions_per_m2_per_level)      (density includes aisles)
shelving:     levels = min(ergonomic_max_levels, floor(shelf_max_height / bin_pitch))
              A = positions / (levels × bins_per_m2_per_level)
cube_bin:     levels = min(max_levels, floor((H_clear − grid_overhead) / level_height))
              A_grid = bins_total / (levels × bins_per_m2_per_level)
              A = A_grid × (1 + service_aisle_share)
pod_bin:      A = pods × pod_footprint_m2                                       (includes robot aisles)
overflow:     manual classes on the non-eligible share, same formulas
```

Output `StorageResult`: per class positions, levels, area (`Range`), total storage area, height utilisation, flags `F_HEIGHT_LIMIT` (levels capped by building), `F_ELIG_LOW`.

#### F6b — Throughput and equipment

```
λ        = peak_hour_lines / η_flow                   (η_flow [P] 0.85: achievable flow efficiency)
λ_sla    = lines_same_day / sla_window_hours          (wave-driven alternative; take max(λ, λ_sla))
λ_e      = λ × share_lines_eligible ;  λ_o = λ − λ_e   (overflow handled by manual rules)

manual_p2p:
  pickers_peak      = ceil(λ / (pick_rate × η_pick))          by zone (shelving / pallet pick) weighted by line split
  forklifts         = ceil((pallets_in_peak_h + pallets_out_peak_h + replen_moves_peak_h) / forklift_moves_h)
  carts             = pickers_peak
amr_gtp:
  stations          = ceil(λ_e / (station_rate × oee))
  pod_moves_h       = λ_e / lines_per_pod_visit
  robots            = ceil(pod_moves_h / (robot_moves_h × availability) × (1 + charging_reserve))
  flag F_ROBOT_DENSITY if robots / A_storage > max_robots_per_m2
cube_asrs:
  ports             = ceil(λ_e / (port_rate × oee))
  bin_pres_h        = λ_e / lines_per_bin_presentation
  robots            = ceil(bin_pres_h × dig_factor / (robot_bins_h × availability))
  inbound load      : decant_station_hours = cases_in / decant_cases_per_h → adds to ports or dedicated decant stations [P]
  flag F_SCALE_LOW  if design lines/day < min_scale_lines_day
bottleneck          = resource with the highest utilisation at typ
```

Peak-hour pallets: `pallets_in_peak_h = pallets_in × inbound_peak_factor × peak_hour_share_inbound` (`[P]` 0.2 if inbound is spread over a 5-hour receiving window).

#### F6c — Labor (FTE by activity)

**Activities, drivers and standards (`labor_standards.yaml`, all `[EXPERT]`)**

| Activity | Design-day workload | Standard (unit) | Manual | AMR GTP | Cube |
|---|---|---|---|---|---|
| receiving | pallets_in, receipt_lines | pallets/h, lines/h | ✓ | ✓ | ✓ |
| put_away | pallets_in | pallets/h | ✓ | ✓ (to pod decant) | ✓ (decant at port) |
| decant | cases_in = units_in / units_per_case | cases/h | – | ✓ | ✓ |
| replenishment | moves = units_picked_A/B / replen_units_per_move | moves/h | ✓ | – | – |
| picking | lines (manual share), lines_e | lines/h (zone), station/port rate | ✓ | ✓ | ✓ |
| packing | orders (by class S/M/L) | orders/h by class | ✓ | ✓ | ✓ |
| shipping | parcels, pallets_out | parcels/h, pallets/h | ✓ | ✓ | ✓ |
| returns | return_lines | lines/h | ✓ | ✓ | ✓ |
| indirect | share of direct hours | – (`[P]` 0.12) | ✓ | ✓ | ✓ |

```
hours_a            = workload_a / productivity_a × (1 + pfd)               (design day)
heads_design_a     = hours_a / (paid_hours_per_person_day × utilisation)
shift split        : hours by hour-of-day follow the intraday profile for outbound activities (lag [P] 1 h),
                     a flat receiving window (06:00–14:00 [P]) for inbound activities;
                     heads_shift = Σ hours in shift / (hours_per_shift × utilisation), floor 1 per staffed activity
roster             = Σ_shift heads_shift × (1 + absenteeism)
annual_hours_{a,t} = Σ_{operating days d} workload_{a,d} × (1+g)^t / productivity_a × (1 + pfd)   ← daily series, never D* × 365
core_fte_t         = annual_hours_t / (annual_paid_hours_per_fte × utilisation)
core heads/day     = heads at the P50 day [P]; temp_hours_t = Σ_d max(0, hours_d − core_capacity_day)
```

Each activity maps to a role in `finance.labor_cost_eur_h` (operator, forklift driver, team leader) via `labor_standards.yaml`.

Output `LaborResult`: per activity hours, heads, roster (`Range`); totals; annual hours per year; core FTE per year; temp hours per year; shift table.

#### F6d — Area budget and docks

```
receiving_staging  = pallets_in × inbound_peak_factor × m2_per_pallet_staged (1.5) × staging_days (1.0)
shipping_staging   = (pallets_out + parcels / parcels_per_pallet_equiv (40)) × m2_per_pallet_staged
packing            = pack_stations × m2_per_pack_station (12);  pack_stations = ceil(peak_hour_orders / (pack_rate × oee))
gtp / ports        = stations_or_ports × m2_per_station
storage            = F6a total (includes aisles)
returns            = return_lines_design × m2_per_return_line_day (0.05) + fixed (30)
equipment          = robots × m2_per_robot_parking (2.0) + maintenance_fixed (40)
amenities_offices  = roster × m2_per_head (4) + fixed (150)        (may sit outside the footprint → flag F_AMENITIES_EXTERNAL)
circulation        = circulation_share (0.25) × Σ zones except storage
total              = Σ ;  fit = total ≤ building.area_m2 ;  utilisation = total / area ;  deficit_m2 if not fit → F_NO_FIT
docks_in           = ceil(trucks_in_peak_h × dwell_h / dock_utilisation) ; same for docks_out → F_DOCK_SHORTFALL if > building doors
icpe_regime        = lookup(building.area × clear_height) in icpe_1510.yaml → info flag only (regime depends on stored
                     combustible volume and cell design, not building volume alone) [VERIFY]
```

All factors above are `[P]`, stored in `area_factors.yaml`.

#### F6e — Queue / SLA check

Erlang-C on packing stations and on GTP stations/ports.

```python
def erlang_c(c: int, a: float) -> float:          # a = λ/μ offered load; requires a < c
    b = 1.0                                       # Erlang-B recursion for numerical stability
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    rho = a / c
    return b / (1 - rho + rho * b)

P_wait = erlang_c(c, λ_s/μ)
W_q    = P_wait / (c·μ − λ_s)                      # mean wait (hours)
P(W > t) = P_wait × exp(−(c·μ − λ_s) × t)
```

`λ_s` = arrival rate in the SLA window (lines or orders per hour), `μ` = service rate per server. Flag `F_SLA_RISK` if `P(W > sla_window_hours × 0.5) > 5 %` `[P]`; flag `F_UNSTABLE` if `a ≥ c` (then suggest `c_min = ceil(a) + 1`).

#### F6f — Calculation trace

Every intermediate quantity goes through `tracer.record(...)`. Example (typical world):

```json
{"id":"S2.equipment.ports","label":"Cube ports","value":4,"unit":"-",
 "formula":"ceil(lambda_e / (port_rate * oee))",
 "inputs":{"lambda_e":"S2.throughput.lambda_e","port_rate":"param:cube_asrs.port_rate_lines_h","oee":"param:cube_asrs.oee"},
 "scope":"S2","world":"typ"}
```

**Flags produced by F6**

| Code | Severity | Trigger |
|---|---|---|
| F_NO_FIT | warning (blocking in `--strict`) | total area > building area |
| F_HEIGHT_LIMIT | info | levels capped by clear height |
| F_ELIG_LOW | warning | < 50 % of lines eligible |
| F_ELIG_ASSUMED | warning | eligibility assumed for SKUs without dims |
| F_SCALE_LOW | warning | demand below the family's minimum scale |
| F_ROBOT_DENSITY | warning | robots per m² above cap |
| F_DOCK_SHORTFALL | warning | doors required > doors available |
| F_SLA_RISK / F_UNSTABLE | warning | queue check |
| F_RATIO_DRIFT, F_PERCENTILE_CLIPPED, F_SHORT_HISTORY | info | design day |
| F_LOW_CONFIDENCE | info | result depends on ≥ 1 parameter with confidence L (count attached) |
| F_AMENITIES_EXTERNAL | info | amenities counted outside the storage footprint |

**Edge cases.** Zero eligible lines → the automated scenario degenerates to manual with the automation capex at zero and `F_ELIG_LOW`. Building height below one level of the family → `F_HEIGHT_LIMIT` with levels = 1. Stock larger than the building can hold in any family → `F_NO_FIT` for all; the comparison still runs.

**Tests**

| Id | Test |
|---|---|
| T6.1 | Golden: storage positions, levels, area per class equal the spreadsheet (S0, S2) |
| T6.2 | Golden: hours and heads per activity equal the spreadsheet |
| T6.3 | Golden: area budget and docks equal the spreadsheet |
| T6.4 | Erlang-C: `erlang_c(1, 0.5) == 0.5`; `erlang_c(2, 1.0) ≈ 0.3333`; `W_q` matches a closed form |
| T6.5 | Property: more lines → FTE, stations and area are non-decreasing |
| T6.6 | Property: doubling lines and doubling every productivity leaves FTE unchanged |
| T6.7 | Property: outputs are non-negative; lo ≤ typ ≤ hi for every Range |
| T6.8 | Property: row order of inputs does not change the result |
| T6.9 | Reproducibility: rerun from manifest gives identical `result.json` |
| T6.10 | Annual hours computed from the daily series are lower than D* × operating days × hours (guards the peak-×-365 mistake) |
| T6.11 | Every number in `result.json` has a `TraceNode` (IC1 precondition) |

**Tasks (Dev A, days 10–18).** classify + storage (1.5 d) · throughput + equipment (1.5 d) · labor incl. shifts and annual series (2 d) · area + docks + ICPE (1 d) · queue (0.5 d) · trace integration and worlds (1 d) · tests (1 d).

**Done when.** T6.1–T6.11 pass and the expert has reviewed one worked example per family (review #1).

---

### F7 — Finance module

**Purpose.** Translate each sized scenario into a business case: capex, opex by year, TCO, NPV and IRR versus the baseline, payback, cost per line.

**Artifacts.** `scenarios/<id>/finance.json`.

**Signature.** `compute_finance(result: ScenarioResult, basis, catalog, baseline: ScenarioResult | None, labor_series) -> FinancialResult`

**Capex items (year 0)**

| Item | S0 manual | S1 AMR GTP | S2 cube |
|---|---|---|---|
| storage | pallet positions × €/position + shelving bins × €/bin | pods × €/pod | bins × €/bin + grid structure × A_grid |
| equipment | carts, forklifts (× €/unit) | robots × €/robot + stations × €/station + charging | robots × €/robot + ports × €/port |
| controls / software upfront | WMS adaptation fixed `[P]` | WES/fleet software fixed | controls fixed |
| building works | zones changed × €/m² | + floor preparation × A_storage | + floor preparation × A_grid |
| overflow zone | n/a | manual formulas on the overflow share | manual formulas on the overflow share |
| integration, commissioning | shares × equipment subtotal | same | same |
| contingency | share × subtotal | same | same |

Baseline capex = 0 if the client's current operation is the baseline (sunk), else the S0 capex.

**Opex items (years 1..T)**

```
labor_t         = Σ_a annual_hours_{a,t} × cost_role(a) × (1 + shift_premium) × (1 + wage_infl)^(t−1)
                  + temp_hours_t × cost_operator × (1 + temp_premium) × (1 + wage_infl)^(t−1)
maintenance_t   = maintenance_share × equipment_capex
energy_t        = (robots × kWh_per_robot_year + stations × kWh_per_station_year + fixed) × price × (1 + energy_infl)^(t−1)
software_t      = software_eur_year
consumables_t   = orders_t × eur_per_order (packaging [P], same across scenarios unless automation changes packaging)
rent_t          = rent_mode == footprint      : area_total × rent_eur_m2_year
                  rent_mode == full_building  : building.area × rent (identical across scenarios, shown but cancels in deltas)
                  rent_mode == none           : 0
renewal_t       = renewal_share × item_capex when t == equipment_life_years (if ≤ T)
opex_t          = Σ items
```

**Metrics**

```
TCO            = capex + Σ_{t=1..T} opex_t / (1 + r)^t  (+ renewals discounted)
Δ cash flow_t  = (opex_baseline_t − opex_scenario_t)   for t ≥ 1 ;  Δ cash flow_0 = −(capex_scenario − capex_baseline)
NPV_vs_base    = Σ_t Δcf_t / (1 + r)^t
IRR_vs_base    = numpy_financial.irr(Δcf)  → None if undefined (all positive or all negative, or no sign change)
payback_years  = first t where cumulative undiscounted Δcf ≥ 0, linearly interpolated within the year; None if not reached
cost_per_line  = (annualised TCO) / annual lines_year1, annualised TCO = TCO × r / (1 − (1 + r)^−T)
```

Ranges: capex and opex are evaluated in the three worlds (F6 results per world × cost parameters at their pessimistic/optimistic ends).

**Edge cases.** No baseline → NPV/IRR/payback are `None`, the report shows absolute TCO only. Payback beyond horizon → `None`, printed as "> T years". Negative capex delta (scenario cheaper than baseline) → payback 0. IRR with multiple sign changes → `None` with a note.

**Tests.** T7.1 golden finance equals the spreadsheet (S0 vs S2). T7.2 NPV equals `numpy_financial.npv` on the same flows. T7.3 payback interpolation: flows [−100, 40, 40, 40] → 2.5 years. T7.4 `rent_mode=full_building` gives identical rent across scenarios and zero rent delta. T7.5 renewal appears exactly at `equipment_life_years` when ≤ T. T7.6 property: higher labor cost never decreases the NPV of an automated scenario vs manual.

**Tasks (Dev A or B, days 14–20).** capex (1 d) · opex incl. labor series (1.5 d) · metrics (1 d) · worlds and ranges (0.5 d) · tests (1 d).

**Done when.** T7.1–T7.6 pass.

---

### F8 — Scenario runner, comparison and sensitivity

**Purpose.** Run all scenarios on the same demand and present comparable, honest results.

**Artifacts.** `scenarios.yaml` (Appendix E), `comparison/comparison.json`, `comparison/sensitivity.json`.

**Signatures.** `run_scenarios(project: Project) -> RunOutput` · `compare(results, finances) -> Comparison` · `sensitivity_oat(project, params, delta=0.2) -> Sensitivity` · `breakeven(project, target_payback=5.0) -> float | None` · `percentile_sweep(project, [80, 90, 95, 98]) -> list[Row]`

**Runner.** Load project → ingest (or reuse canonical by hash) → profile → design day → for each scenario: `size_scenario` × 3 worlds → finance → write artifacts → comparison → sensitivity → report. Scenarios run in parallel with `joblib` when > 2 (optional). One `RunManifest` per run.

**Comparison table columns.** scenario, eligible line share, storage area, total area, fit, pickers/stations/ports/robots, FTE design day, core FTE year 1, roster, capex (lo/typ/hi), opex year 1, TCO, NPV vs baseline, payback, cost per line, number of warnings, count of confidence-L parameters used.

**Ranking.** By TCO and by payback at typ, always printed with the confidence note: "Ranking at typical values; ranges overlap for scenarios X and Y" (overlap test on `Range`). No automatic "recommended" label.

**Sensitivity (one-at-a-time).** Parameters `[P]`: labor cost (all roles), picking productivity, growth rate, equipment capex, design percentile (90/95/98), fill factor, OEE. For each: run at `typ × (1 ± δ)` (δ = 0.2) or at the catalog min/max; record TCO, payback, FTE. Tornado = ΔTCO sorted by magnitude.

**Break-even.** Labor cost multiplier `k` at which the automated scenario's payback equals `target_payback`, solved with `scipy.optimize.brentq` on `k ∈ [0.3, 3]`; `None` if no root.

**Percentile sweep.** Rows for P80/P90/P95/P98: design lines, stations/ports, FTE, capex, TCO — the service-level trade-off.

**Edge cases.** A scenario failing with `SizingInfeasibleError` in non-strict mode is reported as "not computed" with the reason; the others continue.

**Tests.** T8.1 scenarios YAML with a duplicate id → `ConfigError`. T8.2 comparison contains every scenario once. T8.3 tornado is sorted by |ΔTCO|. T8.4 break-even: a synthetic case with a known root within 1e-3. T8.5 three scenarios × three worlds on `ecom_mid` in < 10 s. T8.6 overlap note appears when ranges overlap.

**Tasks (Dev A, days 18–22).** runner + manifest (1 d) · comparison (0.5 d) · sensitivity + break-even + sweep (1.5 d) · tests (0.5 d).

**Done when.** T8.1–T8.6 pass and `whsizing run-all` works end to end on synthetic data.

---

### F9 — Reporting (Excel + PDF)

**Purpose.** Deliver a client-ready, traceable report with no manual rework. For the first paid studies, report quality matters more than the UI.

**Artifacts.** `report/report_<lang>.xlsx`, `report/report_<lang>.pdf`, `report/diagram_<scenario>.svg`.

**Signatures.** `build_excel(run: RunOutput, lang) -> Path` · `build_pdf(run, lang) -> Path` · `check_integrity(run) -> list[IntegrityIssue]`

**Excel workbook (XlsxWriter)**

| Sheet | Content | Format rules |
|---|---|---|
| Summary | comparison table, confidence note, DQ band, run id | header freeze, number formats `#,##0` and `0.0 %`, conditional colour on fit flag |
| Design basis | every basis field, value, origin | |
| Demand profile | series stats, EIQ, ABC table, seasonality indices, shipment split | charts as images |
| Design day | percentile, growth, metrics (P vs ratio-derived), hourly profile, inbound | |
| Scenarios | side-by-side: eligibility, storage per class, equipment, area per zone, flags | lo/typ/hi columns |
| FTE | activity × scenario: hours, heads, roster; annual hours per year; core FTE; temp hours | |
| Capex / Opex | item × scenario (lo/typ/hi), opex by year | |
| Cash flow | years 0..T per scenario, Δ vs baseline, cumulative | |
| Sensitivity | tornado data, break-even, percentile sweep | |
| Assumptions | id, label, value used, unit, min, typ, max, source, confidence, validated_by, origin (default/client/override) | one row per `Param`, filter enabled |
| Data quality | rule results, coverage, score, dropped rows | |
| Methodology | formulas (Appendix B text), engine and catalog versions, run id, limitations | |

Stretch: live formulas on the FTE and Cash flow sheets so a consultant can change a productivity cell and see FTE and TCO move (requires writing formulas instead of values; keep the value-only version as the default).

**PDF (A4 portrait, 12–18 pages)**

| # | Section | Tables / charts |
|---|---|---|
| 0 | Cover: client, site, date, run id, DQ band, "indicative study" banner | |
| 1 | Executive summary (1 page) | comparison table (typ + ranges), three key messages, caveats |
| 2 | Data and demand | DQ summary, daily lines chart, seasonality, EIQ table, Pareto, shipment split |
| 3 | Design basis and design day | assumptions table (client-provided vs default), design-day table, hourly profile chart |
| 4 | Scenario descriptions | one paragraph per family, eligibility shares, overflow share |
| 5 | Results | equipment table, FTE by activity (stacked bar), area budget table + block diagram per scenario, fit and dock flags |
| 6 | Business case | capex/opex table, TCO bars with ranges, cash-flow chart, payback, cost per line |
| 7 | Sensitivity | tornado chart, break-even sentence, percentile sweep table |
| 8 | Risks, limitations and confidence | limitations box (fixed text + generated items: TODO-sourced parameters count, confidence-L count, flags) |
| A | Appendix: assumptions (full list) | |
| B | Appendix: data-quality report | |
| C | Appendix: methodology and trace index | formulas, versions |

**Block diagram algorithm (`report/diagram.py`).** Zones sorted by area descending; storage placed first as a rectangle spanning the building width with height = area ÷ width; remaining zones packed in rows (strip packing) under it; receiving and shipping placed along the dock wall; scale 1 m = 2 px; labels with name and m²; if total > building area, the overflow is drawn hatched outside the envelope with the deficit printed. Output SVG via Matplotlib.

**Style.** Fonts DejaVu Sans / Liberation Sans; margins 18 mm; neutral palette, scenario colours consistent across all charts; every chart has a caption and a source note ("engine v, catalog v, run id").

**Integrity checks (fail the build, exit 5)**

| Id | Check |
|---|---|
| IC1 | every numeric cell in Summary, Scenarios, FTE, Capex/Opex has a `TraceNode` id |
| IC2 | every `TraceNode` leaf input resolves to a `Param` or a dataset-derived node |
| IC3 | no `Param` used without `source`; count of `source == "TODO"` printed in §8 |
| IC4 | area budget totals reconcile with zone sums (± 0.5 m²) |
| IC5 | FTE totals reconcile with activity sums |
| IC6 | cash-flow cumulative equals Σ Δ cash flows |
| IC7 | units: every value with unit `m2`, `h`, `eur` is non-negative |
| IC8 | i18n: no untranslated key in the rendered HTML (`{{ missing }}` sentinel) |

**i18n.** `report/i18n/{fr,en}.yaml` for labels and fixed texts; number formatting: FR = narrow no-break space thousands and decimal comma, EN = comma thousands and decimal point; dates `dd/mm/yyyy` vs `yyyy-mm-dd`.

**Edge cases.** A scenario not computed → greyed column with the reason. No baseline → business-case section shows absolute values and omits NPV/payback.

**Tests.** T9.1 Excel opens and has the 12 sheets with expected headers. T9.2 Summary values equal `comparison.json` (snapshot). T9.3 PDF has ≥ 12 pages and contains the run id. T9.4 IC1–IC8 each fail on a tampered fixture. T9.5 FR and EN renders have identical numbers. T9.6 block diagram: total drawn area equals the zone sum. T9.7 both files built in < 60 s.

**Tasks (Dev B, days 12–26 spread).** Excel builder (2 d) · PDF templates and CSS (2.5 d) · static charts (1 d) · block diagram (1 d) · integrity checks (1 d) · i18n (0.5 d) · tests (1 d) · polish after review #1 (1 d).

**Done when.** T9.1–T9.7 pass and a reader other than the author can reproduce three numbers of the summary from the appendix.

---

### F10 — CLI and Streamlit wrapper

**Purpose.** Make the pipeline usable by the team (CLI) and demonstrable to prospects (UI). The UI is time-boxed and optional.

**CLI reference (Typer)**

| Command | Key options | Input → output | Exit codes |
|---|---|---|---|
| `whsizing synth <profile.yaml>` | `--out`, `--seed`, `--defects` | profile → Parquet/CSV | 0, 2 |
| `whsizing ingest <files…>` | `--dataset {order_lines,sku_master,inventory,receipts}`, `--mapping <yaml>`, `--non-interactive`, `--salt-file`, `--keep-descriptions` | files → `canonical/`, `dq/` | 0, 2, 3 |
| `whsizing profile <run>` | `--cfg` | canonical → `profile/` | 0, 2 |
| `whsizing basis init` | `--lang`, `--out` | → commented `basis.yaml` | 0 |
| `whsizing size <run>` | `--basis`, `--scenarios`, `--catalog`, `--strict`, `--worlds {typ,all}` | → `design/`, `scenarios/` | 0, 2, 4 |
| `whsizing compare <run>` | `--sensitivity/--no-sensitivity`, `--delta` | → `comparison/` | 0 |
| `whsizing report <run>` | `--lang {fr,en,both}`, `--formats {pdf,xlsx,both}` | → `report/` | 0, 5 |
| `whsizing run-all <project.yaml>` | all of the above | files → full run folder | any |
| `whsizing calibrate <run>` | `--actuals`, `--activity-map`, `--holdout-months 3` | → `calibration/` | 0, 2 |
| `whsizing rerun <run>` | | manifest → new run folder | any |
| `whsizing validate-catalog <dir>` | | → report of errors/TODOs | 0, 2 |

`project.yaml` (Appendix E) lists files, mappings, basis, scenarios, catalog path, language and output directory; `run-all` reuses `canonical/` when input hashes are unchanged.

**Streamlit pages**

| Page | Widgets and behaviour |
|---|---|
| 1 Upload & mapping | file uploader (`server.maxUploadSize = 1024` MB), dataset selector, sniff summary, mapping table (target → column, score, accept toggle), unit-hint confirmations, "Run ingest" |
| 2 Data quality | score badge, blocking issues, warnings with sample rows, coverage metrics, download DQ HTML |
| 3 Demand profile | Plotly charts (daily, seasonality, intraday heatmap, Pareto), EIQ table, shipment split |
| 4 Design basis | form generated from the `DesignBasis` schema (defaults marked), percentile slider, growth input, live design-day preview |
| 5 Scenarios | one card per scenario: family, overrides as sliders bounded by catalog min/max, eligibility settings |
| 6 Results | comparison table, FTE chart, area block diagrams, business case; "why this number?" drill-down: click a cell → `tracer.tree(id)` rendered as an expandable tree down to params; export buttons |

**Rules.** No business logic in the UI; all calls go through the library. `st.cache_data` keyed on input hashes. Every results page carries the "indicative study" banner. State in `st.session_state` with keys `run_dir`, `mapping`, `basis`, `scenarios`. Runs are written to the same run folders as the CLI.

**Edge cases.** Upload larger than memory → suggest the CLI. Browser refresh → state restored from `run_dir`.

**Tests.** T10.1 each CLI command has a smoke test with `--help` and a happy path on `tiny_golden`. T10.2 `run-all` reuses canonical when hashes match (log assertion). T10.3 exit codes per §2.7 on fixtures. T10.4 Streamlit app imports and renders page 6 on a stored run (AppTest).

**Tasks (Dev B, days 22–28).** CLI commands and `project.yaml` (1 d) · pages 1–3 (1 d) · pages 4–6 incl. drill-down (1.5 d) · tests (0.5 d).

**Done when.** T10.1–T10.4 pass and a full demo flow (upload → report) runs without the terminal.

---

### F11 — Back-test and calibration

**Purpose.** Prove that the model reproduces a real site. This is the credibility step of the POC.

**Artifacts.** `calibration/actuals.csv`, `calibration/activity_map.yaml`, `calibration/fit.json`, `calibration/holdout.json`, `calibration/plots/*.png`, `calibration/calibration_note.md`.

**Data required.** ≥ 12 months of order lines; monthly hours (or FTE) per activity including temps and overtime; site facts (area, height, docks, equipment, shifts); loaded hourly costs.

**`actuals.csv`**

| Column | Notes |
|---|---|
| month | `yyyy-mm` |
| activity_client | client's label (mapped via `activity_map.yaml` to model activities) |
| hours | paid hours in the month |
| headcount | optional |
| temp_hours | optional |

**Algorithm**
1. Map client activities to model activities (many-to-one allowed; unmapped hours go to `indirect` with a warning).
2. Build the monthly predicted hours per activity from the daily series with the current catalog values (`whsizing size` on the baseline family, labor only).
3. Parameter vector `θ`: productivity multiplier per activity `m_a ∈ [0.5, 2.0]` `[P]`, flow efficiency `η ∈ [0.6, 1.0]`, PF&D `∈ [0.05, 0.25]`; priors = catalog typ with σ = half the catalog range.
4. Objective: `Σ_i w_i (pred_i(θ) − actual_i)² + λ Σ_j ((θ_j − prior_j)/σ_j)²`, weights `w_i ∝ actual hours`, `λ` = 1 `[P]`; solved with `scipy.optimize.least_squares` (bounds, `loss="soft_l1"`).
5. Time split: fit on the first 9 months, hold out the last 3 (must include the peak month, else shift the split and document it).
6. Metrics on hold-out: MAPE per activity, MAPE on total monthly hours, bias (mean signed error %), peak-month error, peak lines/h error vs the client's observed peak (if available).
7. Plots: predicted vs actual per activity, residuals by month, calibrated multipliers with their prior ranges.
8. Write `calibration_note.md`: method, data period, fitted multipliers, hold-out errors, caveats; the report §8 quotes "calibrated on N site(s)".
9. Catalog update: for a single site, update `typ` only if it stays within the current range; set `confidence` to M and `validated_by` to the expert after review; log in `CHANGELOG.md`.
10. If the error exceeds the target: diagnose by activity (data gap, wrong driver, missing activity such as value-added services, peak definition) and record the correction.

**Acceptance.** Hold-out MAPE ≤ 10–15 % `[P]` on total monthly hours and on the peak month; per-activity errors reported, not gated.

**Edge cases.** Actuals only as headcount → convert with paid hours per month. Activities absent in the model (kitting, VAS) → added as a client-specific activity with its own driver (hours per order) and flagged. Temps not separated → combined hours, note the limitation.

**Tests.** T11.1 synthetic site with known multipliers: fit recovers them within 5 %. T11.2 unmapped activity → warning and `indirect` bucket. T11.3 hold-out split always includes the peak month or raises a documented warning. T11.4 real pilot: metrics computed and note generated (manual acceptance by the expert).

**Tasks (Dev A: fit and evaluation, days 24–30; Dev B: actuals ingestion and plots).** actuals + mapping (0.5 d, B) · fit (1.5 d, A) · evaluation + plots (1 d, A/B) · note + catalog update (0.5 d) · real-data run and diagnosis (1.5 d, both).

**Done when.** T11.1–T11.4 pass or the gap is documented; review #2 signed.

---

## 6. Cross-cutting requirements

### C1 — Reproducibility
- `RunManifest` written at the end of every stage; `whsizing rerun` reproduces a run from its manifest and the stored inputs (T6.9).
- Catalog snapshot copied into the run folder; parameter snapshot includes overrides.
- Seeds recorded; engine version from git (`git describe --always --dirty`); dirty working trees are flagged in the manifest.

### C2 — Data protection (standard operating procedure)
1. NDA and data-processing terms signed; purpose, retention (90 days after delivery `[P]`) and deletion agreed in writing.
2. Transfer by encrypted archive (age or 7-zip AES) or SFTP; never by e-mail attachment.
3. Hash identifiers at ingestion; drop PII and free-text columns by default.
4. Store on encrypted disks; access limited to the three founders; no copies on personal devices.
5. No external API calls on client data (including LLM APIs) without written consent.
6. Delete at the end of retention; send a deletion confirmation; keep only the anonymised calibration note and aggregated statistics.

### C3 — Testing strategy and matrix

| Layer | Scope | Tooling | Gate |
|---|---|---|---|
| Unit | functions in `io/`, `profile/`, `engine/`, `finance/` | pytest | every PR |
| Golden | `tiny_golden` vs spreadsheet (T1.5, T3.1, T4.1, T6.1–T6.3, T7.1) | pytest + syrupy | every PR |
| Property | monotonicity, invariance, non-negativity (T3.7, T6.5–T6.8, T7.6) | hypothesis | every PR |
| Data fuzz | encodings, delimiters, dates, defects (T2.1–T2.6) | fixtures | every PR |
| E2E | `run-all` on `ecom_mid`; snapshot of `comparison.json` | pytest | every PR |
| Reports | sheet/page structure, integrity checks (T9.x) | pytest | every PR |
| Performance | C5 budgets | `just bench` | nightly and before demo |
| Back-test | real site (T11.4) | manual | before review #2 |

Coverage target ≥ 80 % on `engine/` and `finance/` `[P]`.

### C4 — Documentation
`docs/methodology.md` (every formula with its rationale and the assumptions it hides) · `docs/assumptions.md` (generated from the catalog: every parameter, source, confidence) · `docs/adr/` (ADR-001 conventions, ADR-002 worlds and ranges, ADR-003 no simulation in the POC) · `docs/runbook.md` (how to run a study end to end, including the data request and the review checklists).

### C5 — Performance budget (proposals, measured by `just bench` on the CI runner)

| Stage | Budget | Measured on |
|---|---|---|
| ingest + validate | < 2 min | 1 M lines CSV |
| profile | < 60 s | 1 M lines |
| size (3 scenarios × 3 worlds) | < 10 s | any |
| sensitivity (7 params × 2) | < 60 s | any |
| report (both formats) | < 60 s | any |

### C6 — Security (hosted mode only)
Reverse proxy with TLS and basic auth; uploads limited to the team; no public URL; logs without client identifiers.

---

## 7. Day-by-day plan

### 7.1 Capacity check

The feature estimates in §5 add up to roughly 28 working days for Dev A and 31 for Dev B, against 20 available. The plan below therefore splits the POC into a **core (D1–D20)** that delivers the definition of done with the CLI only, and a **completion phase (D21–D30)** for the UI, the stretch items and a second site. Finance (F7) and the runner (F8) are assigned to Dev B to balance the load.

### 7.2 Core, D1–D20 (example calendar: Monday 9 November → Friday 4 December 2026; 11 November is a public holiday in France, shift one day if needed)

| Day | Dev A (engine) | Dev B (product) | Business lead |
|---|---|---|---|
| D1 | Repo and `src/` layout with B; contracts session (§2.5); ADR-001 | Tooling, pre-commit, CI stages | Send NDA and data request (Appendix A); book expert half-days D15 and D20 |
| D2 | `schemas/`, `errors.py`, `logging.py`, `config.py` | Dockerfile, `docker-smoke`, stub PDF (walking skeleton) | Pilot follow-up |
| D3 | Generator core: SKUs, popularity, orders, calendar | Readers and sniffing (F2) | Interviews |
| D4 | Exporters EN/FR, inventory, receipts, `tiny_golden` dataset | Parsing, mapping, synonym dictionary | |
| D5 | Golden spreadsheet (storage, labor, finance); B cross-checks | Rules R1–R14, DQ report | **M1:** synthetic → canonical → stub PDF |
| D6 | Profile: aggregate, stats, EIQ, ABC | Anonymisation, canonical writer, `ingest` CLI, tests | |
| D7 | Stock, calendar, seasonality, intraday, shipments | Profile charts (8), remaining F2 tests | Escalate if no data commitment |
| D8 | Basis loader and template; design day | Excel builder skeleton: sheets, formats, Assumptions sheet | |
| D9 | Inbound, assumptions; catalog models and loader | PDF templates §0–3, i18n basics | Expert reads family drafts (async) |
| D10 | Family YAML ×3, supporting files, eligibility | Trace export, params snapshot; CLI `profile`, `size` skeleton | **M2:** profile, design day, catalog loaded |
| D11 | Classify + storage (F6a) | Finance capex (F7) | |
| D12 | Throughput + equipment (F6b) | Finance opex incl. labor series hook | |
| D13 | Labor: shifts, annual series, temps (F6c) | Finance metrics, worlds, tests | **M3:** S0/S1/S2 sized at typ |
| D14 | Area, docks, ICPE flag (F6d); queue (F6e) | Runner, comparison, manifest (F8) | |
| D15 | Worlds and ranges, F6 tests, worked examples per family | PDF §4–6, block diagram | **Expert review #1** (afternoon, §8.1) |
| D16 | Fixes from review #1 | Fixes; integrity checks IC1–IC8 | |
| D17 | Sensitivity: OAT and tornado | `run-all`, `project.yaml`, `rerun` | Real data arrives → both devs: ingestion and mapping of the real files |
| D18 | Real-data run; design-day sanity; baseline labor run | Actuals ingestion, activity map; PDF §7–8 and appendices | |
| D19 | Calibration fit, hold-out evaluation (F11) | Calibration plots and note; `docs/runbook.md` | Prepare review #2 pack |
| D20 | Fixes; demo rehearsal | Fixes; demo rehearsal | **Expert review #2** (morning, §8.2); **M4:** demo-ready report on real data; retrospective |

### 7.3 Completion, D21–D30

| Item | Owner | Days |
|---|---|---|
| Streamlit pages 1–6 with drill-down (F10) | B | 4 |
| Break-even and percentile sweep (F8) | A | 1.5 |
| Excel live formulas on FTE and Cash flow (F9 stretch) | B | 1.5 |
| PDF polish, EN template, second read by a non-author | B | 1.5 |
| Defect injector completion, more fuzz tests (F1, F2) | A | 1 |
| Second site back-test if data available (F11) | A | 2 |
| Catalog updates from calibration, CHANGELOG, `docs/assumptions.md` generation | A | 1 |
| Performance bench, Docker hardening, hosted mode with basic auth (C5, C6) | B | 1.5 |
| Support of the first paid study (both) | A + B | remaining |

---

## 8. Expert review checklists

### 8.1 Review #1 (D15, half day): catalog and formulas

- [ ] Each family file: ranges plausible, units right, `pessimistic_end` right, obvious omissions listed
- [ ] Storage class thresholds (`storage_classes.yaml`) and the pick-face policy
- [ ] Labor standards per activity: order of magnitude, what they include (walking, scanning, breaks)
- [ ] Area factors and the circulation share; dock-door logic
- [ ] Design-day logic: percentile, growth applied at horizon, hourly profile
- [ ] Eligibility rules and the overflow treatment
- [ ] Finance defaults: integration and contingency shares, maintenance, life
- [ ] One worked example per family on `ecom_mid`: "what would a practitioner challenge first?"
- [ ] Report readability: can the executive summary be shown to a client as "indicative"?
- Output: a list of corrections with priority, `validated_by` and `date` set on reviewed parameters

### 8.2 Review #2 (D20, half day): real-data results and calibration

- [ ] Data-quality report consistent with what the expert knows of the site
- [ ] Demand profile and design day plausible (peak day, hourly profile, shipment split)
- [ ] Baseline labor vs actuals: errors per activity, explanations
- [ ] Fitted multipliers within believable ranges; no activity doing the job of another
- [ ] Automated scenarios: eligibility shares, equipment counts, area fit, flags
- [ ] Business case: capex order of magnitude, opex composition, payback plausibility
- [ ] Limitations box complete and honest
- [ ] Readiness: could this report be delivered to a paying pilot with a verbal walkthrough?
- Output: GO / fix-first / NO-GO on using the tool for the first paid study, with the fix list

---

## 9. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| No real dataset by D17 | medium-high | critical | Data request on D1; accept 6 months; synthetic for development only; escalate D7 | Business lead |
| Model not credible to practitioners | high | critical | Two expert reviews; baseline calibration; ranges and confidence flags; limitations box | All |
| Peak × 365 or unit errors inflate results | medium | high | T6.10, golden cases, property tests, pint at the parameter layer | A |
| Eligibility ignored → automation wins on paper | medium | high | F5 eligibility with overflow zone; eligible share in the summary | A |
| Scope creep (3D, connectors, simulation, UI) | high | high | Scope frozen (§1.3); backlog (§10); UI deferred to completion | All |
| Catalog values contested or stale | medium | medium | Generic families, ranges only, `source` and `validated_by`, CHANGELOG | A + expert |
| Client data mishandled | low | critical | C2 SOP; hashing; local processing; deletion procedure | B |
| Dependency friction (Pango, Chrome, Excel readers) | medium | low | Matplotlib for static charts; Docker image tested in CI from D2 | B |
| Estimates optimistic (see §7.1) | high | medium | Core/completion split; Must items first; daily 15-min sync | All |
| Single-site calibration over-fits | medium | medium | Priors and bounds in the fit; confidence M at most; second site in completion | A |
| Expert unavailable | medium | high | Book both half-days on D1; async review of YAML files from D9 | Business lead |

---

## 10. Deferred backlog (MVP and beyond)

- Discrete-event simulation (SimPy) of the peak-day outbound flow, cross-checked against the analytical sizing
- Monte Carlo on uncertain inputs; probability that scenario A beats B; correlation between parameters
- Light 3D view (no editor); CAD import of the building outline
- LLM-assisted mapping and report narrative, with the C2 safeguards
- Authentication, workspaces, audit trail, EU hosting, job queue, FastAPI service
- Editable catalog UI with provenance and versioning; brand-specific sub-families with vendor-validated data
- Plan-vs-actual KPI import after go-live (bridge to operations without WMS connectors)
- Building geometry and an ICPE/fire-cell rules checker; sprinkler and cell constraints in the layout
- Leasing/RaaS, taxes, depreciation and salvage in finance
- Shift optimisation and labour-law constraints (maximum hours, rest periods) in the roster
- Slotting optimisation, multi-site network design, real-time WMS/ERP connectors, digital twin of operations

---

## Appendix A — Pilot data request and file templates

**Minimum to start:** 6 months of order lines + SKU master with dimensions and weight + one stock snapshot + site facts. **Needed for calibration (F11):** 12 months + monthly hours per activity.

| # | Dataset | Columns (any language, any order) | Format |
|---|---|---|---|
| 1 | Order lines (12–24 months) | order id · order timestamp (creation and/or release) · SKU · quantity (units) · channel (optional) · status (optional) · site (optional) | CSV / Excel / Parquet, one or several files |
| 2 | SKU master | SKU · description (dropped at ingestion) · length · width · height (mm or cm) · weight (kg or g) · units per case · cases per pallet · category · stackable · temperature class · hazmat | CSV / Excel |
| 3 | Stock | SKU · quantity · snapshot date (month-end snapshots preferred, one minimum) | CSV / Excel |
| 4 | Receipts (optional, 12 months) | receipt id · date · SKU · quantity · pallets or trucks | CSV / Excel |
| 5 | Site facts | building area · clear height · dock doors in/out · current storage types and positions · equipment · shifts and operating calendar · current layout (PDF/DWG optional) | form (basis template) |
| 6 | Labor actuals | month · activity · paid hours · headcount · temp hours · overtime · loaded hourly cost by role · absenteeism | CSV (format defined in F11) |
| 7 | Service levels | cut-off times · carrier departures · same-day share · delivery promises | form |
| 8 | Costs | rent €/m²/year · energy price · maintenance contracts · packaging cost per order | form |
| 9 | Legal | NDA signed · anonymisation, retention and deletion terms agreed · transfer channel agreed | before any transfer |

**Template headers (sent with the request)**

```
order_lines.csv:  order_id;order_ts;sku;qty_units;channel;line_status;site
sku_master.csv:   sku;length_mm;width_mm;height_mm;weight_kg;units_per_case;cases_per_pallet;category;stackable;temperature_class;hazmat
inventory.csv:    sku;qty_units;snapshot_date
receipts.csv:     receipt_id;receipt_ts;sku;qty_units;pallets
actuals.csv:      month;activity_client;hours;headcount;temp_hours
```

Clients may keep their own headers: the mapping step handles synonyms (Appendix F).

---

## Appendix B — Consolidated formulas (proposals, `[EXPERT]` review required)

```
# Demand and design day (F3, F4)
operating day         : lines_d ≥ max(1, 0.10 × median(lines_d > 0)), not a holiday without volume
peak_to_avg           : P95(lines_d) / mean(lines_d)                               (operating days)
monthly_index_m       : mean(lines_d | month m) / mean(lines_d)
trend_cagr            : exp(12 × slope(log monthly_lines ~ month_index)) − 1
D*                    : P_p(lines_d, trailing window) ;  m* = D* × (m_r / lines_r), r = day nearest P_p
growth                : capacity metrics × (1+g)^T ;  yearly costs × (1+g)^t
hourly_lines_h        : intraday[design weekday][h] × lines*
inbound (derived)     : units_in = mean units_out × (1+g)^T + Δstock/yr ÷ operating_days
                        pallets_in = Σ_sku units_in_sku / units_per_pallet_sku ; trucks = pallets_in / pallets_per_truck

# Storage (F6a)
pallets_i             : ceil(s_i / units_per_pallet_i) ;  positions_pallet = Σ pallets_i / fill_pallet
bins_i                : max(1, ceil(s_i × v_i / (bin_net_cube × fill)))
levels                : floor((H_clear − overhead) / level_pitch), capped by max_levels / ergonomic limit
area_class            : positions / (levels × positions_per_m2_per_level)      (density includes aisles)

# Throughput and equipment (F6b)
λ                     : max(peak_hour_lines / η_flow, lines_same_day / sla_window_hours)
λ_e                   : λ × share_lines_eligible ;  λ_o = λ − λ_e
stations / ports      : ceil(λ_e / (rate × OEE))
robots (AMR)          : ceil(λ_e / lines_per_pod_visit / (robot_moves_h × availability) × (1 + charging_reserve))
robots (cube)         : ceil(λ_e / lines_per_bin_presentation × dig_factor / (robot_bins_h × availability))
pickers (manual)      : ceil(λ / (pick_rate × η_pick))

# Labor (F6c)
hours_a               : workload_a / productivity_a × (1 + PF&D)
heads_a               : hours_a / (paid_hours_per_person_day × utilisation)
roster                : Σ_shift heads_shift × (1 + absenteeism)
annual_hours_{a,t}    : Σ_d workload_{a,d} × (1+g)^t / productivity_a × (1 + PF&D)      (daily series)
core_fte_t            : annual_hours_t / (annual_paid_hours_per_fte × utilisation)
temp_hours_t          : Σ_d max(0, hours_d − core_capacity_day)

# Area and docks (F6d)
zone areas            : see F6d ;  circulation = share × Σ non-storage zones
fit                   : total ≤ building area ;  deficit = max(0, total − area)
docks                 : ceil(trucks_peak_h × dwell_h / dock_utilisation)

# Queue (F6e)
Erlang-B recursion    : B_0 = 1 ; B_k = a B_{k−1} / (k + a B_{k−1})
Erlang-C              : P_wait = B_c / (1 − ρ + ρ B_c), ρ = a / c
W_q                   : P_wait / (cμ − λ) ;  P(W > t) = P_wait × exp(−(cμ − λ) t)

# Finance (F7)
capex                 : storage + equipment + controls + building works + overflow + (integration + commissioning) × equipment + contingency
opex_t                : labor_t + maintenance + energy_t + software + consumables_t + rent + renewal_t
TCO                   : capex + Σ_t opex_t / (1+r)^t
Δcf_0                 : −(capex_s − capex_b) ;  Δcf_t = opex_b,t − opex_s,t
NPV                   : Σ_t Δcf_t / (1+r)^t ;  IRR: root of NPV(r*) = 0 if it exists
payback               : first t with Σ_{k≤t} Δcf_k ≥ 0, interpolated within the year
cost_per_line         : TCO × r / (1 − (1+r)^−T) / annual_lines_1

# Calibration (F11)
objective             : Σ_i w_i (pred_i(θ) − actual_i)² + λ Σ_j ((θ_j − prior_j)/σ_j)²,  min_j ≤ θ_j ≤ max_j
θ                     : productivity multipliers per activity, η_flow, PF&D
hold-out              : fit on first 9 months, evaluate on last 3 (must contain the peak month)
```

---

## Appendix C — Catalog family files (placeholders, `[EXPERT]`)

Shorthand used in this appendix only: `R(min, typ, max, unit, pessimistic_end)` stands for a full `Param` block with `source: TODO`, `confidence: L`, `date: 2026-11`. The real files must spell out every block (the loader rejects shorthand).

### C.1 `manual_p2p.yaml`

```yaml
id: manual_p2p
title: {fr: "Manuel picker-to-parts", en: "Manual picker-to-parts"}
version: 0.1.0
constraints:
  max_item_mm: [2000, 1200, 1200]      # practically unconstrained; pallets handled by forklift
  max_weight_kg: 1000
  excludes_hazmat: false
  temperature_classes: [ambient, chilled, frozen]
  min_scale_lines_day: 0
storage:
  pallet_rack:
    positions_per_m2_per_level: R(0.30, 0.38, 0.45, "1/m2", min)     # includes aisles (wide-aisle reach truck)
    pallet_load_height_mm: 1400
    beam_pitch_mm: 150
    top_clearance_m: 0.6
    max_levels: 6
    fill_factor: R(0.80, 0.85, 0.90, "-", min)
  shelving:
    bins_per_m2_per_level: R(6, 8, 10, "1/m2", min)
    bin_net_cube_m3: 0.040
    bin_pitch_mm: 400
    shelf_max_height_m: 2.1
    ergonomic_max_levels: 5
    fill_factor: R(0.70, 0.80, 0.90, "-", min)
  pick_face_policy: {classes_with_pick_face: [A, B], faces_per_sku: 1}
throughput:
  pick_rate_shelving_lines_h: R(50, 70, 95, "lines/h", min)         # incl. walking, scanning
  pick_rate_pallet_lines_h: R(25, 35, 50, "lines/h", min)
  eta_pick: R(0.75, 0.85, 0.92, "-", min)
  forklift_moves_h: R(12, 16, 22, "moves/h", min)
  replen_units_per_move: R(40, 80, 150, "units", min)
area:
  m2_per_pack_station: R(10, 12, 15, "m2", max)
capex:
  per_pallet_position_eur: R(60, 90, 140, "eur", max)
  per_shelf_bin_eur: R(8, 12, 18, "eur", max)
  per_forklift_eur: R(25000, 35000, 50000, "eur", max)
  per_cart_eur: R(800, 1500, 3000, "eur", max)
  wms_adaptation_fixed_eur: R(20000, 50000, 120000, "eur", max)
  building_works_per_m2_eur: R(30, 60, 120, "eur/m2", max)
  integration_share: 0.05
  commissioning_share: 0.02
  contingency_share: 0.10
opex:
  maintenance_share_of_equipment_capex: R(0.02, 0.04, 0.06, "-", max)
  kwh_per_forklift_year: R(3000, 4500, 6000, "kWh", max)
  software_eur_year: R(5000, 15000, 40000, "eur", max)
life: {equipment_life_years: 10, renewal_share: 0.5}
```

### C.2 `amr_gtp.yaml`

```yaml
id: amr_gtp
title: {fr: "AMR goods-to-person (pods / bacs)", en: "AMR goods-to-person"}
version: 0.1.0
constraints:
  max_item_mm: [600, 400, 400]
  max_weight_kg: 20
  excludes_hazmat: true
  temperature_classes: [ambient]
  min_scale_lines_day: 800
storage:
  bins_per_pod: R(40, 60, 90, "-", min)
  pod_bin_net_cube_m3: 0.030
  pod_footprint_m2: R(2.0, 2.6, 3.2, "m2", max)                       # incl. robot aisles
  fill_factor: R(0.70, 0.80, 0.88, "-", min)
  empty_bin_reserve: 0.05
throughput:
  station_rate_lines_h: R(150, 250, 350, "lines/h", min)
  oee: R(0.75, 0.85, 0.90, "-", min)
  lines_per_pod_visit: R(1.2, 1.8, 2.5, "-", min)
  robot_pod_moves_h: R(8, 12, 16, "moves/h", min)
  robot_availability: R(0.88, 0.94, 0.97, "-", min)
  charging_reserve: 0.15
  decant_cases_per_h: R(50, 80, 110, "cases/h", min)
  max_robots_per_m2: 0.05
area:
  m2_per_station: R(12, 16, 20, "m2", max)
  m2_per_robot_parking: R(1.5, 2.0, 2.5, "m2", max)
capex:
  per_robot_eur: R(20000, 30000, 45000, "eur", max)
  per_station_eur: R(25000, 40000, 60000, "eur", max)
  per_pod_eur: R(600, 900, 1400, "eur", max)
  fleet_software_fixed_eur: R(80000, 150000, 300000, "eur", max)
  floor_prep_per_m2_eur: R(10, 20, 40, "eur/m2", max)
  integration_share: 0.10
  commissioning_share: 0.05
  contingency_share: 0.10
opex:
  maintenance_share_of_equipment_capex: R(0.04, 0.06, 0.08, "-", max)
  kwh_per_robot_year: R(1000, 1500, 2200, "kWh", max)
  software_eur_year: R(20000, 40000, 80000, "eur", max)
life: {equipment_life_years: 8, renewal_share: 0.6}
```

`cube_asrs.yaml` is shown in F5.

---

## Appendix D — Supporting catalog files (placeholders)

```yaml
# storage_classes.yaml  [P] [EXPERT]
pallet_threshold_m3: 0.6              # design stock cube at or above → pallet rack
shelf_bin_net_cube_m3: 0.040
max_bins_per_sku_shelf: 6
shelf_item_max_mm: [500, 400, 350]
mixed_bins_allowed: true
skus_per_mixed_bin: 4
mixed_bin_threshold_share: 0.2
default_units_per_pallet: 400        # fallback when case/pallet data is missing (flagged)

# area_factors.yaml  [P] [EXPERT]
m2_per_pallet_staged: 1.5
staging_days: 1.0
parcels_per_pallet_equiv: 40
m2_per_return_line_day: 0.05
returns_fixed_m2: 30
maintenance_fixed_m2: 40
m2_per_head_amenities: 4
amenities_fixed_m2: 150
circulation_share: 0.25
receiving_window_hours: 8
peak_hour_share_inbound: 0.2

# labor_standards.yaml  [P] [EXPERT]  (R shorthand as in Appendix C)
roles: {operator: operator, forklift: forklift_driver, lead: team_leader}
activities:
  receiving:      {driver: pallets_in,   standard: R(10, 14, 18, "pallets/h", min), role: forklift}
  receipt_check:  {driver: receipt_lines, standard: R(30, 45, 60, "lines/h", min), role: operator}
  put_away:       {driver: pallets_in,   standard: R(10, 13, 16, "pallets/h", min), role: forklift}
  decant:         {driver: cases_in,     standard: family.decant_cases_per_h,     role: operator}
  replenishment:  {driver: replen_moves, standard: R(10, 14, 18, "moves/h", min), role: forklift}
  picking:        {driver: lines,        standard: family.pick_or_station_rate,   role: operator}
  packing_S:      {driver: orders_S,     standard: R(40, 55, 70, "orders/h", min), role: operator}
  packing_ML:     {driver: orders_ML,    standard: R(18, 25, 32, "orders/h", min), role: operator}
  shipping_parcel:{driver: parcels,      standard: R(80, 110, 140, "parcels/h", min), role: operator}
  shipping_pallet:{driver: pallets_out,  standard: R(10, 14, 18, "pallets/h", min), role: forklift}
  returns:        {driver: return_lines, standard: R(15, 22, 30, "lines/h", min), role: operator}
  indirect:       {share_of_direct_hours: 0.12, role: lead}
profiles:
  outbound_lag_hours: 1.0
  inbound_window: ["06:00", "14:00"]

# finance_defaults.yaml  [P]
packaging_eur_per_order: R(0.6, 0.9, 1.3, "eur", max)
fixed_energy_kwh_year: 20000
default_roles_cost_eur_h: {operator: 26, forklift_driver: 28, team_leader: 34}   # replaced by client values
wms_adaptation_default_eur: 30000

# icpe_1510.yaml  [VERIFY] informational only; regime depends on stored combustible volume and cell design
regimes:
  - {label: "Déclaration (D/DC)",  min_m3: 5000,   max_m3: 50000}
  - {label: "Enregistrement (E)",  min_m3: 50000,  max_m3: 900000}
  - {label: "Autorisation (A)",    min_m3: 900000, max_m3: null}
note_fr: "Indicatif : classement selon le volume de l'entrepôt (rubrique 1510), à confirmer avec un bureau ICPE."
```

---

## Appendix E — Project, basis, scenarios and mapping YAML

```yaml
# project.yaml
name: pilot_client_x
language: [fr]
out_dir: runs/
catalog: catalog/
salt_file: ~/.whsizing/salt_client_x
inputs:
  order_lines: {files: [data/ventes_2025.csv, data/ventes_2026.csv], mapping: mapping/order_lines.yaml}
  sku_master:  {files: [data/articles.xlsx], sheet: "Articles", mapping: mapping/sku_master.yaml}
  inventory:   {files: [data/stock_*.csv], mapping: mapping/inventory.yaml}
  receipts:    null
basis: basis/client_x.yaml
scenarios: scenarios/client_x.yaml
profile_cfg: {abc_thresholds: [0.80, 0.95], dead_stock_days: 180}
options: {worlds: all, sensitivity: true, delta: 0.2, strict: false}
```

```yaml
# basis.yaml (excerpt; `whsizing basis init` writes the full commented template)
client: "Client X"
site: "Lyon"
operations: {operating_days_per_year: 252, shifts_per_day: 2, hours_per_shift: 7.0, paid_hours_per_person_day: 7.0,
             annual_paid_hours_per_fte: 1607, utilisation: 0.85, absenteeism: 0.06, pfd_allowance: 0.12}
service:    {cutoff_time: "15:00", carrier_departure_time: "18:30", same_day_share: 0.6}
projection: {horizon_years: 5, growth_rate: 0.04, design_percentile: 95, peak_stock_factor: 1.15, trailing_months: 24}
flows:      {returns_rate: 0.04, inbound_mode: derived, pallets_per_truck: 26, truck_dwell_hours: 1.0, dock_utilisation: 0.7,
             pallet_order_weight_kg: 300, pallet_order_cube_m3: 0.6, parcel_max_weight_kg: 30}
building:   {area_m2: 12000, clear_height_m: 10.5, dock_doors_in: 4, dock_doors_out: 6, rent_eur_m2_year: 58, rent_mode: footprint}
finance:    {discount_rate: 0.08, horizon_years: 5, wage_inflation: 0.025, energy_inflation: 0.03, energy_price_eur_kwh: 0.17,
             labor_cost_eur_h: {operator: 25.5, forklift_driver: 27.8, team_leader: 33.0}, temp_premium: 0.15}
baseline:   {description: "Current manual operation, 2 shifts", actual_fte: {picking: 18, packing: 9, receiving: 4, shipping: 5, indirect: 4}}
overrides:  {"manual_p2p.pick_rate_shelving_lines_h": 62}      # documented as client override
```

```yaml
# scenarios.yaml
scenarios:
  - {id: S0, name: "Manuel optimisé", family: manual_p2p, is_baseline: false}
  - {id: S1, name: "AMR goods-to-person", family: amr_gtp,
     overrides: {"amr_gtp.station_rate_lines_h": 230}}
  - {id: S2, name: "AS/RS cube", family: cube_asrs,
     eligibility: {assume_eligible_if_missing_dims: false}}
baseline: client_current      # or a scenario id
```

```yaml
# mapping/order_lines.yaml (written by `ingest`, reusable)
dataset: order_lines
files: [data/ventes_2025.csv, data/ventes_2026.csv]
encoding: cp1252
delimiter: ";"
header_row: 1
decimal: ","
date_format: "%d/%m/%Y %H:%M"
timezone: Europe/Paris
columns: {order_id: "N° commande", order_ts: "Date commande", sku: "Référence", qty_units: "Qté", channel: "Canal", line_status: null}
filters: [{column: "Entrepôt", equals: "LYON"}]
unit_hints: {}
merge_duplicate_sku_lines: true
```

---

## Appendix F — Synonym dictionary (excerpt of `synonyms_fr_en.yaml`)

| Target | Synonyms (normalised) |
|---|---|
| order_id | order id, order, order number, order no, commande, n commande, num commande, no commande, numero commande, bl, order ref, reference commande |
| order_ts | order date, order time, date, date commande, date de commande, created at, creation date, date creation, timestamp, release date, date liberation |
| sku | sku, item, item code, article, code article, reference, ref, product id, product code, ean, gtin |
| qty_units | qty, quantity, quantite, qte, units, nb pieces, pcs, pieces, qty shipped, qte expediee |
| channel | channel, canal, customer type, type client, sales channel |
| line_status | status, statut, etat, line status |
| length_mm | length, longueur, long, l, len |
| width_mm | width, largeur, larg, w |
| height_mm | height, hauteur, haut, h |
| weight_kg | weight, poids, poids unitaire, unit weight, kg |
| units_per_case | pcb, units per case, colisage, uc par colis, case pack, pack size |
| cases_per_pallet | cases per pallet, colis par palette, cartons par palette, pal |
| snapshot_date | date stock, stock date, date inventaire, as of |
| receipt_id | receipt, reception, asn, po, bon de reception |
| receipt_ts | receipt date, date reception, delivered on |
| pallets | pallets, palettes, nb palettes |

Normalisation strips accents, case and punctuation, so "Qté" and "qte" match.

---

## Appendix G — Glossary

| Term | Meaning |
|---|---|
| ABC / Pareto | Classification of SKUs by pick frequency, cube movement or stock cube |
| AMR | Autonomous mobile robot |
| AS/RS | Automated storage and retrieval system |
| Baseline | The operation every scenario is compared with: the client's current site or S0 |
| Brownfield | Project on an existing site (vs greenfield) |
| Design day | Demand level (percentile of daily volumes plus growth) the site is sized for |
| EIQ | Entry–Item–Quantity analysis: lines per order, units per line, SKU frequency |
| Eligibility | Share of SKUs, lines and stock a family can physically handle |
| FTE | Full-time equivalent |
| GTP | Goods-to-person picking |
| ICPE 1510 | French regulatory heading for covered warehouses; regime indicative here |
| IRR / NPV / TCO | Internal rate of return / net present value / total cost of ownership |
| OEE | Overall equipment effectiveness |
| Overflow zone | Manual area for the non-eligible share of an automated scenario |
| PF&D | Personal, fatigue and delay allowance applied to labor standards |
| Range (lo/typ/hi) | Result evaluated in the pessimistic, typical and optimistic worlds (§2.5.1) |
| SLA window | Time between order cut-off and carrier departure |
| Trace | The recorded chain formula → inputs → parameters behind every number |
| UoM | Unit of measure (units vs cases vs pallets) |
| World | A coherent set of parameter values: pessimistic, typical or optimistic |