"""F2 end to end: T2.9 messy files → canonical with a scripted confirmation, T1.4 F1 FR CSV
re-ingest, C5 bench, exit codes, mapping reuse and the spec's edge cases."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import xlsxwriter

from whsizing.errors import DataQualityError, MappingError
from whsizing.io import hash_id, ingest, read_any
from whsizing.io.mapping import load_mapping, save_mapping
from whsizing.io.parse import parse_int
from whsizing.schemas.frames import Inventory, OrderLines, Receipts, SkuMaster
from whsizing.schemas.ingest import MappingFilter
from whsizing.schemas.manifest import IngestManifest
from whsizing.schemas.project import InputSpec
from whsizing.synth import export, generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "data" / "synth" / "profiles"
RULES = ROOT / "tests" / "fixtures" / "ingest" / "rules"
SALT = b"test-salt"
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")
SCHEMAS = {"order_lines": OrderLines, "sku_master": SkuMaster, "inventory": Inventory,
           "receipts": Receipts}  # fmt: skip
T2_9_BUDGET_S = 15 * 60  # spec: < 15 min including the mapping confirmation
C5_BUDGET_S = 120  # C5: ingest + validate < 2 min on a 1 M-line CSV


def _dq(out: Path) -> dict[str, object]:
    return json.loads((out / "dq" / "dq_report.json").read_text(encoding="utf-8"))


def _manifest(out: Path) -> IngestManifest:
    return IngestManifest.model_validate_json((out / "dq" / "ingest_manifest.json").read_text())


def _rule(out: Path, rule: str, dataset: str = "order_lines") -> dict[str, Any]:
    rules = _dq(out)["rules"]
    assert isinstance(rules, list)
    return next(r for r in rules if r["rule"] == rule and r["dataset"] == dataset)


def _blocking(out: Path) -> list[str]:
    rules = _dq(out)["rules"]
    assert isinstance(rules, list)
    return [r["rule"] for r in rules if r["severity"] == "blocking"]


# ---------------------------------------------------------------- T2.9: three messy files
@pytest.fixture(scope="module")
def messy(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, pl.DataFrame]]:
    """1. order lines: F1 b2b_cases FR CSV with every defect (cp1252, mixed date formats,
    duplicates, orphans, trailing spaces, thousand separators, repeated header row, negatives);
    2. SKU master: Excel, header on row 3, typo'd English headers, dims in cm, weight in g,
    a description column; 3. stock: UTF-8-BOM CSV, 'dd.mm.yyyy' dates, '1,234' quantities."""
    d = tmp_path_factory.mktemp("messy")
    profile = load_synth_profile(PROFILES / "b2b_cases.yaml")
    profile = profile.model_copy(update={"n_days": 150, "n_skus": 600})
    frames = generate(profile, seed=11)
    export(frames, d, ("csv_fr",), defects=profile.defects, seed=11)
    shutil.move(d / "csv_fr" / "order_lines.csv", d / "ventes_2024.csv")
    master = frames["sku_master"]
    wb = xlsxwriter.Workbook(d / "articles.xlsx")
    ws = wb.add_worksheet("Articles")
    ws.write(0, 0, "Item master export, site LYON")
    headers = ["Item code", "Item description", "Lenght (cm)", "Widht (cm)", "Hieght (cm)",
               "Wieght (g)", "Units/case", "Cases/pallet", "Category"]  # fmt: skip
    ws.write_row(2, 0, headers)
    for i, r in enumerate(master.iter_rows(named=True)):
        dims = [r["length_mm"] / 10, r["width_mm"] / 10, r["height_mm"] / 10]  # cm
        packs = [r["units_per_case"], r["cases_per_pallet"], r["category"]]
        ws.write_row(
            3 + i, 0, [r["sku"], f"Article {i} - carton", *dims, r["weight_kg"] * 1000, *packs]
        )
    wb.close()
    stock = frames["inventory"].select(
        pl.col("sku").alias("Item code"),
        pl.col("qty_units")
        .map_elements(lambda q: f"{q:,}", return_dtype=pl.Utf8)
        .alias("Qty on hand"),
        pl.col("snapshot_date").dt.strftime("%d.%m.%Y").alias("Inventory date"),
    )
    (d / "stock.csv").write_bytes(b"\xef\xbb\xbf" + stock.write_csv().encode("utf-8"))
    return d, frames


def _messy_inputs(d: Path, mapping_dir: Path | None = None) -> dict[str, InputSpec]:
    files = {
        "order_lines": "ventes_2024.csv",
        "sku_master": "articles.xlsx",
        "inventory": "stock.csv",
    }
    return {
        ds: InputSpec(files=[d / f], mapping=mapping_dir / f"{ds}.yaml" if mapping_dir else None)
        for ds, f in files.items()
    }


def test_T2_9_three_messy_files_to_canonical_with_scripted_confirmation(
    messy: tuple[Path, dict[str, pl.DataFrame]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d, frames = messy
    asked: list[tuple[str, str]] = []

    def confirm(code: str, question: str) -> bool:  # the scripted user says yes to everything
        asked.append((code, question))
        return True

    t0 = time.perf_counter()
    manifest = ingest(_messy_inputs(d), tmp_path, SALT, confirm=confirm)
    wall = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\nT2.9 wall time: {wall:.1f} s (budget {T2_9_BUDGET_S} s)")
    assert wall < T2_9_BUDGET_S
    codes = {c for c, _ in asked}
    assert {"mapping.length_mm", "mapping.width_mm", "mapping.height_mm", "mapping.weight_kg",
            "mapping.snapshot_date", "W_UNITS_DIMS", "W_UNITS_WEIGHT"} <= codes  # fmt: skip
    # outputs and manifest
    assert manifest.anonymized and {x.dataset for x in manifest.datasets} == {
        "order_lines",
        "sku_master",
        "inventory",
    }
    saved = IngestManifest.model_validate_json(
        (tmp_path / "dq" / "ingest_manifest.json").read_text()
    )
    assert saved == manifest and _blocking(tmp_path) == []
    sniffs = {x.dataset: x.files[0].sniff for x in manifest.datasets}
    assert sniffs["order_lines"].encoding == "cp1252" and sniffs["order_lines"].delimiter == ";"
    assert sniffs["sku_master"].header_row == 3 and sniffs["inventory"].encoding == "utf-8-sig"
    lines_entry = next(x for x in manifest.datasets if x.dataset == "order_lines")
    assert lines_entry.dropped_by_rule.get("R5", 0) > 0  # duplicate_rows defect removed
    assert lines_entry.rows_in - sum(lines_entry.dropped_by_rule.values()) == lines_entry.rows_out
    assert str(_dq(tmp_path)["band"]) in (tmp_path / "dq" / "dq_report.html").read_text()
    canon = {
        ds: pl.read_parquet(tmp_path / "canonical" / f"{ds}.parquet")
        for ds in ("order_lines", "sku_master", "inventory")
    }
    for ds, df in canon.items():
        SCHEMAS[ds].validate(df)
    # anonymised: hashed ids, description dropped; same salt → joinable with the source ids
    master = canon["sku_master"]
    assert "description" not in master.columns
    assert master["sku"].str.len_chars().unique().to_list() == [16]
    src = frames["sku_master"].with_columns(
        sku=pl.col("sku").map_elements(lambda s: hash_id(s, SALT), return_dtype=pl.Utf8)
    )
    joined = master.join(src, on="sku", suffix="_src")
    assert joined.height == master.height == frames["sku_master"].height
    # cm → mm and g → kg after confirmation
    assert (joined["length_mm"] - joined["length_mm_src"]).abs().max() < 1e-6  # pyright: ignore[reportOperatorIssue]
    assert (joined["weight_kg"] - joined["weight_kg_src"]).abs().max() < 1e-9  # pyright: ignore[reportOperatorIssue]
    # '1,234' stock counts (',' file, thousands-only shapes): read as 1234 (I54 amended, F2d)
    assert canon["inventory"]["qty_units"].sum() == frames["inventory"]["qty_units"].sum()
    mapping = load_mapping(tmp_path / "mapping" / "sku_master.yaml")
    assert mapping.unit_hints == {"dims": "cm", "weight": "g"} and mapping.header_row == 3
    assert mapping.columns["length_mm"] == "Lenght (cm)"


def test_persisted_mapping_is_reused_non_interactively(
    messy: tuple[Path, dict[str, pl.DataFrame]], tmp_path: Path
) -> None:
    d, _ = messy
    first, second = tmp_path / "first", tmp_path / "second"
    ingest(_messy_inputs(d), first, SALT, confirm=lambda c, q: True)
    with pytest.raises(MappingError) as e:  # no mapping, nobody to confirm the typo'd headers
        ingest(_messy_inputs(d), tmp_path / "noninteractive", SALT)
    assert e.value.exit_code == 2 and "length_mm" in str(e.value)
    ingest(_messy_inputs(d, first / "mapping"), second, SALT)  # confirm=None: nothing asked
    a = pl.read_parquet(first / "canonical" / "sku_master.parquet")
    b = pl.read_parquet(second / "canonical" / "sku_master.parquet")
    assert a.equals(b)


# ---------------------------------------------------------------- T1.4 and C5
def test_T1_4_fr_csv_reingests_with_zero_blocking_issues(tmp_path: Path) -> None:
    """FR CSV of a 4-month ecom_mid (R9 blocks < 3 months), ingested non-interactively, one
    dataset at a time into the same folder (as `whsizing ingest --dataset X` will do)."""
    profile = load_synth_profile(PROFILES / "ecom_mid.yaml").model_copy(update={"n_days": 120})
    export(generate(profile, seed=42), tmp_path, ("csv_fr",))
    out = tmp_path / "run"
    for ds in DATASETS:
        manifest = ingest({ds: InputSpec(files=[tmp_path / "csv_fr" / f"{ds}.csv"])}, out, SALT)
        assert _blocking(out) == []
    assert [x.dataset for x in manifest.datasets] == list(DATASETS)
    for x in manifest.datasets:
        assert x.rows_out == x.rows_in, (x.dataset, x.dropped_by_rule)  # clean data: nothing lost
    assert manifest.coverage["dims_coverage_lines"] == 1.0
    lines = pl.read_parquet(out / "canonical" / "order_lines.parquet")
    OrderLines.validate(lines)
    assert lines["has_dims"].all()  # recomputed once the master was in the folder


@pytest.mark.bench
@pytest.mark.slow
def test_C5_bench_ingest_and_validate_1m_line_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = load_synth_profile(PROFILES / "ecom_mid.yaml")  # 730 days ≈ 0.95 M lines
    export(generate(profile, seed=42), tmp_path, ("csv_fr",))
    inputs = {ds: InputSpec(files=[tmp_path / "csv_fr" / f"{ds}.csv"]) for ds in DATASETS}
    t0 = time.perf_counter()
    manifest = ingest(inputs, tmp_path / "run", SALT)
    wall = time.perf_counter() - t0
    n = next(x.rows_in for x in manifest.datasets if x.dataset == "order_lines")
    with capsys.disabled():
        print(
            f"\nC5 ingest + validate: {n:,} order lines (+ master, stock, receipts) in {wall:.1f} s"
        )
    assert n > 900_000 and wall < C5_BUDGET_S


# ---------------------------------------------------------------- exit codes
def test_blocking_issue_raises_exit_3_after_writing_the_dq_report(tmp_path: Path) -> None:
    tiny = ROOT / "tests" / "golden" / "tiny_golden" / "csv_fr"  # 31 days → R9
    with pytest.raises(DataQualityError, match="R9") as e:
        ingest({ds: InputSpec(files=[tiny / f"{ds}.csv"]) for ds in DATASETS}, tmp_path, SALT)
    assert e.value.exit_code == 3
    assert (tmp_path / "dq" / "dq_report.html").is_file()
    assert (tmp_path / "dq" / "ingest_manifest.json").is_file()
    assert not (tmp_path / "canonical").exists()
    assert _blocking(tmp_path) == ["R9"]


def test_T2_6_one_stray_1970_line_on_a_31_day_file_still_exits_3_through_r9(
    tmp_path: Path,
) -> None:
    """M2 / I83: tiny_golden (31 days, exit 3 via R9) plus ONE line dated 1970-01-01 used to
    exit 0 with a DQ score of 100 and a 663-month history. The stray line is an R1 hit now."""
    tiny = ROOT / "tests" / "golden" / "tiny_golden" / "csv_en"
    d = tmp_path / "in"
    shutil.copytree(tiny, d)
    with (d / "order_lines.csv").open("a", encoding="utf-8") as f:  # the file's own date format
        f.write("STRAY-ORDER-1,1970-01-01T10:00:00+01:00,020708b3cf573cf4,1,B2C,shipped\n")
    out = tmp_path / "run"
    with pytest.raises(DataQualityError, match="R9") as e:
        ingest({ds: InputSpec(files=[d / f"{ds}.csv"]) for ds in DATASETS}, out, SALT)
    assert e.value.exit_code == 3 and "1.02 months" in str(e.value)
    assert _blocking(out) == ["R9"] and not (out / "canonical").exists()
    r1 = _rule(out, "R1")
    assert (r1["severity"], r1["count"], r1["dropped"]) == ("warning", 1, 1)
    assert "1 dated before 2025-03-01" in r1["message"] and "0 lines without" in r1["message"]
    assert r1["sample_rows"][0]["order_ts"].startswith("1970-01-01")
    assert "1.02 months" in _rule(out, "R9")["message"]
    entry = next(x for x in _manifest(out).datasets if x.dataset == "order_lines")
    assert entry.dropped_by_rule["R1"] == 1


def test_T2_6_thirty_stray_1970_lines_on_a_31_day_file_block_through_r1_and_r9(
    tmp_path: Path,
) -> None:
    """Final audit F1: tiny_golden (1,954 lines) plus 30 lines (1.5 %) on 1970-01-01 exited 0
    with a 663-month history and R1 'ok'. They are R1 hits now: R1 blocks (> 1 %) with R9."""
    tiny = ROOT / "tests" / "golden" / "tiny_golden" / "csv_en"
    d = tmp_path / "in"
    shutil.copytree(tiny, d)
    with (d / "order_lines.csv").open("a", encoding="utf-8") as f:
        for i in range(30):
            f.write(f"STRAY-ORDER-{i},1970-01-01T10:00:00+01:00,020708b3cf573cf4,1,B2C,shipped\n")
    out = tmp_path / "run"
    with pytest.raises(DataQualityError) as e:
        ingest({ds: InputSpec(files=[d / f"{ds}.csv"]) for ds in DATASETS}, out, SALT)
    assert e.value.exit_code == 3 and not (out / "canonical").exists()
    assert _blocking(out) == ["R1", "R9"]
    r1 = _rule(out, "R1")
    assert (r1["severity"], r1["count"], r1["dropped"]) == ("blocking", 30, 30)
    assert "1.02 months" in _rule(out, "R9")["message"]


def test_T2_6_two_stray_dates_within_90_days_of_each_other_still_exit_3_through_r9(
    tmp_path: Path,
) -> None:
    """Final audit round 2 (F1): tiny_golden plus a line on 1969-12-31 and a line on 1970-01-01
    (the epoch default in UTC and in +01:00) exited 0 with a 663-month history and R1 'ok'."""
    tiny = ROOT / "tests" / "golden" / "tiny_golden" / "csv_en"
    d = tmp_path / "in"
    shutil.copytree(tiny, d)
    with (d / "order_lines.csv").open("a", encoding="utf-8") as f:
        f.write("STRAY-1,1969-12-31T23:00:00+01:00,020708b3cf573cf4,1,B2C,shipped\n")
        f.write("STRAY-2,1970-01-01T10:00:00+01:00,020708b3cf573cf4,1,B2C,shipped\n")
    out = tmp_path / "run"
    with pytest.raises(DataQualityError, match="R9") as e:
        ingest({ds: InputSpec(files=[d / f"{ds}.csv"]) for ds in DATASETS}, out, SALT)
    assert e.value.exit_code == 3 and "1.02 months" in str(e.value)
    assert _blocking(out) == ["R9"] and not (out / "canonical").exists()
    r1 = _rule(out, "R1")
    assert (r1["severity"], r1["count"], r1["dropped"]) == ("warning", 2, 2)
    assert "2 dated before 2025-03-01" in r1["message"]


@pytest.mark.parametrize("profile_name", ["b2b_cases", "ecom_mid"])
def test_T2_6_clean_synthetic_files_have_no_r1_hit(tmp_path: Path, profile_name: str) -> None:
    """I83 on the other clean datasets (final audit P1): b2b_cases is sparse (orders every few
    days) and still has no gap of more than 90 days among its earliest dates."""
    profile = load_synth_profile(PROFILES / f"{profile_name}.yaml").model_copy(
        update={"n_days": 150}
    )
    export(generate(profile, seed=7), tmp_path, ("csv_en",))
    inputs = {ds: InputSpec(files=[tmp_path / "csv_en" / f"{ds}.csv"]) for ds in DATASETS}
    ingest(inputs, tmp_path / "run", SALT)
    r1 = _rule(tmp_path / "run", "R1")
    assert (r1["severity"], r1["count"]) == ("ok", 0)


def test_T2_6_clean_file_has_no_r1_hit_and_keeps_every_line(tmp_path: Path) -> None:
    """I83 must not touch a clean file: 4 months of ecom_mid → no R1 drop, same row counts."""
    profile = load_synth_profile(PROFILES / "ecom_mid.yaml").model_copy(update={"n_days": 120})
    export(generate(profile, seed=42), tmp_path, ("csv_en",))
    inputs = {ds: InputSpec(files=[tmp_path / "csv_en" / f"{ds}.csv"]) for ds in DATASETS}
    manifest = ingest(inputs, tmp_path / "run", SALT)
    r1 = _rule(tmp_path / "run", "R1")
    assert (r1["severity"], r1["count"]) == ("ok", 0)
    for x in manifest.datasets:
        assert x.rows_out == x.rows_in and "R1" not in x.dropped_by_rule


# ---------------------------------------------------------------- edge cases
def _base(ds: str) -> pl.DataFrame:
    return pl.read_csv(RULES / "base" / f"{ds}.csv", infer_schema=False)


def _write_base(d: Path, *datasets: str) -> dict[str, InputSpec]:
    d.mkdir(parents=True, exist_ok=True)
    for ds in datasets:
        _base(ds).write_csv(d / f"{ds}.csv")
    return {ds: InputSpec(files=[d / f"{ds}.csv"]) for ds in datasets}


def test_several_files_per_dataset_are_appended_and_deduplicated(tmp_path: Path) -> None:
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    lines = _base("order_lines")
    lines.head(300).write_csv(tmp_path / "in" / "ventes_part1.csv")
    lines.slice(250).write_csv(tmp_path / "in" / "ventes_part2.csv")  # 50 lines overlap
    inputs["order_lines"] = InputSpec(files=[tmp_path / "in" / "ventes_part*.csv"])  # glob
    manifest = ingest(inputs, tmp_path / "run", SALT)
    entry = next(x for x in manifest.datasets if x.dataset == "order_lines")
    assert len(entry.files) == 2 and entry.rows_in == lines.height + 50
    assert entry.dropped_by_rule == {"R5": 50} and entry.rows_out == lines.height


def test_dupheader_repeated_quantity_header_lands_in_the_dq_report_notes(tmp_path: Path) -> None:
    """Final audit (low): two 'qty_units' columns, the first used silently. The DQ report now
    says which file and column, and that the second was ignored; it survives a later ingest
    of another dataset into the same folder (notes of kept datasets are carried over)."""
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    rows = (RULES / "base" / "order_lines.csv").read_text().splitlines()
    doubled = [f"{r},{'qty_units' if i == 0 else '9'}" for i, r in enumerate(rows)]
    (tmp_path / "in" / "order_lines.csv").write_text("\n".join(doubled) + "\n")
    run = tmp_path / "run"
    ingest({"order_lines": InputSpec(files=[tmp_path / "in" / "order_lines.csv"])}, run, SALT)
    notes = _dq(run)["notes"]
    assert isinstance(notes, list)
    [note] = [n for n in notes if "appears twice" in n]
    assert note.startswith("[order_lines] order_lines.csv, column 'qty_units' appears twice")
    assert "was ignored" in note
    canon = pl.read_parquet(run / "canonical" / "order_lines.parquet")
    assert 9 not in canon["qty_units"].to_list()  # the first column was the one read
    ingest({"inventory": inputs["inventory"]}, run, SALT)
    assert any("appears twice" in n for n in _dq(run)["notes"])  # pyright: ignore[reportGeneralTypeIssues]


def test_dates_without_time_flag_the_hour_as_unknown(tmp_path: Path) -> None:
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    lines = _base("order_lines").with_columns(pl.col("order_ts").str.slice(0, 10))
    lines.write_csv(tmp_path / "in" / "order_lines.csv")
    inputs["order_lines"] = InputSpec(files=[tmp_path / "in" / "order_lines.csv"])
    manifest = ingest(inputs, tmp_path / "run", SALT)
    assert manifest.coverage["order_ts_with_time_share"] == 0.0
    notes = _dq(tmp_path / "run")["notes"]
    assert isinstance(notes, list) and any("hour is unknown" in n for n in notes)


def test_site_filter_from_the_mapping_yaml(tmp_path: Path) -> None:
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    lines = _base("order_lines").with_columns(
        site=pl.when(pl.int_range(pl.len()) % 4 == 0)
        .then(pl.lit("PARIS"))
        .otherwise(pl.lit("LYON"))
    )
    lines.write_csv(tmp_path / "in" / "order_lines.csv")
    spec = InputSpec(files=[tmp_path / "in" / "order_lines.csv"])
    ingest({**inputs, "order_lines": spec}, tmp_path / "first", SALT)  # writes mapping/
    mapping = load_mapping(tmp_path / "first" / "mapping" / "order_lines.yaml")
    filtered = mapping.model_copy(update={"filters": [MappingFilter(column="site", equals="LYON")]})
    save_mapping(filtered, tmp_path / "order_lines.yaml")
    spec = InputSpec(files=spec.files, mapping=tmp_path / "order_lines.yaml")
    manifest = ingest({**inputs, "order_lines": spec}, tmp_path / "run", SALT)
    entry = next(x for x in manifest.datasets if x.dataset == "order_lines")
    n_paris = lines.filter(pl.col("site") == "PARIS").height
    assert entry.dropped_by_rule.get("filter") == n_paris
    assert entry.rows_out == lines.height - n_paris - entry.dropped_by_rule.get("R6", 0)


def test_receipts_without_pallets_are_derived_from_units_per_pallet(tmp_path: Path) -> None:
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory", "order_lines")
    receipts = pl.DataFrame(
        {
            "receipt_id": ["R1", "R1", "R2"],
            "receipt_ts": ["2024-03-04 07:30:00"] * 2 + ["2024-03-11 08:00:00"],
            "sku": ["S01", "S02", "ZZ"],
            "qty_units": ["80", "20", "400"],
        }
    )
    receipts.write_csv(tmp_path / "in" / "receipts.csv")
    inputs["receipts"] = InputSpec(files=[tmp_path / "in" / "receipts.csv"])
    ingest(inputs, tmp_path / "run", SALT)
    out = pl.read_parquet(tmp_path / "run" / "canonical" / "receipts.parquet")
    # base master: 1 unit per case × 40 cases per pallet; unknown SKU → default 400
    assert out["pallets"].to_list() == [2.0, 0.5, 1.0]


def test_mapping_file_missing_a_required_target_exits_2(tmp_path: Path) -> None:
    """A hand-edited mapping YAML is a trust boundary: dropping or misspelling a required
    target must stop with MappingError (exit 2), not empty the table and fail later on R9."""
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory", "order_lines")
    ingest(inputs, tmp_path / "first", SALT)
    mapping = load_mapping(tmp_path / "first" / "mapping" / "order_lines.yaml")
    without_qty = {k: v for k, v in mapping.columns.items() if k != "qty_units"}
    misspelt = {**without_qty, "quantity": mapping.columns["qty_units"]}
    for columns in (without_qty, misspelt):
        save_mapping(mapping.model_copy(update={"columns": columns}), tmp_path / "bad.yaml")
        spec = InputSpec(files=inputs["order_lines"].files, mapping=tmp_path / "bad.yaml")
        with pytest.raises(MappingError, match="qty_units") as e:
            ingest({**inputs, "order_lines": spec}, tmp_path / "run", SALT)
        assert e.value.exit_code == 2


def test_non_interactive_unit_hint_needs_a_decision_in_the_mapping(tmp_path: Path) -> None:
    """Step 6 (audit): a cm master with nobody to confirm stops with exit 2 instead of writing
    cm values as mm; once decided (confirmed, or unit_hints in the YAML) it is reused."""
    inputs = _write_base(tmp_path / "in", "inventory", "order_lines")
    master = _base("sku_master").with_columns(
        (pl.col(c).cast(pl.Float64) / 10).cast(pl.Utf8)
        for c in ("length_mm", "width_mm", "height_mm")
    )
    master.write_csv(tmp_path / "in" / "sku_master.csv")
    inputs["sku_master"] = InputSpec(files=[tmp_path / "in" / "sku_master.csv"])
    with pytest.raises(MappingError, match=r"W_UNITS_DIMS.*unit_hints") as e:
        ingest(inputs, tmp_path / "run", SALT)
    assert e.value.exit_code == 2 and not (tmp_path / "run" / "canonical").exists()
    yaml_path = tmp_path / "run" / "mapping" / "sku_master.yaml"  # written, still undecided
    with pytest.raises(MappingError, match="W_UNITS_DIMS"):
        ingest(inputs, tmp_path / "run", SALT)
    decided = load_mapping(yaml_path).model_copy(update={"unit_hints": {"dims": "cm"}})
    save_mapping(decided, yaml_path)  # the user's edit
    ingest(inputs, tmp_path / "run", SALT)  # non-interactive: the recorded decision is used
    out = pl.read_parquet(tmp_path / "run" / "canonical" / "sku_master.parquet")
    assert sorted(out["length_mm"].to_list())[:2] == pytest.approx([101.0, 102.0])


def test_incremental_ingest_keeps_the_order_lines_zone_and_merge_setting(tmp_path: Path) -> None:
    """Audit: a master-only ingest into the folder reset the study zone to Europe/Paris and
    merged duplicate (order, SKU) lines although the order_lines mapping says not to."""
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    lines = pl.concat([_base("order_lines"), pl.read_csv(RULES / "R6" / "order_lines.csv",
                                                          infer_schema=False)])  # fmt: skip
    lines.write_csv(tmp_path / "in" / "order_lines.csv")
    spec = InputSpec(files=[tmp_path / "in" / "order_lines.csv"])
    ingest({**inputs, "order_lines": spec}, tmp_path / "first", SALT)
    mapping = load_mapping(tmp_path / "first" / "mapping" / "order_lines.yaml")
    ny = mapping.model_copy(
        update={"timezone": "America/New_York", "merge_duplicate_sku_lines": False}
    )
    save_mapping(ny, tmp_path / "ny.yaml")
    run = tmp_path / "run"
    ingest({"order_lines": InputSpec(files=spec.files, mapping=tmp_path / "ny.yaml")}, run, SALT)
    ingest({"sku_master": inputs["sku_master"]}, run, SALT)  # order lines reloaded from run/
    path = run / "canonical" / "order_lines.parquet"
    assert pl.read_parquet_metadata(path)["local_tz"] == "America/New_York"
    o001 = pl.read_parquet(path).filter(pl.col("order_id") == hash_id("O001", SALT))
    assert sorted(o001["qty_units"].to_list()) == [2, 5]  # not merged
    rules = _dq(run)["rules"]
    assert isinstance(rules, list)
    r6 = next(r for r in rules if r["rule"] == "R6")
    assert r6["severity"] == "info" and r6["dropped"] == 0


# ---------------------------------------------------------------- audit round 2
def _flagged(out: Path) -> tuple[float, set[tuple[str, str]]]:
    report = _dq(out)
    rules = report["rules"]
    assert isinstance(rules, list) and isinstance(report["score"], float)
    flagged = {(r["rule"], r["dataset"]) for r in rules if r["severity"] in ("warning", "blocking")}
    return report["score"], flagged


def test_one_dataset_per_call_keeps_the_issues_of_earlier_datasets(tmp_path: Path) -> None:
    """`whsizing ingest --dataset X` one call per dataset: the reloaded order lines are already
    cleaned, so R3/R5 re-run on them found nothing and the final score rose from 90 to 100."""
    d = tmp_path / "in"
    inputs = _write_base(d, "sku_master", "inventory")
    extra = [pl.read_csv(RULES / r / "order_lines.csv", infer_schema=False) for r in ("R3", "R5")]
    pl.concat([_base("order_lines"), *extra]).write_csv(d / "order_lines.csv")
    inputs["order_lines"] = InputSpec(files=[d / "order_lines.csv"])
    ingest(inputs, tmp_path / "all", SALT)
    for ds in ("order_lines", "sku_master", "inventory"):
        ingest({ds: inputs[ds]}, tmp_path / "one", SALT)
    score, flagged = _flagged(tmp_path / "all")
    assert flagged == {("R3", "order_lines"), ("R5", "order_lines")} and score == 90.0
    assert _flagged(tmp_path / "one") == (score, flagged)


def _fr_master(df: pl.DataFrame) -> pl.DataFrame:
    dims = ("length_mm", "width_mm", "height_mm", "weight_kg")
    return df.with_columns(pl.col(c).str.replace(".", ",", literal=True) for c in dims)


def test_files_of_one_dataset_keep_their_own_decimal_mark(tmp_path: Path) -> None:
    """Edge case 'several files per dataset' (audit round 2): file 1's decimal ',' was recorded
    in the mapping and forced onto file 2 ('.'), whose dimensions all became null."""
    d = tmp_path / "in"
    inputs = _write_base(d, "inventory", "order_lines")
    master = _base("sku_master").with_columns(length_mm=pl.lit("309.5"))
    _fr_master(master.head(8)).write_csv(d / "m1.csv", separator=";")
    master.slice(8).write_csv(d / "m2.csv", separator=";")
    inputs["sku_master"] = InputSpec(files=[d / "m1.csv", d / "m2.csv"])
    for run in ("first", "first"):  # the second ingest reuses the persisted mapping
        manifest = ingest(inputs, tmp_path / run, SALT)
        out = pl.read_parquet(tmp_path / run / "canonical" / "sku_master.parquet")
        assert out["length_mm"].to_list() == [309.5] * master.height
        assert out["weight_kg"].null_count() == 0
    entry = next(x for x in manifest.datasets if x.dataset == "sku_master")
    assert [f.sniff.decimal for f in entry.files] == [",", "."]
    assert load_mapping(tmp_path / "first" / "mapping" / "sku_master.yaml").decimal is None


def _xlsx(path: Path, sheet: str, df: pl.DataFrame) -> None:
    wb = xlsxwriter.Workbook(path)
    ws = wb.add_worksheet(sheet)
    ws.write_row(0, 0, df.columns)
    for i, row in enumerate(df.rows()):
        ws.write_row(i + 1, 0, row)
    wb.close()


def test_auto_picked_excel_sheet_is_not_forced_on_the_next_file(tmp_path: Path) -> None:
    """Step 6 (audit round 2): the sheet picked for 'Articles 2024' was saved in the mapping
    and required in next year's file, whose sheet is 'Articles 2025' → exit 2."""
    d = tmp_path / "in"
    inputs = _write_base(d, "inventory", "order_lines")
    for year in (2024, 2025):
        _xlsx(d / f"master_{year}.xlsx", f"Articles {year}", _base("sku_master"))
        spec = InputSpec(files=[d / f"master_{year}.xlsx"])
        manifest = ingest({**inputs, "sku_master": spec}, tmp_path / "run", SALT)
        entry = next(x for x in manifest.datasets if x.dataset == "sku_master")
        assert entry.files[0].sniff.sheet == f"Articles {year}"
    assert load_mapping(tmp_path / "run" / "mapping" / "sku_master.yaml").sheet is None


