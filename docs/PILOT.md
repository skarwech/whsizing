# Pilot guide

For the team running the first paid or unpaid studies and for the pilot client's contact. Sources:
spec Appendix A (data request), C2 (data protection), F9 (report), F11 (calibration), §8 (expert
reviews); the commands are in [`runbook.md`](runbook.md), the formulas in
[`methodology.md`](methodology.md), the rulings in [`INTERPRETATIONS.md`](INTERPRETATIONS.md).

**What the tool produces is an indicative study**: lo/typ/hi estimates from a proof-of-concept
model on the data as extracted, with catalog parameters that are placeholders until an expert has
validated them. It is not a quotation, a commitment or a validated design. Say so to the client
before the first file is sent and again when the report is handed over.

## 1. Pilot checklist

### 1.1 Before any file moves (legal and organisational)

- [ ] NDA and data-processing terms signed; purpose, retention (90 days after delivery `[P]`) and
      deletion agreed **in writing** (C2 step 1).
- [ ] Anonymisation terms agreed: the tool *pseudonymises* (hashed identifiers, §2); whether that is
      enough for this client is a matter for the data-processing terms, not for the tool.
- [ ] Transfer channel agreed: encrypted archive (age or 7-zip AES) or SFTP, **never an e-mail
      attachment** (C2 step 2).
- [ ] One person owns the salt for this client (a long random secret, kept outside any repository,
      on an encrypted disk; `runbook.md` §2).
- [ ] Domain expert booked for two half-days: review #1 (catalog and formulas) and review #2
      (real-data results and calibration) (spec §1.5, §8).
- [ ] Decisions recorded (spec §1.5): report languages (French first, English template second), design
      percentile and horizon (P95, 5 years `[P]`), baseline definition (the client's current operation
      if documented, else S0), hosting (local only).

### 1.2 The data request (spec Appendix A)

**Minimum to start**: 6 months of order lines + a SKU master with dimensions and weight + one stock
snapshot + the site facts. **Needed for the calibration** (F11): 12 months + monthly hours per
activity. Prefer 12 to 24 months: seasonality and trend are flagged low confidence under 12 and 24
months, a history under 3 months is a blocking DQ rule, and the design day is the P95 of the last 24
months when available. Clients may keep their own headers (French or English, any order): the
mapping step handles the usual synonyms.

| # | Dataset | Content (any language, any column order) | Format |
|---|---|---|---|
| 1 | Order lines (12-24 months) | order id, order timestamp (creation and/or release), SKU, quantity in units, channel (optional), status (optional), site (optional) | CSV / Excel / Parquet, one or several files |
| 2 | SKU master | SKU, description (dropped at ingestion), length, width, height (mm or cm), weight (kg or g), units per case, cases per pallet, category, stackable, temperature class, hazmat | CSV / Excel |
| 3 | Stock | SKU, quantity, snapshot date (month-end snapshots preferred, one minimum) | CSV / Excel |
| 4 | Receipts (optional, 12 months) | receipt id, date, SKU, quantity, pallets or trucks | CSV / Excel |
| 5 | Site facts | building area, clear height, dock doors in and out, current storage types and positions, equipment, shifts and operating calendar, layout (PDF/DWG optional) | form: the `basis.yaml` template |
| 6 | Labor actuals | month, activity, paid hours, headcount, temp hours, overtime, loaded hourly cost by role, absenteeism | CSV (§4) |
| 7 | Service levels | cut-off times, carrier departures, same-day share, delivery promises | form (basis `service`) |
| 8 | Costs | rent €/m²/year, energy price, maintenance contracts, packaging cost per order | form (basis `building`, `finance`) |
| 9 | Legal | NDA signed, anonymisation, retention and deletion terms agreed, transfer channel agreed | before any transfer |

Template headers sent with the request (the tool also reads the French equivalents):

```
order_lines.csv:  order_id;order_ts;sku;qty_units;channel;line_status;site
sku_master.csv:   sku;length_mm;width_mm;height_mm;weight_kg;units_per_case;cases_per_pallet;category;stackable;temperature_class;hazmat
inventory.csv:    sku;qty_units;snapshot_date
receipts.csv:     receipt_id;receipt_ts;sku;qty_units;pallets
actuals.csv:      month;activity_client;hours;headcount;temp_hours
```

