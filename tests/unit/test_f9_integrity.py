"""T9.4: the integrity checks IC1-IC8 pass on an untampered real run and each one FAILS on a
tampered fixture (the in-memory tables, the traces, the catalog or the HTML)."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from tests.unit.test_f9_tables_support import (
    baseline_scenario_run,
    column_index,
    find_row,
    number,
    private_run,
    report_data,
    with_cell,
)

from whsizing.errors import ReportIntegrityError
from whsizing.report import (
    ReportData,
    assert_integrity,
    check_integrity,
    export_trace,
    iter_cells,
)
from whsizing.report.integrity import IC1_TABLES
from whsizing.schemas import Cell, IntegrityIssue, TraceNode, Tracer
from whsizing.schemas.params import World
from whsizing.schemas.run import RunOutput


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9a_integrity")


@pytest.fixture(scope="module")
def data(run: RunOutput) -> ReportData:
    return report_data(run)


def ids(issues: list[IntegrityIssue]) -> set[str]:
    return {i.id for i in issues}


def retraced(
    data: ReportData,
    sid: str,
    drop: set[tuple[str, World]] = frozenset(),  # pyright: ignore[reportArgumentType]
    change: Mapping[tuple[str, World], dict[str, object]] | None = None,
) -> ReportData:
    """`data` with the trace of `sid` minus the `drop` nodes and with `change`d fields."""
    new = Tracer(sid)
    for n in data.tracers[sid].nodes:
        if (n.id, n.world) in drop:
            continue
        n2: TraceNode = n.model_copy(update=(change or {}).get((n.id, n.world), {}))
        new.record(n2.id, n2.label, n2.value, n2.unit, n2.formula, n2.inputs, n2.scope, n2.world)
    return dataclasses.replace(data, tracers={**data.tracers, sid: new})


# ------------------------------------------------------------------ untampered
def test_T9_4_untampered_real_run_passes_all_checks(run: RunOutput, data: ReportData) -> None:
    assert check_integrity(run) == []
    assert check_integrity(run, data=data) == []
    assert_integrity(run, data=data)  # no exception
    html = "<p>12 345</p><p>Surface</p>"
    assert check_integrity(run, html=html, data=data) == []


def test_T9_4_ic1_really_looks_at_hundreds_of_cells(data: ReportData) -> None:
    n = 0
    for name in IC1_TABLES:
        for block in data.tables[name].blocks:
            scenario = [i for i, c in enumerate(block.columns) if c.scenario_id]
            n += sum(
                1
                for r in block.rows
                for i in scenario
                if r.cells[i].trace_id and isinstance(r.cells[i].value, float)
            )
    assert n > 600


# ------------------------------------------------------------------ IC1
def test_T9_4_ic1_fails_on_a_numeric_cell_without_a_trace_id(
    run: RunOutput, data: ReportData
) -> None:
    bad = with_cell(data, "summary", "tco", 4, trace_id=None)
    issues = check_integrity(run, data=bad)
    assert ids(issues) == {"IC1"}
    assert issues[0].location == "summary/comparison/tco/S1.typ"
    assert "without a trace id" in issues[0].message


def test_T9_4_ic1_fails_when_the_trace_node_does_not_exist(
    run: RunOutput, data: ReportData
) -> None:
    bad = with_cell(data, "scenarios", "area.total", 4, trace_id="S0.area.nope")
    assert ids(check_integrity(run, data=bad)) == {"IC1"}
    # the node exists in the hi world too, but holds another value than the typical cell's
    wrong_world = with_cell(data, "fte", "fte.hours.total", 4, world="hi")
    issues = check_integrity(run, data=wrong_world)
    assert (
        ids(issues) == {"IC1"}
        and "differs from trace node S1.labor.total.hours" in issues[0].message
    )
    ghost = retraced(data, "S0", drop={("S0.finance.tco", "typ")})
    issues = [i for i in check_integrity(run, data=ghost) if i.id == "IC1"]
    assert {i.location for i in issues} >= {"summary/comparison/tco/S0.typ"}


def test_T9_4_ic1_fails_when_the_trace_node_holds_another_value(
    run: RunOutput, data: ReportData
) -> None:
    node = data.tracers["S1"].get("S1.capex.total", "typ")
    bad = retraced(data, "S1", change={("S1.capex.total", "typ"): {"value": node.value * 2}})
    issues = check_integrity(run, data=bad)
    assert ids(issues) <= {"IC1"} and issues
    assert any("differs from trace node S1.capex.total" in i.message for i in issues)
    wrong = with_cell(
        data,
        "summary",
        "capex",
        4,
        value=number(find_row(data.tables["summary"], "capex")[1].cells[4]) + 1,
    )
    assert "IC1" in ids(check_integrity(run, data=wrong))


# ------------------------------------------------------------------ IC2
def test_T9_4_ic2_fails_on_an_input_that_resolves_to_nothing(
    run: RunOutput, data: ReportData
) -> None:
    gone = retraced(data, "S0", drop={("S0.area.storage", "lo")})  # lo world only
    issues = [i for i in check_integrity(run, data=gone) if i.id == "IC2"]
    assert issues and all(i.location.startswith("trace S0/") for i in issues)
    assert any("S0.area.storage" in i.message and "(lo)" in i.message for i in issues)


def test_T9_4_ic2_fails_on_an_unknown_param_but_accepts_data_leaves(
    run: RunOutput, data: ReportData
) -> None:
    node = next(
        n for n in data.tracers["S2"].nodes if "param:cube_asrs.fill_factor" in n.inputs.values()
    )
    symbol = next(s for s, r in node.inputs.items() if r == "param:cube_asrs.fill_factor")
    bad = retraced(
        data,
        "S2",
        change={(node.id, node.world): {"inputs": {**node.inputs, symbol: "param:cube_asrs.nope"}}},
    )
    issues = check_integrity(run, data=bad)
    assert ids(issues) == {"IC2"} and "cube_asrs.nope" in issues[0].message
    leaf = retraced(
        data, "S2", change={(node.id, node.world): {"inputs": {**node.inputs, symbol: "data:x.y"}}}
    )
    assert check_integrity(run, data=leaf) == []  # a dataset-derived leaf is valid


# ------------------------------------------------------------------ IC3
def test_T9_4_ic3_fails_on_a_used_param_without_a_source(run: RunOutput, data: ReportData) -> None:
    pid = "cube_asrs.port_rate_lines_h"
    param = data.catalog.params[pid].model_copy(update={"source": " "})
    catalog = data.catalog.model_copy(update={"params": {**data.catalog.params, pid: param}})
    issues = check_integrity(run, data=dataclasses.replace(data, catalog=catalog))
    assert ids(issues) == {"IC3"} and issues[0].location == f"catalog/{pid}"


def test_T9_4_ic3_fails_when_the_todo_count_of_section_8_is_wrong(
    run: RunOutput, data: ReportData
) -> None:
    table = data.tables["methodology"]
    block = next(b for b in table.blocks if b.key == "methodology_limits")
    row = next(r for r in block.rows if r.key == "limit.gen.todo")
    label = row.label.model_copy(update={"args": {**row.label.args, "n": 0.0}})
    new_row = row.model_copy(update={"label": label})
    new_block = block.model_copy(update={"rows": [new_row if r is row else r for r in block.rows]})
    new = table.model_copy(
        update={"blocks": [new_block if b is block else b for b in table.blocks]}
    )
    bad = dataclasses.replace(data, tables={**data.tables, "methodology": new})
    issues = check_integrity(run, data=bad)
    assert ids(issues) == {"IC3"} and "TODO-source count" in issues[0].message


# ------------------------------------------------------------------ IC4 - IC7
def test_T9_4_ic4_fails_when_the_area_total_is_not_the_sum_of_the_zones(
    run: RunOutput, data: ReportData
) -> None:
    zone = find_row(data.tables["scenarios"], "area.zone.storage")[1].cells[4]
    bad = with_cell(data, "scenarios", "area.zone.storage", 4, value=number(zone) + 0.6)
    assert "IC4" in ids(check_integrity(run, data=bad))
    near = with_cell(data, "scenarios", "area.zone.storage", 4, value=number(zone) + 0.4)
    assert "IC4" not in ids(check_integrity(run, data=near))  # within the 0.5 m2 tolerance


def test_T9_4_ic5_fails_when_the_fte_total_is_not_the_sum_of_the_activities(
    run: RunOutput, data: ReportData
) -> None:
    cell = find_row(data.tables["fte"], "fte.heads.picking")[1].cells[4]
    bad = with_cell(data, "fte", "fte.heads.picking", 4, value=number(cell) + 1.0)
    issues = check_integrity(run, data=bad)
    assert "IC5" in ids(issues)
    assert any(i.id == "IC5" and i.location == "fte/heads/S1.typ" for i in issues)


def test_T9_4_ic6_fails_when_the_cumulative_is_not_the_sum_of_the_flows(
    run: RunOutput, data: ReportData
) -> None:
    table = data.tables["cash_flow"]
    col = column_index(table, "cash_flow", "S0.cumulative")
    cell = find_row(table, "cash.y3")[1].cells[col]
    bad = with_cell(data, "cash_flow", "cash.y3", col, value=number(cell) + 100.0)
    issues = check_integrity(run, data=bad)
    assert ids(issues) == {"IC6"} and issues[0].location == "cash_flow/cash.y3/S0"


def test_T9_4_ic7_fails_on_a_negative_area_hours_or_cost(run: RunOutput, data: ReportData) -> None:
    for table, row, col, unit in (
        ("scenarios", "area.zone.packing", 4, "m2"),
        ("fte", "fte.hours.picking", 4, "h"),
        ("capex_opex", "capex.total", 4, "eur"),
    ):
        bad = with_cell(data, table, row, col, value=-1.0)
        issues = [i for i in check_integrity(run, data=bad) if i.id == "IC7"]
        assert issues and f"unit {unit}" in issues[0].message, (table, row)


def test_T9_4_ic7_accepts_signed_flows_that_are_negative_by_nature(
    run: RunOutput, data: ReportData
) -> None:
    negatives = [
        c
        for _, c in iter_cells(data.tables)
        if c.unit == "eur" and isinstance(c.value, float) and c.value < 0
    ]
    assert negatives and all(c.signed for c in negatives)  # −capex, Δ and cumulative flows
    assert not any(i.id == "IC7" for i in check_integrity(run, data=data))
    unsigned = with_cell(data, "cash_flow", "cash.y0", 0, signed=False)
    assert "IC7" in ids(check_integrity(run, data=unsigned))


# ------------------------------------------------------------------ IC8
def test_T9_4_ic8_fails_on_a_missing_sentinel_in_the_rendered_html(
    run: RunOutput, data: ReportData
) -> None:
    html = (
        "<td>12</td><td>{{ missing:row.fit }}</td><p>{{ missing:flag.F_X }}</p>"
        "<td>{{ missing:row.fit }}</td>"
    )
    issues = check_integrity(run, html=html, data=data)
    assert ids(issues) == {"IC8"}
    assert [i.location for i in issues] == ["html", "html"]  # one issue per distinct sentinel
    assert {m for i in issues for m in ("row.fit", "flag.F_X") if m in i.message} == {
        "row.fit",
        "flag.F_X",
    }


def test_T9_4_ic8_without_html_fails_on_a_key_missing_in_a_language(
    run: RunOutput, data: ReportData
) -> None:
    bad = with_cell(
        data, "scenarios", "area.zone.storage", 0, value="zone.nope", fmt="key", unit=""
    )
    issues = check_integrity(run, data=bad)
    assert "IC8" in ids(issues)
    assert {i.message.split()[2] for i in issues if i.id == "IC8"} == {"zone.nope"}
    no_args = Cell(value="row.year", fmt="key")  # a placeholder with no value is as bad
    worse = with_cell(data, "summary", "fit", 0, **no_args.model_dump())
    assert "IC8" in ids(check_integrity(run, data=worse))


def test_T9_4_a_flag_code_without_a_message_fails_ic8(run: RunOutput, data: ReportData) -> None:
    table = data.tables["scenarios"]
    block, row = find_row(table, "flags.F_LOW_CONFIDENCE")
    new_row = row.model_copy(update={"label": Cell(value="flag.F_NEW_CODE", fmt="key")})
    new_block = block.model_copy(update={"rows": [new_row if r is row else r for r in block.rows]})
    new = table.model_copy(
        update={"blocks": [new_block if b is block else b for b in table.blocks]}
    )
    bad = dataclasses.replace(data, tables={**data.tables, "scenarios": new})
    assert any(
        i.id == "IC8" and "flag.F_NEW_CODE" in i.message for i in check_integrity(run, data=bad)
    )


# ------------------------------------------------------------------ assert_integrity
def test_T9_4_assert_integrity_raises_with_exit_code_5_and_lists_the_issues(
    run: RunOutput, data: ReportData
) -> None:
    bad = with_cell(data, "summary", "tco", 4, trace_id=None)
    with pytest.raises(ReportIntegrityError) as info:
        assert_integrity(run, data=bad)
    assert info.value.exit_code == 5
    assert "IC1 summary/comparison/tco/S1.typ" in str(info.value)
    with pytest.raises(ReportIntegrityError, match="IC8"):
        assert_integrity(run, "{{ missing:x }}", data=data)


# ------------------------------------------------------------------ fix round 1
def test_T9_4_ic7_covers_the_opex_by_year_cells(run: RunOutput, data: ReportData) -> None:
    """A negative annual opex, consistent between the cell and its trace node, is IC7 alone."""
    table = data.tables["capex_opex"]
    col = column_index(table, "opex_by_year", "S1.typ")
    cell = find_row(table, "opex.y1.labor")[1].cells[col]
    assert cell.unit == "eur" and cell.trace_id == "S1.opex.y1.labor"
    bad = with_cell(data, "capex_opex", "opex.y1.labor", col, value=-5.0)
    bad = retraced(bad, "S1", change={("S1.opex.y1.labor", "typ"): {"value": -5.0}})
    issues = check_integrity(run, data=bad)
    assert (
        ids(issues) == {"IC7"}
        and issues[0].location == "capex_opex/opex_by_year/opex.y1.labor/S1.typ"
    )
    assert "unit eur" in issues[0].message


def test_T9_4_ic7_reads_a_euro_cell_without_a_unit_as_euros(
    run: RunOutput, data: ReportData
) -> None:
    col = column_index(data.tables["capex_opex"], "opex_by_year", "S1.typ")
    bad = with_cell(data, "capex_opex", "opex.y1.labor", col, value=-5.0, unit="")
    assert "IC7" in ids(check_integrity(run, data=bad))


def test_T9_4_ic6_fails_when_a_cumulative_has_no_delta_column_to_sum(
    run: RunOutput, data: ReportData
) -> None:
    """A Δ column removed while its cumulative stays: the cumulative cannot be summed from the
    scenario's own flows instead (the other scenarios are against a baseline)."""
    table = data.tables["cash_flow"]
    block = table.blocks[0]
    drop = column_index(table, "cash_flow", "S1.delta")
    keep = [i for i in range(len(block.columns)) if i != drop]
    new_block = block.model_copy(
        update={
            "columns": [block.columns[i] for i in keep],
            "rows": [
                r.model_copy(update={"cells": [r.cells[i] for i in keep]}) for r in block.rows
            ],
        }
    )
    bad = dataclasses.replace(
        data, tables={**data.tables, "cash_flow": table.model_copy(update={"blocks": [new_block]})}
    )
    issues = check_integrity(run, data=bad)
    assert ids(issues) == {"IC6"} and issues[0].location == "cash_flow/S1"
    assert "Δ cash flow column" in issues[0].message


