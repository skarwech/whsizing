"""T7.1 golden finance: the engine on tiny_golden equals the golden spreadsheet
(golden_values.json) within 0.5 % (T1.5) for every `S0.` / `S2.` `capex.`, `opex.` and
`finance.` key (111 keys: per scenario 7 capex items + total, opex y1..y5 × (7 items + total),
and the finance keys: S0 annual_lines_y1, cost_per_line, tco; S2 the same + npv, irr,
payback_years, delta_cf.y0..y5). S2 is compared against S0 as baseline (I42); S0 is the
baseline itself (no S0.finance.npv key). Golden None is exact: `S2.finance.irr` and
`S2.finance.payback_years` (S2 never pays back) have no trace node and are None on the result.

Built end to end: F3 build_tables → profile_from_tables → I58 sku_frame → F4 select_design_day(
sku=, catalog=) → size_scenario(..., lines=t.lines) for S0 and S2 → compute_finance. Values are
read from the typ-world trace by their golden key; the FinancialResult is checked against the
same keys. Keys compared: the `KEYS` pattern below selects them all (no key is skipped)."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl
import pytest

from whsizing.catalog import load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_scenario, sku_frame
from whsizing.finance import compute_finance
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import FinancialResult, ProfileCfg, ScenarioResult, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
TOL = 0.005  # T1.5: 0.5 %
KEYS = re.compile(r"^(S0|S2)\.(capex|opex|finance)\.")
VALUES: dict[str, Any] = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
GOLDEN = {k: v for k, v in VALUES.items() if KEYS.match(k)}


class Run(NamedTuple):
    nodes: dict[str, float]  # typ-world trace nodes of S0 and S2
    fin: dict[str, FinancialResult]
    results: dict[str, ScenarioResult]
    tracers: dict[str, Tracer]


def same(engine: Any, golden: Any) -> bool:
    if golden is None:
        return engine is None
    if engine is None:
        return False
    if golden == 0:
        return abs(engine) < 1e-9
    return math.isclose(engine, golden, rel_tol=TOL)


@pytest.fixture(scope="module")
def run() -> Run:
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    results: dict[str, ScenarioResult] = {}
    tracers: dict[str, Tracer] = {}
    for s in load_yaml_model(HERE / "golden_scenarios.yaml", ScenarioSet).scenarios:
        tracers[s.id] = Tracer(s.id)
        results[s.id] = size_scenario(
            profile, basis, dd, s, catalog, sku, t.daily, tracers[s.id], lines=t.lines
        )
    fin = {
        "S0": compute_finance(
            results["S0"], basis, catalog, None, daily=t.daily, tracer=tracers["S0"],
            client_baseline=False,
        ),
        "S2": compute_finance(
            results["S2"], basis, catalog, results["S0"], daily=t.daily, tracer=tracers["S2"],
            baseline_tracer=tracers["S0"],
        ),
    }  # fmt: skip
    nodes = {n.id: n.value for tr in tracers.values() for n in tr.nodes if n.world == "typ"}
    return Run(nodes, fin, results, tracers)


def test_T7_1_golden_finance_equals_the_spreadsheet(run: Run) -> None:
    """Every golden capex / opex / finance key has a trace node of that id with the golden
    value (0.5 %); the two golden None keys have no node."""
    assert len(GOLDEN) == 111
    assert sum(v is None for v in GOLDEN.values()) == 2
    missing = sorted(k for k, v in GOLDEN.items() if v is not None and k not in run.nodes)
    assert not missing, f"no trace node for {missing}"
    bad = {k: (run.nodes.get(k), v) for k, v in GOLDEN.items() if not same(run.nodes.get(k), v)}
    assert not bad, f"engine vs golden: {bad}"


def test_T7_1_financial_result_carries_the_golden_values(run: Run) -> None:
    g = GOLDEN
    for sid, fin in run.fin.items():
        for item, rng in fin.capex.items():
            assert same(rng.typ, g[f"{sid}.capex.{item}"]), (sid, item)
        assert same(fin.capex_total.typ, g[f"{sid}.capex.total"])
        for t, row in enumerate(fin.opex_by_year, 1):
            for item, value in row.items():
                assert same(value, g[f"{sid}.opex.y{t}.{item}"]), (sid, t, item)
            assert same(sum(row.values()), g[f"{sid}.opex.y{t}.total"]), (sid, t)
        assert same(fin.opex_year1.typ, g[f"{sid}.opex.y1.total"])
        assert same(fin.tco.typ, g[f"{sid}.finance.tco"])
        assert same(fin.cost_per_line.typ, g[f"{sid}.finance.cost_per_line"])
    s2, s0 = run.fin["S2"], run.fin["S0"]
    assert s2.npv_vs_baseline is not None and same(s2.npv_vs_baseline.typ, g["S2.finance.npv"])
    assert all(
        same(x, g[f"S2.finance.delta_cf.y{t}"]) for t, x in enumerate(s2.delta_cash_flows_typ)
    )
    assert len(s2.delta_cash_flows_typ) == 6
    assert s2.irr_vs_baseline is None and s2.payback_years is None  # golden None, exact
    assert "S2.finance.irr" not in run.nodes and "S2.finance.payback_years" not in run.nodes
    assert s0.npv_vs_baseline is None and s0.irr_vs_baseline is None  # S0 is the baseline


def test_T7_1_golden_figures_discriminate_the_documented_rules(run: Run) -> None:
    """Spot checks that tie the golden numbers to the register (a wrong rule would break them):
    I30 S2 storage (bins × 40 + A_grid × 650), I31 contingency on the pre-contingency sum,
    I34 maintenance with the overflow carts and forklift, I32 energy kWh × 0.17, I33 labor
    growth ratio y2 / y1 = (1 + wage) × (1 + g) at fixed hours mix."""
    n = run.nodes
    assert n["S2.capex.storage"] == pytest.approx(
        n["S2.storage.cube_bin.positions"] * 40 + n["S2.storage.cube_bin.grid_area_m2"] * 650
    )
    parts = ("storage", "equipment", "controls", "building_works", "overflow",
             "integration_commissioning")  # fmt: skip
    assert n["S2.capex.contingency"] == pytest.approx(0.10 * sum(n[f"S2.capex.{p}"] for p in parts))
    assert n["S2.opex.y1.maintenance"] == pytest.approx(0.05 * 130_000 + 0.04 * (2 * 1500 + 35_000))
    assert n["S2.opex.y1.energy"] == pytest.approx((2 * 1200 + 1500 + 4500 + 20_000) * 0.17)
    assert n["S0.opex.y1.energy"] == pytest.approx((4500 + 20_000) * 0.17)
    assert n["S2.opex.y2.energy"] / n["S2.opex.y1.energy"] == pytest.approx(1.03)
    assert n["S2.finance.delta_cf.y0"] == pytest.approx(
        -(n["S2.capex.total"] - n["S0.capex.total"])
    )  # I42: Δcf_0 against the computed S0 capex, undiscounted
    assert n["S2.finance.npv"] == pytest.approx(
        sum(n[f"S2.finance.delta_cf.y{t}"] / 1.08**t for t in range(6))
    )
