"""whsizing: Streamlit wrapper (F10b), entry page. Start it with `just app`.

No business logic here or in the pages: every computation is a library call or a CLI command run
in-process (`whsizing.app.calls`), writing the same run folders as the terminal.

The public demo (`streamlit_app.py`, `WHSIZING_DEMO_ONLY=1`) shows the same pages on synthetic data.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from whsizing.app import demo, demo_ui, entry, state
from whsizing.app.strings import tr

lg, run = entry.setup("home.title")
st.write(tr("home.intro", lg))
public = demo.demo_only()  # the hosted demo: synthetic data only, visitors do not see each other
st.caption(tr("demo.hosted", lg) if public else tr("home.local", lg))

if public:
    demo_ui.section(lg)  # the sidebar shows the visitor's own run; the runs are not listed
else:
    root = state.runs_root()
    runs = state.list_runs(root)
    with st.expander(tr("demo.title", lg), expanded=not runs):
        demo_ui.section(lg, heading=False)
    st.subheader(tr("home.runs", lg))
    if not runs:
        st.info(tr("home.no_runs", lg, root=root))
    else:
        names = [r.name for r in runs]
        choice = st.selectbox(
            tr("home.open", lg),
            names,
            names.index(run.name) if run is not None and run.name in names else None,
            format_func=lambda n: f"{n}  [{state.stage(root / n)}]",
            key="home.run",
        )
        if choice is not None and (run is None or choice != run.name):
            state.open_run(Path(root / choice))
            st.rerun()
if st.button(tr("home.new", lg)):
    state.close_run()
    st.rerun()

st.subheader(tr("home.pages", lg))
for line in tr("home.steps", lg).split("\n"):
    st.markdown(f"- {line}")