def test_dot_grouped_quantities_in_a_dot_file_are_counted_in_the_dq_note(tmp_path: Path) -> None:
    """I54 (amended, F2d): in an integer-only ',' file the thousands-only shapes are left out
    and the delimiter decides '.'; '1.200' is 1.2, not a whole number → null, dropped by REQ.
    Audit F2c round 1: '2.000' is read as 2 and was missing from the note; the note counts
    both. `decimal: ','` in the mapping reads them as 1200 and 2000."""
    d = tmp_path / "in"
    inputs = _write_base(d, "sku_master", "inventory")
    row = pl.int_range(pl.len()) % 10
    qty = pl.when(row == 0).then(pl.lit("1.200")).when(row == 5).then(pl.lit("2.000"))
    lines = _base("order_lines").with_columns(qty_units=qty.otherwise(pl.col("qty_units")))
    n_1200 = lines.filter(pl.col("qty_units") == "1.200").height
    n_2000 = lines.filter(pl.col("qty_units") == "2.000").height
    lines.write_csv(d / "order_lines.csv")
    inputs["order_lines"] = InputSpec(files=[d / "order_lines.csv"])
    manifest = ingest(inputs, tmp_path / "run", SALT)
    entry = next(x for x in manifest.datasets if x.dataset == "order_lines")
    assert entry.files[0].sniff.decimal == "." and entry.dropped_by_rule["REQ"] == n_1200
    out = pl.read_parquet(tmp_path / "run" / "canonical" / "order_lines.parquet")
    assert out["qty_units"].max() == 3  # neither 1200 nor 2000
    assert ("REQ", "order_lines") in _flagged(tmp_path / "run")[1]
    notes = _dq(tmp_path / "run")["notes"]
    assert isinstance(notes, list)
    note = next(n for n in notes if n.startswith("[order_lines]"))
    assert f"{n_1200} values are not whole numbers" in note and "decimal: ','" in note
    assert f"{n_2000} values such as '2.000' look like thousands" in note
    mapping = load_mapping(tmp_path / "run" / "mapping" / "order_lines.yaml")
    save_mapping(mapping.model_copy(update={"decimal": ","}), tmp_path / "fixed.yaml")
    spec = InputSpec(files=[d / "order_lines.csv"], mapping=tmp_path / "fixed.yaml")
    manifest = ingest({**inputs, "order_lines": spec}, tmp_path / "fixed", SALT)
    entry = next(x for x in manifest.datasets if x.dataset == "order_lines")
    assert "REQ" not in entry.dropped_by_rule and entry.files[0].sniff.decimal == ","
    out = pl.read_parquet(tmp_path / "fixed" / "canonical" / "order_lines.parquet")
    assert out.filter(pl.col("qty_units") == 1200).height == n_1200
    assert out.filter(pl.col("qty_units") == 2000).height == n_2000
    notes = _dq(tmp_path / "fixed")["notes"]
    assert isinstance(notes, list) and not [n for n in notes if n.startswith("[order_lines]")]


