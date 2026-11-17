"""F8a comparison table: T8.2 (every scenario once, every column), T8.6 (overlap note), rankings,
not-computed rows, warning and confidence-L counts. Built on the shared mock result / finance."""

from __future__ import annotations

import pytest
from tests.fixtures import mock_financial, mock_result, rng

from whsizing.errors import WhsizingError
from whsizing.scenarios import compare, not_computed_result, overlap_note, tco_overlaps
from whsizing.schemas import FinancialResult, Flag, Range, ScenarioResult


def scenario(
    sid: str,
    tco: tuple[float, float, float] = (8.5e6, 1.06e7, 1.38e7),
    payback: float | None = 4.2,
    flags: list[Flag] | None = None,
) -> tuple[ScenarioResult, FinancialResult]:
    base = mock_result()
    result = base.model_copy(
        update={
            "scenario": base.scenario.model_copy(update={"id": sid, "name": f"name {sid}"}),
            "flags": base.flags if flags is None else flags,
        }
    )
    fin = mock_financial().model_copy(
        update={"scenario_id": sid, "tco": rng(*tco, "eur"), "payback_years": payback}
    )
    return result, fin


def table(**specs: tuple[float, float, float]):
    pairs = {sid: scenario(sid, tco) for sid, tco in specs.items()}
    return compare({k: v[0] for k, v in pairs.items()}, {k: v[1] for k, v in pairs.items()})


def test_T8_2_one_row_with_every_column_of_the_f8_list() -> None:
    result, fin = scenario("S2")
    cmp = compare({"S2": result}, {"S2": fin}, "client_current")
    (row,) = cmp.rows
    assert cmp.baseline_id == "client_current"
    assert (row.scenario_id, row.name, row.family, row.status) == (
        "S2", "name S2", "cube_asrs", "computed",
    )  # fmt: skip
    assert row.eligible_line_share == result.eligibility.share_lines == 0.82
    assert row.storage_area_m2 == result.storage.total_area_m2
    assert row.total_area_m2 == result.area.total_m2 and row.fit is True
    assert row.equipment == result.equipment  # ports and robots of a cube scenario
    assert row.fte_design_day == result.labor.total_heads  # design-day heads
    assert row.core_fte_year1 == result.labor.core_fte[0]
    assert row.roster == result.labor.roster
    assert (row.capex, row.opex_year1, row.tco) == (fin.capex_total, fin.opex_year1, fin.tco)
    assert (row.npv_vs_baseline, row.payback_years) == (fin.npv_vs_baseline, 4.2)
    assert row.cost_per_line == fin.cost_per_line
    assert row.n_low_confidence_params == 21


def test_equipment_column_keeps_pickers_stations_ports_and_robots_only() -> None:
    result, fin = scenario("S1")
    equipment = {
        "pickers_peak": rng(5, 6, 8), "pickers.shelving": rng(1, 2, 3), "carts": rng(5, 6, 8),
        "forklifts": rng(1, 1, 2), "gtp_stations": rng(3, 4, 5), "robots": rng(10, 12, 15),
    }  # fmt: skip
    result = result.model_copy(update={"equipment": equipment})
    (row,) = compare({"S1": result}, {"S1": fin}).rows
    assert list(row.equipment) == ["pickers_peak", "gtp_stations", "robots"]


def test_warnings_count_warning_and_blocking_flags_not_info() -> None:
    flags = [
        Flag(code="F_NO_FIT", severity="blocking", message="m", value=12.0),
        Flag(code="F_DOCK_SHORTFALL", severity="warning", message="m"),
        Flag(code="F_SLA_RISK:packing", severity="warning", message="m"),
        Flag(code="F_RATIO_DRIFT:units", severity="info", message="m"),
        Flag(code="F_LOW_CONFIDENCE:30", severity="info", message="m", value=30.0),
    ]
    (row,) = compare({"S2": (r := scenario("S2", flags=flags))[0]}, {"S2": r[1]}).rows
    assert row.n_warnings == 3
    assert row.n_low_confidence_params == 30  # the `:<n>` suffix of I46 is matched by prefix
    quiet, fin = scenario("S3", flags=[])
    (row,) = compare({"S3": quiet}, {"S3": fin}).rows
    assert (row.n_warnings, row.n_low_confidence_params) == (0, 0)


