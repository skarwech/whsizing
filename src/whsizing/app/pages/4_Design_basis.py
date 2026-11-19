"""Page 4: design basis form (from the DesignBasis schema), live design-day preview (F10b)."""

from __future__ import annotations

import json

import streamlit as st

from whsizing.app import basis_form, demo, demo_limits, demo_ui, entry, loaders, state
from whsizing.app.strings import tr
from whsizing.cli._runio import read_model
from whsizing.design import load_basis
from whsizing.errors import WhsizingError
from whsizing.report import Lang, fmt_number
from whsizing.schemas import DesignDay


def show_design_day(day: DesignDay, lg: Lang) -> None:
    """The headline numbers of a design day and its flags."""
    st.subheader(tr("basis.preview", lg))
    st.caption(
        tr("basis.reference", lg, percentile=day.percentile, date=day.reference_date.isoformat())
    )
    metrics = (
        ("lines", day.lines, 0),
        ("orders", day.orders, 0),
        ("units", day.units, 0),
        ("cube_m3", day.cube_m3, 1),
        ("peak_hour_lines", day.peak_hour_lines, 0),
        ("parcels", day.parcels, 0),
        ("pallets_out", day.pallets_out, 1),
        ("stock_cube_m3", day.stock_cube_m3, 0),
    )
    for col, (name, value, nd) in zip(st.columns(2), metrics[:2], strict=True):
        col.metric(tr(f"dd.{name}", lg), fmt_number(value, lg, nd))
    for col, (name, value, nd) in zip(st.columns(2), metrics[2:4], strict=True):
        col.metric(tr(f"dd.{name}", lg), fmt_number(value, lg, nd))
    st.dataframe(
        {
            tr("dd.metric", lg): [tr(f"dd.{n}", lg) for n, _, _ in metrics[4:]],
            tr("dd.value", lg): [fmt_number(v, lg, nd) for _, v, nd in metrics[4:]],
        },
        hide_index=True,
    )
    for flag in [*day.flags, *day.inbound.flags]:
        {"info": st.info, "warning": st.warning}.get(flag.severity, st.error)(
            f"{flag.code}: {flag.message}"
        )


lg, run = entry.setup("basis.title")
state.banner(lg)
run = state.require_run(lg, run, "ingested")

if state.reached(run, "sized"):  # runs are immutable (§2.4): show what the run used
    st.info(tr("basis.sealed", lg))
    saved = state.saved_path(run, "basis")
    if saved is not None:
        st.code(saved.read_text(encoding="utf-8"), language="yaml")
    try:
        show_design_day(
            read_model(run / "design" / "design_day.json", DesignDay, "run `whsizing size`"), lg
        )
    except WhsizingError as e:  # a run of an older engine, or edited by hand
        state.error(f"{type(e).__name__}: {e}")
    st.stop()

st.caption(tr("basis.intro", lg))
left, right = st.columns([3, 2])
with left:
    flat = basis_form.initial_values(st.session_state.get(state.BASIS))
    new_flat, problems = basis_form.render_form(flat, f"basis.{run.name}", lg)
nested = basis_form.nest(new_flat)
st.session_state[state.BASIS] = nested
catalog_path = state.catalog_dir()
catalog_key = loaders.digest_of(catalog_path)
try:
    catalog = loaders.catalog_of(str(catalog_path), catalog_key)
except WhsizingError as e:
    state.error(f"{type(e).__name__}: {e}")
    st.stop()
basis, errors = basis_form.validate(nested, catalog)  # the overrides must name catalog parameters
limits = demo_ui.limit_messages(demo_limits.limit_problems(nested, {}, catalog), lg)  # demo only
errors = [*problems, *errors, *limits]

preview_failed = False
with right:
    if errors:
        for message in errors:
            st.error(message)
    else:
        try:
            day = loaders.design_preview(
                str(run),
                loaders.canonical_digest(run),
                json.dumps(nested, sort_keys=True),
                str(catalog_path),
                catalog_key,
            )
            show_design_day(day, lg)
        except WhsizingError as e:
            preview_failed = True
            state.error(f"{type(e).__name__}: {e}")
        except Exception as e:  # a value the form lets through that no rule of the library
            preview_failed = True  # refuses (a time zone): a message, not a crash
            if demo.demo_only():  # the library's own text names a setting a visitor cannot reach
                st.error(tr("basis.preview_failed", lg, type=type(e).__name__))
            else:
                state.error(f"{type(e).__name__}: {e}")

blocked = bool(errors) or preview_failed
if st.button(tr("basis.save", lg), type="primary", disabled=blocked) and not blocked:
    path = state.write_draft(run, "basis", nested)
    try:
        load_basis(path)  # the loader of the CLI: same checks
        st.success(demo_limits.scrub(tr("basis.saved", lg, path=state.shown_path(run, path))))
    except WhsizingError as e:
        state.error(str(e))
