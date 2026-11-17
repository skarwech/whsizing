"""Shared F9a test support (no test here): one small synthetic site run through the real
pipeline (F1 data, F2-F8, sensitivity on) and cached for the session, plus a few helpers to
edit the report model (tamper tests)."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from whsizing.report import ReportData, load_report_data
from whsizing.scenarios import run_scenarios
from whsizing.scenarios.compare import compare
from whsizing.schemas import Cell, Project, ProjectOptions, ReportTable, TableBlock, TableRow
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 18, 14, 2, 11, tzinfo=UTC)
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
SMALL = {"n_skus": 300, "n_days": 120, "orders_per_day_mean": 40}  # ≥ 3 months (R9)
_RUNS: dict[str, RunOutput] = {}


def small_run(factory: pytest.TempPathFactory) -> RunOutput:
    """The example project and scenarios (S0 manual, S1 AMR, S2 cube) on a small ecom site, with
    the sensitivity analysis; baseline = the client's current operation. Built once."""
    if "small" not in _RUNS:
        base = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
        work = factory.mktemp("f9_small")
        export(generate(base.model_copy(update=SMALL), seed=7), work, ("csv_en",))
        project = Project(
            name="f9_small",
            out_dir=work / "runs",
            catalog=ROOT / "catalog",
            inputs={ds: InputSpec(files=[work / "csv_en" / f"{ds}.csv"]) for ds in DATASETS},
            basis=ROOT / "basis" / "example_basis.yaml",
            scenarios=ROOT / "scenarios" / "example_scenarios.yaml",
            options=ProjectOptions(sensitivity=True),
        )
        old = os.environ.get("WHSIZING_SALT")
        os.environ["WHSIZING_SALT"] = "f9-test-salt"
        try:
            _RUNS["small"] = run_scenarios(project, now=NOW)
        finally:
            if old is None:
                del os.environ["WHSIZING_SALT"]
            else:
                os.environ["WHSIZING_SALT"] = old
    return _RUNS["small"]


def private_run(factory: pytest.TempPathFactory, name: str) -> RunOutput:
    """The cached small run, copied (without any `report/`) to a folder of its own. A module that
    builds a report writes `report/` into the run folder: it must do that in its own copy, so that
    no module leaves files for another one and the suite does not depend on the order."""
    run = small_run(factory)
    dst = factory.mktemp(name) / "run"
    shutil.copytree(run.run_dir, dst, ignore=shutil.ignore_patterns("report"))
    return run.model_copy(update={"run_dir": dst})


def baseline_scenario_run(run: RunOutput, payback_none: tuple[str, ...] = ()) -> RunOutput:
    """`run` as if S0 were the baseline scenario (I42): S0 has no Δ, NPV or payback of its own
    (the F7 contract for the baseline itself); the payback of `payback_none` is not reached."""
    own = {"npv_vs_baseline": None, "irr_vs_baseline": None, "payback_years": None}
    finances = {
        sid: f.model_copy(
            update={**own, "delta_cash_flows_typ": []}
            if sid == "S0"
            else ({"payback_years": None} if sid in payback_none else {})
        )
        for sid, f in run.finances.items()
    }
    return run.model_copy(
        update={"finances": finances, "comparison": compare(run.results, finances, "S0")}
    )


def report_data(run: RunOutput, lang: str = "en") -> ReportData:
    return load_report_data(run, lang)  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ editing the model
def find_row(table: ReportTable, row_key: str) -> tuple[TableBlock, TableRow]:
    for block in table.blocks:
        for row in block.rows:
            if row.key == row_key:
                return block, row
    raise KeyError(row_key)


def with_cell(
    data: ReportData, table_id: str, row_key: str, col_index: int, **change: object
) -> ReportData:
    """`data` with one cell changed (the model is frozen: rebuild the path to it)."""
    import dataclasses

    table = data.tables[table_id]
    block, row = find_row(table, row_key)
    cells = list(row.cells)
    cells[col_index] = cells[col_index].model_copy(update=change)
    new_row = row.model_copy(update={"cells": cells})
    new_block = block.model_copy(update={"rows": [new_row if r is row else r for r in block.rows]})
    new_table = table.model_copy(
        update={"blocks": [new_block if b is block else b for b in table.blocks]}
    )
    return dataclasses.replace(data, tables={**data.tables, table_id: new_table})


def column_index(table: ReportTable, block_key: str, col_key: str) -> int:
    block = next(b for b in table.blocks if b.key == block_key)
    return next(i for i, c in enumerate(block.columns) if c.key == col_key)


def number(cell: Cell) -> float:
    assert isinstance(cell.value, int | float)
    return float(cell.value)
