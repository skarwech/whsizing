"""Run the CLI commands in-process, so the app writes the same run folders as `whsizing ...` and
holds no pipeline logic (F10b).

A command is called as a Python function (Typer defaults are the plain defaults). It prints to
stdout / stderr like in a terminal and `handle_errors` turns an error into `typer.Exit(code)`
after writing the message to stderr: both are captured here and come back as `CliError`.

ponytail: `redirect_stdout` is process-wide, fine for the one-user local app; a multi-user
server would run the CLI in a subprocess instead.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

HINTS = ("(traceback in", "(no run folder;")  # what `handle_errors` appends to an exit 1


@dataclass(frozen=True)
class CliResult:
    stdout: str
    stderr: str

    @property
    def last_line(self) -> str:
        """The run folder is the last line a command prints (I78 g)."""
        lines = self.stdout.strip().splitlines()
        return lines[-1] if lines else ""


class CliError(Exception):
    """A command exited non-zero: `code` is its §2.7 exit code, `message` what it wrote."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def call(command: Callable[..., Any], **kwargs: Any) -> CliResult:
    """`command(**kwargs)` with its output captured; `CliError` on a non-zero exit."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            command(**kwargs)
    except typer.Exit as e:
        if e.exit_code:
            raise CliError(e.exit_code, _message(err.getvalue())) from e
    return CliResult(out.getvalue(), err.getvalue())


def _message(stderr: str) -> str:
    """What the command failed with: from its `error: ` line on (the log lines it wrote before
    are noise here), without the `error: ` prefix and the traceback hint lines (`(traceback in
    ...)`, `(no run folder; repeat with --debug ...)`: advice for a terminal)."""
    lines = [ln for ln in stderr.strip().splitlines() if not ln.startswith(HINTS)]
    start = next((i for i, ln in enumerate(lines) if ln.startswith("error: ")), 0)
    text = "\n".join(lines[start:]).strip()
    return text.removeprefix("error: ") or "failed (no message)"


def printed_paths(result: CliResult, suffixes: tuple[str, ...]) -> list[Path]:
    """Files a command printed, one per line, with one of `suffixes` (the report command)."""
    return [Path(ln) for ln in result.stdout.splitlines() if ln.strip().endswith(suffixes)]
