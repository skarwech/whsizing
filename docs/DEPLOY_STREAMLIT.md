# Demo on Streamlit

`streamlit_app.py` is the public demo of whsizing: the app's own six pages on a **fictitious
e-commerce site**, generated on demand. It is what you deploy on Streamlit Community Cloud, and
what `just demo-app` runs on your machine. The full app for real client files stays local
(`just app`).

## What a visitor sees

- **Open the finished example** (about 30 s the first time, instant afterwards): a complete study of
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
| Runs a visitor sees | all of the runs folder | only runs made by the demo; never another visitor's |
| Address | loopback only (the app refuses another one) | any (the platform has to reach it) |
| Commands | one at a time per server process (`calls._LOCK`) | same |

Why uploads are off: the specification (C2) keeps client data on the team's machines, and a hosted
demo is somebody else's server. Do not put real client data in a deployed copy.

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
3. **Advanced settings**: Python version **3.12** (the default; `requires-python` is `>=3.12`).
   Secrets are optional: `WHSIZING_LANG = "fr"` makes French the default language (otherwise the
   browser's language decides), `WHSIZING_SALT = "..."` replaces the random salt.
4. **Deploy.** The first build installs the locked dependencies and the system packages, then the
   app starts; the first visitor to click "Open the finished example" waits for the build of the
   demo study (the platform's instances are smaller than a laptop: expect 30 s or a little more).

What the platform reads from the repository, and why:

| File | Role |
|---|---|
| `uv.lock` + `pyproject.toml` | the dependencies, pinned. Community Cloud takes the first dependency file it finds in this order: `uv.lock`, `Pipfile`, `environment.yml`, `requirements.txt`, `pyproject.toml`; do not add a second dependency file. The `app` group (Streamlit) is a default group, so a plain `uv sync` installs it. |
| `packages.txt` | Debian packages for the PDF report (WeasyPrint needs Pango): `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0` (the list of the WeasyPrint documentation for Debian) and fonts. Without them the app still runs and the PDF button shows an error instead of crashing. |
| `streamlit_app.py` | the entry point. It makes `src/` importable when the platform installs the dependencies without the project itself. |
| `.streamlit/config.toml` | telemetry off, upload limit. No `server.address`: it would stop the platform from reaching the app. |
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
- The same flow inside the Docker image (Debian Linux, built from `uv.lock` and `packages.txt`'s
  package list), PDF built with WeasyPrint on Linux included; about 1.0 GiB in the container.
- `streamlit_app.py` under Streamlit's `AppTest` (`tests/e2e/test_f10_app_demo.py`,
  `tests/unit/test_f10_app_demo_data.py`): banner, no uploader, language kept across pages, visitors
  separated, the finished example built once and opened by two visitors, the step-by-step path sized
  through the pages, a host without Pango giving a message instead of a crash.
- Every locked dependency has a binary wheel for Debian 11 on x86_64 with Python 3.12
  (`uv pip install --dry-run --python-platform x86_64-manylinux_2_31 --only-binary :all:`).

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
