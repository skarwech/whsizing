"""Page 3: demand profile charts (Plotly), EIQ table, shipment split (F10b)."""

from __future__ import annotations

import streamlit as st

from whsizing.app import entry, loaders, state
from whsizing.app.calls import CliError, call
from whsizing.app.strings import tr
from whsizing.cli.data import profile_cmd
from whsizing.errors import WhsizingError
from whsizing.report import fmt_number, fmt_pct

lg, run = entry.setup("profile.title")
state.banner(lg)
run = state.require_run(lg, run, "ingested")

if not state.reached(run, "profiled") or state.profile_stale(run):  # staged flow: ingest, profile
    with st.spinner(tr("profile.running", lg)):
        try:
            call(profile_cmd, run=run, cfg=state.profile_cfg_file(run))
            state.mark_profiled(run)
        except CliError as e:
            st.error(f"exit {e.code}: {e.message}")
            st.stop()
basis_file = state.saved_path(run, "basis")
try:
    profile, figures = loaders.profile_view(
        str(run),
        loaders.digest_of(run / "profile" / "demand_profile.json"),
        str(basis_file or ""),
        loaders.digest_of(*([basis_file] if basis_file else [])),
    )
except WhsizingError as e:  # a run of an older engine, or edited by hand
    st.error(f"{type(e).__name__}: {e}")
    st.stop()

cols = st.columns(4)
cols[0].metric(tr("profile.period", lg), f"{profile.period_start} - {profile.period_end}")
cols[1].metric(tr("profile.days", lg), fmt_number(profile.operating_days, lg))
cols[2].metric(tr("profile.peak", lg), fmt_number(profile.seasonality.peak_to_average, lg, 2))
cols[3].metric(tr("profile.dims", lg), fmt_pct(profile.dims_coverage_lines, lg))

st.plotly_chart(figures["daily_lines"])
left, right = st.columns(2)
left.plotly_chart(figures["monthly_index"])
right.plotly_chart(figures["weekday_index"])
st.plotly_chart(figures["intraday_heatmap"])
st.plotly_chart(figures["pareto"])

# -- EIQ table and shipment split
st.subheader(tr("profile.eiq", lg))
eiq = profile.eiq
stats = {
    tr("profile.lines_per_order", lg): eiq.lines_per_order,
    tr("profile.units_per_line", lg): eiq.units_per_line,
    tr("profile.units_per_order", lg): eiq.units_per_order,
    tr("profile.cube_per_order", lg): eiq.cube_per_order_m3,
    tr("profile.weight_per_order", lg): eiq.weight_per_order_kg,
}
table = {tr("profile.metric", lg): list(stats)}
for field in ("mean", "p50", "p90", "p95", "p98", "max", "cv"):
    table[field] = [fmt_number(getattr(s, field), lg, 2) for s in stats.values()]
st.dataframe(table, hide_index=True)
st.caption(
    f"{tr('profile.classes', lg)}: "
    + ", ".join(f"{k} {fmt_pct(v, lg)}" for k, v in eiq.order_class_shares.items())
    + f" | {tr('profile.single_line', lg)} {fmt_pct(eiq.single_line_share, lg)}"
)
st.plotly_chart(figures["lines_per_order_hist"])

st.subheader(tr("profile.split", lg))
split = profile.shipment_split
st.dataframe(
    {
        tr("profile.kind", lg): [tr("profile.parcel", lg), tr("profile.pallet", lg)],
        tr("profile.share_orders", lg): [
            fmt_pct(split.parcel_share_orders, lg),
            fmt_pct(split.pallet_share_orders, lg),
        ],
        tr("profile.share_lines", lg): [
            fmt_pct(split.parcel_share_lines, lg),
            fmt_pct(split.pallet_share_lines, lg),
        ],
    },
    hide_index=True,
)
st.caption(tr("profile.parcels_per_order", lg, n=fmt_number(split.mean_parcels_per_order, lg, 2)))
