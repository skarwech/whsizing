"""Report model (F9a): the typed tables the Excel (F9b) and PDF (F9c) renderers draw from, and
the integrity issues of the IC1-IC8 checks.

One model, two renderers: a `Cell` holds the RAW value (never formatted); formatting happens at
render time through `whsizing.report.i18n`. `fmt` says how to format a value:

    text   literal string (client names, scenario names, ids)          value: str
    key    i18n key, translated with `args`                            value: str
    int    #,##0          dec1  #,##0.0          dec2  #,##0.00        value: float
    num    general number, up to 6 significant digits (parameter values) value: float
    pct    share shown as 0.0 %  (value 0.123 -> "12.3 %")             value: float
    eur    #,##0 (the unit says euro)                                  value: float
    bool   yes / no (value 1.0 or 0.0)                                  value: float
    date   ISO yyyy-mm-dd, shown dd/mm/yyyy in FR                       value: str

Re-exported by `whsizing.schemas`: T0.3 needs an example of each in tests/fixtures/factories.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from whsizing.schemas.params import World

CellFmt = Literal["text", "key", "int", "dec1", "dec2", "num", "pct", "eur", "bool", "date"]
RowKind = Literal["data", "total", "section"]
Severity = Literal["error", "warning"]
CheckId = Literal["IC1", "IC2", "IC3", "IC4", "IC5", "IC6", "IC7", "IC8"]


class Cell(BaseModel, frozen=True, extra="forbid"):
    """One table cell. A numeric cell (`value` is a number, `fmt` not text/key/date) in a
    scenario column of the summary, scenarios, fte and capex_opex tables carries the id of its
    TraceNode (IC1)."""

    value: float | str | None = None
    unit: str = ""
    fmt: CellFmt = "text"
    trace_id: str | None = None
    world: World | None = None  # world of the trace node holding `value` (a Range's lo / hi)
    signed: bool = False  # may legitimately be negative (NPV, Δ cash flow): exempt from IC7
    args: dict[str, str | float] = {}  # format arguments of an i18n text (fmt "key")


class TableColumn(BaseModel, frozen=True, extra="forbid"):
    key: str  # unique within the block: "S2.typ", "year", "stat.p95"
    label: Cell
    group: Cell | None = None  # header above the column (the scenario's "S0 - name")
    scenario_id: str | None = None
    world: World | None = None  # lo / typ / hi column of a Range
    kind: str = ""  # free tag the integrity checks read: "cash_flow", "delta", "cumulative"
    disabled_reason: str | None = None  # scenario not computed: the column is greyed with this


class TableRow(BaseModel, frozen=True, extra="forbid"):
    key: str  # stable id: "area.zone.storage", "fte.total.heads", "cash.y3"
    label: Cell
    cells: list[Cell]  # one per column of the block, in order
    kind: RowKind = "data"


class TableBlock(BaseModel, frozen=True, extra="forbid"):
    """A titled grid; a table stacks one or more blocks (an Excel sheet, a PDF section)."""

    key: str
    title: Cell | None = None
    label_header: Cell | None = None  # header of the row-label column ("Id", "Series"), if any
    columns: list[TableColumn]
    rows: list[TableRow]


class ReportTable(BaseModel, frozen=True, extra="forbid"):
    id: str  # summary, design_basis, ..., methodology (the Excel sheet / PDF section names)
    title: Cell
    blocks: list[TableBlock]
    notes: list[Cell] = []  # banner, confidence note, limitations lines


class IntegrityIssue(BaseModel, frozen=True, extra="forbid"):
    id: CheckId
    severity: Severity
    message: str
    location: str  # "scenarios/fte/S1.typ", "trace S2.area.total", "html"
