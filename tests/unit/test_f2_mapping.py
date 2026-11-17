"""F2 mapping: T2.5 accuracy on the FR synthetic CSV, scoring, confirmation, apply, unit hints."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from whsizing.errors import ConfigError, MappingError
from whsizing.io import apply_mapping, read_any, suggest_mapping
from whsizing.io.mapping import (
    TARGETS,
    detect_unit_hints,
    header_score,
    load_mapping,
    normalize,
    number_notes,
    resolve_mapping,
    save_mapping,
    tie_break_notes,
)
from whsizing.io.readers import RawTable
from whsizing.schemas.ingest import Mapping, MappingFilter
from whsizing.schemas.manifest import SniffResult
from whsizing.synth import export, generate, load_synth_profile
from whsizing.synth.export import HEADERS

ROOT = Path(__file__).resolve().parents[2]
TINY_CSV = ROOT / "tests" / "golden" / "tiny_golden"
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")


def _accuracy(folder: Path, lang: str) -> tuple[float, list[str]]:
    """Share of the CSV's targets auto-mapped to the header the generator wrote."""
    right, wrong = 0, []
    for ds in DATASETS:
        suggestion = suggest_mapping(read_any(folder / f"{ds}.csv"), ds)
        got = {t.target: (t.column, t.status) for t in suggestion.targets}
        for target, header in HEADERS[lang][ds].items():
            if got[target] == (header, "auto"):
                right += 1
            else:
                wrong.append(f"{ds}.{target}: {got[target]} != {header}")
    total = sum(len(h) for h in HEADERS[lang].values())
    return right / total, wrong


def test_T2_5_mapping_accuracy_on_fr_synthetic_csv() -> None:
    accuracy, wrong = _accuracy(TINY_CSV / "csv_fr", "fr")
    assert accuracy >= 0.95, wrong
    assert accuracy == 1.0, wrong  # 'Catégorie' needs the F2 synonym addition


def test_T2_5_mapping_accuracy_on_messy_fr_csv_and_en_csv(tmp_path: Path) -> None:
    """cp1252, mixed dates, thousand separators, repeated header row: mapping still exact."""
    profile = load_synth_profile(ROOT / "data" / "synth" / "profiles" / "b2b_cases.yaml")
    profile = profile.model_copy(update={"n_days": 40, "n_skus": 300})
    export(generate(profile, seed=7), tmp_path, ("csv_fr",), defects=profile.defects, seed=7)
    assert read_any(tmp_path / "csv_fr" / "order_lines.csv").sniff.encoding == "cp1252"
    accuracy, wrong = _accuracy(tmp_path / "csv_fr", "fr")
    assert accuracy >= 0.95, wrong
    accuracy_en, wrong_en = _accuracy(TINY_CSV / "csv_en", "en")
    assert accuracy_en >= 0.95, wrong_en


def test_normalize_strips_accents_case_and_punctuation() -> None:
    assert normalize("Qté") == "qte"
    assert normalize("N° commande") == "n commande"
    assert normalize("  Poids (kg)  ") == "poids kg"
    assert normalize("Catégorie") == "categorie"


def test_header_score_exact_then_fuzzy() -> None:
    assert header_score("Qté", "qty_units") == (1.0, True, "qte")
    score, exact, _ = header_score("Lenght", "length_mm")
    assert not exact and 0.60 <= score < 0.85


def _raw(data: dict[str, list[str | None]], decimal: str = ".") -> RawTable:
    df = pl.DataFrame(data, schema=dict.fromkeys(data, pl.Utf8))
    df = df.with_columns(__source_row__=pl.int_range(2, df.height + 2, dtype=pl.Int64))
    sn = SniffResult(encoding="utf-8", delimiter=";", header_row=1, decimal=decimal,
                     date_format=None, n_rows=df.height)  # fmt: skip
    return RawTable(path=Path("client.csv"), df=df, sniff=sn)


ORDERS = {
    "Order date": ["01/03/2025 08:00", "01/03/2025 08:00", "02/03/2025 09:30"],
    "Date livraison": ["03/03/2025", "03/03/2025", "04/03/2025"],
    "Commande": ["C1", "C1", "C2"],
    "Article": ["A1", "A2", "A1"],
    "Qte": ["2", "1", "5"],
    "Etat": ["Expédié", "annulée", None],
}


