"""R8c app hygiene: the `?run=` guard, `save_upload` names and the shell command of the 'too big'
hint (docs/audit/FINAL.md, low list)."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from whsizing.app import entry, ingest_ui
from whsizing.app.strings import tr


def make_run(folder: Path) -> Path:
    """The two folders `state.is_run` looks for (§2.4)."""
    (folder / "canonical").mkdir(parents=True)
    (folder / "dq").mkdir()
    return folder


# ------------------------------------------------------------------ ?run= guard
@pytest.fixture
def root(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    make_run(runs / "2025-01-01T00-00-00_aaaaaa")
    make_run(tmp_path / "elsewhere" / "2030-01-01T00-00-00_bbbbbb")  # a real run, outside the root
    (runs / "not_a_run").mkdir()
    (runs / "link").symlink_to(tmp_path / "elsewhere" / "2030-01-01T00-00-00_bbbbbb")
    return runs


def test_R8c_the_run_parameter_may_name_a_run_folder_under_the_runs_root(root: Path) -> None:
    assert entry.safe_run_name(root, "2025-01-01T00-00-00_aaaaaa") == "2025-01-01T00-00-00_aaaaaa"


@pytest.mark.parametrize(
    "ref",
    [
        None,
        "",
        ".",
        "..",
        "../elsewhere/2030-01-01T00-00-00_bbbbbb",  # relative path out of the root
        "not_a_run",  # a folder of the root that is no run
        "no-such-run",
        "link",  # a symlink under the root to a run outside it
        "2025-01-01T00-00-00_aaaaaa/",  # path syntax, even if it ends in a run
        "2025-01-01T00-00-00_aaaaaa/canonical",
        "a" * 300,  # over the file system limit: the stat call raised ENAMETOOLONG
        "é" * 200,  # 400 bytes
        "a\0b",
    ],
)
def test_R8c_the_run_parameter_never_names_anything_else(root: Path, ref: str | None) -> None:
    assert entry.safe_run_name(root, ref) is None


def test_R8c_an_absolute_path_to_a_run_outside_the_root_is_refused(root: Path) -> None:
    outside = root.parent / "elsewhere" / "2030-01-01T00-00-00_bbbbbb"
    assert (outside / "canonical").is_dir()
    assert entry.safe_run_name(root, str(outside)) is None


# ------------------------------------------------------------------ save_upload
@pytest.fixture
def uploads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path / "runs"))
    return ingest_ui.uploads_dir()


@pytest.mark.parametrize("name", ["..", "", ".", "a/..", "/", "\0", "../.."])
def test_R8c_save_upload_gives_a_default_name_to_a_name_that_is_no_file_name(
    uploads: Path, name: str
) -> None:
    """`..` and '' used to raise IsADirectoryError (folder / '..' is a folder)."""
    path = ingest_ui.save_upload(name, b"a,b\n1,2\n")
    assert path.name == ingest_ui.DEFAULT_UPLOAD_NAME
    assert path.parent.parent == uploads  # under runs/.uploads/<sha8>/, nowhere else
    assert path.read_bytes() == b"a,b\n1,2\n"


@pytest.mark.parametrize(
    ("name", "ends"),
    [
        ("a" * 300 + ".xlsx", ".xlsx"),  # the extension survives (the readers go by it)
        ("é" * 300 + ".csv", "éé.csv"),
        ("a." + "b" * 300, "bbbb"),  # a 'suffix' that is no extension is cut with the rest
        ("x" * 300, "xxxx"),
        ("." * 300, "...."),
        ("é" * 101, "éé"),  # 202 bytes: cut between two characters, not inside one
    ],
)
def test_R8c_save_upload_cuts_a_name_over_the_file_system_limit_and_keeps_the_extension(
    uploads: Path, name: str, ends: str
) -> None:
    """A name over 255 bytes raised OSError (ENAMETOOLONG) out of `save_upload`."""
    path = ingest_ui.save_upload(name, b"a,b\n1,2\n")
    assert len(path.name.encode()) <= ingest_ui.MAX_NAME_BYTES < 255
    assert path.name.endswith(ends)
    assert path.read_bytes() == b"a,b\n1,2\n" and path.parent.parent == uploads


@pytest.mark.parametrize(
    ("name", "saved"),
    [
        ("orders.csv", "orders.csv"),
        ("../../etc/orders.csv", "orders.csv"),
        ("a/b/c.xlsx", "c.xlsx"),
    ],
)
def test_R8c_save_upload_keeps_the_last_component_of_a_real_name(
    uploads: Path, name: str, saved: str
) -> None:
    path = ingest_ui.save_upload(name, b"x")
    assert path.name == saved and path.parent.parent == uploads


# ------------------------------------------------------------------ the 'too big' hint
def test_R8c_the_cli_hint_quotes_every_file_name_for_the_shell() -> None:
    names = [Path('it\'s "big" $(rm -rf x).csv'), Path("plain.csv"), Path("a b;c.csv")]
    command = ingest_ui.cli_command("order_lines", names)
    words = shlex.split(command.replace(" <salt-file>", " SALT"))
    assert words[:2] == ["whsizing", "ingest"]
    assert words[2:5] == [str(n) for n in names]  # each name is one shell word, unchanged
    assert words[5:] == ["--dataset", "order_lines", "--salt-file", "SALT"]


# ------------------------------------------------------------------ the typed-path field
@pytest.mark.parametrize("lang", ["fr", "en"])
def test_R8c_the_typed_path_field_says_it_is_for_local_use(lang: str) -> None:
    label = tr("upload.path", lang)  # type: ignore[arg-type]
    assert "local" in label and "machine" in label


def test_R8c_every_page_starts_through_the_guarded_setup() -> None:
    """A page that called `state.setup` directly would open any `?run=` path again."""
    app = Path(entry.__file__).parent
    pages = [app / "Home.py", *sorted((app / "pages").glob("*.py"))]
    assert len(pages) == 7
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "entry.setup(" in text and "state.setup(" not in text, page.name
