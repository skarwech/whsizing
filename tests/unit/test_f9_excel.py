"""F9b Excel report on the small synthetic site (the F9a test support run: F1 data, F2-F8,
sensitivity on, baseline = the client's current operation). T9.1 the file opens and has the twelve
sheets with their headers in FR and EN, T9.2 the Summary numbers equal comparison.json (and the
scenario sheets equal result.json / finance.json), T9.5 FR and EN workbooks hold the same numbers
at the same coordinates; then the format rules (freeze, number formats, conditional colour,
autofilter, print setup, images), the trace comments, the edge runs (scenario not computed, no
baseline, baseline scenario) and the integrity gate (a failed check writes nothing)."""

from __future__ import annotations

import io
import itertools
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_f9_excel_support import (
    HEADERS,
    LANGS,
    NUMBER_FORMATS,
    SHEETS,
    assert_summary_equals_comparison_json,
    comments,
    is_plain_number,
    numbers_by_sheet,
    numeric_cells,
    open_book,
    read_json,
    row_of,
    string_cells,
    triple,
)
from tests.unit.test_f9_tables_support import (
    baseline_scenario_run,
    private_run,
    small_run,
    with_cell,
)

from whsizing.errors import ConfigError, ReportIntegrityError
from whsizing.report import iter_cells, load_report_data, render_cell, t
from whsizing.report.excel import build_excel, cell_content, render_workbook, sheet_name
from whsizing.report.i18n import Lang
from whsizing.scenarios.compare import compare, not_computed_result
from whsizing.schemas import Cell, Range
from whsizing.schemas.run import RunOutput
from whsizing.schemas.trace import Tracer

NUMERIC_FMTS = {"int", "dec1", "dec2", "num", "pct", "eur", "bool"}
TRACE_HEAD = re.compile(r"Trace (\S+) \((?:cas )?(\w+)(?: world)?\)")
GREEN, RED = "C6EFCE", "FFC7CE"


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9b_excel")


@pytest.fixture(scope="module")
def paths(run: RunOutput) -> dict[Lang, Path]:
    return {lang: build_excel(run, lang) for lang in LANGS}


@pytest.fixture(scope="module")
def books(paths: dict[Lang, Path]) -> dict[Lang, Any]:
    return {lang: open_book(p) for lang, p in paths.items()}


def copy_run(run: RunOutput, dest: Path, **change: Any) -> RunOutput:
    """A copy of the run folder without its report/ and `run` with `change` applied, so that an
    edited run never writes into the shared one."""
    shutil.copytree(run.run_dir, dest, ignore=shutil.ignore_patterns("report"))
    return run.model_copy(update={"run_dir": dest, **change})


def without_baseline(run: RunOutput) -> dict[str, Any]:
    finances = {
        k: v.model_copy(
            update={
                "npv_vs_baseline": None,
                "irr_vs_baseline": None,
                "payback_years": None,
                "delta_cash_flows_typ": [],
            }
        )
        for k, v in run.finances.items()
    }
    return {"finances": finances, "comparison": compare(run.results, finances, None)}


