"""F2 sniffing and parsing: T2.1 encoding/delimiter, T2.2 header row, T2.3 decimals, T2.4 dates."""

from __future__ import annotations

import codecs
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from structlog.testing import capture_logs

from whsizing.errors import MappingError
from whsizing.io import read_any, sniff, suggest_mapping
from whsizing.io.parse import (
    detect_date_format,
    parse_bool,
    parse_datetime,
    parse_int,
    parse_number,
)
from whsizing.io.sniff import (
    WIDE_HEAD_BYTES,
    _wide_without_bom,
    detect_decimal,
    detect_delimiter,
    detect_encoding,
    detect_header_row,
    is_numeric_text,
)
from whsizing.schemas.ingest import Mapping

SNIFF = Path(__file__).resolve().parents[1] / "fixtures" / "ingest" / "sniff"
FR_HEADER = ["N° commande", "Date commande", "Référence", "Qté", "Canal", "Statut"]

# (fixture, accepted encodings, delimiter). Latin-1 and cp1252 decode every printable French
# character identically; only bytes 0x80-0x9F tell them apart, so either label is correct there.
T2_1_CASES = [
    ("utf8_semicolon.csv", {"utf-8"}, ";"),
    ("utf8_bom_comma.csv", {"utf-8-sig"}, ","),
    ("cp1252_semicolon.csv", {"cp1252"}, ";"),
    ("latin1_tab.csv", {"cp1252", "latin-1"}, "\t"),
    ("utf8_pipe.csv", {"utf-8"}, "|"),
    ("cp1252_comma_quoted.csv", {"cp1252"}, ","),
]


@pytest.mark.parametrize(("name", "encodings", "delimiter"), T2_1_CASES)
def test_T2_1_encoding_and_delimiter_detection(
    name: str, encodings: set[str], delimiter: str
) -> None:
    sn = sniff(SNIFF / name)
    assert sn.encoding in encodings
    assert sn.delimiter == delimiter
    raw = read_any(SNIFF / name)
    if name == "cp1252_comma_quoted.csv":
        assert raw.columns == ["Référence", "Désignation", "Prix €", "Poids"]
        assert raw.df["Désignation"].to_list()[:3] == [
            "Carton, grand modèle",
            "Boîte, petite",
            'Sac "kraft"',
        ]
    else:
        assert raw.columns == FR_HEADER
        assert raw.df["Référence"].to_list() == ["RÉF-001", "RÉF-002", "RÉF-à-003", "RÉF-001"]
        assert raw.df["Statut"].to_list()[2] == "annulé"


def test_T2_1_charset_normalizer_misreads_are_coerced_to_cp1252() -> None:
    """charset_normalizer labels short cp1252 French text iso8859_14 / cp1250, which turn '°'
    into 'Ḟ' and 'à' into 'ŕ'; the sniffer must not keep those labels."""
    text = "N° commande;Désignation;Qté\n" + "C1;Pâte à tartiner 750 g €;2\n" * 20
    assert detect_encoding(text.encode("cp1252")) == "cp1252"
    assert detect_encoding(text.encode("utf-8")) == "utf-8"
    assert detect_encoding(b"\xef\xbb\xbf" + text.encode("utf-8")) == "utf-8-sig"


def test_T2_1_utf16_unicode_text_export(tmp_path: Path) -> None:
    """Audit round 2: Excel's 'Unicode Text' (UTF-16 with BOM, tab-separated) was decoded as
    cp1252, so every header and value was full of NUL bytes."""
    text = "N° commande\tQté\tRéférence\nC0\t1\tRÉF-à\nC1\t2\tB\n"
    for enc in ("utf-16", "utf-16-be"):
        bom = b"\xfe\xff" if enc == "utf-16-be" else b""
        path = tmp_path / f"{enc}.txt"
        path.write_bytes(bom + text.encode(enc))
        assert sniff(path).encoding == "utf-16" and sniff(path).delimiter == "\t"
        raw = read_any(path)
        assert raw.columns == ["N° commande", "Qté", "Référence"]
        assert raw.df["Référence"].to_list() == ["RÉF-à", "B"]


def test_T2_1_utf32_with_bom_is_not_read_as_utf16_or_cp1252(tmp_path: Path) -> None:
    """F2c: the UTF-32-LE BOM starts with the UTF-16-LE BOM (sniffed utf-16, garbage) and a
    UTF-32-BE BOM fell back to cp1252; the BOM / charset_normalizer verdict is honoured."""
    text = "N° commande;Qté;Référence\nC0;1;RÉF-à\nC1;2;B\n"
    for enc, bom in (("utf-32", b""), ("utf-32-be", codecs.BOM_UTF32_BE)):
        path = tmp_path / f"{enc}.csv"
        path.write_bytes(bom + text.encode(enc))
        assert sniff(path).encoding == "utf-32" and sniff(path).delimiter == ";"
        raw = read_any(path)
        assert raw.columns == ["N° commande", "Qté", "Référence"]
        assert raw.df["Référence"].to_list() == ["RÉF-à", "B"]