What makes a file usable, from experience of the DQ rules (methodology §1.2): quantities in **units**
(not cases: R11 asks); a timestamp with the time, not only the date (the intraday profile and the
peak-hour sizing need it; above 20 % of lines without a time the profile is the default and flagged
low confidence); dimensions and weight on every SKU that ships (R7: below 95 % of lines covered is a
warning, and an SKU without them cannot be given to automation); the SKU master complete (R2: more
than 5 % of ordered SKUs missing is blocking); a recent stock snapshot (R14: over 6 months old is a
warning); cancelled and returned lines flagged, or negative quantities for returns.

### 1.3 What to send and what not to send

| Send | Do not send (recommendation; not a spec rule) |
|---|---|
| order lines with order id, SKU, quantity, timestamp, channel, status | customer names, delivery addresses, e-mail, phone, any personal data |
| SKU master with dimensions, weight, pack data, category, hazmat and temperature class | free-text product descriptions (the tool drops them anyway; they are still in the file you sent) |
| stock snapshots, receipts, site facts, service levels, costs, monthly labor hours | prices, margins and carrier tariffs (not used by the model) |
| the layout if the client wants it considered (the POC does not read it) | credentials, network diagrams, anything the model does not ask for |

The tool drops `description` and `customer` columns by default (`--keep-descriptions` keeps them; a
kept customer column is still hashed) and hashes `order_id`, `sku`, `receipt_id` and `customer`. The
safest data minimisation is a request that does not ask for the sensitive column in the first place.

### 1.4 Run, review, deliver

- [ ] Ingest, read the DQ report **with the client** (`runbook.md` §3.2). The band (usable, usable with
      caveats, remediation needed) is printed on the report cover.
- [ ] Fill the design basis with the client: every `[CLIENT]` value, confirm the `[P]` ones.
- [ ] `run-all project.yaml`; keep the run folder name and the project files in the study notes
      (`runbook.md` §3.9).
- [ ] Calibrate on the site's actuals (§4); expert review #2.
- [ ] Hand over the PDF/Excel with a verbal walkthrough (§3); do not send the run folder.
- [ ] Retention and deletion (§2.3).

## 2. Data protection (C2): what the tool does and what you do

### 2.1 What the tool does

- **Local processing.** Nothing is uploaded. The package imports no network client (a grep of
  `src/` for `requests`, `urllib`, `http.client`, `httpx`, `aiohttp`, `socket`, `smtplib` finds
  none; third-party packages were not audited) and calls no external API, LLM APIs included. The
  Streamlit config disables usage statistics (`.streamlit/config.toml`); the app is a local server.
  Only `uv` needs the network, to install packages, with two exceptions of Streamlit itself, neither
  carrying client data: started **headless** (`--server.headless true`, typical in Docker or on a
  server) it makes a best-effort request to `checkip.amazonaws.com` at start-up to print an
  "External URL" (`net_util.get_external_ip`), and started non-headless it opens a UDP `connect()` to
  8.8.8.8 to learn the machine's internal IP (no packet is sent). Setting `server.address`, as
  `just app` does (`127.0.0.1`), avoids the lookups. The same setting keeps the app
  **loopback-only**: it has no authentication, so on any other address the full app **answers every
  page with an error** (the server still listens: start it with `--server.address 127.0.0.1`, as
  `just app` does; `WHSIZING_ALLOW_REMOTE=1` says an authenticating proxy is in front: a separate, deliberate
  step, C6). `just app` also passes `--server.maxUploadSize 1024`: the repository's
  `.streamlit/config.toml` takes no upload (cap 0), for the hosted demo, so a full app started
  some other way (behind a proxy, say) needs that flag too for files of real size (page 1 says so
  when the cap is small; a typed path or `whsizing ingest` has no cap). The public demo (`streamlit_app.py`, `docs/DEPLOY_STREAMLIT.md`) is the one exception:
  synthetic data only, no upload, no typed server path; never put client data in a hosted copy. C2 step 5 asks for written consent before any external call on client data: no call
  carries client data in this version.
- **Hashing at ingestion.** `HMAC-SHA256(salt, id)[:16]` on order id, SKU, receipt id and customer;
  `description` and customer columns dropped by default; the correspondence table is never written;
  the ingest manifest records `anonymized: true`. The salt comes from `$WHSIZING_SALT` or a salt
  file outside any git repository and is never written into a run.
- **Data stays where it is.** The manifest hashes the client's files (sha256) but does not copy
  them; the run keeps the *hashed* canonical tables, the mapping (column *names* of the client's
  files), the DQ report (it quotes sample rows after hashing) and the results.