def test_unreadable_numbers_are_explained_in_the_dq_report(tmp_path: Path) -> None:
    """I54 tie-break (F2d): a ';' stock file whose only separator values are '1,500' (US
    thousands, a thousands-only shape) is read as a FR export ',' → 1.5, not whole → null.
    The lost values must not be silent: a note names the column and the `decimal: '.'` fix."""
    d = tmp_path / "in"
    inputs = _write_base(d, "sku_master", "order_lines")
    stock = _base("inventory").with_columns(qty_units=pl.lit("1,500"))
    stock.write_csv(d / "inventory.csv", separator=";")
    inputs["inventory"] = InputSpec(files=[d / "inventory.csv"])
    ingest(inputs, tmp_path / "run", SALT)
    notes = _dq(tmp_path / "run")["notes"]
    assert isinstance(notes, list)
    note = next(n for n in notes if n.startswith("[inventory]"))
    assert f"{stock.height} values" in note and "decimal: '.'" in note


def test_negative_receipt_pallets_are_derived_not_a_crash(tmp_path: Path) -> None:
    """Audit round 2: pallets = -1 reached Pandera and ended in exit 1 ('unhandled failure')."""
    d = tmp_path / "in"
    inputs = _write_base(d, "sku_master", "inventory", "order_lines")
    pl.DataFrame({"receipt_id": ["R1", "R2"], "receipt_ts": ["2024-03-04 07:30:00"] * 2,
                  "sku": ["S01", "S02"], "qty_units": ["80", "20"],
                  "pallets": ["-1", "2"]}).write_csv(d / "receipts.csv")  # fmt: skip
    inputs["receipts"] = InputSpec(files=[d / "receipts.csv"])
    ingest(inputs, tmp_path / "run", SALT)
    out = pl.read_parquet(tmp_path / "run" / "canonical" / "receipts.parquet")
    assert out["pallets"].to_list() == [2.0, 2.0]  # 80 units / 40 per pallet, and as given
    assert ("REQ", "receipts") in _flagged(tmp_path / "run")[1]


