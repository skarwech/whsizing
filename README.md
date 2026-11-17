# whsizing

Warehouse sizing POC: turn a prospect's order lines, SKU master and stock into a traceable sizing
and business case for three generic automation scenarios (manual picker-to-parts, AMR
goods-to-person, cube AS/RS), as a French or English PDF and Excel report in which every number
traces to a formula and a parameter. Results are **lo / typ / hi ranges** from placeholder catalog
parameters: an *indicative study*, not a quotation. Specification: `description.md`.

## Quickstart

```bash
uv sync --all-extras                                              # Python 3.12 and every dependency (uv.lock)
uv run whsizing synth data/synth/profiles/ecom_mid.yaml           # synthetic data in data/generated/ecom_mid
WHSIZING_SALT=choose-a-secret uv run whsizing run-all project/example_project.yaml
```

The last command ingests the CSV files, sizes the three scenarios, compares them and writes the
reports; it prints the comparison table and ends with the run folder, `runs/<timestamp>_<hash>/`
(`report/report_fr.pdf`, `report/report_fr.xlsx`, `manifest.json`, `scenarios/<id>/trace.jsonl`).
On a laptop it takes about twenty seconds. The salt anonymises identifiers (HMAC-SHA256); keep a
real one outside the repository. PDF needs Pango: on macOS `brew install pango` and, if
`import weasyprint` fails, `export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` (the justfile does).

## Demo on Streamlit

```bash
just demo-app      # synthetic e-commerce site, three scenarios, no upload: http://localhost:8501
```

`streamlit_app.py` is the entry point to deploy on [Streamlit Community Cloud](https://share.streamlit.io)
(Main file path `streamlit_app.py`); `docs/DEPLOY_STREAMLIT.md` has the steps, what the hosted demo allows
and what was checked. The full app for real client files stays local: `just app`. The hosted demo
bounds what a visitor can ask of the engine (a horizon of at most 20 years, at most 6 scenarios,
parameters inside the catalog's range); the library and the full app have no such limits.

## Layout

```
src/whsizing/   schemas/ (frozen contracts) · io/ (F2) · profile/ (F3) · design/ (F4) · catalog/ (F5)
                engine/ (F6) · finance/ (F7) · scenarios/ (F8) · report/ (F9) · cli/ + app/ (F10)
                calibration/ (F11) · synth/ (F1)
catalog/        equipment families, labor standards, area, finance defaults (every value a [P] placeholder)
basis/  scenarios/  project/      example design basis, scenarios and project.yaml (Appendix E)
data/synth/     synthetic profiles (tiny_golden, ecom_mid, b2b_cases)
tests/          unit · golden (hand-checked oracle) · property · e2e · fixtures
docs/           methodology, runbook, pilot guide, assumptions, interpretations register, ADRs
```

## Tests and checks

```bash
just test          # ruff, pyright, then pytest (unit, golden, property, e2e; not the bench marker)
just test-fast     # unit tests only
uv run pytest tests/unit/test_f5_*.py -q       # one feature
just app           # the full Streamlit app, loopback only (export WHSIZING_SALT first)
just demo-app      # the public demo: synthetic data, no upload
```

Test ids follow `test_T<feature>_<n>_...` in `tests/**/test_f<feature>_*.py`. `just --list` shows every
recipe (`bench`, `golden-update`, `docker-demo`, ...). Always run `uv run ...` from the repository
root, never the system Python. `just demo` runs the quickstart (synthetic data, then `run-all`; `WHSIZING_SALT` defaults to a demo value);
`just docker-demo` does the same inside the image (not run here: Docker is not installed).

## Documentation

- [`docs/runbook.md`](docs/runbook.md): install, environment, every command with real output, run
  folder, exit codes, troubleshooting.
- [`docs/DEPLOY_STREAMLIT.md`](docs/DEPLOY_STREAMLIT.md): the Streamlit demo, locally and on Community Cloud.
- [`docs/PILOT.md`](docs/PILOT.md): pilot checklist, data protection, how to read the report, calibration and
  expert reviews.
- [`docs/methodology.md`](docs/methodology.md): every formula, its rationale, hidden assumptions, worked numbers,
  open expert rulings and known limits.
- [`docs/assumptions.md`](docs/assumptions.md): the 72 catalog parameters (generated:
  `uv run python -m whsizing.catalog.assumptions`).
- [`docs/INTERPRETATIONS.md`](docs/INTERPRETATIONS.md): the binding register where the spec is ambiguous;
  [`docs/adr/`](docs/adr): conventions, worlds and ranges, no simulation.
