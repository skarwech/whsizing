"""F9c end to end on synthetic ecom_mid (F1 generator, 730 days, about 1 M order lines): the
example project, basis, scenarios and catalog through `run_scenarios` (S0 manual, S1 AMR, S2 cube,
sensitivity on), then `build_pdf` in FR and EN. T9.3 (12-18 pages, the run id), T9.7 (the Excel and
the PDF of both languages together in under 60 s; the times, pages and size are printed), the
done-when (three Summary numbers recomputed from Appendix C) and the files the build leaves in
`report/`."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.unit.test_f9_pdf_support import (
    pdf_pages,
    plain,
    printed_value_and_inputs,
    trace_entry,
)

from whsizing.config import load_project
from whsizing.report import build_excel, load_report_data, render_cell
from whsizing.report.i18n import Lang
from whsizing.report.pdf import build_pdf
from whsizing.scenarios import run_scenarios
from whsizing.schemas import Project
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import synthesize

pytestmark = [pytest.mark.pdf, pytest.mark.slow]
ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
BUDGET_S = 60.0  # T9.7: both files (Excel and PDF), both languages, in under 60 s together
LANGS: tuple[Lang, ...] = ("fr", "en")


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    """example_project.yaml has no salt_file: the salt comes from $WHSIZING_SALT."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f9c-e2e-salt")
        yield


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    out = tmp_path_factory.mktemp("f9c_e2e")
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
def run(project: Project) -> RunOutput:
    return run_scenarios(project)


@pytest.fixture(scope="module")
def built(run: RunOutput) -> dict[Lang, tuple[Path, float]]:
    """{lang: (pdf, seconds)}: the PDF of each language, timed from `build_pdf` alone (the run
    is already sized)."""
    out: dict[Lang, tuple[Path, float]] = {}
    for lang in LANGS:
        t0 = time.perf_counter()
        pdf = build_pdf(run, lang)
        out[lang] = (pdf, time.perf_counter() - t0)
    return out


def test_T9_3_pdf_of_a_real_run_has_12_to_18_pages_and_the_run_id(
    run: RunOutput, built: dict[Lang, tuple[Path, float]]
) -> None:
    for lang, (pdf, _) in built.items():
        pages = pdf_pages(pdf)
        assert 12 <= len(pages) <= 18, (lang, len(pages))
        assert all(run.manifest.run_id in p for p in pages)
        assert pdf == run.run_dir / "report" / f"report_{lang}.pdf"


@pytest.mark.bench  # C5 report row (both formats): measured by `just bench`
def test_T9_7_the_excel_and_the_pdf_are_built_in_under_60_seconds_together(
    run: RunOutput, built: dict[Lang, tuple[Path, float]]
) -> None:
    xlsx: dict[Lang, float] = {}
    for lang in LANGS:  # the run is already sized: the time is that of the builders
        t0 = time.perf_counter()
        build_excel(run, lang)
        xlsx[lang] = time.perf_counter() - t0
    for lang, (pdf, seconds) in built.items():
        print(
            f"\nF9 [{lang}]: PDF {seconds:.1f} s ({len(pdf_pages(pdf))} pages, "
            f"{pdf.stat().st_size / 1024:.0f} KiB), Excel {xlsx[lang]:.1f} s"
        )
    assert sum(s for _, s in built.values()) + sum(xlsx.values()) < BUDGET_S


def test_F9c_three_summary_numbers_of_every_scenario_are_reproduced_from_appendix_c(
    run: RunOutput, built: dict[Lang, tuple[Path, float]]
) -> None:
    """Done-when of F9: total area = sum of the zones, design-day heads = sum of the activities,
    TCO = capex + discounted opex, each from the formula and inputs printed in Appendix C."""
    for lang, (pdf, _) in built.items():
        data = load_report_data(run, lang)
        pages = pdf_pages(pdf)
        appendix = "\n".join(pages)
        block = data.tables["summary"].blocks[1]
        rows = {r.key: r for r in block.rows}
        for sid in data.computed():
            col = next(
                i for i, c in enumerate(block.columns) if c.scenario_id == sid and c.world == "typ"
            )
            for row_key, tol in (("total_area", 0.06), ("fte_design_day", 0.1), ("tco", 0.1)):
                cell = rows[row_key].cells[col]
                assert plain(render_cell(cell, lang)) in pages[1]
                assert cell.trace_id is not None
                value, inputs = printed_value_and_inputs(trace_entry(appendix, cell.trace_id), lang)
                if row_key == "tco":
                    capex, *opex, rate = inputs
                    recomputed = capex + sum(o / (1 + rate) ** t for t, o in enumerate(opex, 1))
                else:
                    recomputed = sum(inputs)
                assert recomputed == pytest.approx(value, abs=tol), (lang, sid, row_key)


def test_F9c_the_report_folder_holds_the_pdfs_the_trace_and_the_diagrams(
    run: RunOutput, built: dict[Lang, tuple[Path, float]]
) -> None:
    report = run.run_dir / "report"
    names = {p.name for p in report.iterdir()}
    assert {"report_fr.pdf", "report_en.pdf", "trace.jsonl"} <= names
    assert {f"diagram_{s}.svg" for s in run.results} <= names
    ids = {json.loads(line)["id"] for line in (report / "trace.jsonl").read_text().splitlines()}
    data = load_report_data(run, "en")
    summary = data.tables["summary"].blocks[1]
    cited = {c.trace_id for r in summary.rows for c in r.cells if c.trace_id}
    assert cited and cited <= ids  # every number of the Summary resolves in the exported trace
