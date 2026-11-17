"""F10b demo mode (T10.4), second review: a busy server, the messages of the pages, a forged click,
and a preview that must not crash. The first review's tests are in test_f10_app_demo.py.

Each page is run through AppTest on a visitor's own run of the demo (`demo.load_demo`); a command
that would size is replaced by a spy or a fake, so that nothing is sized unless a test says so.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from whsizing.app import calls, demo, demo_limits, state
from whsizing.app.calls import BUSY_CODE, CliError, CliResult
from whsizing.app.strings import tr

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "streamlit_app.py"
APP = ROOT / "src" / "whsizing" / "app"
TIMEOUT = 300


@pytest.fixture(autouse=True)
def _restore_error_details() -> Iterator[None]:
    """The entry point sets `client.showErrorDetails` for the whole process: not for other tests."""
    original = st.get_option("client.showErrorDetails")
    yield
    st.set_option("client.showErrorDetails", original)


@pytest.fixture(scope="module")
def demo_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """The environment the hosted demo runs in, with its data and runs under a temp folder."""
    work = tmp_path_factory.mktemp("demo_review")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.DEMO_ENV, "1")
        mp.setenv(demo.WORK_ENV, str(work))
        mp.setenv("WHSIZING_RUNS", str(work / "runs"))
        mp.setenv("WHSIZING_CATALOG", str(ROOT / "catalog"))
        mp.setenv(demo.SALT_ENV, "placeholder")  # set, then removed: the teardown also removes
        mp.delenv(demo.SALT_ENV)  # the salt the demo makes
        mp.delenv("WHSIZING_LANG", raising=False)
        demo.forget_shared()
        yield SimpleNamespace(work=work, runs=work / "runs")
        demo.forget_shared()


@pytest.fixture
def run(demo_env: SimpleNamespace) -> Path:
    """A run of the visitor's own, ingested and not sized (about 3 s)."""
    return demo.load_demo(demo_env.runs)


def page(name: str, run: Path) -> AppTest:
    at = AppTest.from_file(str(APP / "pages" / name), default_timeout=TIMEOUT)
    at.session_state["run_dir"] = str(run)
    at.session_state["lang"] = "en"
    return at.run()


def size_button(at: AppTest) -> Any:
    return next(b for b in at.button if b.label == tr("scn.size", "en"))


def busy(*args: object, **kwargs: object) -> CliResult:
    raise CliError(BUSY_CODE, "another command has been running for over 120 s")


# ----------------------------------------------------------------- what a visitor reads
def test_the_error_of_a_command_on_page_5_shows_no_folder_of_the_server(
    demo_env: SimpleNamespace, run: Path
) -> None:
    """A scenario id the page accepts and the CLI refuses ('bad id!') makes the command fail with
    a message that names the draft it read, under the runs folder of the server."""
    at = page("5_Scenarios.py", run)
    at.text_input(key=f"scn.{run.name}.0.id").set_value("bad id!").run()
    size_button(at).click().run()
    shown = " ".join(e.value for e in at.error)
    assert "<runs>/" in shown and "scenarios.yaml" in shown, shown
    assert str(demo_env.runs) not in shown and str(demo_env.runs.resolve()) not in shown
    assert state.stage(run) == "ingested"  # the command refused it: nothing was sized


def test_a_saved_message_names_the_draft_inside_the_run_not_a_folder_of_the_server(
    run: Path,
) -> None:
    at = page("5_Scenarios.py", run)
    next(b for b in at.button if b.label == tr("scn.save", "en")).click().run()
    saved = [s.value for s in at.success]
    assert saved == [tr("scn.saved", "en", path="ui/scenarios.yaml")], saved
    basis = page("4_Design_basis.py", run)
    next(b for b in basis.button if b.label == tr("basis.save", "en")).click().run()
    assert [s.value for s in basis.success] == [tr("basis.saved", "en", path="ui/basis.yaml")]


def test_without_a_run_the_demo_points_at_the_buttons_it_has(demo_env: SimpleNamespace) -> None:
    at = AppTest.from_file(str(APP / "pages" / "6_Results.py"), default_timeout=TIMEOUT)
    at.session_state["lang"] = "en"
    at.run()
    assert tr("demo.no_run", "en") in [i.value for i in at.info]  # beside the sidebar's banner


def test_at_the_scenario_limit_the_page_says_why_the_add_button_is_disabled(run: Path) -> None:
    """A greyed button with no word about it (found in a real browser)."""
    at = page("5_Scenarios.py", run)
    why = tr("demo.limit.scenarios", "en", max=demo_limits.MAX_SCENARIOS)

    def add() -> Any:
        return next(b for b in at.button if b.label == tr("scn.add", "en"))

    assert why not in [c.value for c in at.caption] and not add().disabled
    for _ in range(demo_limits.MAX_SCENARIOS - 3):  # the demo has three scenarios
        add().click().run()
    assert add().disabled and why in [c.value for c in at.caption]


