"""Page 2: data-quality score badge, blocking issues, warnings with sample rows, coverage (F10b)."""

from __future__ import annotations

import streamlit as st

from whsizing.app import entry, state
from whsizing.app.strings import tr
from whsizing.cli._runio import read_model
from whsizing.errors import WhsizingError
from whsizing.io.dq import DQ_JSON
from whsizing.report import fmt_number, fmt_pct
from whsizing.schemas.ingest import DQReport

lg, run = entry.setup("dq.title")
run = state.require_run(lg, run, "empty")
report_path = run / "dq" / DQ_JSON
if not report_path.is_file():
    st.info(tr("dq.none", lg))
    st.stop()
try:
    report = read_model(report_path, DQReport, "run `whsizing ingest`")
except WhsizingError as e:  # a run of an older engine, or edited by hand
    st.error(f"{type(e).__name__}: {e}")
    st.stop()

# -- score badge
badge = {"usable": st.success, "usable with caveats": st.warning}.get(report.band, st.error)
c_score, c_band = st.columns([1, 3])
c_score.metric(tr("dq.score", lg), f"{report.score:.0f} / 100")
with c_band:
    badge(f"**{report.band}**")
    st.caption(" | ".join(f"{k}: {v:.0f}" for k, v in report.score_breakdown.items()))

# -- blocking issues and warnings
blocking = [r for r in report.rules if r.severity == "blocking"]
warnings = [r for r in report.rules if r.severity == "warning"]
st.subheader(tr("dq.blocking", lg, n=len(blocking)))
if not blocking:
    st.caption(tr("dq.no_blocking", lg))
for rule in blocking:
    st.error(f"**{rule.rule}** ({rule.dataset}): {rule.message}  [{rule.count}]")
    if rule.sample_rows:
        st.dataframe(rule.sample_rows)
st.subheader(tr("dq.warnings", lg, n=len(warnings)))
for rule in warnings:
    title = (
        f"{rule.rule} ({rule.dataset}): {rule.message}  [{rule.count}, {fmt_pct(rule.share, lg)}]"
    )
    with st.expander(title):
        if rule.sample_rows:
            st.caption(tr("dq.sample", lg))
            st.dataframe(rule.sample_rows)
for note in report.notes:
    st.caption(note)

# -- coverage metrics and row counts
st.subheader(tr("dq.coverage", lg))
cols = st.columns(max(len(report.coverage), 1))
for col, (name, value) in zip(cols, report.coverage.items(), strict=False):
    # history_months is a count of months, the other coverage values are shares
    col.metric(name, fmt_number(value, lg, 1) if name == "history_months" else fmt_pct(value, lg))
if report.rows:
    st.caption(" | ".join(f"{name}: {n:,}" for name, n in report.rows.items()))

html = run / "dq" / "dq_report.html"
if html.is_file():
    st.download_button(tr("dq.download", lg), html.read_bytes(), "dq_report.html", "text/html")
