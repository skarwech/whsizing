"""F0 CLI skeleton: T0.2 version and the §2.7 exit-code mapping of `handle_errors`.

The placeholder commands the skeleton had are replaced by F10 (tests/unit/test_f10_cli.py)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import whsizing
from whsizing.cli import app, handle_errors
from whsizing.errors import (
    ConfigError,
    DataQualityError,
    MappingError,
    ReportIntegrityError,
    SizingInfeasibleError,
    WhsizingError,
)

ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def test_T0_2_version_cli_runner() -> None:
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert res.output.strip() == f"whsizing {whsizing.__version__}"
    assert whsizing.__version__ == "0.1.0"


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not on PATH")
def test_T0_2_version_console_script() -> None:
    out = subprocess.run(
        ["uv", "run", "whsizing", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == f"whsizing {whsizing.__version__}"


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (WhsizingError, 1),
        (ConfigError, 2),
        (MappingError, 2),
        (DataQualityError, 3),
        (SizingInfeasibleError, 4),
        (ReportIntegrityError, 5),
    ],
)
def test_handle_errors_maps_exit_codes(exc: type[WhsizingError], code: int) -> None:
    assert exc.exit_code == code
    probe = typer.Typer()

    @probe.command()
    @handle_errors
    def boom(name: str) -> None:
        raise exc(f"{name} failed [P]")

    res = runner.invoke(probe, ["x"])
    assert res.exit_code == code
    assert "error: x failed [P]" in res.output
