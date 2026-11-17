"""F9c view of a report table block: what the PDF templates draw (text only, no layout).

`grid(block, lang)` turns a `TableBlock` into a `Grid` of display strings. Every number is
printed by `render_cell` (the i18n formatters): nothing is recomputed here. A scenario's lo / typ /
hi columns collapse into one column that shows the typical value with `lo – hi` under it; a scenario
not computed keeps its column, greyed, with the reason under the header.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass

from whsizing.report.i18n import Lang, render_cell, unit_label
from whsizing.schemas import Cell, TableBlock, TableColumn, TableRow

RANGE_SEPARATOR = " – "
SUFFIX_UNITS = frozenset({"/100"})  # units the row label does not already carry
LEFT_FMTS = frozenset({"text", "key", "date"})


@dataclass(frozen=True)
class Head:
    text: str
    span: int = 1
    note: str = ""  # reason of a scenario not computed
    off: bool = False
    colour: str = ""  # the scenario's colour in the charts (a rule above its header)


@dataclass(frozen=True)
class Box:
    text: str = ""
    sub: str = ""  # "lo – hi" under the typical value
    left: bool = False
    off: bool = False


@dataclass(frozen=True)
class Line:
    label: str
    boxes: list[Box]
    kind: str = "data"


@dataclass(frozen=True)
class Grid:
    title: str
    label_header: str
    heads: list[list[Head]]
    lines: list[Line]
    width: int  # display columns, label column excluded


@dataclass(frozen=True)
class DisplayColumn:
    """One drawn column: its main source column and, for a stacked range, lo and hi."""

    main: int
    lo: int | None = None
    hi: int | None = None


def display_columns(columns: list[TableColumn], stack: bool = True) -> list[DisplayColumn]:
    """Collapse each scenario's lo / typ / hi triple into one display column."""
    out: list[DisplayColumn] = []
    i = 0
    while i < len(columns):
        if stack and _is_range_triple(columns[i : i + 3]):
            out.append(DisplayColumn(main=i + 1, lo=i, hi=i + 2))
            i += 3
        else:
            out.append(DisplayColumn(main=i))
            i += 1
    return out


def _is_range_triple(cols: list[TableColumn]) -> bool:
    return (
        len(cols) == 3
        and all(c.scenario_id is not None and c.kind == "" for c in cols)
        and len({c.scenario_id for c in cols}) == 1
        and tuple(c.world for c in cols) == ("lo", "typ", "hi")
    )


def _is_empty(block: TableBlock, i: int) -> bool:
    return all(r.cells[i].value in (None, "") for r in block.rows)


def box(cell: Cell, lang: Lang) -> Box:
    text = render_cell(cell, lang)
    if text and cell.unit in SUFFIX_UNITS:
        text = f"{text} {unit_label(cell.unit)}"
    return Box(text=text, left=cell.fmt in LEFT_FMTS)


def _stacked(main: Cell, lo: Cell, hi: Cell, lang: Lang) -> Box:
    b = box(main, lang)
    low, high = render_cell(lo, lang), render_cell(hi, lang)
    if not (low and high) or low == b.text == high:
        return b
    return Box(text=b.text, sub=f"{low}{RANGE_SEPARATOR}{high}", left=b.left)


def _line(row: TableRow, dcols: list[DisplayColumn], disabled: list[bool], lang: Lang) -> Line:
    label = render_cell(row.label, lang)
    if row.kind == "section":
        return Line(label, [], "section")
    boxes: list[Box] = []
    for dc, off in zip(dcols, disabled, strict=True):
        if dc.lo is not None and dc.hi is not None:
            b = _stacked(row.cells[dc.main], row.cells[dc.lo], row.cells[dc.hi], lang)
        else:
            b = box(row.cells[dc.main], lang)
        boxes.append(Box(b.text, b.sub, b.left, off))
    return Line(label, boxes, row.kind)


