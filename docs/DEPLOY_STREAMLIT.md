# Demo on Streamlit

`streamlit_app.py` is the public demo of whsizing: the app's own six pages on a **fictitious
e-commerce site**, generated on demand. It is what you deploy on Streamlit Community Cloud, and
what `just demo-app` runs on your machine. The full app for real client files stays local
(`just app`).

## What a visitor sees

- **Open the finished example** (about 10 s the first time on a laptop, longer on the platform where it was not measured; instant afterwards): a complete study of
  the demo site (three scenarios, finance, sensitivity) on page 6, with the "why this number?"
  drill-down and the Excel / PDF exports.
- **Load the demo data (step by step)**: the four datasets ingested into a run of the visitor's own;
  pages 2 to 5 (data quality, demand profile, design basis, scenarios) start from the demo basis
  and scenarios, and the visitor sizes the run on page 5.
- French or English: the browser's language, then the switch in the sidebar (kept from page to
  page).

## Demo mode: what it does and does not allow

`streamlit_app.py` sets `WHSIZING_DEMO_ONLY=1` before anything else, so a hosted copy can never be
the open app. In demo mode:

| | Full app (`just app`) | Demo (`streamlit_app.py`) |
|---|---|---|
| Upload of client files | yes | **no** (page 1 offers the demo data) |
| Typed path of a file on the server | yes | **no** (it would read any file of the server) |
| Data | the client's, anonymised at ingestion | synthetic, generated on the first visit |
| Salt | typed or `$WHSIZING_SALT` | random per server process (a salt you set is kept) |
| Runs a visitor can open | all of the runs folder | only the demo's: the shared example and the run of their session. A run opens by its name (`?run=`); a visitor's run name ends in 16 random hex digits, so the link is the key to it (the data is synthetic) |
| Old runs | kept | a visitor's demo run older than 3 hours is removed the next time anyone loads the demo data, and so are the oldest above 30 (the shared example stays) |
| Address | loopback only (on another one every page shows an error) | any (the platform has to reach it) |
| Commands | one at a time per server process (`calls._LOCK`) | same; one that waits more than 2 minutes behind another gives up with a "server busy" message |
| Inputs | any | bounded, see below |
| Unexpected errors | the traceback of the page | the type of the error only (`client.showErrorDetails = type`) |
| Upload route | up to 1 GB (`just app` raises `server.maxUploadSize`) | none: `.streamlit/config.toml` sets `server.maxUploadSize = 0`, so every non-empty body is refused (413). Streamlit serves the route even without an uploader and keeps what it takes in memory: with a cap of 1 MB, 300 requests of 0.9 MB were kept (+283 MB). An empty upload sent in chunks is still recorded, with its name and type (about 4 KB per request, some 230 times less than at a cap of 1 MB): an accepted residual |

Why uploads are off: the specification (C2) keeps client data on the team's machines, and a hosted
demo is somebody else's server. Do not put real client data in a deployed copy.

### What the demo bounds, and why

One process serves every visitor, and a command cannot be interrupted once it runs. A security
review of the demo froze it with plain widgets (measured on the demo study), so the demo refuses
these inputs with a message that names the limit (`whsizing.app.demo_limits`; the library and the
full app have no such limits):

