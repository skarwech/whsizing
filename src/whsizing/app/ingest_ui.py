"""Page 1 helpers (F10b): uploads to disk, the mapping table, unit hints and the ingest call.

The mapping follows the library's own steps: `suggest_mapping` scores every target, the user
accepts or changes each row, `resolve_mapping` builds the `Mapping` (required targets still
unmapped are a `MappingError`), `detect_unit_hints` asks what the library asks. The ingest itself
is the CLI `ingest` command run in-process with the saved mapping, so nothing is asked twice.
"""

from __future__ import annotations

import hashlib
import os
import shlex
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from whsizing.app.calls import CliError, call
from whsizing.app.state import list_runs, runs_root
from whsizing.app.strings import tr
from whsizing.cli.data import ingest_cmd
from whsizing.errors import MappingError, WhsizingError
from whsizing.io.ingest import _UNIT_CODES, expand_files  # pyright: ignore[reportPrivateUsage]
from whsizing.io.mapping import (
    apply_mapping,
    detect_unit_hints,
    resolve_mapping,
    save_mapping,
    suggest_mapping,
)
from whsizing.io.readers import RawTable
from whsizing.report import Lang
from whsizing.schemas.ingest import Mapping
from whsizing.schemas.params import DatasetKind

SALT_ENV = "WHSIZING_SALT"
UPLOAD_TYPES = ["csv", "tsv", "txt", "xlsx", "xlsm", "xls", "parquet"]
FALLBACK_MEMORY_BYTES = 4 << 30  # when the system will not tell
DEFAULT_UPLOAD_NAME = "upload"  # for an uploaded name that is no file name ('', '.', '..')
MAX_NAME_BYTES = 200  # a file system refuses a name over 255 bytes (ENAMETOOLONG); some margin
MAX_SUFFIX_BYTES = 16  # the extension is kept (the readers go by it) when it is a real one
MAP_HEADERS = ("map_target", "map_column", "map_score", "map_status", "map_accept")
DEFAULT_UPLOAD_CAP_MB = 200  # Streamlit's own `server.maxUploadSize`


@dataclass(frozen=True)
class IngestOutcome:
    run: Path | None
    error: CliError | None


def uploads_dir() -> Path:
    return runs_root() / ".uploads"


def upload_cap_mb() -> int:
    """The largest upload this server takes (`server.maxUploadSize`, MB). `.streamlit/config.toml`
    sets 1 (the hosted demo takes no upload); `just app` passes 1024."""
    try:
        return int(st.get_option("server.maxUploadSize"))
    except (TypeError, ValueError):
        return DEFAULT_UPLOAD_CAP_MB