def test_T9_4_ic6_holds_with_a_scenario_as_the_baseline(run: RunOutput) -> None:
    run2 = baseline_scenario_run(run)
    data2 = report_data(run2)
    assert check_integrity(run2, data=data2) == []
    table = data2.tables["cash_flow"]
    col = column_index(table, "cash_flow", "S1.cumulative")
    cell = find_row(table, "cash.y2")[1].cells[col]
    bad = with_cell(data2, "cash_flow", "cash.y2", col, value=number(cell) + 100.0)
    assert ids(check_integrity(run2, data=bad)) == {"IC6"}


# ------------------------------------------------------------------ the exported trace (§2.6)
def test_T9_4_every_cited_trace_id_resolves_in_the_exported_trace(
    data: ReportData, tmp_path: Path
) -> None:
    """IC1 reads the in-memory tracers; the trace a reader gets is the exported file: every id the
    four IC1 tables cite must be a node of it, with the cell's value (`report.n_warnings`
    included: no scenario trace.jsonl holds that node)."""
    for sid in data.computed():  # the scenario files do not hold the report's node
        scenario_file = Path(data.run.run_dir) / data.run.results[sid].trace_path
        assert f"{sid}.report.n_warnings" not in scenario_file.read_text(encoding="utf-8")
    path = export_trace(data, tmp_path / "report" / "trace.jsonl")
    exported = Tracer.load_jsonl(path)
    nodes = {(n.id, n.world): n for n in exported.nodes}
    cited = 0
    for name in IC1_TABLES:
        for block in data.tables[name].blocks:
            for row in block.rows:
                for col, cell in zip(block.columns, row.cells, strict=False):
                    if col.scenario_id is None or cell.trace_id is None:
                        continue
                    node = nodes[(cell.trace_id, cell.world or "typ")]
                    assert node.value == pytest.approx(float(number(cell)))
                    assert node.scope == col.scenario_id
                    cited += 1
    assert cited > 100 and "S1.report.n_warnings" in {n.id for n in exported.nodes}
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(nodes)  # no duplicate line


