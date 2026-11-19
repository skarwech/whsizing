"""F10b: the CLI commands run in-process (T10.4): output captured, exit codes become `CliError`,
and the upload helpers of page 1."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from whsizing.app import ingest_ui
from whsizing.app.calls import CliError, call, printed_paths
from whsizing.cli import handle_errors
from whsizing.errors import ConfigError, DataQualityError


@handle_errors
def ok_command(name: str = "x") -> None:
    typer.echo("log line")
    typer.echo(f"/runs/{name}")


@handle_errors
def failing_command(error: Exception) -> None:
    raise error


def test_T10_4_call_returns_the_captured_output_and_the_run_folder_line() -> None:
    result = call(ok_command, name="2026-01-01T00-00-00_abcdef")
    assert result.stdout.splitlines() == ["log line", "/runs/2026-01-01T00-00-00_abcdef"]
    assert result.last_line == "/runs/2026-01-01T00-00-00_abcdef"


@pytest.mark.parametrize(
    ("error", "code"),
    [(ConfigError("basis.yaml: bad key"), 2), (DataQualityError("1 blocking issue"), 3),
     (RuntimeError("boom"), 1)],
)  # fmt: skip
def test_T10_4_call_turns_a_command_failure_into_cli_error_with_its_exit_code(
    error: Exception, code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(CliError) as caught:
        call(failing_command, error=error)
    assert caught.value.code == code
    assert str(error) in caught.value.message
    assert not caught.value.message.startswith("error: ")
    assert capsys.readouterr().err == ""  # captured, not leaked to the terminal


LOG_LINE = "2026-11-09T17:29:47.5Z [warning  ] catalog_todo_sources count=72 run_id=x total=72"


@pytest.mark.parametrize(
    ("error", "expected"),
    [(ConfigError("scenarios.yaml: no scenario defined"), "scenarios.yaml: no scenario defined"),
     (RuntimeError("boom"), "unexpected RuntimeError: boom")],
)  # fmt: skip
def test_T10_4_the_log_lines_a_command_wrote_before_failing_are_not_in_the_message(
    error: Exception, expected: str
) -> None:
    @handle_errors
    def noisy() -> None:
        typer.echo(LOG_LINE, err=True)
        typer.echo(LOG_LINE.replace("72", "73"), err=True)
        raise error

    with pytest.raises(CliError) as caught:
        call(noisy)
    assert caught.value.message == expected  # no log line, no `error: `, no traceback hint


def test_T10_4_a_failure_without_an_error_line_keeps_what_the_command_wrote() -> None:
    def odd() -> None:  # not wrapped by `handle_errors`: no `error: ` line
        typer.echo("something went wrong", err=True)
        raise typer.Exit(4)

    with pytest.raises(CliError) as caught:
        call(odd)
    assert (caught.value.code, caught.value.message) == (4, "something went wrong")


def test_T10_4_call_lists_the_files_a_command_printed() -> None:
    @handle_errors
    def report() -> None:
        typer.echo("/r/report/report_fr.xlsx")
        typer.echo("/r/report/report_fr.pdf")
        typer.echo("indicative study")

    result = call(report)
    assert printed_paths(result, (".pdf",)) == [Path("/r/report/report_fr.pdf")]
    assert len(printed_paths(result, (".pdf", ".xlsx"))) == 2


def test_T10_4_uploads_are_written_under_the_runs_folder_by_content_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    a = ingest_ui.save_upload("sku.csv", b"sku,l\n1,2\n")
    b = ingest_ui.save_upload("../../sku.csv", b"sku,l\n1,2\n")  # a path in the name is dropped
    assert a == b and a.read_bytes() == b"sku,l\n1,2\n"
    assert a.is_relative_to(tmp_path / ".uploads")
    assert ingest_ui.save_upload("sku.csv", b"other").parent != a.parent


def test_T10_4_discarding_uploads_deletes_the_raw_copies_and_their_empty_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WHSIZING_RUNS", str(tmp_path))
    a = ingest_ui.save_upload("a.csv", b"sku,l\n1,2\n")
    twin = ingest_ui.save_upload("b.csv", b"sku,l\n1,2\n")  # same content: same folder
    ingest_ui.discard_uploads([a])
    assert not a.exists() and twin.exists()  # the folder is still in use
    ingest_ui.discard_uploads([twin])
    assert not twin.parent.exists()  # empty folder removed
    ingest_ui.discard_uploads([a])  # a copy that is gone already is fine
    assert list((tmp_path / ".uploads").iterdir()) == []


def test_T10_4_an_upload_above_a_quarter_of_the_memory_is_sent_to_the_cli() -> None:
    limit = ingest_ui.memory_limit()
    assert limit > 0
    assert ingest_ui.too_big(limit + 1) and not ingest_ui.too_big(1024)
    command = ingest_ui.cli_command("sku_master", [Path("big file.csv")])
    assert command.startswith("whsizing ingest 'big file.csv' --dataset sku_master")


def test_T10_4_the_upload_cap_is_the_option_of_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    options: dict[str, object] = {"server.maxUploadSize": 1}
    monkeypatch.setattr(ingest_ui.st, "get_option", lambda key: options.get(key))
    assert ingest_ui.upload_cap_mb() == 1  # a small cap (the repository's config sets 0)
    options["server.maxUploadSize"] = 1024  # `just app`
    assert ingest_ui.upload_cap_mb() == 1024
    options["server.maxUploadSize"] = "not a number"
    assert ingest_ui.upload_cap_mb() == ingest_ui.DEFAULT_UPLOAD_CAP_MB  # then Streamlit's own
    options.clear()
    assert ingest_ui.upload_cap_mb() == ingest_ui.DEFAULT_UPLOAD_CAP_MB


def test_T10_4_the_salt_lives_in_this_process_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WHSIZING_SALT", raising=False)
    assert not ingest_ui.salt_ready()
    ingest_ui.set_salt("s3cret")
    try:
        assert ingest_ui.salt_ready()
    finally:
        monkeypatch.delenv("WHSIZING_SALT", raising=False)
