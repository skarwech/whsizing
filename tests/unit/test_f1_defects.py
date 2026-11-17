"""F1 step 9: each defect is injected when switched on, and only then."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import polars as pl
import pytest

from whsizing.errors import ConfigError
from whsizing.schemas.frames import Inventory, OrderLines, Receipts, SkuMaster
from whsizing.synth import DefectCfg, SynthProfile, export, generate, inject_defects, render_csv
from whsizing.synth.defects import group_thousands

TABLES = ("order_lines", "sku_master", "inventory", "receipts")
CLEAN = DefectCfg()


@pytest.fixture(scope="module")
def frames() -> dict[str, pl.DataFrame]:
    """~6,000 orders, 2,000 SKUs: enough rows to measure the defect shares."""
    p = SynthProfile(name="defects", n_skus=2000, start_date="2025-01-06", n_days=28)  # type: ignore[arg-type]
    return generate(p.model_copy(update={"orders_per_day_mean": 250}), seed=42)


def _text(df: pl.DataFrame, table: str, lang: str, cfg: DefectCfg) -> str:
    return render_csv(df, table, lang, cfg).decode("utf-8-sig")


def _rows(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def test_clean_config_injects_nothing(frames: dict[str, pl.DataFrame]) -> None:
    out = inject_defects(frames, CLEAN)
    for t in TABLES:
        assert out[t].equals(frames[t])


def test_bom(frames: dict[str, pl.DataFrame]) -> None:
    df = frames["inventory"]
    assert render_csv(df, "inventory", "fr", DefectCfg(bom=True)).startswith(b"\xef\xbb\xbf")
    assert not render_csv(df, "inventory", "fr", CLEAN).startswith(b"\xef\xbb\xbf")


def test_cp1252_encoding_wins_over_bom(frames: dict[str, pl.DataFrame]) -> None:
    raw = render_csv(frames["order_lines"], "order_lines", "fr", DefectCfg(cp1252=True, bom=True))
    assert not raw.startswith(b"\xef\xbb\xbf")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert raw.decode("cp1252").startswith("N° commande;Date commande;Référence;Qté")


def test_mixed_date_formats(frames: dict[str, pl.DataFrame]) -> None:
    cfg = DefectCfg(mixed_date_formats=True)
    rows = _rows(_text(frames["order_lines"], "order_lines", "fr", cfg), ";")[1:]
    base = re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}")
    alt = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}")
    n_alt = sum(bool(alt.fullmatch(r[1])) for r in rows)
    assert all(base.fullmatch(r[1]) or alt.fullmatch(r[1]) for r in rows)
    assert n_alt / len(rows) == pytest.approx(0.10, abs=0.02)
    clean = _rows(_text(frames["order_lines"], "order_lines", "fr", CLEAN), ";")[1:]
    assert all(base.fullmatch(r[1]) for r in clean)


def test_missing_dims(frames: dict[str, pl.DataFrame]) -> None:
    sku = inject_defects(frames, DefectCfg(missing_dims=True))["sku_master"]
    missing = sku["length_mm"].is_null()
    assert missing.mean() == pytest.approx(0.08, abs=0.02)
    assert (sku["width_mm"].is_null() == missing).all()
    assert sku["weight_kg"].null_count() == 0


def test_cm_instead_of_mm(frames: dict[str, pl.DataFrame]) -> None:
    before = frames["sku_master"]
    after = inject_defects(frames, DefectCfg(cm_instead_of_mm=True))["sku_master"]
    scaled = (after["length_mm"] - before["length_mm"] / 10).abs() < 1e-9
    assert scaled.mean() == pytest.approx(0.30, abs=0.03)
    assert ((after["height_mm"] == before["height_mm"]) | scaled).all()
    # a cm extract reads '5,06', not the float repr '5,0600000000000005'
    rows = _rows(_text(after, "sku_master", "fr", CLEAN), ";")[1:]
    assert all(re.fullmatch(r"\d+(,\d{1,2})?", v) for r in rows for v in r[1:4])


def test_cp1252_unencodable_text_raises_config_error_and_writes_nothing(tmp_path: Path) -> None:
    p = SynthProfile(
        name="nonlatin",
        n_skus=20,
        start_date="2025-01-06",  # type: ignore[arg-type]
        n_days=7,
        orders_per_day_mean=20,
        channel_shares={"B2C→web": 1.0},
    )
    out = tmp_path / "out"
    with pytest.raises(ConfigError, match="cp1252"):
        export(generate(p, seed=42), out, defects=DefectCfg(cp1252=True))
    assert not out.exists()


def test_orphan_skus(frames: dict[str, pl.DataFrame]) -> None:
    out = inject_defects(frames, DefectCfg(orphan_skus=True))
    orphan = ~out["order_lines"]["sku"].is_in(out["sku_master"]["sku"].implode())
    assert orphan.mean() == pytest.approx(0.02, abs=0.005)
    assert out["order_lines"]["sku"].str.contains(r"^[0-9a-f]{16}$").all()


def test_duplicate_rows(frames: dict[str, pl.DataFrame]) -> None:
    lines = frames["order_lines"]
    out = inject_defects(frames, DefectCfg(duplicate_rows=True))["order_lines"]
    extra = out.height - lines.height
    assert extra / lines.height == pytest.approx(0.005, abs=0.002)
    assert out.is_duplicated().sum() == 2 * extra  # exact copies
    assert out.unique(maintain_order=True).equals(lines)


def test_negative_quantities(frames: dict[str, pl.DataFrame]) -> None:
    out = inject_defects(frames, DefectCfg(negative_quantities=True))
    shipped = out["order_lines"].filter(pl.col("line_status") == "shipped")
    assert (shipped["qty_units"] < 0).mean() == pytest.approx(0.01, abs=0.004)
    assert (out["inventory"]["qty_units"] < 0).sum() > 0
    assert (frames["inventory"]["qty_units"] < 0).sum() == 0


def test_trailing_spaces(frames: dict[str, pl.DataFrame]) -> None:
    out = inject_defects(frames, DefectCfg(trailing_spaces=True))
    padded = out["order_lines"]["sku"].str.ends_with(" ")
    assert padded.mean() == pytest.approx(0.05, abs=0.01)
    assert (out["order_lines"]["sku"].str.strip_chars() == frames["order_lines"]["sku"]).all()
    assert out["inventory"]["sku"].str.ends_with(" ").sum() > 0
    rows = _rows(_text(out["order_lines"], "order_lines", "en", CLEAN), ",")
    assert any(r[2].endswith("  ") for r in rows[1:])


def test_thousand_separators(frames: dict[str, pl.DataFrame]) -> None:
    inv = frames["inventory"]
    cfg = DefectCfg(thousand_separators=True)
    fr = [r[1] for r in _rows(_text(inv, "inventory", "fr", cfg), ";")[1:]]
    en = [r[1] for r in _rows(_text(inv, "inventory", "en", cfg), ",")[1:]]
    assert any("." in v for v in fr) and any("," in v for v in en)
    assert all(re.fullmatch(r"-?\d{1,3}(\.\d{3})*", v) for v in fr)
    assert [int(v.replace(",", "")) for v in en] == inv["qty_units"].to_list()
    clean = [r[1] for r in _rows(_text(inv, "inventory", "fr", CLEAN), ";")[1:]]
    assert all(v.lstrip("-").isdigit() for v in clean)


def test_group_thousands_values() -> None:
    s = pl.Series("x", [0, 7, 999, 1000, -1234, 1234567, 1000000000, 123456789012])
    got = pl.select(group_thousands(pl.lit(s), ",")).to_series().to_list()
    assert got == [
        "0",
        "7",
        "999",
        "1,000",
        "-1,234",
        "1,234,567",
        "1,000,000,000",
        "123,456,789,012",
    ]


def test_second_header_row(frames: dict[str, pl.DataFrame]) -> None:
    df = frames["receipts"]
    lines = _text(df, "receipts", "fr", DefectCfg(second_header_row=True)).splitlines()
    assert len(lines) == df.height + 2
    assert lines.count(lines[0]) == 2
    assert 0 < lines.index(lines[0], 1) < len(lines) - 1  # repeated inside the data


def test_switches_are_independent(frames: dict[str, pl.DataFrame]) -> None:
    """Turning another defect on does not move the rows a defect hits."""
    alone = inject_defects(frames, DefectCfg(missing_dims=True))["sku_master"]
    combo = inject_defects(frames, DefectCfg(missing_dims=True, orphan_skus=True))["sku_master"]
    assert alone.equals(combo)


def test_export_with_defects_keeps_parquet_canonical(
    frames: dict[str, pl.DataFrame], tmp_path: Path
) -> None:
    every = DefectCfg(
        **{k: True for k, v in DefectCfg.model_fields.items() if v.annotation is bool}
    )
    export(frames, tmp_path, defects=every)
    OrderLines.validate(pl.read_parquet(tmp_path / "order_lines.parquet"))
    SkuMaster.validate(pl.read_parquet(tmp_path / "sku_master.parquet"))
    Inventory.validate(pl.read_parquet(tmp_path / "inventory.parquet"))
    Receipts.validate(pl.read_parquet(tmp_path / "receipts.parquet"))
    raw = (tmp_path / "csv_fr" / "order_lines.csv").read_bytes()
    assert raw.decode("cp1252").count("N° commande") == 2
