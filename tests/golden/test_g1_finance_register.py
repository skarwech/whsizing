"""G1f: register I29-I37, I42 and I48 against the golden oracle and the F7 engine. Part of T1.5.

The register formulas are written out here a third time, from `docs/INTERPRETATIONS.md` and the
catalog YAML files alone (no `oracle.py` constants, no `whsizing`), and must reproduce every
S0 / S2 `capex.*`, `opex.*` and `finance.*` golden key. I37 / I42 metrics and the I48 degenerate
cube scenario are compared between the oracle and the engine (`whsizing.finance`).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy_financial as npf  # pyright: ignore[reportMissingTypeStubs]
import polars as pl
import pytest
import yaml
from tests.golden import build_golden, oracle

from whsizing.catalog import load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_scenario, sku_frame
from whsizing.finance import compute_finance, irr, npv, payback
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import ProfileCfg, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parents[1] / "catalog"
GROUPS = ("capex", "opex", "finance")
ITEMS = ("storage", "equipment", "controls", "building_works", "overflow",
         "integration_commissioning")  # fmt: skip
OPEX = ("labor", "maintenance", "energy", "software", "consumables", "rent", "renewal")
FORKLIFT = {"receiving", "put_away", "replenishment", "shipping_pallet"}  # I33 roles
COST_KEY = {"operator": "operator", "forklift": "forklift_driver", "lead": "team_leader"}
YEARS = range(1, 6)


def _golden() -> dict[str, Any]:
    return json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))


def _typ(family: str) -> dict[str, float]:
    """Typ value (or scalar) of every capex / opex / life entry of a family file, by short name."""
    d = yaml.safe_load((CATALOG / "families" / f"{family}.yaml").read_text(encoding="utf-8"))
    return {
        k: v["typ"] if isinstance(v, dict) else v
        for section in ("capex", "opex", "life")
        for k, v in d[section].items()
    }


def _finance_defaults() -> dict[str, float]:
    d = yaml.safe_load((CATALOG / "finance_defaults.yaml").read_text(encoding="utf-8"))
    return {
        "packaging": d["packaging_eur_per_order"]["typ"],
        "kwh_station": d["kwh_per_station_year"]["typ"],
        "fixed_kwh": d["fixed_energy_kwh_year"],
        **{f"cost_{r}": c for r, c in d["default_roles_cost_eur_h"].items()},
    }


def _manual_zone(
    g: dict[str, Any], sid: str, zone: str, m: dict[str, float]
) -> tuple[float, float]:
    """I29: (storage, equipment) of the manual formulas on the manual classes of `zone`."""
    st = g[f"{sid}.storage.{zone}pallet_rack.positions"] * m["per_pallet_position_eur"]
    st += g[f"{sid}.storage.{zone}shelving.positions"] * m["per_shelf_bin_eur"]
    eq = g[f"{sid}.equipment.carts"] * m["per_cart_eur"]
    return st, eq + g[f"{sid}.equipment.forklifts"] * m["per_forklift_eur"]


def expected_capex(g: dict[str, Any], sid: str, auto: bool) -> dict[str, float]:
    """I29 (manual), I30 (cube), I31 (shares) in the typical world."""
    m, cu = _typ("manual_p2p"), _typ("cube_asrs")
    zone = "overflow." if auto else ""
    m_storage, m_equipment = _manual_zone(g, sid, zone, m)
    works = g[f"{sid}.area.total"] * m["building_works_per_m2_eur"]
    if not auto:
        items = {
            "storage": m_storage,
            "equipment": m_equipment,
            "controls": m["wms_adaptation_fixed_eur"],
        }
        items |= {"building_works": works, "overflow": 0.0}
        fam = m
    else:
        grid = g[f"{sid}.storage.cube_bin.grid_area_m2"]
        items = {
            "storage": g[f"{sid}.storage.cube_bin.positions"] * cu["per_bin_eur"]
            + grid * cu["grid_structure_per_m2_eur"],
            "equipment": g[f"{sid}.equipment.robots"] * cu["per_robot_eur"]
            + g[f"{sid}.equipment.ports"] * cu["per_port_eur"],
            "controls": cu["controls_fixed_eur"],
            "building_works": works + grid * cu["floor_prep_per_m2_eur"],
            "overflow": m_storage + m_equipment,
        }
        fam = cu
    items["integration_commissioning"] = (
        fam["integration_share"] + fam["commissioning_share"]
    ) * items["equipment"]
    items["contingency"] = fam["contingency_share"] * sum(items.values())
    return {**items, "total": sum(items.values())}


def _cost_key(activity: str) -> str:
    """I33: forklift_driver for receiving, put_away, replenishment, shipping_pallet; team_leader
    for indirect; operator for all others."""
    if activity == "indirect":
        return "team_leader"
    return "forklift_driver" if activity in FORKLIFT else "operator"


def _labor(g: dict[str, Any], sid: str, t: int, basis: dict[str, Any]) -> float:
    """I33: literal, temp hours counted again on top of the annual hours."""
    f = basis["finance"]
    cost = f["labor_cost_eur_h"]
    pat = re.compile(rf"^{sid}\.labor\.(\w+)\.annual_hours\.y1$")
    acts = {m.group(1) for k in g if (m := pat.match(k))}
    direct = sum(g[f"{sid}.labor.{a}.annual_hours.y{t}"] * cost[_cost_key(a)] for a in acts)
    temp = g[f"{sid}.labor.temp_hours.y{t}"] * cost["operator"] * (1 + f["temp_premium"])
    return (direct * (1 + f["shift_premium"]) + temp) * (1 + f["wage_inflation"]) ** (t - 1)


def expected_opex(
    g: dict[str, Any], sid: str, auto: bool, capex: dict[str, float], basis: dict[str, Any]
) -> list[dict[str, float]]:
    """I32-I35, I41 in the typical world, years 1..5."""
    m, cu, fd = _typ("manual_p2p"), _typ("cube_asrs"), _finance_defaults()
    f, grow = basis["finance"], basis["projection"]["growth_rate"]
    fam = cu if auto else m
    assert basis["building"]["rent_mode"] == "footprint"  # I35 states the footprint mode
    forklifts = g[f"{sid}.equipment.forklifts"]
    kwh = forklifts * m["kwh_per_forklift_year"] + fd["fixed_kwh"]
    maint = fam["maintenance_share_of_equipment_capex"] * capex["equipment"]
    if auto:
        kwh += g[f"{sid}.equipment.robots"] * cu["kwh_per_robot_year"]
        kwh += g[f"{sid}.equipment.ports"] * fd["kwh_station"]
        overflow_eq = (
            g[f"{sid}.equipment.carts"] * m["per_cart_eur"] + forklifts * m["per_forklift_eur"]
        )
        maint += m["maintenance_share_of_equipment_capex"] * overflow_eq
    rows = []
    for t in YEARS:
        row = {
            "labor": _labor(g, sid, t, basis),
            "maintenance": maint,
            "energy": kwh * f["energy_price_eur_kwh"] * (1 + f["energy_inflation"]) ** (t - 1),
            "software": fam["software_eur_year"],
            "consumables": g["daily.orders.mean"] * 252 * (1 + grow) ** t * fd["packaging"],
            "rent": g[f"{sid}.area.total"] * basis["building"]["rent_eur_m2_year"],
            "renewal": fam["renewal_share"] * capex["equipment"]
            if t == fam["equipment_life_years"]
            else 0.0,
        }
        rows.append({**row, "total": sum(row.values())})
    return rows


def expected_keys(g: dict[str, Any], basis: dict[str, Any]) -> dict[str, float | None]:
    """Every S0 / S2 capex / opex / finance golden key from the register formulas (I29-I37, I42)."""
    r, grow = basis["finance"]["discount_rate"], basis["projection"]["growth_rate"]
    out: dict[str, float | None] = {}
    total: dict[str, tuple[float, list[float]]] = {}
    for sid, auto in (("S0", False), ("S2", True)):
        cap = expected_capex(g, sid, auto)
        rows = expected_opex(g, sid, auto, cap, basis)
        out |= {f"{sid}.capex.{k}": v for k, v in cap.items()}
        out |= {f"{sid}.opex.y{t}.{k}": v for t, row in enumerate(rows, 1) for k, v in row.items()}
        tco = cap["total"] + sum(row["total"] / (1 + r) ** t for t, row in enumerate(rows, 1))
        lines = g["daily.lines.mean"] * 252 * (1 + grow)  # I36
        out |= {f"{sid}.finance.tco": tco, f"{sid}.finance.annual_lines_y1": lines}
        out[f"{sid}.finance.cost_per_line"] = tco * r / (1 - (1 + r) ** -5) / lines
        total[sid] = (cap["total"], [row["total"] for row in rows])
    delta = [-(total["S2"][0] - total["S0"][0])]  # I42: against the computed S0 capex
    delta += [b - s for b, s in zip(total["S0"][1], total["S2"][1], strict=True)]
    out |= {f"S2.finance.delta_cf.y{t}": x for t, x in enumerate(delta)}
    out["S2.finance.npv"] = sum(x / (1 + r) ** t for t, x in enumerate(delta))
    out["S2.finance.irr"] = out["S2.finance.payback_years"] = None  # I37: Δcf has no sign change
    assert all(x < 0 for x in delta)
    return out


def test_T1_5_register_finance_formulas_reproduce_every_golden_key() -> None:
    """I29-I37, I41, I42 as the register states them reproduce the 111 golden keys of T7.1 (1e-9:
    same typ Params, same arithmetic), so register = oracle for every capex / opex / finance key."""
    g = _golden()
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    want = expected_keys(g, basis)
    have = {k for k in g if k.split(".")[0] in ("S0", "S2") and k.split(".")[1] in GROUPS}
    assert set(want) == have and len(have) == 111
    labor = yaml.safe_load((CATALOG / "labor_standards.yaml").read_text(encoding="utf-8"))
    roles = {a: COST_KEY[v["role"]] for a, v in labor["activities"].items()}
    assert roles == {a: _cost_key(a) for a in labor["activities"]}  # I33 = the catalog roles
    bad = {k: (g[k], v) for k, v in want.items() if g[k] != v and not (
        v is not None and g[k] is not None and math.isclose(g[k], v, rel_tol=1e-9))}  # fmt: skip
    assert not bad, bad


FLOWS = {
    "one change": [-100.0, 40.0, 40.0, 40.0],
    "payback inside a year": [-100.0, 60.0, 60.0, 60.0],
    "zeros ignored": [-100.0, 0.0, 0.0, 60.0, 60.0],
    "all negative (golden S2)": [-282430.0, -28016.8, -27678.0, -27316.1],
    "all positive": [10.0, 20.0, 30.0],
    "two changes": [-100.0, 150.0, -60.0, 30.0],
    "capex delta <= 0": [20.0, -5.0, -5.0],
    "never repaid": [-100.0, 10.0, 10.0, 10.0],
}


@pytest.mark.parametrize("name", sorted(FLOWS))
def test_T1_5_oracle_and_f7_metrics_agree_on_the_same_flows(name: str) -> None:
    """I37 (IRR only with exactly one sign change, zeros ignored, else None) and the App. B NPV
    (Δcf_0 undiscounted, I42) and payback, oracle against `whsizing.finance`."""
    flows, rate = FLOWS[name], 0.08
    assert npv(flows, rate) == pytest.approx(oracle.npv(rate, flows), rel=1e-12)
    assert npv(flows, rate) == pytest.approx(float(npf.npv(rate, flows)), rel=1e-12)
    assert payback(flows) == oracle.payback(flows)
    f7, why = irr(flows)
    ref = oracle.irr(flows)
    assert (f7 is None) == (ref is None) == (why is not None)
    if ref is not None and f7 is not None:
        assert f7 == pytest.approx(ref, rel=1e-9)
        assert npv(flows, f7) == pytest.approx(0.0, abs=1e-6)  # a root of the NPV, App. B


def _degenerate_scenarios(tmp: Path) -> Path:
    """Golden scenarios with S2 made ineligible for every SKU (extra_max_weight_kg ≈ 0)."""
    scen = yaml.safe_load((HERE / "golden_scenarios.yaml").read_text(encoding="utf-8"))
    scen["scenarios"][1]["eligibility"]["extra_max_weight_kg"] = 1e-9
    path = tmp / "degenerate.yaml"
    path.write_text(yaml.safe_dump(scen), encoding="utf-8")
    return path


def _degenerate_run(tmp: Path) -> tuple[dict[str, Any], dict[str, float], Any]:
    """Golden values, F7 typ nodes of S2 and the S2 finance result of the degenerate cube case."""
    scen_path = _degenerate_scenarios(tmp)
    golden = build_golden.run(scen_path=scen_path)[0].values()
    basis = load_basis(HERE / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(CATALOG)
    dd = select_design_day(profile_from_tables(t, cfg), basis, t.daily, sku=sku, catalog=catalog)
    results, tracers = {}, {}
    for s in load_yaml_model(scen_path, ScenarioSet).scenarios:
        tracers[s.id] = Tracer(s.id)
        results[s.id] = size_scenario(
            profile_from_tables(t, cfg), basis, dd, s, catalog, sku, t.daily, tracers[s.id],
            lines=t.lines,
        )  # fmt: skip
    assert results["S2"].eligibility.share_lines == 0
    compute_finance(results["S0"], basis, catalog, None, daily=t.daily, tracer=tracers["S0"],
                    client_baseline=False)  # fmt: skip
    fin = compute_finance(results["S2"], basis, catalog, results["S0"], daily=t.daily,
                          tracer=tracers["S2"], baseline_tracer=tracers["S0"])  # fmt: skip
    nodes = {n.id: n.value for n in tracers["S2"].nodes if n.world == "typ"}
    return golden, nodes, fin


def _s2_mismatches(golden: dict[str, Any], nodes: dict[str, float], rel: float) -> list[str]:
    """S2 capex / opex / finance keys where the F7 typ node and the golden value differ by more
    than `rel` (a key that is None in the golden has no F7 node)."""
    keys = [k for k in golden if k.startswith("S2.") and k.split(".")[1] in GROUPS]
    assert len(keys) == 60  # 8 capex + 40 opex + 12 finance
    bad = []
    for k in keys:
        if golden[k] is None:
            bad += [k] if k in nodes else []
        else:
            ok = k in nodes and nodes[k] == pytest.approx(golden[k], rel=rel, abs=1e-6)
            bad += [] if ok else [k]
    return bad


def test_T1_5_degenerate_cube_is_costed_as_the_manual_baseline_in_the_oracle_and_f7(
    tmp_path: Path,
) -> None:
    """I48: with no eligible line the cube scenario is costed with the manual formulas (WMS
    adaptation, manual shares, software, maintenance, no overflow item, no floor prep). The oracle
    and F7 agree on every S2 capex / opex / finance key within the T1.5 tolerance (0.5 %: the
    engine follows I6 as amended, F3f), and both equal S0 (NPV 0)."""
    golden, nodes, fin = _degenerate_run(tmp_path)
    assert _s2_mismatches(golden, nodes, rel=5e-3) == []
    assert golden["S2.capex.controls"] == golden["S0.capex.controls"] == 50_000.0
    assert nodes["S2.capex.controls"] == 50_000.0
    assert golden["S2.capex.overflow"] == 0.0 == fin.capex["overflow"].typ
    assert golden["S2.capex.total"] == pytest.approx(golden["S0.capex.total"])
    assert golden["S2.finance.npv"] == pytest.approx(0.0, abs=1e-6)
    assert fin.npv_vs_baseline is not None and fin.npv_vs_baseline.typ == pytest.approx(
        0.0, abs=1e-6
    )


def test_T1_5_degenerate_cube_costs_the_same_in_the_oracle_and_f7(tmp_path: Path) -> None:
    """I48 at 1e-9: oracle and F7 agree on every S2 capex / opex / finance key to rounding (the
    engine follows I6 as amended since F3f; the I48 structure is covered by the test above)."""
    golden, nodes, _ = _degenerate_run(tmp_path)
    assert _s2_mismatches(golden, nodes, rel=1e-9) == []