def test_R7_4_the_workbooks_are_built_in_a_private_copy_of_the_shared_run(
    run: RunOutput, paths: dict[Lang, Path], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The F9 modules share one cached small run; a build writes `report/` into its run folder, so
    each module works on a copy. Another module (the PDF one) lists `report/` of its own copy and
    expects its three diagrams, two PDFs and the trace only: no workbook of this module."""
    shared = Path(small_run(tmp_path_factory).run_dir)
    assert Path(run.run_dir) != shared
    assert all(shared not in p.parents for p in paths.values())
    assert not list((shared / "report").glob("*"))  # the runner makes the folder, empty


# ---------------------------------------------------------------------------------- T9.1
@pytest.mark.parametrize("lang", LANGS)
def test_T9_1_the_workbook_opens_with_the_twelve_sheets_in_order(
    run: RunOutput, paths: dict[Lang, Path], books: dict[Lang, Any], lang: Lang
) -> None:
    assert paths[lang] == Path(run.run_dir) / "report" / f"report_{lang}.xlsx"
    wb = books[lang]
    assert wb.sheetnames == SHEETS[lang]  # exactly twelve: no hidden helper sheet
    assert [ws.sheet_state for ws in wb.worksheets] == ["visible"] * 12
    assert [sheet_name(i, lang) for i in load_report_data(run, lang).tables] == SHEETS[lang]


@pytest.mark.parametrize("lang", LANGS)
def test_T9_1_every_sheet_has_its_title_and_header_cells(
    books: dict[Lang, Any], lang: Lang
) -> None:
    wb = books[lang]
    for ws, (block_title, header_row, header) in zip(wb.worksheets, HEADERS[lang], strict=True):
        assert ws["A3"].value == block_title, ws.title
        got = [ws.cell(header_row, c).value or "" for c in range(1, len(header) + 1)]
        assert got == header, ws.title
    assert wb.worksheets[0]["A1"].value == t("table.summary", lang)


def test_T9_1_the_sheet_name_never_holds_a_character_excel_forbids() -> None:
    assert sheet_name("capex_opex", "en") == "Capex - Opex" == sheet_name("capex_opex", "fr")
    for lang in LANGS:
        for name in SHEETS[lang]:
            assert len(name) <= 31 and not set(name) & set("[]:*?/\\")


# ---------------------------------------------------------------------------------- T9.2
@pytest.mark.parametrize("lang", LANGS)
def test_T9_2_summary_values_equal_comparison_json(
    run: RunOutput, books: dict[Lang, Any], lang: Lang
) -> None:
    checks = assert_summary_equals_comparison_json(books[lang], run, lang)
    assert checks > 40  # per scenario: ranges, payback, scalars and the equipment of the family


def test_T9_2_scenario_sheets_equal_result_and_finance_json(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    wb, lang = books["en"], "en"
    scen, fte, capex, cash = (wb[SHEETS[lang][i]] for i in (4, 5, 6, 7))
    for i, sid in enumerate(run.results):
        r = read_json(run, f"scenarios/{sid}/result.json")
        f = read_json(run, f"scenarios/{sid}/finance.json")
        area = row_of(scen, t("block.scenarios.area", lang))
        total = triple(scen, row_of(scen, t("row.area_total", lang), area), i)
        assert [total[k] for k in range(3)] == pytest.approx(
            [r["area"]["total_m2"][k] for k in ("lo", "typ", "hi")], rel=1e-12
        )
        heads = row_of(fte, t("block.fte.heads", lang))
        got = triple(fte, row_of(fte, t("row.total", lang), heads), i)
        assert list(got) == pytest.approx(
            [r["labor"]["total_heads"][k] for k in ("lo", "typ", "hi")], rel=1e-12
        )
        total_row = row_of(
            capex, t("row.total", lang), row_of(capex, t("block.capex_opex.capex", lang))
        )
        assert list(triple(capex, total_row, i)) == pytest.approx(
            [f["capex_total"][k] for k in ("lo", "typ", "hi")], rel=1e-12
        )
        business = row_of(capex, t("block.capex_opex.totals", lang))
        tco = triple(capex, row_of(capex, t("row.tco", lang), business), i)
        assert list(tco) == pytest.approx([f["tco"][k] for k in ("lo", "typ", "hi")], rel=1e-12)
        flows = [
            cash.cell(6 + y, 2 + _cash_col(run, sid)).value for y in range(len(f["cash_flows_typ"]))
        ]
        assert flows == pytest.approx(f["cash_flows_typ"], rel=1e-12)


def _cash_col(run: RunOutput, sid: str) -> int:
    """0-based offset of the scenario's own-flow column in the Cash flow block (2 or 3 columns
    per scenario: flow, [delta], cumulative)."""
    offset = 0
    for s, fin in run.finances.items():
        if s == sid:
            return offset
        offset += 3 if fin.delta_cash_flows_typ else 2
    raise AssertionError(sid)


@pytest.mark.parametrize("lang", LANGS)
def test_T9_2_every_numeric_model_cell_is_a_number_in_the_sheets(
    run: RunOutput, books: dict[Lang, Any], lang: Lang
) -> None:
    """The report model's numbers, all of them and nothing else, are the numeric cells of the
    workbook: never written as text, never recomputed."""
    data = load_report_data(run, lang)
    model = sorted(
        float(c.value)
        for _, c in iter_cells(data.tables)
        if c.fmt in NUMERIC_FMTS and isinstance(c.value, int | float)
    )
    sheet = sorted(
        float(v)
        for ws in books[lang].worksheets
        for v in numeric_cells(ws).values()
        if is_plain_number(v)
    )
    assert len(model) > 2000
    assert sheet == pytest.approx(model, rel=1e-12, abs=1e-12)


# ---------------------------------------------------------------------------------- T9.5
def test_T9_5_fr_and_en_workbooks_hold_identical_numeric_cells(books: dict[Lang, Any]) -> None:
    fr, en = books["fr"], books["en"]
    assert numbers_by_sheet(fr) == numbers_by_sheet(en)  # same coordinates, same values
    assert sum(len(v) for v in numbers_by_sheet(en).values()) > 2000
    for a, b in zip(fr.worksheets, en.worksheets, strict=True):
        assert (a.max_row, a.max_column) == (b.max_row, b.max_column)
        assert a.freeze_panes == b.freeze_panes and a.auto_filter.ref == b.auto_filter.ref
        assert sorted(map(str, a.merged_cells.ranges)) == sorted(map(str, b.merged_cells.ranges))
        assert comments(a).keys() == comments(b).keys()
        assert [(i.anchor._from.row, i.anchor._from.col) for i in a._images] == [
            (i.anchor._from.row, i.anchor._from.col) for i in b._images
        ]
    assert fr["Synthèse"]["A1"].value != en["Summary"]["A1"].value  # and the texts do differ


def test_T9_5_the_build_is_deterministic(run: RunOutput) -> None:
    data = load_report_data(run, "en")
    assert render_workbook(data, {}) == render_workbook(data, {})


# ---------------------------------------------------------------------------------- format rules
@pytest.mark.parametrize("lang", LANGS)
def test_header_row_is_frozen_on_every_sheet(books: dict[Lang, Any], lang: Lang) -> None:
    for ws, (_, header_row, _) in zip(books[lang].worksheets, HEADERS[lang], strict=True):
        assert ws.freeze_panes == f"B{header_row + 1}", ws.title  # rows to the header, col A
    assert ws.page_setup.orientation == "landscape"


def test_number_formats_and_values_stay_numbers(books: dict[Lang, Any]) -> None:
    wb = books["en"]
    ws = wb["Summary"]
    first = row_of(ws, t("row.eligible_share", "en"), 4)
    expected = {
        "row.eligible_share": "0.0 %",
        "row.storage_area": "#,##0",
        "row.total_area": "#,##0",
        "row.fte_design_day": "#,##0.0",
        "row.capex": "#,##0",
        "row.npv": "#,##0",
        "row.payback": "#,##0.0",
        "row.cost_per_line": "#,##0.00",
        "row.n_warnings": "#,##0",
    }
    for key, fmt in expected.items():
        r = row_of(ws, t(key, "en"), first)
        cells = [ws.cell(r, c) for c in range(2, 11) if ws.cell(r, c).value is not None]
        assert cells and {c.number_format for c in cells} == {fmt}, key
        assert all(c.data_type == "n" for c in cells), key
    share = ws.cell(row_of(ws, t("row.eligible_share", "en"), first), 3).value
    assert 0 <= share <= 1  # the share is 0.975, not "97.5 %" and not 97.5
    fit = ws.cell(row_of(ws, t("row.fit", "en"), first), 3)
    assert fit.value == 1 and fit.data_type == "n" and '"Yes"' in fit.number_format
    assert (
        '"Oui"'
        in books["fr"]["Synthèse"]
        .cell(row_of(books["fr"]["Synthèse"], t("row.fit", "fr"), first), 3)
        .number_format
    )
    allowed = NUMBER_FORMATS | {"yyyy-mm-dd", '"Yes";"Yes";"No"'}
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            for c in row:
                if c.data_type in ("n", "d") and c.value is not None:
                    assert c.number_format in allowed, (sheet.title, c.coordinate, c.number_format)


def test_the_fit_flag_has_a_green_and_a_red_conditional_format(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    ws = books["en"]["Summary"]
    rows = ws.conditional_formatting
    fit_row = row_of(ws, t("row.fit", "en"), 4)
    ranges = [(str(cf.sqref), cf.rules) for cf in rows if str(cf.sqref).startswith(f"C{fit_row}:")]
    assert len(ranges) == 1
    sqref, rules = ranges[0]
    assert sqref == f"C{fit_row}:I{fit_row}"  # S0 typ .. S2 typ: every fit cell is inside
    assert [r.dxf.fill.bgColor.rgb[-6:] for r in rules] == [GREEN, RED]
    assert rules[0].formula == [f"AND(ISNUMBER(C{fit_row}),C{fit_row}=1)"]
    assert rules[1].formula == [f"AND(ISNUMBER(C{fit_row}),C{fit_row}=0)"]  # blanks stay blank
    values = [ws.cell(fit_row, c).value for c in (3, 6, 9)]
    assert values == [1, 1, 1]
    data = load_report_data(run, "en")
    summary = data.tables["summary"]
    block = next(b for b in summary.blocks if b.key == "comparison")
    index = next(i for i, c in enumerate(block.columns) if c.key == "S1.typ")
    no_fit = with_cell(data, "summary", "fit", index, value=0.0)
    ws2 = open_book_bytes(render_workbook(no_fit, {}))["Summary"]
    assert [ws2.cell(fit_row, c).value for c in (3, 6, 9)] == [1, 0, 1]  # S1 does not fit


def open_book_bytes(payload: bytes) -> Any:
    return open_book(io.BytesIO(payload))


def test_scenarios_sheet_has_lo_typ_hi_columns_per_scenario(books: dict[Lang, Any]) -> None:
    ws = books["en"]["Scenarios"]
    assert [ws.cell(5, c).value for c in range(2, 11)] == ["Low", "Typical", "High"] * 3
    groups = [ws.cell(4, c).value for c in (2, 5, 8)]
    assert [g.split(" · ")[0] for g in groups] == ["S0", "S1", "S2"]
    assert {"B4:D4", "E4:G4", "H4:J4"} <= {str(r) for r in ws.merged_cells.ranges}


def test_assumptions_have_one_row_per_param_and_the_filter_is_on(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    ws = books["en"]["Assumptions"]
    n = len(load_report_data(run, "en").catalog.params)
    assert ws.auto_filter.ref == f"A4:M{4 + n}"  # id + 11 columns + one for S1's overrides (I88)
    ids = [ws.cell(r, 1).value for r in range(5, 5 + n)]
    assert len(set(ids)) == n and all(i and "." in i for i in ids)
    assert ws.cell(5 + n, 1).value is None  # nothing after the last param but the end
    assert all(books["en"][s].auto_filter.ref in ("", None) for s in ("Summary", "Scenarios"))


@pytest.mark.parametrize("lang", LANGS)
def test_I88_assumptions_sheet_carries_the_value_each_scenario_used(
    run: RunOutput, books: dict[Lang, Any], lang: Lang
) -> None:
    """One row per Param with the base value (column C), then one column per scenario that
    overrides something: S1's cell holds its `<sid>:<id>` value of the params_snapshot."""
    snap = run.manifest.params_snapshot
    ws = books[lang][sheet_name("assumptions", lang)]
    head = [ws.cell(4, c).value for c in range(1, 15)]
    assert head[2] == t("col.value_used", lang)
    assert head[12] == "S1" and head[13] is None  # headed by the scenario id, nothing after it
    last = 4 + len(load_report_data(run, lang).catalog.params)  # 72 Params, then the note
    rows = {ws.cell(r, 1).value: r for r in range(5, last + 1)}
    assert len(rows) == 72 and all(pid in snap for pid in rows)
    for pid, r in rows.items():
        assert ws.cell(r, 3).value == snap[pid], pid
        override = snap.get(f"S1:{pid}")
        assert ws.cell(r, 13).value == override, pid  # None when S1 did not override it
    note = t("assumptions.scenario_columns", lang, scenarios="S1")  # says what the S1 column is
    assert note in {ws.cell(r, 1).value for r in range(last + 1, ws.max_row + 1)}
    assert ws.cell(rows["amr_gtp.station_rate_lines_h"], 3).value == 250.0
    assert ws.cell(rows["amr_gtp.station_rate_lines_h"], 13).value == 230.0


