"""F9a end to end on synthetic ecom_mid (F1 generator, 730 days, about 1 M order lines): the
example project, basis, scenarios and catalog through `run_scenarios` (S0 manual, S1 AMR, S2
cube; once against the client's current operation, once with S0 as the baseline scenario),
then the F9a report core in FR and EN: tables, integrity checks IC1-IC8, charts, block
diagrams. Prints the build time of tables + charts + diagrams."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from whsizing.config import load_project
from whsizing.report import (
    CHART_IDS,
    TABLE_IDS,
    build_charts,
    build_diagrams,
    check_integrity,
    load_report_data,
    render_cell,
)
from whsizing.report.i18n import Lang
from whsizing.scenarios import run_scenarios
from whsizing.schemas import Project
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
BUDGET_S = 20.0  # tables + charts + diagrams, one language (T9.7: both files < 60 s in total)


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    """example_project.yaml has no salt_file: the salt comes from $WHSIZING_SALT."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f9-e2e-salt")
        yield


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    out = tmp_path_factory.mktemp("f9_e2e")
    synthesize(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml", out / "ecom_mid", seed=42)
    data = out / "ecom_mid" / "csv_en"
    example = load_project(ROOT / "project" / "example_project.yaml")
    return example.model_copy(
        update={
            "out_dir": out / "runs",
            "inputs": {ds: InputSpec(files=[data / f"{ds}.csv"]) for ds in DATASETS},
        }
    )


@pytest.fixture(scope="module")
def client_run(project: Project) -> RunOutput:
    return run_scenarios(project)


@pytest.fixture(scope="module")
def s0_run(project: Project, client_run: RunOutput) -> RunOutput:
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    path = project.out_dir / "scenarios_s0.yaml"
    path.write_text(text.replace("baseline: client_current", "baseline: S0"), encoding="utf-8")
    return run_scenarios(
        project.model_copy(update={"scenarios": path}), reuse_canonical=client_run.run_dir
    )


@pytest.mark.slow
@pytest.mark.parametrize("lang", ["fr", "en"])
def test_F9a_core_builds_tables_charts_and_diagrams_within_budget(
    client_run: RunOutput, lang: Lang
) -> None:
    out = client_run.run_dir / "report"
    t0 = time.perf_counter()
    data = load_report_data(client_run, lang)
    t_tables = time.perf_counter() - t0
    charts = build_charts(data, out / "charts")
    t_charts = time.perf_counter() - t0 - t_tables
    diagrams = build_diagrams(data, out)
    total = time.perf_counter() - t0
    print(
        f"\nF9a core [{lang}]: tables {t_tables:.2f} s, charts {t_charts:.2f} s, "
        f"diagrams {total - t_tables - t_charts:.2f} s, total {total:.2f} s"
    )
    assert total < BUDGET_S
    assert tuple(data.tables) == TABLE_IDS
    assert set(charts) == set(CHART_IDS) and all(p.stat().st_size > 5_000 for p in charts.values())
    assert sorted(diagrams) == ["S0", "S1", "S2"]
    assert all(p == out / f"diagram_{s}.svg" for s, p in diagrams.items())
    assert check_integrity(client_run, data=data) == []


@pytest.mark.slow
def test_F9a_core_integrity_holds_with_a_scenario_as_the_baseline(s0_run: RunOutput) -> None:
    data = load_report_data(s0_run, "en")
    assert check_integrity(s0_run, data=data) == []
    flows = data.tables["cash_flow"].blocks[0]
    kinds = {(c.scenario_id, c.kind) for c in flows.columns}
    assert ("S0", "delta") not in kinds and ("S2", "delta") in kinds  # S0 has no Δ against itself
    assert ("S0", "cumulative") not in kinds  # not its own cost beside the others' cumulative Δ
    assert {("S1", "cumulative"), ("S2", "cumulative")} <= kinds
    assert data.tables["cash_flow"].notes[0].args == {"baseline": "S0"}
    payback = {r.key: r for r in data.tables["summary"].blocks[1].rows}["payback"]
    assert payback.cells[1].value is None  # the baseline scenario: no payback of its own
    assert all(
        c.value is not None for c in payback.cells[4::3]
    )  # S1 and S2: a number or "not reached"
    assert data.tables["capex_opex"].notes  # the finance notes (baseline scope, I73 b) are shown
    summary = {r.key: r for r in data.tables["summary"].blocks[1].rows}
    assert summary["npv"].cells[1].value is None  # the baseline scenario has no NPV of its own
    assert summary["npv"].cells[4].value == s0_run.finances["S1"].npv_vs_baseline.typ  # pyright: ignore[reportOptionalMemberAccess]
    assert check_integrity(s0_run, html="<p>12</p>", data=data) == []


@pytest.mark.slow
def test_F9a_core_every_summary_number_resolves_to_a_trace_tree_down_to_params(
    client_run: RunOutput,
) -> None:
    """A reader can follow a summary number to the parameters and data it comes from."""
    data = load_report_data(client_run, "en")
    row = next(r for r in data.tables["summary"].blocks[1].rows if r.key == "tco")
    cell = row.cells[7]  # S2, typical
    assert cell.trace_id == "S2.finance.tco" and cell.world == "typ"
    tree = data.tracers["S2"].tree(cell.trace_id)
    kinds: list[str] = []
    unresolved: list[str] = []

    def walk(node: dict[str, Any]) -> None:
        kinds.append(node["kind"])
        if node["kind"] == "unresolved":
            unresolved.append(node["id"])
        for child in node.get("inputs", {}).values():
            walk(child)

    walk(tree)
    assert "param" in kinds and "cycle" not in kinds
    assert all(u.startswith("data:") for u in unresolved)  # Tracer.tree shows data: as unresolved
    assert tree["value"] == cell.value
    assert render_cell(cell, "en").replace(",", "") == str(round(float(str(cell.value))))


@pytest.mark.slow
def test_F9a_core_fr_and_en_models_are_identical(client_run: RunOutput) -> None:
    fr, en = load_report_data(client_run, "fr"), load_report_data(client_run, "en")
    assert fr.tables == en.tables
