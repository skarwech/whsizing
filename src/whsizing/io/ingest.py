"""F2 entry point (wrapped by `whsizing ingest` and `run-all`): files → canonical/, dq/, mapping/.

Datasets not given here but already in `<out_dir>/canonical/` (an earlier ingest into the same
folder) are reloaded, so cross-table rules (R2, R7, R11, R14) see the whole study and the
manifest keeps their entries. Their rows are already cleaned, so the rules that look at one
dataset's raw rows (REQ, R1, R3-R6, R8) and their notes are taken from the earlier DQ report.
"""

from __future__ import annotations

import glob
import hashlib
import os
from collections.abc import Mapping as MappingT
from datetime import datetime
from pathlib import Path
from typing import cast

import polars as pl

from whsizing.errors import ConfigError, DataQualityError, MappingError
from whsizing.io.anonymize import anonymize
from whsizing.io.canonical import (
    DEFAULT_UNITS_PER_PALLET,
    MANIFEST,
    derive,
    make_manifest,
    write_canonical,
    write_manifest,
)
from whsizing.io.dq import DQ_JSON, build_dq_report, write_dq_report
from whsizing.io.mapping import (
    Confirm,
    apply_mapping,
    apply_unit_hints,
    detect_unit_hints,
    load_mapping,
    number_notes,
    resolve_mapping,
    save_mapping,
    suggest_mapping,
    tie_break_notes,
)
from whsizing.io.readers import duplicate_header_notes, read_any, read_parquet_file
from whsizing.io.rules import CanonicalFrames, apply_rules
from whsizing.logging import get_logger
from whsizing.schemas.ingest import DQReport, Mapping, RuleResult
from whsizing.schemas.manifest import DatasetIngest, IngestManifest, SourceFile
from whsizing.schemas.params import DatasetKind
from whsizing.schemas.project import InputSpec

DATASETS: tuple[DatasetKind, ...] = ("order_lines", "sku_master", "inventory", "receipts")
RAW_ROW_RULES = ("REQ", "R1", "R3", "R4", "R5", "R6", "R8")  # see the module docstring
SNIFF_FIELDS = ("encoding", "delimiter", "header_row", "decimal", "date_format")
_UNIT_CODES = {"dims": ("W_UNITS_DIMS", "mm", "× 10"), "weight": ("W_UNITS_WEIGHT", "kg", "÷ 1000")}


def expand_files(files: list[Path]) -> list[Path]:
    """Glob patterns (e.g. data/stock_*.csv) → sorted matches; a path that exists, or has no glob
    character, is a plain path whatever characters it holds (`client [2025]/stock.csv`, I75 i). In
    a pattern, the leading folders that exist as written are literal (`client [2025]/*/x.csv`)."""
    out: list[Path] = []
    for f in files:
        if f.exists() or not glob.has_magic(str(f)):
            out.append(f)
            continue
        parts = f.parts
        n = 0  # leading parts that are a folder as written (the last part is the pattern)
        while n < len(parts) - 1 and Path(*parts[: n + 1]).is_dir():
            n += 1
        pattern = os.path.join(glob.escape(str(Path(*parts[:n]))), *parts[n:]) if n else str(f)
        matches = sorted(glob.glob(pattern))
        if not matches:
            raise MappingError(f"no file matches {f}")
        out += [Path(m) for m in matches]
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _saved_mapping(ds: DatasetKind, out_dir: Path, given: Path | None = None) -> Mapping | None:
    """The given mapping file, else the one persisted in out_dir/mapping/ (step 7), else None."""
    path = given or out_dir / "mapping" / f"{ds}.yaml"
    if not path.is_file():
        if given is not None:
            raise ConfigError(f"mapping file not found: {given}")
        return None
    mapping = load_mapping(path)
    if mapping.dataset != ds:
        raise ConfigError(f"{path}: mapping is for {mapping.dataset}, not {ds}")
    return mapping