def test_print_setup_is_landscape_a4_one_page_wide_with_the_run_id_in_the_footer(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    for ws in books["en"].worksheets:
        assert ws.page_setup.orientation == "landscape", ws.title
        assert ws.page_setup.paperSize == 9
        assert ws.sheet_properties.pageSetUpPr.fitToPage is True
        assert ws.page_setup.fitToWidth in (None, 1)  # None: the default, one page wide
        assert ws.page_setup.fitToHeight == 0  # as many pages tall as needed
        assert run.manifest.run_id in ws.oddFooter.left.text


def test_demand_profile_carries_the_charts_as_images_below_the_tables(
    books: dict[Lang, Any],
) -> None:
    ws = books["en"]["Demand profile"]
    assert len(ws._images) == 5
    rows = sorted(i.anchor._from.row + 1 for i in ws._images)
    last_cell = max(c.row for row in ws.iter_rows() for c in row if c.value is not None)
    assert rows[0] > last_cell and all(b - a >= 19 for a, b in itertools.pairwise(rows))
    assert all(i.format == "png" and i.width > 500 for i in ws._images)
    assert all(not books["en"][s]._images for s in ("Summary", "Scenarios"))


def test_summary_carries_the_indicative_banner_and_the_confidence_note(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    names: tuple[tuple[Lang, str], ...] = (("en", "Summary"), ("fr", "Synthèse"))
    for lang, name in names:
        ws = books[lang][name]
        assert ws["A2"].value == t("banner.indicative", lang)
        note = render_cell(load_report_data(run, lang).tables["summary"].notes[1], lang)
        assert note.startswith("Ranking" if lang == "en" else "Classement")
        assert note in string_cells(ws)


def test_methodology_has_the_formulas_one_row_per_line_and_the_versions(
    run: RunOutput, books: dict[Lang, Any]
) -> None:
    ws = books["en"]["Methodology"]
    assert row_of(ws, "Run id") and ws.cell(row_of(ws, "Run id"), 2).value == run.manifest.run_id
    start = row_of(ws, t("block.methodology_formulas", "en")) + 1
    lines = t("methodology.formulas", "en").splitlines()
    assert [ws.cell(start + i, 1).value or "" for i in range(len(lines))] == lines
    assert ws.max_row == start + len(lines) - 1


@pytest.mark.parametrize("lang", LANGS)
def test_R7_3_the_methodology_sheet_says_the_formulas_and_the_flags_in_its_language(
    run: RunOutput, books: dict[Lang, Any], lang: Lang
) -> None:
    from whsizing.report.i18n import flag_text

    ws = books[lang][SHEETS[lang][-1]]  # Methodology / Méthodologie, the last sheet
    cells = " ".join(string_cells(ws))
    assert t("methodology.formulas", lang).splitlines()[1] in string_cells(ws)
    raised = {f.code for r in run.results.values() for f in r.flags if f.severity != "info"}
    assert raised
    for code in raised:
        assert flag_text(code, lang) in cells, code
    assert not re.search(r"\bF_[A-Z_]+", cells)  # no raw flag code on the sheet


# ---------------------------------------------------------------------------------- trace
@pytest.mark.parametrize("lang", LANGS)
def test_every_traced_cell_has_a_comment_with_its_trace_id_and_formula(
    run: RunOutput, paths: dict[Lang, Path], books: dict[Lang, Any], lang: Lang
) -> None:
    data = load_report_data(run, lang)
    traced = [c for _, c in iter_cells(data.tables) if c.trace_id and c.value is not None]
    assert len(traced) > 1000
    nodes = {
        (n.id, n.world): n for n in Tracer.load_jsonl(paths[lang].parent / "trace.jsonl").nodes
    }
    total = 0
    for ws in books[lang].worksheets:
        for (r, c), text in comments(ws).items():
            m = TRACE_HEAD.match(text)
            assert m, text[:80]
            node = nodes[(m.group(1), m.group(2))]
            assert node.formula in text and node.label in text
            for ref in node.inputs.values():
                assert ref in text
            assert ws.cell(r, c).value == pytest.approx(node.value, rel=1e-12), (ws.title, r, c)
            total += 1
    assert total == len(traced)
    for name in ("Design basis", "Assumptions", "Sensitivity"):
        assert not comments(books["en"][name])
    summary = comments(books["en"]["Summary"])
    assert summary and all(k[0] >= 6 for k in summary)  # the comparison rows only


def test_the_exported_trace_resolves_every_cited_id(
    run: RunOutput, paths: dict[Lang, Path]
) -> None:
    exported = Tracer.load_jsonl(paths["en"].parent / "trace.jsonl")
    ids = {(n.id, n.world) for n in exported.nodes}
    data = load_report_data(run, "en")
    cited = {(c.trace_id, c.world) for _, c in iter_cells(data.tables) if c.trace_id}
    assert cited <= ids
    assert any(i.endswith(".report.n_warnings") for i, _ in ids)  # the node only the report has
    assert (paths["fr"].parent / "trace.jsonl").read_bytes() == (
        paths["en"].parent / "trace.jsonl"
    ).read_bytes()


@pytest.mark.parametrize("lang", LANGS)
def test_no_untranslated_text_in_the_cells_or_the_comments(
    books: dict[Lang, Any], lang: Lang
) -> None:
    for ws in books[lang].worksheets:
        texts = [*string_cells(ws), *comments(ws).values()]
        assert texts and not [s for s in texts if "{{" in s and "missing" in s], ws.title


# ---------------------------------------------------------------------------------- cells
@pytest.mark.parametrize(
    ("fmt", "value", "num_format"),
    [
        ("int", 1234.0, "#,##0"),
        ("eur", 1234.5, "#,##0"),
        ("dec1", 1.25, "#,##0.0"),
        ("dec2", 1.255, "#,##0.00"),
        ("pct", 0.123, "0.0 %"),
        ("num", 0.05, None),
    ],
)
def test_cell_content_numbers_are_numbers_with_their_format(
    fmt: str, value: float, num_format: str | None
) -> None:
    got, f = cell_content(Cell(value=value, fmt=fmt), "fr")  # pyright: ignore[reportArgumentType]
    assert got == value and isinstance(got, float) and f == num_format


def test_cell_content_bool_is_one_or_zero_shown_as_yes_or_no_by_the_format() -> None:
    assert cell_content(Cell(value=1.0, fmt="bool"), "en") == (1.0, '"Yes";"Yes";"No"')
    assert cell_content(Cell(value=0.0, fmt="bool"), "fr") == (0.0, '"Oui";"Oui";"Non"')


def test_cell_content_text_and_keys_are_strings_never_formulas() -> None:
    assert cell_content(Cell(value="=1+1", fmt="text"), "en") == ("=1+1", None)
    assert cell_content(Cell(value="common.yes", fmt="key"), "fr") == ("Oui", None)
    assert cell_content(Cell(), "en") == (None, None)


def test_cell_content_refuses_text_in_a_numeric_cell_and_non_finite_numbers() -> None:
    with pytest.raises(ReportIntegrityError, match="holds the text"):
        cell_content(Cell(value="12", fmt="int"), "en")
    for bad in (float("nan"), float("inf"), 1.5e308):  # the last one: beyond Excel's range
        with pytest.raises(ReportIntegrityError, match="no number Excel can hold"):
            cell_content(Cell(value=bad, fmt="dec1"), "en")


# ---------------------------------------------------------------------------------- edge runs
def test_a_scenario_not_computed_is_a_grey_column_with_the_reason(
    run: RunOutput, tmp_path: Path
) -> None:
    reason = "SizingInfeasibleError: test reason"
    results = {
        **run.results,
        "S1": not_computed_result(
            run.results["S1"].scenario, reason, run.results["S1"].area.building_m2
        ),
    }
    finances = {k: v for k, v in run.finances.items() if k != "S1"}
    run2 = copy_run(
        run,
        tmp_path / "run",
        results=results,
        finances=finances,
        comparison=compare(results, finances, run.comparison.baseline_id),
    )
    wb = open_book(build_excel(run2, "en"))
    ws = wb["Summary"]
    first = row_of(ws, t("row.eligible_share", "en"), 4)
    last = row_of(ws, t("row.n_low_confidence", "en"), first)
    assert f"E{first}:G{last}" in {str(r) for r in ws.merged_cells.ranges}
    cell = ws.cell(first, 5)
    assert reason in cell.value and cell.value.startswith("S1")
    assert cell.fill.fgColor.rgb.endswith("D9D9D9") and ws["E4"].fill.fgColor.rgb.endswith("D9D9D9")
    for r in range(first, last + 1):
        assert not any(is_plain_number(ws.cell(r, c).value) for c in (5, 6, 7))
    assert any(is_plain_number(ws.cell(first + 3, c).value) for c in (2, 3, 4, 8, 9, 10))  # S0, S2
    cash = wb["Cash flow"]  # two columns (flow, cumulative) for the scenario with no finance
    assert "E6:F11" in {str(r) for r in cash.merged_cells.ranges}
    assert reason in cash["E6"].value
    assert not any(k[1] in (5, 6) for k in comments(cash))
    assert any(reason in s for s in string_cells(wb["Methodology"]))


def test_a_run_without_a_baseline_shows_absolute_values_and_no_npv_or_payback(
    run: RunOutput, tmp_path: Path
) -> None:
    run2 = copy_run(run, tmp_path / "run", **without_baseline(run))
    wb = open_book(build_excel(run2, "en"))
    for name in ("Summary", "Capex - Opex"):
        labels = {c.value for c in wb[name]["A"]}
        assert {t("row.tco", "en"), t("row.opex_y1", "en")} <= labels, name
        assert not labels & {t("row.npv", "en"), t("row.payback", "en")}, name
    assert t("row.capex", "en") in {c.value for c in wb["Summary"]["A"]}
    header = [c.value for c in wb["Cash flow"][5]]
    assert t("col.delta", "en") not in header and header.count(t("col.cumulative", "en")) == 3
    ws = wb["Summary"]
    tco = triple(ws, row_of(ws, t("row.tco", "en"), 4), 0)
    assert all(is_plain_number(v) for v in tco)
    assert t("limit.gen.no_baseline", "en") in string_cells(wb["Methodology"])


def test_a_scenario_as_the_baseline_has_no_delta_and_no_cumulative_column(
    run: RunOutput, tmp_path: Path
) -> None:
    run2 = baseline_scenario_run(run)
    run2 = copy_run(run2, tmp_path / "run")
    ws = open_book(build_excel(run2, "en"))["Cash flow"]
    assert [c.value for c in ws[5]][1:] == [
        "Cash flow", "Cash flow", "Δ vs baseline", "Cumulative",
        "Cash flow", "Δ vs baseline", "Cumulative",
    ]  # fmt: skip
    assert ws["B4"].value.startswith("S0")  # S0: a single column, its group is not merged
    assert {"C4:E4", "F4:H4"} == {str(r) for r in ws.merged_cells.ranges if r.min_row == 4}


# ---------------------------------------------------------------------------------- the gate
def test_an_integrity_failure_raises_exit_5_and_writes_nothing(
    run: RunOutput, tmp_path: Path
) -> None:
    row = run.comparison.rows[1]
    capex = row.capex
    assert capex is not None
    doubled = Range(lo=capex.lo * 2, typ=capex.typ * 2, hi=capex.hi * 2, unit=capex.unit)
    bad_row = row.model_copy(update={"capex": doubled})
    rows = [bad_row if r is row else r for r in run.comparison.rows]
    bad = run.comparison.model_copy(update={"rows": rows})
    run2 = copy_run(run, tmp_path / "run", comparison=bad)
    with pytest.raises(ReportIntegrityError, match="IC1") as err:
        build_excel(run2, "en")
    assert err.value.exit_code == 5
    assert not (Path(run2.run_dir) / "report").exists()  # no xlsx, no trace.jsonl, no folder


def test_an_unsupported_language_is_a_config_error_and_writes_nothing(
    run: RunOutput, tmp_path: Path
) -> None:
    run2 = copy_run(run, tmp_path / "run")
    with pytest.raises(ConfigError):
        build_excel(run2, "de")  # pyright: ignore[reportArgumentType]
    assert not (Path(run2.run_dir) / "report").exists()


def test_an_untranslated_text_fails_the_build_before_any_file_is_written(
    run: RunOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from whsizing.report import excel

    run2 = copy_run(run, tmp_path / "run")
    real = excel.t
    monkeypatch.setattr(
        excel,
        "t",
        lambda key, lang, **kw: (
            "{{ missing:x }}" if key == "excel.trace" else real(key, lang, **kw)
        ),
    )
    with pytest.raises(ReportIntegrityError, match="IC8"):
        build_excel(run2, "en")
    assert not (Path(run2.run_dir) / "report").exists()


def test_the_workbook_of_an_unreadable_output_folder_is_a_whsizing_error(
    run: RunOutput, tmp_path: Path
) -> None:
    from whsizing.errors import WhsizingError

    run2 = copy_run(run, tmp_path / "run")
    (Path(run2.run_dir) / "report").write_text("a file where the folder should be")
    with pytest.raises(WhsizingError):
        build_excel(run2, "en")


def test_the_workbook_is_value_only_with_no_formula_in_any_cell(books: dict[Lang, Any]) -> None:
    """The stretch (live formulas) is not built: every cell is a value, a string or empty."""
    for wb in books.values():
        kinds = {c.data_type for ws in wb.worksheets for row in ws.iter_rows() for c in row}
        assert kinds <= {"n", "s", "d"}, kinds


def test_build_excel_is_the_function_the_cli_looks_up() -> None:
    import whsizing.report as report

    assert report.build_excel is build_excel and "build_excel" in report.__all__
