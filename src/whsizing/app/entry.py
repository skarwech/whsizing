"""First call of every page (F10b): `state.setup` behind a guard on the `?run=` query parameter.

The URL is typed by whoever can reach the server, so it may only name a run folder directly under
the app's runs root (`WHSIZING_RUNS`, default `runs/`): a bare folder name, never a path. Anything
else is dropped before `state.restore` sees it (R8c; `state.resolve_run` itself still accepts a
path, it is for the app's own callers). The typed-path field of the upload page is the one place
that reads an arbitrary local path, and says it is for local use.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from whsizing.app import demo, state
from whsizing.report import Lang

PARAM = "run"


def safe_run_name(root: Path, ref: str | None) -> str | None:
    """`ref` when it is the bare name of a run folder that lives directly under `root` (a symlink
    to a run elsewhere is not under it), else None; a name the filesystem refuses is no run. In
    the public demo only the demo's own runs count."""
    if not ref or ref in (".", "..") or Path(ref).name != ref:
        return None
    folder = root / ref
    try:  # a name over the filesystem limit (255 bytes) makes the stat raise ENAMETOOLONG
        if not (state.is_run(folder) and folder.resolve().parent == root.resolve()):
            return None
        return ref if not demo.demo_only() or demo.is_demo_run(folder) else None
    except OSError:
        return None


def setup(title_key: str) -> tuple[Lang, Path | None]:
    """`state.setup` after dropping a `?run=` that is not a run folder of the runs root. Not on an
    address the full app refuses to serve: the page then answers with an error, whatever the URL
    names, and keeping or dropping the parameter would tell a caller which runs exist."""
    ref = st.query_params.get(PARAM)
    if (
        ref is not None
        and not state.exposed_without_auth()
        and safe_run_name(state.runs_root(), ref) is None
    ):
        del st.query_params[PARAM]
    return state.setup(title_key)
