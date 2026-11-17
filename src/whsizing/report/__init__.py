"""F9 reporting. F9a (this package's core) builds the report model; the Excel builder (F9b,
`excel.py`) and the PDF builder (F9c, `pdf.py`) render from it. Stable public API:

    data = load_report_data(run, lang)       # ReportData: loads the run folder once, builds tables
    data.tables["summary"]                   # ReportTable; TABLE_IDS lists the twelve ids
    charts = build_charts(data, out_dir)     # {chart id: png path}; CHART_IDS
    svgs = build_diagrams(data, out_dir)     # {scenario id: report/diagram_<scenario>.svg}
    xlsx = build_excel(run, lang)            # report/report_<lang>.xlsx (+ trace.jsonl)
    pdf = build_pdf(run, lang)               # report/report_<lang>.pdf (+ trace.jsonl, diagrams)
    export_trace(data, report_dir / "trace.jsonl")         # every scenario's nodes + the report's
    issues = check_integrity(run, html=None, data=data)    # [] when sound; IC1-IC8
    assert_integrity(run, html, data=data)   # ReportIntegrityError (exit 5) listing the issues
    t(key, lang, **fmt), fmt_number, fmt_pct, fmt_date, render_cell(cell, lang)   # i18n

The model (`whsizing.schemas.report`)
-------------------------------------
`ReportTable(id, title, blocks, notes)`: one Excel sheet / PDF section. `TableBlock(key, title,
columns, rows)`: a titled grid; a table stacks blocks (the sheet writes them one under the
other, the PDF section as one HTML table each). `TableColumn(key, label, group, scenario_id,
world, kind, disabled_reason)`: `group` is the header above a scenario's lo / typ / hi columns;
a scenario not computed keeps its columns with `disabled_reason` set (grey them, show the
reason) and empty cells. `TableRow(key, label, cells, kind)`: `cells[i]` belongs to
`columns[i]`; kind "section" is a sub-heading row (empty cells), "total" a total row.
`Cell(value, unit, fmt, trace_id, world, signed, args)`: `value` is the RAW number (or text);
format it with `render_cell(cell, lang)` (text) or write it as a number and map `fmt` to a
number format: int and eur `#,##0`, dec1 `#,##0.0`, dec2 `#,##0.00`, pct `0.0 %` (value is a
share), num general, bool yes / no (1.0 / 0.0), date (ISO string), text and key (i18n key
translated with `args`) are strings. Labels are i18n keys: `render_cell(row.label, lang)`.
`Cell.unit` is the unit of the value ("m2", "h", "eur", "heads", ...); `unit_label(unit)`
gives the display form. `Cell.trace_id` / `world` name the TraceNode the value comes from
(summary, scenarios, fte, capex_opex: every numeric cell in a scenario column); an Excel cell
comment or the PDF trace index can resolve it with `data.tracers[scenario_id]`, or in the file
`export_trace(data, path)` writes (the report stage's trace.jsonl: every scenario's nodes plus
the report's own `<sid>.report.n_warnings`).

Conventions the renderers rely on
---------------------------------
* A Range is three cells (lo, typ, hi); a scalar sits in the typ column, lo / hi are empty.
* Row keys are stable ("area.zone.storage", "fte.heads.total", "cash.y3"); renderers may use
  them to place charts or conditional formats (e.g. row "fit" of summary: 1.0 / 0.0).
* No baseline: the NPV and payback rows are absent (summary, capex_opex), so is the "ranking
  by payback" row (also when no scenario reaches a payback), and cash_flow has no Δ columns;
  `methodology` then carries the generated limit "limit.gen.no_baseline".
* Not shown as cells but available: the overflow share of a scenario is 1 - the cell of
  row "eligibility.share_lines" (no trace node of its own); the localised confidence note and
  the "indicative study" banner are in `summary.notes`; the limitations of §8 are the rows of
  block "methodology_limits" (label = i18n key with `args`: the TODO and confidence-L counts).
* `ReportData.source_note` is the footer "engine v, catalog v, run id" of every chart.
* Fonts: DejaVu Sans / Liberation Sans (`style.fonts()`); a scenario has one colour in all
  charts (`style.scenario_colours(run.results)`).
* i18n texts of the design_basis rows (F4's notes), the DQ rule messages and the FinancialResult
  notes (capex_opex notes, `limit.gen.finance.<i>` rows of section 8) are in the language the
  pipeline wrote them in (English); everything else is translated.
"""

from whsizing.report.charts import CHART_IDS, build_charts, chart_png
from whsizing.report.data import ReportData, export_trace, load_report_data
from whsizing.report.diagram import Layout, Rect, build_diagram, build_diagrams, layout_blocks
from whsizing.report.excel import build_excel
from whsizing.report.i18n import (
    LANGS,
    Lang,
    fmt_date,
    fmt_number,
    fmt_pct,
    render_cell,
    t,
    unit_label,
)
from whsizing.report.integrity import assert_integrity, check_integrity
from whsizing.report.pdf import build_pdf
from whsizing.report.tables import TABLE_IDS, build_tables, iter_cells, used_keys

__all__ = [
    "CHART_IDS",
    "LANGS",
    "TABLE_IDS",
    "Lang",
    "Layout",
    "Rect",
    "ReportData",
    "assert_integrity",
    "build_charts",
    "build_diagram",
    "build_diagrams",
    "build_excel",
    "build_pdf",
    "build_tables",
    "chart_png",
    "check_integrity",
    "export_trace",
    "fmt_date",
    "fmt_number",
    "fmt_pct",
    "iter_cells",
    "layout_blocks",
    "load_report_data",
    "render_cell",
    "t",
    "unit_label",
    "used_keys",
]