def test_greedy_assignment_uses_each_column_once_and_checks_content() -> None:
    s = suggest_mapping(_raw(ORDERS), "order_lines")
    got = {t.target: t for t in s.targets}
    assert got["order_id"].column == "Commande" and got["order_id"].status == "auto"
    assert got["order_ts"].column == "Order date"  # exact beats 'Date livraison' (also 'date')
    assert got["sku"].column == "Article" and got["qty_units"].column == "Qte"
    assert got["line_status"].column == "Etat"
    columns = [t.column for t in s.targets if t.column]
    assert len(columns) == len(set(columns))
    # a date column scores × 0.5 against an id target (step 3 content check)
    s2 = suggest_mapping(_raw({"Order": ORDERS["Order date"]}), "order_lines")
    order_id = next(t for t in s2.targets if t.target == "order_id")
    assert order_id.column is None and order_id.score == 0.5 and "×0.5" in order_id.reason


def test_tied_fuzzy_scores_are_asked_not_auto_accepted() -> None:
    """Audit round 2: 'Réf client' and 'Réf article' both score 1.00 on the synonym 'ref'
    (token_set_ratio of a subset); column order picked the customer column as sku, silently.
    A fuzzy tie with another free column is a suggestion that needs confirmation."""
    n = 12  # > 10 distinct values: both columns pass the SKU cardinality preference
    raw = _raw({"N° commande": [f"C{i // 2}" for i in range(n)],
                "Date commande": ["01/03/2025 08:00"] * n,
                "Réf client": [f"K{i}" for i in range(n)],
                "Réf article": [f"A{i}" for i in range(n)], "Qté": ["1"] * n})  # fmt: skip
    sku = next(t for t in suggest_mapping(raw, "order_lines").targets if t.target == "sku")
    assert sku.status == "suggest" and sku.score == 1.0 and "tied with 'Réf article'" in sku.reason
    with pytest.raises(MappingError, match="sku"):
        resolve_mapping(suggest_mapping(raw, "order_lines"), raw, confirm=None)
    pick = resolve_mapping(  # the user refuses 'Réf client' and is offered 'Réf article'
        suggest_mapping(raw, "order_lines"), raw, lambda c, q: "Use column 'Réf article'" in q
    )
    assert pick.columns["sku"] == "Réf article"
    master = _raw({"Code article": ["A", "B"], "Longueur": ["1", "2"], "Largeur": ["1", "2"],
                   "Hauteur": ["1", "2"], "Poids brut kg": ["2", "3"],
                   "Poids net kg": ["1", "2"]})  # fmt: skip
    weight = next(t for t in suggest_mapping(master, "sku_master").targets
                  if t.target == "weight_kg")  # fmt: skip
    assert weight.status == "suggest" and "tied with 'Poids net kg'" in weight.reason
    exact = next(t for t in suggest_mapping(_raw(ORDERS), "order_lines").targets
                 if t.target == "order_ts")  # fmt: skip
    assert exact.status == "auto"  # 'Order date' is an exact synonym: no tie with 'Date livraison'


def test_T2_5_exact_synonym_beats_subset_match_then_cardinality_breaks_ties() -> None:
    """F2c: 'ref' scores 'Réf client' 1.0 (token_set subset). With few SKUs in the sample the
    old × 0.9 cardinality penalty dropped the exact 'Référence' to 0.9 and the customer column
    became the SKU. Exact beats subset; among fuzzy ties sku prefers more distinct values."""
    n = 30
    orders: dict[str, list[str | None]] = {"N° commande": [f"C{i // 3}" for i in range(n)],
              "Date commande": ["01/03/2025 08:00"] * n, "Qté": ["1"] * n}  # fmt: skip
    raw = _raw({**orders, "Réf client": [f"K{i}" for i in range(n)],
                "Référence": [f"A{i % 5}" for i in range(n)]})  # fmt: skip
    got = {t.target: t for t in suggest_mapping(raw, "order_lines").targets}
    assert (got["sku"].column, got["sku"].status) == ("Référence", "auto")
    assert got["customer"].column == "Réf client"
    raw = _raw({**orders, "Réf client": [f"K{i % 4}" for i in range(n)],
                "Réf article": [f"A{i}" for i in range(n)]})  # fmt: skip
    sku = next(t for t in suggest_mapping(raw, "order_lines").targets if t.target == "sku")
    assert sku.column == "Réf article" and sku.status == "suggest"  # header tie: still asked
    assert "tied with 'Réf client'" in sku.reason


