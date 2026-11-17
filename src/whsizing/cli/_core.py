"""Shared CLI plumbing: the Typer apps, the §2.7 error mapping, run folders and console output.

`handle_errors` is the one top-level handler: a WhsizingError becomes its `exit_code`, anything
else exit 1; the message goes to stderr, the traceback to `logs/run.log` of the run (exit 1 only)
or to stderr with the global `--debug`.
"""

from __future__ import annotations

import functools
import json
import logging
import signal
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any

import click
import structlog
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from whsizing.errors import ConfigError, WhsizingError
from whsizing.logging import LOGGER_NAME, configure_logging, timings
from whsizing.scenarios.manifest import read_manifest, write_manifest
from whsizing.schemas import Comparison, Project, Range
from whsizing.schemas.project import ProjectOptions

NOTICE = (
    "INDICATIVE STUDY: lo/typ/hi estimates from a proof-of-concept model on the data as "
    "ingested. Not a quotation, a commitment or a validated design."
)
DEBUG: ContextVar[bool] = ContextVar("whsizing_debug", default=False)  # global --debug
SIZED_FILE = Path("design") / "design_day.json"

# No square brackets in a help string: Rich takes "[default]" for a style tag and drops it.
app = typer.Typer(name="whsizing", help="Warehouse sizing POC.", no_args_is_help=True)
basis_app = typer.Typer(help="Design basis helpers.", no_args_is_help=True)
app.add_typer(basis_app, name="basis")

_PASS_THROUGH = (click.ClickException, click.exceptions.Exit, click.Abort)


class Terminated(WhsizingError):
    """SIGTERM (a `kill`, a container stop) turned into an ordinary failure: the runner marks the
    run FAILED and logs `run_failed` like for any other exception, then the command exits with
    128 + the signal number (143), the shell convention."""

    def __init__(self, signum: int) -> None:
        super().__init__(f"terminated by signal {signum} ({signal.Signals(signum).name})")
        self.exit_code = 128 + signum


def _on_sigterm(signum: int, frame: FrameType | None) -> None:
    del frame
    raise Terminated(signum)


def _install_sigterm() -> Callable[[], None]:
    """Route SIGTERM through `Terminated`; returns what restores the previous handler. Only the
    main thread may set a handler (the Streamlit app runs commands in a script thread): there
    the default stays."""
    try:
        previous = signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:
        return lambda: None

    def restore() -> None:
        signal.signal(signal.SIGTERM, signal.SIG_DFL if previous is None else previous)

    return restore


class _NoConsoleTraceback(logging.Filter):
    """On a console handler: drop the `traceback` field of a record (the runner logs it on
    `run_failed`; logs/run.log keeps it, stderr shows the short message only). Returns a copy,
    so the file handler still gets the whole record (Python 3.12 handler filters)."""

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        if not isinstance(record.msg, dict) or "traceback" not in record.msg:
            return True
        copy = logging.makeLogRecord(record.__dict__)
        copy.msg = {k: v for k, v in record.msg.items() if k != "traceback"}
        return copy


class _QuietConsole(logging.Filter):
    """On the logger, which runs before its handlers: put `_NoConsoleTraceback` on the console
    handler (re-made by every `configure_logging`) unless `--debug`."""

    def __init__(self) -> None:
        super().__init__()
        self.console_filter = _NoConsoleTraceback()

    def filter(self, record: logging.LogRecord) -> bool:
        if not DEBUG.get():
            for h in logging.getLogger(LOGGER_NAME).handlers:
                if not isinstance(h, logging.FileHandler) and self.console_filter not in h.filters:
                    h.addFilter(self.console_filter)
        return True


_QUIET = _QuietConsole()