def test_header_only_file_says_it_has_no_data_rows(tmp_path: Path) -> None:
    inputs = _write_base(tmp_path / "in", "sku_master", "inventory")
    path = tmp_path / "in" / "order_lines.csv"
    path.write_text(",".join(_base("order_lines").columns) + "\n", encoding="utf-8")
    with pytest.raises(MappingError, match="no data rows") as e:
        ingest({**inputs, "order_lines": InputSpec(files=[path])}, tmp_path / "run", SALT)
    assert e.value.exit_code == 2


# ---------------------------------------------------------------- F2d: I54 amendment
@pytest.mark.parametrize("profile_name", ["b2b_cases", "ecom_mid"])
def test_T2_3_synthetic_stock_counts_with_grouped_thousands_are_read(
    profile_name: str, tmp_path: Path
) -> None:
    """F2c open issue (F2d): the F1 stock exports are integer-only, '1.234' (FR, ';') and
    '1,234' (EN, ','). Under the verbatim regex they sniffed the wrong mark and REQ dropped
    every grouped count (b2b_cases 176 of 8,000 rows, ecom_mid 18 of 20,000, seed 3, 150 days).
    I54 amended: thousands-only shapes are left out, the delimiter decides → every count reads
    as generated (sign aside: the negative-quantity defect)."""
    profile = load_synth_profile(PROFILES / f"{profile_name}.yaml")
    profile = profile.model_copy(update={"n_days": 150})
    frames = generate(profile, seed=3)
    export(frames, tmp_path, ("csv_fr", "csv_en"), defects=profile.defects, seed=3)
    truth = frames["inventory"]["qty_units"].abs()
    for lang, col, mark, other in (("fr", "Qté", ",", "."), ("en", "Quantity", ".", ",")):
        raw = read_any(tmp_path / f"csv_{lang}" / "inventory.csv")
        assert raw.sniff.decimal == mark
        values = raw.df[col]
        read = raw.df.select(parse_int(pl.col(col), mark)).to_series()
        lost_before = raw.df.select(parse_int(pl.col(col), other).is_null()).to_series().sum()
        assert lost_before > 0  # the file has grouped counts that the other mark loses
        assert read.null_count() == values.null_count() == 0
        assert read.abs().to_list() == truth.to_list()


