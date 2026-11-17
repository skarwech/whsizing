"""Shared pytest setup. Tests marked `pdf` are skipped, with the reason, when WeasyPrint
cannot load Pango; they never pass silently."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

if sys.platform == "darwin" and Path("/opt/homebrew/lib").is_dir():
    # Homebrew Pango fallback (see justfile / README); harmless when already found.
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

try:
    import weasyprint  # noqa: F401

    WEASYPRINT_ERROR: str | None = None
except (ImportError, OSError) as e:  # OSError: Pango/GObject shared library not found
    WEASYPRINT_ERROR = f"WeasyPrint/Pango unavailable: {e}. On macOS: brew install pango"


@pytest.fixture(autouse=True)
def _app_may_listen_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """The full Streamlit app refuses to start on an address the network can reach (it has no
    authentication, `state.exposed_without_auth`); AppTest has no server address at all, so the
    tests that run its pages say they vouch for it. The guard's own tests remove this."""
    monkeypatch.setenv("WHSIZING_ALLOW_REMOTE", "1")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if WEASYPRINT_ERROR is None:
        return
    skip = pytest.mark.skip(reason=WEASYPRINT_ERROR)
    for item in items:
        if "pdf" in item.keywords:
            item.add_marker(skip)
