"""T6.1 (storage, throughput, equipment part): the engine on tiny_golden equals the golden
spreadsheet (golden_values.json) within 0.5 % for S0 and S2, integers exact.

Built end to end: F3 build_tables → profile_from_tables, I58 sku_frame, F4 select_design_day
(sku=...), then the typ world of each scenario. Values are read back from the tracer by their
golden key (trace id), `eligibility.*` from the traced EligibilityResult, `bottleneck` from the
ThroughputWorld."""

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
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import ProfileCfg, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TOL = 0.005  # T1.5: 0.5 %
KEYS = re.compile(r"^(S0|S2)\.(storage|throughput|equipment|utilisation|eligibility|bottleneck)")


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    values = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    return {k: v for k, v in values.items() if KEYS.match(k)}


@pytest.fixture(scope="module")
def run() -> tuple[dict[str, Any], list[Tracer], Catalog]:
    """Engine value for every trace id of S0 and S2 (typ world), plus `<sid>.bottleneck`; the
    tracers; the catalog."""
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
    for scenario in scenarios:
        tracer = Tracer(scenario.id)
        inp = world_inputs(basis, design_day, scenario, catalog, sku, "typ", tracer)
        tp = size_throughput(inp, size_storage(inp))
        out |= {n.id: n.value for n in tracer.nodes}
        out[f"{scenario.id}.bottleneck"] = tp.bottleneck
        tracers.append(tracer)
    return out, tracers, catalog


@pytest.fixture(scope="module")
def engine(run: tuple[dict[str, Any], list[Tracer], Catalog]) -> dict[str, Any]:
    return run[0]


def same(engine: Any, golden: Any) -> bool:
    if isinstance(golden, str) or (isinstance(golden, int) and not isinstance(golden, bool)):
        return engine == golden  # bottleneck, counts, levels: exact
    if golden == 0:
        return abs(engine) < 1e-12
    return math.isclose(engine, golden, rel_tol=TOL)


def test_T6_1_storage_throughput_equipment_equal_golden(
    golden: dict[str, Any], engine: dict[str, Any]
) -> None:
    """Every golden key under S0./S2. storage, throughput, equipment, utilisation, eligibility
    and bottleneck has a trace node of that id with the golden value."""
    # 28 storage + 14 throughput + 18 equipment + 6 utilisation + 6 eligibility + 2 bottleneck
    assert len(golden) == 74
    missing = sorted(k for k in golden if k not in engine)
    assert not missing, f"no trace node for {missing}"
    bad = {k: (engine[k], v) for k, v in golden.items() if not same(engine[k], v)}
    assert not bad, f"engine vs golden: {bad}"


def test_T6_1_trace_inputs_resolve(run: tuple[dict[str, Any], list[Tracer], Catalog]) -> None:
    """F6f: every input of every node is a catalog id (`param:`), a named datum (`data:`) or
    another node of the same tracer and world, and every node is scoped to its scenario."""
    _, tracers, catalog = run
    known = set(catalog.params) | set(catalog.constants)
    for tracer in tracers:
        ids = {n.id for n in tracer.nodes}
        for n in tracer.nodes:
            assert n.scope == n.id.split(".")[0] and n.world == "typ", n.id
            for ref in n.inputs.values():
                if ref.startswith("param:"):
                    assert ref.removeprefix("param:") in known, (n.id, ref)
                elif not ref.startswith("data:"):
                    assert ref in ids, (n.id, ref)