# ---------------------------------------------------------------- F2e: I67 step 4
def _tie_break_notes(out: Path) -> list[str]:
    notes = _dq(out)["notes"]
    assert isinstance(notes, list)
    return [n for n in notes if "chosen by the field delimiter" in n]


def test_T2_3_semicolon_file_of_dot_3_decimal_weights_carries_a_tie_break_warning(
    tmp_path: Path,
) -> None:
    """F2d open issue 1 (I67 step 4): in a ';' master whose only separator values are
    '1.250' weights among integers, the I54 tie-break reads 1.250 kg as 1250 kg, which no
    rule catches (R8: < 1500 kg; W_UNITS_WEIGHT: median 4 kg). The DQ report now says so:
    file, mark, examples as read, `decimal:` override. The guess is not recorded in the
    mapping, so a re-ingest warns again; `decimal: '.'` reads 1.25 kg and silences it."""
    d = tmp_path / "in"
    inputs = _write_base(d, "inventory", "order_lines")
    w = ["2", "5", "10", "1.250", "3", "4"]
    master = _base("sku_master").with_columns(weight_kg=pl.Series([w[i % 6] for i in range(20)]))
    master.write_csv(d / "articles.csv", separator=";")
    inputs["sku_master"] = InputSpec(files=[d / "articles.csv"])
    for _ in range(2):  # the second ingest reuses the persisted mapping
        manifest = ingest(inputs, tmp_path / "run", SALT)
        [note] = _tie_break_notes(tmp_path / "run")
        assert note.startswith("[sku_master] articles.csv: warning, decimal mark ','")
        assert "delimiter ';'" in note and "'1.250' (weight_kg) → 1250." in note
        assert "set decimal: '.' in mapping/sku_master.yaml" in note
        out = pl.read_parquet(tmp_path / "run" / "canonical" / "sku_master.parquet")
        assert sorted(set(out["weight_kg"].to_list())) == [2, 3, 4, 5, 10, 1250]
        entry = next(x for x in manifest.datasets if x.dataset == "sku_master")
        assert entry.files[0].sniff.decimal_by_delimiter
        assert load_mapping(tmp_path / "run" / "mapping" / "sku_master.yaml").decimal is None
    mapping = load_mapping(tmp_path / "run" / "mapping" / "sku_master.yaml")
    save_mapping(mapping.model_copy(update={"decimal": "."}), tmp_path / "dot.yaml")
    spec = InputSpec(files=[d / "articles.csv"], mapping=tmp_path / "dot.yaml")
    manifest = ingest({**inputs, "sku_master": spec}, tmp_path / "dot", SALT)
    assert _tie_break_notes(tmp_path / "dot") == []
    out = pl.read_parquet(tmp_path / "dot" / "canonical" / "sku_master.parquet")
    assert sorted(set(out["weight_kg"].to_list())) == [1.25, 2, 3, 4, 5, 10]
    # a FR master whose comma decimals show the mark: no warning
    _fr_master(_base("sku_master")).write_csv(d / "fr.csv", separator=";")
    ingest({**inputs, "sku_master": InputSpec(files=[d / "fr.csv"])}, tmp_path / "fr", SALT)
    assert _tie_break_notes(tmp_path / "fr") == []


