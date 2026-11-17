"""F5 eligibility: T5.2 orientation, T5.3 golden shares, T5.4 missing dims, shares and bin fit."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
import yaml

from whsizing.catalog import (
    assumed_mask,
    eligibility_shares,
    eligible_mask,
    load_catalog,
    units_per_bin,
)
from whsizing.catalog.models import Family
from whsizing.errors import WhsizingError
from whsizing.schemas import EligibilityCfg, ScenarioSet

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/golden/golden_values.json"
SCENARIOS = ROOT / "tests/golden/golden_scenarios.yaml"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(ROOT / "catalog")


def _sku(*rows: tuple, **extra: list) -> pl.DataFrame:
    """rows of (length_mm, width_mm, height_mm, weight_kg); extra columns by keyword."""
    cols = ["length_mm", "width_mm", "height_mm", "weight_kg"]
    data = {c: [r[i] for r in rows] for i, c in enumerate(cols)}
    return pl.DataFrame(data, schema={c: pl.Float64 for c in cols}).with_columns(
        **{k: pl.Series(v) for k, v in extra.items()}
    )


def test_T5_2_orientation_agnostic(catalog) -> None:
    cube = catalog.families["cube_asrs"]  # max_item_mm [600, 400, 300]
    sku = _sku((300, 600, 400, 5), (400, 300, 600, 5), (610, 100, 100, 5), (350, 350, 350, 5))
    assert eligible_mask(sku, cube, EligibilityCfg()).to_list() == [True, True, False, False]


def test_T5_4_missing_dims_ineligible_unless_flag(catalog) -> None:
    cube = catalog.families["cube_asrs"]
    sku = _sku((300, 200, 100, 1.0), (None, 200, 100, 1.0), (300, 200, 100, None))
    assert eligible_mask(sku, cube, EligibilityCfg()).to_list() == [True, False, False]
    assume = EligibilityCfg(assume_eligible_if_missing_dims=True)
    assert eligible_mask(sku, cube, assume).to_list() == [True, True, True]
    assumed = assumed_mask(sku, cube, assume)
    assert assumed.to_list() == [False, True, True]

    res = eligibility_shares(
        eligible_mask(sku, cube, assume),
        pl.Series([60, 30, 10]),
        pl.Series([1.0, 1.0, 2.0]),
        family="cube_asrs",
        low_share=0.5,
        assumed=assumed,
    )
    assert res.share_lines == 1.0
    assert res.assumed_share_lines == pytest.approx(0.4)
    flag = next(f for f in res.flags if f.code == "F_ELIG_ASSUMED")
    assert flag.value == pytest.approx(0.4)


def test_T5_4_assume_flag_never_overrides_a_known_violation(catalog) -> None:
    """Only MISSING values are assumed to fit; a known dim or weight violation stays ineligible."""
    cube = catalog.families["cube_asrs"]  # [600, 400, 300] mm, 25 kg
    sku = _sku(
        (None, 200, 100, 500.0),  # missing dim, known weight 500 kg > 25
        (2000, 2000, 2000, None),  # known oversize, missing weight
        (None, None, None, 40.0),  # missing dims, known weight 40 kg > 25
        (None, 500, 450, 1.0),  # known dims 500 × 450 cannot fit 400 × 300 in any orientation
        (None, 550, 250, 1.0),  # known dims fit (550 ≤ 600, 250 ≤ 400): the missing one is assumed
        (300, 200, 100, None),  # dims fit, weight missing: assumed
    )
    assume = EligibilityCfg(assume_eligible_if_missing_dims=True)
    expected = [False, False, False, False, True, True]
    assert eligible_mask(sku, cube, assume).to_list() == expected
    assert assumed_mask(sku, cube, assume).to_list() == expected  # every True here is assumed
    assert eligible_mask(sku, cube, EligibilityCfg()).to_list() == [False] * 6
    # an extra weight cap is a known violation too, even with the catalog limits off
    extra = EligibilityCfg(
        assume_eligible_if_missing_dims=True, use_catalog_limits=False, extra_max_weight_kg=10
    )
    assert eligible_mask(sku, cube, extra).to_list() == [False, True, False, True, True, True]


def test_T5_4_missing_dims_ineligible_whatever_the_limits(catalog) -> None:
    """Step 3 holds with `use_catalog_limits=False` too, and a NaN counts as missing (F5b audit)."""
    cube = catalog.families["cube_asrs"]
    nan = float("nan")
    sku = _sku(
        (300, 200, 100, 1.0),
        (None, 200, 100, 1.0),  # missing dim
        (300, 200, 100, None),  # missing weight, no weight cap with the limits off
        (nan, 200, 100, 1.0),  # NaN dim
        (300, 200, 100, nan),  # NaN weight
    )
    for limits in (True, False):
        strict = EligibilityCfg(use_catalog_limits=limits)
        assert eligible_mask(sku, cube, strict).to_list() == [True] + [False] * 4, limits
        assume = EligibilityCfg(use_catalog_limits=limits, assume_eligible_if_missing_dims=True)
        assert eligible_mask(sku, cube, assume).to_list() == [True] * 5, limits
        assert assumed_mask(sku, cube, assume).to_list() == [False] + [True] * 4, limits


def test_eligible_mask_missing_column_is_a_whsizing_error(catalog) -> None:
    sku = _sku((300, 200, 100, 1.0)).drop("weight_kg")
    with pytest.raises(WhsizingError, match=r"lacks column\(s\) \['weight_kg'\]"):
        eligible_mask(sku, catalog.families["cube_asrs"], EligibilityCfg())


def test_weight_limits_and_use_catalog_limits(catalog) -> None:
    cube = catalog.families["cube_asrs"]  # max_weight_kg 25
    sku = _sku((300, 200, 100, 25.0), (300, 200, 100, 26.0), (1000, 900, 800, 12.0))
    assert eligible_mask(sku, cube, EligibilityCfg()).to_list() == [True, False, False]
    extra = EligibilityCfg(extra_max_weight_kg=10)
    assert eligible_mask(sku, cube, extra).to_list() == [False, False, False]
    no_limits = EligibilityCfg(use_catalog_limits=False, extra_max_weight_kg=20)
    assert eligible_mask(sku, cube, no_limits).to_list() == [False, False, True]
    # no column-based check at all (manual, no limits, no temperature column): one row per SKU
    manual = catalog.families["manual_p2p"]
    unlimited = EligibilityCfg(use_catalog_limits=False)
    assert eligible_mask(sku, manual, unlimited).to_list() == [True, True, True]


def test_hazmat_and_temperature(catalog) -> None:
    sku = _sku(
        *[(300, 200, 100, 1.0)] * 5,
        hazmat=[True, None, False, False, False],
        temperature_class=["ambient", "ambient", "chilled", "frozen", None],
    )
    cfg = EligibilityCfg()
    fam = catalog.families
    assert eligible_mask(sku, fam["cube_asrs"], cfg).to_list() == [False, True, True, False, True]
    assert eligible_mask(sku, fam["amr_gtp"], cfg).to_list() == [False, True, False, False, True]
    assert eligible_mask(sku, fam["manual_p2p"], cfg).to_list() == [True] * 5
    no_cols = _sku((300, 200, 100, 1.0))  # hazmat / temperature columns absent → ambient, safe
    assert eligible_mask(no_cols, fam["amr_gtp"], cfg).to_list() == [True]


def test_shares_by_lines_cube_and_count_and_elig_low() -> None:
    lines, stock = pl.Series([50, 30, 15, 5]), pl.Series([1.0, 2.0, 3.0, 4.0])
    res = eligibility_shares(
        pl.Series([True, False, True, False]), lines, stock, family="amr_gtp", low_share=0.5
    )
    assert (res.share_lines, res.share_stock_cube, res.share_skus) == (0.65, 0.4, 0.5)
    assert (res.n_skus_eligible, res.n_skus_total) == (2, 4)
    assert res.flags == []

    low = eligibility_shares(
        pl.Series([False, True, False, True]), lines, stock, family="amr_gtp", low_share=0.5
    )
    assert low.share_lines == pytest.approx(0.35)
    assert [f.code for f in low.flags] == ["F_ELIG_LOW"]
    assert low.flags[0].value == pytest.approx(0.35)

    with pytest.raises(WhsizingError, match="lengths differ"):
        eligibility_shares(pl.Series([True]), lines, stock, family="amr_gtp", low_share=0.5)


@pytest.mark.parametrize(
    ("lines", "stock", "assumed", "match"),
    [
        # a short `assumed` was a polars Rust panic (BaseException), a length-1 one broadcast
        ([9, 1], [1.0, 1.0], [True, False, True], "lengths differ"),
        ([9, 1], [1.0, 1.0], [True], "lengths differ"),
        ([9, 1], [float("nan"), 1.0], None, "stock_by_sku has NaN or negative"),  # was share 0
        ([9, 1], [5.0, -4.0], None, "stock_by_sku has NaN or negative"),  # was share 5.0
        ([9, -1], [1.0, 1.0], None, "lines_by_sku has NaN or negative"),
    ],
)
def test_shares_reject_misaligned_or_invalid_series(lines, stock, assumed, match) -> None:
    a = None if assumed is None else pl.Series(assumed)
    with pytest.raises(WhsizingError, match=match):
        eligibility_shares(
            pl.Series([True, True]),
            pl.Series(lines),
            pl.Series(stock),
            family="cube_asrs",
            low_share=0.5,
            assumed=a,
        )


@pytest.mark.parametrize("dtype", [pl.Boolean, pl.Null])
def test_shares_on_an_empty_sku_set(dtype) -> None:
    """0 SKUs: shares 0, F_ELIG_LOW, no polars SchemaError (an empty list has dtype Null)."""
    empty = pl.Series([], dtype=dtype)
    for assumed in (None, empty):
        res = eligibility_shares(
            empty, pl.Series([]), pl.Series([]), family="cube_asrs", low_share=0.5, assumed=assumed
        )
        assert (res.share_lines, res.share_skus, res.n_skus_total) == (0.0, 0.0, 0)
        assert [f.code for f in res.flags] == ["F_ELIG_LOW"]


def test_units_per_bin() -> None:
    unit_cube = pl.Series([0.007, 0.0121, 0.1, None], dtype=pl.Float64)
    # 0.04 × 0.7 / 0.007 = 3.9999999999999996 in floating point: must be 4
    assert units_per_bin(0.04, 0.7, unit_cube).to_list() == [4, 2, 0, None]
    # the tolerance is relative and tiny: a real 3.9999999995 floors to 3 (W1 finding 10)
    assert units_per_bin(1.0, 1.0, pl.Series([1 / 3.9999999995])).to_list() == [3]


@pytest.mark.parametrize("cube", [0.0, -0.01, float("nan")])
def test_units_per_bin_rejects_non_positive_unit_cube(cube: float) -> None:
    with pytest.raises(WhsizingError, match="unit_cube_m3 must be > 0"):
        units_per_bin(0.055, 0.88, pl.Series([0.01, cube]))


TINY = ROOT / "tests/golden/tiny_golden"


def _tiny_golden() -> list[pl.DataFrame]:
    paths = [TINY / f"{n}.parquet" for n in ("sku_master", "order_lines", "inventory")]
    missing = [p.name for p in paths if not p.is_file()]
    assert not missing, (
        f"tiny_golden canonical parquet missing: {missing} (a golden check, not a skip)"
    )
    return [pl.read_parquet(p) for p in paths]


def test_tiny_golden_cube_envelope_matches_f1_readme(catalog) -> None:
    """tests/golden/tiny_golden/README.md: 9 SKUs outside the cube_asrs envelope, all ≤ 25 kg."""
    sku = _tiny_golden()[0]
    mask = eligible_mask(sku, catalog.families["cube_asrs"], EligibilityCfg())
    assert (len(sku), int((~mask).sum())) == (100, 9)
    manual = eligible_mask(sku, catalog.families["manual_p2p"], EligibilityCfg())
    assert bool(manual.all())


def test_T5_3_golden_eligibility_shares(catalog) -> None:
    """Golden (G1): eligibility shares on tiny_golden equal the spreadsheet within 0.5 % (T1.5).

    Lines = shipped order lines per SKU over the whole (31-day) history; stock cube = mean snapshot
    units × unit cube. Keys: `eligibility.<family>.<field>` with the default EligibilityCfg, and
    `<scenario>.eligibility.<field>` with that scenario's EligibilityCfg from golden_scenarios.yaml
    (S2 sets `extra_max_weight_kg`; docs/INTERPRETATIONS.md I44).
    """
    assert GOLDEN.is_file(), f"{GOLDEN} is missing: the golden check must not turn into a skip"
    data = json.loads(GOLDEN.read_text())
    scenarios = {
        s.id: s for s in ScenarioSet.model_validate(yaml.safe_load(SCENARIOS.read_text())).scenarios
    }
    cases: dict[str, tuple[Family, EligibilityCfg, str]] = {}
    for key in data:
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "eligibility":
            cases[key] = (catalog.families[parts[1]], EligibilityCfg(), parts[2])
        elif len(parts) == 3 and parts[1] == "eligibility":
            sc = scenarios[parts[0]]
            cases[key] = (catalog.families[sc.family], sc.eligibility, parts[2])
    assert cases, "golden_values.json has no eligibility keys: the golden check must not be a skip"
    sku, lines, inv = _tiny_golden()
    shipped = lines.filter((pl.col("line_status") == "shipped") & (pl.col("qty_units") > 0))
    stock = inv.group_by("sku").agg(pl.col("qty_units").mean().alias("stock"))
    per_sku = (
        sku.join(shipped.group_by("sku").len("lines"), on="sku", how="left")
        .join(stock, on="sku", how="left")
        .with_columns((pl.col("stock") * pl.col("unit_cube_m3")).alias("stock_cube"))
    )
    for key, (fam, cfg, field) in cases.items():
        mask = eligible_mask(per_sku, fam, cfg)
        res = eligibility_shares(
            mask, per_sku["lines"], per_sku["stock_cube"], family=fam.id, low_share=0.5
        )
        assert getattr(res, field) == pytest.approx(data[key], rel=0.005), key
    # both key shapes are checked, and the scenario cap really bites (91 → 86 SKUs)
    assert {k.split(".")[0] for k in cases} >= {"eligibility", "S2"}, sorted(cases)
