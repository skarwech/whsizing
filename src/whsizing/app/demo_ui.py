"""The demo section of the Home page and of the (demo-only) upload page.

Two buttons: the finished example (one shared run, built once per server process) and the demo
data loaded into a run of the visitor's own, to walk through pages 2 to 6. All the work is
`whsizing.app.demo`, which runs the same CLI commands as the terminal; this module only shows it.
"""

from __future__ import annotations

import streamlit as st
from streamlit.errors import StreamlitAPIException

from whsizing.app import demo, state
from whsizing.app.calls import BUSY_CODE, CliError
from whsizing.app.demo_limits import Problem
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


def limit_messages(problems: list[Problem], lg: Lang) -> list[str]:
    """The texts of `demo_limits.limit_problems` in the visitor's language."""
    return [tr(key, lg, **values) for key, values in problems]


def _failed(lg: Lang, error: Exception) -> None:
    if isinstance(error, CliError) and error.code == BUSY_CODE:
        st.warning(tr("demo.busy", lg))
    elif isinstance(error, CliError):
        state.error(tr("demo.error", lg, code=error.code, message=error.message))
    else:
        state.error(f"{type(error).__name__}: {error}")


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


def show_notice() -> None:
    """The message of the last build, once (the build asked for a rerun to show the new run)."""
    notice = st.session_state.pop(NOTICE, None)
    if notice:
        st.success(notice)


def section(lg: Lang, *, heading: bool = True, notice: bool = True) -> None:
    """The title, the two buttons and the message of the last build (`notice=False`: the caller
    shows it, outside a collapsed expander for instance)."""
    if heading:
        st.subheader(tr("demo.title", lg))
    st.write(tr("demo.intro", lg))
    if notice:
        show_notice()
    example, steps = st.columns(2)
    if example.button(tr("demo.example", lg), type="primary", key="demo.example"):
        open_example(lg)
    if steps.button(tr("demo.load", lg), key="demo.load"):
        load_steps(lg)
