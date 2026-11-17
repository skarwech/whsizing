"""R8c: the Streamlit app opens from `?run=` only a run folder of its own runs root, and a text a
visitor types (the URL, a file name, a path) never ends in a traceback.

`AppTest` on the real pages with two minimal run folders (the `canonical/` and `dq/` folders
`state.is_run` looks for): one under the runs root, one elsewhere on the disk. The URL names the
one elsewhere by its absolute path: before the guard the app opened it."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "whsizing" / "app"
PAGES = (
    "Home.py",
    "pages/1_Upload.py",
    "pages/2_Data_quality.py",
    "pages/3_Demand_profile.py",
    "pages/4_Design_basis.py",
    "pages/5_Scenarios.py",
    "pages/6_Results.py",
)
TIMEOUT = 60


def make_run(folder: Path) -> Path:
    (folder / "canonical").mkdir(parents=True)
    (folder / "dq").mkdir()
    return folder


@pytest.fixture
def runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    root = tmp_path / "runs"
    found = {
        "old": make_run(root / "2025-01-01T00-00-00_old"),
        "new": make_run(root / "2025-06-01T00-00-00_new"),
        "outside": make_run(tmp_path / "elsewhere" / "2030-01-01T00-00-00_outside"),
    }
    monkeypatch.setenv("WHSIZING_RUNS", str(root))
    return found


def opened(page: str, ref: str) -> str:
    at = AppTest.from_file(str(APP / page), default_timeout=TIMEOUT)
    at.query_params["run"] = ref
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return str(at.session_state["run_dir"])


@pytest.mark.parametrize("page", PAGES)
def test_R8c_a_run_parameter_outside_the_runs_root_is_not_opened(
    runs: dict[str, Path], page: str
) -> None:
    got = opened(page, str(runs["outside"]))
    assert got == str(runs["new"].resolve())  # dropped: the newest run of the root instead


def test_R8c_a_relative_path_to_a_run_outside_the_root_is_not_opened(
    runs: dict[str, Path],
) -> None:
    ref = f"../elsewhere/{runs['outside'].name}"
    assert opened("Home.py", ref) == str(runs["new"].resolve())


def test_R8c_a_run_name_under_the_runs_root_is_still_opened(runs: dict[str, Path]) -> None:
    assert opened("Home.py", runs["old"].name) == str(runs["old"].resolve())
    assert opened("pages/6_Results.py", runs["old"].name) == str(runs["old"].resolve())


@pytest.mark.parametrize("ref", ["a" * 300, "é" * 200, "a\0b"])
@pytest.mark.parametrize("page", PAGES)
def test_R8c_a_run_parameter_the_file_system_refuses_is_dropped_not_a_traceback(
    runs: dict[str, Path], page: str, ref: str
) -> None:
    """300 characters: ENAMETOOLONG from the stat call; the page showed the traceback, with the
    absolute path of the runs root in it."""
    assert opened(page, ref) == str(runs["new"].resolve())


CSV = b"order_id,order_date,sku,quantity\n1,2025-01-01,A,1\n"


def upload_page() -> AppTest:
    """Page 1 with the order_lines dataset selected."""
    at = AppTest.from_file(str(APP / "pages/1_Upload.py"), default_timeout=TIMEOUT)
    at.session_state["lang"] = "en"
    at.run()
    return at.selectbox(key="up.dataset").select("order_lines").run()


def test_R8c_a_typed_path_longer_than_a_file_name_is_an_error_message(
    runs: dict[str, Path],
) -> None:
    at = upload_page()
    at.text_input(key="up.order_lines.path").input("a" * 300).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("too long" in str(e.value) for e in at.error)


def test_R8c_an_uploaded_file_with_a_very_long_name_is_saved_and_read(
    runs: dict[str, Path],
) -> None:
    at = upload_page()
    name = "a" * 300 + ".csv"
    at.file_uploader(key="up.order_lines").upload(name, CSV, "text/csv").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not any("too long" in str(e.value) for e in at.error)
    mapped = [b for b in at.selectbox if b.key and b.key.startswith("map.order_lines.")]
    assert mapped  # the page read the saved file and offers its column mapping
