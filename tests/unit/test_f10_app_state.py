"""F10b app state (T10.4): run discovery, stage detection and the restore of the session keys from
the run folder (`?run=` or the newest run), on bare folders: no Streamlit session needed."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from whsizing import errors
from whsizing.app import loaders, state


def make_run(root: Path, name: str, *, stage_files: tuple[str, ...] = ()) -> Path:
    run = root / name
    for sub in ("canonical", "dq", "inputs/mapping", "logs"):
        (run / sub).mkdir(parents=True, exist_ok=True)
    for rel in stage_files:
        (run / rel).parent.mkdir(parents=True, exist_ok=True)
        (run / rel).write_text("{}", encoding="utf-8")
    return run


def test_T10_4_list_runs_newest_first_and_skips_other_folders(tmp_path: Path) -> None:
    old = make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    new = make_run(tmp_path, "2026-02-01T00-00-00_bbbbbb")
    (tmp_path / ".uploads").mkdir()  # the app's upload folder is no run
    (tmp_path / "notes").mkdir()
    assert state.list_runs(tmp_path) == [new, old]
    assert state.list_runs(tmp_path / "missing") == []


def test_T10_4_stage_follows_the_files_of_the_run(tmp_path: Path) -> None:
    run = make_run(tmp_path, "r")
    assert state.stage(run) == "empty"
    steps = [
        ("canonical/order_lines.parquet", "ingested"),
        ("profile/demand_profile.json", "profiled"),
        ("design/design_day.json", "sized"),
        ("comparison/comparison.json", "compared"),
    ]
    for rel, expected in steps:
        (run / rel).parent.mkdir(parents=True, exist_ok=True)
        (run / rel).write_text("{}", encoding="utf-8")
        assert state.stage(run) == expected
    assert state.reached(run, "sized") and state.reached(run, "compared")
    assert not state.reached(make_run(tmp_path, "r2"), "ingested")


def test_T10_4_restore_prefers_the_session_then_the_query_then_the_newest_run(
    tmp_path: Path,
) -> None:
    old = make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    new = make_run(tmp_path, "2026-02-01T00-00-00_bbbbbb")
    session: dict[str, object] = {}
    assert state.restore(session, {}, tmp_path) == new.resolve()  # nothing given: the last run
    assert session[state.RUN] == str(new.resolve())
    session = {}
    assert state.restore(session, {"run": old.name}, tmp_path) == old.resolve()  # ?run=
    other = {state.RUN: str(new)}
    assert state.restore(other, {"run": old.name}, tmp_path) == new.resolve()  # session wins
    stale = {state.RUN: str(tmp_path / "vanished")}  # a deleted folder is dropped, not trusted
    assert state.restore(stale, {}, tmp_path) == new.resolve()
    assert state.restore({}, {"run": "no-such-run"}, tmp_path) == new.resolve()


def test_T10_4_restore_without_any_run_leaves_no_run_key(tmp_path: Path) -> None:
    session: dict[str, object] = {state.RUN: str(tmp_path / "gone")}
    assert state.restore(session, {}, tmp_path) is None
    assert state.RUN not in session


def test_T10_4_new_run_flag_stops_the_fallback_to_the_newest_run(tmp_path: Path) -> None:
    make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    session: dict[str, object] = {state.NO_RUN: True}
    assert state.restore(session, {}, tmp_path) is None


def test_T10_4_restore_rebuilds_mapping_basis_and_scenarios_from_the_run(tmp_path: Path) -> None:
    run = make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    (run / "inputs" / "mapping" / "order_lines.yaml").write_text(
        yaml.safe_dump({"dataset": "order_lines", "columns": {"sku": "SKU"}}), encoding="utf-8"
    )
    state.write_draft(run, "basis", {"client": "Draft"})
    state.write_draft(run, "scenarios", {"scenarios": [], "baseline": "client_current"})
    session: dict[str, object] = {}
    state.restore(session, {}, tmp_path)
    assert session[state.MAPPING] == {
        "order_lines": {"dataset": "order_lines", "columns": {"sku": "SKU"}}
    }
    assert session[state.BASIS] == {"client": "Draft"}
    assert session[state.SCENARIOS] == {"scenarios": [], "baseline": "client_current"}
    session[state.BASIS] = {"client": "Edited, not saved"}  # same run: the edit is kept
    state.restore(session, {}, tmp_path)
    assert session[state.BASIS] == {"client": "Edited, not saved"}


def test_T10_4_sized_run_inputs_win_over_the_drafts(tmp_path: Path) -> None:
    run = make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    state.write_draft(run, "basis", {"client": "Draft"})
    (run / "inputs" / "basis.yaml").write_text("client: Sealed\n", encoding="utf-8")
    assert state.saved_path(run, "basis") == run / "inputs" / "basis.yaml"
    assert state.run_state(run)[state.BASIS] == {"client": "Sealed"}


def test_T10_4_run_digest_changes_when_the_comparison_changes(tmp_path: Path) -> None:
    run = make_run(tmp_path, "r", stage_files=("manifest.json", "comparison/comparison.json"))
    first = state.run_digest(run)
    (run / "comparison" / "comparison.json").write_text('{"x": 1}', encoding="utf-8")
    assert state.run_digest(run) != first
    assert state.run_digest(run) == state.run_digest(run)


def profiled_run(root: Path, dataset_hash: str = "h1") -> Path:
    """A profiled run folder whose profile says it was made from the tables with `dataset_hash`."""
    run = make_run(root, "r", stage_files=("canonical/order_lines.parquet",))
    profile = run / "profile" / "demand_profile.json"
    profile.parent.mkdir()
    profile.write_text(json.dumps({"dataset_hash": dataset_hash}), encoding="utf-8")
    return run


def current_tables(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """What the canonical tables hash to now (`loaders.tables_hash`: the real one reads parquet)."""
    monkeypatch.setattr(loaders, "tables_hash", lambda run, digest: value)


def test_T10_4_profile_is_stale_when_the_tables_are_not_those_it_was_made_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = make_run(tmp_path, "empty", stage_files=("canonical/order_lines.parquet",))
    assert not state.profile_stale(run)  # not profiled yet: nothing to be stale
    run = profiled_run(tmp_path, "h1")
    current_tables(monkeypatch, "h1")
    assert not state.profile_stale(run)  # the profile was made from these tables
    current_tables(monkeypatch, "h2")  # a dataset was ingested since (R7.5)
    assert state.profile_stale(run)


def test_R7_5_staleness_does_not_read_file_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`profile` writes canonical/daily_series.parquet after the profile file, so a table newer
    than the profile is the normal state of a profiled run; and a touched table is not new data."""
    run = profiled_run(tmp_path, "h1")
    current_tables(monkeypatch, "h1")
    series = run / "canonical" / "daily_series.parquet"
    series.write_text("{}", encoding="utf-8")
    made = (run / "profile" / "demand_profile.json").stat().st_mtime_ns
    os.utime(series, ns=(made + 10**9, made + 10**9))
    later = made + 2 * 10**9
    os.utime(run / "canonical" / "order_lines.parquet", ns=(later, later))
    assert not state.profile_stale(run)


