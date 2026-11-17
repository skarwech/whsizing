"""F9b Excel report: `build_excel(run, lang)` writes `<run>/report/report_<lang>.xlsx`.

    path = build_excel(run, "fr")      # twelve sheets, XlsxWriter, values only

The workbook is a rendering of the F9a report model (`load_report_data`, `report.tables`): it
never computes a number, it writes each `Cell.value` as a real number with a number format
(`#,##0` counts, areas and euros, `#,##0.0`, `#,##0.00`, `0.0 %` shares; the fit flag stays 1 / 0
shown as yes / no by its format), text as text. FR and EN workbooks hold the same numbers at the
same coordinates; only the strings differ.

Stretch (spec F9, live formulas on the FTE and Cash flow sheets): NOT built. The value-only
workbook is the default and the only version; a consultant who changes a productivity changes the
parameter and re-runs.

Sheets: the twelve `TABLE_IDS`, named `t("table.<id>", lang)`; characters Excel forbids in a sheet
name (`[]:*?/\\`) become "-" ("Capex / Opex" is the sheet "Capex - Opex"), 31 characters at most.
Per sheet: title row, the "indicative study" banner (when the table has it), then each block
(title, scenario group header over its lo / typ / hi columns, column labels, rows), then the other
notes. The header row of the first block is frozen (with the label column) and repeated in print;
Summary writes its `comparison` block first; the page is landscape, one page wide, A4, with the
engine / catalog / run id footer. Demand profile carries the demand charts as images below the
tables; Assumptions has the autofilter on its table; the fit rows are green / red by conditional
formatting; a scenario not computed has its columns greyed with the reason (the F8 text of
`limit.gen.not_computed`).

Trace ("why this number"): every cell with a `trace_id` gets a comment holding the id, the world,
the node's label, its formula and its inputs (`excel.trace`, from the scenario trace). The build
also writes `report/trace.jsonl` (`export_trace`), the file in which every cited id resolves.

Gate: `assert_integrity(run)` runs first (a failed check raises `ReportIntegrityError`, exit 5);
the workbook is built in memory and checked for untranslated texts (IC8 on the Excel strings);
only then are `trace.jsonl` and the xlsx written, so a failure leaves nothing behind.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import xlsxwriter
from xlsxwriter.format import Format
from xlsxwriter.utility import xl_rowcol_to_cell

from whsizing.errors import ReportIntegrityError, WhsizingError
from whsizing.report.charts import SIZE_IN, chart_png
from whsizing.report.data import ReportData, export_trace, load_report_data
from whsizing.report.i18n import MISSING_PREFIX, Lang, render_cell, t
from whsizing.report.integrity import assert_integrity
from whsizing.report.tables_data import FORMULAS_KEY
from whsizing.schemas import Cell, ReportTable, TableBlock, TableColumn, TableRow
from whsizing.schemas.run import RunOutput

BANNER_KEY = "banner.indicative"
EXCEL_MAX = 9.99999999999999e307  # the largest magnitude an Excel cell holds
LEAD_BLOCK = {"summary": "comparison"}  # written first, so its header is the frozen one
AUTOFILTER_TABLES = frozenset({"assumptions"})
DEMAND_CHARTS = ("daily", "seasonality", "pareto", "split", "hourly")
CHART_ROWS = int(SIZE_IN[1] * 96 / 20) + 2  # a chart (96 px per inch) spans this many 20 px rows
NUM_FORMATS = {
    "int": "#,##0",
    "eur": "#,##0",
    "dec1": "#,##0.0",
    "dec2": "#,##0.00",
    "pct": "0.0 %",
}  # "num" stays General
DATE_FORMATS: dict[Lang, str] = {"fr": "dd/mm/yyyy", "en": "yyyy-mm-dd"}
BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
MAX_SHEET_NAME = 31
MIN_WIDTH, MAX_WIDTH, LABEL_MIN_WIDTH = 12, 60, 30
FORMULA_COLS = 10
COMMENT_WIDTH_PX, COMMENT_CHARS_PER_LINE = 400, 60
HEAD = {"bold": True, "bg_color": "#E7ECF1", "border": 1, "text_wrap": True, "valign": "vcenter"}
GREY = {"bg_color": "#D9D9D9", "font_color": "#595959"}
ROW_STYLES: dict[str, dict[str, object]] = {
    "data": {},
    "total": {"bold": True, "top": 1},
    "section": {"bold": True, "bg_color": "#F2F2F2"},
}
FIT_STYLES = (
    ("=AND(ISNUMBER({c}),{c}=1)", "#C6EFCE", "#006100"),
    ("=AND(ISNUMBER({c}),{c}=0)", "#FFC7CE", "#9C0006"),
)


def sheet_name(table_id: str, lang: Lang) -> str:
    """The Excel sheet name of a table: its i18n title without the characters Excel forbids."""
    return BAD_SHEET_CHARS.sub("-", t(f"table.{table_id}", lang))[:MAX_SHEET_NAME]


def cell_content(cell: Cell, lang: Lang) -> tuple[str | float | datetime | None, str | None]:
    """What to write for a cell and its number format: numbers stay numbers (never text), text
    and i18n keys become strings, dates real dates; None is a blank cell."""
    v = cell.value
    if v is None:
        return None, None
    if cell.fmt in ("text", "key"):
        return render_cell(cell, lang), None
    if cell.fmt == "date":
        try:
            return datetime.fromisoformat(str(v)), DATE_FORMATS[lang]
        except ValueError as e:
            raise WhsizingError(f"report: {v!r} is not an ISO date") from e
    if isinstance(v, str):
        raise ReportIntegrityError(f"report: a {cell.fmt} cell holds the text {v!r}")
    if not math.isfinite(v) or abs(v) > EXCEL_MAX:
        raise ReportIntegrityError(f"report: a {cell.fmt} cell holds {v}, no number Excel can hold")
    if cell.fmt == "bool":  # 1 / 0 shown as yes / no: positive;negative;zero
        yes, no = t("common.yes", lang), t("common.no", lang)
        return float(v), f'"{yes}";"{yes}";"{no}"'
    return float(v), NUM_FORMATS.get(cell.fmt)


def build_excel(run: RunOutput, lang: Lang) -> Path:
    """Write `<run>/report/report_<lang>.xlsx` (and `report/trace.jsonl`); return the xlsx path.
    `ReportIntegrityError` (exit 5) when an integrity check fails: nothing is written."""
    data = load_report_data(run, lang)
    assert_integrity(run, data=data)
    charts = {c: png for c in DEMAND_CHARTS if (png := chart_png(data, c)) is not None}
    payload = render_workbook(data, charts)
    out = Path(run.run_dir) / "report"
    export_trace(data, out / "trace.jsonl")
    path = out / f"report_{lang}.xlsx"
    try:
        path.write_bytes(payload)
    except OSError as e:
        raise WhsizingError(f"report: cannot write {path} ({e.strerror})") from e
    return path


def render_workbook(data: ReportData, charts: dict[str, bytes]) -> bytes:
    """The xlsx bytes of `data.tables` (no file, no integrity gate); `charts` = chart id -> PNG."""
    buf = io.BytesIO()
    book = _Book(data, buf)
    for table_id in data.tables:
        _Sheet(book, data.tables[table_id], charts).write()
    book.wb.close()
    unresolved = sorted({s for s in book.texts if MISSING_PREFIX in s})
    if unresolved:
        raise ReportIntegrityError(f"report integrity: IC8 untranslated text(s): {unresolved[:5]}")
    return buf.getvalue()


@dataclass
class _Book:
    data: ReportData
    buf: io.BytesIO
    texts: list[str] = field(default_factory=list)  # every string written (IC8)
    _formats: dict[tuple[tuple[str, object], ...], Format] = field(default_factory=dict)
    lang: Lang = field(init=False)
    wb: xlsxwriter.Workbook = field(init=False)

    def __post_init__(self) -> None:
        self.lang = self.data.lang
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True})
        m = self.data.run.manifest
        self.wb.set_properties(
            {
                "title": f"whsizing {m.run_id}",
                "comments": self.data.source_note,
                "created": m.created_at,
            }
        )

    def fmt(self, **props: object) -> Format:
        key = tuple(sorted(props.items()))
        if key not in self._formats:
            self._formats[key] = self.wb.add_format(props)
        return self._formats[key]


class _Sheet:
    """One worksheet: writes a `ReportTable` and tracks what the closing touches need."""

    def __init__(self, book: _Book, table: ReportTable, charts: dict[str, bytes]) -> None:
        self.book, self.table, self.charts = book, table, charts
        self.lang: Lang = book.lang
        self.ws = book.wb.add_worksheet(sheet_name(table.id, self.lang))
        self.row = 0
        self.widths: dict[int, int] = {}
        self.freeze = (1, 1)
        self.repeat: tuple[int, int] | None = None
        self.autofilter: tuple[int, int, int, int] | None = None
        self.fit_rows: list[tuple[int, int, int]] = []  # (row, first col, last col) of bool cells
        self.scenario_sheet = False  # scenario columns: text in them overflows, never widens

    # ------------------------------------------------------------------ whole sheet
    def write(self) -> None:
        table = self.table
        self.string(0, 0, render_cell(table.title, self.lang), bold=True, font_size=14)
        self.row = 2
        self.scenario_sheet = any(c.scenario_id for b in table.blocks for c in b.columns)
        banner = [n for n in table.notes if n.value == BANNER_KEY]
        for n in banner:
            self.string(1, 0, render_cell(n, self.lang), bold=True, font_color="#9C0006")
        lead = LEAD_BLOCK.get(table.id)
        blocks = sorted(table.blocks, key=lambda b: b.key != lead)  # stable: only the lead moves
        for i, block in enumerate(blocks):
            self.block(block, first=i == 0)
        for n in (n for n in table.notes if n.value != BANNER_KEY):
            self.string(self.row, 0, render_cell(n, self.lang), italic=True)
            self.row += 1
        self.images()
        self.finish()

    def finish(self) -> None:
        ws = self.ws
        for c, w in self.widths.items():
            ws.set_column(c, c, max(w + 2, LABEL_MIN_WIDTH if c == 0 else MIN_WIDTH))
        ws.freeze_panes(*self.freeze)
        if self.repeat:
            ws.repeat_rows(*self.repeat)
        if self.autofilter:
            ws.autofilter(*self.autofilter)
        for r, c0, c1 in self.fit_rows:
            top_left = xl_rowcol_to_cell(r, c0)
            for criteria, bg, ink in FIT_STYLES:
                f = self.book.fmt(bg_color=bg, font_color=ink)
                ws.conditional_format(
                    r,
                    c0,
                    r,
                    c1,
                    {"type": "formula", "criteria": criteria.format(c=top_left), "format": f},
                )
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        footer = self.book.data.source_note.replace("&", "&&")
        ws.set_footer(f"&L&8{footer}&R&8&P / &N")

    def images(self) -> None:
        if self.table.id != "demand_profile":
            return
        r = self.row + 1
        for chart_id, png in self.charts.items():
            title = t(f"chart.{chart_id}.title", self.lang)
            self.book.texts.append(title)
            self.ws.insert_image(
                r,
                0,
                f"chart_{chart_id}_{self.lang}.png",
                {"image_data": io.BytesIO(png), "description": title},
            )
            r += CHART_ROWS

    # ------------------------------------------------------------------ one block
    def block(self, block: TableBlock, first: bool) -> None:
        if block.title is not None:
            self.string(self.row, 0, render_cell(block.title, self.lang), bold=True, font_size=12)
            self.row += 1
        head_first = self.row
        if block.columns:
            self.header(block)
        head_last = self.row - 1
        if first:
            self.freeze = (self.row, 1)
            self.repeat = (head_first, head_last) if block.columns else None
        top = self.row
        for row in block.rows:
            self.body_row(block, row)
        if block.rows and any(c.disabled_reason is not None for c in block.columns):
            self.disabled_regions(block, top, self.row - 1)
        if first and self.table.id in AUTOFILTER_TABLES and block.rows:
            self.autofilter = (head_last, 0, self.row - 1, len(block.columns))
        self.row += 1

    def header(self, block: TableBlock) -> None:
        cols = block.columns
        if any(c.group is not None for c in cols):
            self.header_row(block, self.row, [c.group for c in cols], None, merge=True)
            self.row += 1
        label = None if block.label_header is None else render_cell(block.label_header, self.lang)
        self.header_row(block, self.row, [c.label for c in cols], label, merge=False)
        self.row += 1

    def header_row(
        self,
        block: TableBlock,
        r: int,
        cells: Sequence[Cell | None],
        first: str | None,
        merge: bool,
    ) -> None:
        """Header cells at columns 1..n; with `merge`, equal neighbours share one merged cell
        (the scenario group over its lo / typ / hi columns)."""
        self.string(r, 0, first or "", **HEAD)
        i = 0
        while i < len(cells):
            j = i
            while merge and j + 1 < len(cells) and cells[j + 1] == cells[i]:
                j += 1
            style = {**HEAD, "align": "center"}
            if block.columns[i].disabled_reason is not None:
                style = {**style, **GREY}
            cell = cells[i]
            text = "" if cell is None else render_cell(cell, self.lang)
            self.book.texts.append(text)
            if j > i:
                self.merged(r, 1 + i, r, 1 + j, text, self.book.fmt(**style))
            else:
                self.ws.write_string(r, 1 + i, text, self.book.fmt(**style))
            self.track(1 + i, len(text) // (j - i + 1))
            i = j + 1

    def body_row(self, block: TableBlock, row: TableRow) -> None:
        r, style = self.row, ROW_STYLES[row.kind]
        self.row += 1
        if not block.columns:  # a text block (limits, formulas): the label alone
            self.text_row(r, row.label)
            return
        self.cell(r, 0, row.label, None, wrap=True, **style)
        for i, (col, cell) in enumerate(zip(block.columns, row.cells, strict=False)):
            if col.disabled_reason is not None:
                continue
            if cell.value is None and row.kind == "section":
                self.ws.write_blank(r, 1 + i, None, self.book.fmt(**style))
            self.cell(r, 1 + i, cell, col, wrap=not self.scenario_sheet, **style)
        bool_cols = [
            1 + i for i, c in enumerate(row.cells) if c.fmt == "bool" and c.value is not None
        ]
        if bool_cols:
            self.fit_rows.append((r, min(bool_cols), max(bool_cols)))

    def text_row(self, r: int, label: Cell) -> None:
        """A row of a block without columns: a limitation sentence (wrapped in the label column)
        or, for the formulas, one monospaced line per row across `FORMULA_COLS` merged columns
        (so the printed page is as wide as the lines)."""
        text = render_cell(label, self.lang)
        if label.value != FORMULAS_KEY:
            self.string(r, 0, text, text_wrap=True, valign="top")
            self.track(0, len(text))
            self.row = r + 1
            return
        f = self.book.fmt(font_name="Courier New", font_size=9)
        for k, line in enumerate(text.splitlines()):
            self.book.texts.append(line)
            self.merged(r + k, 0, r + k, FORMULA_COLS - 1, line, f)
        self.row = r + len(text.splitlines())

    def disabled_regions(self, block: TableBlock, r0: int, r1: int) -> None:
        """A scenario not computed: its columns are one grey block holding the reason."""
        cols = block.columns
        i = 0
        while i < len(cols):
            j = i
            while (
                j + 1 < len(cols)
                and cols[j + 1].scenario_id == cols[i].scenario_id
                and cols[j + 1].disabled_reason == cols[i].disabled_reason
            ):
                j += 1
            reason = cols[i].disabled_reason
            if reason is not None:
                self.grey_region(cols[i], reason, r0, 1 + i, r1, 1 + j)
            i = j + 1

    def grey_region(
        self, col: TableColumn, reason: str, r0: int, c0: int, r1: int, c1: int
    ) -> None:
        text = t("limit.gen.not_computed", self.lang, scenario=col.scenario_id or "", reason=reason)
        self.book.texts.append(text)
        f = self.book.fmt(**GREY, italic=True, text_wrap=True, valign="top", border=1)
        if (r0, c0) == (r1, c1):
            self.ws.write_string(r0, c0, text, f)
        else:
            self.merged(r0, c0, r1, c1, text, f)

    # ------------------------------------------------------------------ cells
    def merged(self, r0: int, c0: int, r1: int, c1: int, text: str, f: Format) -> None:
        """A merged range holding `text` as a string: `merge_range` would write it with `write()`,
        which turns a text starting with "=" into a formula."""
        self.ws.merge_range(r0, c0, r1, c1, "", f)
        self.ws.write_string(r0, c0, text, f)

    def string(self, r: int, c: int, text: str, **style: object) -> None:
        self.book.texts.append(text)
        self.ws.write_string(r, c, text, self.book.fmt(**style))

    def track(self, c: int, length: int) -> None:
        self.widths[c] = min(max(self.widths.get(c, 0), length), MAX_WIDTH)

    def cell(
        self, r: int, c: int, cell: Cell, col: TableColumn | None, wrap: bool, **style: object
    ) -> None:
        value, num_format = cell_content(cell, self.lang)
        if value is None:
            return
        props = dict(style)
        if num_format:
            props["num_format"] = num_format
        if isinstance(value, str):
            props["text_wrap"] = wrap
            self.book.texts.append(value)
            self.ws.write_string(r, c, value, self.book.fmt(**props))
            if wrap:  # text that overflows (scenario sheets) must not widen a number column
                self.track(c, max(len(x) for x in value.splitlines() or [""]))
        elif isinstance(value, datetime):
            self.ws.write_datetime(r, c, value, self.book.fmt(**props))
            self.track(c, 10)
        else:
            self.ws.write_number(r, c, value, self.book.fmt(**props))
            self.track(c, len(render_cell(cell, self.lang)))
        if cell.trace_id:
            self.comment(r, c, cell, col)

    def comment(self, r: int, c: int, cell: Cell, col: TableColumn | None) -> None:
        text = self.trace_text(cell, col)
        self.book.texts.append(text)
        lines = sum(-(-max(len(x), 1) // COMMENT_CHARS_PER_LINE) for x in text.splitlines())
        self.ws.write_comment(
            r, c, text, {"width": COMMENT_WIDTH_PX, "height": 24 + 15 * lines, "font_size": 9}
        )

    def trace_text(self, cell: Cell, col: TableColumn | None) -> str:
        """Id, world, label, formula and inputs of the cell's trace node (the id alone when the
        node is not in the scenario trace: only the cash-flow cells are not checked by IC1)."""
        tid, world = str(cell.trace_id), cell.world or "typ"
        sid = col.scenario_id if col is not None and col.scenario_id else tid.partition(".")[0]
        tracer = self.book.data.tracers.get(sid)
        try:
            node = None if tracer is None else tracer.get(tid, world)
        except KeyError:
            node = None
        if node is None:
            return f"{tid} ({world})"
        inputs = "\n".join(f"  {sym} = {ref}" for sym, ref in node.inputs.items())
        return t(
            "excel.trace",
            self.lang,
            id=tid,
            world=world,
            label=node.label,
            formula=node.formula,
            inputs=inputs,
        )
