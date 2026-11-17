"""F10b demo mode (T10.4): the public demo on Streamlit Community Cloud, through AppTest.

`streamlit_app.py` is the entry point the platform runs: the app's own pages behind `st.navigation`,
in demo-only mode (no upload, no typed server path, synthetic data generated on demand, a visitor
only sees the demo's runs). The full app (`Home.py`, `just app`) refuses an address the network can
reach. The Streamlit-free part is tested in tests/unit/test_f10_app_demo_data.py.
"""

from __future__ import annotations

import ast
import json
import sys
import time
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from whsizing.app import demo, demo_ui, state
from whsizing.app.strings import tr

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "streamlit_app.py"
APP = ROOT / "src" / "whsizing" / "app"
TIMEOUT = 300
HOME, UPLOAD, SCENARIOS, RESULTS = (
    "src/whsizing/app/Home.py",
    "src/whsizing/app/pages/1_Upload.py",
    "src/whsizing/app/pages/5_Scenarios.py",
    "src/whsizing/app/pages/6_Results.py",
)


@pytest.fixture(scope="module")
def demo_env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SimpleNamespace]:
    """The environment the hosted demo runs in, with its data and runs under a temp folder."""
    work = tmp_path_factory.mktemp("demo_e2e")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(demo.DEMO_ENV, "1")
        mp.setenv(demo.WORK_ENV, str(work))
        mp.setenv("WHSIZING_RUNS", str(work / "runs"))
        mp.setenv("WHSIZING_CATALOG", str(ROOT / "catalog"))
        mp.delenv(demo.SALT_ENV, raising=False)
        mp.delenv("WHSIZING_LANG", raising=False)
        demo.forget_shared()
        yield SimpleNamespace(work=work, runs=work / "runs")
        demo.forget_shared()


def entry() -> AppTest:
    return AppTest.from_file(str(ENTRY), default_timeout=TIMEOUT)


def fake_run(runs: Path, name: str, *, demo_marker: bool) -> Path:
    """A folder that passes `state.is_run`; marked as a demo run or not."""
    run = runs / name
    (run / "canonical").mkdir(parents=True)
    (run / "dq").mkdir()
    if demo_marker:
        (run / "ui").mkdir()
        meta = {"demo": True, "shared": False, "created": time.time()}
        (run / demo.MARKER).write_text(json.dumps(meta), encoding="utf-8")
    return run


def uploaders(at: AppTest) -> list[object]:
    return list(at.get("file_uploader"))


# ------------------------------------------------------------------------- the entry point
def test_T10_4_demo_entry_point_sets_the_demo_defaults_before_it_imports_streamlit() -> None:
    """The hosted app is demo-only by construction: the flag, a temp runs folder and the catalog
    path are set before anything else runs, and `src/` is made importable for a host that
    installs the dependencies without the project."""
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    assigned: dict[str, int] = {}
    streamlit_import = None
    for node in tree.body:
        text = ast.unparse(node)
        for name in ("WHSIZING_DEMO_ONLY", "WHSIZING_RUNS", "WHSIZING_CATALOG"):
            if f"setdefault('{name}'" in text:  # ast.unparse writes single quotes
                assigned[name] = node.lineno
        if isinstance(node, ast.Import) and any(a.name == "streamlit" for a in node.names):
            streamlit_import = node.lineno
    assert streamlit_import is not None
    assert set(assigned) == {"WHSIZING_DEMO_ONLY", "WHSIZING_RUNS", "WHSIZING_CATALOG"}
    assert all(line < streamlit_import for line in assigned.values())
    assert "sys.path.insert" in ENTRY.read_text(encoding="utf-8")


def test_T10_4_demo_entry_point_lists_existing_pages_and_the_results_page_demo_ui_opens() -> None:
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
    values = {
        t.id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        for t in n.targets
        if isinstance(t, ast.Name) and t.id in {"APP", "PAGES"}
    }
    assert values["APP"] == demo_ui.APP  # the two copies of the pages folder agree
    paths = [f"{values['APP']}/{page[0]}" for page in values["PAGES"]]
    assert all((ROOT / p).is_file() for p in paths)
    assert f"{demo_ui.APP}/{demo_ui.RESULTS}" in paths  # st.switch_page needs a registered page
    assert len({page[2] for page in values["PAGES"]}) == len(values["PAGES"])  # unique URLs


def test_T10_4_demo_opens_on_the_home_page_with_the_banner_and_the_two_buttons(
    demo_env: SimpleNamespace,
) -> None:
    at = entry().run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Warehouse sizing"]  # no browser locale: English
    assert "Public demo" in at.sidebar.info[0].value
    assert at.button(key="demo.example").label.startswith("Open the finished example")
    assert at.button(key="demo.load").label.startswith("Load the demo data")
    assert not at.selectbox  # the runs of other visitors are not listed