def _heads(
    columns: list[TableColumn],
    dcols: list[DisplayColumn],
    lang: Lang,
    colours: Mapping[str, str],
) -> list[list[Head]]:
    """One header row per display column; two rows (group above label) when the columns that are
    not stacked carry a group (cash flow: a scenario's own flow, Δ and cumulative)."""
    mains = [columns[dc.main] for dc in dcols]

    def reason(c: TableColumn) -> str:
        return c.disabled_reason or ""

    def colour(c: TableColumn) -> str:
        return colours.get(c.scenario_id or "", "")

    stacked = any(dc.lo is not None for dc in dcols)
    grouped = [c for c in mains if c.group is not None]
    if stacked or not grouped:
        text = [
            render_cell(c.group, lang) if stacked and c.group is not None else "" for c in mains
        ]
        labels = [render_cell(c.label, lang) for c in mains]
        return [
            [
                Head(
                    text[i] or labels[i],
                    note=reason(c),
                    off=bool(c.disabled_reason),
                    colour=colour(c),
                )
                for i, c in enumerate(mains)
            ]
        ]
    top: list[Head] = []
    for c in mains:
        group = render_cell(c.group, lang) if c.group is not None else ""
        if top and top[-1].text == group:
            top[-1] = dataclasses.replace(top[-1], span=top[-1].span + 1)
        else:
            top.append(Head(group, 1, reason(c), bool(c.disabled_reason), colour(c)))
    return [top, [Head(render_cell(c.label, lang), off=bool(c.disabled_reason)) for c in mains]]


def split(g: Grid, per: int) -> list[Grid]:
    """`g` as grids of at most `per` scenarios each, sizes balanced (5 -> 3 + 2); the label column
    repeats, only the first grid keeps the title. A grid is split on its first header row when
    every cell of it is a scenario (it has a chart colour); any other grid is returned as it is."""
    top = g.heads[0]
    if len(top) <= per or not all(h.colour for h in top):
        return [g]
    count = -(-len(top) // per)  # number of grids
    base, extra = divmod(len(top), count)
    out: list[Grid] = []
    first = col = 0  # first header cell and first column of the grid being cut
    for n in range(count):
        last = first + base + (n < extra)
        width = sum(h.span for h in top[first:last])
        cut = slice(col, col + width)
        out.append(
            dataclasses.replace(
                g,
                title=g.title if n == 0 else "",
                heads=[top[first:last], *(row[cut] for row in g.heads[1:])],
                lines=[dataclasses.replace(ln, boxes=ln.boxes[cut]) for ln in g.lines],
                width=width,
            )
        )
        first, col = last, col + width
    return out


def grid(
    block: TableBlock,
    lang: Lang,
    *,
    keep: Callable[[TableRow], bool] | None = None,
    drop: Collection[str] = (),
    drop_empty: bool = False,
    stack: bool = True,
    colours: Mapping[str, str] | None = None,
) -> Grid:
    """The block as display strings. `keep` filters rows, `drop` removes columns by key,
    `drop_empty` the columns with no value in any row, `colours` scenario id → header colour."""
    columns_idx = [
        i
        for i, c in enumerate(block.columns)
        if c.key not in drop and not (drop_empty and _is_empty(block, i))
    ]
    cols = [block.columns[i] for i in columns_idx]
    rows = [
        r.model_copy(update={"cells": [r.cells[i] for i in columns_idx]})
        for r in block.rows
        if keep is None or keep(r)
    ]
    dcols = display_columns(cols, stack)
    disabled = [cols[dc.main].disabled_reason is not None for dc in dcols]
    return Grid(
        title=render_cell(block.title, lang) if block.title is not None else "",
        label_header=render_cell(block.label_header, lang) if block.label_header else "",
        heads=_heads(cols, dcols, lang, colours or {}),
        lines=[_line(r, dcols, disabled, lang) for r in rows],
        width=len(dcols),
    )
