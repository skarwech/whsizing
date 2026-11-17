"""F10a CLI, fast tests: `--help` smoke of every command (T10.1), the cheap happy paths, and the
exit codes of §2.7 that need no run folder (T10.3). The run-folder flows are in
tests/e2e/test_f10_cli_e2e.py."""

from __future__ import annotations

import json
import re
import shutil
import signal
import threading
from pathlib import Path
from typing import Any

import pytest
import typer.main
import yaml
from tests.unit.test_f2_r6 import garbage, quoted_table
from typer.testing import CliRunner

import whsizing.cli.data as cli_data
from whsizing.cli import app
from whsizing.cli._core import (
    Terminated,
    _range,  # pyright: ignore[reportPrivateUsage]
    handle_errors,
)
from whsizing.errors import WhsizingError
from whsizing.schemas import Range

ROOT = Path(__file__).resolve().parents[2]
TINY = ROOT / "tests" / "golden" / "tiny_golden"
runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")

COMMANDS = [
    ["synth"],
    ["ingest"],
    ["profile"],
    ["basis", "init"],
    ["size"],
    ["compare"],
    ["report"],
    ["run-all"],
    ["calibrate"],
    ["rerun"],
    ["validate-catalog"],
]


@pytest.fixture(autouse=True)
def salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHSIZING_SALT", "f10-unit-salt")


@pytest.mark.parametrize("argv", COMMANDS, ids=" ".join)
def test_T10_1_every_command_has_help(argv: list[str]) -> None:
    res = runner.invoke(app, [*argv, "--help"])
    assert res.exit_code == 0, res.output
    help_text = plain(res.output)
    assert "Usage" in help_text
    assert " ".join(argv) in help_text.replace("whsizing ", "")


def plain(text: str) -> str:
    """The text without ANSI styles: Typer forces its rich help to a terminal when GITHUB_ACTIONS,
    FORCE_COLOR or PY_COLORS is set, and the styles cut an option such as `--debug` in pieces."""
    return ANSI.sub("", text)


def test_T10_1_top_level_help_lists_every_command() -> None:
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    help_text = plain(res.output)
    for name in ("synth", "ingest", "profile", "basis", "size", "compare", "report", "run-all"):
        assert name in help_text
    for name in ("calibrate", "rerun", "validate-catalog", "--debug", "--version"):
        assert name in help_text


def test_T10_1_basis_init_writes_the_template_and_never_overwrites(tmp_path: Path) -> None:
    out = tmp_path / "basis.yaml"
    res = runner.invoke(app, ["basis", "init", "--lang", "en", "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert res.stdout.strip() == str(out)
    assert "[CLIENT]" in out.read_text(encoding="utf-8")
    again = runner.invoke(app, ["basis", "init", "--out", str(out)])
    assert again.exit_code == 2 and "exists" in again.stderr


def test_T10_1_synth_writes_the_files_of_the_profile(tmp_path: Path) -> None:
    profile = ROOT / "data" / "synth" / "profiles" / "tiny_golden.yaml"
    res = runner.invoke(app, ["synth", str(profile), "--out", str(tmp_path), "--seed", "42"])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "csv_en" / "order_lines.csv").is_file()
    assert (tmp_path / "order_lines.parquet").is_file()
    assert str(tmp_path / "csv_fr" / "sku_master.csv") in res.stdout.splitlines()


def test_T10_1_validate_catalog_reports_the_todo_sources() -> None:
    res = runner.invoke(app, ["validate-catalog", str(ROOT / "catalog")])
    assert res.exit_code == 0, res.output
    assert "valid" in res.stdout
    n = int(next(ln for ln in res.stdout.splitlines() if "source TODO" in ln).split()[0])
    assert n > 0
    assert res.stdout.count("  TODO ") == n


def test_T10_3_exit_2_validate_catalog_names_the_file_and_the_key(tmp_path: Path) -> None:
    bad = tmp_path / "catalog"
    shutil.copytree(ROOT / "catalog", bad)
    path = bad / "area_factors.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\nsurprise_key: 1\n", encoding="utf-8")
    res = runner.invoke(app, ["validate-catalog", str(bad)])
    assert res.exit_code == 2
    assert "area_factors.yaml" in res.stderr and "surprise_key" in res.stderr


