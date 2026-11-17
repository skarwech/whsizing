"""F10b demo mode (the public demo on Streamlit Community Cloud): the Streamlit-free part.

`whsizing.app.demo` generates the fictitious demo site once, builds demo runs with the same CLI
commands as the terminal and keeps a visitor to the demo's own runs. The AppTest side (entry point,
pages, isolation, the binding guard) is in tests/e2e/test_f10_app_demo.py.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from whsizing.app import calls, demo, state
from whsizing.app.calls import CliError
from whsizing.config import load_yaml_model
from whsizing.design import load_basis
from whsizing.io import load_salt
from whsizing.schemas import ScenarioSet
from whsizing.synth import load_synth_profile


@pytest.fixture
def no_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    """No salt in the environment, and whatever the code under test plants there is removed at the
    end: `delenv` of an absent variable records nothing, so the variable is set first."""
    monkeypatch.setenv(demo.SALT_ENV, "placeholder")
    monkeypatch.delenv(demo.SALT_ENV)


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
    no_salt: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo.ensure_salt()
    first = os.environ[demo.SALT_ENV]
    assert len(first) >= 32  # 16 random bytes in hex: never short enough for the salt warning
    demo.ensure_salt()
    assert os.environ[demo.SALT_ENV] == first
    monkeypatch.setenv(demo.SALT_ENV, "set-by-the-deployer")
    demo.ensure_salt()
    assert os.environ[demo.SALT_ENV] == "set-by-the-deployer"


def test_visitors_arriving_together_on_a_fresh_server_share_one_salt(
    no_salt: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The datasets of one run are hashed with the salt of the moment: a second salt made by a
    second first visitor would not join with the first's (check, then set, needs the lock)."""
    made: list[str] = []

    def slow_token_hex(nbytes: int) -> str:
        time.sleep(0.02)  # the window an unguarded check-then-set leaves open
        made.append(f"salt-{len(made)}-{'0' * nbytes}")
        return made[-1]

    monkeypatch.setattr(demo.secrets, "token_hex", slow_token_hex)
    barrier = threading.Barrier(6)
    seen: list[str] = []

    def visitor() -> None:
        barrier.wait()
        demo.ensure_salt()
        seen.append(os.environ[demo.SALT_ENV])

    threads = [threading.Thread(target=visitor) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(made) == 1  # one salt was made...
    assert seen == made * 6  # ...and every visitor works with it


def test_the_throwaway_salt_of_the_full_app_is_private_usable_and_never_the_public_demos(
    no_salt: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the full app the demo must not set `$WHSIZING_SALT` (page 1 would stop asking for the
    user's own salt and their real files would be hashed with a salt nobody knows): one load
    gets a salt file of its own."""
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    path = demo._throwaway_salt()  # pyright: ignore[reportPrivateUsage]
    assert path is not None
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600  # the library warns about any other
        assert len(load_salt(path)) >= 32  # and accepts it: outside a repository, long enough
    finally:
        path.unlink()
    monkeypatch.setenv(demo.SALT_ENV, "the-salt-of-the-user")
    assert demo._throwaway_salt() is None  # pyright: ignore[reportPrivateUsage]
    monkeypatch.delenv(demo.SALT_ENV)
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    assert demo._throwaway_salt() is None  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------------------------- the data files
def test_the_data_is_regenerated_when_its_marker_outlived_its_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A marker without the four CSV files (a cleaned temp folder, a crash) is no marker: the next
    visit regenerates them instead of failing until the server restarts."""
    monkeypatch.setenv(demo.WORK_ENV, str(tmp_path / "work"))
    made: list[Path] = []

    def fake_synthesize(profile: Path, out: Path, *, seed: int) -> None:
        made.append(out)
        (out / "csv_en").mkdir(parents=True)
        for dataset in demo.DATASETS:
            (out / "csv_en" / f"{dataset}.csv").write_text("x\n", encoding="utf-8")

    monkeypatch.setattr(demo, "synthesize", fake_synthesize)
    csv = demo.ensure_data()
    assert len(made) == 1
    assert demo.ensure_data() == csv and len(made) == 1  # complete: reused
    (csv / "inventory.csv").unlink()
    assert demo.ensure_data() == csv and len(made) == 2  # the marker alone does not count
    assert all((csv / f"{dataset}.csv").is_file() for dataset in demo.DATASETS)


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


def test_prune_never_touches_the_shared_example_or_a_run_without_the_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_000_000.0
    shared = make_run(tmp_path, "shared", created=now - 10 * demo.RUN_MAX_AGE_S, shared=True)
    foreign = make_run(tmp_path, "somebody-elses-run")  # no marker: not the demo's
    (tmp_path / "a-file").write_text("x", encoding="utf-8")
    monkeypatch.setattr(demo, "_shared", shared)  # this server process's finished example
    assert demo.is_shared(shared) and not demo.is_shared(foreign)
    assert demo.prune(tmp_path, now=now) == []
    assert shared.is_dir() and foreign.is_dir() and (tmp_path / "a-file").is_file()
    assert demo.prune(tmp_path / "missing", now=now) == []  # no runs folder yet is fine


def test_the_shared_example_of_an_earlier_server_process_ages_out_like_any_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restart on a folder that survived (a container that kept its temp dir) builds a new
    finished example; the old one must not stay for ever."""
    now = 1_000_000.0
    earlier = make_run(tmp_path, "earlier", created=now - demo.RUN_MAX_AGE_S - 1, shared=True)
    young = make_run(tmp_path, "young", created=now - 60, shared=True)
    current = make_run(tmp_path, "current", created=now - 10 * demo.RUN_MAX_AGE_S, shared=True)
    monkeypatch.setattr(demo, "_shared", current)
    assert demo.prune(tmp_path, now=now) == [earlier]
    assert young.is_dir() and current.is_dir()  # the young one ages out later; ours never


def test_a_demo_run_gets_a_name_nobody_can_guess(
    no_salt: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`?run=<name>` opens any demo run and the stock name of a run is a second and six hex digits
    taken from the (public) demo data, the same for every demo run: guessable in minutes, and the
    pages write to a run. The name a visitor keeps carries a random part."""
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    monkeypatch.setattr(demo, "ensure_data", lambda: tmp_path / "csv")
    runs = tmp_path / "runs"
    made: list[str] = []

    def fake_call(command: object, **kwargs: Any) -> SimpleNamespace:
        run = kwargs["run"]
        if run is None:  # `ingest` of the first dataset makes the folder, the others add to it
            run = make_run(runs, f"2099-01-01T00-00-0{len(made)}_cafe01")
            made.append(run.name)
        return SimpleNamespace(last_line=str(run))

    monkeypatch.setattr(demo, "call", fake_call)
    first, second = demo.load_demo(runs), demo.load_demo(runs)
    for run, stock in zip((first, second), made, strict=True):
        assert re.fullmatch(rf"{stock}-[0-9a-f]{{16}}", run.name), run.name
        assert demo.is_demo_run(run) and state.is_run(run)  # the marker and the folder moved along
        assert not (runs / stock).exists()  # nothing is left under the stock name
        assert (run / "ui" / "basis.yaml").is_file()
    assert first.name.rsplit("-", 1)[1] != second.name.rsplit("-", 1)[1]


def test_a_load_that_fails_midway_cleans_up_its_salt_and_leaves_a_run_the_pruning_removes(
    no_salt: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The full app, no salt exported: the throwaway salt file is deleted even when the second
    dataset fails, and the run the first one made is marked, so that the public demo's pruning
    takes it (an unmarked half-run would stay for ever)."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))  # where the salt file is made
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    monkeypatch.setattr(demo, "ensure_data", lambda: tmp_path / "csv")
    runs = tmp_path / "runs"
    half = runs / "2099-01-01T00-00-00_half"
    salt_files: list[Path] = []

    def fake_call(command: object, **kwargs: Any) -> SimpleNamespace:
        salt_file = kwargs["salt_file"]
        assert salt_file is not None and salt_file.is_file()  # there while the command runs
        salt_files.append(salt_file)
        if len(salt_files) == 2:
            raise CliError(2, "boom")
        return SimpleNamespace(last_line=str(kwargs["run"] or make_run(runs, half.name)))

    monkeypatch.setattr(demo, "call", fake_call)
    with pytest.raises(CliError, match="boom"):
        demo.load_demo(runs)
    assert len(salt_files) == 2 and salt_files[0] == salt_files[1]
    assert not salt_files[0].exists() and list(scratch.iterdir()) == []
    assert demo.is_demo_run(half) and not demo.is_shared(half)
    assert demo.prune(runs, now=time.time() + demo.RUN_MAX_AGE_S + 1) == [half]


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
    """The shared example built once for the module, as the public demo builds it: data generated,
    ingested, sized, compared."""
    work = tmp_path_factory.mktemp("demo_work")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.DEMO_ENV, "1")  # the public demo makes its salt and prunes its runs
        mp.setenv(demo.WORK_ENV, str(work))
        mp.setenv(demo.SALT_ENV, "placeholder")  # set, then removed: the teardown then also
        mp.delenv(demo.SALT_ENV)  # removes the salt the demo makes
        demo.forget_shared()
        runs = work / "runs"
        catalog = demo.resource_root() / "catalog"
        shared = demo.shared_run(runs, catalog)
        yield SimpleNamespace(
            work=work, runs=runs, catalog=catalog, shared=shared, salt=os.environ[demo.SALT_ENV]
        )
        demo.forget_shared()


@pytest.mark.slow
def test_the_demo_data_is_generated_once_per_profile_content(built: SimpleNamespace) -> None:
    csv = next(built.work.glob("data-*/csv_en"))
    for dataset in demo.DATASETS:
        assert (csv / f"{dataset}.csv").stat().st_size > 0
    stamp = (csv.parent / ".complete").stat().st_mtime_ns
    assert demo.ensure_data() == csv  # reused: same folder
    assert (csv.parent / ".complete").stat().st_mtime_ns == stamp  # and not regenerated


@pytest.mark.slow
def test_the_shared_example_is_a_finished_marked_run(built: SimpleNamespace) -> None:
    run = built.shared
    assert state.is_run(run) and demo.is_demo_run(run)
    assert state.stage(run) == "compared"
    assert demo.is_shared(run)
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
    shared_runs = [p for p in built.runs.iterdir() if demo.is_shared(p)]
    assert shared_runs == [built.shared]  # no second finished example, whatever else is there


@pytest.mark.slow
def test_a_visitors_own_run_has_the_data_and_the_drafts_pages_4_and_5_start_from(
    built: SimpleNamespace,
) -> None:
    run = demo.load_demo(built.runs)
    assert run != built.shared and demo.is_demo_run(run) and not demo.is_shared(run)
    assert state.stage(run) == "ingested"  # not sized: the visitor does that on page 5
    assert state.saved_path(run, "basis") == run / "ui" / "basis.yaml"
    assert state.saved_path(run, "scenarios") == run / "ui" / "scenarios.yaml"
    restored = state.run_state(run)  # what the pages read back into the session
    assert restored[state.BASIS]["client"].startswith("Demo")
    assert [s["id"] for s in restored[state.SCENARIOS]["scenarios"]] == ["S0", "S1", "S2"]
    assert (run / "dq" / "dq_report.json").is_file()


@pytest.mark.slow
def test_loading_in_the_public_demo_prunes_old_visitor_runs_but_not_the_shared_example(
    built: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = make_run(built.runs, "2000-01-01T00-00-00_stale", created=1.0)
    foreign = make_run(built.runs, "2000-01-01T00-00-01_foreign")  # not the demo's: never pruned
    monkeypatch.setattr(demo, "RUN_MAX_AGE_S", -1)  # every demo run counts as old
    run = demo.load_demo(built.runs)
    assert not stale.exists()  # an old visitor run went
    assert (
        built.shared.is_dir() and foreign.is_dir()
    )  # the shared example and the foreign run stayed
    # the load made a run of its own, marked as the demo's (so that a later load prunes it) and
    # not as the shared example: with every demo run "old", it is the pruning that must come first
    assert run.parent == built.runs and run != built.shared
    assert demo.is_demo_run(run) and not demo.is_shared(run)


@pytest.mark.slow
def test_in_the_full_app_the_demo_sets_no_salt_prunes_nothing_and_leaves_no_salt_file(
    built: SimpleNamespace, no_salt: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The demo buttons are on the full app's Home page too. There they must leave the user's
    salt and the user's runs alone: no process-wide random salt (page 1 would stop asking for
    the user's own, and real files would be hashed with one nobody knows), no pruning of runs the
    user may have worked in, and the throwaway salt file of the load is gone afterwards."""
    monkeypatch.delenv(demo.DEMO_ENV)  # the full app (the module fixture turned the demo on)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    runs = tmp_path / "runs"
    worked_in = make_run(runs, "2000-01-01T00-00-00_worked_in", created=1.0)  # 'old', demo-marked
    foreign = make_run(runs, "2000-01-01T00-00-01_foreign")
    run = demo.load_demo(runs)  # ingests four datasets: it would fail without any salt
    assert demo.is_demo_run(run) and state.stage(run) == "ingested"
    assert demo.SALT_ENV not in os.environ  # page 1 still asks for the user's salt
    assert worked_in.is_dir() and foreign.is_dir()  # nothing pruned
    assert list(scratch.glob("whsizing-demo-salt-*")) == []
