"""R8b (final audit) on the runner (docs/INTERPRETATIONS.md I75 f, h, I85 b): the `logs/FAILED`
marker of a failed or interrupted run, the reasons in the strict exit-4 message, and the
filesystem errors of `find_canonical` (L5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.test_f8_runner import (
    NOW,
    fail_on,
    log_records,
    run_folder,
    salt_env,  # noqa: F401  (autouse fixture: $WHSIZING_SALT for every run of this module)
    small_data,
    small_project,
)

from whsizing.app import state
from whsizing.errors import ConfigError, MappingError, SizingInfeasibleError
from whsizing.scenarios import find_canonical, runner
from whsizing.schemas.run import RunOutput


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return small_data(tmp_path_factory)


@pytest.fixture(scope="module")
def good_run(data: Path, tmp_path_factory: pytest.TempPathFactory) -> RunOutput:
    return runner.run_scenarios(small_project(data, tmp_path_factory.mktemp("runs")), now=NOW)


def marker(run: Path) -> dict[str, str]:
    return json.loads((run / runner.FAILED_FILE).read_text(encoding="utf-8"))


def test_T10_3_the_failed_marker_path_is_the_one_the_app_reads() -> None:
    assert runner.FAILED_FILE == state.FAILED_FILE == Path("logs") / "FAILED"


def test_T10_3_a_finished_run_has_no_marker_and_is_listed(good_run: RunOutput) -> None:
    assert not (good_run.run_dir / runner.FAILED_FILE).exists()
    assert state.is_run(good_run.run_dir)
    assert state.list_runs(good_run.run_dir.parent) == [good_run.run_dir]


def test_T10_3_a_failing_stage_writes_the_marker_and_the_app_skips_the_folder(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("engine exploded\nsecond line")

    monkeypatch.setattr(runner, "size_scenario", boom)
    with pytest.raises(RuntimeError, match="engine exploded"):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    run = run_folder(tmp_path / "runs")
    assert marker(run) == {"error_type": "RuntimeError", "reason": "engine exploded"}  # one line
    assert log_records(run)[-1]["event"] == "run_failed"
    assert not state.is_run(run) and state.list_runs(tmp_path / "runs") == []
    assert state.resolve_run(tmp_path / "runs", run.name) is None
    assert state.restore({}, {"run": run.name}, tmp_path / "runs") is None  # no newest-run fallback


@pytest.mark.parametrize(
    ("error", "name"),
    [
        (MappingError("column SKU: no candidate"), "MappingError"),
        (KeyboardInterrupt(), "KeyboardInterrupt"),
    ],
)
def test_T10_3_an_ingest_failure_or_an_interrupt_marks_the_run_too(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException, name: str
) -> None:
    def failing_ingest(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(runner, "ingest", failing_ingest)
    with pytest.raises(type(error)):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), now=NOW)
    run = run_folder(tmp_path / "runs")
    assert marker(run)["error_type"] == name
    assert log_records(run)[-1]["event"] == "run_failed"
    assert not state.is_run(run)


def test_T10_3_exit_4_strict_is_a_complete_run_not_a_failed_one(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I75 f: everything is written before the strict check raises, so the folder is a result."""
    fail_on(monkeypatch, {"S2"})
    with pytest.raises(SizingInfeasibleError):
        runner.run_scenarios(small_project(data, tmp_path / "runs"), strict=True, now=NOW)
    run = run_folder(tmp_path / "runs")
    assert not (run / runner.FAILED_FILE).exists() and state.is_run(run)


def test_T10_3_strict_message_carries_the_reason_of_the_first_scenario_not_computed(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_on(monkeypatch, {"S1", "S2"})
    with pytest.raises(SizingInfeasibleError, match=r"not computed: S1, S2 .*; S1: Sizing") as e:
        runner.run_scenarios(small_project(data, tmp_path / "runs"), strict=True, now=NOW)
    assert "no SKU can be stored in the family" in str(e.value)


def test_T10_3_no_scenario_computed_is_exit_4_even_without_strict(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M5 (I85 b): with every scenario not computed there is nothing to compare or report, so the
    run raises (exit 4) with the first reason; the folder is complete, not a failed run."""
    fail_on(monkeypatch, {"S0", "S1", "S2"})
    with pytest.raises(
        SizingInfeasibleError, match=r"^no scenario computed: not computed: S0, S1"
    ) as e:
        runner.run_scenarios(small_project(data, tmp_path / "runs"), strict=False, now=NOW)
    assert "S0: Sizing" in str(e.value) and "strict" not in str(e.value)
    assert e.value.exit_code == 4
    run = run_folder(tmp_path / "runs")
    assert not (run / runner.FAILED_FILE).exists() and state.is_run(run)
    assert (run / "comparison" / "comparison.json").is_file()  # everything is written first


def test_T10_3_one_scenario_not_computed_without_strict_still_exits_0(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The others continue (spec F8 edge case): the all-not-computed rule does not widen."""
    fail_on(monkeypatch, {"S1", "S2"})
    out = runner.run_scenarios(small_project(data, tmp_path / "runs"), strict=False, now=NOW)
    assert {i: r.status for i, r in out.results.items()} == {
        "S0": "computed", "S1": "not_computed", "S2": "not_computed",
    }  # fmt: skip


# ------------------------------------------------------------------------------ L5
def test_L5_find_canonical_wraps_a_filesystem_error_as_config_error(
    data: Path, tmp_path: Path
) -> None:
    """An out_dir component over NAME_MAX (255): glob raises OSError ENAMETOOLONG, which was an
    'unexpected OSError' (exit 1); it is a ConfigError (exit 2) naming the path and the reason."""
    out = tmp_path / ("x" * 300)
    with pytest.raises(ConfigError, match=r"cannot look for earlier runs") as e:
        find_canonical(small_project(data, out))
    assert str(out) in str(e.value) and "File name too long" in str(e.value)
    assert e.value.exit_code == 2


def test_L5_find_canonical_still_returns_none_without_earlier_runs(
    data: Path, tmp_path: Path
) -> None:
    assert find_canonical(small_project(data, tmp_path / "never_made")) is None


def test_L5_a_key_file_that_cannot_be_read_is_a_config_error(
    data: Path, tmp_path: Path, good_run: RunOutput
) -> None:
    project = small_project(data, good_run.run_dir.parent)
    assert find_canonical(project) == good_run.run_dir  # the earlier run is found
    key = good_run.run_dir / "canonical" / runner.KEY_FILE
    key.chmod(0)
    try:
        with pytest.raises(ConfigError, match="cannot look for earlier runs"):
            find_canonical(project)
    finally:
        key.chmod(0o644)