def test_suggested_required_column_needs_confirmation() -> None:
    raw = _raw({"Item code": ["A", "B"], "Lenght": ["100", "200"], "Width": ["1", "2"],
                "Height": ["1", "2"], "Weight": ["1", "2"]})  # fmt: skip
    suggestion = suggest_mapping(raw, "sku_master")
    length = next(t for t in suggestion.targets if t.target == "length_mm")
    assert length.status == "suggest" and length.column == "Lenght"
    with pytest.raises(MappingError, match="length_mm") as e:
        resolve_mapping(suggestion, raw, confirm=None)
    assert e.value.exit_code == 2
    asked: list[str] = []
    mapping = resolve_mapping(suggestion, raw, lambda code, q: asked.append(code) or True)
    assert asked == ["mapping.length_mm"] and mapping.columns["length_mm"] == "Lenght"
    refused = suggest_mapping(raw, "sku_master")
    with pytest.raises(MappingError):
        resolve_mapping(refused, raw, lambda code, q: False)


def test_unmapped_required_target_is_offered_every_column_interactively() -> None:
    """Step 5 (audit): interactive mode prompts for an unmapped required target, offering the
    unused columns best first; non-interactive mode raises MappingError (exit 2)."""
    raw = _raw({"Horodatage": ORDERS["Order date"], "Commande": ORDERS["Commande"],
                "Article": ORDERS["Article"], "Qte": ORDERS["Qte"]})  # fmt: skip
    suggestion = suggest_mapping(raw, "order_lines")
    ts = next(t for t in suggestion.targets if t.target == "order_ts")
    assert ts.status == "unmapped" and set(ts.candidates) == set(raw.columns)
    with pytest.raises(MappingError, match="order_ts") as e:
        resolve_mapping(suggestion, raw, confirm=None)
    assert e.value.exit_code == 2
    asked: list[str] = []

    def pick_horodatage(code: str, question: str) -> bool:
        asked.append(question)
        return code == "mapping.order_ts" and "'Horodatage'" in question

    mapping = resolve_mapping(suggestion, raw, pick_horodatage)
    assert mapping.columns["order_ts"] == "Horodatage"
    assert all("'Commande'" not in q for q in asked)  # columns already used are not offered
    with pytest.raises(MappingError, match="order_ts"):
        resolve_mapping(suggestion, raw, lambda code, q: False)


def test_saved_mapping_sniff_values_fix_a_mis_sniffed_file(tmp_path: Path) -> None:
    """Step 7 (audit): decimal, header_row and date_format recorded in mapping/<dataset>.yaml
    are used on the next ingest, so a hand correction fixes a mis-sniffed file."""
    path = tmp_path / "ventes.csv"
    path.write_text(
        "Export;ventes;janvier 2024;site LYON\n"  # 4 text cells: taken as the header by step 3
        "Commande;Date;Article;Qte\n"
        "C1;02/14/2025 08:13;A1;1\nC2;02/15/2025 09:00;A2;2\n",
        encoding="utf-8",
    )
    columns: dict[str, str | None] = {"order_id": "Commande", "order_ts": "Date", "sku": "Article",
                                      "qty_units": "Qte"}  # fmt: skip
    with pytest.raises(MappingError, match="not in the file"):
        apply_mapping(read_any(path), Mapping(dataset="order_lines", columns=columns))
    fixed = Mapping(dataset="order_lines", columns=columns, header_row=2,
                    date_format="%m/%d/%Y %H:%M")  # fmt: skip
    raw = read_any(path, mapping=fixed)
    assert raw.sniff.header_row == 2 and raw.columns == ["Commande", "Date", "Article", "Qte"]
    df = apply_mapping(raw, fixed)
    assert df["order_ts"].null_count() == 0 and df["order_ts"].dt.month().to_list() == [2, 2]
    master = _raw({"sku": ["A", "B"], "length_mm": ["120,5", "300,0"]})  # sniffed '.'
    dims = dict.fromkeys(("length_mm", "width_mm", "height_mm", "weight_kg"), "length_mm")
    m = Mapping(dataset="sku_master", columns={"sku": "sku", **dims})
    assert apply_mapping(master, m)["length_mm"].to_list() == [None, None]
    m = m.model_copy(update={"decimal": ","})
    assert apply_mapping(master, m)["length_mm"].to_list() == [120.5, 300.0]
    with pytest.raises(ConfigError, match="decimal") as e:
        read_any(path, mapping=fixed.model_copy(update={"decimal": ";"}))
    assert e.value.exit_code == 2


