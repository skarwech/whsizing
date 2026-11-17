"""The demo section of the Home page and of the (demo-only) upload page.

Two buttons: the finished example (one shared run, built once per server process) and the demo
data loaded into a run of the visitor's own, to walk through pages 2 to 6. All the work is
`whsizing.app.demo`, which runs the same CLI commands as the terminal; this module only shows it.
"""

from __future__ import annotations

import streamlit as st
from streamlit.errors import StreamlitAPIException

from whsizing.app import demo, state
from whsizing.app.calls import CliError
from whsizing.app.strings import tr
from whsizing.errors import WhsizingError
from whsizing.report import Lang

NOTICE = "demo.notice"  # session key: the message of the last build, shown once after the rerun
APP = "src/whsizing/app"  # where `streamlit_app.py` finds the pages (relative to the repository)
RESULTS = "pages/6_Results.py"  # the file-based multipage app of `just app` (Home.py)


def results_page() -> str:
    """The path `st.switch_page` needs, relative to the entry file: `streamlit_app.py`
    (`st.navigation` over the page files) in the demo, `Home.py` (its `pages/` folder) locally."""
    return f"{APP}/{RESULTS}" if demo.demo_only() else RESULTS


def goto_results(lg: Lang) -> None:
    """Open page 6; when the page cannot be found (a page run on its own) say where it is."""
    try:
        st.switch_page(results_page())
    except StreamlitAPIException:
        st.info(tr("demo.next", lg))


def _failed(lg: Lang, error: Exception) -> None:
    if isinstance(error, CliError):
        st.error(tr("demo.error", lg, code=error.code, message=error.message))
    else:
        st.error(f"{type(error).__name__}: {error}")


def open_example(lg: Lang) -> None:
    """The finished example (built by the first visitor, then instant) opened on page 6."""
    with st.spinner(tr("demo.building", lg)):
        try:
            run = demo.shared_run(state.runs_root(), state.catalog_dir())
        except (CliError, WhsizingError) as e:
            _failed(lg, e)
            return
    state.open_run(run)
    goto_results(lg)


def load_steps(lg: Lang) -> None:
    """The demo datasets ingested into a run of the visitor's own; the rerun shows the new run."""
    with st.spinner(tr("demo.loading", lg)):
        try:
            run = demo.load_demo(state.runs_root())
        except (CliError, WhsizingError) as e:
            _failed(lg, e)
            return
    state.open_run(run)
    st.session_state[NOTICE] = tr("demo.loaded", lg, run=run.name)
    st.rerun()


def section(lg: Lang, *, heading: bool = True) -> None:
    """The title, the two buttons and the message of the last build."""
    if heading:
        st.subheader(tr("demo.title", lg))
    st.write(tr("demo.intro", lg))
    notice = st.session_state.pop(NOTICE, None)
    if notice:
        st.success(notice)
    example, steps = st.columns(2)
    if example.button(tr("demo.example", lg), type="primary", key="demo.example"):
        open_example(lg)
    if steps.button(tr("demo.load", lg), key="demo.load"):
        load_steps(lg)
