"""F6a storage class assignment and storage sizing, hand-computed on toy SKUs (catalog typ:
fill_pallet 0.85, 0.38 positions/m²/level, fill_shelf 0.80, 8 bins/m²/level, cube fill 0.88,
3.0 bins/m²/level, 5 % empty bins, 8 % service aisles; AMR pod bin 0.03 m³, fill 0.80,
60 bins/pod, 2.6 m²/pod). Design stock = avg_stock in these toys."""

from __future__ import annotations

import polars as pl
import pytest
from tests.unit.test_f6_inputs import BIG, SMALL, build, toy_sku

from whsizing.engine import WORLDS, WorldInputs, fits_shelf, size_storage, storage_result
from whsizing.schemas import World

APPROX = 1e-9


def test_fits_shelf_is_orientation_agnostic_and_needs_every_dim() -> None:
    """I10: sorted dims ≤ sorted [500, 400, 350]; a missing dim → does not fit."""
    df = pl.DataFrame(
        {
            "length_mm": [350.0, 501.0, 360.0, 100.0],
            "width_mm": [500.0, 100.0, 360.0, 100.0],
            "height_mm": [400.0, 100.0, 360.0, None],
        }
    )
    assert df.select(fits_shelf((500, 400, 350)))["fits_shelf"].to_list() == [
        True,
        False,
        False,
        False,
    ]


def test_manual_class_rule() -> None:
    """F6a: not fits_shelf → pallet_rack; sc ≥ 0.6 → pallet_rack; sc ≤ 0.04 × 6 = 0.24 →
    shelving; in between → pallet_rack. Zero-stock SKUs still get a manual class (I14)."""
    sku = toy_sku(
        {"sku": "a", "avg_stock": 200},  # sc 0.20 → shelving
        {"sku": "b", "avg_stock": 300},  # sc 0.30 → pallet_rack
        {"sku": "c", "avg_stock": 700},  # sc 0.70 → pallet_rack
        {"sku": "d", "dims": BIG, "avg_stock": 1},  # does not fit a shelf bin
        {"sku": "e", "dims": None, "avg_stock": 1},  # no dims: not verifiably fitting
        {"sku": "f", "avg_stock": 0},  # no stock: shelving class, no position
    )
    inp = build(sku)
    assert inp.sku["manual_class"].to_list() == [
        "shelving",
        "pallet_rack",
        "pallet_rack",
        "pallet_rack",
        "pallet_rack",
        "shelving",
    ]
    assert inp.sku["storage_class"].to_list() == inp.sku["manual_class"].to_list()


def test_pallet_rack_positions_pick_faces_levels_area() -> None:
    """pallets = ceil(130/50) + ceil(100/(10×20)) + ceil(700/400 default) = 3 + 1 + 2 = 6;
    pick faces = A/B SKUs (c1 A, c3 B) = 2 (I11); positions = 6/0.85 + 2 = 9.0588;
    levels = min(6, floor((8.5 − 0.6)/1.55) = 5) = 5 → F_HEIGHT_LIMIT:pallet_rack (I40);
    area = 9.0588 / (5 × 0.38) = 4.7678 m². The zero-stock A SKU takes no position."""
    sku = toy_sku(
        {"sku": "c1", "dims": BIG, "avg_stock": 130, "upp": 50, "abc": "A"},
        {"sku": "c2", "dims": BIG, "avg_stock": 100, "upc": 10, "cpp": 20, "abc": "C"},
        {"sku": "c3", "avg_stock": 700, "abc": "B"},
        {"sku": "c4", "dims": BIG, "avg_stock": 0, "abc": "A"},
    )
    inp = build(sku)
    st = size_storage(inp)
    pr = st.get("pallet_rack")
    t = inp.tracer
    assert t.get("S9.storage.pallet_rack.pallets").value == 6
    assert t.get("S9.storage.pallet_rack.pallets").inputs["default_upp"] == (
        "param:storage.default_units_per_pallet"
    )
    n_skus = t.get("S9.storage.pallet_rack.n_skus").inputs  # traceable to the class rule
    assert n_skus["pallet_threshold"] == "param:storage.pallet_threshold_m3"
    assert n_skus["s"] == "data:sku.design_stock"
    assert t.get("S9.storage.pallet_rack.pick_faces").value == 2
    assert pr.n_skus == 3
    assert pr.positions == pytest.approx(9.058823529411764, rel=APPROX)
    assert pr.levels == 5
    assert pr.area_m2 == pytest.approx(4.767801857585139, rel=APPROX)
    assert [f.code for f in st.flags] == ["F_HEIGHT_LIMIT:pallet_rack"]
    assert st.total_area_m2 == pytest.approx(pr.area_m2, rel=APPROX)  # shelving emitted, empty
    assert st.get("shelving").positions == 0 and st.get("shelving").levels == 5


