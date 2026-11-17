"""'Why this number?' (page 6): a report cell or trace id -> `Tracer.tree(id)` -> expandable tree.

The library expands a node down to its leaves: `param:` ids (catalog parameters) and `data:` ids,
which `Tracer.tree` reports as unresolved nodes and which this module relabels as dataset leaves
(inputs of the run: design-day values, flags). A Summary cell such as the NPV expands to more than
20 000 nodes (shared sub-results are repeated), so the page shows a depth- and size-limited tree
(`trim`) and lets the user re-root on any node that was cut (`frontier`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from whsizing.app.strings import tr
from whsizing.report import Lang, ReportData, render_cell
from whsizing.report.i18n import fmt_general, unit_label
from whsizing.schemas import Cell, TableColumn, TableRow
from whsizing.schemas.params import World

Tree = dict[str, Any]
DEFAULT_DEPTH = 4
MAX_DEPTH = 12
MAX_NODES = 300  # nested expanders beyond this make the page slow


@dataclass(frozen=True)
class CellRef:
    """A traced cell of the Summary table."""

    label: str
    scenario_id: str
    trace_id: str
    world: World


def cell_ref(data: ReportData, row: TableRow, col: TableColumn, cell: Cell) -> CellRef | None:
    """The traced cell at `row` x `col` of a scenario column (None: untraced, or no scenario)."""
    if cell.trace_id is None or col.scenario_id is None:
        return None
    world: World = cell.world or col.world or "typ"
    label = f"{render_cell(row.label, data.lang)} | {col.scenario_id} | {world}"
    return CellRef(label, col.scenario_id, cell.trace_id, world)


def cell_choices(data: ReportData) -> list[CellRef]:
    """Every Summary cell that carries a trace id (one per scenario, row and world)."""
    refs: dict[tuple[str, World], CellRef] = {}
    for block in data.tables["summary"].blocks:
        for row in block.rows:
            for col, cell in zip(block.columns, row.cells, strict=True):
                if (ref := cell_ref(data, row, col, cell)) is not None:
                    refs.setdefault((ref.trace_id, ref.world), ref)
    return list(refs.values())


def relabel(tree: Tree) -> Tree:
    """`data:` references (unresolved for the Tracer) become kind "dataset" leaves."""
    if tree["kind"] == "unresolved" and str(tree["id"]).startswith("data:"):
        return {**tree, "kind": "dataset"}
    if "inputs" in tree:
        return {**tree, "inputs": {sym: relabel(c) for sym, c in tree["inputs"].items()}}
    return tree


def node_tree(data: ReportData, scenario_id: str, trace_id: str, world: World = "typ") -> Tree:
    """The full tree of one trace node (`Tracer.tree`), `data:` leaves relabelled."""
    return relabel(data.tracers[scenario_id].tree(trace_id, world))


def leaves(tree: Tree) -> list[Tree]:
    if not tree.get("inputs"):
        return [tree]
    return [leaf for child in tree["inputs"].values() for leaf in leaves(child)]


def count_nodes(tree: Tree) -> int:
    return 1 + sum(count_nodes(c) for c in tree.get("inputs", {}).values())


def trim(tree: Tree, max_depth: int = DEFAULT_DEPTH, max_nodes: int = MAX_NODES) -> Tree:
    """The tree cut below `max_depth` levels and so that it holds at most `max_nodes` nodes; a
    cut node keeps its count of hidden inputs in "hidden" and has no "inputs"."""
    budget = [
        max_nodes - 1
    ]  # ponytail: one shared counter, depth-first: later siblings are cut first
    return _trim(tree, max_depth, budget)


def _trim(tree: Tree, depth: int, budget: list[int]) -> Tree:
    inputs: dict[str, Tree] = tree.get("inputs", {})
    if not inputs:
        return tree
    if depth <= 1 or budget[0] < len(inputs):
        return {k: v for k, v in tree.items() if k != "inputs"} | {"hidden": len(inputs)}
    budget[0] -= len(inputs)  # all the inputs of a node are shown, or none
    return {**tree, "inputs": {sym: _trim(c, depth - 1, budget) for sym, c in inputs.items()}}


def frontier(tree: Tree) -> list[str]:
    """Ids of the cut nodes of a trimmed tree: what the user can re-root on."""
    if tree.get("hidden"):
        return [str(tree["id"])]
    return [i for c in tree.get("inputs", {}).values() for i in frontier(c)]


# ------------------------------------------------------------------------------------ render
def render_tree(tree: Tree, data: ReportData, lg: Lang, symbol: str = "") -> None:
    """The tree as nested expanders; leaves are plain lines: `param` (with the catalog value),
    `dataset` (a `data:` input) or unresolved."""
    kind = tree["kind"]
    name = f"`{symbol}` " if symbol else ""
    if kind == "param":
        st.markdown(
            f"{name}**{tr('leaf_param', lg)}** `{tree['id']}`{_param_value(tree, data, lg)}"
        )
    elif kind == "dataset":
        st.markdown(f"{name}**{tr('leaf_dataset', lg)}** `{str(tree['id']).removeprefix('data:')}`")
    elif kind != "node":
        st.markdown(f"{name}**{tr('leaf_' + kind, lg)}** `{tree['id']}`")
    else:
        value = f"{fmt_general(float(tree['value']), lg)} {unit_label(str(tree['unit']))}".strip()
        title = f"{symbol + ' = ' if symbol else ''}{value} - {tree['label']}"
        with st.expander(title, expanded=not symbol):
            st.caption(f"`{tree['id']}`  |  {tree['formula']}")
            if tree.get("hidden"):
                st.caption(tr("hidden_inputs", lg, n=tree["hidden"]))
            for sym, child in tree.get("inputs", {}).items():
                render_tree(child, data, lg, sym)


def _param_value(tree: Tree, data: ReportData, lg: Lang) -> str:
    param = data.catalog.params.get(str(tree["id"]).removeprefix("param:"))
    if param is None:
        return ""
    unit = unit_label(param.unit)
    lo, typ, hi = (fmt_general(v, lg) for v in (param.min, param.typ, param.max))
    return f" = {typ} {unit} ({lo} - {hi}, {param.source})"