def test_R6_3_validate_catalog_lists_every_broken_file_and_exits_2(tmp_path: Path) -> None:
    """Was: only the first file (two broken family files gave the `amr_gtp` error alone)."""
    bad = tmp_path / "catalog"
    shutil.copytree(ROOT / "catalog", bad)
    for rel in ("families/amr_gtp.yaml", "families/cube_asrs.yaml", "area_factors.yaml"):
        path = bad / rel
        path.write_text(path.read_text(encoding="utf-8") + "\nsurprise_key: 1\n", encoding="utf-8")
    res = runner.invoke(app, ["validate-catalog", str(bad)])
    assert res.exit_code == 2, res.output
    for name in ("amr_gtp.yaml", "cube_asrs.yaml", "area_factors.yaml"):
        assert name in res.stderr
    assert "3 error(s)" in res.stderr and "Traceback" not in res.output
    assert "valid" not in res.stdout  # nothing reported as a success


def ingest_order_lines(path: Path, runs: Path, *extra: str) -> Any:
    return runner.invoke(
        app, ["ingest", str(path), "--dataset", "order_lines", "--non-interactive",
              "--out-dir", str(runs), *extra]
    )  # fmt: skip


def error_line(res: Any) -> str:
    """The `error: ...` line of stderr: the log lines above it name the file too."""
    return next((ln for ln in res.stderr.splitlines() if ln.startswith("error: ")), "")


def test_R6_2_ingest_of_a_multi_byte_separated_file_exits_2_and_names_the_file(
    tmp_path: Path,
) -> None:
    """`head -c 4000 /dev/urandom > g.csv; whsizing ingest g.csv ...` was exit 1 with a raw polars
    ValueError (a sniffed multi-byte separator: polars takes one byte). A random file sniffs one
    on some CPython releases only; a file whose cells are joined by '§' does on all of them."""
    res = ingest_order_lines(quoted_table(tmp_path, "§"), tmp_path / "runs")
    assert res.exit_code == 2, res.output
    assert "g.csv" in error_line(res) and "sniffed delimiter" in error_line(res)
    assert "ValueError" not in res.output and "Traceback" not in res.output
    assert list((tmp_path / "runs").iterdir()) == []  # a failed ingest leaves no empty run folder


def test_R6_2_ingest_of_a_binary_file_exits_2_and_names_the_file(tmp_path: Path) -> None:
    """Whatever the sniffer makes of 30 `head -c 4000 /dev/urandom` files (a multi-byte separator,
    an unclosed quote, no header row, a table the mapping then refuses: it differs between CPython
    releases), `ingest` ends in exit 2 naming the file, no traceback, no run folder left."""
    wrong = []
    for seed in range(30):
        runs = tmp_path / f"runs-{seed}"  # one folder per seed: a failure must not blame the next
        res = ingest_order_lines(garbage(seed, tmp_path), runs)
        leftovers = list(runs.iterdir())
        if not (
            res.exit_code == 2
            and "g.csv" in error_line(res)
            and "ValueError" not in res.output
            and "Traceback" not in res.output
            and not leftovers
        ):
            wrong.append(f"seed {seed}: exit {res.exit_code}, {error_line(res)!r}, {leftovers}")
    assert not wrong, "\n".join(wrong)


def test_R6_2_ingest_of_a_line_over_the_csv_field_limit_exits_2_and_names_the_file(
    tmp_path: Path,
) -> None:
    """Was: `error: unexpected Error: field larger than field limit (131072)`, exit 1, no file
    name, run folder kept (a zero-filled file, a one-line JSON export)."""
    path = tmp_path / "g.csv"
    path.write_bytes(b"\x00" * 200_000)
    res = ingest_order_lines(path, tmp_path / "runs")
    assert res.exit_code == 2, res.output
    assert "g.csv" in error_line(res) and "unexpected" not in res.stderr
    assert list((tmp_path / "runs").iterdir()) == []