# --------------------------------------------------------------------- a busy server
def test_a_busy_server_is_a_warning_on_page_5_and_nothing_is_sized(
    monkeypatch: pytest.MonkeyPatch, run: Path
) -> None:
    at = page("5_Scenarios.py", run)
    monkeypatch.setattr(calls, "call", busy)
    size_button(at).click().run()
    assert [w.value for w in at.warning][-1:] == [tr("demo.busy", "en")]
    assert not at.error and not at.exception
    assert state.stage(run) == "ingested"


def test_a_busy_server_is_a_warning_on_the_home_buttons(
    monkeypatch: pytest.MonkeyPatch, demo_env: SimpleNamespace
) -> None:
    at = AppTest.from_file(str(ENTRY), default_timeout=TIMEOUT).run()
    monkeypatch.setattr(demo, "shared_run", busy)
    at.button(key="demo.example").click().run()
    assert tr("demo.busy", "en") in [w.value for w in at.warning]
    assert not at.error and not at.exception


def test_a_run_sized_by_another_tab_gets_the_demo_message_not_the_advice_of_the_terminal(
    monkeypatch: pytest.MonkeyPatch, run: Path
) -> None:
    at = page("5_Scenarios.py", run)

    def sealed(*args: object, **kwargs: object) -> CliResult:
        message = "<runs>/x: already sized and runs are immutable; whsizing rerun makes a new one"
        raise CliError(2, message)

    monkeypatch.setattr(calls, "call", sealed)
    size_button(at).click().run()
    infos = [i.value for i in at.info]
    assert tr("demo.sealed", "en") in infos
    assert not at.error and "whsizing rerun" not in " ".join(infos)


# ---------------------------------------------------- size and compare under one lock
def test_size_then_compare_are_called_while_one_visitor_holds_the_lock_on_page_5(
    monkeypatch: pytest.MonkeyPatch, run: Path
) -> None:
    """The lock is not a queue: a `compare` that had to wait behind other visitors' commands could
    give up (busy) after its `size`, leaving a run that is sized and cannot be compared."""
    at = page("5_Scenarios.py", run)
    held: list[bool] = []

    def spy(command: Any, **kwargs: Any) -> CliResult:
        held.append(calls._LOCK._is_owned())  # pyright: ignore[reportAttributeAccessIssue]
        return CliResult("", "")

    monkeypatch.setattr(calls, "call", spy)
    size_button(at).click().run()
    assert held == [True, True], held
    assert not at.error and not at.exception


def test_the_shared_example_is_sized_and_compared_while_one_visitor_holds_the_lock(
    monkeypatch: pytest.MonkeyPatch, run: Path
) -> None:
    held: list[bool] = []

    def spy(command: Any, **kwargs: Any) -> CliResult:
        held.append(calls._LOCK._is_owned())  # pyright: ignore[reportAttributeAccessIssue]
        return CliResult("", "")

    monkeypatch.setattr(demo, "call", spy)
    demo.size_demo(run, ROOT / "catalog")
    assert held == [True, True], held


# ------------------------------------------------------------------- a forged click
def test_a_forged_click_on_the_disabled_size_button_runs_nothing(run: Path) -> None:
    """What a client that is not the page can send: a seventh card in the session, then the click
    on the button the page has disabled."""
    at = page("5_Scenarios.py", run)
    cards = at.session_state[state.SCENARIOS]
    seventh = [{"id": f"X{i}", "family": "manual_p2p"} for i in range(demo_limits.MAX_SCENARIOS)]
    at.session_state[state.SCENARIOS] = {**cards, "scenarios": [*cards["scenarios"], *seventh]}
    at.run()
    wanted = tr("demo.limit.scenarios", "en", max=demo_limits.MAX_SCENARIOS)
    assert wanted in [e.value for e in at.error] and size_button(at).disabled
    forged = size_button(at)
    forged.proto.disabled = False  # what a crafted trigger message does: the server never sees it
    forged.click().run()
    assert wanted in [e.value for e in at.error] and not at.exception
    assert state.stage(run) == "ingested"  # nothing ran


# --------------------------------------------------- a preview that must not crash
@pytest.mark.filterwarnings("ignore:divide by zero:RuntimeWarning")  # a parcel weight of 0
@pytest.mark.parametrize(
    ("leaf", "value"),
    [
        ("timezone", "Not/AZone"),
        ("flows.parcel_max_weight_kg", 0.0),
        ("projection.trailing_months", 10**9),
    ],
)
def test_a_form_value_no_rule_refuses_is_a_message_on_page_4_not_an_exception(
    run: Path, leaf: str, value: str | float
) -> None:
    """Found in a real browser: a time zone that is none, a parcel weight of 0 and a design-day
    window of a billion months passed the form and made the preview raise (polars errors): an
    unhandled exception box and a traceback with server paths in the log, not a message."""
    at = page("4_Design_basis.py", run)
    key = f"basis.{run.name}.{leaf}"
    if isinstance(value, str):
        at.text_input(key=key).set_value(value).run()
    else:
        at.number_input(key=key).set_value(value).run()
    assert not at.exception
    shown = " ".join(e.value for e in at.error)
    assert shown  # a message, named after the error's type
    assert os.environ["WHSIZING_RUNS"] not in shown  # and with no folder of the server