- **What a run folder still reveals.** Dimensions, weights, volumes, dates, the building and cost
  facts: commercially sensitive even without identifiers. Treat the whole run folder as client
  data.

### 2.2 What you do (C2 steps 2 to 4)

- Receive the archive on an encrypted channel; extract it to an encrypted disk; access limited to
  the founders; no copies on personal devices.
- Keep the salt apart from the data and the reports.
- Never paste client rows into an issue, a chat or an LLM prompt (C2 step 5).
- Hosted mode (not in the POC) would need the C6 controls: TLS reverse proxy with basic auth, no
  public URL, logs without client identifiers.

### 2.3 Retention and deletion (C2 step 6)

At the end of the retention period (90 days after delivery `[P]`, or as agreed in writing): delete
the client's original files, the run folders (canonical tables, DQ report, traces, reports) and
every copy including backups and the salt; send the client a **deletion confirmation**; keep only
what the terms allow, normally the anonymised `calibration_note.md` (no client name, aggregated
errors and multipliers) and aggregated statistics. Catalog changes learned from a client site go to
`catalog/CHANGELOG.md` without client data.

## 3. How to read the report

The report is a PDF (A4, about 12 to 18 pages) and an Excel workbook (12 sheets) built from the same
numbers; `report/report_<lang>.{pdf,xlsx}`. The French and English files carry identical numbers.

### 3.1 The banner and the cover

The cover carries the **"indicative study" banner**: "INDICATIVE STUDY - sized on the client's data
extract and catalog placeholders; not a design for tender." (French: "ÉTUDE INDICATIVE - ..."), and
every other page header reads "Indicative study" (the Streamlit results pages carry the banner too).
The cover also gives the client, site, date, **run id** (any number can be traced
to it, `runbook.md` §3.8) and the **data-quality band** (usable / usable with caveats / remediation
needed, with the score out of 100). A band under "usable" means the findings below inherit the
caveats listed in the DQ appendix.

### 3.2 Ranges: lo / typ / hi

Each result is shown as the typical value with a **low-high range** below it. The range comes from a
pessimistic and an optimistic *world* (all parameters at their pessimistic or optimistic end at
once). It **bounds** the result; it is **not a confidence interval** and not a probability
(methodology §0.3). Wide ranges are normal while every parameter is a placeholder; they shrink as
parameters are validated or calibrated. Do not compare the typical values of two scenarios without
looking at the ranges: the report says "ranges overlap for scenarios X and Y" when their TCO ranges
touch, and then **those scenarios cannot be told apart**. There is no "recommended" label.
Payback beyond the horizon is printed "> T years" or "not reached"; NPV, IRR and payback exist only
against a baseline.

### 3.3 Executive summary (page 1)

A comparison table at typical values with ranges, and three key messages: the TCO ranking (with the
overlap note), the payback against the baseline, and people and space (design-day heads, total area
and whether each scenario fits the building). Caveats follow. Read the **eligible line share** and
the **fit** column before the cost: a scenario that automates 40 % of the lines, or does not fit,
is not what its TCO suggests.

### 3.4 Flags

Flags are in each scenario's results and in the limitations box (section 8). Severity: *warning*
needs a conversation, *info* is context. Codes carry a value after `:` where the spec attaches one.

| Flag | Meaning | What to ask or do |
|---|---|---|
| `F_NO_FIT` (warning) | total area above the building area | read the area table; the deficit is printed; not an error |
| `F_HEIGHT_LIMIT:<class>` (info) | the building height, not the catalog, caps the levels | clear height is a client fact: confirm it |
| `F_ELIG_LOW` (warning) | under half of the lines are eligible for the automation | most volume goes to the manual overflow zone: the scenario is "mostly manual" |
| `F_ELIG_ASSUMED:<share>` (warning) | some lines are eligible only because SKUs without dimensions were assumed to fit | get the dimensions; `--strict` refuses this |
| `F_SCALE_LOW` (warning) | the design day is below the family's minimum scale | the automation is probably not justified at this volume |
| `F_ROBOT_DENSITY` (warning) | robots per m² above the catalog cap (0.05, an open `[EXPERT]` value) | treat as a prompt for the expert |
| `F_DOCK_SHORTFALL` (warning) | more dock doors needed than the building has | check dock hours and truck dwell time |
| `F_UNSTABLE:<pool>` / `F_SLA_RISK:<pool>` (warning) | the queue check says demand exceeds capacity, or waiting beyond half the SLA window is likely | `c_min` is the number of stations the SLA window needs (open `[EXPERT]` ruling, I69) |
| `F_SHORT_HISTORY` (info) | fewer than 60 operating days in the window | the design day is weakly supported |
| `F_RATIO_DRIFT:<m>` (info) | the design-day value of metric `m` built from the reference day differs from its percentile by over 15 % | normal for lumpy metrics (pallets out, weight) |
| `F_PERCENTILE_CLIPPED` (info) | design percentile above 100 was cut to the maximum day | |
| `F_INBOUND_SPARSE`, `F_RECEIPTS_NO_PALLETS` (warning) | receipts mode: few receipt days, or no pallet counts | load more receipts or use derived inbound |
| `F_DEFAULT_UPP:<share>` (info) | units per pallet defaulted to 400 for SKUs without pack data | ask for case and pallet data |
| `F_LOW_CONFIDENCE:<n>` (info) | the result reads `n` catalog parameters of confidence L | see §3.5 |

