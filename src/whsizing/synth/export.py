"""F1 step 8: export canonical frames to Parquet and to client-like CSV files (EN and FR).

Parquet: canonical names and dtypes, UTC timestamps, `local_tz` in the file metadata (§3.5).
CSV EN: Appendix F English headers, ',' delimiter, ISO 8601 Paris time with offset.
CSV FR: Appendix F French headers, ';' delimiter, decimal comma, 'dd/mm/yyyy HH:MM' Paris time.
CSVs simulate client extracts: provenance and derived columns (source_*, units_per_pallet,
unit_cube_m3) are left for F2 to fill. Defects (step 9) apply to the CSVs only.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import polars as pl

from whsizing.errors import ConfigError
from whsizing.synth.defects import (
    ALT_DATE_FORMATS,
    ALT_DATETIME_FORMATS,
    defect_rng,
    group_thousands,
    inject_defects,
    mixed_dates,
)
from whsizing.synth.generator import generate
from whsizing.synth.profile import LOCAL_TZ, DefectCfg, load_synth_profile

FORMATS = ("parquet", "csv_en", "csv_fr")
HEADERS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "order_lines": {
            "order_id": "Order Number",
            "order_ts": "Order Date",
            "sku": "SKU",
            "qty_units": "Quantity",
            "channel": "Channel",
            "line_status": "Line Status",
        },
        "sku_master": {
            "sku": "SKU",
            "length_mm": "Length",
            "width_mm": "Width",
            "height_mm": "Height",
            "weight_kg": "Weight",
            "units_per_case": "Units per Case",
            "cases_per_pallet": "Cases per Pallet",
            "category": "Category",
        },
        "inventory": {"sku": "SKU", "qty_units": "Quantity", "snapshot_date": "Stock Date"},
        "receipts": {
            "receipt_id": "Receipt",
            "receipt_ts": "Receipt Date",
            "sku": "SKU",
            "qty_units": "Quantity",
            "pallets": "Pallets",
        },
    },
    "fr": {
        "order_lines": {
            "order_id": "N° commande",
            "order_ts": "Date commande",
            "sku": "Référence",
            "qty_units": "Qté",
            "channel": "Canal",
            "line_status": "Statut",
        },
        "sku_master": {
            "sku": "Référence",
            "length_mm": "Longueur",
            "width_mm": "Largeur",
            "height_mm": "Hauteur",
            "weight_kg": "Poids",
            "units_per_case": "PCB",
            "cases_per_pallet": "Colis par palette",
            "category": "Catégorie",
        },
        "inventory": {"sku": "Référence", "qty_units": "Qté", "snapshot_date": "Date stock"},
        "receipts": {
            "receipt_id": "Bon de réception",
            "receipt_ts": "Date réception",
            "sku": "Référence",
            "qty_units": "Qté",
            "pallets": "Palettes",
        },
    },
}
DATETIME_FORMAT = {"en": "%Y-%m-%dT%H:%M:%S%:z", "fr": "%d/%m/%Y %H:%M"}
DATE_FORMAT = {"en": "%Y-%m-%d", "fr": "%d/%m/%Y"}
SEPARATOR = {"en": ",", "fr": ";"}
THOUSANDS = {"en": ",", "fr": "."}


def export(
    frames: dict[str, pl.DataFrame],
    out_dir: Path | str,
    formats: Sequence[str] = FORMATS,
    defects: DefectCfg | None = None,
    seed: int = 42,
) -> list[Path]:
    """Write `<out>/<table>.parquet`, `<out>/csv_en/<table>.csv`, `<out>/csv_fr/<table>.csv`."""
    unknown = set(formats) - set(FORMATS)
    if unknown:
        raise ConfigError(f"unknown export format(s) {sorted(unknown)}; expected {FORMATS}")
    out_dir = Path(out_dir)
    cfg = defects or DefectCfg()
    csv_frames = inject_defects(frames, cfg, seed) if defects else frames
    csvs = {  # rendered before the first write: a rendering error leaves no partial output
        Path(fmt, f"{name}.csv"): render_csv(df, name, fmt.removeprefix("csv_"), cfg, seed)
        for fmt in formats
        if fmt.startswith("csv_")
        for name, df in csv_frames.items()
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if "parquet" in formats:
        for name, df in frames.items():
            path = out_dir / f"{name}.parquet"
            df.write_parquet(path, metadata={"local_tz": LOCAL_TZ})
            paths.append(path)
    for rel, data in csvs.items():
        path = out_dir / rel
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        paths.append(path)
    return paths


def render_csv(df: pl.DataFrame, table: str, lang: str, cfg: DefectCfg, seed: int = 42) -> bytes:
    """One table as client-like CSV bytes in `lang` ('en' | 'fr'), with `cfg`'s format defects."""
    headers = HEADERS[lang][table]
    cols = [c for c in headers if c in df.columns]
    rendered = df.select(_render_column(df, c, lang, cfg, seed) for c in cols).rename(
        headers, strict=False
    )
    opts = {"separator": SEPARATOR[lang], "decimal_comma": lang == "fr"}
    if cfg.second_header_row and rendered.height > 1:
        cut = int(defect_rng(seed, "second_header_row").integers(1, rendered.height))
        text = rendered.head(cut).write_csv(**opts) + rendered.slice(cut).write_csv(**opts)
    else:
        text = rendered.write_csv(**opts)
    if not cfg.cp1252:
        return text.encode("utf-8-sig" if cfg.bom else "utf-8")
    try:  # cp1252 wins over `bom`: a UTF-8 BOM in a cp1252 file is contradictory
        return text.encode("cp1252")
    except UnicodeEncodeError as e:
        bad = e.object[e.start : e.end]
        raise ConfigError(
            f"cp1252 defect: {table} contains {bad!r}, which cp1252 cannot encode "
            "(check the profile's channel names)"
        ) from e


def _render_column(df: pl.DataFrame, c: str, lang: str, cfg: DefectCfg, seed: int) -> pl.Expr:
    dtype = df.schema[c]
    if isinstance(dtype, pl.Datetime):
        col = pl.col(c).dt.convert_time_zone(LOCAL_TZ)
        return _dates(col, DATETIME_FORMAT[lang], ALT_DATETIME_FORMATS, df.height, cfg, seed, c)
    if dtype == pl.Date:
        return _dates(pl.col(c), DATE_FORMAT[lang], ALT_DATE_FORMATS, df.height, cfg, seed, c)
    if dtype.is_integer() and cfg.thousand_separators:
        return group_thousands(pl.col(c), THOUSANDS[lang]).alias(c)
    if dtype == pl.Categorical:
        return pl.col(c).cast(pl.Utf8)
    return pl.col(c)


def _dates(
    col: pl.Expr, fmt: str, alts: tuple[str, ...], n: int, cfg: DefectCfg, seed: int, name: str
) -> pl.Expr:
    if not cfg.mixed_date_formats:
        return col.dt.strftime(fmt).alias(name)
    rng = defect_rng(seed, "mixed_date_formats")
    return mixed_dates(col, fmt, alts, n, cfg.mixed_dates_share, rng).alias(name)


def synthesize(
    profile_path: Path | str, out_dir: Path | str, seed: int = 42, defects: bool = False
) -> list[Path]:
    """Profile YAML → generated frames → Parquet + CSV EN/FR (`whsizing synth`, data/synth shim).
    With `defects`, the profile's `defects` section is injected into the CSVs."""
    profile = load_synth_profile(profile_path)
    frames = generate(profile, seed)
    return export(frames, out_dir, defects=profile.defects if defects else None, seed=seed)