def test_T2_1_delimiter_ignores_decimal_commas_and_quoted_delimiters() -> None:
    fr = ["Réf;Longueur;Poids", "A;387,0;0,369", "B;12,5;1,2", "C;3,0;4,5"]
    assert detect_delimiter(fr) == ";"
    quoted = ["sku,desc,qty", 'A,"x; y; z",1', 'B,"a; b",2', "C,c,3"]
    assert detect_delimiter(quoted) == ","


def test_T2_2_header_on_row_3_csv() -> None:
    sn = sniff(SNIFF / "header_row3.csv")
    assert sn.header_row == 3
    raw = read_any(SNIFF / "header_row3.csv")
    assert raw.columns == ["Référence", "Longueur", "Largeur", "Hauteur"]
    assert raw.df["Référence"].to_list() == ["A1", "A2", "A3"]  # blank line dropped
    assert raw.df["__source_row__"].to_list() == [4, 5, 7]  # 1-based file lines


def test_T2_2_header_on_row_3_excel_picks_the_biggest_sheet() -> None:
    raw = read_any(SNIFF / "header_row3.xlsx")
    assert raw.sniff.sheet == "Articles" and raw.sniff.header_row == 3
    assert raw.columns == ["Référence", "Longueur", "Poids", "Date création"]
    assert raw.df["Longueur"].to_list() == ["120.5", "300", "45"]
    fmt, share = detect_date_format(raw.df["Date création"])
    assert fmt is not None and fmt.startswith("%Y-%m-%d") and share == 1.0
    with pytest.raises(MappingError, match="no header row"):  # explicit sheet is honoured
        read_any(SNIFF / "header_row3.xlsx", sheet="Notes")
    with pytest.raises(MappingError, match="sheet"):
        read_any(SNIFF / "header_row3.xlsx", sheet="Nope")


def test_T2_2_header_rule_skips_sparse_and_numeric_rows() -> None:
    rows = [["Export"], ["", "", ""], ["1", "2", "3", "x"], ["sku", "qty", "date", "1"]]
    assert detect_header_row(rows) == 3  # row 3 has 3 numeric cells of 4 → not a header
    with pytest.raises(MappingError, match="no header row"):
        detect_header_row([["1", "2", "3"]] * 5)


def _parse(path: Path, col: str, kind: str) -> list[object]:
    raw = read_any(path)
    expr = parse_int if kind == "int" else parse_number
    return raw.df.select(expr(pl.col(col), raw.sniff.decimal)).to_series().to_list()


def test_T2_3_decimal_comma_with_thousand_dots() -> None:
    path = SNIFF / "decimal_comma_fr.csv"
    assert sniff(path).decimal == ","
    assert _parse(path, "Longueur", "float") == [1234.5, 387.0, 45.25, 10.0]
    assert _parse(path, "Poids", "float") == [0.369, 12.5, 1050.75, 0.005]
    assert _parse(path, "Colis par palette", "int") == [1200, 48, 2400, 6]


def test_T2_3_decimal_dot_with_thousand_commas() -> None:
    path = SNIFF / "thousands_en.csv"
    assert sniff(path).decimal == "."
    assert _parse(path, "Length", "float") == [1234.5, 387.0, 45.25, 10.0]
    assert _parse(path, "Weight", "float") == [0.369, 12.5, 1050.75, 0.005]
    assert _parse(path, "Cases per Pallet", "int") == [1200, 48, 2400, 6]


def test_T2_3_french_integers_with_dot_thousands_in_a_file_without_decimals(
    tmp_path: Path,
) -> None:
    """I54 amendment (F2d): thousands-only shapes ('1.234', '2.500.000') are left out of the
    share; with no separator value left the delimiter decides: ';' (FR Excel export) → ','
    and '1.234' is 1234. F2c read the file '.' and lost every grouped stock count. The same
    values in a ',' file are '.' → '1.234' is 1.234, not whole → null (counted), never 1234;
    the mapping's `decimal: ','` reads them as thousands."""
    path = SNIFF / "int_thousands_fr.csv"
    raw = read_any(path)
    assert (raw.sniff.delimiter, raw.sniff.decimal) == (";", ",")
    assert _parse(path, "Qté", "int") == [1234, 12, 2_500_000, 7]
    comma = _csv(tmp_path, path.read_text(encoding="utf-8").replace(";", ","))
    assert (sniff(comma).delimiter, sniff(comma).decimal) == (",", ".")
    assert _parse(comma, "Qté", "int") == [None, 12, None, 7]
    qty = read_any(comma).df.select(parse_int(pl.col("Qté"), ",")).to_series().to_list()
    assert qty == [1234, 12, 2_500_000, 7]


def test_T2_3_english_three_decimal_weights_next_to_integers_are_not_thousands(
    tmp_path: Path,
) -> None:
    """Audit round 2: the integer-only heuristic in step 4 turned this EN file ',' and read
    1.250 kg as 1250. No separator value matches '1.234,5' → '.'."""
    rows = ["A,1.250,10", "B,2.500,20", "C,3,30", "D,12.125,40", "E,4.750,50"]
    path = _csv(tmp_path, "SKU,Weight,Length\n" + "\n".join(rows))
    assert sniff(path).decimal == "."
    assert _parse(path, "Weight", "float") == [1.25, 2.5, 3.0, 12.125, 4.75]


