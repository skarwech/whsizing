"""G1d: golden oracle, register and engine agree on the F4 flags of I57 (F_RATIO_DRIFT at P_m = 0)
and I59 (F_DEFAULT_UPP). Neither is raised on the golden case, so both are pinned on modified
data. G1e: I63 (11) whole-pitch levels and I63 (12) robot parking (amr_gtp, no golden scenario).
Part of T1.5."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml
from tests.golden import build_golden, demand, oracle
from tests.golden.test_f4_golden import engine_values, same
from tests.golden.test_g1_sync import _data, _read

from whsizing.catalog import load_catalog
from whsizing.config import load_yaml_model
from whsizing.design import load_basis, select_design_day, with_pack_data
from whsizing.design.design_day import _flags  # pyright: ignore[reportPrivateUsage]
from whsizing.engine import size_storage, size_throughput, sku_frame, world_inputs
from whsizing.engine.area import size_area
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import ProfileCfg, ScenarioDef, ScenarioSet
from whsizing.schemas.trace import Tracer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _daily(pallets_out: list[int]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """30 operating days, flat except pallets_out; lines all at 10:00."""
    days = [date(2025, 3, 3) + timedelta(days=i) for i in range(len(pallets_out))]
    n = len(days)
    flat = {"orders": 50, "lines": 100, "units": 150, "cube_m3": 1.0, "weight_kg": 100.0}
    cols: dict[str, Any] = {k: [v] * n for k, v in flat.items()}
    daily = pl.DataFrame(
        {"date": days, **cols, "parcels": [55] * n, "pallets_out": pallets_out}
    ).with_columns(weekday=pl.col("date").dt.weekday() - 1, is_operating=pl.lit(True))
    lines = pl.DataFrame({"date": days, "hour": [10] * n, "has_time": [True] * n})
    return daily, lines


@pytest.mark.parametrize(
    ("pallets_out", "raised"),
    [([1] + [0] * 29, True), ([0] * 30, False)],  # P95 = 0; the reference day (first) has 1 / 0
)
def test_T1_5_ratio_drift_at_zero_percentile(pallets_out: list[int], raised: bool) -> None:
    """I57: P_m = 0 and m* > 0 → F_RATIO_DRIFT:<m> (unbounded drift); both 0 → no flag. The
    engine raises the same codes on the same P_m and m*."""
    basis = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    out = oracle.Out()
    dd = demand.design_day(out, *_daily(pallets_out), basis)
    v = out.values()
    assert v["design_day.p.pallets_out"] == 0.0
    assert (v["design_day.base.pallets_out"] > 0) is raised
    assert ("F_RATIO_DRIFT:pallets_out" in dd["flags"]) is raised
    assert dd["flags"] == ["F_SHORT_HISTORY"] + ["F_RATIO_DRIFT:pallets_out"] * raised
    metrics = ("orders", "lines", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
    p = {m: v[f"design_day.p.{m}"] for m in metrics}
    base = {m: v[f"design_day.base.{m}"] for m in metrics}
    assert [f.code for f in _flags(False, 30, base, p)] == dd["flags"]


def test_T1_5_default_units_per_pallet_flag_matches_the_engine(tmp_path: Path) -> None:
    """I59: the most-shipped SKU loses units_per_case × cases_per_pallet (F2 then fills
    units_per_pallet with 400). The oracle raises F_DEFAULT_UPP after the design-day flags,
    before F_LOW_CONFIDENCE, value = its share of inbound units; the engine's F4 keys (flags
    included) and flag value equal the oracle's. Not raised on the golden case."""
    g0 = json.loads((HERE / "golden_values.json").read_text(encoding="utf-8"))
    assert "F_DEFAULT_UPP" not in g0["design_day.flags"]
    _, c0 = build_golden.run()
    top = c0["skus"][0]  # sorted by lines, descending
    assert not top["default_upp"] and top["units"] > 0
    hit = pl.col("sku") == top["sku"]
    sku = _read("sku_master").with_columns(
        pl.when(hit).then(None).otherwise(pl.col(c)).alias(c)
        for c in ("units_per_case", "cases_per_pallet")
    )
    sku = sku.with_columns(units_per_pallet=pl.when(hit).then(400).otherwise("units_per_pallet"))
    data = _data(tmp_path, sku_master=sku)
    out, c = build_golden.run(data_dir=data)
    g = out.values()
    share = top["units"] / sum(r["units"] for r in c["skus"])
    assert c["inb"]["default_upp_share"] == pytest.approx(share, rel=1e-12)
    assert g["design_day.flags"] == g0["design_day.flags"] + ",F_DEFAULT_UPP"
    assert g["S0.flags"].split(",")[-2:] == ["F_DEFAULT_UPP", "F_LOW_CONFIDENCE:30"]
    assert g["inbound.pallets_per_day"] != pytest.approx(g0["inbound.pallets_per_day"])

    basis, cfg = load_basis(HERE / "golden_basis.yaml"), ProfileCfg()
    t = build_tables(data, basis, cfg)
    profile = profile_from_tables(t, cfg)
    pack = with_pack_data(t.skus, pl.read_parquet(data / "sku_master.parquet"))
    dd = select_design_day(
        profile, basis, t.daily, sku=pack, catalog=load_catalog(ROOT / "catalog")
    )
    engine = engine_values(dd, profile, basis)
    bad = {k: (e, g[k]) for k, e in engine.items() if not same(e, g[k])}
    assert not bad, f"{len(bad)} of {len(engine)} F4 keys differ (engine, oracle): {bad}"
    flag = next(f for f in dd.flags if f.code == "F_DEFAULT_UPP")
    assert flag.severity == "info" and flag.value == pytest.approx(share, rel=1e-9)