### 3.5 Confidence L

Every catalog parameter carries `confidence` H, M or L; in the shipped catalog (`manual_p2p` 0.1.0, `amr_gtp` 0.2.0, `cube_asrs` 0.2.0; the manifest prints `manual_p2p=0.1.0 amr_gtp=0.2.0 cube_asrs=0.2.0`) **all 72 are L with source
TODO**. The report counts, per scenario, the confidence-L parameters its formulas read (about 30 for
a manual scenario, 50 for the cube, `F_LOW_CONFIDENCE:<n>`), and the limitations box says how many of
the catalog parameters used have the source TODO. Until the expert has reviewed and a calibration
has covered a parameter, read the report as *orders of magnitude and structure* (which resource
binds, whether it fits, how the scenarios rank *and* overlap), not as a quotation. The Assumptions
table (appendix and sheet, filter enabled) lists each parameter with min, typ, max, source,
confidence and `validated_by`; client values and overrides are marked *client* and *override*.

### 3.6 Checking a number

Appendix C of the PDF (the trace index) lists, per scenario, the Summary numbers with their trace id,
formula and direct inputs; the three numbers of the "done when" test (total area, design-day heads,
TCO) can be reproduced from the PDF alone. In the Excel workbook every traced cell carries a
comment with the node id, the world, the formula and its inputs. Deeper chains are in
`report/trace.jsonl` and `scenarios/<id>/trace.jsonl`; `runbook.md` §5 shows how to expand one.

### 3.7 What the report does not say

No supplier, brand or quotation; no building structure, permits (the ICPE 1510 regime is a prompt to
ask an ICPE office, `[VERIFY]`), tax or financing; no simulation (waiting times come from an Erlang-C
approximation); no forecast beyond the growth rate in the basis. The limitations box (section 8) is
generated from the run: it states what was TODO-sourced, which flags were raised and which scenario
was not computed.

## 4. Calibration and expert reviews

### 4.1 Data and files

