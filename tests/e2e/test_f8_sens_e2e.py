"""F8b end to end on synthetic ecom_mid (F1 generator, 730 days, ≈ 0.98 M order lines) with the
example project, basis, scenarios and catalog: `run_scenarios` with `options.sensitivity` (the
default) on manual_p2p (S0), amr_gtp (S1) and cube_asrs (S2), once against the client's current
operation and once with S0 as the baseline scenario (I42), then `rerun`. Reports the time of the
sensitivity stage (expected: seconds) and prints the tornado, break-even rows and sweep."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from whsizing.config import load_project
from whsizing.scenarios import PARAMS, rerun, run_scenarios
from whsizing.schemas import Project, Sensitivity
from whsizing.schemas.project import InputSpec
from whsizing.schemas.run import RunOutput
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
IDS = ("S0", "S1", "S2")
SENS_BUDGET_S = 60  # "seconds": the stage re-sizes 3 scenarios about 50 times


@pytest.fixture(scope="module", autouse=True)
def salt_env() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "f8b-e2e-salt")
        yield


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Project:
    out = tmp_path_factory.mktemp("f8b_e2e")
    synthesize(ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml", out / "ecom_mid", seed=42)
    data = out / "ecom_mid" / "csv_en"
    example = load_project(ROOT / "project" / "example_project.yaml")
    assert example.options.sensitivity  # the default: the hook runs
    return example.model_copy(
        update={
            "out_dir": out / "runs",
            "inputs": {ds: InputSpec(files=[data / f"{ds}.csv"]) for ds in DATASETS},
        }
    )


@pytest.fixture(scope="module")
def client_run(project: Project) -> RunOutput:
    return run_scenarios(project)


@pytest.fixture(scope="module")
def s0_run(project: Project, client_run: RunOutput) -> RunOutput:
    text = (ROOT / "scenarios" / "example_scenarios.yaml").read_text(encoding="utf-8")
    path = project.out_dir / "scenarios_s0.yaml"
    path.write_text(text.replace("baseline: client_current", "baseline: S0"), encoding="utf-8")
    return run_scenarios(
        project.model_copy(update={"scenarios": path}), reuse_canonical=client_run.run_dir
    )


def sensitivity(run: RunOutput) -> Sensitivity:
    assert run.sensitivity is not None
    return run.sensitivity


@pytest.mark.slow
def test_T8_3_ecom_mid_tornado_is_sorted_with_a_bar_per_scenario_and_parameter(
    client_run: RunOutput, s0_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    for run in (client_run, s0_run):
        s = sensitivity(run)
        assert sorted((b.scenario_id, b.param) for b in s.tornado) == sorted(
            (i, p) for i in IDS for p in PARAMS
        )
        deltas = [b.delta_tco for b in s.tornado]
        assert deltas == sorted(deltas, reverse=True) and deltas[0] > 0
        assert s.base_tco == {r.scenario_id: r.tco.typ for r in run.comparison.rows if r.tco}
        stored = Sensitivity.model_validate_json(
            (run.run_dir / "comparison" / "sensitivity.json").read_text(encoding="utf-8")
        )
        assert stored == s
    s = sensitivity(client_run)
    lines = [
        f"  {b.scenario_id} {b.param:20s} d_TCO {b.delta_tco / 1e3:8.0f} k EUR, "
        f"payback {b.payback_low} / {b.payback_high}, FTE {b.fte_low:.1f} / {b.fte_high:.1f}"
        for b in s.tornado[:8]
    ]
    with capsys.disabled():
        print("\nF8b ecom_mid, baseline client_current: top of the tornado\n" + "\n".join(lines))


@pytest.mark.slow
def test_ecom_mid_sensitivity_stage_takes_seconds(
    client_run: RunOutput, s0_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    times = {
        name: r.manifest.timings["sensitivity"]
        for name, r in (("client", client_run), ("S0", s0_run))
    }
    with capsys.disabled():
        print(
            "\nF8b ecom_mid sensitivity stage (7 parameters x 3 scenarios x 2 runs, break-even, "
            "4 percentiles): " + ", ".join(f"{k} baseline {v:.1f} s" for k, v in times.items())
        )
    assert all(0 < t < SENS_BUDGET_S for t in times.values())


@pytest.mark.slow
def test_ecom_mid_break_even_rows_reproduce_the_target_and_the_sweep_is_monotone(
    client_run: RunOutput, s0_run: RunOutput, capsys: pytest.CaptureFixture[str]
) -> None:
    s = sensitivity(client_run)
    assert [r.scenario_id for r in s.break_even] == ["S1", "S2"]
    for r in s.break_even:
        assert r.labor_cost_multiplier is not None and 0.3 < r.labor_cost_multiplier < 3.0
        assert r.labor_cost_multiplier < 1.0  # both pay back within 5 years at today's labor cost
    s0 = sensitivity(s0_run)  # against S0 (same labor cost in both): rows exist, may be None
    assert [r.scenario_id for r in s0.break_even] == ["S1", "S2"]
    for run_s in (s, s0):
        for sid in IDS:
            lines = [r.design_lines for r in run_s.percentile_sweep if r.scenario_id == sid]
            assert len(lines) == 4 and lines == sorted(lines)
    with capsys.disabled():
        print(
            "\nF8b ecom_mid break-even labor multiplier for a 5-year payback: client baseline "
            + ", ".join(f"{r.scenario_id} {r.labor_cost_multiplier}" for r in s.break_even)
            + "; S0 baseline "
            + ", ".join(f"{r.scenario_id} {r.labor_cost_multiplier}" for r in s0.break_even)
        )


@pytest.mark.slow
def test_ecom_mid_rerun_writes_a_byte_identical_sensitivity_json(client_run: RunOutput) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("WHSIZING_SALT")  # a rerun re-hashes nothing: canonical/ is reused
        again = rerun(client_run.run_dir)
    assert again.run_dir != client_run.run_dir
    one, two = (r.run_dir / "comparison" / "sensitivity.json" for r in (client_run, again))
    assert one.read_bytes() == two.read_bytes()
