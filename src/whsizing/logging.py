"""structlog setup (§2.8): JSON lines to a file plus a console renderer.

Every record carries run_id, stage and scenario. `stage_timer` logs `duration_s` per stage and
collects the timings that go into `RunManifest.timings` (C5 budget).
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog

LOGGER_NAME = "whsizing"
_timings: dict[str, float] = {}


def configure_logging(run_id: str, log_file: Path | None = None, level: int = logging.INFO) -> None:
    """(Re)configure logging for one run and reset the collected stage timings."""
    _timings.clear()
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    logger = logging.getLogger(LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger.setLevel(level)
    logger.propagate = False
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(_formatter(structlog.dev.ConsoleRenderer(colors=False), shared))
    logger.addHandler(console)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(_formatter(structlog.processors.JSONRenderer(), shared))
        logger.addHandler(fh)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(run_id=run_id, stage=None, scenario=None)


def _formatter(
    renderer: structlog.typing.Processor, shared: list[structlog.typing.Processor]
) -> structlog.stdlib.ProcessorFormatter:
    return structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared,
    )


def get_logger(name: str = LOGGER_NAME) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)


@contextmanager
def stage_timer(stage: str) -> Iterator[None]:
    """Bind `stage`, log its duration_s at the end and add it to the run's timings."""
    with structlog.contextvars.bound_contextvars(stage=stage):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - t0
            _timings[stage] = _timings.get(stage, 0.0) + duration
            get_logger().info("stage_done", duration_s=round(duration, 6))


def timings() -> dict[str, float]:
    """Stage → cumulated duration_s since the last configure_logging()."""
    return dict(_timings)
