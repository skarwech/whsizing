"""The run manifest is replaced atomically (`write_manifest`).

A command rewrites `manifest.json` (the stage timings) while another thread or process may read it:
on the Streamlit demo every visitor reads the shared example, and any visitor's Excel or PDF export
rewrites its manifest. A reader must see the old file or the new one, never a half-written one.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from tests.fixtures import mock_manifest

from whsizing.errors import ConfigError
from whsizing.scenarios import manifest as mf


def test_the_old_manifest_stays_whole_until_the_new_one_replaces_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = mock_manifest()
    mf.write_manifest(old, tmp_path)
    seen: list[str] = []
    real_write_text = Path.write_text

    def spying_write_text(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.parent == tmp_path and self.name != "manifest.json":  # the new content, elsewhere
            seen.append((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        return real_write_text(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", spying_write_text)
    new = old.model_copy(update={"timings": {"report": 9.0}})
    mf.write_manifest(new, tmp_path)
    monkeypatch.undo()

    assert len(seen) == 1  # the new content was written to a file of its own...
    assert mf.RunManifest.model_validate_json(seen[0]) == old  # ...while the old one was whole
    assert mf.read_manifest(tmp_path) == new
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]  # no temporary file left


def test_a_failed_write_leaves_the_old_manifest_and_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = mock_manifest()
    mf.write_manifest(old, tmp_path)

    def disk_full(source: object, destination: object) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(mf.os, "replace", disk_full)
    with pytest.raises(OSError, match="No space left"):  # the error is not swallowed
        mf.write_manifest(old.model_copy(update={"timings": {"report": 9.0}}), tmp_path)
    monkeypatch.undo()

    assert mf.read_manifest(tmp_path) == old
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_a_reader_polling_during_many_rewrites_never_fails(tmp_path: Path) -> None:
    manifest = mock_manifest()
    mf.write_manifest(manifest, tmp_path)
    stop = threading.Event()
    failures: list[ConfigError] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                mf.read_manifest(tmp_path)
            except ConfigError as error:  # unreadable or invalid: what a half-written file gives
                failures.append(error)
                return

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        for i in range(300):
            mf.write_manifest(
                manifest.model_copy(update={"timings": {"report": float(i)}}), tmp_path
            )
    finally:
        stop.set()
        thread.join()
    assert failures == []
    assert mf.read_manifest(tmp_path).timings == {"report": 299.0}
