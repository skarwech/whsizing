"""The data one calibration reads: the baseline scenario's engine inputs (no actuals)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl

from whsizing.catalog import Catalog
from whsizing.design import select_design_day
from whsizing.engine import sku_frame
from whsizing.io.readers import read_parquet_file
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import DesignBasis, DesignDay, ProfileCfg, ScenarioDef

# ponytail: the baseline is the manual family unless the caller names a scenario
DEFAULT_BASELINE = ScenarioDef(id="BASE", name="Baseline", family="manual_p2p", is_baseline=True)


@dataclass(frozen=True)
class CalibrationInputs:
    """What `size_scenario` reads for labor: `daily` and `lines` are the F3 `ProfileTables.daily`
    and `.lines`, `sku` the I58 `sku_frame`, `design_day` the F4 design day (I61)."""

    basis: DesignBasis
    design_day: DesignDay
    scenario: ScenarioDef
    catalog: Catalog
    sku: pl.DataFrame
    daily: pl.DataFrame
    lines: pl.DataFrame


def inputs_from_run(
    run_dir: Path | str,
    basis: DesignBasis,
    catalog: Catalog,
    scenario: ScenarioDef = DEFAULT_BASELINE,
    cfg: ProfileCfg | None = None,
) -> CalibrationInputs:
    """Rebuild the F3 tables and the F4 design day from `<run>/canonical/` (F6 e2e chain)."""
    run = Path(run_dir)
    cfg = cfg or ProfileCfg()
    tables = build_tables(run / "canonical", basis, cfg)
    master = run / "canonical" / "sku_master.parquet"
    sku = sku_frame(tables, read_parquet_file(master) if master.is_file() else None)
    profile = profile_from_tables(tables, cfg)
    dd = select_design_day(profile, basis, tables.daily, sku=sku, catalog=catalog)
    return CalibrationInputs(basis, dd, scenario, catalog, sku, tables.daily, tables.lines)