| Input | Limit | What it cost without the limit |
|---|---|---|
| `finance.horizon_years`, `projection.horizon_years` | at most 20 years | `finance.horizon_years` of 320: about 51 s and 2.4 GB in `compare` (20 years take about 8 s); a 320-year `projection.horizon_years` is refused by the engine's own guard in 2 s |
| number of scenarios | at most 6 | 30 scenarios: about 102 s in `compare`; the PDF of 20 scenarios: 34 s and 46 pages |
| an override of a constant (`engine.max_equipment_count` and the other structural scalars) | not allowed | that guard refuses a queue model that needs millions of stations (a packing rate far below the catalog's asks for 1.3 to 2.8 million: refused in 2 s). Lifted, a security review saw the engine run for minutes on such an input; a later audit measured 10 s with the packing rate, so this limit is kept as a precaution |
| an override of a parameter | inside the catalog's own range (`min` to `max`) | the engine's guard trips only for a value that pushes a queue model over 100,000 stations (a packing rate about a million times too low, refused in 2 s); one 700 times below the range (0.055 for a range of 40 to 70) is sized without error. The range limit bounds the rest and keeps the numbers of the demo meaningful |
| `operations.shifts_per_day` | at most 4 | 300 shifts of a few minutes (the library only asks for one shift at least, and 24 hours in all): 34 s and 2.1 GB in `size` and `compare`; 1,000 shifts about 2 minutes and 4 GB |
| a text: the client, the site, a scenario's id or name, an override's id | at most 200 characters (the demo's longest is 47); a YAML box of overrides at most 10,000, without aliases (`*name`) | a 2 MB box was parsed again at every rerun (5.7 s of CPU each, outside the locks); 200 KB of YAML with a few aliases took 7 s and 2.5 GB at every rerun; a 400,000-character client name without spaces made the PDF take 14 s under the lock, and 20,000 characters of words took 20 s and added 10 pages |

A number typed as text (`"0.000055"`, `1e-5`, which YAML reads as text) is checked like a number: the
library reads it as one.

Several other numeric fields (`operations.utilisation` of 1e-5, a `building.area_m2` of 5e7, a
`stock_growth_rate` override of 9, a `parcel_max_weight_kg` of 1e-5, ...) have one effect in common:
the sized plan of the building becomes tens of square kilometres, and the block diagram measured its
labels on a raster canvas of that size (2.4 to 4.6 GB at the peak of page 6). That is bounded where
it happens, in `report/diagram.py` (the canvas of a plan beyond 4 million pixels is measured at a
lower resolution: 1.1 GB for each of those inputs, as for the demo's own; a plan beyond about 30 km2,
which no warehouse is, is not drawn: page 6 and the report say so and name the design basis), so none of
those fields has a limit of its own.

Also: at most two heavy page computations at a time (`loaders.HEAVY_AT_ONCE`: eight at once took
the process from 0.9 to 2.8 GB), and the messages a visitor sees show `<runs>` where the server's
folders would be. A visitor can still make 30 demo runs and so push the oldest ones of other
visitors out of the 30 kept (a free demo; run it behind a login if that matters), and the commands
run in the server's process: a hostile visitor with a lot of patience is not stopped by these
limits, only the accidental or cheap ones are. Running every command in a child process with a
time and memory limit is the real fix, and would be a change of `whsizing.app.calls`.

## Run it locally

```bash
just demo-app          # = uv run streamlit run streamlit_app.py --server.address 127.0.0.1
```

## Deploy on Streamlit Community Cloud

1. Push the repository to GitHub (a private repository works: Community Cloud asks for the GitHub
   `repo` permission and reads it through a read-only deploy key; you need admin rights on it).
2. On <https://share.streamlit.io>: **Create app** → **Yup, I have an app**, then
   - Repository: `<your-user>/whsizing`, Branch: `main`
   - **Main file path: `streamlit_app.py`**
   - Optional: a custom subdomain.
3. **Advanced settings**: Python version **3.12**, chosen explicitly: the lock was made and tested on 3.12 (`requires-python` is `>=3.12`), and the platform's default may differ from it (its documentation names 3.12 for now, and says it follows new Streamlit-supported versions), so the choice is made here, not left to a default.
   Secrets are optional: `WHSIZING_LANG = "fr"` makes French the default language (otherwise the
   browser's language decides), `WHSIZING_SALT = "..."` replaces the random salt. Write them at the
   top of the secrets text, outside any `[section]`: only top-level keys become environment
   variables. `WHSIZING_DEMO_ONLY` is set by `streamlit_app.py` itself and cannot be switched off
   from outside.
4. **Deploy.** The first build installs the locked dependencies and the system packages, then the
   app starts; the first visitor to click "Open the finished example" waits for the build of the
   demo study (about 10 s on a laptop; the platform's instances are smaller, expect longer: not measured there).

What the platform reads from the repository, and why:

| File | Role |
|---|---|
| `uv.lock` + `pyproject.toml` | the dependencies, pinned. Community Cloud takes the first dependency file it finds in this order: `uv.lock`, `Pipfile`, `environment.yml`, `requirements.txt`, `pyproject.toml`; do not add a second dependency file. The `app` group (Streamlit) is a default group, so a plain `uv sync` installs it. |
| `packages.txt` | Debian packages for the PDF report (WeasyPrint needs Pango): `libpango-1.0-0 libpangoft2-1.0-0` and fonts; `tzdata`, the time-zone database that ingestion reads (a no-op where the image has it). Every line must exist on **Debian 11**, the release whose package list the Community Cloud documentation points to: one unknown name aborts the apt step and the deployment. That is why `libharfbuzz-subset0`, which the WeasyPrint documentation also lists, is not here: Debian 11 does not have it (Debian 12 does) and WeasyPrint 70 loads that library only if present. The `Dockerfile` and the CI runner, newer systems, install it. Without the Pango packages the app still runs and the PDF button shows an error instead of crashing. |
| `streamlit_app.py` | the entry point. It makes `src/` importable when the platform installs the dependencies without the project itself. |
| `.streamlit/config.toml` | telemetry off, an upload cap of 0 (the hosted demo takes no upload; `just app` passes `--server.maxUploadSize 1024`). No `server.address`: it would stop the platform from reaching the app. |
| `catalog/`, `basis/demo_basis.yaml`, `scenarios/demo_scenarios.yaml`, `data/synth/profiles/demo.yaml` | what the demo reads. Community Cloud starts the app from the root of the repository, which is where they are looked for. |

Limits of the platform to keep in mind (from its documentation at the time of writing: check it):
an app without traffic goes to sleep after 12 hours and starts again on the next visit (the demo
study is rebuilt); the files written while it runs are not durable; an app has roughly 2 CPU cores
and 2.7 GB of memory (the demo needs 1.0 to 1.3 GB at its peak); the platform sets
`browser.gatherUsageStats` itself, so Streamlit's own usage statistics are on for a hosted app
whatever `.streamlit/config.toml` says.

## What was checked, and what only the platform can tell

Checked on the build machine (macOS with Docker Desktop), on a clean copy of the repository:

- `uv sync --frozen` (what a `uv.lock` host runs) installs Streamlit through the default `app` group
  and the project; the server starts in about a second and answers its health check.
- A real headless Chromium drives it: the home page renders, one click builds the finished example
  (about 10 s on this machine), the Results page shows the comparison, tables, block diagrams and
  business case, and the Excel and PDF (17 pages) are built from the page. No error in the browser
  console. Peak memory of the whole flow: 1.0 to 1.3 GB.
- The same flow inside the Docker image (Debian Linux, built from `uv.lock`; its apt list has the
  Pango, harfbuzz and font packages), PDF built with WeasyPrint on Linux included; about 1.0 GiB in
  the container.
- An emulation of the Community Cloud build on **Debian 11**, the release its documentation names:
  every line of `packages.txt` installed with `apt-get install` (an unknown name aborts it: an
  earlier version of the file listed `libharfbuzz-subset0`, which Debian 11 does not have),
  `uv sync --frozen` on Python 3.12, then the app served to a headless Chromium. The finished
  example opens in about 16 s on the build machine, the Excel and the PDF (17 pages) are built,
  and neither the page nor the server log shows an error. It ran in an arm64 container, and the
  image pins `archive.debian.org` for Debian 11 (the stock repositories answered 404 for some
  security packages when it was built).
- `streamlit_app.py` under Streamlit's `AppTest` (`tests/e2e/test_f10_app_demo.py`,
  `tests/unit/test_f10_app_demo_data.py`): banner, no uploader, language kept across pages, visitors
  separated, the finished example built once and opened by two visitors, the step-by-step path sized
  through the pages, a host without Pango giving a message instead of a crash.
- Every locked dependency has a binary wheel for Debian 11 on x86_64 with Python 3.12:
  `uv export --frozen --no-hashes --no-emit-project -o req.txt` then
  `uv pip install --dry-run --python-platform x86_64-manylinux_2_31 --python-version 3.12 --only-binary :all: -r req.txt`.

Not checkable from here: the deployment itself on Community Cloud (its uv version, the exact way it
installs a `uv.lock` project, its memory under load, x86_64 instead of the arm64 used for the
container run). If the first build fails, its log (the "Manage app" panel) names the step; the usual
suspects are a dependency that needs a system library, or a Python version other than 3.12.

## The same demo in a container

```bash
docker build -t whsizing:dev .
docker run --rm -p 8501:8501 --entrypoint streamlit whsizing:dev \
    run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
```

Then open <http://localhost:8501>. (The full app refuses a non-loopback address; the demo accepts
it.)
