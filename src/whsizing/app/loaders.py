"""Cached library calls of the pages (`st.cache_data`, keyed on input hashes) (F10b).

Arguments are strings: the run folder plus a digest of what the result is built from (the run's
files, the basis text, the catalog files), so a changed input is a new key and a run folder
never serves another run's result. Nothing here computes anything the library does not.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from whsizing.catalog import Catalog, load_catalog
from whsizing.cli._runio import load_run, read_model
from whsizing.cli._staged import profile_cfg_of
from whsizing.design import load_basis, select_design_day
from whsizing.design.validate import check_basis
from whsizing.engine import sku_frame
from whsizing.io.ingest import read_parquet_file
from whsizing.profile import build_tables, profile_from_tables
from whsizing.profile.aggregate import CANONICAL, load_canonical
from whsizing.profile.build import dataset_hash
from whsizing.profile.charts import CHARTS
from whsizing.report import Lang, ReportData, load_report_data
from whsizing.schemas import DemandProfile, DesignBasis, DesignDay
from whsizing.schemas.run import RunOutput

PROFILE_FIGURES = (
    "daily_lines",
    "monthly_index",
    "weekday_index",
    "intraday_heatmap",
    "pareto",
    "lines_per_order_hist",
)


def digest_of(*paths: Path) -> str:
    """sha256 (16 hex) of the bytes of the files and, for a folder, of its yaml files."""
    h = hashlib.sha256()
    for path in paths:
        files = sorted(path.rglob("*.yaml")) if path.is_dir() else [path]
        for f in files:
            h.update(f.name.encode())
            h.update(f.read_bytes() if f.is_file() else b"-")
    return h.hexdigest()[:16]


def canonical_digest(run: Path) -> str:
    """Names, sizes and times of the canonical tables ingest wrote: new data in the run is a new
    key. `daily_series.parquet`, which `profile` writes in the same folder, is not one of them: it
    changes at every profile and would make every profile a change of the data."""
    h = hashlib.sha256()
    for name in CANONICAL:
        f = run / "canonical" / f"{name}.parquet"
        if f.is_file():
            s = f.stat()
            h.update(f"{f.name}{s.st_size}{s.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


@st.cache_data(show_spinner=False)
def tables_hash(run: str, digest: str) -> str:
    """`dataset_hash` of the run's canonical tables, the value `DemandProfile.dataset_hash` holds
    when the profile was made from them (`digest`: `canonical_digest`, so that it is computed once
    per content: reading and hashing the tables costs seconds on a big run)."""
    del digest
    return dataset_hash(load_canonical(Path(run) / "canonical"))


@st.cache_data(show_spinner=False)
def catalog_of(path: str, digest: str) -> Catalog:
    """The catalog folder, loaded once per content (`digest_of(folder)`)."""
    del digest
    return load_catalog(path)


@st.cache_data(show_spinner=False)
def output(run: str, digest: str) -> RunOutput:
    """The sized and compared run (`digest`: `state.run_digest`)."""
    del digest
    return load_run(Path(run))


@st.cache_data(show_spinner=False)
def report_data(run: str, lang: Lang, digest: str) -> ReportData:
    """Everything the report reads, with its tables and the traces (F9a)."""
    return load_report_data(output(run, digest), lang)


@st.cache_data(show_spinner=False)
def profile_view(
    run: str, dataset_hash: str, basis_file: str, basis_digest: str
) -> tuple[DemandProfile, dict[str, go.Figure]]:
    """The demand profile of the run and its Plotly charts (F3). `basis_file` "" = no basis yet."""
    del dataset_hash, basis_digest
    run_dir = Path(run)
    cfg = profile_cfg_of(run_dir)
    basis = load_basis(basis_file) if basis_file else None
    tables = build_tables(run_dir / "canonical", basis, cfg)
    profile = read_model(run_dir / "profile" / "demand_profile.json", DemandProfile, "run profile")
    return profile, {name: CHARTS[name](profile, tables)[1] for name in PROFILE_FIGURES}


@st.cache_data(show_spinner=False)
def design_preview(
    run: str, canonical_key: str, basis_json: str, catalog_path: str, catalog_key: str
) -> DesignDay:
    """F4 design day of the basis as it is now, on the run's canonical tables (nothing written)."""
    del canonical_key, catalog_key
    run_dir = Path(run)
    basis = check_basis(DesignBasis.model_validate(json.loads(basis_json)))
    cfg = profile_cfg_of(run_dir)
    tables = build_tables(run_dir / "canonical", basis, cfg)
    profile = profile_from_tables(tables, cfg)
    master = run_dir / "canonical" / "sku_master.parquet"
    sku = sku_frame(tables, read_parquet_file(master) if master.is_file() else None)
    catalog = load_catalog(catalog_path)
    return select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
