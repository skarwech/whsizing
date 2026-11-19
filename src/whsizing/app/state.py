"""Session state and run discovery of the Streamlit wrapper (F10b).

`st.session_state` keys: `run_dir` (the run folder, a str), `mapping` (dataset -> mapping dict),
`basis` (design basis values) and `scenarios` (scenarios.yaml content), plus `lang`. The run
folder is the persistent state: a browser refresh starts an empty session and `restore` rebuilds
the keys from `?run=<folder>` (set on every page) or the newest run folder. Drafts the pages write
before `size` live in `<run>/ui/`; the run's own `inputs/` copies win once the run is sized.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, Literal, cast

import streamlit as st
import yaml

from whsizing.app import demo, demo_limits
from whsizing.app.calls import BUSY_CODE, CliError
from whsizing.app.strings import tr
from whsizing.errors import WhsizingError
from whsizing.report import LANGS, Lang, t

RUN, MAPPING, BASIS, SCENARIOS, LANG = "run_dir", "mapping", "basis", "scenarios", "lang"
RESTORED = "_restored_run"  # the run whose files filled the other keys
NO_RUN = "_no_run"  # the user asked for a new run: no fallback to the newest one
RUNS_ENV, CATALOG_ENV, LANG_ENV = "WHSIZING_RUNS", "WHSIZING_CATALOG", "WHSIZING_LANG"
ALLOW_REMOTE_ENV = "WHSIZING_ALLOW_REMOTE"  # "1": the deployer vouches for an authenticating proxy
LOOPBACK = ("127.0.0.1", "localhost", "::1")
UI_DIR = "ui"
Stage = Literal["empty", "ingested", "profiled", "sized", "compared"]
STAGES: tuple[Stage, ...] = ("empty", "ingested", "profiled", "sized", "compared")


def runs_root() -> Path:
    return Path(os.environ.get(RUNS_ENV, "runs"))


def catalog_dir() -> Path:
    return Path(os.environ.get(CATALOG_ENV, "catalog"))


def browser_lang() -> Lang:
    """French for a French browser (its language tag starts with `fr`: fr, fr-FR, fr-CA), English
    otherwise (the public demo assumes no language). `st.context.locale` is None outside a
    browser session (tests, bare mode); a Streamlit without it (before 1.45) gives English."""
    locale = getattr(st.context, "locale", None) or ""
    return "fr" if re.split(r"[-_]", locale.lower())[0] == "fr" else "en"


def default_lang() -> Lang:
    """`WHSIZING_LANG` when it names a language, else the browser's (public demo), else French."""
    value = os.environ.get(LANG_ENV)
    if value in LANGS:
        return cast(Lang, value)
    return browser_lang() if demo.demo_only() else "fr"


def exposed_without_auth() -> bool:
    """True when the full app (uploads, a typed server path, every run on disk) is served on an
    address the network can reach: it has no authentication. The demo (`streamlit_app.py`, synthetic
    data, nothing to read) and `WHSIZING_ALLOW_REMOTE=1` (an authenticating proxy in front) are
    exempt. `just app` passes `--server.address 127.0.0.1`."""
    if demo.demo_only() or os.environ.get(ALLOW_REMOTE_ENV) == "1":
        return False
    return str(st.get_option("server.address") or "") not in LOOPBACK


# ----------------------------------------------------------------------------- run discovery
# `logs/FAILED`: the runner (scenarios/runner.py FAILED_FILE, a test keeps them equal) writes it
# when a run-all fails or is killed; the folder is not a run to list or open.
FAILED_FILE = Path("logs") / "FAILED"


def is_run(path: Path) -> bool:
    """A folder `ingest` or `run-all` made (§2.4: canonical/ and dq/ exist) that did not fail."""
    return (
        (path / "canonical").is_dir()
        and (path / "dq").is_dir()
        and not (path / FAILED_FILE).exists()
    )


def list_runs(root: Path) -> list[Path]:
    """Run folders under `root`, newest first (the name starts with the UTC timestamp)."""
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and is_run(p)), reverse=True)


def resolve_run(root: Path, ref: str | None) -> Path | None:
    """`ref` (a folder name under `root`, or a path) as a run folder, None when it is not one."""
    if not ref:
        return None
    for candidate in (Path(ref), root / ref):
        if candidate.is_dir() and is_run(candidate):
            return candidate.resolve()
    return None


def stage(run: Path) -> Stage:
    """How far the run went, from the files it holds."""
    for name, rel in (
        ("compared", "comparison/comparison.json"),
        ("sized", "design/design_day.json"),
        ("profiled", "profile/demand_profile.json"),
        ("ingested", "canonical/order_lines.parquet"),
    ):
        if (run / rel).is_file():
            return name  # type: ignore[return-value]
    return "empty"