def test_R6_2_ingest_of_an_empty_file_with_a_saved_mapping_exits_2_and_names_the_file(
    tmp_path: Path,
) -> None:
    """Was: `error: unexpected NoDataError: empty CSV`, exit 1, run folder kept: the mapping of the
    last export (header_row 1) read against an export that came out empty."""
    mapping = tmp_path / "order_lines.yaml"
    mapping.write_text(
        yaml.safe_dump({"dataset": "order_lines", "header_row": 1, "columns": {"order_id": "id"}}),
        encoding="utf-8",
    )
    path = tmp_path / "g.csv"
    path.write_bytes(b"")
    res = ingest_order_lines(path, tmp_path / "runs", "--mapping", str(mapping))
    assert res.exit_code == 2, res.output
    assert "g.csv" in error_line(res) and "unexpected" not in res.stderr
    assert list((tmp_path / "runs").iterdir()) == []


def test_R6_2_ingest_of_a_header_cell_that_reads_as_a_regex_exits_2_and_names_the_file(
    tmp_path: Path,
) -> None:
    """Was: `error: unexpected InvalidOperationError: invalid regex in selector '^[$'`, exit 1, no
    file name, run folder kept (a header cell that starts with ^ and ends with $: polars takes it
    for a regex; a binary file has one now and then)."""
    path = tmp_path / "g.csv"
    path.write_text("sku;^[$;a\nA;x;p\nB;y;q\n", encoding="utf-8")
    res = ingest_order_lines(path, tmp_path / "runs")
    assert res.exit_code == 2, res.output
    assert "g.csv" in error_line(res) and "unexpected" not in res.stderr
    assert list((tmp_path / "runs").iterdir()) == []


def test_R6_2_ingest_of_a_corrupt_parquet_exits_2_and_names_the_file(tmp_path: Path) -> None:
    """Was: `error: unexpected ComputeError ...`, exit 1, and the run folder left behind."""
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"garbage")
    res = runner.invoke(
        app, ["ingest", str(bad), "--dataset", "sku_master", "--non-interactive",
              "--out-dir", str(tmp_path / "runs")]
    )  # fmt: skip
    assert res.exit_code == 2, res.output
    assert "bad.parquet" in res.stderr and "not a readable Parquet file" in res.stderr
    assert "unexpected" not in res.stderr and "Traceback" not in res.output
    assert list((tmp_path / "runs").iterdir()) == []


