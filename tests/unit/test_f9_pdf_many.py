"""F9c with more than the three example scenarios: the page budget (12-18 pages, kept up to four
scenarios at sizes that stay legible), the block diagrams, Appendix C and the tornado not shrunk
to buy pages, tables cut by scenario instead of running off the A4 page, `split` itself, the
page fit loop and the error of a report folder that cannot be written."""

from __future__ import annotations

import io
import re
import warnings
from pathlib import Path

import pytest
from pypdf import PdfReader
from tests.unit.test_f9_pdf_support import (
    APPENDIX_C_MIN_PT,
    DIAGRAM_MIN_PT,
    RIGHT_EDGE_PT,
    appendix_c_sizes,
    diagram_label_sizes,
    image_boxes,
    layout_overflow,
    many_scenarios_run,
    own_run,
    plain,
    text_starts,
)

from whsizing.errors import WhsizingError
from whsizing.report import load_report_data, t
from whsizing.report import pdf as pdf_module
from whsizing.report.charts import DPI, SIZE_IN
from whsizing.report.i18n import Lang
from whsizing.report.pdf import (
    COMPACT_LEVELS,
    MAX_PAGES,
    build_pdf,
    fit_pdf,
    render_html,
)
from whsizing.report.pdf_text import caveats
from whsizing.report.pdf_view import Box, Grid, Head, Line, split
from whsizing.schemas.run import RunOutput

pytestmark = pytest.mark.pdf
N_SCENARIOS = (4, 6)
BUDGET_SCENARIOS = 4  # I81 c: the most scenarios that fit in 18 pages at the legible sizes
OVER_BUDGET_PAGES = 4  # a study of more scenarios is longer (6: 21 pages), not unboundedly
CASH_TABLES = re.compile(r'<section class="blk cash">(.*?)</section>', re.DOTALL)
ROW_LABELS = re.compile(r'<th class="lab" scope="row">(.*?)</th>')


