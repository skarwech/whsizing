"""PDF report (F9c): Jinja2 templates + styles.css → WeasyPrint, from the F9a report model.

    build_pdf(run, "fr")      # <run>/report/report_fr.pdf (+ trace.jsonl, diagram_<scenario>.svg)
    render_html(data)         # the HTML the PDF is made of (integrity check IC8 reads it)

A4 portrait, sections 0-8 and appendices A-C (see `templates/`). Numbers are never recomputed:
the tables are the `ReportTable`s of `load_report_data`, printed by `render_cell` (FR: U+202F
thousands, decimal comma, dd/mm/yyyy; EN: comma thousands, decimal point, yyyy-mm-dd).
`build_pdf` renders the HTML, runs `assert_integrity` (IC1-IC8, exit 5) BEFORE anything is
written, then writes the PDF, `report/trace.jsonl` (I79 i) and the block diagrams. The PDF is
set loosely when it fits in 18 pages and tighter (`fit_pdf`) when the study has many scenarios.
`render_stub_pdf` is the F0 walking skeleton (T0.5), kept as it was.
"""

from __future__ import annotations

import base64
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from whsizing import __version__
from whsizing.errors import WhsizingError
from whsizing.logging import get_logger
from whsizing.report.charts import CHART_IDS, chart_png
from whsizing.report.data import ReportData, export_trace, load_report_data, printable
from whsizing.report.diagram import build_diagrams
from whsizing.report.i18n import Lang, render_cell, t
from whsizing.report.integrity import assert_integrity
from whsizing.report.pdf_text import (
    block_of,
    break_even_sentences,
    caveats,
    key_messages,
    limits,
    scenario_texts,
    trace_index,
)
from whsizing.report.pdf_view import Grid, box, grid, split
from whsizing.report.style import scenario_colours
from whsizing.schemas import ScenarioResult, TableRow
from whsizing.schemas.run import RunOutput

_HERE = Path(__file__).parent
TEMPLATES = _HERE / "templates"
STYLES = _HERE / "styles.css"
MAX_PAGES = 18  # spec: A4 portrait, 12-18 pages
COMPACT_LEVELS = 2  # tighter typesettings of styles.css (.compact, .compact2) for many scenarios
MAX_TEXT_CHARS = 80  # a design-basis value longer than this (a JSON dict) is left to the Excel
OPEX_DETAIL_YEAR = "opex.y1"  # the opex table lists the items of year 1, the totals of the others
# (id, i18n key, number) of the sections of the spec; the appendices carry their letter in the key
SECTIONS = (
    ("summary", "pdf.section.executive_summary", "1"),
    ("data", "pdf.section.data_demand", "2"),
    ("basis", "pdf.section.basis_design_day", "3"),
    ("scenarios", "pdf.section.scenarios", "4"),
    ("results", "pdf.section.results", "5"),
    ("business", "pdf.section.business_case", "6"),
    ("sensitivity", "pdf.section.sensitivity", "7"),
    ("risks", "pdf.section.risks", "8"),
    ("app_a", "pdf.section.appendix_assumptions", ""),
    ("app_b", "pdf.section.appendix_dq", ""),
    ("app_c", "pdf.section.appendix_methodology", ""),
)


@dataclass(frozen=True)
class Figure:
    uri: str  # data: URI, so the HTML is self-contained
    alt: str


def render_stub_pdf(result: ScenarioResult, out: Path) -> Path:
    """Render one ScenarioResult as a one-page PDF (walking skeleton, T0.5)."""
    from weasyprint import CSS, HTML  # lazy: needs Pango at runtime

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
    )
    html = env.get_template("stub.html.j2").render(r=result, version=__version__)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(_HERE)).write_pdf(out, stylesheets=[CSS(filename=str(STYLES))])
    return out


def build_pdf(run: RunOutput, lang: Lang) -> Path:
    """`<run>/report/report_<lang>.pdf`. A failed integrity check raises `ReportIntegrityError`
    (exit 5) and nothing is written to the run folder; an unsupported language is a
    `ConfigError`, a file that cannot be written a `WhsizingError`."""
    data = load_report_data(run, lang)
    with tempfile.TemporaryDirectory() as tmp:
        svgs = build_diagrams(data, Path(tmp))
        ctx = _context(data, svgs)
        # the gate, before any file is written; the tighter typesettings print the same numbers
        assert_integrity(run, _page(lang, ctx, 0), data=data)
        pdf = fit_pdf(lambda level: _page(lang, ctx, level), len(data.run.results))
        return _write(data, svgs, pdf)


