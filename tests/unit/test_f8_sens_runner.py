"""F8b through F8a's runner on the small synthetic site: `options.sensitivity` calls
`run_sensitivity`, comparison/sensitivity.json is written, RunOutput.sensitivity is the model, the
stage is timed, and two fresh runs of the same inputs write byte-identical sensitivity.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.test_f8_runner import (
    NOW,
    salt_env,  # noqa: F401  (autouse fixture: $WHSIZING_SALT for every run of this module)
    small_data,
    small_project,
)

from whsizing.scenarios import PARAMS, run_scenarios
from whsizing.schemas import ProjectOptions, Sensitivity
from whsizing.schemas.run import RunOutput


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    project = small_project(data, tmp_path_factory.mktemp("runs"), options=ProjectOptions())
    return run_scenarios(project, now=NOW)


def test_the_option_runs_the_hook_and_writes_sensitivity_json(run: RunOutput) -> None:
    s = run.sensitivity
    assert isinstance(s, Sensitivity)
    path = run.run_dir / "comparison" / "sensitivity.json"
    assert Sensitivity.model_validate_json(path.read_text(encoding="utf-8")) == s
    assert s.delta == 0.2 and set(s.base_tco) == {"S0", "S1", "S2"}
    assert "sensitivity" in run.manifest.timings
    assert list(run.manifest.timings)[-1] == "sensitivity"  # the last stage


def test_T8_3_the_runs_tornado_has_a_sorted_bar_per_scenario_and_parameter(run: RunOutput) -> None:
    assert run.sensitivity is not None
    bars = run.sensitivity.tornado
    assert sorted((b.scenario_id, b.param) for b in bars) == sorted(
        (s, p) for s in ("S0", "S1", "S2") for p in PARAMS
    )
    deltas = [b.delta_tco for b in bars]
    assert deltas == sorted(deltas, reverse=True) and deltas[0] > 0
    for b in bars:  # base TCO is the comparison's own
        row = next(r for r in run.comparison.rows if r.scenario_id == b.scenario_id)
        assert row.tco is not None and run.sensitivity.base_tco[b.scenario_id] == row.tco.typ


def test_break_even_and_sweep_are_part_of_the_runs_sensitivity(run: RunOutput) -> None:
    assert run.sensitivity is not None
    assert [r.scenario_id for r in run.sensitivity.break_even] == ["S1", "S2"]
    assert all(r.target_payback_years == 5.0 for r in run.sensitivity.break_even)
    sweep = run.sensitivity.percentile_sweep
    assert len(sweep) == 3 * 4
    for sid in ("S0", "S1", "S2"):
        lines = [r.design_lines for r in sweep if r.scenario_id == sid]
        assert lines == sorted(lines)


def test_two_fresh_runs_write_byte_identical_sensitivity_json(
    run: RunOutput, data: Path, tmp_path: Path
) -> None:
    again = run_scenarios(small_project(data, tmp_path / "runs", options=ProjectOptions()), now=NOW)
    one, two = (r.run_dir / "comparison" / "sensitivity.json" for r in (run, again))
    assert one.read_bytes() == two.read_bytes()
    assert json.loads(one.read_text())["tornado"]  # not an empty file


def test_without_the_option_nothing_is_written(data: Path, tmp_path: Path) -> None:
    off = run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)  # sensitivity=False
    assert off.sensitivity is None
    assert not (off.run_dir / "comparison" / "sensitivity.json").exists()