def test_T10_4_demo_upload_page_takes_no_file_and_no_server_path(demo_env: SimpleNamespace) -> None:
    at = entry().run()
    at.switch_page(UPLOAD).run()
    assert not at.exception
    assert uploaders(at) == []
    assert not at.text_input  # the typed-path field reads any file of the server: not offered
    assert "Uploads are disabled" in at.warning[0].value
    assert at.button(key="demo.example") and at.button(
        key="demo.load"
    )  # the demo is offered instead


def test_T10_4_the_upload_check_can_fail_the_full_app_still_takes_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control for the test above: with the demo off the same page does show an uploader and the
    typed-path field, so an empty list is the demo's doing."""
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    at = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT).run()
    assert len(uploaders(at)) == 1
    assert len(at.text_input) >= 1


def test_T10_4_the_visitors_language_is_kept_from_page_to_page(demo_env: SimpleNamespace) -> None:
    """A page switch leaves the previous page's radio value as stale state: without the re-assign
    in `state.init` every page went back to French."""
    at = entry().run()
    assert at.session_state["lang"] == "en"
    at.switch_page(UPLOAD).run()
    assert at.session_state["lang"] == "en"
    assert [t.value for t in at.title] == ["1 Upload and mapping"]
    at.sidebar.radio[0].set_value("fr").run()
    at.switch_page(HOME).run()
    assert at.session_state["lang"] == "fr"
    assert [t.value for t in at.title] == ["Dimensionnement d'entrepôt"]


def test_T10_4_a_browser_in_french_gets_the_french_demo(
    demo_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(state, "browser_lang", lambda: "fr")
    at = entry().run()
    assert at.session_state["lang"] == "fr"
    monkeypatch.undo()
    assert state.browser_lang() == "en"  # no browser session in a test: English


def test_T10_4_a_set_language_wins_over_the_browser(
    demo_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_LANG", "fr")
    assert state.default_lang() == "fr"
    monkeypatch.setenv("WHSIZING_LANG", "en")
    assert state.default_lang() == "en"


# ------------------------------------------------------------------- visitors are separated
def test_T10_4_a_visitor_does_not_land_in_somebody_elses_run(demo_env: SimpleNamespace) -> None:
    """The full app opens the newest run of the folder; on a shared demo server that is another
    visitor's. Here a run without the demo marker is never opened, listed or named in `?run=`."""
    foreign = fake_run(demo_env.runs, "2099-01-01T00-00-00_foreign", demo_marker=False)
    mine = fake_run(demo_env.runs, "2000-01-01T00-00-00_mine", demo_marker=True)

    at = entry().run()
    assert "run_dir" not in at.session_state  # the newest run is the foreign one: not taken
    assert not at.selectbox

    at = entry()
    at.query_params["run"] = foreign.name
    at.run()
    assert "run_dir" not in at.session_state
    assert "run" not in at.query_params  # the entry guard dropped it

    at = entry()
    at.query_params["run"] = mine.name
    at.run()
    assert at.session_state["run_dir"] == str(mine.resolve())  # a refresh keeps the visitor's run

    at = entry()
    at.query_params["run"] = str(foreign)  # a path is no run name, whatever it points at
    at.run()
    assert "run_dir" not in at.session_state


def test_T10_4_the_full_app_still_lists_every_run_and_opens_the_newest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Control: the isolation is the demo's, the local app keeps its behaviour."""
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    older = fake_run(tmp_path / "runs", "2000-01-01T00-00-00_a", demo_marker=False)
    newer = fake_run(tmp_path / "runs", "2099-01-01T00-00-00_b", demo_marker=False)
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=TIMEOUT).run()
    assert at.session_state["run_dir"] == str(newer.resolve())
    assert at.selectbox(key="home.run").options == [
        f"{newer.name}  [empty]",
        f"{older.name}  [empty]",
    ]


# --------------------------------------------------------------- the full app and the network
Serve = Callable[[str | None], None]


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Serve:
    """The full app as `just app` serves it: no demo flag, no remote allowance, a runs folder;
    `address` is the value Streamlit reports for `server.address`."""
    monkeypatch.delenv(demo.DEMO_ENV, raising=False)
    monkeypatch.delenv(state.ALLOW_REMOTE_ENV, raising=False)
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    original = st.get_option

    def at_address(address: str | None) -> None:
        def get_option(name: str) -> object:
            return address if name == "server.address" else original(name)

        monkeypatch.setattr(st, "get_option", get_option)

    return at_address


@pytest.mark.parametrize("address", [None, "", "0.0.0.0", "::", "192.168.1.20", "myhost.local"])
def test_T10_4_the_full_app_refuses_an_address_the_network_can_reach(
    served: Serve, address: str | None
) -> None:
    served(address)
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=TIMEOUT).run()
    assert not at.exception
    assert len(at.error) == 1
    assert "WHSIZING_ALLOW_REMOTE" in at.error[0].value  # says how to proceed
    assert not at.title and not at.button  # nothing of the app was served