def _unit_hints(
    df: pl.DataFrame, mapping: Mapping, confirm: Confirm | None
) -> tuple[pl.DataFrame, Mapping, list[str]]:
    """Step 6: hints not yet decided in the mapping are confirmed (then recorded) or reported."""
    hints, notes = dict(mapping.unit_hints), []
    for key, (unit, why) in detect_unit_hints(df).items():
        if key in hints:
            continue
        code, base, op = _UNIT_CODES[key]
        question = f"{code}: {why}; values look like {unit}. Convert to {base} ({op})?"
        if confirm is None:  # step 6: both hints require confirmation, as step 5 → exit 2
            raise MappingError(
                f"sku_master {code}: {why}; values look like {unit}. Confirm interactively, or "
                f"set unit_hints: {{{key}: {unit}}} (convert) or {{{key}: {base}}} (keep) in "
                "mapping/sku_master.yaml (written to the output folder) and re-run"
            )
        accepted = confirm(code, question)
        hints[key] = unit if accepted else base
        if accepted:
            df = apply_unit_hints(df, {key: unit})
            notes.append(
                f"[sku_master] {code}: {why}; confirmed as {unit} and converted to {base} ({op})."
            )
    return df, mapping.model_copy(update={"unit_hints": hints}), notes


def _read_dataset(
    ds: DatasetKind, spec: InputSpec, out_dir: Path, confirm: Confirm | None
) -> tuple[pl.DataFrame, Mapping, list[SourceFile], int, list[str]]:
    saved = _saved_mapping(ds, out_dir, spec.mapping)
    raws = [read_any(p, spec.sheet, saved) for p in expand_files(spec.files)]
    if not raws:
        raise MappingError(f"{ds}: no input file")
    if not any(r.df.height for r in raws):
        names = ", ".join(r.path.name for r in raws)
        raise MappingError(f"{ds} ({names}): no data rows below the header row")
    if saved is None:
        mapping = resolve_mapping(suggest_mapping(raws[0], ds), raws[0], confirm)
        # sniff fields the files disagree on stay None (each file keeps its own sniff, now and
        # on the next ingest); an auto-picked sheet is not recorded (step 6: unless specified)
        agreed = {
            k: getattr(raws[0].sniff, k) if len({getattr(r.sniff, k) for r in raws}) == 1 else None
            for k in SNIFF_FIELDS
        }
        if any(r.sniff.decimal_by_delimiter for r in raws):
            # I67 step 4: the delimiter's choice is no decision; it stays unrecorded, so each
            # ingest warns again (tie_break_notes) until decimal: is set in the mapping
            agreed["decimal"] = None
        mapping = mapping.model_copy(update={**agreed, "sheet": spec.sheet})
    else:
        mapping = saved
    mapping = mapping.model_copy(update={"files": [str(r.path) for r in raws]})
    df = pl.concat([apply_mapping(r, mapping) for r in raws], how="vertical_relaxed")
    notes = [n for r in raws for n in number_notes(r, mapping)]
    notes += [n for r in raws for n in tie_break_notes(r, mapping)]
    notes += [n for r in raws for n in duplicate_header_notes(r, mapping)]
    if ds == "sku_master":
        try:
            df, mapping, hint_notes = _unit_hints(df, mapping, confirm)
            notes += hint_notes
        except MappingError:  # write the mapping so the unit decision can be added to it
            save_mapping(mapping, out_dir / "mapping" / f"{ds}.yaml")
            raise
    files = [
        SourceFile(
            path=str(r.path),
            sha256=_sha256(r.path),
            size_bytes=r.path.stat().st_size,
            n_rows=r.df.height,
            sniff=r.sniff,
        )
        for r in raws
    ]
    return df, mapping, files, sum(r.df.height for r in raws), notes


def _existing(
    out_dir: Path, skip: set[str]
) -> tuple[CanonicalFrames, list[DatasetIngest], list[RuleResult], list[str]]:
    """Canonical frames of an earlier ingest, with their manifest entries, raw-row rule
    results and notes from the earlier DQ report."""
    frames = {
        ds: read_parquet_file(p)
        for ds in DATASETS
        if ds not in skip and (p := out_dir / "canonical" / f"{ds}.parquet").is_file()
    }
    manifest_path, report_path = out_dir / "dq" / MANIFEST, out_dir / "dq" / DQ_JSON
    entries, rules, notes = [], [], []
    if manifest_path.is_file():
        old = IngestManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        entries = [d for d in old.datasets if d.dataset in frames]
    if report_path.is_file():
        report = DQReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        rules = [r for r in report.rules if r.dataset in frames and r.rule in RAW_ROW_RULES]
        notes = [n for n in report.notes if any(n.startswith(f"[{ds}]") for ds in frames)]
    return frames, entries, rules, notes