def test_T8_2_every_scenario_appears_once_in_the_order_of_results() -> None:
    cmp = table(S2=(1, 2, 3), S0=(1, 2, 3), S1=(1, 2, 3))
    assert [r.scenario_id for r in cmp.rows] == ["S2", "S0", "S1"]


def test_T8_2_not_computed_scenario_keeps_its_row_with_the_reason() -> None:
    ok, fin = scenario("S0")
    stub = not_computed_result(mock_result().scenario.model_copy(update={"id": "S1"}), "why", 5000)
    assert stub.status == "not_computed" and stub.area.building_m2 == 5000 and not stub.area.fit
    cmp = compare({"S0": ok, "S1": stub}, {"S0": fin}, "S0")
    statuses = [(r.scenario_id, r.status) for r in cmp.rows]
    assert statuses == [("S0", "computed"), ("S1", "not_computed")]
    row = cmp.rows[1]
    assert row.status_reason == "why"
    assert row.tco is None and row.capex is None and row.fit is None and row.equipment == {}
    assert row.n_warnings == 0
    assert cmp.ranking_tco == ["S0"] and cmp.overlaps == [] and cmp.ranking_payback == ["S0"]


def test_computed_scenario_without_finance_is_an_error() -> None:
    result, _ = scenario("S0")
    with pytest.raises(WhsizingError, match="S0 is computed but has no FinancialResult"):
        compare({"S0": result}, {})


def test_T8_6_note_appears_iff_ranges_overlap() -> None:
    far = table(A=(1, 2, 3), B=(10, 11, 12))
    assert far.overlaps == [] and far.confidence_note == "Ranking at typical values"
    near = table(A=(1, 2, 5), B=(4, 6, 9))
    assert near.overlaps == [("A", "B")]
    assert near.confidence_note == "Ranking at typical values; ranges overlap for scenarios A and B"
    touching = table(A=(1, 2, 5), B=(5, 6, 9))  # closed intervals: a shared end overlaps
    assert touching.overlaps == [("A", "B")]
    many = table(A=(1, 2, 5), B=(4, 6, 9), C=(8, 9, 12), D=(20, 21, 22))
    assert many.overlaps == [("A", "B"), ("B", "C")]  # D is alone, A and C do not meet
    assert many.confidence_note == (
        "Ranking at typical values; ranges overlap for scenarios A and B; B and C"
    )
    assert "D" not in many.confidence_note
    assert overlap_note([]) == "Ranking at typical values"
    assert tco_overlaps({"A": Range(lo=1, typ=2, hi=3, unit="eur")}) == []


def test_rankings_are_ascending_at_typ_and_payback_none_is_left_out() -> None:
    specs = {
        "S0": ((1.0e6, 5.0e6, 9.0e6), None),  # the baseline: no payback
        "S1": ((1.0e6, 7.0e6, 9.0e6), 3.5),
        "S2": ((1.0e6, 6.0e6, 9.0e6), 2.0),
        "S3": ((1.0e6, 4.0e6, 9.0e6), None),  # not paid back within the horizon
    }
    pairs = {sid: scenario(sid, tco, pb) for sid, (tco, pb) in specs.items()}
    cmp = compare({k: v[0] for k, v in pairs.items()}, {k: v[1] for k, v in pairs.items()})
    assert cmp.ranking_tco == ["S3", "S0", "S2", "S1"]
    assert cmp.ranking_payback == ["S2", "S1"]


def test_there_is_no_recommended_label_anywhere() -> None:
    cmp = table(A=(1, 2, 5), B=(4, 6, 9))
    assert "recommend" not in cmp.model_dump_json().lower()
    assert not [f for f in type(cmp).model_fields if "recommend" in f]