def test_T9_4_the_exported_trace_is_reproducible_and_holds_every_scenario(
    data: ReportData, tmp_path: Path
) -> None:
    a = export_trace(data, tmp_path / "a.jsonl").read_bytes()
    assert export_trace(data, tmp_path / "b.jsonl").read_bytes() == a
    scopes = {n.scope for n in Tracer.load_jsonl(tmp_path / "a.jsonl").nodes}
    assert set(data.computed()) <= scopes
    assert not re.search(rb"\bnan\b", a, re.I)


def test_T9_4_export_trace_reports_an_unwritable_path_and_conflicting_nodes(
    data: ReportData, tmp_path: Path
) -> None:
    from whsizing.errors import WhsizingError

    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(WhsizingError, match="cannot write the trace"):
        export_trace(data, blocker / "trace.jsonl")
    tampered = retraced(data, "S1", change={("S1.report.n_warnings", "typ"): {"value": 99.0}})
    clash = Tracer("S0")  # S0 records the S1 node id with another value
    node = tampered.tracers["S1"].get("S1.report.n_warnings")
    clash.record(node.id, node.label, 1.0, node.unit, node.formula, node.inputs, "S0", "typ")
    both = dataclasses.replace(tampered, tracers={**tampered.tracers, "S0": clash})
    with pytest.raises(WhsizingError, match="traces disagree"):
        export_trace(both, tmp_path / "x.jsonl")