def reached(run: Path, wanted: Stage) -> bool:
    return STAGES.index(stage(run)) >= STAGES.index(wanted)


PROFILE_CFG = Path("inputs") / "profile_cfg.yaml"  # `profile --cfg` saves it (cli/_staged.py)
PROFILED_WITH = Path(UI_DIR) / "profile_cfg.digest"  # the cfg page 3 profiled with


def profile_cfg_file(run: Path) -> Path | None:
    """The profile configuration the run holds (`--cfg` of an earlier `profile`), None for the
    defaults: page 3 profiles with it, as `size` will."""
    path = run / PROFILE_CFG
    return path if path.is_file() else None


def _cfg_digest(run: Path) -> str:
    path = run / PROFILE_CFG
    return hashlib.sha256(path.read_bytes() if path.is_file() else b"").hexdigest()[:16]


def mark_profiled(run: Path) -> None:
    """Remember which profile configuration the profile of `run` was made with (the profile file
    does not say)."""
    mark = run / PROFILED_WITH
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(_cfg_digest(run), encoding="utf-8")


def profile_stale(run: Path) -> bool:
    """True when the demand profile of a profiled run (not sized yet: a sized run is immutable and
    `size` profiled its own inputs) was not made from what the run holds now: other canonical
    tables (the profile's own `dataset_hash` against theirs) or another profile configuration (the
    digest `mark_profiled` saved; a profile made by the CLI has none and counts as current). A
    profile file that cannot be read is not stale: page 3 reports it, a re-profile would hide it.
    Tables that cannot be read (damaged, removed) are stale: the re-profile page 3 then runs fails
    with a clear message (`CliError`, shown by `st.error`) instead of a traceback from here.
    Nothing here looks at file times: `profile` writes `canonical/daily_series.parquet` after the
    profile file."""
    if stage(run) != "profiled":
        return False
    try:
        made_from = json.loads((run / "profile" / "demand_profile.json").read_text("utf-8"))[
            "dataset_hash"
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    # ponytail: the tables' hash is computed once per server process and content (st.cache_data);
    # store it in the run folder when a restart of a big run's page 3 must not wait for it
    from whsizing.app import loaders  # heavy imports: only the pages that profile need them

    try:
        current = loaders.tables_hash(str(run), loaders.canonical_digest(run))
    except WhsizingError:
        return True
    if made_from != current:
        return True
    mark = run / PROFILED_WITH
    return mark.is_file() and mark.read_text("utf-8") != _cfg_digest(run)


def run_digest(run: Path) -> str:
    """sha256 of what the results pages read, the key of their caches: a run is immutable, but
    `compare` rewrites comparison/."""
    h = hashlib.sha256()
    for rel in ("manifest.json", "comparison/comparison.json", "comparison/sensitivity.json"):
        path = run / rel
        h.update(path.read_bytes() if path.is_file() else b"-")
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------------- run state
def read_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def draft_path(run: Path, name: str) -> Path:
    return run / UI_DIR / f"{name}.yaml"


def saved_path(run: Path, name: str) -> Path | None:
    """The basis or scenarios file of the run: its `inputs/` copy once sized, else the draft."""
    for path in (run / "inputs" / f"{name}.yaml", draft_path(run, name)):
        if path.is_file():
            return path
    return None


def write_draft(run: Path, name: str, content: Mapping[str, Any]) -> Path:
    path = draft_path(run, name)
    path.parent.mkdir(exist_ok=True)
    path.write_text(yaml.safe_dump(dict(content), sort_keys=False, allow_unicode=True), "utf-8")
    return path


def run_state(run: Path) -> dict[str, Any]:
    """What the session keys hold for `run`: mappings (inputs/mapping), basis and scenarios."""
    folder = run / "inputs" / "mapping"
    mapping = (
        {p.stem: read_yaml(p) for p in sorted(folder.glob("*.yaml"))} if folder.is_dir() else {}
    )
    return {
        MAPPING: {ds: m for ds, m in mapping.items() if m is not None},
        BASIS: read_yaml(p) if (p := saved_path(run, "basis")) else None,
        SCENARIOS: read_yaml(p) if (p := saved_path(run, "scenarios")) else None,
    }


def restore(
    session: MutableMapping[str, Any],
    query: Mapping[str, str],
    root: Path,
    *,
    isolated: bool = False,
) -> Path | None:
    """Make `session` hold a run folder and its state: the session's own run, else `?run=`, else
    the newest run. The other keys are rebuilt from the folder when the run changed. `isolated`
    (the public demo, where visitors share the server): only demo runs, and never the newest one,
    which belongs to another visitor."""
    run = None
    if not session.get(NO_RUN):
        for ref in (session.get(RUN), query.get("run")):
            found = resolve_run(root, ref)
            if found is not None and (not isolated or demo.is_demo_run(found)):
                run = found
                break
        if run is None and not isolated:
            run = next(iter(list_runs(root)), None)
    if run is None:
        session.pop(RUN, None)
        return None
    session[RUN] = str(run)
    if session.get(RESTORED) != str(run):
        session.update(run_state(run))
        session[RESTORED] = str(run)
    return run


def open_run(run: Path) -> None:
    """Switch the session to `run` (the next `init` rebuilds its state)."""
    st.session_state[RUN] = str(run)
    st.session_state.pop(RESTORED, None)
    st.session_state.pop(NO_RUN, None)
    st.query_params["run"] = Path(run).name


def close_run() -> None:
    """Forget the run: pages 1 to 6 start from nothing (the next ingest makes a new folder)."""
    for key in (RUN, RESTORED, MAPPING, BASIS, SCENARIOS):
        st.session_state.pop(key, None)
    st.session_state[NO_RUN] = True
    st.query_params.pop("run", None)


# ------------------------------------------------------------------------------------ chrome
def lang() -> Lang:
    value = st.session_state.get(LANG, default_lang())
    return value if value in LANGS else default_lang()


def init() -> Path | None:
    """Restore the session from the URL or the disk; keep `?run=` pointing at the run."""
    # Assign, not `setdefault`: after a page switch the key still holds the language of the
    # previous page's radio, as stale state that a new radio ignores (it starts at "fr"); only a
    # value assigned in this run is honoured (Streamlit's "re-assign the key on every page").
    st.session_state[LANG] = st.session_state.get(LANG, default_lang())
    run = restore(
        cast(MutableMapping[str, Any], st.session_state),
        st.query_params,
        runs_root(),
        isolated=demo.demo_only(),
    )
    if run is not None and st.query_params.get("run") != run.name:
        st.query_params["run"] = run.name
    return run


def setup(title_key: str) -> tuple[Lang, Path | None]:
    """First call of every page: page config, state restore, language switch, run summary."""
    st.set_page_config(page_title="whsizing", layout="wide")
    if exposed_without_auth():
        st.error(tr("guard.exposed", default_lang()))
        st.stop()
    run = init()
    st.sidebar.radio("Langue / Language", LANGS, key=LANG, horizontal=True)
    lg = lang()
    if demo.demo_only():
        st.sidebar.info(tr("demo.banner", lg))
    if run is not None:
        st.sidebar.caption(f"{tr('run', lg)}: {run.name} ({stage(run)})")
    st.title(tr(title_key, lg))
    return lg, run


def error(text: str) -> None:
    """`st.error` for a message that comes from an exception or a command: in the public demo
    without the folders of the server."""
    st.error(demo_limits.scrub(text))


def cli_error(failed: CliError, lg: Lang) -> None:
    """The message of a command that exited non-zero (a busy server in the visitor's language, and
    in the public demo a run another tab sized meanwhile: the CLI's advice does not apply there)."""
    if failed.code == BUSY_CODE:
        st.warning(tr("demo.busy", lg))
    elif demo.demo_only() and "already sized" in failed.message:
        st.info(tr("demo.sealed", lg))
    else:
        error(f"exit {failed.code}: {failed.message}")


def shown_path(run: Path, path: Path) -> str:
    """A draft's path as the page tells it: in the public demo relative to the run (the folders of
    the server stay out of the messages), else the path itself."""
    return str(path.relative_to(run)) if demo.demo_only() else str(path)


def banner(lg: Lang) -> None:
    """The 'indicative study' banner of every results page (i18n of the report package)."""
    st.warning(t("banner.indicative", lg))


def require_run(lg: Lang, run: Path | None, wanted: Stage = "ingested") -> Path:
    """The run, or a friendly page: no run yet, or the run has not reached `wanted`."""
    if run is None:
        st.info(tr("demo.no_run" if demo.demo_only() else "no_run", lg))
        st.stop()
    if not reached(run, wanted):
        unfinished = wanted == "compared" and reached(run, "sized")  # sizing or comparison failed
        st.info(
            tr(
                "run.unfinished" if unfinished else "stage_missing",
                lg,
                stage=wanted,
                have=stage(run),
            )
        )
        st.stop()
    return run
