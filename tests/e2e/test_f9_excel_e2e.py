"""F9b Excel report end to end on synthetic ecom_mid (F1 generator, 730 days, about 1 M order
lines): the example project, basis, scenarios and catalog through `run_scenarios` (S0 manual, S1
AMR, S2 cube; against the client's current operation, and once with S0 as the baseline), then
`build_excel` in FR and EN. T9.7 (Excel part): built in well under the 60 s budget of both files;
T9.1 the twelve sheets and their headers; T9.2 Summary equals comparison.json; T9.5 FR and EN hold
the same numbers; the trace comments resolve in the exported trace.jsonl."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_f9_excel_support import (
    HEADERS,
    LANGS,
    SHEETS,
    assert_summary_equals_comparison_json,
    comments,
    numbers_by_sheet,
    open_book,
)

from whsizing.config import load_project
from whsizing.report import iter_cells, load_report_data
from whsizing.report.excel import build_excel
from whsizing.report.i18n import Lang
from whsizing.scenarios import run_scenarios
from whsizing.schemas import Project
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.schemas.trace import Tracer
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
BUDGET_S = 30.0  # the Excel half of T9.7 (both files: 60 s)


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    """example_project.yaml has no salt_file: the salt comes from $WHSIZING_SALT."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f9b-e2e-salt")
        yield


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    out = tmp_path_factory.mktemp("f9b_e2e")
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


@pytest.fixture(scope="module")
def built(client_run: RunOutput) -> dict[Lang, tuple[Path, float]]:
    out: dict[Lang, tuple[Path, float]] = {}
    for lang in LANGS:
        t0 = time.perf_counter()
        path = build_excel(client_run, lang)
        out[lang] = (path, time.perf_counter() - t0)
    return out


@pytest.mark.slow
@pytest.mark.parametrize("lang", LANGS)
def test_T9_7_the_excel_report_builds_within_budget(
    built: dict[Lang, tuple[Path, float]], lang: Lang
) -> None:
    path, seconds = built[lang]
    print(f"\nF9b Excel [{lang}] on ecom_mid: {seconds:.2f} s, {path.stat().st_size / 1e3:.0f} kB")
    assert seconds < BUDGET_S
    assert path.stat().st_size > 50_000


@pytest.mark.slow
@pytest.mark.parametrize("lang", LANGS)
def test_T9_1_ecom_mid_workbook_has_the_twelve_sheets_and_their_headers(
    built: dict[Lang, tuple[Path, float]], lang: Lang
) -> None:
    wb = open_book(built[lang][0])
    assert wb.sheetnames == SHEETS[lang]
    for ws, (block_title, header_row, header) in zip(wb.worksheets, HEADERS[lang], strict=True):
        assert ws["A3"].value == block_title, ws.title
        assert [ws.cell(header_row, c).value or "" for c in range(1, len(header) + 1)] == header
        assert ws.freeze_panes == f"B{header_row + 1}"


@pytest.mark.slow
@pytest.mark.parametrize("lang", LANGS)
def test_T9_2_ecom_mid_summary_equals_comparison_json(
    client_run: RunOutput, built: dict[Lang, tuple[Path, float]], lang: Lang
) -> None:
    assert assert_summary_equals_comparison_json(open_book(built[lang][0]), client_run, lang) > 40


@pytest.mark.slow
def test_T9_5_ecom_mid_fr_and_en_workbooks_hold_identical_numbers(
    client_run: RunOutput, built: dict[Lang, tuple[Path, float]]
) -> None:
    fr, en = (open_book(built[lang][0]) for lang in ("fr", "en"))
    numbers = numbers_by_sheet(en)
    assert numbers == numbers_by_sheet(fr)
    assert sum(len(v) for v in numbers.values()) > 2000
    data = load_report_data(client_run, "en")
    traced = sum(1 for _, c in iter_cells(data.tables) if c.trace_id and c.value is not None)
    for wb in (fr, en):
        assert sum(len(comments(ws)) for ws in wb.worksheets) == traced > 1000


@pytest.mark.slow
def test_ecom_mid_every_summary_number_has_a_comment_that_resolves_in_the_exported_trace(
    built: dict[Lang, tuple[Path, float]],
) -> None:
    path = built["en"][0]
    exported = Tracer.load_jsonl(path.parent / "trace.jsonl")
    nodes = {(n.id, n.world): n for n in exported.nodes}
    ws = open_book(path)["Summary"]
    tco = next(r for r in range(1, ws.max_row) if ws.cell(r, 1).value == "TCO (€)")
    cell, note = ws.cell(tco, 9), comments(ws)[(tco, 9)]  # S2, typical
    assert note.startswith("Trace S2.finance.tco (typ world)")
    node = nodes[("S2.finance.tco", "typ")]
    assert node.formula in note and cell.value == pytest.approx(node.value, rel=1e-12)
    assert node.inputs and all(ref in note for ref in node.inputs.values())


@pytest.mark.slow
def test_ecom_mid_with_a_scenario_as_the_baseline_builds_and_keeps_the_gate_open(
    s0_run: RunOutput,
) -> None:
    wb: Any = open_book(build_excel(s0_run, "en"))
    cash = wb["Cash flow"]
    labels = [c.value for c in cash[5]][1:]
    assert labels[0] == "Cash flow" and labels.count("Δ vs baseline") == 2  # S0 has none
    summary = wb["Summary"]
    npv = next(
        r for r in range(1, summary.max_row) if summary.cell(r, 1).value == "NPV vs baseline (€)"
    )
    assert summary.cell(npv, 3).value is None and summary.cell(npv, 6).value is not None