def test_apply_mapping_types_filters_and_defaults() -> None:
    data = {**ORDERS, "Entrepôt": ["LYON", "PARIS", "LYON"]}
    columns: dict[str, str | None] = {"order_id": "Commande", "order_ts": "Order date",
               "sku": "Article", "qty_units": "Qte", "line_status": "Etat"}  # fmt: skip
    m = Mapping(dataset="order_lines", columns=columns,
                filters=[MappingFilter(column="Entrepôt", equals="LYON")])  # fmt: skip
    df = apply_mapping(_raw(data), m)
    assert df.columns == [*[t for t in TARGETS["order_lines"] if t != "customer"],
                          "source_file", "source_row"]  # fmt: skip
    assert df["order_id"].to_list() == ["C1", "C2"]
    assert df["qty_units"].dtype == pl.Int64 and df["qty_units"].to_list() == [2, 5]
    assert df["order_ts"].dtype == pl.Datetime("us", "UTC")
    assert df["line_status"].to_list() == ["shipped", "shipped"]  # expédié, null → default
    assert df["channel"].null_count() == 2 and df["source_row"].to_list() == [2, 4]
    statuses = apply_mapping(
        _raw({**ORDERS, "Etat": ["retourné", "ANNULÉ", "???"]}),
        m.model_copy(update={"filters": []}),
    )
    assert statuses["line_status"].to_list() == ["returned", "cancelled", "unknown"]
    with pytest.raises(MappingError, match="Nope"):
        apply_mapping(_raw(ORDERS), m.model_copy(update={"columns": {**columns, "sku": "Nope"}}))


def test_T2_3_number_notes_count_whole_values_shaped_like_thousands() -> None:
    """Audit F2c round 1: in a '.' file '2.000' reads as 2 (a whole number, silently / 1000)
    while '1.145' is null; the note counted only the nulls. Both are counted, for ',' too
    ('1,000' reads as 1). A float column is not flagged: '2.000' kg is a 3-decimal weight."""
    stock = Mapping(dataset="inventory", columns={"sku": "Art", "qty_units": "Qte"})
    qty: list[str | None] = ["2.000", "1.145", "7", "1.000.000", "3.5", "12.000"]
    data: dict[str, list[str | None]] = {"Art": [*"ABCDEF"], "Qte": qty, "Date": ["01/03/2025"] * 6}
    [note] = number_notes(_raw(data, "."), stock)
    assert "3 values are not whole numbers with the decimal mark '.'" in note
    assert "2 values such as '2.000' look like thousands" in note and "decimal: ','" in note
    data = {**data, "Qte": ["1,000", "1,234", "7", "8", "9", "10"]}
    [note] = number_notes(_raw(data, ","), stock)
    assert "1 values are not whole" in note and "1 values such as '2,000'" in note
    [note] = number_notes(_raw({**data, "Qte": ["1,000"] * 6}, ","), stock)
    assert "not whole" not in note and "6 values such as '2,000'" in note
    master = Mapping(dataset="sku_master", columns={"sku": "Art", "weight_kg": "Poids"})
    assert number_notes(_raw({"Art": ["A", "B"], "Poids": ["2.000", "1.250"]}), master) == []


def test_unit_hints_detect_cm_and_grams() -> None:
    df = pl.DataFrame({"length_mm": [38.0, 45.5, 60.0], "weight_kg": [450.0, 1200.0, 800.0]})
    hints = detect_unit_hints(df)
    assert hints["dims"][0] == "cm" and hints["weight"][0] == "g"
    ok = pl.DataFrame({"length_mm": [380.0, 455.0, 600.0], "weight_kg": [0.45, 1.2, 0.8]})
    assert detect_unit_hints(ok) == {}


