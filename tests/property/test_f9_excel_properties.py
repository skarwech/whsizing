"""F9b Excel report, property tests: whatever content the report model holds, the workbook keeps
every number a number (never text), every text a text (a string such as "=1+1" or "123" is never
read as a formula or a number), writes no formula at all (value-only), comments exactly the
traced cells, and FR and EN hold the same numbers at the same coordinates."""

from __future__ import annotations

import dataclasses
import io
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from tests.unit.test_f9_tables_support import private_run

from whsizing.report import TABLE_IDS, ReportData, iter_cells, load_report_data
from whsizing.report.excel import render_workbook
from whsizing.schemas import Cell, ReportTable, TableBlock, TableColumn, TableRow
from whsizing.schemas.report import CellFmt

NUMERIC_FMTS: list[CellFmt] = ["int", "dec1", "dec2", "num", "pct", "eur"]
TRICKY = ["=1+1", "123", "-5", "1e3", "@SUM(A1)", "+3", "0x10", " 7 ", "TRUE", "#N/A", "'12", "=A1"]
text_st = st.one_of(
    st.sampled_from(TRICKY),
    st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs", "Cn")), max_size=40),
)
number_st = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e300, max_value=1e300)
trace_ids = st.sampled_from([None, None, "S0.area.total", "S1.finance.tco", "no.such.node"])
worlds = st.sampled_from(["lo", "typ", "hi"])

text_cell = text_st.map(lambda v: Cell(value=v, fmt="text"))
key_cell = st.sampled_from(["common.yes", "common.no", "severity.ok"]).map(
    lambda v: Cell(value=v, fmt="key")
)
date_cell = st.dates(min_value=date(1900, 3, 1), max_value=date(2200, 1, 1)).map(
    lambda d: Cell(value=d.isoformat(), fmt="date")
)
bool_cell = st.sampled_from([0.0, 1.0]).map(
    lambda v: Cell(value=v, fmt="bool", trace_id="S0.area.fit")
)
number_cell = st.builds(
    Cell,
    value=number_st,
    fmt=st.sampled_from(NUMERIC_FMTS),
    unit=st.sampled_from(["", "m2", "eur"]),
    trace_id=trace_ids,
    world=worlds,
    signed=st.booleans(),
)
cell_st = st.one_of(text_cell, key_cell, date_cell, bool_cell, number_cell, st.just(Cell()))


@st.composite
def block_st(draw: st.DrawFn, index: int) -> TableBlock:
    n_cols = draw(st.integers(0, 4))
    columns = [
        TableColumn(
            key=f"c{i}",
            label=draw(text_cell),
            group=draw(st.one_of(st.none(), text_cell)),
            scenario_id=draw(st.sampled_from([None, "S0", "S1"])),
            disabled_reason=draw(st.sampled_from([None, None, "why not"])),
        )
        for i in range(n_cols)
    ]
    rows = []
    for r in range(draw(st.integers(0, 5))):
        cells = [Cell() if col.disabled_reason is not None else draw(cell_st) for col in columns]
        rows.append(
            TableRow(
                key=f"r{r}",
                label=draw(text_cell),
                cells=cells,
                kind=draw(st.sampled_from(["data", "total", "section"])),
            )
        )
    return TableBlock(
        key=f"b{index}", title=draw(st.one_of(st.none(), text_cell)), columns=columns, rows=rows
    )


@st.composite
def tables_st(draw: st.DrawFn) -> dict[str, ReportTable]:
    out: dict[str, ReportTable] = {}
    for tid in draw(st.lists(st.sampled_from(TABLE_IDS), unique=True, max_size=4)):
        blocks = [draw(block_st(i)) for i in range(draw(st.integers(0, 3)))]
        out[tid] = ReportTable(
            id=tid,
            title=draw(text_cell),
            blocks=blocks,
            notes=draw(st.lists(text_cell, max_size=2)),
        )
    return out


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> ReportData:
    return load_report_data(private_run(tmp_path_factory, "f9b_props"), "en")