def memory_limit() -> int:
    """A quarter of the physical memory: an upload above it is better ingested with the CLI.
    ponytail: Streamlit holds the whole upload in memory before the page sees it, this is advice."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 4
    except (ValueError, OSError, AttributeError):
        return FALLBACK_MEMORY_BYTES // 4


def too_big(size: int) -> bool:
    return size > memory_limit()


def safe_upload_name(name: str) -> str:
    """The last component of the uploaded name; '', '.' and '..' (a folder, not a file: writing to
    `folder / '..'` raised IsADirectoryError) and a NUL byte give a fixed default name, a name over
    `MAX_NAME_BYTES` (UTF-8) is cut in its stem and keeps its extension."""
    base = Path(name.replace("\0", "")).name
    if base in ("", ".", ".."):
        return DEFAULT_UPLOAD_NAME
    if len(base.encode()) <= MAX_NAME_BYTES:
        return base
    suffix = Path(base).suffix
    if len(suffix.encode()) > MAX_SUFFIX_BYTES:
        suffix = ""
    stem = base.removesuffix(suffix).encode()[: MAX_NAME_BYTES - len(suffix.encode())]
    return stem.decode(errors="ignore") + suffix  # errors="ignore": a cut inside a character


def save_upload(name: str, data: memoryview | bytes) -> Path:
    """The uploaded bytes as a file under runs/.uploads/<sha8>/<name> (the library reads paths)."""
    folder = uploads_dir() / hashlib.sha256(data).hexdigest()[:8]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe_upload_name(name)
    path.write_bytes(data)
    return path


def discard_uploads(paths: Iterable[Path]) -> None:
    """Delete the disk copies `save_upload` made (and their folder once empty): the run keeps
    only the anonymised canonical tables, the raw client file does not outlive the script run."""
    for path in paths:
        path.unlink(missing_ok=True)
        with suppress(OSError):  # another upload of the same content shares the folder
            path.parent.rmdir()


def collect_files(dataset: DatasetKind, lg: Lang, uploaded: list[Path]) -> list[Path]:
    """The files of the page: the uploads (written to disk, listed in `uploaded` for
    `discard_uploads`; the library reads paths) and a typed local path, which avoids the upload."""
    files: list[Path] = []
    for up in st.file_uploader(
        tr("upload.files", lg), UPLOAD_TYPES, accept_multiple_files=True, key=f"up.{dataset}"
    ):
        if too_big(up.size):
            st.error(tr("upload.too_big", lg, name=up.name))
            st.code(cli_command(dataset, [Path(up.name)]))
            continue
        try:
            uploaded.append(save_upload(up.name, up.getbuffer()))
            files.append(uploaded[-1])
        except (MemoryError, OSError) as e:  # larger than memory, or the disk is full
            st.error(tr("upload.too_big", lg, name=f"{up.name} ({e})"))
            st.code(cli_command(dataset, [Path(up.name)]))
    typed = st.text_input(tr("upload.path", lg), key=f"up.{dataset}.path").strip()
    if typed:
        try:
            files += expand_files([Path(typed)])
        except (WhsizingError, OSError) as e:  # OSError: a name over the file system limit
            st.error(str(e))
    return files


def cli_command(dataset: str, files: list[Path]) -> str:
    """The terminal command that does what the 'Run ingest' button does, for large files."""
    names = " ".join(shlex.quote(str(f)) for f in files)
    return f"whsizing ingest {names} --dataset {shlex.quote(dataset)} --salt-file <salt-file>"


def salt_ready() -> bool:
    return bool(os.environ.get(SALT_ENV))


def set_salt(value: str) -> None:
    """The salt of this server process only: never written to a file (I75 d)."""
    os.environ[SALT_ENV] = value


# ---------------------------------------------------------------------------- mapping widgets
def mapping_table(raw: RawTable, dataset: DatasetKind, key: str, lg: Lang) -> Mapping | str:
    """Target -> column rows (score, status, accept toggle); the `Mapping` they make, or the
    library's message when a required target is unmapped."""
    suggestion = suggest_mapping(raw, dataset)
    head = st.columns([2, 4, 1, 2, 2])
    for col, name in zip(head, MAP_HEADERS, strict=True):
        col.markdown(f"**{tr(name, lg)}**")
    edited = []
    for t in suggestion.targets:
        row = st.columns([2, 4, 1, 2, 2])
        row[0].markdown(f"`{t.target}`" + (" \\*" if t.required else ""))
        options = ["", *raw.columns]
        index = options.index(t.column) if t.column in options else 0
        column = row[1].selectbox(
            t.target, options, index, key=f"{key}.{t.target}.col", help=t.reason,
            label_visibility="collapsed",
        )  # fmt: skip
        row[2].write(f"{t.score:.2f}")
        row[3].write(t.status)
        accepted = row[4].toggle(
            tr("map_accept", lg), t.status == "auto", key=f"{key}.{t.target}.ok",
            label_visibility="collapsed",
        )  # fmt: skip
        chosen = column if column and accepted else None
        edited.append(
            t.model_copy(update={"column": chosen, "status": "auto" if chosen else "unmapped"})
        )
    try:
        return resolve_mapping(suggestion.model_copy(update={"targets": edited}), raw)
    except MappingError as e:
        return str(e)


def unit_hints(raw: RawTable, mapping: Mapping, key: str, lg: Lang) -> Mapping:
    """sku_master: the unit questions of the ingest (cm / g), answered here and recorded in the
    mapping so the ingest has nothing left to ask."""
    if mapping.dataset != "sku_master":
        return mapping
    hints: dict[str, str] = {}
    try:
        detected = detect_unit_hints(apply_mapping(raw, mapping))
    except MappingError:
        return mapping
    for hint, (unit, why) in detected.items():
        code, base, op = _UNIT_CODES[hint]
        convert = st.checkbox(
            tr("unit_hint", lg, code=code, why=why, unit=unit, base=base, op=op), True,
            key=f"{key}.{hint}",
        )  # fmt: skip
        hints[hint] = unit if convert else base
    return mapping.model_copy(update={"unit_hints": hints})


# ---------------------------------------------------------------------------------- the ingest
def run_ingest(
    dataset: DatasetKind, files: list[Path], mapping: Mapping, run: Path | None
) -> IngestOutcome:
    """`whsizing ingest` of `files` with `mapping`, into `run` (a new run folder when None)."""
    path = uploads_dir() / f"{dataset}.mapping.yaml"
    save_mapping(mapping, path)
    before = set(list_runs(runs_root()))
    kwargs: dict[str, Any] = {"out_dir": runs_root(), "run": run}
    try:
        result = call(
            ingest_cmd, files=files, dataset=dataset, mapping=path, non_interactive=True, **kwargs
        )
    except CliError as e:  # exit 3 keeps the folder (its dq/ says why): hand it over
        made = sorted(set(list_runs(runs_root())) - before)
        return IngestOutcome(run or (made[-1] if made else None), e)
    finally:  # the run keeps its own copy (inputs/mapping)
        path.unlink(missing_ok=True)
    return IngestOutcome(Path(result.last_line), None)
