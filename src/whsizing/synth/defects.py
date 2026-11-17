"""F1 step 9: defect injector for the CSV exports (the Parquet stays canonical).

Row-level defects act on the typed frames (`inject_defects`); format-level defects (mixed date
formats, thousand separators, second header row, BOM, cp1252) are applied while rendering the
CSV in `whsizing.synth.export`, using the helpers below. Each defect draws from its own random
stream, so switching one on or off never moves the rows another one hits.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from whsizing.synth.generator import _hex_ids  # pyright: ignore[reportPrivateUsage]
from whsizing.synth.profile import DefectCfg

DIMS = ("length_mm", "width_mm", "height_mm")
ID_COLUMNS = ("sku", "order_id")
ALT_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M")
ALT_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y")
_STREAM = {  # one random stream per defect
    "missing_dims": 1,
    "cm_instead_of_mm": 2,
    "orphan_skus": 3,
    "negative_quantities": 4,
    "trailing_spaces": 5,
    "duplicate_rows": 6,
    "mixed_date_formats": 7,
    "second_header_row": 8,
}


def defect_rng(seed: int, defect: str) -> np.random.Generator:
    return np.random.default_rng([seed, _STREAM[defect]])


def _mask(rng: np.random.Generator, n: int, share: float) -> pl.Series:
    return pl.Series(rng.random(n) < share)


def inject_defects(
    frames: dict[str, pl.DataFrame], cfg: DefectCfg, seed: int = 42
) -> dict[str, pl.DataFrame]:
    """Return new frames with the row-level defects switched on in `cfg`."""
    out = dict(frames)
    if cfg.missing_dims and "sku_master" in out:
        df = out["sku_master"]
        m = _mask(defect_rng(seed, "missing_dims"), df.height, cfg.missing_dims_share)
        out["sku_master"] = df.with_columns(
            pl.when(m).then(None).otherwise(pl.col(DIMS)).name.keep()
        )
    if cfg.cm_instead_of_mm and "sku_master" in out:
        df = out["sku_master"]
        m = _mask(defect_rng(seed, "cm_instead_of_mm"), df.height, cfg.cm_rows_share)
        out["sku_master"] = df.with_columns(
            pl.when(m).then((pl.col(DIMS) / 10).round(2)).otherwise(pl.col(DIMS))
        )
    if cfg.orphan_skus and "order_lines" in out:
        out["order_lines"] = _orphans(
            out["order_lines"], out.get("sku_master"), cfg.orphan_skus_share, seed
        )
    if cfg.negative_quantities:
        out = _negatives(out, cfg.negative_qty_share, seed)
    if cfg.trailing_spaces:
        rng = defect_rng(seed, "trailing_spaces")
        for name, df in out.items():
            m = _mask(rng, df.height, cfg.trailing_spaces_share)
            cols = [c for c in ID_COLUMNS if c in df.columns]
            out[name] = df.with_columns(
                pl.when(m).then(pl.col(cols) + "  ").otherwise(pl.col(cols))
            )
    if cfg.duplicate_rows and "order_lines" in out:
        df = out["order_lines"]
        m = _mask(defect_rng(seed, "duplicate_rows"), df.height, cfg.duplicate_rows_share)
        # copies sit right after their original (stable sort on the provenance row)
        out["order_lines"] = pl.concat([df, df.filter(m)]).sort("source_row", maintain_order=True)
    return out


def _orphans(
    df: pl.DataFrame, master: pl.DataFrame | None, share: float, seed: int
) -> pl.DataFrame:
    """Replace the SKU of `share` of lines by fresh 16-hex ids absent from the master."""
    rng = defect_rng(seed, "orphan_skus")
    m = rng.random(df.height) < share
    n = int(m.sum())
    known = (master if master is not None else df)["sku"].to_numpy()
    candidates = _hex_ids(n + 16, rng.integers(0, 2**64, dtype=np.uint64))
    fresh = candidates[~np.isin(candidates, known)][:n]
    sku = df["sku"].to_numpy().copy()
    sku[m] = fresh
    return df.with_columns(sku=pl.Series(sku, dtype=pl.Utf8))


def _negatives(frames: dict[str, pl.DataFrame], share: float, seed: int) -> dict[str, pl.DataFrame]:
    """Sign errors: shipped order lines and inventory rows with a negated quantity."""
    rng = defect_rng(seed, "negative_quantities")
    out = dict(frames)
    if "order_lines" in out:
        df = out["order_lines"]
        hit = _mask(rng, df.height, share) & (pl.col("line_status") == "shipped")
        out["order_lines"] = df.with_columns(
            qty_units=pl.when(hit).then(-pl.col("qty_units")).otherwise(pl.col("qty_units"))
        )
    if "inventory" in out:
        df = out["inventory"]
        hit = _mask(rng, df.height, share)
        out["inventory"] = df.with_columns(
            qty_units=pl.when(hit).then(-pl.col("qty_units")).otherwise(pl.col("qty_units"))
        )
    return out


def mixed_dates(
    col: pl.Expr,
    base_fmt: str,
    alt_fmts: tuple[str, ...],
    n: int,
    share: float,
    rng: np.random.Generator,
) -> pl.Expr:
    """String-format `col` with `base_fmt`, except `share` of rows in a random alternative."""
    alt_fmts = tuple(f for f in alt_fmts if f != base_fmt)
    pick = pl.Series(np.where(rng.random(n) < share, rng.integers(1, len(alt_fmts) + 1, n), 0))
    out = col.dt.strftime(base_fmt)
    for i, fmt in enumerate(alt_fmts, start=1):
        out = pl.when(pl.lit(pick) == i).then(col.dt.strftime(fmt)).otherwise(out)
    return out


def group_thousands(col: pl.Expr, sep: str) -> pl.Expr:
    """Integer → string with `sep` between groups of 3 digits (|x| < 10¹²): 1234567 → 1,234,567."""
    a = col.abs()

    def part(k: int) -> pl.Expr:
        return ((a // 10 ** (3 * k)) % 1000).cast(pl.Utf8).str.zfill(3)

    def head(k: int) -> pl.Expr:
        return (a // 10 ** (3 * k)).cast(pl.Utf8)

    digits = (
        pl.when(a >= 10**9)
        .then(pl.concat_str([head(3), part(2), part(1), part(0)], separator=sep))
        .when(a >= 10**6)
        .then(pl.concat_str([head(2), part(1), part(0)], separator=sep))
        .when(a >= 10**3)
        .then(pl.concat_str([head(1), part(0)], separator=sep))
        .otherwise(a.cast(pl.Utf8))
    )
    return pl.when(col < 0).then(pl.lit("-") + digits).otherwise(digits)
