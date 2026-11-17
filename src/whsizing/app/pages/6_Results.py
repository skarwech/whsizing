"""Page 6: comparison table, FTE chart, area block diagrams, business case, sensitivity, the
'why this number?' drill-down and the exports (F10b)."""

from __future__ import annotations

import streamlit as st

from whsizing.app import entry, loaders, results_ui, state
from whsizing.app.strings import tr
from whsizing.errors import WhsizingError

lg, run = entry.setup("results.title")
state.banner(lg)
run = state.require_run(lg, run, "compared")
digest = state.run_digest(run)
try:
    data = loaders.report_data(str(run), lg, digest)
except WhsizingError as e:
    state.error(f"{type(e).__name__}: {e}")
    st.stop()
tables = data.tables
all_worlds = st.toggle(tr("results.all_worlds", lg), False, key="results.worlds")
st.caption(data.source_note)

st.header(tr("results.comparison", lg))
results_ui.show_table(tables["summary"], lg, all_worlds, keys=("comparison", "ranking"), pick=data)

st.header(tr("results.fte", lg))
results_ui.chart(data, "fte", lg)
results_ui.show_table(tables["fte"], lg, all_worlds, keys=("heads", "roster"))

st.header(tr("results.area", lg))
results_ui.diagrams(data)

st.header(tr("results.business", lg))
results_ui.chart(data, "tco", lg)
results_ui.show_table(tables["capex_opex"], lg, all_worlds)
results_ui.chart(data, "cash", lg)
results_ui.show_table(tables["cash_flow"], lg, all_worlds)

st.header(tr("results.sensitivity", lg))
if data.run.sensitivity is None:
    st.info(tr("results.no_sensitivity", lg))
else:
    results_ui.chart(data, "tornado", lg)
    results_ui.chart(data, "sweep", lg)
    results_ui.show_table(tables["sensitivity"], lg, all_worlds)

st.header(tr("results.why", lg))
st.caption(tr("results.why_help", lg))
results_ui.drill_down(data, lg)

st.header(tr("results.export", lg))
results_ui.export_section(run, lg)