def _write(data: ReportData, svgs: dict[str, Path], pdf: bytes) -> Path:
    """The files of a build: the trace and the diagrams first, the PDF last, so that a PDF in the
    report folder means every file was written."""
    report = Path(data.run.run_dir) / "report"
    out = report / f"report_{data.lang}.pdf"
    try:
        report.mkdir(parents=True, exist_ok=True)
        export_trace(data, report / "trace.jsonl")
        for path in svgs.values():
            shutil.copy2(path, report / path.name)
        out.write_bytes(pdf)
    except OSError as e:
        raise WhsizingError(f"report: cannot write {out}: {e}") from e
    return out


def fit_pdf(html_at: Callable[[int], str], n_scenarios: int = 0) -> bytes:
    """The PDF at the loosest of the typesettings `html_at(0..COMPACT_LEVELS)` (styles.css,
    `.compact`, `.compact .compact2`) that has at most MAX_PAGES pages: a study of the three example
    scenarios is 17 pages as it is, one of four is set tighter. The diagrams and Appendix C keep
    their sizes at every level, so a larger study keeps the tightest typesetting, is longer than
    MAX_PAGES and the overrun is logged."""
    from weasyprint import CSS, HTML  # lazy: needs Pango at runtime

    css = CSS(filename=str(STYLES))
    for level in range(COMPACT_LEVELS + 1):
        doc = HTML(string=html_at(level), base_url=str(_HERE)).render(stylesheets=[css])
        if len(doc.pages) <= MAX_PAGES:
            break
    else:
        get_logger().warning(
            "report_over_page_budget", pages=len(doc.pages), max=MAX_PAGES, scenarios=n_scenarios
        )
    pdf = doc.write_pdf()
    if pdf is None:  # write_pdf returns the bytes when it is given no target
        raise WhsizingError("report: WeasyPrint produced no PDF")
    return pdf


def render_html(data: ReportData, diagrams: dict[str, Path] | None = None, compact: int = 0) -> str:
    """The report as one HTML document (images inline). `diagrams`: the block diagram SVG of
    each computed scenario (built into a temporary folder when not given); `compact`: the
    typesetting level, 0 (loosest) to COMPACT_LEVELS."""
    if diagrams is not None:
        return _page(data.lang, _context(data, diagrams), compact)
    with tempfile.TemporaryDirectory() as tmp:
        return _page(data.lang, _context(data, build_diagrams(data, Path(tmp))), compact)


def _page(lang: Lang, ctx: dict[str, Any], compact: int) -> str:
    return _env(lang).get_template("report.html.j2").render(compact=compact, **ctx)


CSS_NEWLINES = str.maketrans({"\n": " ", "\r": " ", "\f": " "})


