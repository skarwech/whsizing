"""C3 syrupy snapshots (audit M6): numeric drift across code changes is caught, not only
determinism within one tree.

Two snapshots, both in `tests/e2e/__snapshots__/test_snapshots.ambr`, numbers rounded to 6
significant digits so float noise (a different salt moves floats by about 1e-15) never matters:

- the golden layer: the typical-world trace of S0 and S2 on tiny_golden (F3 build_tables ->
  profile -> I58 sku_frame -> F4 design day -> `size_scenario` -> `compute_finance`), key -> value;
- the E2E layer: `comparison/comparison.json` of `run_scenarios` on synthetic ecom_mid with the
  example project, basis, scenarios and catalog.

A change that moves a number fails here until `just golden-update` (that is `pytest
tests/e2e/test_snapshots.py --snapshot-update`) is run and its diff reviewed.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from syrupy.assertion import SnapshotAssertion

from whsizing.catalog import load_catalog
from whsizing.config import load_project, load_yaml_model
from whsizing.design import load_basis, select_design_day
from whsizing.engine import size_scenario, sku_frame
from whsizing.finance import compute_finance
from whsizing.profile import build_tables, profile_from_tables
from whsizing.scenarios import run_scenarios
from whsizing.schemas import ProfileCfg, ScenarioResult, ScenarioSet
from whsizing.schemas.project import InputSpec
from whsizing.schemas.trace import Tracer
from whsizing.synth import synthesize

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"
DATASETS = ("order_lines", "sku_master", "inventory", "receipts")
SIGNIFICANT_DIGITS = 6
NOISE_FLOOR = 1e-9  # a float this small is rounding noise around zero, never a quantity


def rounded(value: Any) -> Any:
    """`value` (parsed JSON or a dict of numbers) with every float at 6 significant digits and
    noise around zero as 0.0; ints, bools, strings and None are kept as they are."""
    if isinstance(value, bool) or value is None or isinstance(value, int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or abs(value) < NOISE_FLOOR:
            return value if not math.isfinite(value) else 0.0
        return float(f"{value:.{SIGNIFICANT_DIGITS}g}")
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list | tuple):
        return [rounded(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    raise TypeError(f"cannot snapshot a {type(value).__name__}")


def test_rounded_is_stable_under_float_noise() -> None:
    a = {"x": [1234567.8912, 0.1 + 0.2, -1e-17], "n": 3, "ok": True, "s": "S1", "none": None}
    b = {"x": [1234567.8913, 0.3, 4e-16], "n": 3, "ok": True, "s": "S1", "none": None}
    assert rounded(a) == rounded(b) == {
        "x": [1234570.0, 0.3, 0.0], "n": 3, "ok": True, "s": "S1", "none": None,
    }  # fmt: skip
    assert rounded(1234565.0) != rounded(1234575.0)  # a real change of 1e-5 relative shows


# ------------------------------------------------------------------ golden layer (tiny_golden)
@pytest.fixture(scope="module")
def golden_typ_nodes() -> dict[str, float]:
    """Typical-world trace nodes of S0 and S2: sizing, then finance (S2 against S0, I42)."""
    basis = load_basis(GOLDEN / "golden_basis.yaml")
    cfg = ProfileCfg()
    t = build_tables(GOLDEN / "tiny_golden", basis, cfg)
    profile = profile_from_tables(t, cfg)
    sku = sku_frame(t, pl.read_parquet(GOLDEN / "tiny_golden" / "sku_master.parquet"))
    catalog = load_catalog(ROOT / "catalog")
    dd = select_design_day(profile, basis, t.daily, sku=sku, catalog=catalog)
    results: dict[str, ScenarioResult] = {}
    tracers: dict[str, Tracer] = {}
    for s in load_yaml_model(GOLDEN / "golden_scenarios.yaml", ScenarioSet).scenarios:
        tracers[s.id] = Tracer(s.id)
        results[s.id] = size_scenario(
            profile, basis, dd, s, catalog, sku, t.daily, tracers[s.id], lines=t.lines
        )
    compute_finance(
        results["S0"], basis, catalog, None, daily=t.daily, tracer=tracers["S0"],
        client_baseline=False,
    )  # fmt: skip
    compute_finance(
        results["S2"], basis, catalog, results["S0"], daily=t.daily, tracer=tracers["S2"],
        baseline_tracer=tracers["S0"],
    )  # fmt: skip
    return {n.id: n.value for sid in ("S0", "S2") for n in tracers[sid].nodes if n.world == "typ"}


def test_golden_layer_typical_world_of_tiny_golden_matches_its_snapshot(
    golden_typ_nodes: dict[str, float], snapshot: SnapshotAssertion
) -> None:
    table = {k: golden_typ_nodes[k] for k in sorted(golden_typ_nodes)}
    assert len(table) > 200  # S0 and S2: sizing, labor, area, capex, opex, finance
    assert {k.split(".")[0] for k in table} == {"S0", "S2"}
    assert rounded(table) == snapshot


# ------------------------------------------------------------------ E2E layer (ecom_mid)
@pytest.fixture(scope="module")
def ecom_mid_comparison(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """`comparison/comparison.json` (parsed) of the example scenarios on synthetic ecom_mid."""
    out = tmp_path_factory.mktemp("snapshot_ecom_mid")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("WHSIZING_SALT", "snapshot-salt")
        synthesize(
            ROOT / "data" / "synth" / "profiles" / "ecom_mid.yaml", out / "ecom_mid", seed=42
        )
        data = out / "ecom_mid" / "csv_en"
        project = load_project(ROOT / "project" / "example_project.yaml").model_copy(
            update={
                "out_dir": out / "runs",
                "inputs": {ds: InputSpec(files=[data / f"{ds}.csv"]) for ds in DATASETS},
            }
        )
        run = run_scenarios(project)
    yield json.loads((run.run_dir / "comparison" / "comparison.json").read_text(encoding="utf-8"))


@pytest.mark.slow
def test_e2e_layer_ecom_mid_comparison_json_matches_its_snapshot(
    ecom_mid_comparison: Any, snapshot: SnapshotAssertion
) -> None:
    rows = ecom_mid_comparison["rows"]
    assert [r["scenario_id"] for r in rows] == ["S0", "S1", "S2"]
    assert all(r["status"] == "computed" and r["tco"]["typ"] > 0 for r in rows)
    assert rounded(ecom_mid_comparison) == snapshot
