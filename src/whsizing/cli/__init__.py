"""Typer CLI (F10): `whsizing synth | ingest | profile | basis init | size | compare | report |
run-all | calibrate | rerun | validate-catalog`. Exit codes follow §2.7 (`handle_errors`)."""

from __future__ import annotations

from typing import Annotated

import typer

from whsizing import __version__
from whsizing.cli import data, sizing  # noqa: F401  (importing registers the commands)
from whsizing.cli._core import DEBUG, app, basis_app, handle_errors

__all__ = ["app", "basis_app", "handle_errors"]


def _version(value: bool) -> None:
    if value:
        typer.echo(f"whsizing {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Print the version."),
    ] = None,
    debug: Annotated[
        bool, typer.Option("--debug", envvar="WHSIZING_DEBUG", help="Print tracebacks on stderr.")
    ] = False,
) -> None:
    """Warehouse sizing POC: ingest → profile → size → finance → report."""
    DEBUG.set(debug)
