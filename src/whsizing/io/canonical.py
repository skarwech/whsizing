"""Canonical frames: derived columns, Pandera validation (§4.1), Parquet + ingest manifest."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandera.errors
import polars as pl

from whsizing import __version__
from whsizing.errors import WhsizingError
from whsizing.io.rules import CanonicalFrames
from whsizing.schemas.frames import Inventory, OrderLines, Receipts, SkuMaster
from whsizing.schemas.manifest import DatasetIngest, IngestManifest

# [P] catalog/storage_classes.yaml `default_units_per_pallet` (Appendix D); the share of SKUs
# using it is reported as coverage["units_per_pallet_default_share"].
DEFAULT_UNITS_PER_PALLET = 400
SCHEMAS = {
    "order_lines": OrderLines,
    "sku_master": SkuMaster,
    "inventory": Inventory,
    "receipts": Receipts,
}
MANIFEST = "ingest_manifest.json"


def derive(
    frames: CanonicalFrames, default_units_per_pallet: int = DEFAULT_UNITS_PER_PALLET
) -> CanonicalFrames:
    """sku_master: units_per_pallet (case × cases/pallet, else default), unit_cube_m3 (mm³ →
    m³); receipts: missing pallets = qty / units_per_pallet of the SKU."""
    out = dict(frames)
    master = out.get("sku_master")
    if master is not None:
        upp = (pl.col("units_per_case") * pl.col("cases_per_pallet")).fill_null(
            default_units_per_pallet
        )
        cube = pl.col("length_mm") * pl.col("width_mm") * pl.col("height_mm") / 1e9
        out["sku_master"] = master = master.with_columns(units_per_pallet=upp, unit_cube_m3=cube)
    receipts = out.get("receipts")
    if receipts is not None:
        lookup = (
            master.select("sku", "units_per_pallet")
            if master is not None
            else pl.DataFrame(schema={"sku": pl.Utf8, "units_per_pallet": pl.Int64})
        )
        upp_r = pl.col("sku").replace_strict(
            lookup["sku"], lookup["units_per_pallet"], default=default_units_per_pallet
        )
        out["receipts"] = receipts.with_columns(
            pallets=pl.col("pallets").fill_null(pl.col("qty_units") / upp_r)
        )
    return out


def validate(frames: CanonicalFrames) -> CanonicalFrames:
    """Pandera column checks; a failure here is an F2 bug or a hand-built table (rules should
    have cleaned it), so WhsizingError (exit 1), never the R-rules' exit 3. Missing required
    columns are checked first: pandera coerces before it checks presence, so polars'
    ColumnNotFoundError escaped for coerced columns (F2e)."""
    out: CanonicalFrames = {}
    for name, df in frames.items():
        if name not in SCHEMAS:
            raise WhsizingError(f"unknown canonical table {name!r} (known: {list(SCHEMAS)})")
        columns = SCHEMAS[name].to_schema().columns.items()
        missing = [c for c, col in columns if col.required and c not in df.columns]
        if missing:
            wording = "; ".join(f'cannot find column "{c}" (required by §4.1)' for c in missing)
            raise WhsizingError(f"canonical {name}: {wording}")  # I72: the one wording
        try:
            out[name] = SCHEMAS[name].validate(df)
        except (pandera.errors.SchemaError, pandera.errors.SchemaErrors) as e:
            raise WhsizingError(f"canonical {name} failed schema validation: {e}") from e
    return out


def make_manifest(
    datasets: Sequence[DatasetIngest], coverage: dict[str, float], dq_score: float
) -> IngestManifest:
    return IngestManifest(
        tool_version=__version__,
        created_at=datetime.now(UTC),
        datasets=list(datasets),
        coverage=coverage,
        dq_score=dq_score,
        anonymized=True,
    )


def write_manifest(manifest: IngestManifest, out_dir: Path) -> Path:
    path = Path(out_dir) / "dq" / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return path


def write_canonical(
    frames: CanonicalFrames,
    out_dir: Path,
    manifest: IngestManifest,
    timezone: str = "Europe/Paris",
) -> IngestManifest:
    """Validate, write `canonical/<table>.parquet` (zone in metadata, §3.5) and the manifest."""
    valid = validate(frames)
    canonical = Path(out_dir) / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    for name, df in valid.items():
        df.write_parquet(canonical / f"{name}.parquet", metadata={"local_tz": timezone})
    write_manifest(manifest, out_dir)
    return manifest