def test_T2_3_one_tie_break_file_among_several_keeps_the_mark_unrecorded(tmp_path: Path) -> None:
    """I67 step 4, several files per dataset (F2e audit mutant agreed_any_to_all): m1's comma
    decimals decide ',', m2 (integers and '1.250') gets ',' from the tie-break. Both files
    agree on ',', but the mark is not saved in the mapping because one file only guessed it,
    so the next ingest still warns about m2, and only about m2."""
    d = tmp_path / "in"
    inputs = _write_base(d, "inventory", "order_lines")
    base = _base("sku_master")
    _fr_master(base.head(8)).write_csv(d / "m1.csv", separator=";")
    w = ["2", "5", "10", "1.250", "3", "4"]
    m2 = base.slice(8).with_columns(weight_kg=pl.Series([w[i % 6] for i in range(12)]))
    m2.write_csv(d / "m2.csv", separator=";")
    inputs["sku_master"] = InputSpec(files=[d / "m1.csv", d / "m2.csv"])
    for _ in range(2):  # the second ingest reuses the persisted mapping
        manifest = ingest(inputs, tmp_path / "run", SALT)
        entry = next(x for x in manifest.datasets if x.dataset == "sku_master")
        assert [(f.sniff.decimal, f.sniff.decimal_by_delimiter) for f in entry.files] == [
            (",", False),
            (",", True),
        ]
        assert load_mapping(tmp_path / "run" / "mapping" / "sku_master.yaml").decimal is None
        [note] = _tie_break_notes(tmp_path / "run")
        assert note.startswith("[sku_master] m2.csv: warning, decimal mark ','")
