"""T6.1-T6.3 end to end through `size_scenario` (F6z): on tiny_golden, F3 build_tables →
profile_from_tables → I58 sku_frame → F4 select_design_day(sku=, catalog=) →
size_scenario(..., lines=t.lines) for S0 and S2 equals golden_values.json within 0.5 % on every
key under S0. / S2. storage, throughput, equipment, utilisation, eligibility, bottleneck, labor,
area (amenities from the real F6c roster), docks, queue, low_confidence_params and flags (the I46
string); integers, booleans and strings exact. Numbers are read from the typ-world trace by their
golden key; golden None (`queue.*.c_min` of a stable pool) → no node and None on the result."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from whsizing.catalog import load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_scenario, sku_frame
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import ProfileCfg, ScenarioResult, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TOL = 0.005  # T1.5: 0.5 %
GROUPS = {
    "T6.1": "storage|throughput|equipment|utilisation|eligibility|bottleneck",
    "T6.2": "labor",
    "T6.3": "area|docks|queue",
    "flags": "low_confidence_params|flags",
}
VALUES: dict[str, Any] = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
Run = dict[str, tuple[ScenarioResult, Tracer]]


def keys(group: str) -> dict[str, Any]:
    pattern = re.compile(rf"^(S0|S2)\.({GROUPS[group]})(\.|$)")
    return {k: v for k, v in VALUES.items() if pattern.match(k)}


@pytest.fixture(scope="module")
def run() -> Run:
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    out: Run = {}
    for s in load_yaml_model(HERE / "golden_scenarios.yaml", ScenarioSet).scenarios:
        tracer = Tracer(s.id)
        result = size_scenario(profile, basis, dd, s, catalog, sku, t.daily, tracer, lines=t.lines)
        out[s.id] = (result, tracer)
    return out


def engine_value(run: Run, key: str) -> Any:
    """Value of a golden key: bottleneck and flags from the ScenarioResult, numbers from the
    typ-world trace node of that id (None when there is no node)."""
    sid, field = key.split(".", 1)
    result, tracer = run[sid]
    if field == "bottleneck":
        return result.bottleneck
    if field == "flags":
        return ",".join(f.code for f in result.flags)
    nodes = {n.id: n.value for n in tracer.nodes if n.world == "typ"}
    return nodes.get(key)


def same(engine: Any, golden: Any) -> bool:
    if golden is None or isinstance(golden, str):
        return engine == golden
    if isinstance(golden, bool):
        return engine in (0.0, 1.0) and bool(engine) is golden
    if engine is None:
        return False
    if isinstance(golden, int):
        return engine == golden  # counts, levels: exact
    if golden == 0:
        return abs(engine) < 1e-12
    return math.isclose(engine, golden, rel_tol=TOL)


def mismatches(run: Run, golden: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    found = {k: engine_value(run, k) for k in golden}
    return {k: (found[k], v) for k, v in golden.items() if not same(found[k], v)}


def test_T6_1_storage_throughput_equipment_through_size_scenario(run: Run) -> None:
    """28 storage + 14 throughput + 18 equipment + 6 utilisation + 6 eligibility + 2
    bottleneck keys; the ScenarioResult carries the same values (storage classes, equipment
    Ranges, eligibility)."""
    golden = keys("T6.1")
    assert len(golden) == 74
    assert not mismatches(run, golden)
    s2, _ = run["S2"]
    cube = next(c for c in s2.storage.classes if c.storage_class == "cube_bin")
    assert same(cube.positions.typ, golden["S2.storage.cube_bin.positions"])
    assert cube.levels == golden["S2.storage.cube_bin.levels"]
    assert same(s2.equipment["ports"].typ, golden["S2.equipment.ports"])
    assert same(s2.eligibility.share_lines, golden["S2.eligibility.share_lines"])


def test_T6_2_labor_through_size_scenario(run: Run) -> None:
    """Every S0/S2 labor key (123 + 134): workloads, hours, heads, rosters, annual series, P50
    day, core heads and FTE, temp hours, with the daily packing split and zone lines from the
    shipped lines (I61, I66)."""
    golden = keys("T6.2")
    assert len(golden) == 257
    assert not mismatches(run, golden)
    for sid, (result, _) in run.items():
        assert same(result.labor.roster.typ, golden[f"{sid}.labor.total.roster"])
        assert same(result.labor.temp_hours[4].typ, golden[f"{sid}.labor.temp_hours.y5"])


def test_T6_3_area_docks_queue_through_size_scenario(run: Run) -> None:
    """70 area / docks / queue keys, amenities from the roster F6c computes in the same run
    (S2 does not fit: F_NO_FIT on the area result too); share_S is F6c's (one source)."""
    golden = keys("T6.3")
    assert len(golden) == 70
    assert not mismatches(run, golden)
    for sid, (result, tracer) in run.items():
        assert same(result.area.zones["amenities"].typ, golden[f"{sid}.area.amenities"])
        assert result.area.fit is golden[f"{sid}.area.fit"]
        rate = tracer.get(f"{sid}.area.pack_rate")
        assert rate.inputs["s_S"] == f"{sid}.labor.single_line_share"
        assert tracer.get(f"{sid}.labor.single_line_share").value == pytest.approx(0.6022727, 1e-6)
    pools = [r.resource for r in run["S2"][0].queue.resources]
    assert pools == ["packing", "ports"] and run["S2"][0].queue.resources[1].c_min is None
    assert [f.code for f in run["S2"][0].area.flags] == ["F_NO_FIT"]


def test_T6_1_flags_and_low_confidence_count_equal_golden(run: Run) -> None:
    """`S*.flags` as the I46 string (F6 flags, design-day flags, F_LOW_CONFIDENCE:<n>) and the
    I47 count: S0 = 30, S2 = 50; S0 reads no robot parking Param (I26), S2 the cube one."""
    golden = keys("flags")
    assert len(golden) == 4
    assert not mismatches(run, golden)
    for sid, (_, tracer) in run.items():
        params = tracer.get(f"{sid}.low_confidence_params").inputs
        assert len(params) == golden[f"{sid}.low_confidence_params"]
        assert ("cube_asrs.m2_per_robot_parking" in params) is (sid == "S2")
        assert not any(p.startswith("amr_gtp.") for p in params)
    s0_equipment = run["S0"][1].get("S0.area.equipment").inputs
    assert s0_equipment == {"maintenance_fixed_m2": "param:area.maintenance_fixed_m2"}
