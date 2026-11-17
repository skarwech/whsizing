"""Records logged before the run folder exists (the load stage, run_id `setup`) must reach
logs/run.log too: `LogBuffer` keeps them from its creation, `replay` writes them to the run's log
file once `configure_logging` has opened it, with the run's id (§2.8: every record carries it).
They went to the console when they were logged, so `replay` does not print them again."""

from __future__ import annotations

import logging
from typing import Any

from whsizing.logging import LOGGER_NAME


class LogBuffer(logging.Handler):
    """A handler of the `whsizing` logger that only keeps the records it sees."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []
        logging.getLogger(LOGGER_NAME).addHandler(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def detach(self) -> None:
        """Stop collecting (also when the load stage failed: no handler is left on the logger)."""
        logging.getLogger(LOGGER_NAME).removeHandler(self)

    def replay(self, run_id: str) -> None:
        """Write the kept records, in order and with their own timestamps, as `run_id`'s to the log
        file handler of the `whsizing` logger (the one `configure_logging(run_id, file)` added)."""
        logger = logging.getLogger(LOGGER_NAME)
        files = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        for record in self.records:
            event: Any = record.msg  # structlog's event dict, else the text of a foreign logger
            if isinstance(event, dict):
                record = logging.makeLogRecord(
                    {**record.__dict__, "msg": {**event, "run_id": run_id}}
                )
            for handler in files:
                handler.handle(record)