def test_mapping_yaml_round_trip(tmp_path: Path) -> None:
    m = Mapping(dataset="order_lines", columns={"order_id": "N° commande", "channel": None},
                filters=[MappingFilter(column="Entrepôt", equals="LYON")])  # fmt: skip
    digest = save_mapping(m, tmp_path / "mapping" / "order_lines.yaml")
    assert len(digest) == 64
    text = (tmp_path / "mapping" / "order_lines.yaml").read_text(encoding="utf-8")
    assert "N° commande" in text and "merge_duplicate_sku_lines: true" in text
    assert load_mapping(tmp_path / "mapping" / "order_lines.yaml") == m


def test_mapping_yaml_with_unknown_time_zone_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "order_lines.yaml"
    path.write_text("dataset: order_lines\ntimezone: Europe/Pariss\ncolumns: {}\n")
    with pytest.raises(ConfigError, match="Pariss") as e:
        load_mapping(path)
    assert e.value.exit_code == 2


# ---------------------------------------------------------------- F2e
def test_T2_3_number_notes_never_read_a_leading_zero_group_as_thousands() -> None:
    """I54 leading-zero refinement in `number_notes` (F2d open issue 4): '0.000' in an int
    column of a '.' file is zero, never a '0' thousands group; only '2.000' is flagged.
    Kills the grouped_shape_leading_zero mutant (`\\d{1,3}` instead of `[1-9]\\d{0,2}`)."""
    stock = Mapping(dataset="inventory", columns={"sku": "Art", "qty_units": "Qte"})
    data: dict[str, list[str | None]] = {"Art": ["A", "B", "C"], "Qte": ["0.000", "2.000", "7"]}
    [note] = number_notes(_raw(data, "."), stock)
    assert "1 values such as '2.000' look like thousands" in note and "not whole" not in note
    assert number_notes(_raw({**data, "Qte": ["0.000", "0,000", "7"]}, "."), stock) == [
        "[inventory] client.csv, column 'Qte' (qty_units): 1 values are not whole numbers with "
        "the decimal mark '.' and count as missing. If the file uses ',' as decimal mark, set "
        "decimal: ',' in mapping/inventory.yaml and re-run."
    ]


def test_T2_3_tie_break_note_names_file_mark_examples_and_override() -> None:
    """I67 step 4: when the field delimiter chose the mark, the DQ note names the file, the
    mark, up to 5 distinct ambiguous values of the mapped numeric columns as read, and the
    `decimal:` override. Not when the values or the mapping decided, nor without an
    ambiguous value (an integer-only file: the mark changes nothing)."""
    weights: list[str | None] = ["2", "1.250", "-12.500", "1.250", "2.000.000", "3.000"]
    weights += ["4.500", "5.000"]
    data: dict[str, list[str | None]] = {"Art": [*"ABCDEFGH"], "Poids": weights}
    data["Code"] = ["9.999"] * 8
    master = Mapping(dataset="sku_master", columns={"sku": "Art", "weight_kg": "Poids"})
    raw = _raw(data, ",")
    raw = RawTable(raw.path, raw.df, raw.sniff.model_copy(update={"decimal_by_delimiter": True}))
    [note] = tie_break_notes(raw, master)
    assert note == (
        "[sku_master] client.csv: warning, decimal mark ',' chosen by the field delimiter ';', "
        "because no number in the first 2000 data rows shows the mark; values that can be "
        "thousands or 3 decimals were read as '1.250' (Poids) → 1250, '-12.500' (Poids) → "
        "-12500, '2.000.000' (Poids) → 2000000, '3.000' (Poids) → 3000, '4.500' (Poids) → "
        "4500. If the file uses '.' as decimal mark, set decimal: '.' in "
        "mapping/sku_master.yaml and re-run (decimal: ',' confirms this reading)."
    )  # 5 distinct, mapped columns only ('9.999' in the unmapped 'Code' is not shown)
    # F2e fix round 1: 6 ambiguous lengths do not crowd out the weight; columns take turns
    data["Long"] = ["1.100", "2.101", "3.102", "4.103", "5.104", "6.105", "7.106", "8"]
    both = master.model_copy(update={"columns": {**master.columns, "length_mm": "Long"}})
    [note] = tie_break_notes(RawTable(raw.path, _raw(data).df, raw.sniff), both)
    assert (
        "read as '1.100' (Long) → 1100, '1.250' (Poids) → 1250, '2.101' (Long) → 2101, "
        "'-12.500' (Poids) → -12500, '3.102' (Long) → 3102. If" in note
    )
    # a parsed decimal is shown exactly, not rounded to 6 significant digits ({x:g})
    pipe = raw.sniff.model_copy(update={"delimiter": "|", "decimal": "."})
    odd: dict[str, list[str | None]] = {"Art": ["A"], "Poids": ["1,234.567"]}
    [note] = tie_break_notes(RawTable(raw.path, _raw(odd).df, pipe), master)
    assert "'1,234.567' (Poids) → 1234.567. If the file uses ','" in note
    assert tie_break_notes(raw, master.model_copy(update={"decimal": ","})) == []
    assert tie_break_notes(_raw(data, ","), master) == []  # the values decided
    whole = {**data, "Poids": ["2", "5", "10", "3", "4", "6", "7", "8"]}
    assert tie_break_notes(RawTable(raw.path, _raw(whole).df, raw.sniff), master) == []


