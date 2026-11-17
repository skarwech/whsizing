"""I88 on a study the example run does not cover: several scenarios that override Params, one Param
overridden by two scenarios, a Param overridden by the client's basis and by a scenario, and one
overridden by the basis alone. The example run (S1 overrides one Param) cannot tell which scenario
column holds a value, nor which origin a Param that both the basis and a scenario override gets.

The run is the small example run with its `params_snapshot` and basis overrides replaced; the table
is rebuilt from it by `tables_data.assumptions`, and the PDF's Annex A view is the same block put
through `pdf_view.grid` with the columns the template drops."""

from __future__ import annotations

import dataclasses

import pytest
from tests.unit.test_f9_tables_support import report_data, small_run

from whsizing.report import ReportData
from whsizing.report.cells import EMPTY
from whsizing.report.pdf_view import box, grid
from whsizing.report.tables_data import assumptions
from whsizing.schemas import Cell, ReportTable

CLIENT_AND_S0 = "manual_p2p.pick_rate_shelving_lines_h"  # the example basis overrides it (62)
S1_ONLY = "amr_gtp.station_rate_lines_h"
S1_AND_S2 = "cube_asrs.port_rate_lines_h"
CLIENT_ONLY = "manual_p2p.pick_rate_pallet_lines_h"
OVERRIDES = {
    "S0": {CLIENT_AND_S0: 55.0},
    "S1": {S1_ONLY: 230.0, S1_AND_S2: 330.0},
    "S2": {S1_AND_S2: 280.0},
}
ORIGIN = {
    CLIENT_AND_S0: "origin.override",  # a scenario overrides it: the note says 'origin Override'
    S1_ONLY: "origin.override",
    S1_AND_S2: "origin.override",
    CLIENT_ONLY: "origin.client",
}


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> ReportData:
    base = report_data(small_run(tmp_path_factory))
    params = base.catalog.params
    assert {*ORIGIN, CLIENT_ONLY} <= set(params) and base.basis.overrides[CLIENT_AND_S0] == 62.0
    snap = {k: v for k, v in base.run.manifest.params_snapshot.items() if ":" not in k}
    snap[CLIENT_ONLY] = params[CLIENT_ONLY].typ * 1.1  # the basis override: typ x 1.1
    snap.update({f"{sid}:{pid}": v for sid, o in OVERRIDES.items() for pid, v in o.items()})
    manifest = base.run.manifest.model_copy(update={"params_snapshot": snap})
    basis = base.basis.model_copy(
        update={"overrides": {**base.basis.overrides, CLIENT_ONLY: snap[CLIENT_ONLY]}}
    )
    return dataclasses.replace(
        base, basis=basis, run=base.run.model_copy(update={"manifest": manifest})
    )


@pytest.fixture(scope="module")
def table(data: ReportData) -> ReportTable:
    return assumptions(data)


def test_I88_each_scenario_column_holds_the_values_of_that_scenario_only(
    data: ReportData, table: ReportTable
) -> None:
    block = table.blocks[0]
    keys = [c.key for c in block.columns]
    assert keys[-3:] == ["override.S0", "override.S1", "override.S2"]  # scenario order
    column = {sid: keys.index(f"override.{sid}") for sid in OVERRIDES}
    seen = 0
    for r in block.rows:
        pid = r.key.removeprefix("param.")
        for sid, i in column.items():
            wanted = OVERRIDES[sid].get(pid)
            assert r.cells[i].value == wanted, (sid, pid)
            if wanted is None:
                assert r.cells[i] == EMPTY
            else:
                assert r.cells[i].unit == data.catalog.params[pid].unit
                seen += 1
    assert seen == sum(map(len, OVERRIDES.values())) == 4
    assert [r.cells[1].value for r in block.rows if r.key == f"param.{S1_AND_S2}"] == [
        data.run.manifest.params_snapshot[S1_AND_S2]  # the base column is the plain key
    ]


def test_I88_a_param_overridden_by_a_scenario_has_the_origin_the_table_note_names(
    data: ReportData, table: ReportTable
) -> None:
    """The note says a scenario's value is an 'origin Override'; the row of a Param that the basis
    overrides too printed 'Client' (the basis value stays in the base column)."""
    origin = {r.key.removeprefix("param."): r.cells[9].value for r in table.blocks[0].rows}
    assert {pid: origin[pid] for pid in ORIGIN} == ORIGIN
    assert {v for pid, v in origin.items() if pid not in ORIGIN} == {"origin.default"}
    base = {r.key.removeprefix("param."): r.cells[1].value for r in table.blocks[0].rows}
    assert base[CLIENT_AND_S0] == 62.0  # the client's value, which S0's 55 replaces for S0 only
    assert base[CLIENT_ONLY] == data.basis.overrides[CLIENT_ONLY]


def test_I88_the_pdf_annex_puts_each_value_under_the_header_of_its_scenario(
    data: ReportData, table: ReportTable
) -> None:
    g = grid(table.blocks[0], "en", drop=["label", "note"], drop_empty=True)
    heads = [h.text for h in g.heads[-1]]
    column = {sid: heads.index(sid) for sid in OVERRIDES}
    assert sorted(column.values()) == list(range(g.width - 3, g.width))  # the last three columns
    lines = {ln.label: ln for ln in g.lines}
    assert len(lines) == len(data.catalog.params)
    for pid, ln in lines.items():
        for sid, i in column.items():
            wanted = OVERRIDES[sid].get(pid)
            shown = (
                ""
                if wanted is None
                else box(
                    Cell(value=wanted, fmt="num", unit=data.catalog.params[pid].unit), "en"
                ).text
            )
            assert ln.boxes[i].text == shown, (sid, pid)
