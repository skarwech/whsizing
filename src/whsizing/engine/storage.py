"""F6a storage sizing: positions, levels and footprint per storage class (I11, I39, I40, I43)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import polars as pl

from whsizing.engine.classify import AUTOMATED_CLASS
from whsizing.engine.inputs import WORLDS, WorldInputs, to_range
from whsizing.errors import WhsizingError
from whsizing.schemas import (
    EligibilityResult,
    Flag,
    Range,
    StorageClassResult,
    StorageResult,
    World,
)

Zone = Literal["main", "overflow"]
MANUAL = ("pallet_rack", "shelving")
H_CLEAR = "data:basis.building.clear_height_m"
# what decides a SKU's storage class (classify_skus), the inputs of every `<class>.n_skus` node
CLASS_INPUTS = {
    "s": "data:sku.design_stock",
    "eligible": "data:sku.eligible",
    "fits_shelf": "data:sku.fits_shelf",
    "stock_cube": "data:sku.design_stock_cube_m3",
    "pallet_threshold": "param:storage.pallet_threshold_m3",
    "shelf_bin_net_cube": "param:storage.shelf_bin_net_cube_m3",
    "max_bins_per_sku_shelf": "param:storage.max_bins_per_sku_shelf",
}


@dataclass(frozen=True)
class ClassWorld:
    """One storage class in one world (fields of `StorageClassResult`, as floats)."""

    storage_class: Literal["pallet_rack", "shelving", "cube_bin", "pod_bin"]
    zone: Zone
    n_skus: int
    positions: float  # pallet positions (incl. pick faces) or bins (incl. reserve)
    levels: int | None  # None for pod_bin
    area_m2: float
    height_limited: bool  # I40: the building, not the catalog, caps the levels
    used_height_m: float  # levels × level pitch (+ grid overhead); 0 for pod_bin
    pods: float | None = None  # pod_bin only
    grid_area_m2: float | None = None  # cube_bin only


@dataclass(frozen=True)
class StorageWorld:
    classes: tuple[ClassWorld, ...]
    total_area_m2: float
    height_utilisation: float  # max used height / clear height
    flags: tuple[Flag, ...]  # F_HEIGHT_LIMIT:<class>

    def get(self, storage_class: str) -> ClassWorld:
        """The scenario's class of that name (each class appears once per scenario)."""
        return next(c for c in self.classes if c.storage_class == storage_class)


def size_storage(inp: WorldInputs) -> StorageWorld:
    """F6a for one world. Only SKUs with `s_i > 0` take positions (I14). Emitted classes (I39):
    manual family → pallet_rack, shelving (main); cube → cube_bin (main) + pallet_rack,
    shelving (overflow); amr → pod_bin (main) + the overflow pair. Trace ids
    `<sid>.storage[.overflow].<class>.<field>`."""
    stocked = inp.sku.filter(pl.col("design_stock") > 0)
    auto = AUTOMATED_CLASS.get(inp.scenario.family)
    manual_zone: Zone = "overflow" if auto else "main"
    main: list[tuple[str, Zone]] = [(auto, "main")] if auto else []
    emitted = main + [(c, manual_zone) for c in MANUAL]
    classes: list[ClassWorld] = []
    for cls, zone in emitted:
        prefix = f"storage.{'overflow.' if zone == 'overflow' else ''}{cls}"
        rows = stocked.filter(pl.col("storage_class") == cls)
        inp.record(
            f"{prefix}.n_skus",
            f"SKUs in {cls}",
            rows.height,
            "-",
            f"count(s_i > 0 and storage_class_i = {cls})",
            CLASS_INPUTS,
        )
        classes.append(SIZERS[cls](inp, rows, prefix, zone))
    areas = {c.storage_class: inp.tid(f"{_prefix(c)}.area_m2") for c in classes}
    total = inp.record(
        "storage.total_area_m2",
        "Total storage area",
        sum(c.area_m2 for c in classes),
        "m2",
        "Σ class area_m2",
        areas,
    )
    used = max((c.used_height_m for c in classes if c.positions > 0), default=0.0)
    h_util = inp.record(
        "storage.height_utilisation",
        "Height utilisation",
        used / inp.basis.building.clear_height_m,
        "-",
        "max(levels × level pitch of the used classes) / H_clear",
        {"H_clear": H_CLEAR},
    )
    flags = tuple(
        Flag(
            code=f"F_HEIGHT_LIMIT:{c.storage_class}",
            severity="info",
            message=f"{c.storage_class}: {c.levels} level(s), capped by the clear height",
        )
        for c in classes
        if c.height_limited
    )
    return StorageWorld(tuple(classes), total, h_util, flags)


