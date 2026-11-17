"""R8b: the swap of `calibrate` into `<run>/calibration/` (I86), on a stand-in for `calibrate()`
that writes a few files, so no engine run is needed. The real flow is in
tests/e2e/test_f10_cli_r8b.py."""

from __future__ import annotations

import errno
import stat
from pathlib import Path
from typing import Any, cast

import pytest

import whsizing.cli.sizing as sizing
from whsizing.calibration import CalibrationResult

MARK = "calibration_note.md"


def fake_calibrate(
    inputs: object,
    actuals: Path,
    activity_map: Path,
    out: Path,
    holdout_months: int,
    observed_peak_lines_h: float | None = None,
) -> CalibrationResult:
    """Writes fit.json and plots/p.png into `out` and names them like the real one."""
    (out / "plots").mkdir()
    files = (out / "fit.json", out / MARK, out / "plots" / "p.png")
    for f in files:
        f.write_text(f"new {f.name}", encoding="utf-8")
    any_ = cast(Any, None)
    return CalibrationResult(any_, any_, (), True, out, files, 0.0, 0.0)


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    monkeypatch.setattr(sizing, "calibrate", fake_calibrate)
    run = tmp_path / "run"
    run.mkdir()
    actuals, amap = tmp_path / "a.csv", tmp_path / "m.yaml"
    actuals.write_text("month,hours\n", encoding="utf-8")
    amap.write_text("map: {}\n", encoding="utf-8")
    return run / "calibration", actuals, amap


def swap(out: Path, actuals: Path, amap: Path) -> CalibrationResult:
    return sizing._calibrate_into(out, cast(Any, None), actuals, amap, 3, None)  # pyright: ignore[reportPrivateUsage]


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_T10_3_a_first_calibration_has_the_modes_of_the_other_run_folders(
    patched: tuple[Path, Path, Path],
) -> None:
    """mkdtemp made calibration/ 0700 (final audit): another uid reading the run could not enter."""
    out, actuals, amap = patched
    swap(out, actuals, amap)
    (out.parent / "canonical").mkdir()  # a folder made the way the runner makes its own
    assert stat.S_IMODE(out.stat().st_mode) == stat.S_IMODE(
        (out.parent / "canonical").stat().st_mode
    )
    assert (out / "actuals.csv").read_bytes() == actuals.read_bytes()
    assert (out / "activity_map.yaml").read_bytes() == amap.read_bytes()
    assert names(out.parent) == ["calibration", "canonical"]  # no scratch left


def test_T10_3_the_returned_result_names_the_folder_it_ended_in(
    patched: tuple[Path, Path, Path],
) -> None:
    """The scratch folder is gone after the swap: out_dir and files must not name it."""
    out, actuals, amap = patched
    result = swap(out, actuals, amap)
    assert result.out_dir == out
    assert [f.relative_to(out).as_posix() for f in result.files] == [
        "fit.json",
        MARK,
        "plots/p.png",
    ]
    assert all(f.is_file() for f in result.files)


def test_T10_3_a_recalibration_replaces_the_earlier_one_and_leaves_no_folder_behind(
    patched: tuple[Path, Path, Path],
) -> None:
    out, actuals, amap = patched
    out.mkdir()
    (out / "stale.txt").write_text("from the earlier calibration", encoding="utf-8")
    swap(out, actuals, amap)
    assert names(out) == [
        "activity_map.yaml",
        "actuals.csv",
        "calibration_note.md",
        "fit.json",
        "plots",
    ]
    assert names(out.parent) == ["calibration"]


def snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_T10_3_a_failure_while_swapping_keeps_the_earlier_calibration(
    patched: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final audit: rmtree(out) then rename(scratch) lost BOTH calibrations when the rename
    failed. The earlier folder is renamed aside first and put back if the new one cannot move in."""
    out, actuals, amap = patched
    out.mkdir()
    (out / "fit.json").write_text("earlier fit", encoding="utf-8")
    (out / "sub").mkdir()
    (out / "sub" / "x.txt").write_text("earlier x", encoding="utf-8")
    before = snapshot(out)
    real = Path.rename

    def flaky(self: Path, target: Path) -> Path:
        if self.name.startswith(".calibration-") and not self.name.startswith(".calibration-old-"):
            raise OSError(errno.EIO, "simulated rename failure")  # the scratch -> out step
        return real(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(OSError, match="simulated rename failure"):
        swap(out, actuals, amap)
    assert snapshot(out) == before
    assert names(out.parent) == ["calibration"]  # neither the scratch nor the aside folder


def test_T10_3_a_failing_calibrate_keeps_the_earlier_one_and_removes_the_scratch(
    patched: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    out, actuals, amap = patched
    out.mkdir()
    (out / "fit.json").write_text("earlier fit", encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(sizing, "calibrate", boom)
    with pytest.raises(KeyboardInterrupt):
        swap(out, actuals, amap)
    assert snapshot(out) == {"fit.json": b"earlier fit"}
    assert names(out.parent) == ["calibration"]
