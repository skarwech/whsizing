"""Page 5: scenario cards (family, overrides bounded by the catalog, eligibility); sizes the run
with the library's `size` and `compare` commands (F10b)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

from whsizing.app import basis_form, demo, demo_limits, demo_ui, entry, scenario_cards, state
from whsizing.app.calls import CliError, call
from whsizing.app.strings import tr
from whsizing.catalog import load_catalog
from whsizing.cli.sizing import compare_cmd, size_cmd
from whsizing.errors import WhsizingError
from whsizing.report import Lang


def size_run(run: Path, basis_path: Path, scenarios_path: Path, lg: Lang) -> None:
    """`whsizing size` then `whsizing compare` on the run, like the terminal."""
    with st.spinner(tr("scn.sizing", lg)):
        try:
            call(
                size_cmd,
                run=run,
                basis=basis_path,
                scenarios=scenarios_path,
                catalog=state.catalog_dir(),
            )
            call(compare_cmd, run=run, sensitivity=True)
        except CliError as e:
            state.cli_error(e, lg)
            return
    st.success(tr("scn.sized", lg))


lg, run = entry.setup("scn.title")
state.banner(lg)
run = state.require_run(lg, run, "ingested")
if state.reached(run, "sized"):
    st.info(tr("scn.sealed", lg))
    saved = state.saved_path(run, "scenarios")
    if saved is not None:
        st.code(saved.read_text(encoding="utf-8"), language="yaml")
    st.stop()

try:
    catalog = load_catalog(state.catalog_dir())
except WhsizingError as e:
    state.error(f"{type(e).__name__}: {e}")
    st.stop()

data = scenario_cards.initial_scenarios(st.session_state.get(state.SCENARIOS))
data, removed = scenario_cards.render_cards(data, catalog, run.name, lg)
if removed:
    kept = [s for i, s in enumerate(data["scenarios"]) if i not in removed]
    data = {**data, "scenarios": kept}
st.session_state[state.SCENARIOS] = data
at_limit = demo.demo_only() and len(data["scenarios"]) >= demo_limits.MAX_SCENARIOS
if removed or st.button(tr("scn.add", lg), disabled=at_limit):
    if not removed:
        st.session_state[state.SCENARIOS] = scenario_cards.with_added(data)
    scenario_cards.reset_widgets()
    st.rerun()

scenario_set, problems = scenario_cards.validate(data, lg)
limits = demo_ui.limit_messages(  # the public demo bounds what a visitor can ask of the engine
    demo_limits.limit_problems(st.session_state.get(state.BASIS) or {}, data, catalog), lg
)
for message in [*problems, *limits]:
    st.error(message)
if scenario_set is not None:
    st.code(yaml.safe_dump(scenario_set.model_dump(mode="json"), sort_keys=False), language="yaml")

c_save, c_size = st.columns(2)
if c_save.button(tr("scn.save", lg), disabled=scenario_set is None or bool(limits)) and (
    scenario_set and not limits
):
    path = state.write_draft(run, "scenarios", scenario_set.model_dump(mode="json"))
    st.success(demo_limits.scrub(tr("scn.saved", lg, path=path)))
if (
    c_size.button(tr("scn.size", lg), type="primary", disabled=scenario_set is None or bool(limits))
    and not limits
):  # a disabled button can still be triggered by a client that is not the page
    basis = st.session_state.get(state.BASIS)
    # page 4 not visited, or its basis invalid (overrides are checked against the catalog too)
    if basis is None or basis_form.validate(basis, catalog)[0] is None:
        st.error(tr("scn.need_basis", lg))
        st.stop()
    if scenario_set is not None:
        basis_path = state.write_draft(run, "basis", basis)
        scenarios_path = state.write_draft(run, "scenarios", scenario_set.model_dump(mode="json"))
        size_run(run, basis_path, scenarios_path, lg)
