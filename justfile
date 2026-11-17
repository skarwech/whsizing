# whsizing task runner (§3.2). `just --list` shows every recipe.

# WeasyPrint loads Pango via dlopen. On macOS with Homebrew, if `import weasyprint` fails with
# "cannot load library 'libgobject-2.0-0'", this fallback path fixes it. Harmless elsewhere.
export DYLD_FALLBACK_LIBRARY_PATH := env("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

default:
    @just --list

# ruff lint + format check
lint:
    uv run ruff check src tests streamlit_app.py
    uv run ruff format --check src tests streamlit_app.py

# pyright: strict on schemas/, engine/, finance/; basic elsewhere (pyproject.toml)
typecheck:
    uv run pyright

# lint, typecheck, unit + golden + property tests
test: lint typecheck
    uv run pytest -m "not bench"

# unit tests only
test-fast:
    uv run pytest tests/unit -m "not slow and not bench" -q

# NOTE: `python -m tests.golden.build_golden` regenerates tests/golden/golden_values.json (the
# spreadsheet oracle the golden tests compare against): a different thing from the snapshots below.

# regenerate the syrupy snapshots (tiny_golden golden layer, ecom_mid comparison.json); asks first
[confirm("Regenerate golden snapshots? Review the diff before committing. [y/N]")]
golden-update:
    uv run pytest tests/e2e/test_snapshots.py --snapshot-update

# demo (§3.2): synthetic ecom_mid data, then the full run (ingest → profile → size → report)
demo:
    uv run whsizing synth data/synth/profiles/ecom_mid.yaml
    WHSIZING_SALT="${WHSIZING_SALT:-demo-salt}" uv run whsizing run-all project/example_project.yaml

docker-build:
    docker build -t whsizing:dev .

docker-demo: docker-build
    mkdir -p runs
    docker run --rm --entrypoint sh -e WHSIZING_SALT="${WHSIZING_SALT:-demo-salt}" -v "$(pwd)/runs:/app/runs" whsizing:dev -c 'whsizing synth data/synth/profiles/ecom_mid.yaml && whsizing run-all project/example_project.yaml'

# C5 performance budgets
bench:
    uv run pytest -m bench -q

# print the documentation index
docs:
    @ls docs docs/adr

# Streamlit wrapper (F10b); run from the repository root so .streamlit/config.toml applies.
# export WHSIZING_SALT=<secret> first, or type the salt on page 1.
app:
    uv run streamlit run src/whsizing/app/Home.py --server.address 127.0.0.1

# The public demo (streamlit_app.py: synthetic data only, no upload) on this machine: the same app
# Streamlit Community Cloud serves (docs/DEPLOY_STREAMLIT.md).
demo-app:
    uv run streamlit run streamlit_app.py --server.address 127.0.0.1