def handle_errors[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Map WhsizingError subclasses to their §2.7 exit code, any other exception to exit 1."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        configure_logging("cli")  # console only; commands with a run folder reconfigure
        logging.getLogger(LOGGER_NAME).addFilter(_QUIET)
        restore_sigterm = _install_sigterm()
        try:
            return fn(*args, **kwargs)
        except _PASS_THROUGH:
            raise  # Typer usage errors (exit 2), typer.Exit, Ctrl-C
        except WhsizingError as e:
            raise _fail(e, e.exit_code) from e
        except Exception as e:  # §2.7: unexpected failure, exit 1
            raise _fail(e, 1) from e
        finally:
            restore_sigterm()
            DEBUG.set(False)  # `--debug` is for one command
            _close_logging()

    return wrapper


def _fail(e: Exception, code: int) -> typer.Exit:
    unexpected = not isinstance(e, WhsizingError)
    typer.echo(f"error: {f'unexpected {type(e).__name__}: {e}' if unexpected else e}", err=True)
    tb = "".join(traceback.format_exception(e))
    if DEBUG.get():
        typer.echo(tb, err=True)
    elif code == 1:
        log_file = _log_file()
        if log_file is None:
            typer.echo("(no run folder; repeat with --debug for the traceback)", err=True)
        else:
            _append_failure(log_file, e, tb)
            typer.echo(f"(traceback in {log_file})", err=True)
    return typer.Exit(code=code)


def _log_file() -> Path | None:
    for h in logging.getLogger(LOGGER_NAME).handlers:
        if isinstance(h, logging.FileHandler):
            return Path(h.baseFilename)
    return None


def _append_failure(log_file: Path, e: Exception, tb: str) -> None:
    """A JSON line like the run.log records, written directly: the console must not show it."""
    line = {
        "event": "command_failed",
        "level": "error",
        "timestamp": datetime.now(UTC).isoformat(),
        "run_id": structlog.contextvars.get_contextvars().get("run_id"),
        "error_type": type(e).__name__,
        "error": str(e),
        "traceback": tb,
    }
    with log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def _close_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.removeFilter(_QUIET)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


# ------------------------------------------------------------------------------- run folders
def open_run(run: Path) -> Path:
    """The run folder `run` (it must hold canonical/order_lines.parquet), logging to its run.log."""
    run = Path(run)
    if not (run / "canonical" / "order_lines.parquet").is_file():
        raise ConfigError(
            f"{run}: not a run folder with ingested order lines "
            "(no canonical/order_lines.parquet); `whsizing ingest` makes one"
        )
    run = run.resolve()
    configure_logging(run.name, run / "logs" / "run.log")
    return run


def require_unsized(run: Path) -> None:
    """Runs are immutable (§2.4): the stages that write design/ refuse a run that has one."""
    if (run / SIZED_FILE).exists():
        raise ConfigError(
            f"{run}: already sized and runs are immutable; `whsizing rerun` makes a new run "
            "folder, or ingest into a new one"
        )


def require_sized(run: Path) -> None:
    """The stages that read design/ and scenarios/ need `whsizing size` (or run-all) first."""
    if not (run / SIZED_FILE).exists():
        raise ConfigError(f"{run}: not sized yet; run `whsizing size` first")


def record_timings(run: Path, earlier: dict[str, float] | None = None) -> None:
    """Merge the stage timings of this command into manifest.json (C5). `earlier`: stages that
    ran in another command (see `logged_seconds`)."""
    manifest = read_manifest(run)
    merged = {**manifest.timings, **(earlier or {}), **timings()}
    write_manifest(manifest.model_copy(update={"timings": merged}), run)


def logged_seconds(run: Path, stage: str) -> float | None:
    """Total duration_s of the `stage_done` records of `stage` in logs/run.log (None: no record):
    a command of an earlier process (`ingest`) timed itself there, the manifest did not exist."""
    total, found = 0.0, False
    for line in (run / "logs" / "run.log").read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:  # not a JSON record: not ours to judge
            continue
        if isinstance(rec, dict) and rec.get("event") == "stage_done" and rec.get("stage") == stage:
            total, found = total + float(rec["duration_s"]), True
    return total if found else None


def with_options(project: Project, **overrides: Any) -> Project:
    """`project` with some `options` replaced, validated (a bad --delta: ConfigError, exit 2)."""
    try:
        options = ProjectOptions.model_validate({**project.options.model_dump(), **overrides})
    except ValidationError as e:
        raise ConfigError(f"invalid option: {e.errors()[0]['msg']} ({overrides})") from e
    return project.model_copy(update={"options": options})


# ------------------------------------------------------------------------------------ output
def _range(r: Range | None, scale: float, worlds: str, nd: int = 0) -> str:
    """`typ` or `typ [lo-hi]` with `nd` decimals (FTE needs one: small sites are 0.7-1.4 FTE)."""
    if r is None:
        return "-"
    typ = f"{r.typ / scale:,.{nd}f}"
    return typ if worlds == "typ" else f"{typ} [{r.lo / scale:,.{nd}f}-{r.hi / scale:,.{nd}f}]"


def print_comparison(cmp: Comparison, worlds: str = "all") -> None:
    """The comparison table (typ only with worlds='typ', typ [lo-hi] otherwise) and its note."""
    table = Table(title=f"Comparison, baseline: {cmp.baseline_id}")
    for col in ("Scenario", "Family", "Fit"):
        table.add_column(col)
    for col in ("Area m2", "FTE day", "Capex k€", "TCO k€", "NPV k€", "Payback y"):
        table.add_column(col, justify="right")
    for r in cmp.rows:
        if r.status == "not_computed":
            table.add_row(r.scenario_id, r.family, "not computed", r.status_reason or "", *[""] * 4)
            continue
        payback = "-" if r.payback_years is None else f"{r.payback_years:.1f}"
        table.add_row(
            r.scenario_id,
            r.family,
            "yes" if r.fit else "NO",
            _range(r.total_area_m2, 1, worlds),
            _range(r.fte_design_day, 1, worlds, 1),
            _range(r.capex, 1e3, worlds),
            _range(r.tco, 1e3, worlds),
            _range(r.npv_vs_baseline, 1e3, worlds),
            payback,
        )
    console = Console()
    console.width = max(console.width, 130)
    console.print(table)
    typer.echo(cmp.confidence_note)


def print_notice() -> None:
    typer.echo(NOTICE)
