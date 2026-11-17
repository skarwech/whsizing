"""T6.3 (area budget, docks, queue): the engine on tiny_golden equals the golden spreadsheet
(golden_values.json) within 0.5 % for S0 and S2; integers and booleans exact.

Built end to end like the F6a golden test (F3 → I58 sku_frame → F4 → typ world of each
scenario → storage → throughput), then F6d / F6e. Unit-level inputs from outside F6d: the roster
is the golden `S*.labor.total.roster` (F6c, re-checked end to end by F6z) and `share_s` is the
profile's `eiq.single_line_share` (I15; size_scenario passes the equal F6c value). Values are
read from the tracer by their golden key; golden None values (`queue.*.c_min` of a stable pool)
must have no trace node and be None on the `QueueResource`."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from whsizing.catalog import Catalog, load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_storage, size_throughput, sku_frame, world_inputs
from whsizing.engine.area import AreaWorld, area_result, size_area
from whsizing.engine.queue import QueueWorld, queue_result, size_queue
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import ProfileCfg, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TOL = 0.005  # T1.5: 0.5 %
KEYS = re.compile(r"^(S0|S2)\.(area|docks|queue)\.")
VALUES = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return {k: v for k, v in VALUES.items() if KEYS.match(k)}


Run = tuple[dict[str, Any], list[Tracer], Catalog, dict[str, tuple[AreaWorld, QueueWorld]]]


@pytest.fixture(scope="module")
def run() -> Run:
    """Trace value per id (typ world) of S0 and S2, the tracers, the catalog, and the area and
    queue results per scenario."""
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    design_day = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    scenarios = load_yaml_model(HERE / "golden_scenarios.yaml", ScenarioSet).scenarios
    out: dict[str, Any] = {}
    tracers: list[Tracer] = []
    results: dict[str, tuple[AreaWorld, QueueWorld]] = {}
    for scenario in scenarios:
        tracer = Tracer(scenario.id)
        inp = world_inputs(basis, design_day, scenario, catalog, sku, "typ", tracer)
        st = size_storage(inp)
        tp = size_throughput(inp, st)
        roster = VALUES[f"{scenario.id}.labor.total.roster"]
        area = size_area(inp, st, tp, roster=roster, share_s=profile.eiq.single_line_share)
        results[scenario.id] = (area, size_queue(inp, tp, area))
        out |= {n.id: n.value for n in tracer.nodes}
        tracers.append(tracer)
    return out, tracers, catalog, results


def same(engine: Any, golden: Any) -> bool:
    if isinstance(golden, bool):
        return engine in (0.0, 1.0) and bool(engine) is golden
    if isinstance(golden, int):
        return engine == golden  # counts: exact
    if golden == 0:
        return abs(engine) < 1e-12
    return math.isclose(engine, golden, rel_tol=TOL)


def test_T6_3_area_docks_queue_equal_golden(golden: dict[str, Any], run: Run) -> None:
    """Every golden key under S0./S2. area, docks and queue has a trace node of that id with the
    golden value (None → no node, None on the QueueResource)."""
    engine, _, _, results = run
    # area 16 × 2 + docks 4 × 2 + queue.packing 10 × 2 + queue.ports 10 (S2)
    assert len(golden) == 70
    nones = {k for k, v in golden.items() if v is None}
    assert nones == {"S0.queue.packing.c_min", "S2.queue.packing.c_min", "S2.queue.ports.c_min"}
    for k in nones:
        sid, _, pool, field = k.split(".")
        resource = next(r for r in results[sid][1].resources if r.resource == pool)
        assert k not in engine and getattr(resource, field) is None, k
    missing = sorted(k for k in golden if k not in nones and k not in engine)
    assert not missing, f"no trace node for {missing}"
    bad = {
        k: (engine[k], v) for k, v in golden.items() if k not in nones and not same(engine[k], v)
    }
    assert not bad, f"engine vs golden: {bad}"


def test_T6_3_results_match_the_trace(golden: dict[str, Any], run: Run) -> None:
    """The returned AreaWorld / QueueWorld carry the traced values; flags as I46 (S2 does not fit,
    S0 does; no dock shortfall, no queue flag on the golden case); ICPE volume 410 × 8.5 is below
    the first regime."""
    engine, _, _, results = run
    for sid, (area, queue) in results.items():
        for zone, value in area.zones.items():
            assert value == engine[f"{sid}.area.{zone}"], (sid, zone)
        assert area.total_m2 == engine[f"{sid}.area.total"]
        assert (area.docks_in, area.docks_out) == (
            golden[f"{sid}.docks.in"],
            golden[f"{sid}.docks.out"],
        )
        assert area.icpe_volume_m3 == pytest.approx(410 * 8.5) and area.icpe_regime is None
        assert queue.flags == ()
        assert [r.resource for r in queue.resources] == (
            ["packing", "ports"] if sid == "S2" else ["packing"]
        )
    assert [f.code for f in results["S0"][0].flags] == []
    assert [f.code for f in results["S2"][0].flags] == ["F_NO_FIT"]
    s2 = area_result({"lo": results["S2"][0], "typ": results["S2"][0], "hi": results["S2"][0]})
    assert s2.fit is False and s2.deficit_m2.typ == pytest.approx(
        golden["S2.area.deficit_m2"], rel=TOL
    )
    assert (
        queue_result({w: results["S2"][1] for w in ("lo", "typ", "hi")}).resources[1].servers == 1
    )


def test_T6_3_trace_inputs_resolve(run: Run) -> None:
    """F6f: every input of every area / docks / queue node is a catalog id, a named datum or
    another node of the same tracer; `labor.total.roster` and `labor.single_line_share` are
    F6c's (not run here; resolved end to end by tests/golden/test_f6_size_golden.py)."""
    _, tracers, catalog, _ = run
    known = set(catalog.params) | set(catalog.constants)
    for tracer in tracers:
        ids = {n.id for n in tracer.nodes}
        for n in tracer.nodes:
            if not KEYS.match(n.id):
                continue
            for ref in n.inputs.values():
                if ref.startswith("param:"):
                    assert ref.removeprefix("param:") in known, (n.id, ref)
                elif not ref.startswith("data:") and ".labor." not in ref:
                    assert ref in ids, (n.id, ref)
