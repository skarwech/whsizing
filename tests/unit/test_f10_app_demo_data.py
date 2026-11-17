"""F10b demo mode (the public demo on Streamlit Community Cloud): the Streamlit-free part.

`whsizing.app.demo` generates the fictitious demo site once, builds demo runs with the same CLI
commands as the terminal and keeps a visitor to the demo's own runs. The AppTest side (entry point,
pages, isolation, the binding guard) is in tests/e2e/test_f10_app_demo.py.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from whsizing.app import calls, demo, state
from whsizing.config import load_yaml_model
from whsizing.design import load_basis
from whsizing.schemas import ScenarioSet
from whsizing.synth import load_synth_profile


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """No salt, no demo flag, the demo's work folder in `tmp_path`; the module state forgotten."""
    monkeypatch.delenv(demo.SALT_ENV, raising=False)
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    monkeypatch.setenv(demo.WORK_ENV, str(tmp_path / "work"))
    demo.forget_shared()
    return tmp_path


def make_run(root: Path, name: str, *, created: float | None = None, shared: bool = False) -> Path:
    """A folder that passes `state.is_run`, marked as a demo run when `created` is given."""
    run = root / name
    (run / "canonical").mkdir(parents=True)
    (run / "dq").mkdir()
    if created is not None:
        (run / "ui").mkdir()
        meta = {"demo": True, "shared": shared, "created": created}
        (run / demo.MARKER).write_text(json.dumps(meta), encoding="utf-8")
    return run


# --------------------------------------------------------------------------------- the flag
def test_demo_only_follows_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    assert demo.demo_only() is False
    for value in ("0", "", "true", "yes"):  # only the exact "1" turns the demo on
        monkeypatch.setenv(demo.DEMO_ENV, value)
        assert demo.demo_only() is False
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    assert demo.demo_only() is True


def test_the_demo_resources_exist_and_load() -> None:
    """The profile, the basis and the scenarios of the demo are real, valid files."""
    root = demo.resource_root()
    assert load_synth_profile(root / demo.PROFILE).name == "demo"
    assert load_basis(root / demo.BASIS).client.startswith("Demo")
    scenarios = load_yaml_model(root / demo.SCENARIOS, ScenarioSet)
    assert [s.id for s in scenarios.scenarios] == ["S0", "S1", "S2"]
    assert scenarios.baseline == "client_current"


def test_resources_are_found_from_another_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Community Cloud starts from the repository root, but a checkout run from elsewhere works
    too: the package's own location is the fallback."""
    monkeypatch.chdir(tmp_path)
    assert (demo.resource_root() / demo.PROFILE).is_file()


# ---------------------------------------------------------------------------------- the salt
def test_a_random_salt_is_made_once_per_process_and_a_set_salt_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(demo.SALT_ENV, raising=False)
    demo.ensure_salt()
    first = os.environ[demo.SALT_ENV]
    assert len(first) >= 32  # 16 random bytes in hex: never short enough for the salt warning
    demo.ensure_salt()
    assert os.environ[demo.SALT_ENV] == first
    monkeypatch.setenv(demo.SALT_ENV, "set-by-the-deployer")
    demo.ensure_salt()
    assert os.environ[demo.SALT_ENV] == "set-by-the-deployer"


# ------------------------------------------------------------------- markers and the pruning
def test_only_a_run_with_the_demo_marker_is_a_demo_run(tmp_path: Path) -> None:
    plain = make_run(tmp_path, "plain")
    marked = make_run(tmp_path, "marked", created=time.time())
    assert not demo.is_demo_run(plain)
    assert demo.is_demo_run(marked)
    (plain / "ui").mkdir()
    (plain / demo.MARKER).write_text("not json", encoding="utf-8")
    assert not demo.is_demo_run(plain)  # a damaged marker is no marker
    (plain / demo.MARKER).write_text(json.dumps({"demo": "yes"}), encoding="utf-8")
    assert not demo.is_demo_run(plain)  # only a true flag counts


def test_prune_deletes_old_runs_and_the_oldest_above_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000_000.0
    old = make_run(tmp_path, "old", created=now - demo.RUN_MAX_AGE_S - 1)
    fresh = [make_run(tmp_path, f"fresh{i}", created=now - 100 + i) for i in range(5)]
    monkeypatch.setattr(demo, "MAX_RUNS", 3)
    removed = demo.prune(tmp_path, now=now)
    assert old in removed and not old.exists()
    kept = [p for p in fresh if p.exists()]
    # room for the run about to be made: MAX_RUNS - 1 = 2 survive, the newest ones
    assert kept == fresh[-2:]
    assert sorted(p.name for p in removed) == ["fresh0", "fresh1", "fresh2", "old"]


def test_prune_never_touches_the_shared_example_or_a_run_without_the_marker(tmp_path: Path) -> None:
    now = 1_000_000.0
    shared = make_run(tmp_path, "shared", created=now - 10 * demo.RUN_MAX_AGE_S, shared=True)
    foreign = make_run(tmp_path, "somebody-elses-run")  # no marker: not the demo's
    (tmp_path / "a-file").write_text("x", encoding="utf-8")
    assert demo.prune(tmp_path, now=now) == []
    assert shared.is_dir() and foreign.is_dir() and (tmp_path / "a-file").is_file()
    assert demo.prune(tmp_path / "missing", now=now) == []  # no runs folder yet is fine