def test_T2_3_tie_break_note_shows_an_int_column_example_as_parse_int_reads_it() -> None:
    """I67 (c), F2e open issue 1: the example is parsed exactly as the column's parser does.
    `apply_mapping` reads an integer target (qty_units) with parse_int, so '1,500' in a ','
    file is 1.5, not whole, hence null (counted as missing), and the note must say so; it
    showed `→ 1.5` because it always used parse_number. The float column (weight_kg) of the
    same file keeps parse_number: '1,500' there is 1.5. Kills the float-only mutant."""
    sniff = _raw({"x": ["1"]}, ",").sniff.model_copy(update={"decimal_by_delimiter": True})
    stock = Mapping(
        dataset="inventory",
        columns={"sku": "Art", "qty_units": "Qte", "snapshot_date": "Date"},
    )
    data: dict[str, list[str | None]] = {
        "Art": ["A", "B"],
        "Qte": ["1,500", "2,000"],
        "Date": ["2025-03-01"] * 2,
    }
    raw = RawTable(Path("client.csv"), _raw(data, ",").df, sniff)
    canonical = apply_mapping(raw, stock)["qty_units"].to_list()
    assert canonical == [None, 2]  # what the canonical table holds
    [note] = tie_break_notes(raw, stock)
    assert "'1,500' (Qte) → unreadable (counted as missing), '2,000' (Qte) → 2." in note
    assert "1.5" not in note
    master = Mapping(dataset="sku_master", columns={"sku": "Art", "weight_kg": "Qte"})
    [note] = tie_break_notes(raw, master)
    assert "'1,500' (Qte) → 1.5, '2,000' (Qte) → 2." in note  # a float column: parse_number
    # int and float columns of one file each keep their own parser, in one note
    both = Mapping(
        dataset="sku_master",
        columns={"sku": "Art", "weight_kg": "Poids", "units_per_case": "Colis"},
    )
    mixed: dict[str, list[str | None]] = {"Art": ["A"], "Poids": ["1,500"], "Colis": ["1,500"]}
    [note] = tie_break_notes(RawTable(Path("client.csv"), _raw(mixed, ",").df, sniff), both)
    assert "'1,500' (Colis) → unreadable (counted as missing)" in note
    assert "'1,500' (Poids) → 1.5" in note


def test_T2_3_tie_break_note_ignores_rows_the_site_filter_drops() -> None:
    """I67 step 4 with a site filter (F2e audit mutant tb_no_filter): the examples come from
    the rows the mapping keeps; ambiguous values only on dropped rows give no note."""
    data: dict[str, list[str | None]] = {
        "Art": ["A", "B", "C", "D"],
        "Poids": ["1.250", "2", "3.500", "4"],
        "Site": ["PARIS", "LYON", "PARIS", "LYON"],
    }
    lyon = [MappingFilter(column="Site", equals="LYON")]
    master = Mapping(
        dataset="sku_master", columns={"sku": "Art", "weight_kg": "Poids"}, filters=lyon
    )
    raw = _raw(data, ",")
    raw = RawTable(raw.path, raw.df, raw.sniff.model_copy(update={"decimal_by_delimiter": True}))
    assert tie_break_notes(raw, master) == []
    [note] = tie_break_notes(raw, master.model_copy(update={"filters": []}))
    assert "'1.250'" in note and "'3.500'" in note
