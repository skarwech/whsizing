"""R6 remediation of the F2 findings: a parquet input under a folder with glob characters (I75 i),
and a binary or garbage file that must be a MappingError (exit 2) naming the file, never the raw
polars ValueError of a multi-byte separator (exit 1)."""

from __future__ import annotations

import random
from pathlib import Path

import polars as pl
import pytest

from whsizing.errors import ConfigError, MappingError
from whsizing.io import ingest, read_any, sniff
from whsizing.io.readers import read_parquet_file
from whsizing.schemas.ingest import Mapping
from whsizing.schemas.project import InputSpec

WEIRD = "client [2025] *x?"  # every glob character of fnmatch


def garbage(seed: int, folder: Path) -> Path:
    """4000 pseudo-random bytes (`head -c 4000 /dev/urandom`, but repeatable) in `g.csv`."""
    path = folder / "g.csv"
    path.write_bytes(random.Random(seed).randbytes(4000))
    return path


# ------------------------------------------------------------------ I75 i: parquet input
def test_I75_i_read_any_reads_a_parquet_input_under_a_folder_with_glob_characters(
    tmp_path: Path,
) -> None:
    """Was: a raw polars ComputeError (`_read_parquet` read the path as a glob)."""
    path = tmp_path / WEIRD / "stock.parquet"
    path.parent.mkdir()
    pl.DataFrame({"sku": ["A", "B", "C"], "qty": [1, 2, 3]}).write_parquet(path)
    raw = read_any(path)
    assert raw.columns == ["sku", "qty"]
    assert raw.df["qty"].to_list() == ["1", "2", "3"]
    assert read_parquet_file(path).height == 3  # the helper moved to io.readers, same behaviour


def test_I75_i_ingest_takes_a_parquet_sku_master_from_a_folder_with_glob_characters(
    tmp_path: Path,
) -> None:
    csv = (
        Path(__file__).resolve().parents[1] / "golden" / "tiny_golden" / "csv_en" / "sku_master.csv"
    )
    path = tmp_path / WEIRD / "sku_master.parquet"
    path.parent.mkdir()
    pl.read_csv(csv, infer_schema=False).write_parquet(path)
    ingest({"sku_master": InputSpec(files=[path])}, tmp_path / "run", b"salt")
    canonical = read_parquet_file(tmp_path / "run" / "canonical" / "sku_master.parquet")
    assert canonical.height == pl.read_csv(csv, infer_schema=False).height


def test_I75_i_the_helper_is_still_importable_from_ingest() -> None:
    from whsizing.io.ingest import read_parquet_file as from_ingest

    assert from_ingest is read_parquet_file


# ------------------------------------------------------------------ R6.2: binary files
@pytest.mark.parametrize("seed", [7, 9, 10])
def test_R6_2_a_sniffed_multi_byte_separator_is_a_mapping_error_naming_the_file(
    seed: int, tmp_path: Path
) -> None:
    """Was: `ValueError: separator="\\x96" should be a single byte character` out of pl.read_csv
    (about one random file in six), exit 1. These seeds all sniff a multi-byte delimiter."""
    path = garbage(seed, tmp_path)
    with pytest.raises(MappingError, match=r"g\.csv: not a readable CSV.*sniffed delimiter") as e:
        read_any(path)
    assert e.value.exit_code == 2


def test_R6_2_a_file_without_a_header_row_names_the_file(tmp_path: Path) -> None:
    """The sniffer's 'no header row found' did not say which file (several inputs per dataset)."""
    with pytest.raises(MappingError, match=r"g\.csv: no header row found"):
        read_any(garbage(13, tmp_path))


def test_R6_2_a_saved_delimiter_of_more_than_one_byte_is_a_config_error(tmp_path: Path) -> None:
    csv = tmp_path / "a.csv"
    csv.write_text("sku;qty;name\nA;1;x\nB;2;y\n", encoding="utf-8")
    mapping = Mapping(dataset="sku_master", delimiter="é", columns={"sku": "sku"})
    with pytest.raises(ConfigError, match="one-byte delimiter"):
        read_any(csv, mapping=mapping)


def test_R6_2_the_public_sniff_of_a_csv_has_the_same_guards_as_read_any(tmp_path: Path) -> None:
    """Audit R6 low: `sniff(path)` returned a 2-byte delimiter (seed 7) and its 'no header row'
    error did not name the file (seed 13); only read_any guarded."""
    folder = tmp_path / "a"
    folder.mkdir()
    with pytest.raises(MappingError, match=r"g\.csv: not a readable CSV.*sniffed delimiter"):
        sniff(garbage(7, folder))
    with pytest.raises(MappingError, match=r"g\.csv: no header row found"):
        sniff(garbage(13, folder))


# ------------------------------------------------------------------ R6.2b: corrupt parquet
def _truncated(folder: Path) -> Path:
    good = folder / "good.parquet"
    pl.DataFrame({"sku": ["A", "B"], "qty": [1, 2]}).write_parquet(good)
    path = folder / "truncated.parquet"
    path.write_bytes(good.read_bytes()[:-20])  # footer cut off
    return path


@pytest.mark.parametrize("kind", ["empty", "garbage", "magic_only", "random_framed", "truncated"])
def test_R6_2_a_corrupt_parquet_is_a_mapping_error_naming_the_file(
    kind: str, tmp_path: Path
) -> None:
    """Was: the raw polars ComputeError (or a pyo3 PanicException for some bit flips), exit 1,
    run folder left behind; the R6.2 guard only covered CSV."""
    path = tmp_path / f"{kind}.parquet"
    payloads = {
        "empty": b"",
        "garbage": b"garbage",
        "magic_only": b"PAR1",
        "random_framed": b"PAR1" + random.Random(1).randbytes(500) + b"PAR1",
    }
    if kind == "truncated":
        path = _truncated(tmp_path)
    else:
        path.write_bytes(payloads[kind])
    with pytest.raises(MappingError, match=rf"{path.name}: not a readable Parquet file") as e:
        read_any(path)
    assert e.value.exit_code == 2


def test_R6_2_a_parquet_with_a_nested_column_is_a_mapping_error(tmp_path: Path) -> None:
    """The text cast of a List column raised InvalidOperationError (exit 1)."""
    path = tmp_path / "nested.parquet"
    pl.DataFrame({"sku": ["A"], "tags": [[1, 2]]}).write_parquet(path)
    with pytest.raises(MappingError, match=r"nested\.parquet: not a readable Parquet file"):
        read_any(path)
