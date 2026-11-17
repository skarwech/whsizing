"""F10b Streamlit wrapper, end to end with `streamlit.testing.v1.AppTest` (T10.4).

A small real run (F1 synthetic site, 243 days, 120 SKUs; the library's `run_scenarios`) is built
once per session. Every page imports and renders on it, page 6 shows the comparison, charts,
block diagrams and the drill-down down to params, the banner is on pages 3 to 6, the state comes
back from the run folder, and a staged flow (upload, ingest, profile, basis, scenarios, size)
reaches the results without the terminal. `whsizing.report` Excel / PDF builders (F9b, F9c) are
faked here: the app is tested for what it asks of them."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import streamlit as st
import yaml
from streamlit.testing.v1 import AppTest
from tests.e2e.test_f10_app_support import (
    APP,
    DATASETS,
    ROOT,
    TIMEOUT,
    ingest_run,
    raw_copies,
    render,
    salted,
    synthetic_csv_dir,
    texts,
    upload_page,
)

import whsizing.report as report_api
from whsizing.app import drilldown, ingest_ui, results_ui
from whsizing.app.strings import tr
from whsizing.cli._runio import COMPARISON_FILE, load_run
from whsizing.config import load_project
from whsizing.report import Lang, fmt_number, load_report_data, t
from whsizing.scenarios import run_scenarios
from whsizing.schemas import Comparison, IntegrityIssue

PAGES = (
    "Home.py",
    "pages/1_Upload.py",
    "pages/2_Data_quality.py",
    "pages/3_Demand_profile.py",
    "pages/4_Design_basis.py",
    "pages/5_Scenarios.py",
    "pages/6_Results.py",
)
RESULT_PAGES = PAGES[3:]  # pages 3 to 6 carry the "indicative study" banner


# --------------------------------------------------------------------------------------- helpers
def frame_cells(at: AppTest) -> list[str]:
    """Every cell of every dataframe of the page, as text."""
    cells: list[str] = []
    for df in at.dataframe:
        cells += [str(v) for v in df.value.to_numpy().ravel()]
    return cells


@pytest.fixture(scope="session", autouse=True)
def salt_env() -> Iterator[None]:
    yield from salted()


@pytest.fixture(scope="session")
def csv_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_csv_dir(tmp_path_factory)


@pytest.fixture(scope="session")
def stored_run(csv_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A finished run folder, made by the library as `whsizing run-all` would."""
    folder = tmp_path_factory.mktemp("f10b_stored")
    project = {
        "name": "small_app",
        "language": ["fr", "en"],
        "out_dir": str(folder / "runs"),
        "catalog": str(ROOT / "catalog"),
        "inputs": {ds: {"files": [str(csv_dir / f"{ds}.csv")]} for ds in DATASETS},
        "basis": str(ROOT / "basis" / "example_basis.yaml"),
        "scenarios": str(ROOT / "scenarios" / "example_scenarios.yaml"),
        "options": {"worlds": "all", "sensitivity": True, "delta": 0.2, "strict": False},
    }
    (folder / "project.yaml").write_text(yaml.safe_dump(project), encoding="utf-8")
    return run_scenarios(load_project(folder / "project.yaml")).run_dir


