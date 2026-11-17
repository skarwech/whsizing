"""Demo data and demo mode of the Streamlit app (no Streamlit import here).

`WHSIZING_DEMO_ONLY=1` (set by `streamlit_app.py`, the entry point of the public demo on
Streamlit Community Cloud) turns the app into a demo on synthetic data: no upload, no typed server
path, a random salt per server process, and a visitor only sees the runs of the demo.

The demo site is fictitious (`data/synth/profiles/demo.yaml`: about 370,000 order lines over 18
months). Its CSV files are generated on the first visit, then ingested and sized by the same CLI
commands the terminal runs (`whsizing.app.calls`), so the demo exercises the real pipeline:

- `shared_run`: the finished example, built once per server process and opened by every visitor
  (read-only, a run is immutable once sized);
- `load_demo`: a run of the visitor's own with the four datasets ingested and the demo basis and
  scenarios saved as drafts, to walk through pages 2 to 6 step by step.

A demo run carries `ui/demo.json`; only those are listed, opened from `?run=` or pruned.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from whsizing.app.calls import call
from whsizing.cli.data import ingest_cmd
from whsizing.cli.sizing import compare_cmd, size_cmd
from whsizing.errors import ConfigError
from whsizing.synth import synthesize

DEMO_ENV = "WHSIZING_DEMO_ONLY"
SALT_ENV = "WHSIZING_SALT"
WORK_ENV = "WHSIZING_DEMO_DIR"  # where the demo keeps its data and runs (default: the temp dir)
PROFILE = Path("data/synth/profiles/demo.yaml")
BASIS = Path("basis/demo_basis.yaml")
SCENARIOS = Path("scenarios/demo_scenarios.yaml")
DATASETS = (
    "sku_master",
    "order_lines",
    "inventory",
    "receipts",
)  # the others are checked against it
MARKER = Path("ui") / "demo.json"
SEED = 42
RUN_MAX_AGE_S = 3 * 3600  # [P] a visitor's demo run is deleted three hours after it was made
MAX_RUNS = 30  # [P] and above this many demo runs the oldest go first (the shared one stays)

_LOCK = threading.RLock()  # one data generation / shared build at a time
_shared: Path | None = None  # ponytail: per server process; a restart rebuilds it (about 30 s)


def demo_only() -> bool:
    """True for the public demo (`streamlit_app.py`): synthetic data only, no upload."""
    return os.environ.get(DEMO_ENV) == "1"


def work_dir() -> Path:
    return Path(os.environ.get(WORK_ENV) or Path(tempfile.gettempdir()) / "whsizing-demo")


def resource_root() -> Path:
    """The folder with `data/synth/`, `basis/` and `scenarios/`: the working directory when it has
    them (Community Cloud starts every app from the repository root), else the checkout the
    package sits in (src layout: `src/whsizing/app/demo.py` is three levels below it)."""
    for root in (Path.cwd(), Path(__file__).resolve().parents[3]):
        if all((root / name).is_file() for name in (PROFILE, BASIS, SCENARIOS)):
            return root
    raise ConfigError(
        f"demo: {PROFILE}, {BASIS} and {SCENARIOS} not found: run from the repository root"
    )


def ensure_salt() -> None:
    """A random salt for this server process when none is set. The data is synthetic, there is
    nothing to protect, but the ingest refuses to run without a salt (C2); a salt the deployer
    set (secrets, environment) is kept."""
    if not os.environ.get(SALT_ENV):
        os.environ[SALT_ENV] = secrets.token_hex(16)


def ensure_data() -> Path:
    """The folder with the demo CSV files (English headers), generated once per profile content."""
    profile = resource_root() / PROFILE
    key = hashlib.sha256(profile.read_bytes()).hexdigest()[:8]
    out = work_dir() / f"data-{key}-{SEED}"
    done = out / ".complete"
    with _LOCK:
        if not done.is_file():
            shutil.rmtree(out, ignore_errors=True)
            synthesize(profile, out, seed=SEED)
            done.write_text("ok\n", encoding="utf-8")
    return out / "csv_en"


# ------------------------------------------------------------------------------------ markers
def _meta(run: Path) -> dict[str, Any]:
    try:
        data = json.loads((run / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_demo_run(run: Path) -> bool:
    """A run `load_demo` made: the only runs the demo mode lists, opens or prunes."""
    return _meta(run).get("demo") is True


def mark(run: Path, *, shared: bool = False) -> None:
    path = run / MARKER
    path.parent.mkdir(exist_ok=True)
    meta = {"demo": True, "shared": shared, "created": time.time()}
    path.write_text(json.dumps(meta), encoding="utf-8")


def prune(runs: Path, now: float | None = None) -> list[Path]:
    """Delete the demo runs older than `RUN_MAX_AGE_S` and, above `MAX_RUNS`, the oldest ones.
    Never a run without the demo marker, never the shared example."""
    now = time.time() if now is None else now
    found = sorted(
        (float(_meta(p).get("created", 0.0)), p)
        for p in (runs.iterdir() if runs.is_dir() else [])
        if p.is_dir() and is_demo_run(p) and not _meta(p).get("shared")
    )
    old = [p for created, p in found if now - created > RUN_MAX_AGE_S]
    rest = [p for _, p in found if p not in old]
    excess = rest[: max(0, len(rest) - MAX_RUNS + 1)]  # room for the run about to be made
    for path in (*old, *excess):
        shutil.rmtree(path, ignore_errors=True)
    return [*old, *excess]


# -------------------------------------------------------------------------------------- builds
def load_demo(runs: Path) -> Path:
    """A new run folder with the four demo datasets ingested (the CLI `ingest`, one dataset after
    the other, `sku_master` first) and the demo basis and scenarios saved as the run's drafts, which
    pages 4 and 5 start from. `CliError` when a command fails."""
    ensure_salt()
    data = ensure_data()
    root = resource_root()
    prune(runs)
    run: Path | None = None
    for dataset in DATASETS:
        done = call(
            ingest_cmd,
            files=[data / f"{dataset}.csv"],
            dataset=dataset,
            non_interactive=True,
            out_dir=runs,
            run=run,
        )
        run = Path(done.last_line)
    assert run is not None
    drafts = run / "ui"
    drafts.mkdir(exist_ok=True)
    for name, source in (("basis", BASIS), ("scenarios", SCENARIOS)):
        shutil.copyfile(root / source, drafts / f"{name}.yaml")
    mark(run)
    return run


def size_demo(run: Path, catalog: Path) -> None:
    """The CLI `size` then `compare` (with the sensitivity) on the run's drafts, like page 5."""
    drafts = run / "ui"
    call(
        size_cmd,
        run=run,
        basis=drafts / "basis.yaml",
        scenarios=drafts / "scenarios.yaml",
        catalog=catalog,
    )
    call(compare_cmd, run=run, sensitivity=True)


def forget_shared() -> None:
    """Drop the memory of the shared example (tests; the folder itself is left alone)."""
    global _shared
    with _LOCK:
        _shared = None


def shared_run(runs: Path, catalog: Path) -> Path:
    """The finished example: ingested, sized and compared once per server process (the first visit
    waits about 30 s), then every visitor opens the same immutable run."""
    global _shared
    with _LOCK:
        run = _shared
        if run is None or not (run / "comparison" / "comparison.json").is_file():
            run = load_demo(runs)
            size_demo(run, catalog)
            mark(run, shared=True)
            _shared = run
        return run
