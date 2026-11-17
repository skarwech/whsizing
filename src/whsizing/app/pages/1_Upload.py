"""Page 1: upload, sniff summary, mapping table, unit hints, 'Run ingest' (F10b)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from whsizing.app import entry, ingest_ui, state
from whsizing.app.strings import tr
from whsizing.io.readers import read_any
from whsizing.report import Lang
from whsizing.schemas.ingest import DQReport, Mapping
from whsizing.schemas.params import DatasetKind

DATASET_ORDER: tuple[DatasetKind, ...] = ("sku_master", "order_lines", "inventory", "receipts")


def ingest_section(
    lg: Lang, run: Path | None, dataset: DatasetKind, files: list[Path], mapping: Mapping
) -> None:
    """The salt, the 'add to this run' choice and the 'Run ingest' button with its outcome."""
    st.subheader(tr("upload.ingest", lg))
    if not ingest_ui.salt_ready():
        salt = st.text_input(tr("upload.salt", lg), type="password", key="up.salt")
        if salt:
            ingest_ui.set_salt(salt)
    if not ingest_ui.salt_ready():
        st.info(tr("upload.salt_needed", lg))
        st.stop()
    into = run is not None and not state.reached(run, "sized")
    add = into and st.checkbox(tr("upload.add_to_run", lg, run=run.name if run else ""), True)
    if not st.button(tr("upload.run", lg), type="primary"):
        return
    with st.spinner(tr("upload.running", lg)):
        outcome = ingest_ui.run_ingest(dataset, files, mapping, run if add else None)
    if outcome.run is not None:
        state.open_run(outcome.run)
        st.session_state[state.MAPPING] = {
            **st.session_state.get(state.MAPPING, {}),
            dataset: mapping.model_dump(),
        }
    if outcome.error is not None:
        st.error(f"exit {outcome.error.code}: {outcome.error.message}")
        if outcome.run is not None:
            st.info(tr("upload.see_dq", lg))
    elif outcome.run is not None:
        dq = DQReport.model_validate_json(
            (outcome.run / "dq" / "dq_report.json").read_text("utf-8")
        )
        st.success(
            tr("upload.done", lg, run=outcome.run.name, score=f"{dq.score:.0f}", band=dq.band)
        )


def main(uploaded: list[Path]) -> None:
    """The page. `uploaded` collects the disk copies of the uploads (deleted by the caller)."""
    lg, run = entry.setup("upload.title")
    st.caption(tr("upload.privacy", lg))
    dataset: DatasetKind = st.selectbox(tr("upload.dataset", lg), DATASET_ORDER, key="up.dataset")
    if dataset != "sku_master":
        st.caption(tr("upload.order", lg))
    files = ingest_ui.collect_files(dataset, lg, uploaded)
    if not files:
        st.info(tr("upload.nothing", lg))
        st.stop()

    # -- sniff summary and the first rows of the first file
    try:
        raw = read_any(files[0])
    except Exception as e:  # a client file: any reader error is a message, not a traceback
        st.error(f"{type(e).__name__}: {e}")
        st.stop()
    st.subheader(tr("upload.sniff", lg))
    sniffed = {k: str(v) for k, v in raw.sniff.model_dump().items()}
    st.dataframe({"field": list(sniffed), "value": list(sniffed.values())}, hide_index=True)
    st.dataframe(raw.df.head(5))

    # -- mapping table and unit hints
    key = f"map.{dataset}.{files[0].name}"
    st.subheader(tr("upload.mapping", lg))
    mapping = ingest_ui.mapping_table(raw, dataset, key, lg)
    if isinstance(mapping, str):
        st.error(mapping)
        st.stop()
    ingest_section(lg, run, dataset, files, ingest_ui.unit_hints(raw, mapping, key, lg))


saved: list[Path] = []
try:
    main(saved)
finally:  # the raw client files never outlive the script run (the run holds anonymised data)
    ingest_ui.discard_uploads(saved)