@pytest.fixture
def runs_root(stored_run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A runs folder holding a copy of the stored run; the app looks there (WHSIZING_RUNS)."""
    root = tmp_path / "runs"
    root.mkdir()
    shutil.copytree(stored_run, root / stored_run.name)
    monkeypatch.setenv("WHSIZING_RUNS", str(root))
    return root


@pytest.fixture(scope="session")
def report_data(stored_run: Path) -> Any:
    return load_report_data(load_run(stored_run), "en")


# -------------------------------------------------------------------------- every page renders
@pytest.mark.parametrize("page", PAGES)
def test_T10_4_every_page_imports_and_renders_on_a_stored_run(page: str, stored_run: Path) -> None:
    at = render(page, stored_run)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, texts(at, "error")


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_T10_4_page_6_renders_the_stored_run_and_reports_its_time(
    lang: Lang, stored_run: Path
) -> None:
    st.cache_data.clear()  # cold: the library loads the run, builds the tables and traces
    started = time.perf_counter()
    at = render("pages/6_Results.py", stored_run, lang)
    cold = time.perf_counter() - started
    started = time.perf_counter()
    at.run()
    warm = time.perf_counter() - started
    print(f"\nF10b page 6 render ({lang}): cold {cold:.2f} s, cached {warm:.2f} s")
    assert not at.exception, [e.value for e in at.exception]
    assert cold < 30, f"page 6 took {cold:.1f} s"
    headers = [h.value for h in at.header]
    assert tr("results.comparison", lang) in headers and tr("results.why", lang) in headers
    scenarios = load_run(stored_run).results
    assert len(at.image) >= 3 + len(scenarios)  # fte, tco, cash charts and one diagram each
    assert all("{{ missing" not in cell for cell in frame_cells(at))  # i18n: no missing key


def test_T10_4_page_6_numbers_are_those_of_comparison_json(
    stored_run: Path,
) -> None:
    at = render("pages/6_Results.py", stored_run, "en")
    cmp = Comparison.model_validate_json((stored_run / COMPARISON_FILE).read_text("utf-8"))
    cells = set(frame_cells(at))
    for row in cmp.rows:
        assert row.total_area_m2 is not None and row.tco is not None
        assert fmt_number(row.total_area_m2.typ, "en", 0) in cells
        assert fmt_number(row.tco.typ, "en", 0) in cells
    columns = {c for df in at.dataframe for c in df.value.columns}
    assert all(any(row.scenario_id in c for c in columns) for row in cmp.rows)


def test_T10_4_page_6_exports_comparison_json_and_says_when_excel_pdf_are_absent(
    stored_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(report_api, "build_excel", raising=False)
    monkeypatch.delattr(report_api, "build_pdf", raising=False)
    at = render("pages/6_Results.py", stored_run, "en")
    assert [b.label for b in at.download_button] == [tr("results.dl_comparison", "en")]
    assert tr("results.unavailable", "en", kind="XLSX") in texts(at, "info")
    assert tr("results.unavailable", "en", kind="PDF") in texts(at, "info")


def test_T10_4_page_6_builds_excel_and_pdf_through_the_report_command(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = next(runs_root.iterdir())
    built: list[tuple[str, str]] = []

    def fake(kind: str) -> Any:
        def build(out: Any, lang: str) -> Path:
            built.append((kind, lang))
            path = out.run_dir / "report" / f"report_{lang}.{kind}"
            path.write_bytes(b"x")
            return path

        return build

    monkeypatch.setattr(report_api, "check_integrity", lambda out: [], raising=False)
    monkeypatch.setattr(report_api, "build_excel", fake("xlsx"), raising=False)
    monkeypatch.setattr(report_api, "build_pdf", fake("pdf"), raising=False)
    at = render("pages/6_Results.py", run, "en")
    assert not at.exception
    at.button(key="export.xlsx").click().run()
    assert built == [("xlsx", "en")]
    assert not at.error, texts(at, "error")
    assert "report_en.xlsx" in [b.label for b in at.download_button]  # offered for download
    assert (run / "report" / "report_en.xlsx").read_bytes() == b"x"


def test_T10_4_page_6_shows_a_failed_report_as_an_error_with_its_exit_code(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = next(runs_root.iterdir())
    issue = IntegrityIssue(id="IC1", severity="error", message="tampered", location="summary/S0")
    monkeypatch.setattr(report_api, "check_integrity", lambda out: [issue], raising=False)
    monkeypatch.setattr(report_api, "build_excel", lambda out, lang: Path("x"), raising=False)
    at = render("pages/6_Results.py", run, "en")
    at.button(key="export.xlsx").click().run()
    assert not at.exception
    errors = texts(at, "error")
    assert any("exit 5" in e and "IC1" in e for e in errors)
    assert not any("[warning" in e or "[info" in e for e in errors)  # no log lines in the message


# ---------------------------------------------------------------------------------- the banner
@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("page", RESULT_PAGES)
def test_T10_4_banner_is_on_pages_3_to_6_in_both_languages(
    page: str, lang: Lang, stored_run: Path
) -> None:
    at = render(page, stored_run, lang)
    assert not at.exception
    assert t("banner.indicative", lang) in texts(at, "warning")


def test_T10_4_language_switch_translates_the_page_and_not_the_numbers(stored_run: Path) -> None:
    fr, en = (render("pages/6_Results.py", stored_run, lang) for lang in ("fr", "en"))
    assert [h.value for h in fr.header] != [h.value for h in en.header]
    assert t("banner.indicative", "fr") in texts(fr, "warning")
    assert t("banner.indicative", "en") in texts(en, "warning")
    assert fr.session_state["lang"] == "fr" and en.session_state["lang"] == "en"
    cmp = load_run(stored_run).comparison
    typ_area = cmp.rows[0].total_area_m2
    assert typ_area is not None
    assert fmt_number(typ_area.typ, "fr", 0) in frame_cells(fr)
    assert fmt_number(typ_area.typ, "en", 0) in frame_cells(en)


# ---------------------------------------------------------------------------- no run, no stage
@pytest.mark.parametrize("page", PAGES[2:])
def test_T10_4_pages_without_a_run_show_a_friendly_message(
    page: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "no-runs-here"))
    at = render(page)
    assert not at.exception and not at.error
    assert tr("no_run", "fr") in texts(at, "info")


def test_T10_4_home_without_a_run_says_so_and_with_runs_lists_them(
    tmp_path: Path, runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_runs = render("Home.py")
    assert not with_runs.exception
    options = with_runs.selectbox(key="home.run").options
    assert options[0].startswith(next(runs_root.iterdir()).name)
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "empty"))
    empty = render("Home.py")
    assert not empty.exception
    assert any("empty" in i for i in texts(empty, "info"))


# -------------------------------------------------------------------- state restored from disk
def test_T10_4_state_is_restored_from_the_run_query_parameter(runs_root: Path) -> None:
    run = next(runs_root.iterdir())
    at = AppTest.from_file(str(APP / "pages/6_Results.py"), default_timeout=TIMEOUT)
    at.query_params["run"] = run.name  # a browser refresh: empty session, the URL says which run
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["run_dir"] == str(run.resolve())
    assert at.query_params["run"] == [run.name] or at.query_params["run"] == run.name
    assert set(at.session_state["mapping"]) == set(DATASETS)
    assert [s["id"] for s in at.session_state["scenarios"]["scenarios"]] == ["S0", "S1", "S2"]
    expected = yaml.safe_load((run / "inputs" / "basis.yaml").read_text(encoding="utf-8"))
    assert at.session_state["basis"] == expected
    assert t("banner.indicative", "fr") in texts(at, "warning")  # and the page itself rendered


def test_T10_4_state_is_restored_from_the_last_run_without_a_query(runs_root: Path) -> None:
    newest = next(runs_root.iterdir())
    older = runs_root / "2020-01-01T00-00-00_000000"
    shutil.copytree(newest, older)
    at = AppTest.from_file(str(APP / "pages/4_Design_basis.py"), default_timeout=TIMEOUT).run()
    assert at.session_state["run_dir"] == str(newest.resolve())  # newest by timestamp
    assert at.session_state["basis"]["building"]["area_m2"] > 0
    assert not at.exception


def test_T10_4_a_page_that_needs_a_sized_run_explains_the_stage_of_an_ingested_one(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    outcome = ingest_run(csv_dir, tmp_path)
    at = render("pages/6_Results.py", outcome, "en")
    assert not at.exception
    assert tr("stage_missing", "en", stage="compared", have="ingested") in texts(at, "info")


# ------------------------------------------------------------------------------- the drill-down
def summary_cells(report_data: Any) -> list[drilldown.CellRef]:
    return drilldown.cell_choices(report_data)


def test_T10_4_drilldown_of_a_summary_cell_reaches_params_and_datasets(report_data: Any) -> None:
    refs = summary_cells(report_data)
    assert len(refs) > 50  # every scenario, row and world of the Summary that carries a trace id
    picked = [r for r in refs if r.world == "typ"][:12] + [
        r for r in refs if r.trace_id.endswith(("finance.tco", "area.total", "labor.total.heads"))
    ]
    seen: set[str] = set()
    for ref in picked:
        tree = drilldown.node_tree(report_data, ref.scenario_id, ref.trace_id, ref.world)
        assert tree["kind"] == "node" and tree["id"] == ref.trace_id
        leaves = drilldown.leaves(tree)
        kinds = {leaf["kind"] for leaf in leaves}
        assert "unresolved" not in kinds and "cycle" not in kinds, (ref.trace_id, kinds)
        # down to params and data; the only other leaves are constants (`0: sunk`, no inputs)
        assert all(leaf["kind"] in ("param", "dataset") or leaf["inputs"] == {} for leaf in leaves)
        seen |= kinds
    assert {"param", "dataset"} <= seen


def test_T10_4_drilldown_cells_resolve_in_their_own_scenario_trace(report_data: Any) -> None:
    for ref in summary_cells(report_data):
        tracer = report_data.tracers[ref.scenario_id]
        assert tracer.get(ref.trace_id, ref.world).id == ref.trace_id  # IC1: the cell resolves


def test_T10_4_drilldown_trim_keeps_the_biggest_tree_small(report_data: Any) -> None:
    npv = next(r for r in summary_cells(report_data) if r.trace_id.endswith("finance.npv"))
    tree = drilldown.node_tree(report_data, npv.scenario_id, npv.trace_id, npv.world)
    assert drilldown.count_nodes(tree) > 1000  # why the page cannot render it whole
    shown = drilldown.trim(tree, drilldown.DEFAULT_DEPTH)
    assert 1 < drilldown.count_nodes(shown) <= drilldown.MAX_NODES
    cut = drilldown.frontier(shown)
    assert cut  # re-root on a cut node to see more of it
    deeper = drilldown.node_tree(report_data, npv.scenario_id, cut[0], npv.world)
    assert deeper["id"] == cut[0] and deeper["kind"] == "node"


def test_T10_4_page_6_drilldown_renders_the_tree_with_param_and_data_leaves(
    stored_run: Path, report_data: Any
) -> None:
    ref = next(r for r in summary_cells(report_data) if r.trace_id == "S1.area.total")
    at = render("pages/6_Results.py", stored_run, "en")
    before = len(at.expander)
    at.selectbox(key="drill.cell").select(ref.label).run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.expander) > before  # the tree is nested expanders, the root first
    markdown = "\n".join(texts(at, "markdown"))
    assert "**parameter**" in markdown and "**data**" in markdown  # leaves of both kinds
    assert "area.m2_per_pallet_staged" in markdown  # a catalog parameter, with its value
    assert "design_day.pallets_out" in markdown  # a dataset leaf, `data:` prefix removed
    expanders = [e.label for e in at.expander]
    assert any(
        label.startswith("S1.area.total") is False and "Total area" in label for label in expanders
    )


def clicked(report_data: Any, trace_id: str, world: str = "typ") -> tuple[drilldown.CellRef, Any]:
    """The Summary cell with this trace id and what `st.dataframe` reports when it is clicked in
    the table of page 6: ({selection: {cells: [(row position, column name)]}}, its CellRef)."""
    block = next(b for b in report_data.tables["summary"].blocks if b.key == results_ui.PICK_BLOCK)
    names = results_ui.frame_columns(block, "en", False)
    for r, row in enumerate(block.rows):
        for name, i in names.items():
            cell = row.cells[i] if i >= 0 else None
            if (
                cell
                and cell.trace_id == trace_id
                and (cell.world or block.columns[i].world) == world
            ):
                ref = drilldown.cell_ref(report_data, row, block.columns[i], cell)
                assert ref is not None
                return ref, {"selection": {"rows": [], "columns": [], "cells": [(r, name)]}}
    raise AssertionError(f"{trace_id} is not in the table of page 6")


PICK_KEY = f"{results_ui.PICK_KEY}.en.False"  # the table's widget key: language, all worlds off


def test_R7_7_page_6_a_clicked_summary_cell_starts_the_drilldown(
    stored_run: Path, report_data: Any
) -> None:
    ref, event = clicked(report_data, "S1.area.total")
    at = render("pages/6_Results.py", stored_run, "en", **{PICK_KEY: event})
    assert not at.exception, [e.value for e in at.exception]
    assert at.selectbox(key="drill.cell").value == ref.label  # the selectbox took the cell
    assert tr("drill.picked", "en", cell=ref.label) in [c.value for c in at.caption]
    labels = [e.label for e in at.expander]
    assert any("Total area" in label for label in labels)  # the tree of S1.area.total, unfolded
    assert any(c.value.startswith("`S1.area.total`") for c in at.caption)


def test_R7_7_the_clicked_cell_replaces_a_typed_trace_id_and_the_selectbox_stays_usable(
    stored_run: Path, report_data: Any
) -> None:
    ref, event = clicked(report_data, "S1.area.total")
    other = next(r for r in summary_cells(report_data) if r.trace_id == "S0.labor.total.heads")
    at = render(
        "pages/6_Results.py", stored_run, "en", **{PICK_KEY: event, "drill.typed": "S2.area.total"}
    )
    assert not at.exception and at.text_input(key="drill.typed").value == ""  # the click wins
    at.selectbox(key="drill.cell").select(other.label).run()  # the table still shows its click
    assert not at.exception
    assert at.selectbox(key="drill.cell").value == other.label  # not set back to the click
    assert any(c.value.startswith(f"`{other.trace_id}`") for c in at.caption)
    assert not any(c.value.startswith(f"`{ref.trace_id}`") for c in at.caption)
    at.text_input(key="drill.typed").input("S0.labor.total.heads").run()  # and so is the field
    assert not at.exception and any("S0.labor.total.heads" in c.value for c in at.caption)


def test_R7_7_page_6_without_a_click_keeps_the_first_cell_and_a_language_switch_keeps_working(
    stored_run: Path, report_data: Any
) -> None:
    ref, event = clicked(report_data, "S1.area.total")
    at = render("pages/6_Results.py", stored_run, "en", **{PICK_KEY: event})
    assert not at.exception and at.selectbox(key="drill.cell").value == ref.label
    at.session_state["lang"] = "fr"  # the labels of the selectbox are French now: no stale value
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.selectbox(key="drill.cell").value != ref.label
    assert at.selectbox(key="drill.cell").value in at.selectbox(key="drill.cell").options


def test_T10_4_page_6_drilldown_accepts_a_typed_trace_id(stored_run: Path) -> None:
    at = render("pages/6_Results.py", stored_run, "en")
    at.text_input(key="drill.typed").input("S0.labor.total.heads").run()
    assert not at.exception
    assert any("S0.labor.total.heads" in c.value for c in at.caption)
    at.text_input(key="drill.typed").input("S9.nothing").run()
    assert tr("drill.unknown", "en", id="S9.nothing") in texts(at, "error")


def test_T10_4_page_6_drilldown_depth_slider_changes_how_much_is_shown(stored_run: Path) -> None:
    at = render("pages/6_Results.py", stored_run, "en")
    shallow = len(at.expander)
    at.slider(key="drill.depth").set_value(drilldown.MAX_DEPTH).run()
    assert not at.exception
    assert len(at.expander) >= shallow


# ------------------------------------------------------------------------- the staged flow (UI)
@pytest.mark.parametrize(("cap", "explained"), [(0, True), (1, True), (200, False), (1024, False)])
def test_T10_4_the_upload_page_explains_a_small_upload_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cap: int, explained: bool
) -> None:
    """`.streamlit/config.toml` takes no upload (cap 0) for the hosted demo: the full app, started
    without `just app`, says so and how to lift it, instead of leaving the user with the
    uploader's bare refusal of a file."""
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    monkeypatch.setattr(ingest_ui, "upload_cap_mb", lambda: cap)
    up = render("pages/1_Upload.py", lang="en")
    assert not up.exception
    notice = tr("upload.cap", "en", mb=cap)
    assert (notice in texts(up, "caption")) is explained
    assert "--server.maxUploadSize 1024" in notice and "just app" in notice


@pytest.mark.slow
def test_T10_4_staged_flow_from_upload_to_results_without_the_terminal(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Page 1 upload (file uploader for sku_master, a local path for the rest), then pages 2 to 6
    on the run it made, sizing from page 5, and the run folder is the CLI's."""
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    assert tr("upload.nothing", "en") in texts(up, "info")
    for ds in DATASETS:
        up.selectbox(key="up.dataset").select(ds).run()
        if ds == "sku_master":  # a real upload; the others come from a local path
            blob = (csv_dir / "sku_master.csv").read_bytes()
            up.file_uploader(key="up.sku_master").upload("sku_master.csv", blob, "text/csv").run()
        else:
            up.text_input(key=f"up.{ds}.path").input(str(csv_dir / f"{ds}.csv")).run()
        assert not up.exception and not up.error, texts(up, "error")
        up.button[-1].click().run()
        assert not up.error, texts(up, "error")
        assert any("quality score" in s for s in texts(up, "success")), ds
    run = Path(up.session_state["run_dir"])
    assert (run / "inputs" / "mapping" / "order_lines.yaml").is_file()  # same folders as the CLI
    assert set(up.session_state["mapping"]) == set(DATASETS)
    assert raw_copies(tmp_path) == []  # the upload and the mapping files are gone after ingest
    assert (csv_dir / "order_lines.csv").is_file()  # a typed local path is the user's: kept

    dq = render("pages/2_Data_quality.py", run, "en")
    assert dq.metric[0].label == tr("dq.score", "en")
    assert [b.label for b in dq.download_button] == [tr("dq.download", "en")]
    assert not dq.exception

    profile = render("pages/3_Demand_profile.py", run, "en")
    assert not profile.exception and (run / "profile" / "demand_profile.json").is_file()
    assert len(profile.dataframe) >= 2  # EIQ table and shipment split

    basis_page = render("pages/4_Design_basis.py", run, "en")
    assert not basis_page.exception and not basis_page.error
    assert basis_page.metric[0].label == tr("dd.lines", "en")  # live preview
    basis = basis_page.session_state["basis"]
    basis_page.number_input(key=f"basis.{run.name}.projection.growth_rate").set_value(0.05).run()
    assert basis_page.session_state["basis"]["projection"]["growth_rate"] == 0.05
    basis_page.slider(key=f"basis.{run.name}.projection.design_percentile").set_value(90.0).run()
    assert basis_page.session_state["basis"]["projection"]["design_percentile"] == 90.0
    basis = basis_page.session_state["basis"]

    # one browser session across pages: the keys page 4 set (the run is already restored)
    kept = {"basis": basis, "_restored_run": str(run.resolve())}
    sizing = render("pages/5_Scenarios.py", run, "en", **kept)
    assert not sizing.exception
    size_button = next(b for b in sizing.button if b.label == tr("scn.size", "en"))
    size_button.click().run()
    assert not sizing.exception and not sizing.error, texts(sizing, "error")
    assert tr("scn.sized", "en") in texts(sizing, "success")
    assert (run / "comparison" / "comparison.json").is_file()

    results = render("pages/6_Results.py", run, "en")
    assert not results.exception and len(results.image) >= 3
    sized_basis = yaml.safe_load((run / "inputs" / "basis.yaml").read_text(encoding="utf-8"))
    assert sized_basis["projection"]["growth_rate"] == 0.05  # what the form said reached the run
    assert sized_basis["projection"]["design_percentile"] == 90.0
    again = render("pages/5_Scenarios.py", run, "en")  # sealed: shown, not editable
    assert tr("scn.sealed", "en") in texts(again, "info")


@pytest.mark.slow
def test_T10_4_blocking_data_quality_issue_keeps_the_run_and_page_2_explains_it(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    lines = (csv_dir / "order_lines.csv").read_text(encoding="utf-8").splitlines()
    short = tmp_path / "short_history.csv"  # one month of history: R9 is blocking (< 3 months)
    short.write_text(
        "\n".join(lines[:1] + [ln for ln in lines[1:] if ln.split(",")[1] < "2025-02-01"]) + "\n",
        encoding="utf-8",
    )
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    up.selectbox(key="up.dataset").select("order_lines").run()
    up.text_input(key="up.order_lines.path").input(str(short)).run()
    up.button[-1].click().run()
    assert not up.exception
    assert any("exit 3" in e and "R9" in e for e in texts(up, "error"))
    assert tr("upload.see_dq", "en") in texts(up, "info")
    run = Path(up.session_state["run_dir"])  # the folder is kept: dq/ says why
    dq = render("pages/2_Data_quality.py", run, "en")
    assert not dq.exception
    assert any("R9" in e for e in texts(dq, "error"))


def test_T10_4_an_upload_larger_than_memory_suggests_the_cli(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    monkeypatch.setattr(ingest_ui, "memory_limit", lambda: 10)  # 10 bytes: everything is too big
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    up.file_uploader(key="up.sku_master").upload("sku_master.csv", b"x" * 100, "text/csv").run()
    assert not up.exception
    assert any("too large" in e for e in texts(up, "error"))
    assert any(c.value.startswith("whsizing ingest sku_master.csv ") for c in up.code)
    assert not (tmp_path / ".uploads").exists()  # nothing was written


def test_R8c_the_cli_hint_for_an_upload_with_a_quote_in_its_name_is_one_shell_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shlex

    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    monkeypatch.setattr(ingest_ui, "memory_limit", lambda: 10)
    up = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    up.session_state["lang"] = "en"
    up.run()
    name = 'client\'s "big" $(x).csv'
    up.file_uploader(key="up.sku_master").upload(name, b"x" * 100, "text/csv").run()
    assert not up.exception
    words = [shlex.split(c.value.replace("<salt-file>", "SALT")) for c in up.code]
    assert [w[2] for w in words if w[:2] == ["whsizing", "ingest"]] == [name]


def test_T10_4_the_run_written_by_the_app_is_a_cli_run(
    csv_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same run folders as the CLI: ingested by the app's helper, then `whsizing profile`."""
    from typer.testing import CliRunner

    from whsizing.cli import app as cli_app

    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    run = ingest_run(csv_dir, tmp_path / "runs")
    result = CliRunner().invoke(cli_app, ["profile", str(run)])
    assert result.exit_code == 0, result.output
    assert json.loads((run / "profile" / "demand_profile.json").read_text("utf-8"))[
        "operating_days"
    ]


# ------------------------------------------------------------------- fix round 1 (audit findings)
@pytest.fixture(scope="session")
def ingested_run(csv_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A run with the four datasets ingested, not sized: pages 4 and 5 are open on it."""
    root = tmp_path_factory.mktemp("f10b_ingested")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_RUNS", str(root))
        return ingest_run(csv_dir, root)


@pytest.fixture
def ingested(ingested_run: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the ingested run in its own runs folder (the pages may write drafts)."""
    root = tmp_path / "runs"
    root.mkdir()
    monkeypatch.setenv("WHSIZING_RUNS", str(root))
    return Path(shutil.copytree(ingested_run, root / ingested_run.name))


@pytest.mark.parametrize(
    ("name", "content"),
    [("fake.parquet", b"this is not parquet"), ("fake.xlsx", b"this is not xlsx"),
     ("empty.csv", b""), ("garbage.csv", bytes(range(256)) * 20)],
)  # fmt: skip
def test_T10_4_page_1_a_corrupt_file_is_an_error_message_not_a_traceback(
    name: str, content: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    bad = tmp_path / name
    bad.write_bytes(content)
    up = upload_page("order_lines", bad)
    assert not up.exception, [str(e.value) for e in up.exception]
    assert up.error, "the file was neither read nor refused"
    assert not [b for b in up.button if b.label == tr("upload.run", "en")]  # nothing to ingest


def test_T10_4_page_1_a_reader_error_that_is_not_a_whsizing_error_is_shown_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever a reader raises on a client file (here a polars error, which `io.readers` used
    to leak for a corrupt parquet) is an error message on the page, never a traceback."""
    import polars as pl

    import whsizing.io.readers as readers

    def leaky(path: Path, *args: Any, **kwargs: Any) -> Any:
        raise pl.exceptions.ComputeError("parquet: File out of specification")

    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    monkeypatch.setattr(readers, "read_any", leaky)
    (tmp_path / "x.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    up = upload_page("order_lines", tmp_path / "x.csv")
    assert not up.exception, [str(e.value) for e in up.exception]
    assert any("ComputeError" in e and "out of specification" in e for e in texts(up, "error"))


def test_T10_4_page_4_save_is_disabled_for_an_override_the_catalog_does_not_know(
    ingested: Path,
) -> None:
    p4 = render("pages/4_Design_basis.py", ingested, "en")
    key = f"basis.{ingested.name}.overrides"
    save = lambda: next(b for b in p4.button if b.label == tr("basis.save", "en"))  # noqa: E731
    assert not save().disabled and not p4.error
    p4.text_area(key=key).set_value("nope.param: 3").run()
    assert not p4.exception
    assert any("unknown parameter id 'nope.param'" in e for e in texts(p4, "error"))
    assert save().disabled
    p4.text_area(key=key).set_value("manual_p2p.pick_rate_shelving_lines_h: 60").run()
    assert not p4.error and not save().disabled  # a catalog parameter is accepted
    assert p4.session_state["basis"]["overrides"] == {"manual_p2p.pick_rate_shelving_lines_h": 60}


def test_T10_4_page_5_refuses_to_size_a_basis_with_an_unknown_override(ingested: Path) -> None:
    basis = render("pages/4_Design_basis.py", ingested, "en").session_state["basis"]
    basis = {**basis, "overrides": {"nope.param": 3}}  # what an unsaved page-4 edit leaves behind
    p5 = render("pages/5_Scenarios.py", ingested, "en", basis=basis)
    next(b for b in p5.button if b.label == tr("scn.size", "en")).click().run()
    assert not p5.exception
    assert texts(p5, "error") == [tr("scn.need_basis", "en")]  # not a CLI "exit 2" afterwards
    assert not p5.success


def test_T10_4_page_5_with_no_scenario_left_cannot_be_saved_or_sized(ingested: Path) -> None:
    p5 = render("pages/5_Scenarios.py", ingested, "en")
    remove = tr("sc_remove", "en")
    while cards := [b for b in p5.button if b.label == remove]:
        cards[0].click().run()
    assert not p5.exception
    assert texts(p5, "error") == [tr("scn.none", "en")]
    buttons = {b.label: b.disabled for b in p5.button}
    assert buttons[tr("scn.size", "en")] and buttons[tr("scn.save", "en")]
    assert not buttons[tr("scn.add", "en")]  # a card can still be added


def test_T10_4_page_6_row_labels_carry_their_unit_once(report_data: Any) -> None:
    from whsizing.app.results_ui import block_frame

    labels = [
        label
        for table in report_data.tables.values()
        for block in table.blocks
        for label in next(iter(block_frame(block, "en", True).values()))
    ]
    assert "Total area (m²)" in labels and "Capex (€)" in labels  # already in the report label
    assert "Rent [€]" in labels  # added when the report label has none
    doubled = [x for x in labels if ("(m²" in x and x.endswith("[m²]")) or x.endswith("(€) [€]")]
    assert not doubled
    assert not [x for x in labels if "[-]" in x]


@pytest.mark.pdf
def test_T10_4_page_6_builds_the_real_excel_and_pdf_and_offers_them(runs_root: Path) -> None:
    """No faked builder: F9b and F9c through the `report` command, from the page buttons."""
    run = next(runs_root.iterdir())
    at = render("pages/6_Results.py", run, "en")
    assert [b.label for b in at.button if b.key and b.key.startswith("export.")] == [
        tr("results.build", "en", kind="XLSX"),
        tr("results.build", "en", kind="PDF"),
    ]
    assert not [i for i in texts(at, "info") if "not available" in i]
    for kind in ("xlsx", "pdf"):
        at.button(key=f"export.{kind}").click().run()
        assert not at.exception and not at.error, texts(at, "error")
    assert (run / "report" / "report_en.xlsx").read_bytes()[:2] == b"PK"
    assert (run / "report" / "report_en.pdf").read_bytes()[:5] == b"%PDF-"
    assert {"report_en.xlsx", "report_en.pdf"} <= {b.label for b in at.download_button}


@pytest.mark.parametrize(
    ("page", "rel", "content"),
    [
        ("pages/2_Data_quality.py", "dq/dq_report.json", "{}"),  # parses, is no DQReport
        ("pages/3_Demand_profile.py", "profile/demand_profile.json", "{"),
        ("pages/4_Design_basis.py", "design/design_day.json", "{"),  # not even JSON
    ],
)
def test_T10_4_a_run_file_that_does_not_parse_is_an_error_message_not_a_traceback(
    page: str, rel: str, content: str, runs_root: Path
) -> None:
    run = next(runs_root.iterdir())
    (run / rel).write_text(content, encoding="utf-8")
    at = render(page, run, "en")
    assert not at.exception, [str(e.value) for e in at.exception]
    assert any("ConfigError" in e and Path(rel).name in e for e in texts(at, "error"))