# ------------------------------------------------------------------- the commands are serial
def test_in_process_commands_run_one_at_a_time() -> None:
    """The commands capture the process-wide stdout and keep module-level timings: two visitors
    must not interleave them (`calls._LOCK`)."""
    inside = 0
    peak = 0
    guard = threading.Lock()

    def command() -> None:
        nonlocal inside, peak
        with guard:
            inside += 1
            peak = max(peak, inside)
        time.sleep(0.05)
        print("done")
        with guard:
            inside -= 1

    results: list[str] = []

    def visitor() -> None:
        results.append(calls.call(command).stdout.strip())

    threads = [threading.Thread(target=visitor) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 1  # never two commands at once
    assert results == ["done"] * 6  # and each visitor got its own output, not another's


# --------------------------------------------------------------- the data and the demo runs
@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """The shared example built once for the module: data generated, ingested, sized, compared."""
    work = tmp_path_factory.mktemp("demo_work")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.WORK_ENV, str(work))
        mp.delenv(demo.SALT_ENV, raising=False)
        demo.forget_shared()
        runs = work / "runs"
        catalog = demo.resource_root() / "catalog"
        t0 = time.perf_counter()
        shared = demo.shared_run(runs, catalog)
        yield SimpleNamespace(
            work=work,
            runs=runs,
            catalog=catalog,
            shared=shared,
            seconds=time.perf_counter() - t0,
            salt=os.environ[demo.SALT_ENV],
        )
        demo.forget_shared()


@pytest.mark.slow
def test_the_demo_data_is_generated_once_per_profile_content(built: SimpleNamespace) -> None:
    csv = next(built.work.glob("data-*/csv_en"))
    for dataset in demo.DATASETS:
        assert (csv / f"{dataset}.csv").stat().st_size > 0
    stamp = (csv.parent / ".complete").stat().st_mtime_ns
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.WORK_ENV, str(built.work))
        assert demo.ensure_data() == csv  # reused: same folder
    assert (csv.parent / ".complete").stat().st_mtime_ns == stamp  # and not regenerated


@pytest.mark.slow
def test_the_shared_example_is_a_finished_marked_run(built: SimpleNamespace) -> None:
    run = built.shared
    assert state.is_run(run) and demo.is_demo_run(run)
    assert state.stage(run) == "compared"
    meta = json.loads((run / demo.MARKER).read_text(encoding="utf-8"))
    assert meta["shared"] is True
    comparison = json.loads((run / "comparison" / "comparison.json").read_text(encoding="utf-8"))
    assert [row["scenario_id"] for row in comparison["rows"]] == ["S0", "S1", "S2"]
    assert all(row["status"] == "computed" for row in comparison["rows"])
    assert (run / "comparison" / "sensitivity.json").is_file()  # the demo shows the tornado too


@pytest.mark.slow
def test_the_salt_the_demo_used_is_random_and_not_in_the_run(built: SimpleNamespace) -> None:
    assert len(built.salt) >= 32
    for path in built.shared.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".yaml", ".jsonl", ".log"}:
            assert built.salt not in path.read_text(encoding="utf-8", errors="ignore"), path


@pytest.mark.slow
def test_the_shared_example_is_built_once_then_reused(built: SimpleNamespace) -> None:
    again = demo.shared_run(built.runs, built.catalog)
    assert again == built.shared
    assert sorted(p.name for p in built.runs.iterdir()) == [built.shared.name]  # no second run


@pytest.mark.slow
def test_a_visitors_own_run_has_the_data_and_the_drafts_pages_4_and_5_start_from(
    built: SimpleNamespace,
) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.WORK_ENV, str(built.work))
        run = demo.load_demo(built.runs)
    assert run != built.shared and demo.is_demo_run(run)
    assert state.stage(run) == "ingested"  # not sized: the visitor does that on page 5
    assert state.saved_path(run, "basis") == run / "ui" / "basis.yaml"
    assert state.saved_path(run, "scenarios") == run / "ui" / "scenarios.yaml"
    restored = state.run_state(run)  # what the pages read back into the session
    assert restored[state.BASIS]["client"].startswith("Demo")
    assert [s["id"] for s in restored[state.SCENARIOS]["scenarios"]] == ["S0", "S1", "S2"]
    assert (run / "dq" / "dq_report.json").is_file()


@pytest.mark.slow
def test_pruning_while_a_visitor_loads_never_deletes_the_shared_example(
    built: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "RUN_MAX_AGE_S", -1)  # every run counts as old
    monkeypatch.setenv(demo.WORK_ENV, str(built.work))
    run = demo.load_demo(built.runs)
    assert built.shared.is_dir()  # the old visitor runs went, the shared example stayed
    assert run.is_dir()  # and the run just made is not pruned by its own load
