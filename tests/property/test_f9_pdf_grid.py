"""F9c property: the PDF view of a scenario's lo / typ / hi cells (`pdf_view.grid`) stacks them
into one column whose printed typical value and range parse back to the raw numbers, in FR and EN,
whatever the values (T9.5 at the level of one cell)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.unit.test_f9_pdf_support import parse_number

from whsizing.report.i18n import Lang
from whsizing.report.pdf_view import grid
from whsizing.schemas import Cell, TableBlock, TableColumn, TableRow
from whsizing.schemas.report import CellFmt

DECIMALS: dict[CellFmt, int] = {"int": 0, "eur": 0, "dec1": 1, "dec2": 2}
amounts = st.floats(min_value=0, max_value=5e7, allow_nan=False, allow_infinity=False)


def block_of(lo: float, typ: float, hi: float, fmt: CellFmt) -> TableBlock:
    cols = [
        TableColumn(
            key=f"S1.{w}", label=Cell(value=f"col.{w}", fmt="key"), scenario_id="S1", world=w
        )
        for w in ("lo", "typ", "hi")
    ]
    cells = [Cell(value=v, fmt=fmt, unit="eur") for v in (lo, typ, hi)]
    row = TableRow(key="r", label=Cell(value="x", fmt="text"), cells=cells)
    return TableBlock(key="b", columns=cols, rows=[row])


@settings(max_examples=200, deadline=None)
@given(
    values=st.tuples(amounts, amounts, amounts).map(sorted),
    fmt=st.sampled_from(sorted(DECIMALS)),
    lang=st.sampled_from(["fr", "en"]),
)
def test_T9_5_prop_a_stacked_range_prints_back_to_its_raw_values(
    values: list[float], fmt: CellFmt, lang: Lang
) -> None:
    lo, typ, hi = values
    g = grid(block_of(lo, typ, hi, fmt), lang)
    assert g.width == 1 and len(g.lines) == 1  # three columns became one
    shown = g.lines[0].boxes[0]
    tol = 0.5 * 10 ** -DECIMALS[fmt] + 1e-9
    assert parse_number(shown.text, lang) == pytest.approx(typ, abs=tol)
    if shown.sub:  # the range is left out only when lo, typ and hi print the same
        low, _, high = shown.sub.partition(" – ")
        assert parse_number(low, lang) == pytest.approx(lo, abs=tol)
        assert parse_number(high, lang) == pytest.approx(hi, abs=tol)
    else:
        assert max(hi - typ, typ - lo) <= tol * 2 or round(lo, DECIMALS[fmt]) == round(
            hi, DECIMALS[fmt]
        )
