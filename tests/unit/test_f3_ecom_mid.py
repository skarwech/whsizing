"""F3 on the full ecom_mid synthetic dataset (≈ 1 M order lines): T3.6 and T3.8."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import polars as pl
import pytest

from whsizing.profile import build_profile, build_tables
from whsizing.schemas import ProfileCfg
from whsizing.synth import generate, load_synth_profile

ROOT = Path(__file__).resolve().parents[2]
BUDGET_S = 60.0  # T3.8 / C5

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def ecom_mid(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("ecom_mid")
    frames = generate(load_synth_profile(ROOT / "data/synth/profiles/ecom_mid.yaml"), seed=42)
    for name, df in frames.items():
        df.write_parquet(out / f"{name}.parquet")
    return out


def test_T3_6_operating_days_exclude_sundays_in_ecom_mid(ecom_mid: Path) -> None:
    t = build_tables(ecom_mid, None, ProfileCfg())
    sundays = t.daily.filter(weekday=6)
    assert sundays.height >= 100  # two years of calendar
    assert not sundays["is_operating"].any()
    workdays = t.daily.filter((t.daily["weekday"] < 5) & ~t.daily["is_holiday"])
    # Mon-Fri non-holidays are operating
    assert float(workdays["is_operating"].mean()) > 0.99  # pyright: ignore[reportArgumentType]


@pytest.mark.bench
def test_T3_8_one_million_lines_profiled_under_60_s(ecom_mid: Path) -> None:
    """T3.8 / C5 profile row: ≥ 1 M canonical order lines in (1,030,012; 981,910 shipped after I1).
    A bench test (R8c): `just bench` and the CI bench job measure the 60 s budget; the normal
    test job (`-m "not bench"`) no longer runs it."""
    n_in = pl.scan_parquet(ecom_mid / "order_lines.parquet").select(pl.len()).collect().item()
    assert n_in >= 1_000_000
    t0 = time.perf_counter()
    p = build_profile(ecom_mid, None, ProfileCfg())
    elapsed = time.perf_counter() - t0
    print(f"T3.8 build_profile on ecom_mid: {elapsed:.2f} s")
    # sanity, not the T3.8 bar (n_in above): the bulk is shipped and profiled (95.3 % here)
    assert p.daily["lines"].mean * p.operating_days > 0.9 * n_in
    assert elapsed < BUDGET_S
    assert 6 not in p.intraday and p.seasonality.weekday_index[6] == 0.0


def test_T3_7_shuffled_ecom_mid_gives_a_bit_identical_profile(
    ecom_mid: Path, tmp_path: Path
) -> None:
    """Principle 5 at 1 M lines: shuffled tables and a rerun give the same profile to the bit
    (float sums in group order varied in the last ULP before the sort / maintain_order fix)."""
    for f in ecom_mid.glob("*.parquet"):
        pl.read_parquet(f).sample(fraction=1.0, shuffle=True, seed=11).write_parquet(
            tmp_path / f.name
        )
    base = build_profile(ecom_mid, None, ProfileCfg()).model_dump()
    assert build_profile(tmp_path, None, ProfileCfg()).model_dump() == base
    assert build_profile(ecom_mid, None, ProfileCfg()).model_dump() == base


DUMP = (
    "import sys; from pathlib import Path; from whsizing.profile import build_profile; "
    "from whsizing.schemas import ProfileCfg; "
    "Path(sys.argv[2]).write_text(build_profile(Path(sys.argv[1]), None, ProfileCfg())"
    ".model_dump_json())"
)


def test_T3_7_profile_json_identical_across_polars_thread_counts(
    ecom_mid: Path, tmp_path: Path
) -> None:
    """Principle 5 across machines: POLARS_MAX_THREADS (read at import, hence subprocesses)
    must not change a byte of the profile. Before the exact per-group sums, threads 1 and 2
    gave eiq.weight_per_order_kg.p95 6.281000000000001 against 6.281 by default (F3c); before
    the exact whole-column sums, 64 threads (sorted SKU table in 256-row chunks) moved
    stock.avg_units (F3d). The fast tiny_golden variant is in tests/property."""
    out = {}
    for threads in ("1", "2", "64", None):
        env = {k: v for k, v in os.environ.items() if k != "POLARS_MAX_THREADS"}
        if threads is not None:
            env["POLARS_MAX_THREADS"] = threads
        path = tmp_path / f"profile_{threads or 'default'}.json"
        subprocess.run([sys.executable, "-c", DUMP, str(ecom_mid), str(path)], env=env, check=True)
        out[threads] = path.read_bytes()
    assert out["1"] == out["2"] == out["64"] == out[None]
