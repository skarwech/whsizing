"""Shared F8b test support (no test here): the `RunContext` of tiny_golden, built the way the
runner builds it (F3 tables, profile, I58 SKU frame, F4 design day) without a run folder, and
helpers to compare a variant with `evaluate_scenario`."""

from __future__ import annotations

from functools import cache
from pathlib import Path

import polars as pl

from whsizing.catalog import load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import sku_frame
from whsizing.profile import build_tables, profile_from_tables
from whsizing.scenarios import RunContext
from whsizing.schemas import Baseline, ProfileCfg, Project, ScenarioSet

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
CLIENT_FTE = {"picking": 6.0, "packing": 3.0, "receiving": 1.0, "shipping": 1.0}  # test data


@cache
def golden_ctx(baseline: str = "S0") -> RunContext:
    """tiny_golden with golden_basis.yaml and golden_scenarios.yaml (S0 manual, S2 cube). Baseline
    "S0" = the golden case (S2 never pays back at k = 1); "client_current" = a made-up current
    operation of `CLIENT_FTE` (more people than S0 needs) so that S2 has a payback to solve for."""
    basis = load_basis(GOLDEN / "golden_basis.yaml")
    scenarios = load_yaml_model(GOLDEN / "golden_scenarios.yaml", ScenarioSet)
    if baseline != "S0":
        scenarios = scenarios.model_copy(update={"baseline": baseline})
        basis = basis.model_copy(update={"baseline": Baseline(actual_fte=CLIENT_FTE)})
    cfg = ProfileCfg()
    tables = build_tables(GOLDEN / "tiny_golden", basis, cfg)
    profile = profile_from_tables(tables, cfg)
    sku = sku_frame(tables, pl.read_parquet(GOLDEN / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    design_day = select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
    project = Project(
        name="f8b_golden",
        out_dir=ROOT / "runs",  # never written: nothing here creates a run folder
        inputs={},
        basis=GOLDEN / "golden_basis.yaml",
        scenarios=GOLDEN / "golden_scenarios.yaml",
    )
    return RunContext(
        project, basis, scenarios, catalog, tables, profile, sku, design_day, ROOT / "runs" / "none"
    )
