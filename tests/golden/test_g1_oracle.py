"""G1 golden oracle: T1.5 spreadsheet equals JSON, determinism, hand-checks of oracle formulas."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import numpy_financial as npf
import openpyxl
import pytest
import yaml
from tests.golden import build_golden, oracle

HERE = Path(__file__).resolve().parent
JSON_PATH = HERE / "golden_values.json"
XLSX_PATH = HERE / "golden_case.xlsx"


def _golden() -> dict[str, Any]:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _xlsx_rows(path: Path) -> dict[str, tuple[Any, Any]]:
    """key → (value, comment text) from every stage sheet (header 'key' in A1)."""
    wb = openpyxl.load_workbook(path)
    rows: dict[str, tuple[Any, Any]] = {}
    for ws in wb.worksheets:
        if ws["A1"].value != "key":
            continue
        for key_cell, value_cell in ws.iter_rows(min_row=2, max_col=2):
            assert key_cell.value not in rows, f"duplicate key {key_cell.value} in workbook"
            comment = value_cell.comment.text if value_cell.comment else None
            rows[str(key_cell.value)] = (value_cell.value, comment)
    return rows


def _same(a: Any, b: Any) -> bool:
    """Exact for str/bool/None/int; floats within 1e-12 (xlsx stores 16 significant digits)."""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
    return a == b


# --- T1.5 ----------------------------------------------------------------------------------------
def test_T1_5_golden_spreadsheet_equals_golden_json() -> None:
    """Every golden_values.json key appears once in golden_case.xlsx with the same value, and
    every value cell carries a comment naming its formula."""
    golden, rows = _golden(), _xlsx_rows(XLSX_PATH)
    assert set(rows) == set(golden)
    assert len(golden) > 600
    bad = [k for k, v in golden.items() if not _same(rows[k][0], v)]
    assert not bad, f"xlsx ≠ json for {bad[:10]}"
    no_comment = [k for k, (_, c) in rows.items() if not c or not c.strip()]
    assert not no_comment, f"value cells without a formula comment: {no_comment[:10]}"
    sheets = openpyxl.load_workbook(XLSX_PATH).sheetnames
    assert {"Explanation", "Inputs", "SKUs", "DailySeries", "Storage", "Labor", "Finance"} <= set(
        sheets
    )


def test_T1_5_build_is_deterministic_and_committed_files_are_current(tmp_path: Path) -> None:
    """Two builds give byte-identical files; the committed JSON equals a fresh build."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    build_golden.build(a)
    build_golden.build(b)
    for name in ("golden_values.json", "golden_case.xlsx"):
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
    fresh = json.loads((a / "golden_values.json").read_text(encoding="utf-8"))
    committed = _golden()
    assert set(fresh) == set(committed)
    stale = [k for k in fresh if not _same(fresh[k], committed[k])]
    assert not stale, f"golden_values.json is stale, rerun build_golden: {stale[:10]}"


def test_T1_5_golden_anchors_match_tiny_golden_readme() -> None:
    """Counts stated in tests/golden/tiny_golden/README.md (independent of the oracle)."""
    g = _golden()
    assert g["profile.n_lines"] == 1881  # shipped lines
    assert g["profile.operating_days"] == 26  # 31 days, no orders on Sundays
    assert g["eligibility.cube_asrs.n_skus_total"] == 100
    assert g["eligibility.cube_asrs.n_skus_eligible"] == 91  # 9 outside [600, 400, 300]
    assert g["stock.n_skus_in_stock"] == 90  # 10 SKUs with zero stock