The back-test compares the model's baseline labor with the site's real monthly hours. Needed:
**at least 12 months** of order lines (the actuals' months must be months of the daily series) and
monthly paid hours per activity, temps and overtime included. With fewer than 12 months of actuals
the tool warns (`W_SHORT_HISTORY`); it does not stop.

`actuals.csv` (`,` or `;` separated; with `;` a decimal comma is allowed), one row per month and
client activity, and a row for every month of every activity (write 0 for none):

| Column | Notes |
|---|---|
| `month` | `yyyy-mm` |
| `activity_client` | the client's label, mapped by `activity_map.yaml` |
| `hours` | paid hours in the month, temps and overtime included |
| `headcount` | optional; a row with a headcount and no hours gets `headcount × annual_paid_hours_per_fte / 12` (flag `I_HEADCOUNT_ONLY`) |
| `temp_hours` | optional, informational; never more than `hours`; without it temps are not separated (`I_TEMPS_COMBINED`) |

`activity_map.yaml` maps the client's labels (case and spacing ignored) to the model's activities:
`receiving` (also takes receipt checks), `put_away`, `decant`, `replenishment`, `picking`,
`packing`, `shipping`, `returns`, `indirect`. Several labels may map to one activity. A label that is
missing goes to `indirect` with a warning (`W_UNMAPPED_ACTIVITY`); an activity the model does not
have (kitting, value-added services) must be declared under `client_activities` and is then reported
as client-specific (`F_CLIENT_ACTIVITY`), not fed into the catalog:

```yaml
activities:
  Réception: receiving
  Mise en stock: put_away
  Préparation: picking
  Emballage: packing
  Expédition: shipping
  Retours: returns
  Encadrement: indirect
  Kitting: kitting
client_activities: [kitting]
```

### 4.2 Running it and reading it

```bash
uv run whsizing calibrate runs/<run> --actuals calibration/actuals.csv --activity-map calibration/activity_map.yaml
```

(`--holdout-months 3` by default.) The run must be sized; the baseline is the scenario that
`scenarios.yaml` names as baseline, else the manual family (`runbook.md` §3.10 runs it end to end
on synthetic data). Outputs in `<run>/calibration/`: `calibration_note.md`, `fit.json`,
`holdout.json`, `plots/`.

- **Acceptance** (`[P]`): MAPE on total monthly hours **and** the peak-month error both ≤ 15 % on the
  hold-out months (spec: 10 to 15 %). The command prints `calibration accepted` or `NOT accepted`
  with both figures. Per-activity errors are reported, not gated.
- **Hold-out** = the last 3 months, shifted to start at the peak month when the peak is not in them
  (`W_HOLDOUT_SHIFTED`). Partial months (an extract starting or ending mid-month) are left out
  (`W_PARTIAL_MONTH`).
- **Fitted multipliers** `m` (productivity vs the catalog, 0.5 to 2.0) should be believable: a
  multiplier at a bound, or one activity absorbing another's hours, is a diagnosis, not a result.
  Read `Effective` (the identified value) in `calibration_note.md`; η and PF&D are not identified
  separately from the multipliers.
- **If the error exceeds the target**, diagnose by activity before touching parameters: a data gap
  (missing months, temps not in the hours), a wrong driver (an activity driven by lines that the
  client drives by orders), a missing activity (kitting, VAS), the peak definition. Record the
  correction in the note (spec F11 step 10).
- **Catalog update** (library function `update_catalog`, run by hand on a *copy*): for one site,
  `typ` is updated only if it stays within the current range; confidence becomes M and
  `validated_by` the expert's name only after the review; a `catalog/CHANGELOG.md` line per change.
  One site never makes a parameter H. The report then says "calibrated on N site(s)".

### 4.3 Expert reviews (spec §8)

Review #1 (catalog and formulas) and review #2 (real-data results and calibration) are required
before a client sees a study from the tool (definition of done, spec §1.4). Pack for the expert:
`docs/methodology.md`, `docs/assumptions.md`, the open rulings (`methodology.md` §10.1), the report
of a worked example per family, the DQ report and the calibration note.

**Review #1 (half day): catalog and formulas.**
- [ ] each family file: ranges plausible, units right, `pessimistic_end` right, omissions listed
- [ ] storage class thresholds and the pick-face policy
- [ ] labor standards per activity: order of magnitude, what they include (walking, scanning, breaks)
- [ ] area factors, the circulation share, the dock-door logic
- [ ] design-day logic: percentile, growth at the horizon, hourly profile
- [ ] eligibility rules and the overflow treatment
- [ ] finance defaults: integration and contingency shares, maintenance, life
- [ ] one worked example per family: "what would a practitioner challenge first?"
- [ ] report readability: can the executive summary be shown to a client as "indicative"?
- Output: a list of corrections with priority; `validated_by` and `date` set on reviewed parameters.

**Review #2 (half day): real-data results and calibration.**
- [ ] DQ report consistent with what the expert knows of the site
- [ ] demand profile and design day plausible (peak day, hourly profile, shipment split)
- [ ] baseline labor vs actuals: errors per activity, explanations
- [ ] fitted multipliers believable; no activity doing the job of another
- [ ] automated scenarios: eligibility shares, equipment counts, area fit, flags
- [ ] business case: capex order of magnitude, opex composition, payback plausibility
- [ ] limitations box complete and honest
- [ ] readiness: could this report go to a paying pilot with a verbal walkthrough?
- Output: **GO / fix-first / NO-GO** on using the tool for the first paid study, with the fix list.

The register's open rulings (`INTERPRETATIONS.md`, "Open expert rulings"; `methodology.md` §10.1) are
the natural agenda: I33 (temp hours counted twice in the labor cost), I46 (robot density cap), I48
(degenerate cube scenario), I64 and I65 (receipts-mode temp hours, floor of one head per shift), I69
(pack stations vs the queue check), I73 (AMR capex, client-current baseline), I76 (sensitivity
definitions, break-even bracket), and the three input-format rulings I53, I54, I67.
