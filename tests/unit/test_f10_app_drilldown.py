"""F10b drill-down (T10.4): the tree of a trace node down to params and dataset leaves, the
trimming that keeps page 6 fast, and the re-root frontier, on a hand-built Tracer."""

from __future__ import annotations

from typing import Any

from whsizing.app import drilldown
from whsizing.schemas.trace import Tracer


def tracer() -> Tracer:
    """S.total = S.a + S.b; S.a reads a parameter and a dataset; S.b reads S.a (shared) too."""
    t = Tracer("S")
    t.record(
        "S.a",
        "A",
        4.0,
        "m2",
        "rate * lines",
        {"rate": "param:x.rate", "lines": "data:design_day.lines"},
    )
    t.record("S.b", "B", 2.0, "m2", "a / k", {"a": "S.a", "k": "param:x.k"})
    t.record("S.total", "Total", 6.0, "m2", "a + b", {"a": "S.a", "b": "S.b"})
    return t


def kinds(tree: dict[str, Any]) -> list[str]:
    return [leaf["kind"] for leaf in drilldown.leaves(tree)]


def test_T10_4_library_tree_reports_data_inputs_as_unresolved() -> None:
    raw = tracer().tree("S.total")
    leaves = {leaf["id"]: leaf["kind"] for leaf in drilldown.leaves(raw)}
    assert leaves["data:design_day.lines"] == "unresolved"  # what the library says
    assert leaves["param:x.rate"] == "param"


def test_T10_4_relabel_turns_data_inputs_into_dataset_leaves() -> None:
    tree = drilldown.relabel(tracer().tree("S.total"))
    assert set(kinds(tree)) == {"param", "dataset"}  # every leaf is a param or a dataset
    ids = {leaf["id"] for leaf in drilldown.leaves(tree) if leaf["kind"] == "dataset"}
    assert ids == {"data:design_day.lines"}
    assert tree["kind"] == "node" and tree["label"] == "Total"


def test_T10_4_an_unknown_node_stays_unresolved_after_relabel() -> None:
    tree = drilldown.relabel(tracer().tree("S.nothing"))
    assert tree == {"id": "S.nothing", "kind": "unresolved"}


def test_T10_4_trim_cuts_below_the_depth_and_counts_the_hidden_inputs() -> None:
    tree = drilldown.relabel(tracer().tree("S.total"))
    full = drilldown.count_nodes(tree)
    one = drilldown.trim(tree, max_depth=1)
    assert one["hidden"] == 2 and "inputs" not in one and drilldown.count_nodes(one) == 1
    two = drilldown.trim(tree, max_depth=2)
    assert drilldown.frontier(two) == ["S.a", "S.b"]  # both inputs have inputs of their own
    assert drilldown.count_nodes(two) < full
    assert drilldown.trim(tree, max_depth=drilldown.MAX_DEPTH) == tree  # deep enough: untouched


def test_T10_4_trim_stops_at_the_node_budget() -> None:
    tree = drilldown.relabel(tracer().tree("S.total"))
    cut = drilldown.trim(tree, max_depth=10, max_nodes=3)
    assert drilldown.count_nodes(cut) <= 3
    assert drilldown.frontier(cut)  # something was cut: the user can re-root there


def test_T10_4_trim_does_not_modify_the_tree_it_is_given() -> None:
    tree = drilldown.relabel(tracer().tree("S.total"))
    before = drilldown.count_nodes(tree)
    drilldown.trim(tree, max_depth=1)
    assert drilldown.count_nodes(tree) == before
