"""F9a report tables on a real small run (F1 data, F2-F8, sensitivity on): the structure of the
twelve tables, the T9.2 precondition (table values equal comparison.json, result.json and
finance.json, raw), the edge cases (scenario not computed, no baseline, no sensitivity) and
the limitations generated from the run."""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_f9_tables_support import (
    baseline_scenario_run,
    find_row,
    private_run,
    report_data,
)

from whsizing.errors import ConfigError
from whsizing.report import TABLE_IDS, ReportData, check_integrity, render_cell
from whsizing.scenarios.compare import compare, not_computed_result
from whsizing.schemas import Cell, ReportTable, TableRow
from whsizing.schemas.run import RunOutput

SCENARIOS = ("S0", "S1", "S2")
WORLDS = ("lo", "typ", "hi")


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return private_run(tmp_path_factory, "f9a_tables")


@pytest.fixture(scope="module")
def data(run: RunOutput) -> ReportData:
    return report_data(run)


def row_cells(table: ReportTable, row_key: str) -> list[Cell]:
    return find_row(table, row_key)[1].cells


def values(table: ReportTable, row_key: str, sid: str) -> list[float | str | None]:
    """The (lo, typ, hi) raw values of a row for one scenario."""
    i = SCENARIOS.index(sid) * 3
    return [c.value for c in row_cells(table, row_key)[i : i + 3]]


def rng(r: dict[str, Any]) -> list[float]:
    return [r["lo"], r["typ"], r["hi"]]


def typ(table: ReportTable, row_key: str, sid: str) -> float | str | None:
    return values(table, row_key, sid)[1]


