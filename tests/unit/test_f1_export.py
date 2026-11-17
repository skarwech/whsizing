"""F1 step 8: Parquet + CSV EN/FR exports (formats, headers, local time)."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
import pytest

from whsizing.errors import ConfigError
from whsizing.schemas.frames import OrderLines
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
TINY = ROOT / "data" / "synth" / "profiles" / "tiny_golden.yaml"

# Appendix F synonyms (excerpt), used to check every exported header maps exactly.
SYNONYMS = {
    "order_id": "order id, order, order number, order no, commande, n commande, num commande, "
    "no commande, numero commande, bl, order ref, reference commande",
    "order_ts": "order date, order time, date, date commande, date de commande, created at, "
    "creation date, date creation, timestamp, release date, date liberation",
    "sku": "sku, item, item code, article, code article, reference, ref, product id, "
    "product code, ean, gtin",
    "qty_units": "qty, quantity, quantite, qte, units, nb pieces, pcs, pieces, qty shipped, "
    "qte expediee",
    "channel": "channel, canal, customer type, type client, sales channel",
    "line_status": "status, statut, etat, line status",
    "length_mm": "length, longueur, long, l, len",
    "width_mm": "width, largeur, larg, w",
    "height_mm": "height, hauteur, haut, h",
    "weight_kg": "weight, poids, poids unitaire, unit weight, kg",
    "units_per_case": "pcb, units per case, colisage, uc par colis, case pack, pack size",
    "cases_per_pallet": "cases per pallet, colis par palette, cartons par palette, pal",
    "snapshot_date": "date stock, stock date, date inventaire, as of",
    "receipt_id": "receipt, reception, asn, po, bon de reception",
    "receipt_ts": "receipt date, date reception, delivered on",
    "pallets": "pallets, palettes, nb palettes",
}
FR_ORDER_HEADERS = ["N° commande", "Date commande", "Référence", "Qté", "Canal", "Statut"]
FR_SKU_HEADERS = [
    "Référence",
    "Longueur",
    "Largeur",
    "Hauteur",
    "Poids",
    "PCB",
    "Colis par palette",
    "Catégorie",
]


def _normalize(h: str) -> str:
    """F2 mapping step 1: NFKD, strip accents, lower-case, non-alphanumerics → space."""
    s = "".join(c for c in unicodedata.normalize("NFKD", h) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s.lower()).split())


@pytest.fixture(scope="module")
def frames() -> dict[str, pl.DataFrame]:
    return generate(load_synth_profile(TINY), seed=42)


@pytest.fixture(scope="module")
def out(frames: dict[str, pl.DataFrame], tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("synth")
    paths = export(frames, out)
    assert len(paths) == 12
    return out


def _rows(path: Path, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_text(encoding="utf-8")), delimiter=delimiter))


def test_fr_csv_delimiter_headers_and_encoding(out: Path) -> None:
    raw = (out / "csv_fr" / "order_lines.csv").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # clean export: plain UTF-8
    first = raw.decode("utf-8").splitlines()[0]
    assert first == ";".join(FR_ORDER_HEADERS)
    assert _rows(out / "csv_fr" / "sku_master.csv", ";")[0] == FR_SKU_HEADERS
    assert _rows(out / "csv_fr" / "inventory.csv", ";")[0] == ["Référence", "Qté", "Date stock"]


def test_fr_csv_decimal_comma(out: Path, frames: dict[str, pl.DataFrame]) -> None:
    rows = _rows(out / "csv_fr" / "sku_master.csv", ";")[1:]
    sku = frames["sku_master"]
    assert all("." not in v for r in rows for v in r[1:5])
    assert any("," in r[4] for r in rows)  # weights have decimals
    parsed = [float(r[1].replace(",", ".")) for r in rows]
    assert parsed == sku["length_mm"].to_list()


def test_fr_csv_dates_are_paris_wall_time(out: Path, frames: dict[str, pl.DataFrame]) -> None:
    rows = _rows(out / "csv_fr" / "order_lines.csv", ";")[1:]
    assert all(re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", r[1]) for r in rows)
    paris = frames["order_lines"]["order_ts"].dt.convert_time_zone("Europe/Paris")
    assert [r[1] for r in rows] == paris.dt.strftime("%d/%m/%Y %H:%M").to_list()
    inv = _rows(out / "csv_fr" / "inventory.csv", ";")[1:]
    assert {r[2] for r in inv} == {"31/03/2025"}


def test_en_csv_iso_timestamps_with_offset(out: Path, frames: dict[str, pl.DataFrame]) -> None:
    rows = _rows(out / "csv_en" / "order_lines.csv", ",")
    assert rows[0] == ["Order Number", "Order Date", "SKU", "Quantity", "Channel", "Line Status"]
    stamps = pl.Series([r[1] for r in rows[1:]])
    assert stamps.str.contains(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+0[12]:00$").all()
    parsed = stamps.str.to_datetime("%Y-%m-%dT%H:%M:%S%:z", time_unit="us", time_zone="UTC")
    assert parsed.to_list() == frames["order_lines"]["order_ts"].to_list()
    sku_rows = _rows(out / "csv_en" / "sku_master.csv", ",")
    assert float(sku_rows[1][1]) == frames["sku_master"]["length_mm"][0]


def test_every_csv_header_is_an_appendix_f_synonym(out: Path) -> None:
    from whsizing.synth.export import HEADERS

    synonyms = {t: {s.strip() for s in v.split(",")} for t, v in SYNONYMS.items()}
    for lang, tables in HEADERS.items():
        for table, headers in tables.items():
            written = _rows(out / f"csv_{lang}" / f"{table}.csv", "," if lang == "en" else ";")[0]
            assert written == list(headers.values())
            for target, header in headers.items():
                if target in synonyms:  # `category` has no synonym (optional column)
                    assert _normalize(header) in synonyms[target], (lang, table, header)


def test_csv_has_no_provenance_or_derived_columns(out: Path) -> None:
    header = _rows(out / "csv_en" / "sku_master.csv", ",")[0]
    assert "units_per_pallet" not in header and "unit_cube_m3" not in header
    assert len(_rows(out / "csv_en" / "order_lines.csv", ",")[0]) == 6


def test_parquet_is_canonical_with_local_tz_metadata(out: Path) -> None:
    meta = pq.read_metadata(out / "order_lines.parquet").metadata
    assert meta[b"local_tz"] == b"Europe/Paris"
    lines = pl.read_parquet(out / "order_lines.parquet")
    OrderLines.validate(lines)
    assert lines.schema["order_ts"] == pl.Datetime("us", "UTC")


def test_export_rejects_unknown_format(frames: dict[str, pl.DataFrame], tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="xlsx"):
        export(frames, tmp_path, formats=("parquet", "xlsx"))


def test_shim_cli_writes_all_formats(tmp_path: Path) -> None:
    import runpy

    shim = runpy.run_path(str(ROOT / "data" / "synth" / "generator.py"))
    code = shim["main"]([str(TINY), "--out", str(tmp_path), "--seed", "42"])
    assert code == 0
    assert (tmp_path / "order_lines.parquet").exists()
    assert (tmp_path / "csv_fr" / "receipts.csv").exists()
    assert shim["main"]([str(tmp_path / "nope.yaml"), "--out", str(tmp_path)]) == 2
    assert shim["main"]([str(TINY), "--out", str(tmp_path / "neg"), "--seed", "-1"]) == 2
    assert not (tmp_path / "neg").exists()


# T1.4 (FR CSV re-ingests through F2 with zero blocking issues) lives with F2:
# tests/e2e/test_f2_ingest.py::test_T1_4_fr_csv_reingests_with_zero_blocking_issues