@pytest.mark.parametrize(
    ("height", "rack_levels", "cube_levels", "flags"),
    [
        (12.0, 6, 20, []),  # floor(11.4/1.55) = 7 ≥ 6; floor(10.8/0.33) = 32 ≥ 20
        (8.5, 5, 20, ["F_HEIGHT_LIMIT:pallet_rack"]),  # floor(7.9/1.55) = 5; 22 ≥ 20
        (5.0, 2, 11, ["F_HEIGHT_LIMIT:cube_bin", "F_HEIGHT_LIMIT:pallet_rack"]),
        (1.5, 1, 1, ["F_HEIGHT_LIMIT:cube_bin", "F_HEIGHT_LIMIT:pallet_rack"]),  # < one level
    ],
)
def test_levels_capped_by_building_or_catalog(
    height: float, rack_levels: int, cube_levels: int, flags: list[str]
) -> None:
    """I40 + F6 edge case: levels = min(max_levels, floor(usable / pitch)), at least 1;
    F_HEIGHT_LIMIT when the building gives fewer than max_levels."""
    sku = toy_sku(
        {"sku": "a", "avg_stock": 10, "lines": 1},
        {"sku": "b", "dims": BIG, "avg_stock": 10, "upp": 10, "lines": 1},
    )
    st = size_storage(build(sku, "cube_asrs", clear_height=height))
    assert st.get("pallet_rack").levels == rack_levels
    assert st.get("cube_bin").levels == cube_levels
    assert [f.code for f in st.flags] == flags
    assert st.get("shelving").levels == 5  # ergonomic cap, never flagged


@pytest.mark.parametrize(
    ("cls", "top", "pitch", "cap"),
    [("pallet_rack", 0.6, 1.55, 6), ("cube_bin", 1.2, 0.33, 20)],
)
def test_levels_exact_at_heights_that_are_whole_pitches(
    cls: str, top: float, pitch: float, cap: int
) -> None:
    """I40: H_clear = overhead + k × pitch gives exactly k levels (min with max_levels) and no
    F_HEIGHT_LIMIT once k ≥ max_levels. A bare float floor gave 19 cube levels at 7.8 m
    ((7.8 − 1.2) / 0.33 = 19.999999999999996) and a spurious flag."""
    sku = toy_sku(
        {"sku": "a", "avg_stock": 10, "lines": 1},
        {"sku": "b", "dims": BIG, "avg_stock": 10, "upp": 10, "lines": 1},
    )
    for k in range(1, cap + 3):
        st = size_storage(build(sku, "cube_asrs", clear_height=top + k * pitch))
        c = st.get(cls)
        assert (c.levels, c.height_limited) == (min(k, cap), k < cap), k
        assert (f"F_HEIGHT_LIMIT:{cls}" in {f.code for f in st.flags}) == (k < cap), k
    cube = size_storage(build(sku, "cube_asrs", clear_height=7.8))
    assert cube.get("cube_bin").levels == 20
    assert "F_HEIGHT_LIMIT:cube_bin" not in {f.code for f in cube.flags}


def test_shelving_bins_levels_area() -> None:
    """bins_i = max(1, ceil(sc_i / (0.04 × 0.8))): 0.05 → 2, 0.001 → 1, 0.2 → 7; positions 10;
    levels = min(5, floor(2.1 / 0.4)) = 5; area = 10 / (5 × 8) = 0.25 m²."""
    sku = toy_sku(
        {"sku": "s1", "avg_stock": 50},
        {"sku": "s2", "avg_stock": 1},
        {"sku": "s3", "avg_stock": 200},
    )
    sh = size_storage(build(sku)).get("shelving")
    assert sh.positions == 10
    assert sh.levels == 5
    assert sh.area_m2 == pytest.approx(0.25, rel=APPROX)
    assert sh.n_skus == 3