def ingest(
    inputs: MappingT[str, InputSpec | None],
    out_dir: Path,
    salt: bytes,
    *,
    confirm: Confirm | None = None,
    keep_descriptions: bool = False,
    now: datetime | None = None,
    default_units_per_pallet: int = DEFAULT_UNITS_PER_PALLET,
) -> IngestManifest:
    """Read, map, anonymise, validate (R1-R14) and write the canonical tables.

    `confirm(code, question) -> bool` answers suggested mappings (`mapping.<target>`) and unit
    hints (`W_UNITS_DIMS`, `W_UNITS_WEIGHT`); None = non-interactive (nothing is assumed).
    Raises MappingError (exit 2) for unmapped required columns and DataQualityError (exit 3)
    after writing dq/ when a blocking rule fires; canonical/ is written only without one.
    """
    out_dir = Path(out_dir)
    new: CanonicalFrames = {}
    meta: dict[DatasetKind, tuple[list[SourceFile], str, int, int]] = {}
    notes: list[str] = []
    lines_mapping: Mapping | None = None
    unknown = sorted(set(inputs) - set(DATASETS))
    if unknown:
        raise ConfigError(f"ingest: unknown dataset(s) {unknown}; expected {list(DATASETS)}")
    for name, spec in inputs.items():
        if spec is None:
            continue
        ds = cast(DatasetKind, name)
        df, mapping, files, rows_in, hint_notes = _read_dataset(ds, spec, out_dir, confirm)
        mapping_hash = save_mapping(mapping, out_dir / "mapping" / f"{ds}.yaml")
        filtered = sum(f.n_rows for f in files) - df.height
        meta[ds] = (files, mapping_hash, rows_in, filtered)
        new[ds], notes = df, notes + hint_notes
        if ds == "order_lines":
            lines_mapping = mapping
    if not new:
        raise ConfigError("ingest: no input files given")
    # order lines reloaded from an earlier ingest keep that ingest's zone and merge setting
    lines_mapping = lines_mapping or _saved_mapping("order_lines", out_dir)
    tz, merge = (
        (lines_mapping.timezone, lines_mapping.merge_duplicate_sku_lines)
        if lines_mapping
        else ("Europe/Paris", True)
    )
    old_frames, old_entries, old_rules, old_notes = _existing(out_dir, set(new))
    frames = {**old_frames, **anonymize(new, salt, keep_descriptions)}
    frames, rules = apply_rules(frames, merge_duplicate_sku_lines=merge, timezone=tz, now=now)
    earlier = {(r.rule, r.dataset): r for r in old_rules}
    rules = [earlier.get((r.rule, r.dataset), r) for r in rules]
    frames = derive(frames, default_units_per_pallet)
    report = build_dq_report(rules, frames, old_notes + notes, timezone=tz)
    entries = old_entries + [
        DatasetIngest(
            dataset=ds,
            files=files,
            mapping_hash=mapping_hash,
            rows_in=rows_in,
            rows_out=frames[ds].height,
            dropped_by_rule=({"filter": filtered} if filtered else {})
            | {r.rule: r.dropped for r in rules if r.dataset == ds and r.dropped},
        )
        for ds, (files, mapping_hash, rows_in, filtered) in meta.items()
    ]
    manifest = make_manifest(entries, report.coverage, report.score)
    write_dq_report(report, out_dir, entries)
    blocking = [r for r in rules if r.severity == "blocking"]
    if blocking:
        write_manifest(manifest, out_dir)
        detail = "; ".join(f"{r.rule} ({r.dataset}): {r.message}" for r in blocking)
        raise DataQualityError(
            f"{len(blocking)} blocking data-quality issue(s): {detail}. "
            f"See {out_dir / 'dq' / 'dq_report.html'}"
        )
    get_logger().info("ingest_done", datasets=list(meta), dq_score=report.score, band=report.band)
    return write_canonical(frames, out_dir, manifest, tz)