def _css_str(text: str) -> Markup:
    """A text as the inside of a CSS string literal (the running header and footer, in a <style>
    element: HTML escaping does not apply there, so `<` and `>` are CSS-escaped instead). The three
    CSS newlines (LF, CR, FF) end a string: one in a client name would drop the declaration, so
    each becomes a space."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').translate(CSS_NEWLINES)
    return Markup(escaped.replace("<", "\\3c ").replace(">", "\\3e "))


def _finalize(value: object) -> object:
    """Every `{{ expression }}` of the report is plain text: a form feed in a scenario name, a note
    or a message garbles the PDF text layer of every page, so the one place that sees all the text
    is the template output. Line breaks and tabs stay (the formulas of Appendix C are a <pre>)."""
    if isinstance(value, Markup):
        return Markup(printable(str(value), keep="\n\t\r"))
    return printable(value, keep="\n\t\r") if isinstance(value, str) else value


def _env(lang: Lang) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        finalize=_finalize,
    )
    env.globals["t"] = lambda key, **fmt: t(key, lang, **fmt)  # pyright: ignore[reportArgumentType]
    env.globals["split"] = split
    env.filters["css_str"] = _css_str
    return env


def _data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _charts(data: ReportData) -> dict[str, Figure | None]:
    """Each chart as an inline image (None when the run has no data for it); the title, caption
    and source note are drawn in the PNG (F9a), the alt text repeats title and source note."""
    out: dict[str, Figure | None] = {}
    for cid in CHART_IDS:
        png = chart_png(data, cid)
        out[cid] = None if png is None else _figure(data, cid, png)
    return out


def _figure(data: ReportData, cid: str, png: bytes) -> Figure:
    alt = f"{t(f'chart.{cid}.title', data.lang)} - {data.source_note}"
    return Figure(_data_uri(png, "image/png"), alt)


def _diagrams(data: ReportData, paths: dict[str, Path]) -> dict[str, Figure]:
    return {
        sid: Figure(
            _data_uri(path.read_bytes(), "image/svg+xml"),
            f"{t('diagram.title', data.lang, scenario=sid)} - {data.source_note}",
        )
        for sid, path in paths.items()
    }


def _basis_keep(row: TableRow) -> bool:
    return not any(isinstance(c.value, str) and len(c.value) > MAX_TEXT_CHARS for c in row.cells)


def _opex_keep(row: TableRow) -> bool:
    return row.key.startswith(OPEX_DETAIL_YEAR) or row.kind in ("section", "total")


def _context(data: ReportData, diagrams: dict[str, Path]) -> dict[str, Any]:
    lang, m = data.lang, data.run.manifest
    study = block_of(data, "summary", "study")
    fixed, generated = limits(data)
    sections = [{"id": sid, "title": t(key, lang), "num": num} for sid, key, num in SECTIONS]
    notes = data.tables["summary"].notes
    capex_notes = [render_cell(n, lang) for n in data.tables["capex_opex"].notes]
    return {
        "lang": lang,
        "run_id": data.run_id,
        "study": {"client": data.basis.client, "site": data.basis.site},
        "banner": render_cell(notes[0], lang),
        "cover_facts": [
            (render_cell(r.label, lang), box(r.cells[0], lang).text) for r in study.rows
        ],
        "header_left": f"{data.basis.client} · {data.basis.site}",
        "header_right": t("pdf.header.indicative", lang),
        "footer_left": " · ".join(
            (
                f"{t('row.run_id', lang)} {data.run_id}",
                f"{t('pdf.footer.engine', lang)} {m.engine_version}",
            )
        ),
        "sections": sections,
        "S": {s["id"]: s for s in sections},
        "g": _grid_fn(data),
        "bt": _title_fn(data),
        "charts": _charts(data),
        "diagrams": _diagrams(data, diagrams),
        "messages": key_messages(data),
        "caveats": caveats(data),
        "scen": scenario_texts(data),
        "limits_fixed": fixed,
        "limits_generated": generated,
        "sens": data.run.sensitivity is not None,
        "sens_note": render_cell(data.tables["sensitivity"].notes[0], lang)
        if data.run.sensitivity is None
        else "",
        "break_even": break_even_sentences(data),
        "basis_keep": _basis_keep,
        "opex_keep": _opex_keep,
        "capex_notes": capex_notes,
        "assumptions_notes": [render_cell(n, lang) for n in data.tables["assumptions"].notes],
        "cash_notes": [render_cell(n, lang) for n in data.tables["cash_flow"].notes],
        "dq_notes": [render_cell(n, lang) for n in data.tables["data_quality"].notes],
        "formulas": t("methodology.formulas", lang),
        "trace": trace_index(data),
    }


def _grid_fn(data: ReportData) -> Callable[..., Grid]:
    colours = scenario_colours(data.run.results)  # the colour of each scenario in the charts

    def g(table_id: str, block_key: str, **kw: Any) -> Grid:
        return grid(block_of(data, table_id, block_key), data.lang, colours=colours, **kw)

    return g


def _title_fn(data: ReportData) -> Callable[[str, str], str]:
    def title(table_id: str, block_key: str) -> str:
        cell = block_of(data, table_id, block_key).title
        return render_cell(cell, data.lang) if cell is not None else ""

    return title
