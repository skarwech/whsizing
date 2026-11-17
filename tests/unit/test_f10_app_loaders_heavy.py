"""F10b the turns of the page loaders (`loaders._HEAVY`): each heavy computation takes one, and no
call takes two.

`st.cache_data` computes a miss in the visitor's own script thread, so without a turn the visitors
run side by side (eight at once took the demo from 0.9 to 2.8 GB). A call that took a second turn
inside the first (a cached function calling another one) could make two visitors wait for each
other: the turns are never nested. `test_f10_app_demo_limits.py` runs the semaphore itself with
eight threads on `design_preview`; here every other loader is checked to use it, with the heavy
work replaced by fakes that record how many turns are held when they run.
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any

import pytest

from whsizing.app import loaders


class Turns:
    """Stands in for the semaphore: counts the turns taken and the most held at once."""

    def __init__(self) -> None:
        self.taken = 0
        self.held = 0
        self.most_held = 0
        self.held_when_working: list[int] = []

    def __enter__(self) -> Turns:
        self.taken += 1
        self.held += 1
        self.most_held = max(self.most_held, self.held)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.held -= 1

    def work(self, result: Any) -> Any:
        """A fake of the heavy call: how many turns are held while it runs."""
        self.held_when_working.append(self.held)
        return result


@pytest.fixture
def turns(monkeypatch: pytest.MonkeyPatch) -> Turns:
    recorder = Turns()
    monkeypatch.setattr(loaders, "_HEAVY", recorder)
    monkeypatch.setattr(loaders, "dataset_hash", lambda tables: recorder.work("hash"))
    monkeypatch.setattr(loaders, "load_canonical", lambda folder: "tables")
    monkeypatch.setattr(loaders, "load_run", lambda run: recorder.work("run output"))
    monkeypatch.setattr(loaders, "load_report_data", lambda run, lang: recorder.work("report"))
    monkeypatch.setattr(loaders, "profile_cfg_of", lambda run: "cfg")
    monkeypatch.setattr(loaders, "build_tables", lambda *a, **k: recorder.work("tables"))
    monkeypatch.setattr(loaders, "read_model", lambda *a, **k: "profile")
    figures = {name: (lambda profile, tables: (None, "figure")) for name in loaders.PROFILE_FIGURES}
    monkeypatch.setattr(loaders, "CHARTS", figures)
    for cached in (loaders.tables_hash, loaders.output, loaders.report_data, loaders.profile_view):
        cached.clear()
    return recorder


@pytest.mark.parametrize(
    ("name", "call", "turns_taken"),
    [
        ("tables_hash", lambda run: loaders.tables_hash(run, "k"), 1),
        ("output", lambda run: loaders.output(run, "k"), 1),
        ("report_data", lambda run: loaders.report_data(run, "en", "k"), 2),  # its own and output's
        ("profile_view", lambda run: loaders.profile_view(run, "h", "", "b"), 1),
    ],
)
def test_every_heavy_loader_takes_its_turn_and_never_holds_two(
    turns: Turns, tmp_path: Path, name: str, call: Any, turns_taken: int
) -> None:
    call(str(tmp_path / name))  # distinct arguments: no cache hit to share
    assert turns.taken == turns_taken, name
    assert turns.most_held == 1, f"{name} held {turns.most_held} turns at once"
    assert set(turns.held_when_working) <= {1}, f"{name} worked outside a turn"
    loaders.tables_hash.clear()
    loaders.output.clear()
    loaders.report_data.clear()
    loaders.profile_view.clear()