@pytest.mark.parametrize("address", ["127.0.0.1", "localhost", "::1"])
def test_T10_4_the_full_app_starts_on_loopback(served: Serve, address: str) -> None:
    served(address)
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=TIMEOUT).run()
    assert not at.exception and not at.error
    assert at.title


def test_T10_4_the_full_app_starts_anywhere_when_an_authenticating_proxy_is_vouched_for(
    served: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    served("0.0.0.0")
    monkeypatch.setenv(state.ALLOW_REMOTE_ENV, "1")
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=TIMEOUT).run()
    assert not at.error and at.title


def test_T10_4_the_demo_is_served_on_any_address(
    served: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic data, no upload, no server path: nothing to protect, and the platform that hosts
    the demo has to reach it."""
    served("0.0.0.0")
    monkeypatch.setenv(demo.DEMO_ENV, "1")
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=TIMEOUT).run()
    assert not at.error and at.title


# ------------------------------------------------------------------------ the two demo flows
@pytest.mark.slow
def test_T10_4_the_finished_example_is_built_once_and_every_visitor_opens_it(
    demo_env: SimpleNamespace,
) -> None:
    first = entry().run()
    first.button(key="demo.example").click().run()
    assert not first.exception and not first.error
    assert [t.value for t in first.title] == ["6 Results"]  # st.switch_page landed on page 6
    run = Path(first.session_state["run_dir"])
    assert demo.is_demo_run(run) and state.stage(run) == "compared"
    assert [h.value for h in first.header][:2] == ["Comparison", "Staffing (FTE)"]
    assert len(first.dataframe) >= 5  # the tables of the study

    second = entry().run()  # another visitor
    second.button(key="demo.example").click().run()
    assert not second.exception and not second.error
    assert Path(second.session_state["run_dir"]) == run  # the same finished study, not a new one

    # a visitor opening the page on their own sees the study through `?run=` as well
    again = entry()
    again.query_params["run"] = run.name
    again.run()
    again.switch_page(RESULTS).run()
    assert not again.exception
    assert [t.value for t in again.title] == ["6 Results"]


@pytest.mark.slow
def test_T10_4_step_by_step_gives_the_visitor_a_run_of_their_own_and_the_pages_size_it(
    demo_env: SimpleNamespace,
) -> None:
    at = entry().run()
    at.button(key="demo.load").click().run()
    assert not at.exception and not at.error
    run = Path(at.session_state["run_dir"])
    assert demo.is_demo_run(run) and state.stage(run) == "ingested"
    assert at.success[0].value.startswith("Demo data loaded into run")
    marker = json.loads((run / demo.MARKER).read_text(encoding="utf-8"))
    assert marker["shared"] is False  # a run of the visitor's own, not the finished example

    # pages 4 and 5 start from the demo basis and scenarios the run was given
    assert at.session_state[state.BASIS]["client"].startswith("Demo")
    at.switch_page(SCENARIOS).run()
    assert not at.exception
    size = next(b for b in at.button if b.label == tr("scn.size", "en"))
    size.click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert tr("scn.sized", "en") in [s.value for s in at.success]
    assert state.stage(run) == "compared"

    at.switch_page(RESULTS).run()
    assert not at.exception
    assert [h.value for h in at.header][:1] == ["Comparison"]


@pytest.mark.slow
def test_T10_4_a_host_without_pango_gets_an_error_for_the_pdf_and_the_app_stays_up(
    demo_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WeasyPrint needs the Pango system library (`packages.txt` on the hosted demo). Without it
    the failure shows up when the PDF is built, as an OSError from the dynamic loader: the page
    must show it as a message, and the Excel export must keep working."""
    run = demo.shared_run(demo_env.runs, ROOT / "catalog")
    broken = types.ModuleType("weasyprint")

    def missing(name: str) -> object:
        raise OSError("cannot load library 'libpango-1.0-0': libpango-1.0-0: not found")

    broken.__getattr__ = missing  # type: ignore[attr-defined]  # `from weasyprint import HTML` fails
    monkeypatch.setitem(sys.modules, "weasyprint", broken)

    at = entry()
    at.session_state["run_dir"] = str(run)
    at.run()
    at.switch_page(RESULTS).run()
    assert not at.exception
    at.button(key="export.pdf").click().run()
    assert not at.exception  # a message, not a crash
    assert any("libpango" in e.value for e in at.error), [e.value for e in at.error]
    assert [h.value for h in at.header][:1] == ["Comparison"]  # the page is still there

    at.button(key="export.xlsx").click().run()
    assert not at.exception
    assert any(".xlsx" in s.value for s in at.success)  # the Excel export does not need Pango