def storage_result(
    worlds: Mapping[World, StorageWorld], eligibility: EligibilityResult
) -> StorageResult:
    """Merge the three worlds into `StorageResult` (ADR-002 Ranges). Levels, SKU counts, height
    utilisation and F_HEIGHT_LIMIT are those of the typical world; F_ELIG_LOW is copied from the
    scenario's eligibility."""
    typ = worlds["typ"]

    def rng(i: int, field: str, unit: str) -> Range:
        return to_range({w: getattr(worlds[w].classes[i], field) for w in WORLDS}, unit)

    classes = [
        StorageClassResult(
            storage_class=c.storage_class,
            zone=c.zone,
            n_skus=c.n_skus,
            positions=rng(
                i, "positions", "pallets" if c.storage_class == "pallet_rack" else "bins"
            ),
            levels=c.levels,
            area_m2=rng(i, "area_m2", "m2"),
            pods=None if c.pods is None else rng(i, "pods", "pods"),
            grid_area_m2=None if c.grid_area_m2 is None else rng(i, "grid_area_m2", "m2"),
        )
        for i, c in enumerate(typ.classes)
    ]
    return StorageResult(
        classes=classes,
        total_area_m2=to_range({w: worlds[w].total_area_m2 for w in WORLDS}, "m2"),
        height_utilisation=typ.height_utilisation,
        flags=[*typ.flags, *(f for f in eligibility.flags if f.code == "F_ELIG_LOW")],
    )


def _prefix(c: ClassWorld) -> str:
    return f"storage.{'overflow.' if c.zone == 'overflow' else ''}{c.storage_class}"


def _fit(height_m: float, pitch_m: float) -> int:
    """I63 (11): floor(height / pitch + 1e-9), exact at whole pitches: (7.8 − 1.2) / 0.33 is
    19.999999999999996 in floats, 20 levels on paper."""
    return math.floor(height_m / pitch_m + 1e-9)  # ponytail: 1e-9 level slack, not mm math


def _levels(usable_m: float, pitch_m: float, max_levels: int) -> tuple[int, bool]:
    """min(max_levels, floor(usable / pitch)), at least 1 (F6 edge case); flagged when the
    building gives fewer than max_levels (I40)."""
    fit = _fit(usable_m, pitch_m)
    return max(1, min(max_levels, fit)), fit < max_levels


def _pallet_rack(inp: WorldInputs, rows: pl.DataFrame, prefix: str, zone: Zone) -> ClassWorld:
    """positions = Σ ceil(s_i / upp_i) / fill_pallet + pick faces (I11); levels capped by the
    building (I40); A = positions / (levels × positions_per_m2_per_level)."""
    m = "manual_p2p.pallet_rack_"
    pallets, faces = _pallets_and_faces(inp, rows, prefix)
    fill = inp.v(f"{m}fill_factor")
    positions = inp.record(
        f"{prefix}.positions",
        "Pallet positions",
        pallets / fill + faces,
        "positions",
        "pallets / fill_pallet + pick_faces",
        {
            "pallets": inp.tid(f"{prefix}.pallets"),
            "fill_pallet": f"param:{m}fill_factor",
            "pick_faces": inp.tid(f"{prefix}.pick_faces"),
        },
    )
    pitch = (inp.v(f"{m}pallet_load_height_mm") + inp.v(f"{m}beam_pitch_mm")) / 1000
    usable = inp.basis.building.clear_height_m - inp.v(f"{m}top_clearance_m")
    levels, limited = _levels(usable, pitch, int(inp.v(f"{m}max_levels")))
    inp.record(
        f"{prefix}.levels",
        "Pallet rack levels",
        levels,
        "-",
        "max(1, min(max_levels, floor((H_clear − top_clearance) / "
        "(pallet_load_height + beam_pitch))))",
        {
            "H_clear": H_CLEAR,
            "top_clearance": f"param:{m}top_clearance_m",
            "pallet_load_height": f"param:{m}pallet_load_height_mm",
            "beam_pitch": f"param:{m}beam_pitch_mm",
            "max_levels": f"param:{m}max_levels",
        },
    )
    area = _area(inp, prefix, positions, levels, f"{m}positions_per_m2_per_level")
    return ClassWorld(
        "pallet_rack", zone, rows.height, positions, levels, area, limited, levels * pitch
    )


