"""F7 end to end on synthetic ecom_mid (F1, 730 days, ≈ 0.98 M order lines): F1 generate + FR CSV
export → F2 ingest → F3 build_tables / profile → I58 sku_frame → F4 design day → F6
size_scenario for manual_p2p (S0), amr_gtp (S1) and cube_asrs (S2) with the example basis → F7
compute_finance (S0 first, then S1 and S2 against S0) → write_finance + write_scenario.
Prints the run time and the main outputs (capex, opex y1, TCO, NPV, IRR, payback, cost per line,
with their lo / hi worlds)."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import polars as pl
import pytest
from tests.unit.test_f7_finance import Run, check_traced, count_numbers

from whsizing.catalog import load_catalog
from whsizing.design import load_basis, select_design_day
from whsizing.engine import WORLDS, size_scenario, sku_frame, write_scenario
from whsizing.finance import compute_finance, write_finance
from whsizing.io import ingest
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import FamilyId, FinancialResult, ProfileCfg, Range, ScenarioDef
from whsizing.schemas.project import InputSpec
from whsizing.schemas.trace import Tracer
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")
SCENARIOS: dict[str, FamilyId] = {"S0": "manual_p2p", "S1": "amr_gtp", "S2": "cube_asrs"}
BUDGET_S = 120  # whole chain, generous: about 15 s on a laptop


def eur(r: Range) -> str:
    return f"{r.typ / 1e6:.2f} M€ [{r.lo / 1e6:.2f}-{r.hi / 1e6:.2f}]"


@pytest.mark.slow
def test_F7_ecom_mid_three_families_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    t0 = time.perf_counter()
    profile_cfg = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
    export(generate(profile_cfg, seed=42), tmp_path, ("csv_fr",))
    run = tmp_path / "run"
    for ds in DATASETS:
        ingest({ds: InputSpec(files=[tmp_path / "csv_fr" / f"{ds}.csv"])}, run, b"e2e-salt")
    basis, cfg = load_basis(ROOT / "basis" / "example_basis.yaml"), ProfileCfg()
    t = build_tables(run / "canonical", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(run / "canonical" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    t1 = time.perf_counter()
    sized = {}
    for sid, fam in SCENARIOS.items():
        s, tracer = ScenarioDef(id=sid, name=fam, family=fam), Tracer(sid)
        sized[sid] = (
            size_scenario(profile, basis, dd, s, catalog, sku, t.daily, tracer, lines=t.lines),
            tracer,
        )
    t2 = time.perf_counter()
    runs: dict[str, Run] = {}
    client: dict[str, FinancialResult] = {}
    for sid, (result, tracer) in sized.items():
        base = None if sid == "S0" else sized["S0"]
        # the spec default `baseline: client_current` on the shipped example basis (coarse labels
        # picking / packing / receiving / shipping / indirect), on a tracer without finance nodes
        client[sid] = compute_finance(
            result, basis, catalog, None, daily=t.daily, tracer=copy.deepcopy(tracer)
        )
        fin = compute_finance(
            result, basis, catalog, base and base[0], daily=t.daily, tracer=tracer,
            baseline_tracer=base and base[1], client_baseline=False,
        )  # fmt: skip
        runs[sid] = Run(result, tracer, fin)
        project = tmp_path / "project"
        write_finance(fin, project)  # finance first, then the trace that holds its nodes
        folder = write_scenario(result, tracer, project)
        assert json.loads((folder / "finance.json").read_text())["scenario_id"] == sid
    t3 = time.perf_counter()

    report = [f"{t.lines.height:,} shipped lines, design day {dd.lines:.0f} lines"]
    for sid, r in runs.items():
        fin = r.fin
        ranges = [*fin.capex.values(), fin.capex_total, fin.opex_year1, fin.tco, fin.cost_per_line]
        ranges += [fin.npv_vs_baseline] if fin.npv_vs_baseline else []
        assert all(x.lo <= x.typ <= x.hi for x in ranges), sid
        assert fin.capex_total.typ > 0 and fin.opex_year1.typ > 0 and fin.cost_per_line.typ > 0
        assert len(fin.opex_by_year) == basis.finance.horizon_years
        assert check_traced(sid, r) == count_numbers(fin.model_dump(mode="json")), sid
        for key in ("capex.total", "opex.y1.total", "finance.tco"):  # pessimistic dearer
            lo, typ, hi = (r.tracer.get(f"{sid}.{key}", w).value for w in WORLDS)
            assert lo > typ > hi, (sid, key)
        npv = fin.npv_vs_baseline
        report.append(
            f"{sid} {SCENARIOS[sid]}: capex {eur(fin.capex_total)}, opex y1 {eur(fin.opex_year1)}, "
            f"TCO {eur(fin.tco)}, cost/line {fin.cost_per_line.typ:.2f} € "
            f"[{fin.cost_per_line.lo:.2f}-{fin.cost_per_line.hi:.2f}], "
            + ("baseline" if npv is None else f"NPV {eur(npv)}, IRR {fin.irr_vs_baseline}, "
               f"payback {fin.payback_years}")
        )  # fmt: skip
    assert runs["S0"].fin.npv_vs_baseline is None
    for sid, cfin in client.items():  # client-current baseline: capex 0, labor from the FTE
        assert cfin.npv_vs_baseline is not None, sid
        assert cfin.delta_cash_flows_typ[0] == -cfin.capex_total.typ, sid
        assert any("client's current operation" in n for n in cfin.notes), sid
        assert cfin.capex_total == runs[sid].fin.capex_total, sid
        report.append(f"{sid} vs client current: NPV {eur(cfin.npv_vs_baseline)}")
    assert all(runs[s].fin.npv_vs_baseline is not None for s in ("S1", "S2"))
    wall = time.perf_counter() - t0
    with capsys.disabled():
        print(
            f"\nF7 e2e ecom_mid: F1-F4 {t1 - t0:.1f} s, F6 x3 {t2 - t1:.1f} s, F7 x3 + write "
            f"{t3 - t2:.2f} s, total {wall:.1f} s\n  " + "\n  ".join(report)
        )
    assert wall < BUDGET_S
