"""F0 walking skeleton: T0.5 mock result → Jinja2 → WeasyPrint one-page PDF."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader
from tests.fixtures import mock_result

from whsizing.report.pdf import render_stub_pdf


@pytest.mark.pdf
def test_T0_5_mock_result_renders_one_page_pdf(tmp_path: Path) -> None:
    result = mock_result()
    out = render_stub_pdf(result, tmp_path / "report" / "stub.pdf")
    reader = PdfReader(out)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "S2" in text and "AS/RS cube" in text
    assert "Indicative study" in text
    assert "ports" in text and "13.0" in text  # equipment typ value rendered


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker not installed")
def test_T0_5_docker_image_renders_one_page_pdf(tmp_path: Path) -> None:  # pragma: no cover
    root = Path(__file__).resolve().parents[2]
    subprocess.run(["docker", "build", "-t", "whsizing:test", "."], cwd=root, check=True)
    code = (
        "from pathlib import Path; from tests.fixtures import mock_result;"
        "from whsizing.report.pdf import render_stub_pdf;"
        "render_stub_pdf(mock_result(), Path('/out/stub.pdf'))"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{tmp_path}:/out",
            "--entrypoint",
            "python",
            "whsizing:test",
            "-c",
            code,
        ],
        check=True,
    )
    assert len(PdfReader(tmp_path / "stub.pdf").pages) == 1