def _pallets_and_faces(inp: WorldInputs, rows: pl.DataFrame, prefix: str) -> tuple[float, float]:
    """pallets = Σ ceil(s_i / upp_i), upp = units_per_pallet | units_per_case × cases_per_pallet
    | default 400 (I13); pick faces = A/B SKUs × faces_per_sku (I11, whole stock in reserve)."""
    default_upp = inp.v("storage.default_units_per_pallet")
    upp = pl.coalesce(
        pl.col("units_per_pallet").cast(pl.Float64),
        pl.col("units_per_case").cast(pl.Float64) * pl.col("cases_per_pallet").cast(pl.Float64),
        pl.lit(default_upp),
    )
    if not rows.filter(upp <= 0).is_empty():
        raise WhsizingError(f"{inp.scenario.id}: units_per_pallet ≤ 0 for a pallet-rack SKU")
    n_pallets = float(rows.select((pl.col("design_stock") / upp).ceil().sum()).item())
    pallets = inp.record(
        f"{prefix}.pallets",
        "Pallets in stock",
        n_pallets,
        "pallets",
        "Σ ceil(s_i / units_per_pallet_i)",
        {
            "s": "data:sku.design_stock",
            "upp": "data:sku.units_per_pallet",
            "upc": "data:sku.units_per_case",
            "cpp": "data:sku.cases_per_pallet",
            "default_upp": "param:storage.default_units_per_pallet",
        },
    )
    policy = inp.catalog.families["manual_p2p"].storage.pick_face_policy
    face_classes = policy.classes_with_pick_face if policy else []
    n_faced = rows.filter(pl.col("abc").is_in(face_classes)).height
    pf_id = "manual_p2p.pick_face_policy_faces_per_sku"
    faces = inp.record(
        f"{prefix}.pick_faces",
        "Pick faces (A/B SKUs, level 1)",
        n_faced * inp.v(pf_id),
        "positions",
        "n(A/B SKUs in pallet_rack) × faces_per_sku",
        {"abc": "data:sku.abc", "faces_per_sku": f"param:{pf_id}"},
    )
    return pallets, faces


def _shelving(inp: WorldInputs, rows: pl.DataFrame, prefix: str, zone: Zone) -> ClassWorld:
    m = "manual_p2p.shelving_"
    net, fill = inp.v("storage.shelf_bin_net_cube_m3"), inp.v(f"{m}fill_factor")
    bins = (pl.col("design_stock_cube_m3") / (net * fill)).ceil().clip(lower_bound=1)
    positions = inp.record(
        f"{prefix}.positions",
        "Shelf bins",
        float(rows.select(bins.sum()).item() or 0.0),
        "bins",
        "Σ max(1, ceil(stock_cube_i / (shelf_bin_net_cube × fill_shelf)))",
        {
            "stock_cube": "data:sku.design_stock_cube_m3",
            "shelf_bin_net_cube": "param:storage.shelf_bin_net_cube_m3",
            "fill_shelf": f"param:{m}fill_factor",
        },
    )
    pitch = inp.v(f"{m}bin_pitch_mm") / 1000
    fit = _fit(inp.v(f"{m}shelf_max_height_m"), pitch)
    levels = max(1, min(int(inp.v(f"{m}ergonomic_max_levels")), fit))
    inp.record(
        f"{prefix}.levels",
        "Shelving levels",
        levels,
        "-",
        "min(ergonomic_max_levels, floor(shelf_max_height / bin_pitch))",
        {
            "ergonomic_max_levels": f"param:{m}ergonomic_max_levels",
            "shelf_max_height": f"param:{m}shelf_max_height_m",
            "bin_pitch": f"param:{m}bin_pitch_mm",
        },
    )
    area = _area(inp, prefix, positions, levels, f"{m}bins_per_m2_per_level")
    return ClassWorld("shelving", zone, rows.height, positions, levels, area, False, levels * pitch)


def _bins(inp: WorldInputs, rows: pl.DataFrame, prefix: str, fam: str, net_id: str) -> float:
    """cube_bin / pod_bin: bins_i = max(1, ceil(sc_i / (bin_net_cube × fill))), or
    1 / skus_per_mixed_bin when sc_i < mixed_bin_threshold_share × bin_net_cube and mixed bins
    are allowed (I43); bins_total = Σ bins_i × (1 + empty_bin_reserve). Returns bins_total."""
    net, fill = inp.v(net_id), inp.v(f"{fam}.fill_factor")
    sc = pl.col("design_stock_cube_m3")
    full = (sc / (net * fill)).ceil().clip(lower_bound=1)
    mixed_limit = inp.v("storage.mixed_bin_threshold_share") * net
    if inp.catalog.storage.mixed_bins_allowed:
        full = (
            pl.when(sc < mixed_limit).then(1 / inp.v("storage.skus_per_mixed_bin")).otherwise(full)
        )
    raw = inp.record(
        f"{prefix}.bins_raw",
        "Bins before the empty-bin reserve",
        float(rows.select(full.sum()).item() or 0.0),
        "bins",
        "Σ (1 / skus_per_mixed_bin if stock_cube_i < mixed_bin_threshold_share × bin_net_cube "
        "else max(1, ceil(stock_cube_i / (bin_net_cube × fill))))",
        {
            "stock_cube": "data:sku.design_stock_cube_m3",
            "bin_net_cube": f"param:{net_id}",
            "fill": f"param:{fam}.fill_factor",
            "skus_per_mixed_bin": "param:storage.skus_per_mixed_bin",
            "mixed_bin_threshold_share": "param:storage.mixed_bin_threshold_share",
        },
    )
    return inp.record(
        f"{prefix}.positions",
        "Bins incl. empty-bin reserve",
        raw * (1 + inp.v(f"{fam}.empty_bin_reserve")),
        "bins",
        "bins_raw × (1 + empty_bin_reserve)",
        {"bins_raw": inp.tid(f"{prefix}.bins_raw"), "reserve": f"param:{fam}.empty_bin_reserve"},
    )