def test_T1_5_golden_values_respect_spec_invariants() -> None:
    g = _golden()
    hourly = sum(g[f"design_day.hourly_lines.h{h:02d}"] for h in range(24))
    assert hourly == pytest.approx(g["design_day.lines"], abs=1e-6)  # T4.3
    assert g["design_day.lines"] == pytest.approx(
        g["daily.lines.p95"] * g["design_day.growth_factor"]
    )
    assert g["abc.lines.A.line_share"] >= 0.8  # T3.2
    assert sum(g[f"abc.lines.{c}.line_share"] for c in "ABC") == pytest.approx(1.0)
    for s in ("S0", "S2"):
        assert g[f"{s}.throughput.lambda_e"] + g[f"{s}.throughput.lambda_o"] == pytest.approx(
            g[f"{s}.throughput.lambda"]
        )
        # T6.10 guard: annual hours from the daily series < peak day × operating days per year
        assert g[f"{s}.labor.annual_hours.y1"] < g[f"{s}.labor.total.hours"] * 252
    assert g["S2.throughput.lambda_e"] == pytest.approx(
        g["S2.throughput.lambda"] * g["S2.eligibility.share_lines"]  # scenario EligibilityCfg
    )
    decant = g["S2.equipment.decant_port_load_peak_h"]  # F6b + I23: decant adds to the ports
    assert decant > 0
    assert g["S2.equipment.ports"] == math.ceil(g["S2.throughput.lambda_e"] / (350 * 0.85) + decant)
    assert g["S2.finance.npv"] == pytest.approx(
        npf.npv(0.08, [g[f"S2.finance.delta_cf.y{t}"] for t in range(6)])
    )


# --- hand-checkable formula units ----------------------------------------------------------------
def test_erlang_c_values() -> None:
    assert oracle.erlang_c(1, 0.5) == pytest.approx(0.5)  # M/M/1: P_wait = ρ
    assert oracle.erlang_c(2, 1.0) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        oracle.erlang_c(2, 2.0)


def test_erlang_wq_matches_mm1_closed_form() -> None:
    lam, mu = 8.0, 10.0  # M/M/1: W_q = ρ / (μ − λ)
    assert oracle.erlang_wq(1, lam, mu) == pytest.approx((lam / mu) / (mu - lam))


def test_payback_interpolation_and_edge_cases() -> None:
    assert oracle.payback([-100, 40, 40, 40]) == pytest.approx(2.5)  # T7.3
    assert oracle.payback([-100, 10, 10]) is None  # not reached
    assert oracle.payback([20, -5, -5]) == 0.0  # scenario cheaper than baseline


def test_npv_irr_against_numpy_financial() -> None:
    flows = [-1000.0, 300.0, 400.0, 500.0]
    assert oracle.npv(0.08, flows) == pytest.approx(npf.npv(0.08, flows))  # T7.2
    assert oracle.irr(flows) == pytest.approx(npf.irr(flows))
    assert oracle.irr([-10.0, -5.0, -5.0]) is None  # no sign change
    assert oracle.irr([-10.0, 30.0, -25.0]) is None  # two sign changes
    assert oracle.annuity_factor(0.08, 5) == pytest.approx(0.08 / (1 - 1.08**-5))


def test_levels_and_area_formulas() -> None:
    # pallet rack, 8.5 m: floor((8.5 − 0.6) / (1.4 + 0.15)) = floor(5.10) = 5 < 6
    assert oracle.levels(8.5 - 0.6, 1.55, 6) == 5
    # cube grid: floor((8.5 − 1.2) / 0.33) = 22 → capped at 20; at 7.0 m: floor(17.6) = 17
    assert oracle.levels(8.5 - 1.2, 0.33, 20) == 20
    assert oracle.levels(7.0 - 1.2, 0.33, 20) == 17
    assert oracle.levels(0.2, 0.33, 20) == 1  # F6 edge case: at least one level
    assert oracle.levels(2.1, 0.4, 5) == 5  # shelving: ergonomic cap
    assert oracle.class_area(76.0, 5, 0.38) == pytest.approx(40.0)


