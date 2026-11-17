"""Demo data and demo mode of the Streamlit app (no Streamlit import here).

`WHSIZING_DEMO_ONLY=1` (set by `streamlit_app.py`, the entry point of the public demo on
Streamlit Community Cloud) turns the app into a demo on synthetic data: no upload, no typed server
path, a random salt per server process, and a visitor only sees the runs of the demo.

The demo site is fictitious (`data/synth/profiles/demo.yaml`: about 370,000 order lines over 18
months). Its CSV files are generated on the first visit, then ingested and sized by the same CLI
commands the terminal runs (`whsizing.app.calls`), so the demo exercises the real pipeline:

- `shared_run`: the finished example, built once per server process and opened by every visitor
  (sized once and never sized again; what a visitor's export on page 6 adds to it is the report
  files and the timings of the manifest, see `shared_run`);
- `load_demo`: a run of the visitor's own with the four datasets ingested and the demo basis and
  scenarios saved as drafts, to walk through pages 2 to 6 step by step.

A demo run carries `ui/demo.json`; only those are opened from `?run=` in the public demo, and
only there are the old ones pruned (the full app keeps every run it is given). The salt: the
public demo gets a random one per server process; the full app never sets one for the user, whose
own salt (page 1, `$WHSIZING_SALT`) must stay what decides it.
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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from whsizing.app import calls
from whsizing.app.calls import BUSY_CODE, CliError, call, exclusive
from whsizing.cli.data import ingest_cmd
from whsizing.cli.sizing import compare_cmd, size_cmd
from whsizing.errors import ConfigError
from whsizing.schemas.params import DatasetKind
from whsizing.synth import synthesize

DEMO_ENV = "WHSIZING_DEMO_ONLY"
SALT_ENV = "WHSIZING_SALT"
WORK_ENV = "WHSIZING_DEMO_DIR"  # where the demo keeps its data and runs (default: the temp dir)
PROFILE = Path("data/synth/profiles/demo.yaml")
BASIS = Path("basis/demo_basis.yaml")
SCENARIOS = Path("scenarios/demo_scenarios.yaml")
# the order of the ingest (the SKU master first: the others are checked against it) and the order
# of the dataset selector of page 1
DATASETS: tuple[DatasetKind, ...] = ("sku_master", "order_lines", "inventory", "receipts")
MARKER = Path("ui") / "demo.json"
SEED = 42
RUN_MAX_AGE_S = 3 * 3600  # [P] a visitor's demo run is deleted three hours after it was made
MAX_RUNS = 30  # [P] and above this many demo runs the oldest go first (the shared one stays)

_LOCK = threading.RLock()  # one data generation / shared build at a time


@contextmanager
def _held() -> Iterator[None]:
    """`_LOCK` with the patience of a command (`calls.WAIT_S`): the first visitor's build holds it
    for its whole length, and the ones behind it are told the server is busy instead of waiting
    for as long as that build waits for the commands (the `CliError` is shown like theirs)."""
    if not _LOCK.acquire(timeout=calls.WAIT_S):
        raise CliError(BUSY_CODE, f"the demo has been busy for over {calls.WAIT_S:g} s")
    try:
        yield
    finally:
        _LOCK.release()


_shared: Path | None = (
    None  # ponytail: per server process; a restart rebuilds it (about 10 s on a laptop)
)


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
    """A random salt for this server process when none is set (public demo only, see `load_demo`).
    The data is synthetic, there is nothing to protect, but the ingest refuses to run without a
    salt (C2); a salt the deployer set (secrets, environment) is kept. Under the lock: two first
    visitors must not each plant a different salt, the datasets of one run would not join."""
    with _held():
        if not os.environ.get(SALT_ENV):
            os.environ[SALT_ENV] = secrets.token_hex(16)


def _throwaway_salt() -> Path | None:
    """The salt file of one `load_demo` in the full app when the user has not exported a salt: the
    environment stays unset, so page 1 still asks for the user's own salt (a process-wide random
    one would be used for their real files, and be lost). None: `$WHSIZING_SALT` is used, which
    the public demo has (`ensure_salt`) and a user who exported one keeps."""
    if demo_only() or os.environ.get(SALT_ENV):
        return None
    fd, name = tempfile.mkstemp(prefix="whsizing-demo-salt-")  # 0600, outside any repository
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_hex(16))
    return Path(name)


def ensure_data() -> Path:
    """The folder with the demo CSV files (English headers), generated once per profile content."""
    profile = resource_root() / PROFILE
    key = hashlib.sha256(profile.read_bytes()).hexdigest()[:8]
    out = work_dir() / f"data-{key}-{SEED}"
    done = out / ".complete"
    with _held():  # complete = the marker and the four files (a marker that outlived its files is
        # no marker: the next visit regenerates instead of failing until the process restarts)
        if not (done.is_file() and all((out / "csv_en" / f"{d}.csv").is_file() for d in DATASETS)):
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


def is_shared(run: Path) -> bool:
    """The finished example (of this server process or of an earlier one)."""
    return _meta(run).get("shared") is True


def mark(run: Path, *, shared: bool = False) -> None:
    path = run / MARKER
    path.parent.mkdir(exist_ok=True)
    meta = {"demo": True, "shared": shared, "created": time.time()}
    path.write_text(json.dumps(meta), encoding="utf-8")


def _is_current_shared(run: Path) -> bool:
    return _shared is not None and run.resolve() == _shared.resolve()


def prune(runs: Path, now: float | None = None) -> list[Path]:
    """Delete the demo runs older than `RUN_MAX_AGE_S` and, above `MAX_RUNS`, the oldest ones.
    Never a run without the demo marker, never this process's shared example (the one an earlier
    server process left in the folder ages out like any other)."""
    now = time.time() if now is None else now
    found = sorted(
        (float(_meta(p).get("created", 0.0)), p)
        for p in (runs.iterdir() if runs.is_dir() else [])
        if p.is_dir() and is_demo_run(p) and not _is_current_shared(p)
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
    pages 4 and 5 start from. `CliError` when a command fails (the run is marked from its first
    dataset on, so that a failed build is pruned like any other in the public demo)."""
    if demo_only():  # the full app keeps the user's runs and the user's salt: no pruning, no
        ensure_salt()  # process-wide salt (the public demo has both: visitors share the server)
        prune(runs)
    data = ensure_data()
    root = resource_root()
    salt_file = _throwaway_salt()
    run: Path | None = None
    try:
        for dataset in DATASETS:
            done = call(
                ingest_cmd,
                files=[data / f"{dataset}.csv"],
                dataset=dataset,
                non_interactive=True,
                out_dir=runs,
                run=run,
                salt_file=salt_file,
            )
            run = Path(done.last_line)
            if dataset == DATASETS[0]:
                # `?run=<name>` opens any marked demo run, so the name is the visitor's key to
                # theirs. The stock name is a second and six hex digits that every demo run
                # shares (the site and the seed are public): the folder gets its own name before
                # it is first marked, and is never reachable under the stock one.
                run = run.rename(run.with_name(f"{run.name}-{secrets.token_hex(8)}"))
            mark(run)
    finally:
        if salt_file is not None:
            salt_file.unlink(missing_ok=True)
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
    with exclusive():  # `compare` must not wait behind another visitor's command after `size`
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
    waits about 10 s on a laptop), then every visitor opens the same run. It is sized once and
    never again, but it is not read-only: a visitor's Excel or PDF export on page 6 adds files to
    `report/` and the timings to `manifest.json` (`report_cmd`), which is why the manifest is
    written atomically."""
    global _shared
    with _held():
        run = _shared
        if run is None or not (run / "comparison" / "comparison.json").is_file():
            run = load_demo(runs)
            size_demo(run, catalog)
            mark(run, shared=True)
            _shared = run
        return run