def test_T2_3_dotted_codes_do_not_veto_a_french_decimal_comma(tmp_path: Path) -> None:
    """Audit round 2: a family code '10.10' looked like a dot decimal and vetoed the comma, so
    every FR dimension became null. F2c: no veto; one share over the file's separator values
    (80 comma values of 100 → ',')."""
    rows = [f"A{i};10.{i % 9 + 10};300,5;200,5;100,5;0,25" for i in range(20)]
    path = _csv(tmp_path, "Référence;Famille;Longueur;Largeur;Hauteur;Poids\n" + "\n".join(rows))
    assert sniff(path).decimal == ","
    assert _parse(path, "Longueur", "float")[:2] == [300.5, 300.5]
    assert _parse(path, "Poids", "float")[0] == 0.25


def _csv(tmp_path: Path, text: str, name: str = "f.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_T2_3_fr_dot_grouped_integers_do_not_veto_decimal_comma(tmp_path: Path) -> None:
    """F1's FR master writes '1.200' integers next to '120,5' dims and weight (4 decimal
    columns, 1 grouped integer column): 40 of 50 separator values match → ',', and the
    grouped integers are thousands in a comma file. Pooled, not per column (F2c)."""
    rows = [f"A{i};120,5;80,0;40,5;0,300;1.{i:03d}" for i in range(10)]
    header = "Référence;Longueur;Largeur;Hauteur;Poids;Unités par palette\n"
    path = _csv(tmp_path, header + "\n".join(rows))
    assert sniff(path).decimal == ","
    assert _parse(path, "Longueur", "float")[:2] == [120.5, 120.5]
    assert _parse(path, "Poids", "float")[0] == 0.3
    assert _parse(path, "Unités par palette", "int")[:2] == [1000, 1001]
    # I54 amendment: grouped integers in 2 of 4 columns are thousands-only shapes, left out;
    # '0,300' (leading 0) is a comma decimal: 20 of 20 → ','. F2c read this file '.'.
    rows = [f"A{i};120,5;0,300;1.{i:03d};2.{i:03d}" for i in range(10)]
    path = _csv(tmp_path, "Référence;Longueur;Poids;UVC;Colis\n" + "\n".join(rows), "g.csv")
    assert sniff(path).decimal == ","
    assert _parse(path, "Longueur", "float")[0] == 120.5
    assert _parse(path, "Poids", "float")[0] == 0.3
    assert _parse(path, "UVC", "int")[:2] == [1000, 1001]
    # the 80 % [P] threshold, pooled over the file: 30 comma decimals of 40 values → '.'
    rows = [f"A{i};120,5;80,5;40,5;0.25" for i in range(10)]
    path = _csv(tmp_path, "Référence;Longueur;Largeur;Hauteur;Poids\n" + "\n".join(rows), "h.csv")
    assert sniff(path).decimal == "."
    rows = [f"A{i};120,5;80,5;40,5;0,5;0.25" for i in range(10)]  # 40 of 50: exactly 80 % → ','
    path = _csv(tmp_path, "Réf;Longueur;Largeur;Hauteur;Poids;Volume\n" + "\n".join(rows), "k.csv")
    assert sniff(path).decimal == ","
    # F2d audit: just below the threshold stays '.' (kills DECIMAL_MIN_SHARE = 0.79)
    assert detect_decimal([["120,5"] * 799 + ["0.25"] * 201], ";") == "."
    assert detect_decimal([["120,5"] * 800 + ["0.25"] * 200], ";") == ","


def test_T2_3_english_file_with_comma_grouped_quantities_stays_decimal_dot(tmp_path: Path) -> None:
    rows = [f'A{i},120.5,0.369,"1,{i:03d}"' for i in range(10)]
    path = _csv(tmp_path, "SKU,Length,Weight,Units per pallet\n" + "\n".join(rows))
    assert sniff(path).decimal == "."  # 0 of 20: '1,000' thousands-only, left out (I54)
    assert _parse(path, "Length", "float")[0] == 120.5
    assert _parse(path, "Units per pallet", "int")[:2] == [1000, 1001]


def test_T2_3_three_decimal_quantities_in_a_dot_file_are_not_thousands(tmp_path: Path) -> None:
    """Audit: SAP-style '1.000' / '2.500' quantities in a decimal-dot file are 1 and 2.5 (not
    an integer → null), never 1000 and 2500."""
    path = _csv(tmp_path, "Material,Qty,Weight\nM1,1.000,0.5\nM2,2.000,1.25\nM3,12.000,3.75\n"
                          "M4,2.500,0.05\n")  # fmt: skip
    assert sniff(path).decimal == "."
    assert _parse(path, "Qty", "int") == [1, 2, 12, None]


def test_T2_3_a_mark_that_is_not_a_thousands_grouping_gives_null(tmp_path: Path) -> None:
    """Audit: in a '.' file '0,25' must be null (counted by R7), never 25 kg. F2c: plain
    integers no longer dilute the share, so a FR master with whole-kg weights is ','."""
    s = pl.DataFrame({"v": ["0,25", "2,75", "1,234.5", "1,234,567", "12", "1e-3", "1.5"]})
    assert s.select(parse_number(pl.col("v"), ".")).to_series().to_list() == [
        None, None, 1234.5, 1234567.0, 12.0, 0.001, 1.5,
    ]  # fmt: skip
    s = pl.DataFrame({"v": ["1.5", "12.34,5", "1.234,5", "0,25", "2.500.000"]})
    assert s.select(parse_number(pl.col("v"), ",")).to_series().to_list() == [
        None, None, 1234.5, 0.25, 2_500_000.0,
    ]  # fmt: skip
    rows = ["A;0,25;10", "B;2;10", "C;3;10", "D;1,5;10", "E;4;10", "F;5;10"]
    path = _csv(tmp_path, "Référence;Poids;Longueur\n" + "\n".join(rows))
    assert sniff(path).decimal == ","  # 2 of 2 separator values match; integers ignored
    assert _parse(path, "Poids", "float") == [0.25, 2.0, 3.0, 1.5, 4.0, 5.0]


def test_T2_4_dotted_dates_are_dates_not_numbers_in_the_decimal_sniff(tmp_path: Path) -> None:
    """Audit F2c round 1: '01.03.2025' counted as a separator value without a '1.234,5' match,
    so 20 dates + 20 comma decimals gave a 50 % share → '.', every pallet count became null and
    the file date format was None. A '%d.%m.%Y' date is a date (step 5), not a number."""
    rows = [f"BR{i};{i % 9 + 1:02d}.03.2025;A{i};{i + 5};0,{i + 1}5" for i in range(20)]
    header = "Bon de réception;Date réception;Référence;Qté;Palettes\n"
    path = _csv(tmp_path, header + "\n".join(rows))
    sn = sniff(path)
    assert (sn.decimal, sn.date_format) == (",", "%d.%m.%Y")
    assert _parse(path, "Palettes", "float")[:3] == [0.15, 0.25, 0.35]
    assert not is_numeric_text("01.03.2025") and not is_numeric_text(" 1.3.2025 ")
    assert is_numeric_text("1.234.567") and is_numeric_text("12.03") and is_numeric_text("1.000")


def test_T2_3_non_integral_and_garbage_become_null() -> None:
    s = pl.DataFrame({"v": ["1,5", "abc", "", "1 234", "NaN"]})
    out = s.select(i=parse_int(pl.col("v"), ","), f=parse_number(pl.col("v"), ","))
    assert out["i"].to_list() == [None, None, None, 1234, None]
    assert out["f"].to_list() == [1.5, None, None, 1234.0, None]


def test_T2_3_integers_outside_int64_and_infinities_become_null() -> None:
    """Audit round 2: one '99999999999999999999' cell crashed the whole ingest (strict cast)."""
    s = pl.DataFrame({"v": ["99999999999999999999", "1e20", "-1e19", "1e400", "7"]})
    out = s.select(i=parse_int(pl.col("v"), "."), f=parse_number(pl.col("v"), "."))
    assert out["i"].to_list() == [None, None, None, None, 7]
    assert out["f"].to_list()[3:] == [None, 7.0]  # inf is not a number


def test_bool_parsing_fr_en() -> None:
    s = pl.DataFrame({"v": ["Oui", "non", "TRUE", "0", "peut-être", None]})
    assert s.select(parse_bool(pl.col("v"))).to_series().to_list() == [
        True, False, True, False, None, None,
    ]  # fmt: skip


# 08:15 Paris on 1 March 2025 (UTC+1) = 07:15 UTC; date-only values are local midnight.
_UTC_0815 = datetime(2025, 3, 1, 7, 15, tzinfo=UTC)
_UTC_MIDNIGHT = datetime(2025, 2, 28, 23, 0, tzinfo=UTC)
T2_4_CASES = [
    ("2025-03-01T08:15:00+01:00", "%Y-%m-%dT%H:%M:%S%.f%#z", _UTC_0815),
    ("2025-03-01T07:15:00Z", "%Y-%m-%dT%H:%M:%S%.f%#z", _UTC_0815),
    ("2025-03-01 08:15:00", "%Y-%m-%d %H:%M:%S%.f", _UTC_0815),
    ("2025-03-01T08:15", "%Y-%m-%dT%H:%M", _UTC_0815),
    ("2025-03-01", "%Y-%m-%d", _UTC_MIDNIGHT),
    ("01/03/2025 08:15:00", "%d/%m/%Y %H:%M:%S", _UTC_0815),
    ("01/03/2025 08:15", "%d/%m/%Y %H:%M", _UTC_0815),
    ("01/03/2025", "%d/%m/%Y", _UTC_MIDNIGHT),
    ("01.03.2025 08:15", "%d.%m.%Y %H:%M", _UTC_0815),
    ("01.03.2025", "%d.%m.%Y", _UTC_MIDNIGHT),
    ("01-03-2025 08:15", "%d-%m-%Y %H:%M", _UTC_0815),
    ("01-03-2025", "%d-%m-%Y", _UTC_MIDNIGHT),
    ("20250301", "%Y%m%d", _UTC_MIDNIGHT),
    ("45717.34375", "excel_serial", _UTC_0815),  # 45717 days after 1899-12-30, + 8 h 15
]


@pytest.mark.parametrize(("value", "fmt", "expected"), T2_4_CASES)
def test_T2_4_each_date_format(value: str, fmt: str, expected: datetime) -> None:
    sample = pl.Series([value, value.replace("01", "13", 1) if fmt[1] == "d" else value])
    assert detect_date_format(sample)[0] == fmt
    out = pl.DataFrame({"v": [value]}).select(parse_datetime(pl.col("v"), "Europe/Paris"))
    assert out.to_series().dtype == pl.Datetime("us", "UTC")
    assert out.item() == expected


def test_T2_4_mixed_formats_are_coalesced_and_best_format_wins() -> None:
    values = ["01/03/2025 08:15"] * 90 + ["2025-03-01 08:15:00"] * 9 + ["31/02/2025 08:15"]
    fmt, share = detect_date_format(pl.Series(values))
    assert fmt == "%d/%m/%Y %H:%M" and share == pytest.approx(0.90)
    parsed = pl.DataFrame({"v": values}).select(parse_datetime(pl.col("v"), "Europe/Paris", fmt))
    assert parsed.to_series().null_count() == 1  # 31 February is not a date
    assert set(parsed.to_series().drop_nulls().to_list()) == {_UTC_0815}


def test_T2_4_ambiguous_day_month_assumes_ddmm_and_warns() -> None:
    with capture_logs() as logs:
        fmt, _ = detect_date_format(pl.Series(["01/03/2025", "02/03/2025", "12/11/2025"]))
    assert fmt == "%d/%m/%Y"
    assert any(e["event"] == "date_day_month_ambiguous" for e in logs)


def test_T2_4_two_digit_years_are_not_read_as_year_24() -> None:
    """Audit: %Y accepts '24' (year 0024), which R1 never flags. Such values are null (R1 then
    counts them); a mapping `date_format: '%d/%m/%y %H:%M'` reads them."""
    values = pl.Series(["01/01/24 00:01", "15/02/24 13:30"])
    assert detect_date_format(values)[1] == 0.0
    df = values.to_frame("v")
    assert df.select(parse_datetime(pl.col("v"), "Europe/Paris")).to_series().null_count() == 2
    fixed = df.select(parse_datetime(pl.col("v"), "Europe/Paris", "%d/%m/%y %H:%M")).to_series()
    assert fixed.to_list()[0] == datetime(2023, 12, 31, 23, 1, tzinfo=UTC)


def test_T2_4_dst_gap_and_overlap_in_paris() -> None:
    v = pl.DataFrame({"v": ["30/03/2025 02:30", "26/10/2025 02:30"]})
    out = v.select(parse_datetime(pl.col("v"), "Europe/Paris")).to_series().to_list()
    assert out[0] == datetime(2025, 3, 30, 1, 30, tzinfo=UTC)  # gap: shifted to 03:30 CEST
    assert out[1] == datetime(2025, 10, 26, 0, 30, tzinfo=UTC)  # overlap: earliest (CEST)


def test_sniff_reports_rows_and_date_format() -> None:
    sn = sniff(SNIFF / "utf8_semicolon.csv")
    assert sn.n_rows == 4 and sn.header_row == 1 and sn.date_format == "%d/%m/%Y %H:%M"


def test_parquet_input_is_read_as_text_and_round_trips() -> None:
    path = Path(__file__).resolve().parents[1] / "golden" / "tiny_golden" / "order_lines.parquet"
    source = pl.read_parquet(path)
    raw = read_any(path)
    assert raw.sniff.delimiter is None and raw.sniff.n_rows == source.height
    assert all(raw.df.schema[c] == pl.Utf8 for c in raw.columns)
    assert raw.df["line_status"].to_list() == source["line_status"].cast(pl.Utf8).to_list()
    fmt, share = detect_date_format(raw.df["order_ts"])
    assert fmt == "%Y-%m-%dT%H:%M:%S%.f%#z" and share == 1.0
    back = raw.df.select(parse_datetime(pl.col("order_ts"), "Europe/Paris", fmt)).to_series()
    assert back.to_list() == source["order_ts"].to_list()


def test_T2_2_leading_blank_line_and_cr_only_line_ends(tmp_path: Path) -> None:
    """Audit: a blank line above the header shifted the header onto the first data row."""
    for text in ("\nsku;qty;date\nA;1;x\nB;2;y\n", "sku;qty;date\rA;1;x\rB;2;y\r"):
        raw = read_any(_csv(tmp_path, text))
        assert raw.columns == ["sku", "qty", "date"] and raw.df["sku"].to_list() == ["A", "B"]
    raw = read_any(_csv(tmp_path, "\n\nsku;qty;date\nA;1;x\n"))
    assert raw.sniff.header_row == 3 and raw.df["__source_row__"].to_list() == [4]


def test_T2_1_stray_quote_in_an_unquoted_field_is_read_as_text(tmp_path: Path) -> None:
    """Audit: an inch mark (Ecran 24" LED) crashed Polars' strict CSV reader (exit 1)."""
    text = (
        'sku;description;length\nA;Ecran 24" LED;600\nB;Tube 3/4" PVC;2000\nC;"Carton; grand";300\n'
    )
    raw = read_any(_csv(tmp_path, text))
    assert raw.df["description"].to_list() == ['Ecran 24" LED', 'Tube 3/4" PVC', "Carton; grand"]
    assert raw.df["__source_row__"].to_list() == [2, 3, 4]
    bad = _csv(tmp_path, 'sku;description;length\nA;"Ecran LED;600\nB;Tube;2000\n', "bad.csv")
    with pytest.raises(MappingError, match="never closed") as e:
        read_any(bad)
    assert e.value.exit_code == 2


# ---------------------------------------------------------------- F2d: F2c open issues
def test_T2_3_ungrouped_and_space_grouped_comma_decimals_are_decimal_comma(
    tmp_path: Path,
) -> None:
    """I54 amendment (F2d): FR Excel CSV exports write '1037,5' (no grouping) and '1 200,5'
    (space, U+00A0 or U+202F thousands). The verbatim regex rejects both: F2c sniffed '.' and
    every such value was null. Each shape alone is decimal-comma evidence, in a ',' file too."""
    rows = [f"A{i};1037,5;1 200,5;2\u00a0345,25;12\u202f000,75" for i in range(5)]
    path = _csv(tmp_path, "Référence;Longueur;Largeur;Hauteur;Poids\n" + "\n".join(rows))
    assert sniff(path).decimal == ","
    for col, x in (("Longueur", 1037.5), ("Largeur", 1200.5), ("Hauteur", 2345.25),
                   ("Poids", 12000.75)):  # fmt: skip
        assert _parse(path, col, "float") == [x] * 5
    for i, v in enumerate(("1037,5", "1 200,5", "1\u00a0200,5", "1\u202f200,5")):
        one = _csv(tmp_path, f'Ref,Length,Width\nA,"{v}",3\nB,"{v}",4\n', f"one{i}.csv")
        assert sniff(one).decimal == ",", v
        assert _parse(one, "Length", "float") == [1037.5 if i == 0 else 1200.5] * 2
    # a dot-decimal file with 4-digit values stays '.': '1037.5' is no comma evidence
    dot = _csv(tmp_path, "Ref;Length;Width\nA;1037.5;3\nB;1200.25;4\n", "dot.csv")
    assert sniff(dot).decimal == "."


def test_T2_2_date_range_preamble_is_not_the_header(tmp_path: Path) -> None:
    """F2c regression (F2d): once dotted dates stopped being numbers, a 'Période du;01.01.2025;
    au;31.12.2025' preamble had 4 of 4 text cells and was taken as the header (header_row 1,
    mapping sku='Période du'). A date cell is a value, not a label: 2 of 4 → skipped."""
    for i, period in enumerate(("01.01.2025;au;31.12.2025", "01/01/2025;au;31/12/2025")):
        body = "\nRéférence;Qté;Date stock\nA;5;01.03.2025\nB;1.200;01.03.2025\n"
        path = _csv(tmp_path, f"Période du;{period}\n{body}", f"pre{i}.csv")
        raw = read_any(path)
        assert raw.sniff.header_row == 3 and raw.columns == ["Référence", "Qté", "Date stock"]
        assert raw.df["Référence"].to_list() == ["A", "B"]
        cols = {t.target: t.column for t in suggest_mapping(raw, "inventory").targets}
        assert (cols["sku"], cols["qty_units"], cols["snapshot_date"]) == (
            "Référence", "Qté", "Date stock",
        )  # fmt: skip
    assert detect_header_row([["Du", "2025-01-01", "au", "2025-12-31"], ["a", "b", "c"]]) == 1


def test_T2_1_utf16_and_utf32_without_bom_are_told_by_their_nul_bytes(tmp_path: Path) -> None:
    """F2c open issue (F2d): Excel 'Unicode Text' saved without a BOM (tab-separated UTF-16-LE).
    charset_normalizer gives no verdict, so the file was read as cp1252 full of NUL bytes."""
    text = "N° commande\tQté\tRéférence\n" + "".join(f"C{i}\t{i}\tRÉF-à-{i}\n" for i in range(30))
    for enc in ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
        path = tmp_path / f"{enc}.txt"
        path.write_bytes(text.encode(enc))
        sn = sniff(path)
        assert (sn.encoding, sn.delimiter, sn.header_row) == (enc, "\t", 1)
        raw = read_any(path)
        assert raw.columns == ["N° commande", "Qté", "Référence"] and raw.df.height == 30
        assert raw.df["Référence"].to_list()[:2] == ["RÉF-à-0", "RÉF-à-1"]
    euros = "Réf\tPrix €\tLibellé\n" + "A\t12,5 €\tCrème brûlée – 1 €\n" * 20  # € is 0x20AC
    assert detect_encoding(euros.encode("utf-16-le")) == "utf-16-le"
    assert detect_encoding(text.encode("cp1252")) == "cp1252"  # 8-bit text has no NUL byte


def test_T2_4_all_digit_yyyymmdd_column_names_the_file_date_format(tmp_path: Path) -> None:
    """F2c open issue (F2d): an all-digit '%Y%m%d' column was hidden from the file date format
    by the all-numeric gate (date_format None). 8-digit ids that are not dates stay None."""
    rows = [f"A{i};{i + 1};202503{i % 28 + 1:02d}" for i in range(20)]
    path = _csv(tmp_path, "Référence;Qté;Date stock\n" + "\n".join(rows))
    assert sniff(path).date_format == "%Y%m%d"
    rows = [f"A{i};{i + 1};{20_000_000 + 37 * i}" for i in range(20)]  # '20', month 00
    path = _csv(tmp_path, "Référence;Qté;N° commande\n" + "\n".join(rows), "ids.csv")
    assert sniff(path).date_format is None


# ---------------------------------------------------------------- F2d fix round 1
def test_T2_3_leading_zero_three_decimal_weights_in_a_semicolon_file_are_decimals(
    tmp_path: Path,
) -> None:
    """F2d audit (medium): '0.125' matched the I54 thousands-only shape, so a ';' master with
    integer dims and 3-decimal weights fell to the ';' tie-break → ',' and read 0.125 kg as
    125 kg, silently. A leading 0 group is never thousands: it stays in the share (dot
    evidence) and no decimal mark reads it as a grouping."""
    w = ["0.125", "0.250", "0.369", "0.080", "0.450", "0.200"]
    rows = [f"S{i:03d};{300 + i};{200 + i};{100 + i};{w[i % 6]};6" for i in range(30)]
    path = _csv(tmp_path, "SKU;Length;Width;Height;Weight;Units per case\n" + "\n".join(rows))
    assert sniff(path).decimal == "."
    assert _parse(path, "Weight", "float")[:6] == [0.125, 0.25, 0.369, 0.08, 0.45, 0.2]
    s = pl.DataFrame({"v": ["0.125", "-0.250", "1.250", "12.500.000"]})
    assert s.select(parse_number(pl.col("v"), ",")).to_series().to_list() == [
        None, None, 1250.0, 12_500_000.0,
    ]  # fmt: skip
    s = pl.DataFrame({"v": ["0,125", "1,250"]})
    assert s.select(parse_number(pl.col("v"), ".")).to_series().to_list() == [None, 1250.0]
    # '0,125' in a tab file is comma evidence now, not a left-out thousands shape
    tab = _csv(tmp_path, "Ref\tPoids\tQté\nA\t0,125\t3\nB\t0,250\t4\n", "tab.csv")
    assert sniff(tab).decimal == ","
    assert _parse(tab, "Poids", "float") == [0.125, 0.25]


def test_T2_2_pivoted_date_header_falls_back_to_the_verbatim_rule() -> None:
    """F2d audit: with dates as values, a pivoted header (2 labels + 3 month columns) had no
    qualifying row and raised 'no header row found'. No row passes the date-aware rule → the
    verbatim step-3 rule (non-numeric) takes row 0. Only a fallback: a preamble before a
    label header is still skipped (test_T2_2_date_range_preamble_is_not_the_header)."""
    pivot = ["Référence", "Désignation", "01/01/2025", "01/02/2025", "01/03/2025"]
    rows = [pivot, ["A1", "Vis", "5", "6", "7"], ["A2", "Ecrou", "1", "2", "3"]]
    assert detect_header_row(rows) == 0
    assert detect_header_row([["Du", "01.01.2025", "au", "31.12.2025"], rows[0][:3]]) == 1
    with pytest.raises(MappingError, match="no header row"):
        detect_header_row([["1", "2", "3"], ["4", "5", "6"]])


def test_T2_1_utf16_without_bom_with_many_non_latin1_letters(tmp_path: Path) -> None:
    """F2d audit: the ≥ 90 % NUL high-byte rule missed Polish UTF-16 (Ł, ż have high byte
    0x01) and read it as cp1252. Mostly-NUL is now ≥ 50 % of the high bytes."""
    body = "".join(f"P{i}\t{i}\tŁódź żółć ściółka ąę\n" for i in range(40))
    text = "Indeks\tIlość\tOpis\n" + body
    for enc in ("utf-16-le", "utf-16-be"):
        path = tmp_path / f"{enc}.txt"
        path.write_bytes(text.encode(enc))
        assert detect_encoding(text.encode(enc)) == enc
        raw = read_any(path)
        assert raw.columns == ["Indeks", "Ilość", "Opis"] and raw.df.height == 40
    fr = "Référence\tQté\n" + "".join(f"R{i}\t{i}\n" for i in range(40))
    assert detect_encoding(fr.encode("utf-8") + b"\x00\x00\x00") == "utf-8"  # stray NULs


# ---------------------------------------------------------------- F2e
def _wide(enc: str, n_latin: int, other: str, n_other: int) -> bytes:
    """4 KB of UTF-16 (2,048 code units): `n_latin` 'a' (NUL high byte) + `n_other` `other`."""
    head = ("a" * n_latin + other * n_other).encode(enc)
    assert len(head) == WIDE_HEAD_BYTES
    return head


@pytest.mark.parametrize("enc", ["utf-16-le", "utf-16-be"])
def test_T2_1_utf16_without_bom_nul_thresholds_are_50_and_10_percent(enc: str) -> None:
    """I67 step 1 (F2d open issue 4): ≥ 50 % NUL at the high-byte offsets and < 10 % at the
    low-byte offsets. 'Ł' (U+0141) has a non-NUL high byte; 'Ā' (U+0100) a NUL low byte.
    Kills WIDE_MOSTLY_NUL = 0.3 (49 % passes) and WIDE_RARELY_NUL = 0.5 (10 % passes)."""
    assert _wide_without_bom(_wide(enc, 1024, "Ł", 1024)) == enc  # exactly 50 % NUL highs
    assert _wide_without_bom(_wide(enc, 1003, "Ł", 1045)) is None  # 48.97 %
    assert _wide_without_bom(_wide(enc, 1844, "Ā", 204)) == enc  # 9.96 % NUL lows
    assert _wide_without_bom(_wide(enc, 1843, "Ā", 205)) is None  # 10.01 %
    # mostly Cyrillic text has few NUL high bytes: left to charset_normalizer (I67)
    ru = ("Артикул\tКол-во\tОписание\n" + "А1\t5\tБолт стальной\n" * 200).encode(enc)
    assert _wide_without_bom(ru) is None


PIVOT = ["Référence", "Désignation", "01/01/2025", "01/02/2025", "01/03/2025"]


@pytest.mark.parametrize(
    ("rows", "header"),
    [
        ([PIVOT, ["A1", "Vis", "", "", "7"]], 0),  # sparse data row
        ([PIVOT, ["A1", "Vis M6", "Acier", "", "7"]], 0),  # text-heavy data row
        ([PIVOT, ["A1", "Vis", "5", "6", "7"], ["A2", "Ecrou", "", "", "3"]], 0),
        ([PIVOT, [], ["A1", "Vis", "", "", "7"]], 0),
        ([["Période du", "01.01.2025", "au", "31.12.2025"], ["Référence", "Qté", "Date"]], 1),
        ([["Période du", "01.01.2025", "au", "31.12.2025"], [], ["Réf", "Qté", "Date"]], 2),
        ([["Du", "01.01.2025", "au", "31.12.2025"], PIVOT[:3], ["A", "5", "01.03.2025"]], 1),
    ],
)
def test_T2_2_pivoted_date_header_with_a_sparse_data_row_is_still_row_0(
    rows: list[list[str]], header: int
) -> None:
    """F2d open issue 2: below a pivoted date header, a sparse or text-heavy data row
    ('A1;Vis;;;7', 3 cells, 2 labels) passed the date-aware rule and was taken as the header
    (index 1). A date-aware pick holding a number below a row that qualifies only verbatim is
    a data row: the verbatim row is the header. A real header below a date-range preamble
    holds no number and is still found, with or without a blank line between."""
    assert detect_header_row(rows) == header


def test_T2_2_pivoted_csv_with_a_sparse_first_data_row_reads_the_pivot_header(
    tmp_path: Path,
) -> None:
    body = "A1;Vis;;;7\nA2;Ecrou;1;2;3\n"
    raw = read_any(_csv(tmp_path, ";".join(PIVOT) + "\n" + body))
    assert raw.sniff.header_row == 1 and raw.columns == PIVOT and raw.df.height == 2


def test_T2_3_tie_break_flag_is_set_only_when_the_delimiter_chose_the_mark(
    tmp_path: Path,
) -> None:
    """I67 step 4: `decimal_by_delimiter` records that no value showed the mark (I54
    tie-break). Values that decide and a saved mapping's `decimal` leave it False (Excel and
    Parquet have no field delimiter and never set it)."""
    weights = "SKU;Poids;Colis\nA;2;6\nB;1.250;6\nC;10;6\n"
    sn = sniff(_csv(tmp_path, weights))
    assert (sn.decimal, sn.decimal_by_delimiter) == (",", True)
    assert sniff(_csv(tmp_path, weights.replace(";", ","), "c.csv")).decimal_by_delimiter
    fr = _csv(tmp_path, "SKU;Poids;Colis\nA;2,5;6\nB;1.250;6\n", "fr.csv")
    assert (sniff(fr).decimal, sniff(fr).decimal_by_delimiter) == (",", False)
    saved = Mapping(dataset="sku_master", columns={}, decimal=".")
    raw = read_any(tmp_path / "f.csv", mapping=saved)
    assert (raw.sniff.decimal, raw.sniff.decimal_by_delimiter) == (".", False)
