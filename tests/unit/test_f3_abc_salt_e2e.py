"""F3f end to end (T3.7 family, kept under tests/unit with the other F3 tests): the same
synthetic export ingested with two anonymisation salts gives the same demand profile on every
field that carries no hashed id (I6 amended)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from whsizing.io import ingest
from whsizing.profile import build_profile
from whsizing.schemas import ProfileCfg
from whsizing.schemas.project import InputSpec
from whsizing.synth import export, generate, load_synth_profile

PROFILES = Path(__file__).resolve().parents[2] / "data" / "synth" / "profiles"
DATASETS = ("sku_master", "inventory", "receipts", "order_lines")
# With np.mean / np.std these two salts differ in the last ULP of eiq.weight_per_order_kg (R6)
SALTS = (b"salt-0", b"salt-1")
SKU_ID_FIELDS = {"dataset_hash"}  # sha256 of the canonical tables, which hold the hashed ids


def _same(a: Any, b: Any, path: str = "") -> list[str]:
    """Paths where two JSON trees differ: every number bit for bit (R6: `series_stats` sums
    exactly, so the EIQ stats no longer move with the salt in the last ULP)."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [f"{path}: keys {sorted(a)} != {sorted(b)}"]
        return [d for k in a for d in _same(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        pairs = enumerate(zip(a, b, strict=True))
        return [d for i, (x, y) in pairs for d in _same(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def _profile_json(csv_dir: Path, salt: bytes, out: Path) -> tuple[dict[str, Any], set[str]]:
    """Ingest the CSV export with `salt`, profile it, write and re-read demand_profile.json.
    Returns the JSON and the hashed sku ids of the run."""
    ingest({ds: InputSpec(files=[csv_dir / f"{ds}.csv"]) for ds in DATASETS}, out, salt)
    profile = build_profile(out / "canonical", None, ProfileCfg())
    path = out / "profile" / "demand_profile.json"
    path.parent.mkdir()
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    doc = json.loads(path.read_text(encoding="utf-8"))
    ids = set(pl.read_parquet(out / "canonical" / "sku_master.parquet")["sku"].to_list())
    return doc, ids


@pytest.fixture(scope="module")
def two_salts(tmp_path_factory: pytest.TempPathFactory) -> list[tuple[dict[str, Any], set[str]]]:
    """A small ecom_mid (many SKUs sharing a line count, so the long tail ties across B / C)."""
    root = tmp_path_factory.mktemp("salts")
    profile = load_synth_profile(PROFILES / "ecom_mid.yaml")
    profile = profile.model_copy(update={"n_days": 120, "n_skus": 250})
    export(generate(profile, seed=7), root, ("csv_fr",))
    return [_profile_json(root / "csv_fr", s, root / f"run{i}") for i, s in enumerate(SALTS)]


def test_T3_7_profile_json_does_not_depend_on_the_anonymisation_salt(
    two_salts: list[tuple[dict[str, Any], set[str]]],
) -> None:
    (one, ids_one), (two, ids_two) = two_salts
    assert len(ids_one) == len(ids_two) == 250
    assert not ids_one & ids_two, "the two salts must give different sku ids"
    assert one["dataset_hash"] != two["dataset_hash"]  # the hashed tables do differ ...
    assert one["abc"]["by_lines"]["C"]["n_skus"] > 0 and len(one["abc"]["pareto_lines"]) == 100
    salt_free = [{k: v for k, v in d.items() if k not in SKU_ID_FIELDS} for d in (one, two)]
    assert (
        _same(salt_free[0], salt_free[1]) == []
    )  # ... the rest does not: classes, shares, stock, ...
