"""F10b page 6 tables (T10.4): a row label carries the unit of its cells once."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from whsizing.app import drilldown, results_ui
from whsizing.app.results_ui import _with_unit  # pyright: ignore[reportPrivateUsage]
from whsizing.schemas import Cell, TableBlock, TableColumn, TableRow


@pytest.mark.parametrize(
    ("label", "units", "expected"),
    [
        ("Rent", {"eur"}, "Rent [€]"),
        ("Total area (m²)", {"m2"}, "Total area (m²)"),  # the report label has it already
        ("Area (m², with aisles)", {"m2"}, "Area (m², with aisles)"),
        ("Capex (€)", {"eur"}, "Capex (€)"),
        ("Year 1", {"h"}, "Year 1 [h]"),  # an `h` inside another word is not the unit
        ("Shipping, parcels", {"h"}, "Shipping, parcels [h]"),
        ("Heads, design day", {"heads"}, "Heads, design day"),  # the label's case is not the unit's
        ("Robots", {"-"}, "Robots"),  # unitless
        ("Cost per line", {"eur/line"}, "Cost per line [€/line]"),
        ("Mixed", {"m2", "eur"}, "Mixed"),  # several units: none shown
        ("Empty", set(), "Empty"),
    ],
)
def test_T10_4_row_label_gets_its_unit_unless_it_already_says_it(
    label: str, units: set[str], expected: str
) -> None:
    assert _with_unit(label, set(units)) == expected


# ------------------------------------------------------- R7.7: a table cell starts the drill-down
WORLDS = ("lo", "typ", "hi")


def summary_block() -> TableBlock:
    """Two scenarios x (lo, typ, hi) with a group header, a traced and an untraced row."""
    pairs = [(sid, w) for sid in ("S0", "S1") for w in WORLDS]
    columns = [
        TableColumn(
            key=f"{sid}.{w}",
            label=Cell(value=f"col.{w}", fmt="key"),
            group=Cell(value=sid, fmt="text"),
            scenario_id=sid,
            world=w,  # type: ignore[arg-type]
        )
        for sid, w in pairs
    ]
    traced = [
        Cell(value=1.0, fmt="int", trace_id=f"{sid}.area.total", world=w)  # type: ignore[arg-type]
        for sid, w in pairs
    ]
    return TableBlock(
        key="comparison",
        label_header=Cell(value="Row", fmt="text"),
        columns=columns,
        rows=[
            TableRow(key="area", label=Cell(value="Total area", fmt="text"), cells=traced),
            TableRow(
                key="notes",
                label=Cell(value="Untraced", fmt="text"),
                cells=[Cell(value=2.0, fmt="int") for _ in columns],
            ),
        ],
    )


def frame_names(block: TableBlock, all_worlds: bool) -> list[str]:
    return list(results_ui.block_frame(block, "en", all_worlds))


def test_R7_7_a_selected_frame_cell_is_the_table_cell_of_a_column_the_frame_shows() -> None:
    block = summary_block()
    assert list(results_ui.frame_columns(block, "en", False).values()) == [-1, 1, 4]  # typ only
    assert list(results_ui.frame_columns(block, "en", True).values()) == [-1, 0, 1, 2, 3, 4, 5]
    names = frame_names(block, False)
    assert len(names) == 3 and all(
        len(v) == 2 for v in results_ui.block_frame(block, "en", False).values()
    )
    row, column, cell = results_ui.picked_cell(block, "en", False, [(0, names[2])]) or (None,) * 3
    assert (row.key, column.key, cell.trace_id) == ("area", "S1.typ", "S1.area.total")  # type: ignore[union-attr]
    # with every world the frame has more columns and the same name is another cell
    wide = results_ui.picked_cell(block, "en", True, [(0, frame_names(block, True)[1])])
    assert wide is not None and wide[1].key == "S0.lo"


def test_R7_7_a_row_label_a_missing_row_or_no_selection_picks_no_cell() -> None:
    block = summary_block()
    names = frame_names(block, False)
    assert results_ui.picked_cell(block, "en", False, []) is None
    assert results_ui.picked_cell(block, "en", False, [(0, names[0])]) is None  # the row labels
    assert results_ui.picked_cell(block, "en", False, [(9, names[1])]) is None  # no such row
    assert results_ui.picked_cell(block, "en", False, [(0, "no such column")]) is None


def test_R7_7_only_a_traced_cell_of_a_scenario_column_starts_a_drill_down() -> None:
    block = summary_block()
    data: Any = SimpleNamespace(lang="en")
    traced, untraced = block.rows
    ref = drilldown.cell_ref(data, traced, block.columns[1], traced.cells[1])
    assert ref == drilldown.CellRef("Total area | S0 | typ", "S0", "S0.area.total", "typ")
    assert drilldown.cell_ref(data, untraced, block.columns[1], untraced.cells[1]) is None
    no_scenario = block.columns[1].model_copy(update={"scenario_id": None})
    assert drilldown.cell_ref(data, traced, no_scenario, traced.cells[1]) is None