def with_tables(
    base: ReportData, random_tables: dict[str, ReportTable], **change: Any
) -> ReportData:
    """`base` (its run and traces) with the twelve tables: the random ones, the rest empty."""
    empty = {t: ReportTable(id=t, title=Cell(value=t, fmt="text"), blocks=[]) for t in TABLE_IDS}
    return dataclasses.replace(base, tables={**empty, **random_tables}, **change)


def book(payload: bytes) -> Any:
    return openpyxl.load_workbook(io.BytesIO(payload))


def numbers(wb: Any) -> list[dict[tuple[int, int], Any]]:
    return [
        {
            (c.row, c.column): c.value
            for row in ws.iter_rows()
            for c in row
            if c.data_type in ("n", "d") and c.value is not None
        }
        for ws in wb.worksheets
    ]


@pytest.mark.filterwarnings("error::UserWarning")  # openpyxl: a comment lost in a merged range
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(random_tables=tables_st())
def test_T9_5_property_random_content_never_turns_a_number_into_text_or_text_into_a_number(
    base: ReportData, random_tables: dict[str, ReportTable]
) -> None:
    data = with_tables(base, random_tables)
    wb = book(render_workbook(data, {}))
    cells = [c for _, c in iter_cells(data.tables)]
    # every number of the model, and nothing else, is a numeric cell (dates are real dates)
    model = sorted(
        float(c.value)
        for c in cells
        if c.fmt not in ("text", "key", "date") and isinstance(c.value, int | float)
    )
    sheet = sorted(
        float(v)
        for ws in numbers(wb)
        for v in ws.values()
        if isinstance(v, int | float) and not isinstance(v, bool)
    )
    assert sheet == pytest.approx(model, rel=1e-12, abs=1e-300)
    # every text of the model is a string cell, and no cell of the workbook is a formula
    strings = Counter(
        c.value for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.data_type == "s"
    )
    # (a scenario's group header is one merged cell over its columns: counted apart)
    texts = Counter(
        c.value
        for w, c in iter_cells(data.tables)
        if c.fmt == "text" and c.value and "/group" not in w
    )
    assert not (texts - strings), sorted((texts - strings).items())[:3]
    groups = {c.value for w, c in iter_cells(data.tables) if w.endswith("/group") and c.value}
    assert groups <= set(strings)
    assert not [
        c for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.data_type == "f"
    ]
    # a comment exactly on each traced cell
    traced = sum(1 for c in cells if c.trace_id and c.value is not None)
    assert (
        sum(1 for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.comment) == traced
    )


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(random_tables=tables_st())
def test_T9_5_property_fr_and_en_hold_the_same_numbers_at_the_same_coordinates(
    base: ReportData, random_tables: dict[str, ReportTable]
) -> None:
    en = with_tables(base, random_tables)
    fr = with_tables(base, random_tables, lang="fr")
    assert numbers(book(render_workbook(fr, {}))) == numbers(book(render_workbook(en, {})))


def test_property_strategies_reach_the_hard_cases(base: ReportData) -> None:
    """Guard against a vacuous property: the strategy does draw formulas-looking text, traced
    cells whose node does not exist, and not-computed columns."""
    drawn: list[dict[str, ReportTable]] = []

    @settings(max_examples=150, deadline=None, database=None, derandomize=True)
    @given(random_tables=tables_st())
    def collect(random_tables: dict[str, ReportTable]) -> None:
        drawn.append(random_tables)

    collect()
    every = [c for t in drawn for _, c in iter_cells(t)]
    assert any(c.fmt == "text" and str(c.value).startswith("=") for c in every)
    assert any(c.trace_id == "no.such.node" for c in every)
    assert any(c.fmt == "date" for c in every) and any(c.fmt == "pct" for c in every)
    assert any(
        col.disabled_reason
        for t in drawn
        for tab in t.values()
        for b in tab.blocks
        for col in b.columns
    )
    assert Path(str(base.run.run_dir)).is_dir()