def test_T1_5_whole_pitch_clear_height_engine_equals_the_oracle(tmp_path: Path) -> None:
    """I63 (11) at 7.8 m (cube grid exactly 20 pitches): every S0/S2 storage key of the oracle
    equals the engine's typ trace (levels exact, the rest within 1e-9), and both raise
    F_HEIGHT_LIMIT for the pallet rack only."""
    raw = yaml.safe_load((HERE / "golden_basis.yaml").read_text(encoding="utf-8"))
    raw["building"]["clear_height_m"] = 7.8
    path = tmp_path / "basis.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    g = build_golden.run(basis_path=path)[0].values()
    golden = {k: v for k, v in g.items() if k.split(".")[1:2] == ["storage"]}
    assert golden["S2.storage.cube_bin.levels"] == 20
    for sid in ("S0", "S2"):  # oracle side of "both raise F_HEIGHT_LIMIT for the pallet rack only"
        heights = [f for f in g[f"{sid}.flags"].split(",") if f.startswith("F_HEIGHT_LIMIT")]
        assert heights == ["F_HEIGHT_LIMIT:pallet_rack"], sid

    basis, cfg, catalog = load_basis(path), ProfileCfg(), load_catalog(ROOT / "catalog")
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    dd = select_design_day(profile_from_tables(t, cfg), basis, t.daily, sku=sku, catalog=catalog)
    engine: dict[str, Any] = {}
    for scenario in load_yaml_model(HERE / "golden_scenarios.yaml", ScenarioSet).scenarios:
        tracer = Tracer(scenario.id)
        st = size_storage(world_inputs(basis, dd, scenario, catalog, sku, "typ", tracer))
        engine |= {n.id: n.value for n in tracer.nodes}
        assert [f.code for f in st.flags] == ["F_HEIGHT_LIMIT:pallet_rack"], scenario.id
    bad = {
        k: (engine.get(k), v)
        for k, v in golden.items()
        if k not in engine or not math.isclose(engine[k], v, rel_tol=1e-9, abs_tol=1e-12)
    }
    assert not bad, f"engine vs oracle at 7.8 m: {bad}"
    assert all(engine[k] == v for k, v in golden.items() if k.endswith(".levels"))  # exact


def test_T1_5_amr_robot_parking_reads_the_cube_param() -> None:
    """I63 (12), I26: an amr_gtp scenario's equipment area reads
    `cube_asrs.m2_per_robot_parking`, so an override of `amr_gtp.m2_per_robot_parking` changes
    nothing. The golden case has no amr_gtp scenario: tiny_golden with an inline S1."""
    basis, cfg, catalog = (
        load_basis(HERE / "golden_basis.yaml"),
        ProfileCfg(),
        load_catalog(ROOT / "catalog"),
    )
    t = build_tables(HERE / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(HERE / "tiny_golden" / "sku_master.parquet"))
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    nodes = []
    for overrides in ({}, {"amr_gtp.m2_per_robot_parking": 10.0}):
        scenario = ScenarioDef(id="S1", name="AMR", family="amr_gtp", overrides=overrides)
        tracer = Tracer("S1")
        inp = world_inputs(basis, dd, scenario, catalog, sku, "typ", tracer)
        st = size_storage(inp)
        tp = size_throughput(inp, st)
        assert tp.equipment["robots"] > 0
        size_area(inp, st, tp, roster=10.0, share_s=profile.eiq.single_line_share)
        nodes.append(next(n for n in tracer.nodes if n.id == "S1.area.equipment"))
    assert nodes[1].inputs["m2_per_robot_parking"] == "param:cube_asrs.m2_per_robot_parking"
    assert nodes[1].value == nodes[0].value