def load(run: RunOutput, rel: str) -> dict[str, Any]:
    return json.loads((Path(run.run_dir) / rel).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ structure
def test_T9_2_twelve_tables_with_the_spec_names(data: ReportData) -> None:
    assert tuple(data.tables) == TABLE_IDS
    assert len(TABLE_IDS) == 12
    assert all(t.id == k for k, t in data.tables.items())
    assert data.run_id == data.run.manifest.run_id


def test_T9_2_every_row_has_one_cell_per_column_and_keys_are_unique(data: ReportData) -> None:
    for table in data.tables.values():
        for block in table.blocks:
            keys = [r.key for r in block.rows]
            assert len(keys) == len(set(keys)), (table.id, block.key)
            for row in block.rows:
                assert len(row.cells) == len(block.columns), (table.id, block.key, row.key)


def test_T9_2_scenario_tables_have_lo_typ_hi_columns_per_scenario(data: ReportData) -> None:
    for tid, block_key in (("summary", "comparison"), ("scenarios", "area"), ("fte", "hours")):
        block = next(b for b in data.tables[tid].blocks if b.key == block_key)
        assert [(c.scenario_id, c.world) for c in block.columns] == [
            (s, w) for s in SCENARIOS for w in WORLDS
        ]
        assert block.columns[0].group is not None and block.columns[0].group.value == (
            f"S0 · {data.run.results['S0'].scenario.name}"
        )


# ------------------------------------------------------------------ T9.2 precondition
def test_T9_2_summary_values_equal_comparison_json(run: RunOutput, data: ReportData) -> None:
    cmp = load(run, "comparison/comparison.json")
    table = data.tables["summary"]
    rng_rows = {
        "storage_area_m2": "storage_area", "total_area_m2": "total_area",
        "fte_design_day": "fte_design_day", "core_fte_year1": "core_fte_y1", "roster": "roster",
        "capex": "capex", "opex_year1": "opex_y1", "tco": "tco", "npv_vs_baseline": "npv",
        "cost_per_line": "cost_per_line",
    }  # fmt: skip
    scalar_rows = {
        "eligible_line_share": "eligible_share", "payback_years": "payback",
        "n_warnings": "n_warnings", "n_low_confidence_params": "n_low_confidence",
    }  # fmt: skip
    covered = {"scenario_id", "name", "family", "status", "status_reason", "equipment", "fit"}
    for jr in cmp["rows"]:
        sid = jr["scenario_id"]
        for field, row_key in rng_rows.items():
            assert values(table, row_key, sid) == rng(jr[field]), (sid, field)
        for field, row_key in scalar_rows.items():
            assert typ(table, row_key, sid) == jr[field], (sid, field)
        assert typ(table, "fit", sid) == float(jr["fit"])
        for eq, r in jr["equipment"].items():
            assert values(table, f"equipment.{eq}", sid) == rng(r), (sid, eq)
        covered |= set(rng_rows) | set(scalar_rows)
        assert set(jr) <= covered, sorted(set(jr) - covered)  # a new field needs a row
    assert [(c.scenario_id) for c in find_row(table, "tco")[0].columns][::3] == list(SCENARIOS)


def test_T9_2_scenario_tables_equal_result_json(run: RunOutput, data: ReportData) -> None:
    table, fte = data.tables["scenarios"], data.tables["fte"]
    for sid in SCENARIOS:
        r = load(run, f"scenarios/{sid}/result.json")
        for name, v in r["eligibility"].items():
            if isinstance(v, int | float):
                assert typ(table, f"eligibility.{name}", sid) == v, (sid, name)
        assert values(table, "storage.total_area_m2", sid) == rng(r["storage"]["total_area_m2"])
        for c in r["storage"]["classes"]:
            key = f"storage.{c['zone']}.{c['storage_class']}.positions"
            assert values(table, key, sid) == rng(c["positions"]), (sid, key)
        for k, v in r["equipment"].items():
            assert values(table, f"equipment.{k}", sid) == rng(v), (sid, k)
        for z, v in r["area"]["zones"].items():
            assert values(table, f"area.zone.{z}", sid) == rng(v), (sid, z)
        assert values(table, "area.total", sid) == rng(r["area"]["total_m2"])
        assert typ(table, "area.docks_in", sid) == r["area"]["docks_in_required"]
        assert typ(table, "area.fit", sid) == float(r["area"]["fit"])
        assert values(table, "area.deficit_m2", sid) == rng(r["area"]["deficit_m2"])
        lab = r["labor"]
        for a in lab["activities"]:
            for m in ("hours", "heads", "roster"):
                assert values(fte, f"fte.{m}.{a['activity']}", sid) == rng(a[m]), (sid, a, m)
        assert values(fte, "fte.hours.total", sid) == rng(lab["total_hours"])
        assert values(fte, "fte.heads.total", sid) == rng(lab["total_heads"])
        assert values(fte, "fte.roster.total", sid) == rng(lab["roster"])
        for name in ("annual_hours", "core_fte", "temp_hours"):
            for t, v in enumerate(lab[name], 1):
                assert values(fte, f"fte.{name}.y{t}", sid) == rng(v), (sid, name, t)


def test_T9_2_business_tables_equal_finance_json(run: RunOutput, data: ReportData) -> None:
    cx, cash = data.tables["capex_opex"], data.tables["cash_flow"]
    flows = next(b for b in cash.blocks if b.key == "cash_flow")
    for sid in SCENARIOS:
        f = load(run, f"scenarios/{sid}/finance.json")
        for item, v in f["capex"].items():
            assert values(cx, f"capex.{item}", sid) == rng(v), (sid, item)
        assert values(cx, "capex.total", sid) == rng(f["capex_total"])
        assert values(cx, "business.opex_y1", sid) == rng(f["opex_year1"])
        assert values(cx, "business.tco", sid) == rng(f["tco"])
        assert values(cx, "business.npv", sid) == rng(f["npv_vs_baseline"])
        assert typ(cx, "business.payback", sid) == f["payback_years"]
        for t, year in enumerate(f["opex_by_year"], 1):
            opex = next(b for b in cx.blocks if b.key == "opex_by_year")
            i = SCENARIOS.index(sid)
            for item, v in year.items():
                assert find_row(cx, f"opex.y{t}.{item}")[1].cells[i].value == v
            assert opex.rows  # the block is not empty
        col = {(c.scenario_id, c.kind): i for i, c in enumerate(flows.columns)}
        assert [r.cells[col[sid, "cash_flow"]].value for r in flows.rows] == f["cash_flows_typ"]
        assert [r.cells[col[sid, "delta"]].value for r in flows.rows] == f["delta_cash_flows_typ"]


def test_T9_2_numeric_cells_of_scenario_tables_are_raw_numbers_with_units(
    data: ReportData,
) -> None:
    area = row_cells(data.tables["scenarios"], "area.zone.storage")
    assert all(c.unit == "m2" and isinstance(c.value, float) for c in area)
    hours = row_cells(data.tables["fte"], "fte.hours.picking")
    assert {c.unit for c in hours} == {"h"}
    tco = row_cells(data.tables["summary"], "tco")
    assert {c.unit for c in tco} == {"eur"} and all(c.fmt == "eur" for c in tco)
    assert [c.world for c in tco[:3]] != [None] * 3  # worlds resolved by value


# ------------------------------------------------------------------ the other tables
def test_T9_2_assumptions_one_row_per_catalog_param_with_origin(data: ReportData) -> None:
    block = data.tables["assumptions"].blocks[0]
    assert len(block.rows) == len(data.catalog.params) == 72
    assert [c.key for c in block.columns] == [
        "label", "value_used", "unit", "min", "typ", "max", "source", "confidence",
        "validated_by", "origin", "note", "override.S1",
    ]  # fmt: skip
    rows = {r.key: r for r in block.rows}
    # example_basis.yaml overrides manual_p2p.pick_rate_shelving_lines_h with 62 (a client value)
    pid = "manual_p2p.pick_rate_shelving_lines_h"
    r = rows[f"param.{pid}"]
    assert r.cells[1].value == 62.0 and r.cells[9].value == "origin.client"
    assert rows["param.cube_asrs.port_rate_lines_h"].cells[9].value == "origin.default"
    # example_scenarios.yaml: S1 overrides amr_gtp.station_rate_lines_h with 230
    s1 = rows["param.amr_gtp.station_rate_lines_h"]
    assert s1.cells[9].value == "origin.override"
    assert s1.cells[1].value == 250.0 and s1.cells[11].value == 230.0  # base value, S1's value
    p = data.catalog.params["cube_asrs.port_rate_lines_h"]
    cells = rows["param.cube_asrs.port_rate_lines_h"].cells
    assert [c.value for c in cells[3:6]] == [p.min, p.typ, p.max] and cells[6].value == p.source


def test_I88_every_annex_a_value_equals_the_params_snapshot_of_the_scenario_it_is_quoted_for(
    data: ReportData,
) -> None:
    """The base column is the snapshot's plain key, a scenario column its `<sid>:<pid>` key; a
    scenario that does not override a Param has an empty cell (it used the base value)."""
    snap = data.run.manifest.params_snapshot
    block = data.tables["assumptions"].blocks[0]
    scenario_cols = {
        c.key.removeprefix("override."): i
        for i, c in enumerate(block.columns)
        if c.key.startswith("override.")
    }
    assert list(scenario_cols) == ["S1"]  # S0 and S2 override nothing: no column for them
    quoted = 0
    for r in block.rows:
        pid = r.key.removeprefix("param.")
        assert r.cells[1].value == snap[pid], pid
        for sid, i in scenario_cols.items():
            cell = r.cells[i]
            if cell.value is None:
                assert f"{sid}:{pid}" not in snap, (sid, pid)
            else:
                assert cell.value == snap[f"{sid}:{pid}"], (sid, pid)
                assert cell.unit == data.catalog.params[pid].unit and cell.fmt == "num"
                assert r.cells[9].value == "origin.override"  # the note says so
                quoted += 1
    overrides = {k for k in snap if ":" in k}
    assert quoted == len(overrides) == 1  # example_scenarios.yaml: S1 overrides one Param
    assert snap["S1:amr_gtp.station_rate_lines_h"] == 230.0 != snap["amr_gtp.station_rate_lines_h"]


def test_T9_2_blocks_name_the_header_of_their_label_column(data: ReportData) -> None:
    assert data.tables["assumptions"].blocks[0].label_header == Cell(value="col.id", fmt="key")
    assert data.tables["design_basis"].blocks[0].label_header is not None
    for block in data.tables["sensitivity"].blocks:
        assert block.label_header is not None


def test_T9_2_design_basis_lists_every_basis_field_with_its_origin(data: ReportData) -> None:
    block = data.tables["design_basis"].blocks[0]
    assert len(block.rows) == len(data.design_day.assumptions) >= 50
    by_key = {r.label.value: r for r in block.rows}
    assert by_key["operations.shifts_per_day"].cells[0].value == 2.0
    assert by_key["operations.shifts_per_day"].cells[2].value == "origin.client"
    assert by_key["building.area_m2"].cells[0].value == 12000.0


def test_T9_2_demand_profile_and_design_day_hold_the_profile_numbers(data: ReportData) -> None:
    p, d = data.profile, data.design_day
    daily = next(b for b in data.tables["demand_profile"].blocks if b.key == "profile_daily")
    lines = next(r for r in daily.rows if r.key == "daily.lines")
    assert [c.value for c in lines.cells] == [
        getattr(p.daily["lines"], s) for s in ("mean", "p50", "p90", "p95", "p98", "max", "cv")
    ]
    months = next(b for b in data.tables["demand_profile"].blocks if b.key == "profile_monthly")
    assert [r.cells[0].value for r in months.rows] == p.seasonality.monthly_index
    hourly = next(b for b in data.tables["design_day"].blocks if b.key == "dd_hourly")
    assert [r.cells[0].value for r in hourly.rows] == d.hourly_lines and len(hourly.rows) == 24
    metrics = next(b for b in data.tables["design_day"].blocks if b.key == "dd_metrics")
    lines_row = next(r for r in metrics.rows if r.key == "metric.lines")
    assert [c.value for c in lines_row.cells] == [d.lines, d.percentile_values["lines"]]


def test_T9_2_data_quality_table_holds_rules_coverage_and_dropped_rows(data: ReportData) -> None:
    t = data.tables["data_quality"]
    rules = next(b for b in t.blocks if b.key == "dq_rules")
    assert len(rules.rows) == len(data.dq.rules) > 15
    assert {r.cells[1].value for r in rules.rows} <= {
        f"severity.{s}" for s in ["ok", "info", "warning", "blocking"]
    }
    score = next(b for b in t.blocks if b.key == "dq_score")
    assert score.rows[0].cells[0].value == data.dq.score
    rows = next(b for b in t.blocks if b.key == "dq_rows")
    assert {r.key for r in rows.rows} == {f"dq.rows.{d.dataset}" for d in data.ingest.datasets}


def test_T9_2_methodology_counts_todo_and_confidence_l_parameters_it_used(
    data: ReportData,
) -> None:
    m = data.tables["methodology"]
    versions = next(b for b in m.blocks if b.key == "methodology_versions")
    got = {r.key: r.cells[0].value for r in versions.rows}
    assert got["method.run_id"] == data.run_id
    assert got["method.catalog_version"] == data.run.manifest.catalog_version
    assert got["method.n_todo_catalog"] == data.catalog.todo_count == 72
    limits = {
        r.key: r.label for r in next(b for b in m.blocks if b.key == "methodology_limits").rows
    }
    assert limits["limit.gen.todo"].args["n"] == got["method.n_todo_used"]
    assert limits["limit.gen.low_confidence"].args["n"] == got["method.n_low_confidence_used"]
    for sid in SCENARIOS:
        n = data.run.comparison.rows[SCENARIOS.index(sid)].n_low_confidence_params
        assert limits[f"limit.gen.confidence.{sid}"].args["n"] == n
    for sid in SCENARIOS:
        raised = [f.code for f in data.run.results[sid].flags if f.severity != "info"]
        assert (f"limit.gen.flags.{sid}" in limits) == bool(raised), sid
        if raised:
            assert limits[f"limit.gen.flags.{sid}"].args["flags"] == ", ".join(raised)
    formulas = render_cell(limits_formulas(m), "en")
    assert "NPV" in formulas and "Erlang-C" in formulas


def limits_formulas(m: ReportTable) -> Cell:
    return find_row(m, "formulas")[1].label


def test_T9_2_summary_notes_hold_the_banner_and_the_localised_confidence_note(
    data: ReportData,
) -> None:
    notes = data.tables["summary"].notes
    assert notes[0].value == "banner.indicative"
    overlaps = data.run.comparison.overlaps
    assert overlaps, "the small run has overlapping TCO ranges"
    assert notes[1].value == "summary.confidence.overlap"
    assert notes[1].args["pairs"] == "; ".join(f"{a} – {b}" for a, b in overlaps)
    assert "ranges overlap" not in render_cell(notes[1], "fr")  # not the English F8 string


def test_T9_2_sensitivity_table_holds_tornado_break_even_and_sweep(data: ReportData) -> None:
    s = data.run.sensitivity
    assert s is not None
    t = data.tables["sensitivity"]
    tornado, be, sweep = t.blocks
    assert len(tornado.rows) == len(s.tornado) and len(be.rows) == len(s.break_even)
    first = s.tornado[0]
    cells = tornado.rows[0].cells
    assert (cells[0].value, cells[3].value, cells[4].value) == (
        first.scenario_id,
        first.tco_low,
        first.tco_high,
    )
    assert len(sweep.rows) == len(s.percentile_sweep)
    for bar, row in zip(s.break_even, be.rows, strict=True):
        assert row.cells[1].value == bar.labor_cost_multiplier
        want = "sentence" if bar.labor_cost_multiplier is not None else "none"
        assert row.cells[2].value == f"sens.break_even.{want}", bar
        assert "{{ missing" not in render_cell(row.cells[2], "fr")


# ------------------------------------------------------------------ edge cases
def edited(run: RunOutput, **change: Any) -> RunOutput:
    return run.model_copy(update=change)


def test_edge_scenario_not_computed_gives_a_greyed_column_with_the_reason(
    run: RunOutput,
) -> None:
    reason = "SizingInfeasibleError: test"
    building = run.results["S1"].area.building_m2
    results = {
        **run.results,
        "S1": not_computed_result(run.results["S1"].scenario, reason, building),
    }
    finances = {k: v for k, v in run.finances.items() if k != "S1"}
    run2 = edited(
        run,
        results=results,
        finances=finances,
        comparison=compare(results, finances, run.comparison.baseline_id),
    )
    d = report_data(run2)
    for table_id in ("summary", "scenarios", "fte", "capex_opex"):
        for block in d.tables[table_id].blocks:
            cols = [i for i, c in enumerate(block.columns) if c.scenario_id == "S1"]
            if not cols:
                continue
            assert {block.columns[i].disabled_reason for i in cols} == {reason}
            for row in block.rows:
                assert all(row.cells[i].value is None for i in cols), (table_id, row.key)
    flows = d.tables["cash_flow"].blocks[0]
    assert [c.disabled_reason for c in flows.columns if c.scenario_id == "S1"] == [reason] * 2
    assert any(r.cells[0].value is not None for r in d.tables["summary"].blocks[1].rows)  # S0 kept
    lim = {r.key: r.label for r in d.tables["methodology"].blocks[1].rows}
    assert lim["limit.gen.not_computed.S1"].args["reason"] == reason
    assert check_integrity(run2, data=d) == []
    assert d.computed() == ["S0", "S2"]


def test_edge_no_baseline_shows_absolute_values_and_omits_npv_and_payback(
    run: RunOutput,
) -> None:
    finances = {
        k: v.model_copy(
            update={
                "npv_vs_baseline": None,
                "irr_vs_baseline": None,
                "payback_years": None,
                "delta_cash_flows_typ": [],
            }
        )
        for k, v in run.finances.items()
    }
    run2 = edited(run, finances=finances, comparison=compare(run.results, finances, None))
    d = report_data(run2)
    summary_rows = {r.key for r in d.tables["summary"].blocks[1].rows}
    assert {"tco", "capex", "opex_y1"} <= summary_rows
    assert not summary_rows & {"npv", "payback"}
    ranking = {r.key: r.cells[0].value for r in ranking_rows(d)}
    assert ranking == {"ranking.tco": " < ".join(run2.comparison.ranking_tco)}  # no empty row
    business = {r.key for r in find_row(d.tables["capex_opex"], "business.tco")[0].rows}
    assert "business.npv" not in business and "business.payback" not in business
    flows = d.tables["cash_flow"].blocks[0]
    assert {c.kind for c in flows.columns} == {"cash_flow", "cumulative"}  # no Δ columns
    cum = [r.cells[1].value for r in flows.rows]  # S0 cumulative of its own (negative) flows
    assert cum[-1] == pytest.approx(sum(finances["S0"].cash_flows_typ))
    lim = {r.key for r in d.tables["methodology"].blocks[1].rows}
    assert "limit.gen.no_baseline" in lim
    assert check_integrity(run2, data=d) == []


def test_edge_no_sensitivity_leaves_the_table_empty_with_a_note(run: RunOutput) -> None:
    d = report_data(edited(run, sensitivity=None))
    t = d.tables["sensitivity"]
    assert t.blocks == [] and t.notes[0].value == "sensitivity.not_run"


def test_edge_a_run_folder_without_the_profile_is_a_config_error(
    run: RunOutput, tmp_path: Path
) -> None:
    from whsizing.errors import ConfigError

    with pytest.raises(ConfigError, match="not a finished run folder"):
        report_data(edited(run, run_dir=tmp_path))


# ------------------------------------------------------------------ fix round 1
def test_T9_2_every_euro_cell_carries_the_eur_unit(data: ReportData) -> None:
    """IC7 reads the unit: a euro cell without one (the opex by year once) escaped it."""
    from whsizing.report import iter_cells

    euros = [(w, c) for w, c in iter_cells(data.tables) if c.fmt == "eur" and c.value is not None]
    assert len(euros) > 300
    assert [w for w, c in euros if c.unit != "eur"] == []
    opex = find_row(data.tables["capex_opex"], "opex.y1.labor")[1].cells
    assert {c.unit for c in opex if c.value is not None} == {"eur"}


def test_T9_2_cash_flow_without_baseline_scenario_keeps_every_cumulative_column(
    data: ReportData,
) -> None:
    flows = data.tables["cash_flow"].blocks[0]
    kinds = {(c.scenario_id, c.kind) for c in flows.columns}
    assert {(s, k) for s in SCENARIOS for k in ("cash_flow", "delta", "cumulative")} == kinds
    assert data.tables["cash_flow"].notes == []  # the client's operation is the baseline


def test_T9_2_cash_flow_baseline_scenario_has_no_cumulative_of_its_own_cost(
    run: RunOutput,
) -> None:
    """With S0 as the baseline the cumulative columns are all cumulative Δ: S0 shows its own cash
    flow only (it was the cumulative of its own cost beside the Δ of the others)."""
    run2 = baseline_scenario_run(run)
    d = report_data(run2)
    flows = d.tables["cash_flow"].blocks[0]
    col = {(c.scenario_id, c.kind): i for i, c in enumerate(flows.columns)}
    assert ("S0", "cumulative") not in col and ("S0", "delta") not in col
    assert ("S0", "cash_flow") in col
    for sid in ("S1", "S2"):
        delta = run2.finances[sid].delta_cash_flows_typ
        got = [r.cells[col[sid, "cumulative"]].value for r in flows.rows]
        want = [sum(delta[: t + 1]) for t in range(len(delta))]
        assert got == pytest.approx(want), sid
    note = d.tables["cash_flow"].notes[0]
    assert note.value == "cash.baseline_scenario" and note.args == {"baseline": "S0"}
    assert check_integrity(run2, data=d) == []


def test_T9_2_payback_not_reached_is_said_not_left_empty(run: RunOutput) -> None:
    run2 = baseline_scenario_run(run, payback_none=("S1",))
    d = report_data(run2)
    for table, key in (("summary", "payback"), ("capex_opex", "business.payback")):
        cells = row_cells(d.tables[table], key)
        assert [c.value for c in cells[3:6]] == [None, "payback.not_reached", None]  # S1
        assert cells[7].value == run2.finances["S2"].payback_years  # S2 reached it
        assert cells[1].value is None  # the baseline itself: no payback, nothing to say
        for lang in ("fr", "en"):
            assert "{{ missing" not in render_cell(cells[4], lang)
    assert render_cell(row_cells(d.tables["summary"], "payback")[4], "en") == (
        "not reached within the horizon"
    )
    assert check_integrity(run2, data=d) == []


def test_T9_2_finance_notes_are_shown_in_capex_opex_and_in_the_limitations(
    run: RunOutput, data: ReportData
) -> None:
    notes = {n for f in run.finances.values() for n in f.notes}
    assert notes  # the client baseline scope (I73 b) at least
    shown = [str(c.value) for c in data.tables["capex_opex"].notes]
    limits = {r.key: str(r.label.value) for r in data.tables["methodology"].blocks[1].rows}
    in_limits = [v for k, v in limits.items() if k.startswith("limit.gen.finance.")]
    for note in notes:
        assert any(note in s for s in shown), note
        assert any(note in s for s in in_limits), note
    assert len(shown) == len(notes)  # each distinct note once, with the scenarios it applies to
    assert all(s.startswith("S0, S1, S2: ") for s in shown if "client's current" in s)


def test_T9_2_a_note_of_one_scenario_names_it(run: RunOutput) -> None:
    finances = {
        k: v.model_copy(update={"notes": ["IRR is None: no sign change"] if k == "S1" else []})
        for k, v in run.finances.items()
    }
    d = report_data(edited(run, finances=finances))
    assert [c.value for c in d.tables["capex_opex"].notes] == ["S1: IRR is None: no sign change"]


def test_T9_2_flag_counts_show_as_integers(data: ReportData) -> None:
    cells = [c for c in row_cells(data.tables["scenarios"], "flags.F_LOW_CONFIDENCE") if c.value]
    assert cells and all(c.fmt == "int" for c in cells)
    assert all(render_cell(c, "en").isdigit() for c in cells)  # "30", not "30.00"


@pytest.mark.parametrize("band", ["usable", "usable with caveats", "remediation needed"])
def test_T9_2_the_data_quality_limit_is_translated_in_both_languages(
    data: ReportData, band: str
) -> None:
    from whsizing.report.tables_data import methodology

    d2 = dataclasses.replace(data, dq=data.dq.model_copy(update={"band": band}))
    limit = next(r for r in methodology(d2).blocks[1].rows if r.key == "limit.gen.dq")
    fr, en = render_cell(limit.label, "fr"), render_cell(limit.label, "en")
    assert "{{ missing" not in fr + en
    assert band in en.lower()
    assert render_cell(Cell(value=f"dq.band.{band}", fmt="key"), "fr").lower() in fr.lower()
    assert band not in fr.lower()  # no English band code in the French report


def test_T9_2_no_baseline_at_all_is_not_the_clients_current_operation(run: RunOutput) -> None:
    finances = {
        k: v.model_copy(update={"npv_vs_baseline": None, "payback_years": None})
        for k, v in run.finances.items()
    }
    d = report_data(edited(run, finances=finances, comparison=compare(run.results, finances, None)))
    study = {r.key: r.cells[0] for r in d.tables["summary"].blocks[0].rows}
    assert study["baseline"].value == "baseline.none"
    assert render_cell(study["baseline"], "en") != render_cell(
        Cell(value="baseline.client_current", fmt="key"), "en"
    )
    assert report_data(run).tables["summary"].blocks[0].rows[-1].cells[0].value == (
        "baseline.client_current"
    )


# ------------------------------------------------------------------ errors are WhsizingError
def copied_run(run: RunOutput, tmp_path: Path) -> RunOutput:
    shutil.copytree(run.run_dir, tmp_path / "run")
    return run.model_copy(update={"run_dir": tmp_path / "run"})


def test_edge_an_unsupported_language_is_a_config_error(run: RunOutput) -> None:
    with pytest.raises(ConfigError, match="unsupported language 'de'"):
        report_data(run, "de")


@pytest.mark.parametrize(
    ("rel", "needle"),
    [
        ("scenarios/S1/trace.jsonl", "trace"),
        ("design/design_day.json", "DesignDay"),
        ("dq/dq_report.json", "DQReport"),
        ("canonical/daily_series.parquet", "daily series"),
    ],
)
def test_edge_a_corrupt_run_file_is_a_config_error_naming_it(
    run: RunOutput, tmp_path: Path, rel: str, needle: str
) -> None:
    run2 = copied_run(run, tmp_path)
    path = Path(run2.run_dir) / rel
    assert path.is_file(), rel
    path.write_bytes(path.read_bytes()[: max(10, path.stat().st_size // 3)])  # truncated
    with pytest.raises(ConfigError, match=needle) as info:
        report_data(run2)
    assert str(path) in str(info.value)


def test_edge_n_warnings_node_recorded_upstream_is_kept(data: ReportData, run: RunOutput) -> None:
    """The node is the report's own only until F6 / F8 record the count: theirs stands."""
    from whsizing.report.data import _record_n_warnings

    tracer = data.tracers["S1"]
    before = tracer.get("S1.report.n_warnings")
    assert before.value == run.comparison.rows[1].n_warnings
    _record_n_warnings(tracer, "S1", run.results["S1"])  # a second call must not raise
    assert tracer.get("S1.report.n_warnings") == before


def ranking_rows(d: ReportData) -> list[TableRow]:
    return next(b for b in d.tables["summary"].blocks if b.key == "ranking").rows


def test_edge_payback_not_reached_leaves_out_the_payback_ranking_row(run: RunOutput) -> None:
    """The ranking by payback was a row with an empty string when no scenario had a payback."""
    run2 = baseline_scenario_run(run, payback_none=("S1", "S2"))
    assert run2.comparison.ranking_payback == []
    assert {r.key for r in ranking_rows(report_data(run2))} == {"ranking.tco"}
    assert {r.key for r in ranking_rows(report_data(run))} == {"ranking.tco", "ranking.payback"}
