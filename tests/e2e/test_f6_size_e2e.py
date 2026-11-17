"""F6 end to end on synthetic ecom_mid (F1, 730 days, ≈ 0.98 M order lines): F1 generate + FR CSV
export → F2 ingest (one dataset at a time) → F3 build_tables / profile → I58 sku_frame → F4
design day → F6 size_scenario + write_scenario for manual_p2p, amr_gtp and cube_asrs with the
example basis (2 shifts × 7 h, 12 000 m²). Prints the run time and the main outputs."""

from __future__ import annotations

import time
from pathlib import Path

import polars as pl
import pytest
from tests.unit.test_f6_size import assert_traced

from whsizing.catalog import load_catalog
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_scenario, sku_frame, write_scenario
from whsizing.io import ingest
from whsizing.profile import build_tables, profile_from_tables
from whsizing.schemas import FamilyId, ProfileCfg, ScenarioDef
from whsizing.schemas.project import InputSpec
from whsizing.schemas.trace import Tracer
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")
FAMILIES: tuple[FamilyId, ...] = ("manual_p2p", "amr_gtp", "cube_asrs")
BUDGET_S = 120  # whole chain, generous: about 10 s on a laptop


@pytest.mark.slow
def test_F6_ecom_mid_three_families_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    t0 = time.perf_counter()
    profile_cfg = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml")
    export(generate(profile_cfg, seed=42), tmp_path, ("csv_fr",))
    run = tmp_path / "run"
    for ds in DATASETS:
        ingest({ds: InputSpec(files=[tmp_path / "csv_fr" / f"{ds}.csv"])}, run, b"e2e-salt")
    t1 = time.perf_counter()
    basis, cfg = load_basis(ROOT / "basis" / "example_basis.yaml"), ProfileCfg()
    t = build_tables(run / "canonical", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(run / "canonical" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    t2 = time.perf_counter()
    report = [f"{t.lines.height:,} shipped lines, design day {dd.lines:.0f} lines"]
    for fam in FAMILIES:
        s = ScenarioDef(id=fam, name=fam, family=fam)
        tracer = Tracer(s.id)
        r = size_scenario(profile, basis, dd, s, catalog, sku, t.daily, tracer, lines=t.lines)
        assert_traced(fam, write_scenario(r, tracer, tmp_path / "project"))  # T6.11
        lab, area = r.labor, r.area
        assert 0 < lab.annual_hours[0].typ < lab.total_hours.typ * 252  # T6.10 guard
        assert area.total_m2.typ > r.storage.total_area_m2.typ > 0 and lab.roster.typ > 0
        assert len({x.shift for x in lab.shifts}) == 2
        assert tracer.get(f"{fam}.labor.single_line_share").value == pytest.approx(
            profile.eiq.single_line_share, rel=1e-12
        )  # one share_S: F6c's from the lines equals F3's
        report.append(
            f"{fam}: storage {r.storage.total_area_m2.typ:.0f} m², area {area.total_m2.typ:.0f} m²"
            f" (fit {area.fit}), roster {lab.roster.typ:.1f}, core FTE y1 "
            f"{lab.core_fte[0].typ:.1f}, equipment "
            f"{ {k: v.typ for k, v in r.equipment.items()} }, bottleneck {r.bottleneck}, "
            f"flags {[f.code for f in r.flags]}"
        )
    wall = time.perf_counter() - t0
    with capsys.disabled():
        print(
            f"\nF6 e2e ecom_mid: F1+F2 {t1 - t0:.1f} s, F3+F4 {t2 - t1:.1f} s, "
            f"F6 x3 {time.perf_counter() - t2:.1f} s, total {wall:.1f} s\n  " + "\n  ".join(report)
        )
    assert t.lines.height > 900_000 and wall < BUDGET_S
