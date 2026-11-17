"""F8a end to end on synthetic ecom_mid (F1 generator, 730 days, ≈ 0.98 M order lines) with the
example project, basis, scenarios and catalog: `run_scenarios` on manual_p2p (S0), amr_gtp (S1)
and cube_asrs (S2), once against the client's current operation and once with S0 as the baseline
scenario, then `rerun`. T8.5 (bench): the scenario stage (3 scenarios × 3 worlds, size + finance +
write) takes < 10 s. Prints the time and the main outputs."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from whsizing.config import load_project
from whsizing.scenarios import rerun, run_scenarios
from whsizing.schemas import FamilyId, Project, Range
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
FAMILIES: dict[str, FamilyId] = {"S0": "manual_p2p", "S1": "amr_gtp", "S2": "cube_asrs"}
EQUIPMENT = {
    "S0": {"pickers_peak"},
    "S1": {"pickers_peak", "gtp_stations", "robots"},
    "S2": {"pickers_peak", "ports", "robots"},
}
SCENARIO_BUDGET_S = 10  # T8.5
FILES = ("result.json", "finance.json", "trace.jsonl")
ARTIFACTS = (
    "manifest.json", "logs/run.log", "report", "inputs/project.yaml", "inputs/basis.yaml",
    "inputs/scenarios.yaml", "inputs/catalog/labor_standards.yaml",
    *(f"inputs/mapping/{ds}.yaml" for ds in DATASETS),
    *(f"canonical/{ds}.parquet" for ds in DATASETS), "canonical/daily_series.parquet",
    "dq/dq_report.json", "dq/dq_report.html", "dq/ingest_manifest.json",
    "profile/demand_profile.json", "design/design_day.json", "design/assumptions.json",
    "comparison/comparison.json",
    *(f"scenarios/{s}/{f}" for s in FAMILIES for f in FILES),
)  # fmt: skip


def eur(r: Range) -> str:
    return f"{r.typ / 1e6:.2f} M€ [{r.lo / 1e6:.2f}-{r.hi / 1e6:.2f}]"


def typ(r: Range | None) -> float:
    assert r is not None
    return r.typ


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    """example_project.yaml has no salt_file: the salt comes from $WHSIZING_SALT."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f8-e2e-salt")
        yield


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    out = tmp_path_factory.mktemp("f8_e2e")
    synthesize(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml", out / "ecom_mid", seed=42)
    data = out / "ecom_mid" / "csv_en"
    example = load_project(ROOT / "project" / "example_project.yaml")  # Appendix E paths
    return example.model_copy(
        update={
            "out_dir": out / "runs",
            "inputs": {ds: InputSpec(files=[data / f"{ds}.csv"]) for ds in DATASETS},
        }
    )


@pytest.fixture(scope="module")
def client_run(project: Project) -> RunOutput:
    """Baseline: the client's current operation (`baseline: client_current`)."""
    return run_scenarios(project)


@pytest.fixture(scope="module")
def s0_run(project: Project, client_run: RunOutput) -> RunOutput:
    """Baseline: the sized manual scenario S0 (I42); canonical tables reused from the first run."""
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    path = project.out_dir / "scenarios_s0.yaml"
    path.write_text(text.replace("baseline: client_current", "baseline: S0"), encoding="utf-8")
    return run_scenarios(
        project.model_copy(update={"scenarios": path}), reuse_canonical=client_run.run_dir
    )


@pytest.mark.slow
def test_F8_every_artifact_of_the_run_folder_exists(
    client_run: RunOutput, s0_run: RunOutput
) -> None:
    for out in (client_run, s0_run):
        missing = [a for a in ARTIFACTS if not (out.run_dir / a).exists()]
        assert missing == [], (out.run_dir, missing)
        charts = out.run_dir / "profile" / "charts"
        assert len(list(charts.glob("*.png"))) == len(list(charts.glob("*.html"))) == 8
        assert out.manifest.run_id == out.run_dir.name
        # `sensitivity: null` until F8b exists; then its file is written next to the comparison
        has_file = (out.run_dir / "comparison/sensitivity.json").exists()
        assert (out.sensitivity is not None) == has_file
    assert client_run.run_dir != s0_run.run_dir
    assert (s0_run.run_dir / "canonical/order_lines.parquet").read_bytes() == (
        client_run.run_dir / "canonical/order_lines.parquet"
    ).read_bytes()  # reused, not re-ingested


@pytest.mark.slow
def test_F8_comparison_rows_are_sane_for_the_three_families(
    client_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    cmp = client_run.comparison
    assert [(r.scenario_id, r.family) for r in cmp.rows] == list(FAMILIES.items())
    work_h = client_run.results["S0"].labor.total_hours.typ
    lines = [f"baseline {cmp.baseline_id}, design day {work_h:.0f} h of manual work"]
    for r in cmp.rows:
        assert r.status == "computed" and r.fit is True
        assert set(r.equipment) == EQUIPMENT[r.scenario_id], r.scenario_id
        ranges = [r.storage_area_m2, r.total_area_m2, r.fte_design_day, r.core_fte_year1, r.roster]
        ranges += [r.capex, r.opex_year1, r.tco, r.npv_vs_baseline, r.cost_per_line]
        for rng in (*ranges, *r.equipment.values()):
            assert rng is not None and rng.lo <= rng.typ <= rng.hi
        assert typ(r.tco) > typ(r.capex) > 0 and typ(r.opex_year1) > 0
        assert typ(r.total_area_m2) > 0 and typ(r.fte_design_day) > 0
        assert 0 < (r.eligible_line_share or 0) <= 1 and r.n_low_confidence_params > 0
        assert r.payback_years is not None and r.payback_years > 0
        assert r.capex and r.opex_year1 and r.tco and r.npv_vs_baseline
        lines.append(
            f"{r.scenario_id} {r.family}: capex {eur(r.capex)}, opex y1 {eur(r.opex_year1)}, "
            f"TCO {eur(r.tco)}, NPV vs client {eur(r.npv_vs_baseline)}, payback "
            f"{r.payback_years:.2f} y, area {typ(r.total_area_m2):.0f} m2, FTE design day "
            f"{typ(r.fte_design_day):.1f}, cost/line {typ(r.cost_per_line):.3f} €, "
            f"{r.n_warnings} warning(s), {r.n_low_confidence_params} L params"
        )
    capex = {r.scenario_id: typ(r.capex) for r in cmp.rows}
    assert capex["S0"] < capex["S1"] and capex["S0"] < capex["S2"]  # automation costs capex
    tco = {r.scenario_id: typ(r.tco) for r in cmp.rows}
    assert cmp.ranking_tco == sorted(tco, key=lambda s: tco[s])
    assert sorted(cmp.ranking_payback) == sorted(FAMILIES)
    assert cmp.confidence_note.startswith("Ranking at typical values")
    assert ("ranges overlap" in cmp.confidence_note) == bool(cmp.overlaps)
    lines.append(f"ranking TCO {cmp.ranking_tco}, payback {cmp.ranking_payback}")
    lines.append(cmp.confidence_note)
    with capsys.disabled():
        print("\nF8a e2e ecom_mid, baseline client_current\n  " + "\n  ".join(lines))


@pytest.mark.slow
def test_F8_scenario_baseline_run_compares_against_s0(
    s0_run: RunOutput, client_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    cmp = s0_run.comparison
    assert cmp.baseline_id == "S0"
    rows = {r.scenario_id: r for r in cmp.rows}
    assert rows["S0"].npv_vs_baseline is None and rows["S0"].payback_years is None
    assert "S0" not in cmp.ranking_payback
    s0 = s0_run.finances["S0"]
    for sid in ("S1", "S2"):
        fin = s0_run.finances[sid]
        assert fin.delta_cash_flows_typ[0] == pytest.approx(
            -(fin.capex_total.typ - s0.capex_total.typ)
        )  # I42: the baseline's capex is its computed capex, not 0
        assert rows[sid].npv_vs_baseline is not None
        assert fin.tco == client_run.finances[sid].tco  # only the baseline differs
        assert s0_run.results[sid] == client_run.results[sid]
    summary = ", ".join(
        f"{sid} NPV {eur(r.npv_vs_baseline)} payback {r.payback_years}"
        for sid, r in rows.items()
        if r.npv_vs_baseline is not None
    )
    with capsys.disabled():
        print(f"\nF8a e2e ecom_mid, baseline S0: {summary}; ranking payback {cmp.ranking_payback}")


@pytest.mark.slow
def test_F8_rerun_of_the_ecom_mid_run_is_byte_identical(client_run: RunOutput) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("WHSIZING_SALT")  # a rerun re-hashes nothing: canonical/ is reused
        again = rerun(client_run.run_dir)
    assert again.run_dir != client_run.run_dir
    for sid in FAMILIES:
        for f in FILES:
            one, two = (r.run_dir / "scenarios" / sid / f for r in (client_run, again))
            assert one.read_bytes() == two.read_bytes(), (sid, f)
    assert (again.run_dir / "comparison/comparison.json").read_bytes() == (
        client_run.run_dir / "comparison/comparison.json"
    ).read_bytes()


@pytest.mark.bench
@pytest.mark.slow
def test_T8_5_three_scenarios_times_three_worlds_run_in_under_10_seconds(
    client_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    timings = client_run.manifest.timings
    with capsys.disabled():
        print(
            "\nT8.5 scenario stage (3 scenarios x 3 worlds, size + finance + write): "
            f"{timings['scenarios']:.2f} s; all stages "
            + ", ".join(f"{k} {v:.2f}" for k, v in timings.items())
        )
    assert 0 < timings["scenarios"] < SCENARIO_BUDGET_S
