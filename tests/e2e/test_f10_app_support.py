"""Shared by the F10b / R8c AppTest files (no test here): a small synthetic site, the page runner
and the ingest helper. The fixtures are defined by each file (a fixture imported into a test file
is flagged by the linter), on these functions."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from whsizing.app import ingest_ui
from whsizing.report import Lang
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "whsizing" / "app"
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")  # sku_master first (F2 checks)
SALT = "f10b-app-salt"
TIMEOUT = 120
SMALL_PROFILE = """\
name: small_app
n_skus: 120
start_date: 2025-01-01
n_days: 243
orders_per_day_mean: 40
promos: []
"""


def render(page: str, run: Path | None = None, lang: Lang = "fr", **state: Any) -> AppTest:
    """The page run once, on `run` (the session key `run_dir`), in `lang`."""
    at = AppTest.from_file(str(APP / page), default_timeout=TIMEOUT)
    if run is not None:
        at.session_state["run_dir"] = str(run)
    at.session_state["lang"] = lang
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


def texts(at: AppTest, element: str) -> list[str]:
    return [str(e.value) for e in getattr(at, element)]


def salted() -> Iterator[None]:
    """The body of each module's session fixture `salt_env` (the ingest needs WHSIZING_SALT)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", SALT)
        yield


def synthetic_csv_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The CSV folder of a small synthetic site; the body of each module's fixture `csv_dir`."""
    root = tmp_path_factory.mktemp("f10b_data")
    (root / "small.yaml").write_text(SMALL_PROFILE, encoding="utf-8")
    synthesize(root / "small.yaml", root / "out", seed=42)
    return root / "out" / "csv_en"


def upload_page(dataset: str, path: Path) -> AppTest:
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    up.selectbox(key="up.dataset").select(dataset).run()
    return up.text_input(key=f"up.{dataset}.path").input(str(path)).run()


def ingest_run(
    csv_dir: Path, root: Path, datasets: tuple[str, ...] = DATASETS, run: Path | None = None
) -> Path:
    """The datasets ingested into one run (`run`, else a new folder), as page 1 does (library
    plus CLI command). The app writes under WHSIZING_RUNS: it must be `root`, or the test would
    leave run folders in the working directory."""
    from whsizing.io.mapping import resolve_mapping, suggest_mapping
    from whsizing.io.readers import read_any

    assert ingest_ui.runs_root().resolve() == root.resolve(), "set WHSIZING_RUNS to root first"
    for ds in datasets:
        raw = read_any(csv_dir / f"{ds}.csv")
        mapping = resolve_mapping(suggest_mapping(raw, ds), raw)  # type: ignore[arg-type]
        outcome = ingest_ui.run_ingest(ds, [csv_dir / f"{ds}.csv"], mapping, run)  # type: ignore[arg-type]
        assert outcome.error is None, outcome.error
        run = outcome.run
    assert run is not None
    return run


def raw_copies(root: Path) -> list[Path]:
    """Files the app left under `<root>/.uploads` (raw client uploads, mapping files)."""
    return [p for p in (root / ".uploads").rglob("*") if p.is_file()]