def test_cube_bins_mixed_reserve_grid_and_overflow() -> None:
    """cube_bin: sc 0.005 < 0.2 × 0.055 → 1/4 bin (I43); 0.1 → ceil(0.1 / 0.0484) = 3;
    0.02 → 1; bins_raw 4.25; bins_total 4.25 × 1.05 = 4.4625; levels min(20, 22) = 20;
    A_grid = 4.4625 / (20 × 3.0) = 0.074375; A = A_grid × 1.08 = 0.080325 m².
    Overflow pallet_rack (non-eligible big SKU): 2 pallets / 0.85 = 2.3529 positions,
    area 2.3529 / (5 × 0.38) = 1.2384 m²; overflow shelving emitted empty (I39)."""
    sku = toy_sku(
        {"sku": "k1", "avg_stock": 5, "lines": 1},
        {"sku": "k2", "avg_stock": 100, "lines": 1},
        {"sku": "k3", "avg_stock": 20, "lines": 1},
        {"sku": "k4", "dims": BIG, "avg_stock": 100, "upp": 50, "lines": 1},
    )
    inp = build(sku, "cube_asrs")
    st = size_storage(inp)
    cube = st.get("cube_bin")
    assert inp.tracer.get("S9.storage.cube_bin.bins_raw").value == pytest.approx(4.25)
    assert cube.positions == pytest.approx(4.4625, rel=APPROX)
    assert cube.levels == 20
    assert cube.grid_area_m2 == pytest.approx(0.074375, rel=APPROX)
    assert cube.area_m2 == pytest.approx(0.080325, rel=APPROX)
    assert (cube.zone, cube.n_skus) == ("main", 3)
    ovf = st.get("pallet_rack")
    assert ovf.zone == "overflow"
    assert ovf.positions == pytest.approx(2.3529411764705883, rel=APPROX)
    assert inp.tracer.get("S9.storage.overflow.pallet_rack.area_m2").value == pytest.approx(
        1.238390092879257, rel=APPROX
    )
    assert st.get("shelving").positions == 0
    assert st.total_area_m2 == pytest.approx(0.080325 + 1.238390092879257, rel=APPROX)
    assert [c.storage_class for c in st.classes] == ["cube_bin", "pallet_rack", "shelving"]


def test_pod_bins_and_pods() -> None:
    """pod_bin: sc 0.005 < 0.2 × 0.03 → 1/4; 0.1 → ceil(0.1 / 0.024) = 5; bins_total =
    5.25 × 1.05 = 5.5125; pods = ceil(5.5125 / 60) = 1; area = 1 × 2.6 m²; no levels."""
    sku = toy_sku({"sku": "p1", "avg_stock": 5, "lines": 1}, {"sku": "p2", "avg_stock": 100})
    pod = size_storage(build(sku, "amr_gtp")).get("pod_bin")
    assert pod.positions == pytest.approx(5.5125, rel=APPROX)
    assert pod.pods == 1
    assert pod.area_m2 == pytest.approx(2.6, rel=APPROX)
    assert pod.levels is None


def test_storage_result_maps_worlds_to_ranges_and_copies_elig_low() -> None:
    """StorageResult: Ranges over lo/typ/hi (lo world = min fill → most positions), typ levels,
    F_HEIGHT_LIMIT and F_ELIG_LOW (share of eligible lines 1/3 < 0.5)."""
    sku = toy_sku(
        {"sku": "a", "dims": SMALL, "avg_stock": 100, "lines": 1},
        {"sku": "b", "dims": BIG, "avg_stock": 100, "upp": 50, "lines": 2},
    )
    worlds: dict[World, WorldInputs] = {w: build(sku, "cube_asrs", w) for w in WORLDS}
    res = storage_result({w: size_storage(i) for w, i in worlds.items()}, worlds["typ"].eligibility)
    cube = res.classes[0]
    assert (cube.storage_class, cube.levels, cube.n_skus) == ("cube_bin", 20, 1)
    # bins: lo fill 0.80 → ceil(0.1/0.044) = 3; typ 0.88 → 3; hi 0.92 → ceil(1.976) = 2
    assert (cube.positions.lo, cube.positions.typ, cube.positions.hi) == pytest.approx(
        (2 * 1.05, 3 * 1.05, 3 * 1.05)
    )
    assert cube.grid_area_m2 is not None and cube.grid_area_m2.unit == "m2"
    rack = res.classes[1]
    # positions: 2 pallets / fill (lo 0.80, typ 0.85, hi 0.90)
    assert rack.positions.lo == pytest.approx(2 / 0.9)
    assert rack.positions.hi == pytest.approx(2 / 0.8)
    assert res.total_area_m2.lo <= res.total_area_m2.typ <= res.total_area_m2.hi
    assert [f.code for f in res.flags] == ["F_HEIGHT_LIMIT:pallet_rack", "F_ELIG_LOW"]
    # used height: cube 20 × 0.33 + 1.2 = 7.8 m of 8.5 m
    assert res.height_utilisation == pytest.approx(7.8 / 8.5)