def test_R7_5_the_digest_of_the_canonical_tables_leaves_out_the_profile_output(
    tmp_path: Path,
) -> None:
    run = make_run(tmp_path, "r", stage_files=("canonical/order_lines.parquet",))
    before = loaders.canonical_digest(run)
    (run / "canonical" / "daily_series.parquet").write_text("{}", encoding="utf-8")
    assert loaders.canonical_digest(run) == before  # written by `profile`: not data
    (run / "canonical" / "sku_master.parquet").write_text("{}", encoding="utf-8")
    assert loaders.canonical_digest(run) != before  # a table ingest wrote


def test_R7_5_a_changed_profile_configuration_makes_the_profile_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = profiled_run(tmp_path, "h1")
    current_tables(monkeypatch, "h1")
    assert state.profile_cfg_file(run) is None
    state.mark_profiled(run)  # page 3 profiled with the defaults
    assert not state.profile_stale(run)
    cfg = run / "inputs" / "profile_cfg.yaml"
    cfg.write_text("abc_thresholds: [0.7, 0.9]\n", encoding="utf-8")
    assert state.profile_cfg_file(run) == cfg
    assert state.profile_stale(run)  # another cfg
    state.mark_profiled(run)  # profiled with it
    assert not state.profile_stale(run)
    cfg.write_text("abc_thresholds: [0.6, 0.9]\n", encoding="utf-8")
    assert state.profile_stale(run)


def test_R7_5_a_profile_made_by_the_cli_or_one_that_cannot_be_read_is_not_stale_on_its_cfg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = profiled_run(tmp_path, "h1")
    current_tables(monkeypatch, "h1")
    (run / "inputs" / "profile_cfg.yaml").write_text("abc_thresholds: [0.7, 0.9]\n", "utf-8")
    assert not state.profile_stale(run)  # no digest: the CLI made it, with that cfg
    (run / "profile" / "demand_profile.json").write_text("{", encoding="utf-8")
    current_tables(monkeypatch, "other")
    assert not state.profile_stale(run)  # page 3 shows the ConfigError, it does not hide it


def test_R7_5_tables_that_cannot_be_read_make_the_profile_stale_instead_of_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tables_hash` reads the canonical tables and raises a WhsizingError for a damaged or
    removed one: page 3 calls `profile_stale` outside any try, so it must answer, and a stale
    answer makes the page profile again, which reports the same table as a CliError."""
    run = profiled_run(tmp_path, "h1")

    def unreadable(run: str, digest: str) -> str:
        raise errors.WhsizingError("canonical order_lines: cannot read the table")

    monkeypatch.setattr(loaders, "tables_hash", unreadable)
    assert state.profile_stale(run)


def test_T10_4_a_sized_run_is_never_stale(tmp_path: Path) -> None:
    run = make_run(
        tmp_path, "r", stage_files=("profile/demand_profile.json", "design/design_day.json")
    )
    table = run / "canonical" / "late.parquet"
    table.write_text("{}", encoding="utf-8")
    os.utime(table, ns=(1, 1))
    later = run / "profile" / "demand_profile.json"
    os.utime(later, ns=(0, 0))  # older than the table: a profiled run would be stale
    assert not state.profile_stale(run)  # sized runs are immutable (profile_cmd refuses them)


def test_T10_4_a_failed_run_is_neither_listed_nor_opened(tmp_path: Path) -> None:
    """R8b: `run-all` writes logs/FAILED when it fails or is killed; the folder holds a half-made
    run, so the run list, `?run=` and the newest-run fallback all skip it."""
    ok = make_run(tmp_path, "2026-01-01T00-00-00_aaaaaa")
    bad = make_run(tmp_path, "2026-02-01T00-00-00_bbbbbb")
    (bad / state.FAILED_FILE).write_text('{"error_type": "Terminated", "reason": "x"}\n', "utf-8")
    assert not state.is_run(bad) and state.is_run(ok)
    assert state.list_runs(tmp_path) == [ok]
    assert state.resolve_run(tmp_path, bad.name) is None
    assert state.restore({}, {"run": bad.name}, tmp_path) == ok.resolve()  # newest *good* run
