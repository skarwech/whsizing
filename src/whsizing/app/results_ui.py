"""Page 6 building blocks (F10b): report tables as frames, the library's charts and block
diagrams, the 'why this number?' picker and the export buttons. Numbers are the report's own
(`ReportData.tables`, `render_cell`), never recomputed here."""

from __future__ import annotations

import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

import streamlit as st

import whsizing.report as report_api
from whsizing.app import demo, drilldown, state
from whsizing.app.calls import CliError, call, printed_paths
from whsizing.app.strings import tr
from whsizing.cli._runio import COMPARISON_FILE
from whsizing.cli.sizing import report_cmd
from whsizing.errors import WhsizingError
from whsizing.report import Lang, ReportData, build_diagram, chart_png, render_cell, unit_label
from whsizing.schemas import Cell, ReportTable, TableBlock, TableColumn, TableRow

PICK_BLOCK = "comparison"  # the Summary block whose cells start the drill-down
PICK_KEY = "summary.pick"
PICKED = "drill.picked"  # the selection of the table that was applied
DRILL_CELL, DRILL_TYPED = "drill.cell", "drill.typed"  # keys of the drill-down widgets
EXPORTS = (
    ("xlsx", "build_excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("pdf", "build_pdf", "application/pdf"),
)


# ------------------------------------------------------------------------------------ tables
def frame_columns(block: TableBlock, lg: Lang, all_worlds: bool) -> dict[str, int]:
    """Column name of `block_frame` -> index in `block.columns` (-1: the row labels). A column's
    name is its label with its group; lo and hi columns only with `all_worlds`."""
    head = render_cell(block.label_header, lg) if block.label_header else ""
    names = {head: -1}
    for i, col in enumerate(block.columns):
        if all_worlds or col.world in (None, "typ"):
            name = render_cell(col.label, lg)
            if col.group is not None:
                name = f"{render_cell(col.group, lg)} {name}"
            names[_unique(names, name)] = i
    return names


def block_frame(block: TableBlock, lg: Lang, all_worlds: bool) -> dict[str, list[str]]:
    """One block as columns of display text: the row labels, then one column per table column
    (lo and hi only with `all_worlds`). A row label carries the unit of its cells."""
    names = frame_columns(block, lg, all_worlds)
    frame: dict[str, list[str]] = {name: [] for name in names}
    for row in block.rows:
        units = {c.unit for c in row.cells if c.unit}
        for name, i in names.items():
            frame[name].append(
                _with_unit(render_cell(row.label, lg), units)
                if i < 0
                else render_cell(row.cells[i], lg)
            )
    return frame


def picked_cell(
    block: TableBlock, lg: Lang, all_worlds: bool, cells: list[tuple[int, str]]
) -> tuple[TableRow, TableColumn, Cell] | None:
    """The table cell a `st.dataframe` selection (row position, column name) of `block_frame`
    stands for; None when nothing is selected or it is a row label."""
    names = frame_columns(block, lg, all_worlds)
    for r, name in cells:
        if names.get(name, -1) >= 0 and 0 <= r < len(block.rows):
            row = block.rows[r]
            return row, block.columns[names[name]], row.cells[names[name]]
    return None


def _with_unit(label: str, units: set[str]) -> str:
    """`label [unit]` when the row has one unit and its label does not already say it
    ("Area (m2, with aisles)" does); no bracket for a unitless row."""
    if len(units) != 1:
        return label
    unit = unit_label(units.pop())
    if unit == "-" or re.search(rf"(?<!\w){re.escape(unit)}(?!\w)", label, re.IGNORECASE):
        return label
    return f"{label} [{unit}]"


def _unique(frame: Mapping[str, object], name: str) -> str:
    return name if name not in frame else f"{name} ({len(frame)})"


def show_table(
    table: ReportTable,
    lg: Lang,
    all_worlds: bool,
    keys: tuple[str, ...] | None = None,
    pick: ReportData | None = None,
) -> None:
    """The blocks of a report table (those named in `keys`, else all), and why a scenario column
    is empty (not computed). With `pick`, a cell of the block `PICK_BLOCK` can be clicked to start
    the drill-down from it (`pick_cell`)."""
    for block in (b for b in table.blocks if keys is None or b.key in keys):
        if block.title is not None:
            st.markdown(f"**{render_cell(block.title, lg)}**")
        if pick is not None and block.key == PICK_BLOCK:
            event = st.dataframe(
                block_frame(block, lg, all_worlds),
                hide_index=True,
                on_select="rerun",
                selection_mode="single-cell",
                key=f"{PICK_KEY}.{lg}.{all_worlds}",  # a new table (language, worlds): no selection
            )
            pick_cell(pick, block, lg, all_worlds, event["selection"]["cells"])
        else:
            st.dataframe(block_frame(block, lg, all_worlds), hide_index=True)
    reasons = {
        (c.scenario_id, c.disabled_reason)
        for b in table.blocks
        for c in b.columns
        if c.disabled_reason
    }
    for sid, reason in sorted(reasons, key=str):
        st.caption(tr("results.not_computed", lg, sid=sid, reason=reason))
    for note in table.notes:
        st.caption(render_cell(note, lg))


def pick_cell(
    data: ReportData,
    block: TableBlock,
    lg: Lang,
    all_worlds: bool,
    cells: list[tuple[int, str]],
) -> None:
    """A cell clicked in the Summary table becomes the cell of the drill-down below: its selectbox
    takes the cell and the typed trace id is cleared. A selection is applied once, so that the
    selectbox and the trace id stay usable after it (the table keeps showing the cell)."""
    hit = picked_cell(block, lg, all_worlds, cells)
    ref = drilldown.cell_ref(data, *hit) if hit else None
    if ref is None:
        st.session_state.pop(PICKED, None)
        return
    st.caption(tr("drill.picked", lg, cell=ref.label))
    if st.session_state.get(PICKED) == (cells, lg):
        return
    known = {(r.trace_id, r.world): r.label for r in drilldown.cell_choices(data)}
    st.session_state[DRILL_CELL] = known[(ref.trace_id, ref.world)]
    st.session_state[DRILL_TYPED] = ""
    st.session_state[PICKED] = (cells, lg)


# ------------------------------------------------------------------------- charts and diagrams
def chart(data: ReportData, chart_id: str, lg: Lang) -> None:
    """A chart of the report (PNG), or a note when the run has no data for it."""
    png = chart_png(data, chart_id)
    if png is None:
        st.info(tr("results.no_chart", lg))
    else:
        st.image(png)


def diagrams(data: ReportData) -> None:
    """The area block diagram of every computed scenario (SVG built in a temporary folder:
    looking at a run never writes into it)."""
    with tempfile.TemporaryDirectory() as tmp:
        for sid in data.computed():
            st.caption(f"{sid} - {data.run.results[sid].scenario.name}")
            try:
                st.image(build_diagram(data, sid, Path(tmp)).read_text(encoding="utf-8"))
            except WhsizingError as e:  # a plan too large to draw: the other scenarios still show
                state.error(str(e))


# ------------------------------------------------------------------------------------ export
def export_section(run: Path, lg: Lang) -> None:
    """comparison.json, and the Excel / PDF of the library when it provides them (F9b, F9c)."""
    comparison = run / COMPARISON_FILE
    st.download_button(
        tr("results.dl_comparison", lg),
        comparison.read_bytes(),
        "comparison.json",
        "application/json",
    )
    for suffix, builder, mime in EXPORTS:
        if getattr(report_api, builder, None) is None:  # F9b / F9c are built apart
            st.info(tr("results.unavailable", lg, kind=suffix.upper()))
            continue
        built = any((run / "report").glob(f"*_{lg}.{suffix}"))  # the library names them *_<lang>.*
        if (not (demo.demo_only() and built)) and st.button(
            tr("results.build", lg, kind=suffix.upper()), key=f"export.{suffix}"
        ):
            with st.spinner(tr("results.building", lg)):
                try:
                    done = call(report_cmd, run=run, lang=lg, formats=suffix)
                except CliError as e:
                    state.cli_error(e, lg)
                else:
                    st.success(", ".join(p.name for p in printed_paths(done, (f".{suffix}",))))
        for path in sorted((run / "report").glob(f"*.{suffix}")):
            st.download_button(path.name, path.read_bytes(), path.name, mime, key=f"dl.{path.name}")


# ---------------------------------------------------------------------------------- drill-down
def drill_down(data: ReportData, lg: Lang) -> None:
    """The cell clicked in the Summary table (`pick_cell`), else one picked here or a typed trace
    id: its `tracer.tree(id)` as an expandable tree."""
    choices = {ref.label: ref for ref in drilldown.cell_choices(data)}
    if not choices:
        st.info(tr("drill.none", lg))
        return
    ref = choices[st.selectbox(tr("drill.cell", lg), list(choices), key=DRILL_CELL)]
    typed = st.text_input(tr("drill.trace_id", lg), key=DRILL_TYPED).strip()
    sid = typed.split(".")[0] if typed else ref.scenario_id
    if sid not in data.tracers:
        st.error(tr("drill.unknown", lg, id=typed))
        return
    world = ref.world
    rkey = f"drill.root.{sid}.{typed or ref.trace_id}.{world}"
    root_id = st.session_state.get(rkey) or typed or ref.trace_id
    tree = drilldown.node_tree(data, sid, root_id, world)
    if tree["kind"] == "unresolved":
        st.error(tr("drill.unknown", lg, id=root_id))
        return
    depth = st.slider(
        tr("drill.depth", lg), 1, drilldown.MAX_DEPTH, drilldown.DEFAULT_DEPTH, key="drill.depth"
    )
    shown = drilldown.trim(tree, depth)
    st.caption(
        tr("drill.size", lg, total=drilldown.count_nodes(tree), shown=drilldown.count_nodes(shown))
    )
    options = ["", *drilldown.frontier(shown)]
    if root_id not in options:
        options.append(root_id)
    st.selectbox(
        tr("drill.reroot", lg), options, options.index(st.session_state.get(rkey, "")), key=rkey
    )
    drilldown.render_tree(shown, data, lg)
