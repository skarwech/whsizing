"""T3.7 property: shuffling the rows of the canonical tables leaves the profile unchanged."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import polars as pl
from hypothesis import example, given, settings
from hypothesis import strategies as st

from whsizing.config import load_yaml_model
from whsizing.profile import build_profile
from whsizing.schemas import DesignBasis, ProfileCfg

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
TABLES = ("order_lines", "sku_master", "inventory", "receipts")
BASIS = load_yaml_model(GOLDEN / "golden_basis.yaml", DesignBasis)
CFG = ProfileCfg()


def _frames() -> dict[str, pl.DataFrame]:
    """tiny_golden, with every 7th order line 30 h later: multi-day orders (first ts wins)."""
    frames = {n: pl.read_parquet(GOLDEN / "tiny_golden" / f"{n}.parquet") for n in TABLES}
    late = pl.col("order_ts") + pl.duration(hours=30)
    frames["order_lines"] = frames["order_lines"].with_columns(
        order_ts=pl.when(pl.col("source_row") % 7 == 0).then(late).otherwise("order_ts")
    )
    return frames


def profile_of(frames: dict[str, pl.DataFrame]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        for name, df in frames.items():
            df.write_parquet(Path(tmp) / f"{name}.parquet")
        return build_profile(Path(tmp), BASIS, CFG).model_dump()


FRAMES = _frames()
BASELINE = profile_of(FRAMES)


def diff(a: Any, b: Any, path: str = "") -> list[str]:
    """Paths where two model_dump trees differ, exactly: floats too (principle 5, bit-identical
    reruns), so every float sum must run in a row-order-independent order."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [f"{path}: keys {sorted(a)} != {sorted(b)}"]
        return [d for k in a for d in diff(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [
            d for i, (x, y) in enumerate(zip(a, b, strict=True)) for d in diff(x, y, f"{path}[{i}]")
        ]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def shuffled(seed: int) -> dict[str, pl.DataFrame]:
    return {
        name: df.sample(fraction=1.0, shuffle=True, seed=(seed + i) % 2**32)
        for i, (name, df) in enumerate(FRAMES.items())
    }


@settings(max_examples=8, deadline=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@example(seed=531)  # F3d audit: failed at 12 threads (one unit cube 1 ULP off)
def test_T3_7_shuffling_rows_leaves_profile_unchanged(seed: int) -> None:
    assert not diff(profile_of(shuffled(seed)), BASELINE)


DUMP = (
    "import sys; from pathlib import Path; from whsizing.config import load_yaml_model; "
    "from whsizing.profile import build_profile; from whsizing.schemas import DesignBasis, "
    "ProfileCfg; b = load_yaml_model(Path(sys.argv[2]), DesignBasis); "
    "print(build_profile(Path(sys.argv[1]), b, ProfileCfg()).model_dump_json())"
)


def test_T3_7_profile_identical_across_polars_thread_counts(tmp_path: Path) -> None:
    """Principle 5 across machines (F3d audit). POLARS_MAX_THREADS is read at import, hence
    subprocesses. At 12 threads the validated 100-row sku_master came in chunks of 9 x 11 + 1,
    and polars divides a length-1 chunk by 1e9 exactly but the others by a reciprocal
    multiply: one unit cube moved by 1 ULP. 64 threads covers the high-count regime."""
    for name, df in shuffled(531).items():
        df.write_parquet(tmp_path / f"{name}.parquet")
    out = set()
    for threads in ("1", "12", "64"):
        env = os.environ | {"POLARS_MAX_THREADS": threads}
        cmd = [sys.executable, "-c", DUMP, str(tmp_path), str(GOLDEN / "golden_basis.yaml")]
        out.add(subprocess.run(cmd, env=env, check=True, capture_output=True, text=True).stdout)
    assert len(out) == 1