def test_R6_3_validate_catalog_loads_a_valid_catalog_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Was: validate_catalog loaded it, then the CLI loaded it again (warnings logged twice)."""
    import whsizing.catalog.loader as loader

    calls: list[Path] = []
    real = loader.load_catalog

    def counting(catalog_dir: Path | str) -> Any:
        calls.append(Path(catalog_dir))
        return real(catalog_dir)

    monkeypatch.setattr(loader, "load_catalog", counting)
    res = runner.invoke(app, ["validate-catalog", str(ROOT / "catalog")])
    assert res.exit_code == 0, res.output
    assert len(calls) == 1


def test_T10_3_exit_2_unknown_yaml_key_in_project(tmp_path: Path) -> None:
    project = tmp_path / "project.yaml"
    project.write_text(
        (ROOT / "tests/fixtures/config/project_example.yaml").read_text(encoding="utf-8")
        + "surprise_key: 1\n",
        encoding="utf-8",
    )
    res = runner.invoke(app, ["run-all", str(project)])
    assert res.exit_code == 2
    assert "surprise_key" in res.stderr and "unknown key" in res.stderr
    assert "Traceback" not in res.output


def test_T10_3_exit_2_unmapped_required_column_non_interactive(tmp_path: Path) -> None:
    csv = tmp_path / "mystery.csv"
    csv.write_text("alpha,beta,gamma\n1,2,3\n4,5,6\n", encoding="utf-8")
    res = runner.invoke(
        app, ["ingest", str(csv), "--dataset", "order_lines", "--non-interactive", "--out-dir",
              str(tmp_path / "runs")]
    )  # fmt: skip
    assert res.exit_code == 2, res.output
    assert "error:" in res.stderr and "Traceback" not in res.output
    assert list((tmp_path / "runs").iterdir()) == []  # a failed ingest leaves no empty run folder


def test_T10_3_exit_2_missing_input_file(tmp_path: Path) -> None:
    res = runner.invoke(
        app,
        ["ingest", str(tmp_path / "nope.csv"), "--dataset", "order_lines", "--non-interactive",
         "--out-dir", str(tmp_path / "runs")],
    )  # fmt: skip
    assert res.exit_code == 2 and "nope.csv" in res.stderr
    assert runner.invoke(app, ["rerun", str(tmp_path / "no-run")]).exit_code == 2
    assert runner.invoke(app, ["profile", str(tmp_path)]).exit_code == 2  # not a run folder


def test_T10_3_exit_2_without_a_salt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHSIZING_SALT")
    res = runner.invoke(
        app,
        ["ingest", str(TINY / "csv_en" / "sku_master.csv"), "--dataset", "sku_master",
         "--non-interactive", "--out-dir", str(tmp_path / "runs")],
    )  # fmt: skip
    assert res.exit_code == 2 and "salt" in res.stderr
    assert not (tmp_path / "runs").exists()  # checked before anything is created


def test_T10_3_exit_2_usage_error_is_not_swallowed() -> None:
    res = runner.invoke(app, ["size"])  # no run, no --basis, no --scenarios
    assert res.exit_code == 2
    assert "Missing" in res.output or "required" in res.output.lower()
    assert runner.invoke(app, ["no-such-command"]).exit_code == 2


def test_T10_3_exit_3_tiny_golden_is_blocked_by_r9(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    salt_file = tmp_path / "salt.txt"
    salt_file.write_text("tiny-salt\n", encoding="utf-8")
    res = runner.invoke(
        app,
        ["ingest", str(TINY / "csv_en" / "order_lines.csv"), "--dataset", "order_lines",
         "--non-interactive", "--salt-file", str(salt_file), "--out-dir", str(runs)],
    )  # fmt: skip
    assert res.exit_code == 3, res.output
    assert "R9" in res.stderr and "Traceback" not in res.output
    (run,) = runs.iterdir()  # the folder is kept: its dq/ explains the refusal
    report = json.loads((run / "dq" / "dq_report.json").read_text(encoding="utf-8"))
    assert any(r["rule"] == "R9" and r["severity"] == "blocking" for r in report["rules"])
    assert not (run / "canonical" / "order_lines.parquet").exists()


def test_T10_3_exit_1_unexpected_exception_has_a_short_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(cli_data, "synthesize", boom)
    res = runner.invoke(app, ["synth", str(tmp_path / "p.yaml")])
    assert res.exit_code == 1
    assert "error: unexpected RuntimeError: injected failure" in res.stderr
    assert "Traceback" not in res.output


def test_T10_3_exit_1_debug_prints_the_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(cli_data, "synthesize", boom)
    res = runner.invoke(app, ["--debug", "synth", str(tmp_path / "p.yaml")])
    assert res.exit_code == 1
    assert "Traceback" in res.stderr and "injected failure" in res.stderr
    quiet = runner.invoke(app, ["synth", str(tmp_path / "p.yaml")])  # the flag does not stick
    assert "Traceback" not in quiet.output


def test_T10_3_exit_1_base_whsizing_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise WhsizingError("pipeline integrity failure")

    monkeypatch.setattr(cli_data, "synthesize", boom)
    res = runner.invoke(app, ["synth", str(tmp_path / "p.yaml")])
    assert res.exit_code == 1 and "error: pipeline integrity failure" in res.stderr


def test_T10_3_exit_0_version() -> None:
    assert runner.invoke(app, ["--version"]).exit_code == 0


def all_commands(cmd: Any, path: str = "whsizing") -> list[tuple[str, Any]]:
    """Every (path, command) of the Typer app, groups included (Typer 0.28 has its own click)."""
    found = [(path, cmd)]
    for name, sub in getattr(cmd, "commands", {}).items():
        found += all_commands(sub, f"{path} {name}")
    return found


def test_T10_1_help_strings_have_no_square_brackets() -> None:
    """Rich takes "[default]" for a style tag and drops it from --help."""
    for path, cmd in all_commands(typer.main.get_command(app)):
        for param in cmd.params:
            assert "[" not in (getattr(param, "help", None) or ""), (path, param.name)
    ingest = runner.invoke(app, ["ingest", "--help"]).output
    assert "WHSIZING_SALT" in ingest  # the default of --salt-file is readable


def test_T10_1_run_all_has_every_option_of_the_commands_it_runs() -> None:
    cmd = dict(all_commands(typer.main.get_command(app)))["whsizing run-all"]
    options = {
        o for p in cmd.params for o in getattr(p, "opts", []) + getattr(p, "secondary_opts", [])
    }
    assert {
        "--strict", "--no-strict", "--worlds", "--sensitivity", "--no-sensitivity", "--delta",
        "--lang", "--formats", "--salt-file", "--basis", "--scenarios", "--catalog",
        "--non-interactive", "--keep-descriptions",
    } <= options  # fmt: skip


def test_T10_1_comparison_fte_keeps_a_decimal() -> None:
    """A small site is 0.7 to 1.4 FTE: whole numbers hid the range (S0 printed '1 [1-1]')."""
    fte = Range(lo=0.715, typ=1.003, hi=1.403, unit="fte")
    assert _range(fte, 1, "all", 1) == "1.0 [0.7-1.4]"
    assert _range(fte, 1, "typ", 1) == "1.0"
    assert _range(Range(lo=1_200.0, typ=3_400.0, hi=5_600.0, unit="eur"), 1e3, "all") == "3 [1-6]"


def test_T10_3_exit_2_run_all_without_order_lines(tmp_path: Path) -> None:
    """A forgotten required dataset is a bad project (exit 2), found before a run folder exists."""
    text = yaml.safe_load(
        (ROOT / "tests/fixtures/config/project_example.yaml").read_text(encoding="utf-8")
    )
    text["inputs"]["order_lines"] = None
    project = tmp_path / "project.yaml"
    project.write_text(yaml.safe_dump(text), encoding="utf-8")
    res = runner.invoke(app, ["run-all", str(project)])
    assert res.exit_code == 2, res.output
    assert "order_lines" in res.stderr and "Traceback" not in res.output
    assert not (tmp_path / "runs").exists()


def test_T10_3_exit_2_run_all_override_paths_are_the_ones_used(tmp_path: Path) -> None:
    project = tmp_path / "project.yaml"
    shutil.copyfile(ROOT / "tests/fixtures/config/project_example.yaml", project)
    salt = tmp_path / "salt.txt"
    salt.write_text("s\n", encoding="utf-8")  # the project's own salt file does not exist here
    gone = tmp_path / "gone"
    real_catalog = ["--catalog", str(ROOT / "catalog")]
    for name, override in (
        ("b.yaml", ["--basis", str(gone / "b.yaml"), *real_catalog]),
        ("cat", ["--catalog", str(gone / "cat")]),
    ):
        res = runner.invoke(app, ["run-all", str(project), "--salt-file", str(salt), *override])
        assert res.exit_code == 2 and f"gone/{name}" in res.stderr, (name, res.output)
    bad = runner.invoke(app, ["run-all", str(project), "--delta", "2"])
    assert bad.exit_code == 2 and "invalid option" in bad.stderr


# --- R8b: SIGTERM, calibrate options -----------------------------------------------------------
def test_T10_3_sigterm_becomes_terminated_with_exit_code_128_plus_signal() -> None:
    """`handle_errors` routes SIGTERM through `Terminated` (a WhsizingError, so the runner's failure
    path marks the run); the code is the shell's 128 + 15 and the old handler comes back."""
    before = signal.getsignal(signal.SIGTERM)

    @handle_errors
    def command() -> None:
        assert signal.getsignal(signal.SIGTERM) is not before
        signal.raise_signal(signal.SIGTERM)  # runs the handler now, in this (the main) thread

    with pytest.raises(typer.Exit) as exit_:
        command()
    assert exit_.value.exit_code == 143
    assert signal.getsignal(signal.SIGTERM) is before
    assert (
        Terminated(signal.SIGTERM).exit_code == 143 and Terminated(signal.SIGHUP).exit_code == 129
    )


def test_T10_3_a_command_in_a_thread_keeps_the_default_sigterm_handler() -> None:
    """Only the main thread may set a handler (Streamlit runs commands in a script thread)."""

    @handle_errors
    def command() -> str:
        return "done"

    out: list[str] = []
    thread = threading.Thread(target=lambda: out.append(command()))
    thread.start()
    thread.join()
    assert out == ["done"]


def test_T10_1_calibrate_has_force_and_observed_peak_options() -> None:
    cmd = dict(all_commands(typer.main.get_command(app)))["whsizing calibrate"]
    options = {o for p in cmd.params for o in getattr(p, "opts", [])}
    assert {"--actuals", "--activity-map", "--holdout-months", "--force"} <= options
    assert "--observed-peak-lines-h" in options