def test_T1_5_whole_pitch_clear_height_keeps_its_top_level(tmp_path: Path) -> None:
    """I63 (11): levels = floor with a 1e-9 tolerance. At 7.8 m the cube grid has (7.8 − 1.2) /
    0.33 = 20 levels on paper (19.999999999999996 in floats): 20 levels, no F_HEIGHT_LIMIT:cube_bin
    (I40 uses the same floor); a clear height 1 µm lower still loses the level."""
    assert (7.8 - 1.2) / 0.33 < 20  # the float trap the tolerance exists for
    assert oracle.fit_levels(7.8 - 1.2, 0.33) == oracle.levels(7.8 - 1.2, 0.33, 20) == 20
    assert oracle.fit_levels(7.8 - 1e-6 - 1.2, 0.33) == 19
    assert oracle.levels(7.8 - 0.6, 1.55, 6) == 4  # pallet rack: floor(4.65)
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    basis["building"]["clear_height_m"] = 7.8
    path = tmp_path / "basis.yaml"
    path.write_text(yaml.safe_dump(basis), encoding="utf-8")
    g = build_golden.run(basis_path=path)[0].values()
    assert g["S2.storage.cube_bin.levels"] == 20
    assert g["S0.storage.pallet_rack.levels"] == g["S2.storage.overflow.pallet_rack.levels"] == 4
    s2 = g["S2.flags"].split(",")
    assert "F_HEIGHT_LIMIT:cube_bin" not in s2 and "F_HEIGHT_LIMIT:pallet_rack" in s2
    g0 = _golden()  # 8.5 m: the cube grid is at its cap either way, so the grid area is equal
    assert g["S2.storage.cube_bin.grid_area_m2"] == g0["S2.storage.cube_bin.grid_area_m2"]


def test_positions_formulas() -> None:
    assert oracle.pallets_i(401, 400) == 2
    assert oracle.pallet_positions(44, 0.85, 16) == pytest.approx(44 / 0.85 + 16)
    assert oracle.shelf_bins_i(0.1, 0.04, 0.8) == 4  # ceil(0.1 / 0.032) = ceil(3.125)
    assert oracle.shelf_bins_i(0.0, 0.04, 0.8) == 1  # max(1, ...)
    assert oracle.cube_bins_i(0.005) == 0.25  # < 0.2 × 0.055 → mixed bin, 1/4
    assert oracle.cube_bins_i(0.05) == 2.0  # ceil(0.05 / (0.055 × 0.88))


def test_classification_formulas() -> None:
    assert oracle.fits((300, 600, 400), (600, 400, 300))  # T5.2 orientation-agnostic
    assert not oracle.fits((301, 600, 400), (600, 400, 300))
    assert oracle.manual_class(True, 0.1) == "shelving"
    assert oracle.manual_class(True, 0.3) == "pallet_rack"  # > 0.04 × 6
    assert oracle.manual_class(False, 0.01) == "pallet_rack"  # does not fit a shelf bin
    assert oracle.abc_classes([50, 30, 10, 5, 5]) == ["A", "A", "B", "B", "C"]
    assert oracle.is_pallet_order(400, 0.1, 300, 0.6)  # T3.5
    assert oracle.parcels_per_order(61, 30) == 3
    assert oracle.parcels_per_order(0.2, 30) == 1


def test_calendar_and_misc_formulas() -> None:
    assert oracle.operating_threshold(np.array([0.0, 10, 100, 200])) == pytest.approx(10.0)
    assert oracle.hours_between("15:00", "18:30") == 3.5
    assert oracle.hours_between("22:00", "02:00") == 4.0  # crossing midnight
    assert oracle.growth_factor(0.04, 5) == pytest.approx(1.04**5)
    assert oracle.ceil_div(0.0, 10) == 0
    assert oracle.ceil_div(10.01, 10) == 2
    assert oracle.docks(0.5, 1.0, 0.7) == 1
    assert oracle.shift_heads(0.5, 7.5, 0.85) == 1.0  # floor 1 per staffed activity
    assert oracle.shift_heads(0.0, 7.5, 0.85) == 0.0
    assert oracle.icpe_regime(400 * 8.5) is None  # below 5,000 m3
    assert oracle.icpe_regime(17000) == "Déclaration (D/DC)"
    stats = oracle.series_stats(np.array([1.0, 2, 3, 4]))
    assert stats["p50"] == 2.5
    assert stats["cv"] == pytest.approx(np.std([1, 2, 3, 4]) / 2.5)
