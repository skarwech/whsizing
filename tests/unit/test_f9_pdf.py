"""F9c PDF report on a real small run (F1 data, F2-F8, sensitivity on; copied to its own folder):
T9.3 (pages and run id), T9.5 (FR and EN print the same numbers), the integrity gate (a failed
check writes no file), the edge cases (scenario not computed, no baseline, unsupported language)
and the done-when of F9: three Summary numbers recomputed from Appendix C of the PDF."""

from __future__ import annotations

import dataclasses
import io
import json
import re
import shutil
from pathlib import Path

import pytest
from markupsafe import escape
from pypdf import PdfReader
from tests.unit.test_f9_pdf_support import (
    APPENDIX_C_MIN_PT,
    DIAGRAM_MIN_PT,
    RIGHT_EDGE_PT,
    appendix_c_sizes,
    diagram_label_sizes,
    html_numbers,
    own_run,
    parse_number,
    pdf_pages,
    plain,
    printed_value_and_inputs,
    squash,
    text_starts,
    trace_entry,
    without_baseline,
    without_scenario,
)
from tests.unit.test_f9_tables_support import report_data, small_run

from whsizing.errors import ConfigError, ReportIntegrityError
from whsizing.report import data as report_data_module
from whsizing.report import export_trace, load_report_data, render_cell, t
from whsizing.report.i18n import Lang
from whsizing.report.pdf import STYLES, _css_str, build_pdf, fit_pdf, render_html  # pyright: ignore[reportPrivateUsage]
from whsizing.report.pdf_text import caveats, trace_number
from whsizing.schemas import Cell
from whsizing.schemas.run import RunOutput

pytestmark = pytest.mark.pdf
LANGS: tuple[Lang, ...] = ("fr", "en")
SECTION_KEYS = (
    "pdf.section.executive_summary",
    "pdf.section.data_demand",
    "pdf.section.basis_design_day",
    "pdf.section.scenarios",
    "pdf.section.results",
    "pdf.section.business_case",
    "pdf.section.sensitivity",
    "pdf.section.risks",
    "pdf.section.appendix_assumptions",
    "pdf.section.appendix_dq",
    "pdf.section.appendix_methodology",
)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return own_run(tmp_path_factory, "f9c_pdf")


@pytest.fixture(scope="module")
def pdfs(run: RunOutput) -> dict[Lang, Path]:
    return {lang: build_pdf(run, lang) for lang in LANGS}


@pytest.fixture(scope="module")
def htmls(run: RunOutput) -> dict[Lang, str]:
    return {lang: render_html(load_report_data(run, lang)) for lang in LANGS}


