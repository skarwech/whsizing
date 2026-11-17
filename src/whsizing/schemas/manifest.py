"""RunManifest and IngestManifest (§2.5, F2 'Ingest manifest')."""

from __future__ import annotations

from datetime import datetime

from whsizing.schemas.params import DatasetKind, StrictModel


class RunManifest(StrictModel):
    run_id: str
    created_at: datetime
    engine_version: str
    git_sha: str
    catalog_version: str
    inputs: dict[str, str]  # path → sha256
    basis_hash: str
    scenarios_hash: str
    mapping_hashes: dict[str, str]
    params_snapshot: dict[str, float]  # every param value used (typ after overrides)
    seed: int
    python: str
    platform: str
    packages: dict[str, str]
    timings: dict[str, float] = {}  # stage → duration_s (C5 budget), from logging.stage_timer
    # I75 b: sha256 of the normalised project model (paths left out), checked by `rerun`;
    # None in manifests written before it existed
    project_hash: str | None = None


class SniffResult(StrictModel):
    """F2 sniffing outcome for one source file."""

    encoding: str
    delimiter: str | None  # None for Excel / Parquet
    header_row: int  # 1-based
    decimal: str  # "." or ","
    date_format: str | None
    n_rows: int
    sheet: str | None = None
    # I67 step 4: True when no value showed the mark and the field delimiter chose it (I54
    # tie-break); False when the values or a saved mapping decided, and for Excel / Parquet.
    decimal_by_delimiter: bool = False


class SourceFile(StrictModel):
    path: str
    sha256: str
    size_bytes: int
    n_rows: int
    sniff: SniffResult


class DatasetIngest(StrictModel):
    dataset: DatasetKind
    files: list[SourceFile]
    mapping_hash: str
    rows_in: int
    rows_out: int
    dropped_by_rule: dict[str, int] = {}  # rule id (R1..R14) → rows dropped


class IngestManifest(StrictModel):
    tool_version: str
    created_at: datetime
    datasets: list[DatasetIngest]
    coverage: dict[str, float]  # e.g. dims_coverage_lines, orphan_sku_share
    dq_score: float
    anonymized: bool