def _cube_bin(inp: WorldInputs, rows: pl.DataFrame, prefix: str, zone: Zone) -> ClassWorld:
    c = "cube_asrs."
    bins = _bins(inp, rows, prefix, "cube_asrs", f"{c}bin_net_cube_m3")
    pitch = inp.v(f"{c}level_height_mm") / 1000
    overhead = inp.v(f"{c}grid_overhead_m")
    usable = inp.basis.building.clear_height_m - overhead
    levels, limited = _levels(usable, pitch, int(inp.v(f"{c}max_levels")))
    inp.record(
        f"{prefix}.levels",
        "Cube grid levels",
        levels,
        "-",
        "max(1, min(max_levels, floor((H_clear − grid_overhead) / level_height)))",
        {
            "H_clear": H_CLEAR,
            "grid_overhead": f"param:{c}grid_overhead_m",
            "level_height": f"param:{c}level_height_mm",
            "max_levels": f"param:{c}max_levels",
        },
    )
    density = f"{c}bins_per_m2_per_level"
    grid = inp.record(
        f"{prefix}.grid_area_m2",
        "Cube grid area",
        bins / (levels * inp.v(density)),
        "m2",
        "bins_total / (levels × bins_per_m2_per_level)",
        {
            "bins_total": inp.tid(f"{prefix}.positions"),
            "levels": inp.tid(f"{prefix}.levels"),
            "bins_per_m2_per_level": f"param:{density}",
        },
    )
    area = inp.record(
        f"{prefix}.area_m2",
        "Cube storage area",
        grid * (1 + inp.v(f"{c}service_aisle_share")),
        "m2",
        "A_grid × (1 + service_aisle_share)",
        {"A_grid": inp.tid(f"{prefix}.grid_area_m2"), "share": f"param:{c}service_aisle_share"},
    )
    used = levels * pitch + overhead
    return ClassWorld(
        "cube_bin", zone, rows.height, bins, levels, area, limited, used, grid_area_m2=grid
    )


def _pod_bin(inp: WorldInputs, rows: pl.DataFrame, prefix: str, zone: Zone) -> ClassWorld:
    a = "amr_gtp."
    bins = _bins(inp, rows, prefix, "amr_gtp", f"{a}pod_bin_net_cube_m3")
    pods = inp.record(
        f"{prefix}.pods",
        "Pods",
        math.ceil(bins / inp.v(f"{a}bins_per_pod")),
        "pods",
        "ceil(bins_total / bins_per_pod)",
        {"bins_total": inp.tid(f"{prefix}.positions"), "bins_per_pod": f"param:{a}bins_per_pod"},
    )
    area = inp.record(
        f"{prefix}.area_m2",
        "Pod storage area (incl. robot aisles)",
        pods * inp.v(f"{a}pod_footprint_m2"),
        "m2",
        "pods × pod_footprint_m2",
        {"pods": inp.tid(f"{prefix}.pods"), "pod_footprint_m2": f"param:{a}pod_footprint_m2"},
    )
    return ClassWorld("pod_bin", zone, rows.height, bins, None, area, False, 0.0, pods=pods)


def _area(inp: WorldInputs, prefix: str, positions: float, levels: int, density: str) -> float:
    return inp.record(
        f"{prefix}.area_m2",
        "Storage area (incl. aisles)",
        positions / (levels * inp.v(density)),
        "m2",
        "positions / (levels × density per m² per level)",
        {
            "positions": inp.tid(f"{prefix}.positions"),
            "levels": inp.tid(f"{prefix}.levels"),
            "density": f"param:{density}",
        },
    )


SIZERS = {
    "pallet_rack": _pallet_rack,
    "shelving": _shelving,
    "cube_bin": _cube_bin,
    "pod_bin": _pod_bin,
}