# ------------------------------------------------------------------ T9.3
@pytest.mark.parametrize("lang", LANGS)
def test_T9_3_pdf_has_at_least_12_pages_and_the_run_id_on_each(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    pages = pdf_pages(pdfs[lang])
    assert pdfs[lang] == run.run_dir / "report" / f"report_{lang}.pdf"
    assert 12 <= len(pages) <= 18
    assert run.manifest.run_id in "\n".join(pages)
    assert all(run.manifest.run_id in p for p in pages)  # the running footer
    assert all(f"{i} / {len(pages)}" in p for i, p in enumerate(pages, 1))  # page numbers


@pytest.mark.parametrize("lang", LANGS)
def test_T9_3_sections_0_to_8_and_appendices_come_in_the_spec_order(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    pages = [squash(p) for p in pdf_pages(pdfs[lang])]
    cover = pages[0]
    data = report_data(run, lang)
    assert t("pdf.title", lang) in cover and data.basis.client in cover and data.basis.site in cover
    assert render_cell(data.tables["summary"].notes[0], lang) in cover  # the indicative banner
    study = {r.key: r for r in data.tables["summary"].blocks[0].rows}
    assert render_cell(study["dq_band"].cells[0], lang) in cover
    assert str(study["run_id"].cells[0].value) in cover
    body = " ".join(pages[1:])  # the table of contents of the cover has the titles too
    at = [body.index(t(key, lang)) for key in SECTION_KEYS]
    assert at == sorted(at)


def test_T9_3_the_cover_dates_follow_the_language(run: RunOutput, pdfs: dict[Lang, Path]) -> None:
    day = run.manifest.created_at.date()
    assert day.strftime("%d/%m/%Y") in pdf_pages(pdfs["fr"])[0]
    assert day.isoformat() in pdf_pages(pdfs["en"])[0]


# ------------------------------------------------------------------ page layout
@pytest.mark.parametrize("lang", LANGS)
def test_I88_annex_a_prints_the_value_each_scenario_was_sized_with(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """M3: the PDF line of amr_gtp.station_rate_lines_h read 250 although S1 was sized at 230.
    Every Annex A line starts with the base value of the manifest's params_snapshot and ends with
    the `<scenario>:<id>` value of each override, in the language of the report."""
    snap = run.manifest.params_snapshot
    params = report_data(run, lang).catalog.params

    def shown(value: float, pid: str) -> str:
        return squash(render_cell(Cell(value=value, fmt="num", unit=params[pid].unit), lang))

    lines = {
        words[0]: line
        for page in pdf_pages(pdfs[lang])
        for line in map(squash, page.split("\n"))
        if (words := line.split(" "))[0] in params
    }
    assert set(lines) == set(params)  # one line per Param, 72 of them
    for pid, line in lines.items():
        assert line.startswith(f"{pid} {shown(snap[pid], pid)} "), line
    overrides = {k.partition(":")[::2]: v for k, v in snap.items() if ":" in k}
    assert overrides == {("S1", "amr_gtp.station_rate_lines_h"): 230.0}
    for (sid, pid), value in overrides.items():
        assert snap[pid] != value
        assert lines[pid].endswith(f" {shown(value, pid)}"), (sid, lines[pid])
    note = squash(t("assumptions.scenario_columns", lang, scenarios="S1"))
    pages = [squash(p) for p in pdf_pages(pdfs[lang])]
    assert any(note in page for page in pages)  # under the table: what the S1 column is
    annex = [page for page in pages if "amr_gtp.station_rate_lines_h" in page]
    assert annex and all(" Origin S1 " in p or " Origine S1 " in p for p in annex)  # its header


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_the_executive_summary_is_exactly_one_page(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """Section 1 (table, key messages, caveats) fills page 2 and section 2 starts page 3."""
    pages = [squash(p) for p in pdf_pages(pdfs[lang])]
    data = report_data(run, lang)
    last_caveat = squash(caveats(data)[-1])  # the end of the summary
    assert t("pdf.section.executive_summary", lang) in pages[1]
    assert t("pdf.s1.messages", lang) in pages[1] and last_caveat in pages[1]
    assert t("pdf.section.data_demand", lang) not in pages[1]
    assert t("pdf.section.data_demand", lang) in pages[2]


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_no_text_runs_beyond_the_right_margin(pdfs: dict[Lang, Path], lang: Lang) -> None:
    """No table or figure caption is clipped at the A4 edge (the ABC tables of section 2 were,
    in French): every text run starts inside the 18 mm margin."""
    off = [(n, round(x), s[:30]) for n, x, s in text_starts(pdfs[lang]) if x > RIGHT_EDGE_PT + 1]
    assert not off, off[:8]


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_diagram_labels_and_appendix_c_are_set_at_legible_sizes(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """The floors the tighter typesettings of a larger study must keep (test_f9_pdf_many.py)."""
    assert min(diagram_label_sizes(pdfs[lang], lang, list(run.results))) >= DIAGRAM_MIN_PT
    runs = appendix_c_sizes(pdfs[lang], lang)
    assert min(s for _, s, _ in runs) >= APPENDIX_C_MIN_PT


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_the_cover_has_no_running_header_and_the_other_pages_have_it(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    data = report_data(run, lang)
    pages = [squash(p) for p in pdf_pages(pdfs[lang])]
    header_left = f"{data.basis.client} · {data.basis.site}"
    assert pages[0].count(header_left) == 1  # the subtitle only
    assert t("pdf.header.indicative", lang) not in pages[0]
    assert all(header_left in p and t("pdf.header.indicative", lang) in p for p in pages[1:])


@pytest.mark.parametrize(
    ("raw", "visible"),
    [
        ("Acme\rCorp", "Acme Corp"),
        ("Acme\fCorp", "Acme Corp"),
        ("Acme\nCorp", "Acme Corp"),
        ('Say "hi" <b>', 'Say "hi" <b>'),
    ],
)
def test_R8c_css_string_has_no_raw_newline_so_the_margin_text_survives(
    raw: str, visible: str
) -> None:
    """A CR or FF in a CSS string ends it like LF does: the running header was silently dropped
    from every page. WeasyPrint must still draw the cleaned text in the margin box."""
    from weasyprint import HTML  # lazy: needs Pango

    out = str(_css_str(raw))
    assert not re.search(r"[\r\n\f]", out)
    html = f'<style>@page {{ @top-left {{ content: "{out}"; }} }}</style><p>body</p>'
    pdf = HTML(string=html).write_pdf()
    assert pdf is not None
    assert visible in squash(PdfReader(io.BytesIO(pdf)).pages[0].extract_text())


def test_R8c_a_client_name_with_a_cr_keeps_the_running_header_on_every_page(
    run: RunOutput,
) -> None:
    data = report_data(run, "en")
    named = dataclasses.replace(
        data, basis=data.basis.model_copy(update={"client": "Acme\rIndustries SA"})
    )
    html = render_html(named)
    pages = [squash(p.extract_text()) for p in PdfReader(io.BytesIO(fit_pdf(lambda _: html))).pages]
    assert len(pages) >= 12
    header = t("pdf.header.indicative", "en")
    assert all("Acme Industries SA" in p and header in p for p in pages[1:])


@pytest.mark.parametrize("control", ["\f", "\v", "\x00", "\x1b", "\r", "\n", "\t"])
def test_R8c_a_control_character_in_the_client_or_site_name_is_a_space_in_the_whole_report(
    run: RunOutput, monkeypatch: pytest.MonkeyPatch, control: str
) -> None:
    """A form feed in the HTML body (the cover subtitle) turned the text layer of that page into
    NUL-spaced characters. `load_report_data` reads the names through `printable`, so the cover,
    the tables and the running header all carry the plain text."""
    real = report_data_module.load_basis
    monkeypatch.setattr(
        report_data_module,
        "load_basis",
        lambda path: real(path).model_copy(
            update={"client": f"Acme{control}Corp", "site": f"Lyon{control}Nord"}
        ),
    )
    data = load_report_data(run, "en")
    assert (data.basis.client, data.basis.site) == ("Acme Corp", "Lyon Nord")
    html = render_html(data)
    assert not re.search(r"[\x00-\x08\x0b-\x1f]", html)
    pages = [squash(p.extract_text()) for p in PdfReader(io.BytesIO(fit_pdf(lambda _: html))).pages]
    assert "Acme Corp" in pages[0] and "Lyon Nord" in pages[0]
    assert "\x00" not in "".join(pages)  # the garbled text layer
    assert all("Acme Corp · Lyon Nord" in p for p in pages[1:])


def _renamed(run: RunOutput, name: str) -> RunOutput:
    """`run` with the name of every scenario set to `name` (it is free text of scenarios.yaml)."""
    results = {
        sid: r.model_copy(update={"scenario": r.scenario.model_copy(update={"name": name})})
        for sid, r in run.results.items()
    }
    return run.model_copy(update={"results": results})


@pytest.mark.parametrize("control", ["\f", "\v", "\x00", "\x1b", "\u2028", "\u2029"])
def test_R8c_a_control_character_in_a_scenario_name_keeps_the_text_layer_of_every_page(
    run: RunOutput, control: str
) -> None:
    """The names are not read through `printable` in `load_report_data`: the sanitiser sits at the
    template output, so a scenario name (any free text) cannot garble the page it is printed on."""
    data = load_report_data(_renamed(run, f"Manu{control}elle"), "en")
    html = render_html(data)
    assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u2028\u2029]", html)
    pages = [squash(p.extract_text()) for p in PdfReader(io.BytesIO(fit_pdf(lambda _: html))).pages]
    assert "\x00" not in "".join(pages)  # the garbled text layer
    assert "Manu elle" in "".join(pages)


def test_R8c_bidi_overrides_in_the_client_name_are_dropped_and_the_formulas_keep_their_lines(
    run: RunOutput, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = report_data_module.load_basis
    monkeypatch.setattr(
        report_data_module,
        "load_basis",
        lambda path: real(path).model_copy(update={"client": "Acme\u202eCorp\u2028SA"}),
    )
    data = load_report_data(run, "en")
    assert data.basis.client == "AcmeCorp SA"
    appendix = render_html(data)
    pre = re.search(r'<pre class="formulas">(.*?)</pre>', appendix, re.S)
    assert pre is not None and pre.group(1).count("\n") >= 3  # line breaks of <pre> survive


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_the_running_footer_is_in_the_language_of_the_report(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    engine = f"{t('pdf.footer.engine', lang)} {run.manifest.engine_version}"
    pages = pdf_pages(pdfs[lang])
    assert all(f"{run.manifest.run_id} · {engine}" in squash(p) for p in pages)
    footers = [[ln for ln in p.splitlines() if run.manifest.run_id in ln][-1] for p in pages]
    assert all(("engine" in f) == (lang == "en") for f in footers)  # no English word in French


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_appendix_c_formulas_are_titled_without_a_wrong_appendix_letter(
    htmls: dict[Lang, str], lang: Lang
) -> None:
    html = htmls[lang]
    appendix = html[html.index('id="app_c"') :]
    assert f"<h3>{t('pdf.appc.formulas', lang)}</h3>" in appendix
    assert "(Appendix B" not in html and "(annexe B" not in html  # B is the data-quality report


@pytest.mark.parametrize("lang", LANGS)
def test_R7_3_the_pdf_prints_the_formulas_and_the_raised_flags_in_its_own_language(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """Appendix C formulas and the flags of the generated limitations of section 8: French in the
    French PDF (the F4/DQ/F7 notes the pipeline wrote stay as they are, I79 h)."""
    from whsizing.report.i18n import flag_text

    text = squash("\n".join(pdf_pages(pdfs[lang])))
    other: Lang = "en" if lang == "fr" else "fr"
    assert squash(t("methodology.formulas", lang).splitlines()[1]) in text  # the first formula
    assert t("methodology.formulas", other).splitlines()[1] not in text
    data = report_data(run, lang)
    raised = {f.code for r in data.run.results.values() for f in r.flags if f.severity != "info"}
    assert raised
    for code in raised:
        assert flag_text(code, lang) in text, code
    assert not re.search(r"\bF_[A-Z_]+:?\w*(?=[,.;])", text)  # no raw code in a sentence


@pytest.mark.parametrize("lang", LANGS)
def test_F9c_the_limitations_box_of_section_8_is_not_split_across_pages(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    pages = [squash(p) for p in pdf_pages(pdfs[lang])]
    heading = next(i for i, p in enumerate(pages[1:], 1) if t("pdf.section.risks", lang) in p)
    for key in ("pdf.s8.fixed", "pdf.s8.generated"):
        assert t(key, lang) in pages[heading]  # heading, fixed and generated items together


def test_F9c_the_limitations_box_is_drawn(htmls: dict[Lang, str]) -> None:
    css = STYLES.read_text()
    assert '<div class="limits">' in htmls["en"]
    assert re.search(r"\.limits \{[^}]*border:[^}]*background:", css)  # a box, not bare lists


def test_F9c_trace_numbers_print_counts_as_whole_numbers() -> None:
    assert trace_number(2.0, "en") == "2" and trace_number(30.0, "fr") == "30"
    assert trace_number(0.0, "en") == "0"
    assert trace_number(42.64, "en") == "42.64" and trace_number(42.64, "fr") == "42,64"
    assert trace_number(0.08, "en") == "0.0800"


def test_F9c_the_warnings_count_of_appendix_c_has_no_decimals(htmls: dict[Lang, str]) -> None:
    row = re.search(
        r'<td class="id">S1\.report\.n_warnings.*?<td class="r">(.*?)</td>', htmls["en"], re.S
    )
    assert row is not None and re.fullmatch(r"\d+", row.group(1).strip())


# ------------------------------------------------------------------ T9.5
def test_T9_5_fr_and_en_render_the_same_numbers(htmls: dict[Lang, str]) -> None:
    fr, en = html_numbers(htmls["fr"], "fr"), html_numbers(htmls["en"], "en")
    assert len(fr) == len(en) > 400
    assert fr == en  # every table cell, typical value and range, parsed back through its locale


def test_T9_5_summary_cells_parse_back_to_the_raw_values(
    run: RunOutput, htmls: dict[Lang, str]
) -> None:
    """The comparison table of section 1, parsed back through the locale parser, holds the raw
    typical-value Cells of the report model to the precision of their format, in FR and EN."""
    decimals = {"int": 0, "eur": 0, "dec1": 1, "dec2": 2, "pct": 1, "bool": 0}
    for lang in LANGS:
        block = report_data(run, lang).tables["summary"].blocks[1]
        wanted = [  # (raw value as printed, tolerance): a share is printed in percent
            (100 * c.value if c.fmt == "pct" else float(c.value), 0.5 * 10 ** -decimals[c.fmt])
            for row in block.rows
            for c in row.cells
            if c.world == "typ" and isinstance(c.value, float)
        ]
        html = htmls[lang]
        section = html[html.index('id="summary"') : html.index('id="data"')]
        printed = [v for v, _ in html_numbers(section, lang)]
        assert len(printed) == len(wanted) > 50
        for got, (raw, tol) in zip(printed, wanted, strict=True):
            assert got == pytest.approx(raw, abs=tol + 1e-9)


@pytest.mark.parametrize("lang", LANGS)
def test_T9_5_the_pdf_text_holds_the_summary_numbers_of_its_language(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """Every number of the Summary table, printed by the language formatter, is in the text of
    the Summary page of that language's PDF; its parsed value is the raw Cell value."""
    data = report_data(run, lang)
    page = pdf_pages(pdfs[lang])[1]
    block = data.tables["summary"].blocks[1]
    checked = 0
    for row in block.rows:
        for cell in row.cells:
            if not isinstance(cell.value, float) or cell.fmt in ("bool", "pct"):
                continue
            text = plain(render_cell(cell, lang))
            assert text in page, (lang, row.key, text)
            decimals = {"int": 0, "eur": 0, "dec1": 1, "dec2": 2}.get(cell.fmt)
            if decimals is not None:
                assert parse_number(text, lang) == pytest.approx(
                    cell.value, abs=0.5 * 10**-decimals
                )
            checked += 1
    assert checked > 100


def test_T9_5_french_html_uses_the_french_separators(htmls: dict[Lang, str]) -> None:
    fr, en = htmls["fr"], htmls["en"]
    assert re.search(r"\d \d{3},\d", fr) or re.search(r"\d \d{3}<", fr)  # U+202F, comma
    assert not re.search(r"\d,\d{3}\.\d", fr) and re.search(r"\d,\d{3}", en)
    assert "{{ missing" not in fr and "{{ missing" not in en  # IC8


# ------------------------------------------------------------------ generated text and images
@pytest.mark.parametrize("lang", LANGS)
def test_F9c_key_messages_have_no_recommended_label_and_carry_the_overlap_note(
    run: RunOutput, htmls: dict[Lang, str], lang: Lang
) -> None:
    data = report_data(run, lang)
    note = render_cell(data.tables["summary"].notes[1], lang)
    html = htmls[lang]
    assert run.comparison.overlaps  # this run has overlapping TCO ranges: the note names the pairs
    assert " – ".join(run.comparison.overlaps[0]) in note
    messages = re.findall(r'<ul class="msg">(.*?)</ul>', html, re.DOTALL)[0]
    assert messages.count("<li>") == 3
    assert str(escape(note)) in messages  # the ranking sentence carries the overlap note
    assert " &lt; ".join(run.comparison.ranking_tco) in messages
    assert not re.search(r"recommend|recommand", html, re.IGNORECASE)


def test_F9c_every_chart_and_diagram_has_an_alt_with_the_source_note(
    run: RunOutput, htmls: dict[Lang, str]
) -> None:
    data = report_data(run, "en")
    imgs = re.findall(r'<img src="data:(image/[a-z+]+);base64,[^"]+" alt="([^"]*)"', htmls["en"])
    assert sum(m == "image/png" for m, _ in imgs) == 9  # no sweep chart: its table is shown
    assert sum(m == "image/svg+xml" for m, _ in imgs) == len(data.computed())
    assert all(data.source_note.replace("&", "&amp;") in alt for _, alt in imgs)


def test_F9c_the_appendix_c_trace_index_lists_every_summary_number(
    run: RunOutput, htmls: dict[Lang, str]
) -> None:
    data = report_data(run, "en")
    summary = data.tables["summary"].blocks[1]
    html = htmls["en"]
    for sid in data.computed():
        ids = {
            c.trace_id
            for row in summary.rows
            for col, c in zip(summary.columns, row.cells, strict=True)
            if col.scenario_id == sid and col.world == "typ" and c.trace_id
        }
        assert len(ids) >= 15
        assert all(f'<td class="id">{i}' in html for i in ids), sid
    assert "data:basis.finance.discount_rate (0.0800)" in html  # a dataset leaf with its value
    assert "param:" in html and "30 catalog parameters" in html  # a long parameter list: counted


# ------------------------------------------------------------------ done-when: three numbers
@pytest.mark.parametrize("lang", LANGS)
def test_T9_5_three_summary_numbers_are_reproduced_from_appendix_c(
    run: RunOutput, pdfs: dict[Lang, Path], lang: Lang
) -> None:
    """A reader other than the author: for each scenario the total area, the TCO and the design-day
    heads are found in the Summary page, their trace ids in Appendix C, and each is recomputed from
    the formula and the inputs printed there (sum of zones, capex + discounted opex, sum of
    activities)."""
    data = report_data(run, lang)
    pages = pdf_pages(pdfs[lang])
    summary_page, appendix = pages[1], "\n".join(pages)
    block = data.tables["summary"].blocks[1]
    rows = {r.key: r for r in block.rows}
    for sid in data.computed():
        col = next(
            i for i, c in enumerate(block.columns) if c.scenario_id == sid and c.world == "typ"
        )
        for row_key, trace_key, tol in (
            ("total_area", "area.total", 0.06),
            ("fte_design_day", "labor.total.heads", 0.1),
            ("tco", "finance.tco", 0.1),
        ):
            cell = rows[row_key].cells[col]
            assert cell.trace_id == f"{sid}.{trace_key}"
            assert cell.trace_id is not None
            assert (
                plain(render_cell(cell, lang)) in summary_page
            )  # the number as the reader sees it
            value, inputs = printed_value_and_inputs(trace_entry(appendix, cell.trace_id), lang)
            if trace_key == "finance.tco":  # capex + Σ_t opex_t / (1 + r)^t
                capex, *opex, rate = inputs
                recomputed = capex + sum(o / (1 + rate) ** t for t, o in enumerate(opex, 1))
            else:  # Σ zones (circulation included), Σ activities
                recomputed = sum(inputs)
            assert recomputed == pytest.approx(value, abs=tol), (sid, trace_key)
            assert value == pytest.approx(float(cell.value), abs=0.006), (sid, trace_key)  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ files written
def test_F9c_build_writes_the_pdf_the_trace_and_the_diagrams(
    run: RunOutput, pdfs: dict[Lang, Path], tmp_path: Path
) -> None:
    report = run.run_dir / "report"
    assert sorted(p.name for p in report.iterdir()) == [
        "diagram_S0.svg",
        "diagram_S1.svg",
        "diagram_S2.svg",
        "report_en.pdf",
        "report_fr.pdf",
        "trace.jsonl",
    ]
    exported = {
        json.loads(line)["id"] for line in (report / "trace.jsonl").read_text().splitlines()
    }
    data = report_data(run, "en")
    assert {n.id for tr in data.tracers.values() for n in tr.nodes} <= exported
    assert "S1.report.n_warnings" in exported  # the node the Summary cites (I79 d, i)
    assert (report / "trace.jsonl").read_bytes() == export_trace(
        data, tmp_path / "again.jsonl"
    ).read_bytes()  # the trace is reproducible: the same run gives the same bytes


def test_R7_4_the_pdfs_are_built_in_a_private_copy_of_the_shared_run(
    run: RunOutput, pdfs: dict[Lang, Path], tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Another module builds workbooks into its own copy: the shared small run stays without a
    `report/` whatever the order of the modules (the file list above is exact)."""
    shared = Path(small_run(tmp_path_factory).run_dir)
    assert Path(run.run_dir) != shared
    assert all(shared not in p.parents for p in pdfs.values())
    assert not list((shared / "report").glob("*"))  # the runner makes the folder, empty


# ------------------------------------------------------------------ the integrity gate
def tampered_copy(run: RunOutput, tmp_path: Path) -> RunOutput:
    """A copy of the run whose S1 trace says the capex total is twice what the tables show."""
    dst = tmp_path / "run"
    shutil.copytree(run.run_dir, dst, ignore=shutil.ignore_patterns("report"))
    path = dst / "scenarios" / "S1" / "trace.jsonl"
    lines = []
    for line in path.read_text().splitlines():
        node = json.loads(line)
        if node["id"] == "S1.capex.total" and node["world"] == "typ":
            node["value"] *= 2
        lines.append(json.dumps(node))
    path.write_text("\n".join(lines) + "\n")
    return run.model_copy(update={"run_dir": dst})


def test_F9c_a_failed_integrity_check_raises_exit_5_and_writes_no_file(
    run: RunOutput, tmp_path: Path
) -> None:
    bad = tampered_copy(run, tmp_path)
    with pytest.raises(ReportIntegrityError, match="IC1") as err:
        build_pdf(bad, "en")
    assert err.value.exit_code == 5
    assert not (bad.run_dir / "report").exists()  # no PDF, no trace, no diagram


def test_F9c_an_untranslated_text_in_the_rendered_html_fails_ic8_and_writes_no_file(
    run: RunOutput, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from whsizing.report import i18n

    dst = tmp_path / "run"
    shutil.copytree(run.run_dir, dst, ignore=shutil.ignore_patterns("report"))
    ok = run.model_copy(update={"run_dir": dst})
    real = i18n.texts
    monkeypatch.setattr(
        i18n, "texts", lambda lang: {k: v for k, v in real(lang).items() if k != "pdf.s1.caveats"}
    )
    with pytest.raises(ReportIntegrityError, match="IC8") as err:
        build_pdf(ok, "en")
    assert "pdf.s1.caveats" in str(err.value)
    assert not (dst / "report").exists()


def test_F9c_an_unsupported_language_is_a_clear_config_error(run: RunOutput) -> None:
    with pytest.raises(ConfigError, match="unsupported language 'de'"):
        build_pdf(run, "de")  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ edge cases
def test_F9c_a_scenario_not_computed_is_greyed_with_its_reason(
    run: RunOutput, tmp_path: Path
) -> None:
    dst = tmp_path / "run"
    shutil.copytree(run.run_dir, dst, ignore=shutil.ignore_patterns("report"))
    reason = "SizingInfeasibleError: the cube does not fit"
    nc = without_scenario(run.model_copy(update={"run_dir": dst}), "S1", reason)
    html = render_html(load_report_data(nc, "en"))
    assert html.count(f"Not computed: {reason}") >= 3  # section 1, 4 and the tables of 5 and 6
    assert 'class="scen off"' in html  # section 4: the paragraph is greyed
    assert 'class="off"' in html and "S1 · AMR goods-to-person" in html
    out = build_pdf(nc, "en")  # the other scenarios are reported, nothing fails
    text = "\n".join(pdf_pages(out))
    assert reason in text and len(PdfReader(out).pages) >= 12
    assert not (dst / "report" / "diagram_S1.svg").exists()
    assert "S1.finance.tco" not in text and "S2.finance.tco" in text  # no trace of S1 in App. C


def test_F9c_without_a_baseline_the_business_case_shows_absolute_values_only(
    run: RunOutput, tmp_path: Path
) -> None:
    dst = tmp_path / "run"
    shutil.copytree(run.run_dir, dst, ignore=shutil.ignore_patterns("report"))
    nb = without_baseline(run.model_copy(update={"run_dir": dst}))
    data = load_report_data(nb, "en")
    html = render_html(data)
    assert "NPV vs baseline" not in html and "Payback (years)" not in html
    assert "No baseline was given" in html  # the message and the generated limitation
    assert "TCO (€)" in html and "Cost per line (€)" in html  # absolute values remain
    assert len(PdfReader(build_pdf(nb, "en")).pages) >= 12
    fr = render_html(load_report_data(nb, "fr"))
    assert "Aucune référence" in fr and "{{ missing" not in fr


def test_F9c_the_html_is_built_from_the_model_not_from_a_recomputation(
    run: RunOutput, htmls: dict[Lang, str]
) -> None:
    """Change a raw Cell of the model and the section 1 table prints that number: the renderer
    keeps no number of its own."""
    data = load_report_data(run, "en")
    summary = data.tables["summary"]
    block = summary.blocks[1]
    rows = [
        r.model_copy(update={"cells": [c.model_copy(update={"value": 777.0}) for c in r.cells]})
        if r.key == "capex"
        else r
        for r in block.rows
    ]
    blocks = [summary.blocks[0], block.model_copy(update={"rows": rows}), summary.blocks[2]]
    changed = dataclasses.replace(
        data, tables={**data.tables, "summary": summary.model_copy(update={"blocks": blocks})}
    )
    html = render_html(changed)
    assert html.count('<td class="r">777</td>') == 3  # one per scenario, in section 1 only
    assert '<td class="r">777</td>' not in htmls["en"]


def test_F9c_a_client_name_with_markup_cannot_break_the_running_header(run: RunOutput) -> None:
    data = load_report_data(run, "en")
    name = 'A & B "C" </style><b>x</b>'
    changed = dataclasses.replace(data, basis=data.basis.model_copy(update={"client": name}))
    html = render_html(changed)
    style = html[html.index("<style>") : html.index("</style>")]  # the real end of the header CSS
    assert "<b>" not in style and "\\3c /style" in style  # CSS-escaped, cannot close the element
    assert 'A & B \\"C\\"' in style  # the quote is escaped for the CSS string, '&' is not doubled
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html  # the body is HTML-escaped


def test_F9c_each_scenario_has_its_chart_colour_in_the_tables_and_descriptions(
    run: RunOutput, htmls: dict[Lang, str]
) -> None:
    from whsizing.report.style import scenario_colours

    html = htmls["en"]
    colours = scenario_colours(run.results)
    assert len(set(colours.values())) == len(colours) == 3
    for colour in colours.values():
        assert f'style="border-top: 2.5pt solid {colour}"' in html  # table header rule
        assert f'style="border-left: 2.5pt solid {colour}"' in html  # section 4 paragraph