@pytest.fixture(scope="module", params=N_SCENARIOS, ids=lambda n: f"{n}_scenarios")
def many(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return many_scenarios_run(tmp_path_factory, request.param)


@pytest.fixture(scope="module", params=("fr", "en"))
def pdf(many: RunOutput, request: pytest.FixtureRequest) -> tuple[Lang, Path]:
    lang: Lang = request.param
    return lang, build_pdf(many, lang)


# ------------------------------------------------------------------ page budget
def test_F9c_a_study_of_four_scenarios_stays_within_12_to_18_pages_and_more_is_longer(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    """The budget is met with the diagrams and Appendix C at their legible sizes up to four
    scenarios; beyond, the PDF is longer than 18 pages (and logs it), not set in smaller type."""
    lang, path = pdf
    pages = len(PdfReader(path).pages)
    limit = MAX_PAGES + (OVER_BUDGET_PAGES if len(many.results) > BUDGET_SCENARIOS else 0)
    assert 12 <= pages <= limit, (lang, len(many.results), pages)


def test_F9c_block_diagram_labels_are_not_shrunk_to_fit_the_page_budget(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    """Zone names and m2 were 2.3 pt (two diagrams a row) at four scenarios and more."""
    lang, path = pdf
    sizes = diagram_label_sizes(path, lang, list(many.results))
    assert min(sizes) >= DIAGRAM_MIN_PT, sorted(set(round(s, 1) for s in sizes))


def test_F9c_appendix_c_type_is_not_shrunk_to_fit_the_page_budget(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    """Appendix C is where a reader reproduces the numbers: 5.2-5.6 pt at four scenarios and
    more, 5.8 pt and up now."""
    lang, path = pdf
    runs = appendix_c_sizes(path, lang)
    small = [(n, round(s, 1), x[:24]) for n, s, x in runs if s < APPENDIX_C_MIN_PT]
    assert not small, small[:6]


def test_F9c_the_tornado_is_one_figure_with_a_panel_per_scenario_at_every_size(
    many: RunOutput, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F9a's tornado stacks the panels and grows with the scenarios (R7.1), so the PDF prints one
    figure of the run's own sensitivity: no groups of three, no second title, one x scale."""
    data = load_report_data(many, "en")
    seen: list[tuple[str, list[str]]] = []
    real = pdf_module.chart_png

    def record(d: object, chart_id: str) -> bytes | None:
        if chart_id == "tornado":
            tornado = d.run.sensitivity.tornado  # type: ignore[attr-defined]
            seen.append((chart_id, sorted({b.scenario_id for b in tornado})))
        return real(d, chart_id)  # type: ignore[arg-type]

    monkeypatch.setattr(pdf_module, "chart_png", record)
    html = render_html(data)
    assert seen == [("tornado", sorted(many.results))]  # one figure, every scenario in it
    title = t("chart.tornado.title", "en")
    assert html.count(f'alt="{title}') == 1


def test_F9c_a_many_scenario_report_draws_its_charts_without_a_collapsed_layout(
    many: RunOutput,
) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=".*constrained_layout.*")
        html = render_html(load_report_data(many, "en"))
    assert html.count(f'alt="{t("chart.tornado.title", "en")}') == 1


def test_F9c_the_tornado_is_not_shrunk_to_buy_pages(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    """Its tick labels are 6 pt in the figure and the figure grows with the scenarios: the page
    sets it at the page width (0.95 of its size), not under a cap meant for the fixed-size charts
    (80 mm, 64 mm and 54 mm at the tighter typesettings would scale four panels to 0.6)."""
    _, path = pdf
    fixed_px = round(SIZE_IN[1] * DPI)
    tall = [b for b in image_boxes(path) if b[2] != fixed_px]  # the other charts are SIZE_IN
    assert len(tall) == 1, tall  # one tornado, one page
    _, w_px, _, w_pt, h_pt = tall[0]
    scale = w_pt / (w_px / DPI * 72)
    assert scale >= 0.9, (scale, h_pt)
    assert h_pt <= 297 / 25.4 * 72 - 2 * 18 / 25.4 * 72  # and it fits a page between the margins


def test_F9c_the_executive_summary_stays_on_one_page_with_many_scenarios(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    lang, path = pdf
    pages = [" ".join(plain(p.extract_text()).split()) for p in PdfReader(path).pages]
    last_caveat = " ".join(caveats(load_report_data(many, lang))[-1].split())
    assert t("pdf.s1.messages", lang) in pages[1] and last_caveat in pages[1]
    assert t("pdf.section.data_demand", lang) in pages[2]  # section 2 starts the next page


def test_F9c_appendix_c_traces_every_scenario_of_a_large_study(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    _, path = pdf
    text = "\n".join(plain(p.extract_text()) for p in PdfReader(path).pages)
    assert len(many.results) in N_SCENARIOS
    for sid in many.results:
        assert f"\n{sid}.finance.tco\n" in text, sid


def test_F9c_no_text_runs_beyond_the_right_margin_with_many_scenarios(
    pdf: tuple[Lang, Path],
) -> None:
    """Wide tables are cut by scenario (the label column repeats), none is clipped at the page
    edge: every text run of every page starts inside the 18 mm margin."""
    _, path = pdf
    off = [(n, round(x), s[:30]) for n, x, s in text_starts(path) if x > RIGHT_EDGE_PT + 1]
    assert not off, off[:8]


def test_F9c_no_text_box_or_table_ends_beyond_the_right_margin_with_many_scenarios(
    many: RunOutput, pdf: tuple[Lang, Path]
) -> None:
    """The end of every box in the layout of the tightest typesetting (the one a larger study is
    written in), not only where a text run starts."""
    lang, _ = pdf
    html = render_html(load_report_data(many, lang), compact=COMPACT_LEVELS)
    assert not layout_overflow(html)[:8]


def test_F9c_the_overflow_check_sees_a_box_that_ends_beyond_the_margin() -> None:
    wide = '<html><body><p style="white-space: nowrap">' + "wide " * 80 + "</p></body></html>"
    assert layout_overflow(wide) and not layout_overflow("<html><body><p>short</p></body></html>")


def test_F9c_the_cash_flow_is_cut_into_tables_of_at_most_three_scenarios(
    many: RunOutput,
) -> None:
    html = render_html(load_report_data(many, "en"))
    tables = CASH_TABLES.findall(html)
    assert len(tables) == 2  # 4 scenarios -> 2 + 2, 6 -> 3 + 3
    for sid in many.results:  # each scenario heads the columns of exactly one table
        assert sum(f"{sid} · " in tb[: tb.index("</thead>")] for tb in tables) == 1, sid
    years = [ROW_LABELS.findall(tb) for tb in tables]
    assert years[0] == years[1] and len(years[0]) >= 6  # the years repeat in every table


# ------------------------------------------------------------------ split
def _grid(n: int, columns: int = 1, coloured: bool = True) -> Grid:
    """Heads of `n` scenarios of `columns` columns each; the cell of a line is `row.column`."""
    top = [Head(f"S{i}", columns, colour="#123456" if coloured else "") for i in range(n)]
    heads = [top] if columns == 1 else [top, [Head(f"c{i}") for i in range(n * columns)]]
    lines = [Line("row", [Box(f"{r}.{c}") for c in range(n * columns)]) for r in range(2)]
    return Grid("title", "label", heads, [*lines, Line("sec", [], "section")], n * columns)


@pytest.mark.parametrize(
    ("n", "per", "sizes"),
    [
        (3, 4, [3]),
        (4, 3, [2, 2]),
        (5, 4, [3, 2]),
        (6, 3, [3, 3]),
        (7, 3, [3, 2, 2]),
        (8, 4, [4, 4]),
    ],
)
def test_F9c_split_balances_the_scenarios_over_the_tables(
    n: int, per: int, sizes: list[int]
) -> None:
    parts = split(_grid(n), per)
    assert [p.width for p in parts] == sizes
    assert [h.text for p in parts for h in p.heads[0]] == [f"S{i}" for i in range(n)]
    assert [p.title for p in parts] == ["title"] + [""] * (len(parts) - 1)
    first_row = [b.text for p in parts for b in p.lines[0].boxes]
    assert first_row == [f"0.{c}" for c in range(n)]  # nothing lost, nothing repeated
    assert all(p.lines[2].kind == "section" and p.lines[2].boxes == [] for p in parts)
    assert all(p.label_header == "label" and len(p.lines) == 3 for p in parts)


def test_F9c_split_keeps_the_three_columns_of_a_scenario_together() -> None:
    parts = split(_grid(4, columns=3), 3)  # the cash flow: three columns under each scenario
    assert [p.width for p in parts] == [6, 6]
    assert [[h.text for h in p.heads[1]] for p in parts] == [
        [f"c{i}" for i in range(6)],
        [f"c{i}" for i in range(6, 12)],
    ]
    assert [b.text for b in parts[1].lines[0].boxes] == [f"0.{c}" for c in range(6, 12)]
    assert [h.span for h in parts[1].heads[0]] == [3, 3]


def test_F9c_split_leaves_a_table_that_is_not_by_scenario_alone() -> None:
    g = _grid(8, coloured=False)  # heads without a scenario colour: ABC classes, series, ...
    assert split(g, 3) == [g]


# ------------------------------------------------------------------ the page fit loop
def _html_of(pages: int) -> str:
    return (
        "<html><body>"
        + '<p style="break-after: page">x</p>' * (pages - 1)
        + "<p>x</p></body></html>"
    )


def test_F9c_fit_pdf_takes_the_loosest_typesetting_within_the_budget() -> None:
    asked: list[int] = []

    def html_at(level: int) -> str:
        asked.append(level)
        return _html_of(MAX_PAGES + 2 - 2 * level)  # 20, 18, 16 pages

    assert len(PdfReader(io.BytesIO(fit_pdf(html_at))).pages) == MAX_PAGES
    assert asked == [0, 1]  # level 1 fits: level 2 is never rendered


def test_F9c_fit_pdf_keeps_the_tightest_and_logs_when_nothing_fits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        pdf = fit_pdf(lambda level: _html_of(MAX_PAGES + 5 - level), n_scenarios=9)
    assert len(PdfReader(io.BytesIO(pdf)).pages) == MAX_PAGES + 5 - COMPACT_LEVELS
    assert "report_over_page_budget" in caplog.text


# ------------------------------------------------------------------ files written
def test_F9c_a_report_folder_that_cannot_be_written_is_a_whsizing_error(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    run = own_run(tmp_path_factory, "f9c_unwritable")
    report = Path(run.run_dir) / "report"
    report.write_text("a file where the folder should be")
    with pytest.raises(WhsizingError, match="cannot write") as err:
        build_pdf(run, "en")
    assert not isinstance(err.value, OSError)
    assert report.is_file()  # nothing was replaced
