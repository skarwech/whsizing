"""F6 inputs: the per-SKU frame (I58) and the per-world inputs of one scenario run (ADR-002)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from whsizing.catalog import (
    Catalog,
    Family,
    ParamSet,
    assumed_mask,
    eligibility_shares,
    eligible_mask,
)
from whsizing.design import with_pack_data
from whsizing.engine.classify import classify_skus
from whsizing.errors import DataQualityError, WhsizingError
from whsizing.profile import ProfileTables
from whsizing.schemas import (
    DesignBasis,
    DesignDay,
    EligibilityResult,
    Range,
    ScenarioDef,
    World,
)
from whsizing.schemas.trace import Tracer

WORLDS: tuple[World, ...] = ("lo", "typ", "hi")
# I58: SKU master columns F3 does not keep, besides the pack columns of `with_pack_data`
EXTRA = {"hazmat": pl.Boolean, "temperature_class": pl.Utf8}
REQUIRED = (
    "sku",
    "length_mm",
    "width_mm",
    "height_mm",
    "weight_kg",
    "unit_cube_m3",
    "lines",
    "units",
    "avg_stock",
    "stock_cube_m3",
    "abc",
    "units_per_pallet",
    "units_per_case",
    "cases_per_pallet",
)


def sku_frame(tables: ProfileTables, sku_master: pl.DataFrame | None) -> pl.DataFrame:
    """I58: F3 `ProfileTables.skus` + the canonical master's pack columns (`with_pack_data`) +
    `hazmat`, `temperature_class` (null when absent: not hazmat, ambient). Sorted by `sku`, so the
    row order of the inputs never changes a result (T6.8). Pass the same frame to F4
    `select_design_day(..., sku=..., catalog=...)` (I61) and to the engine."""
    sku = with_pack_data(tables.skus, sku_master)
    cols = [c for c in EXTRA if sku_master is not None and c in sku_master.columns]
    if sku_master is not None and cols:
        sku = sku.drop(cols, strict=False).join(
            sku_master.select("sku", *cols), on="sku", how="left"
        )
    missing = [pl.lit(None, t).alias(c) for c, t in EXTRA.items() if c not in sku.columns]
    return sku.with_columns(missing).sort("sku")


@dataclass(frozen=True, eq=False)
class WorldInputs:
    """Everything one world of one scenario reads. Built by `world_inputs`.

    `sku` = the I58 frame sorted by `sku` plus `eligible` (the scenario's mask after I48),
    `assumed`, `design_stock` (s_i, units), `design_stock_cube_m3` (s_i × v_i), `fits_shelf`,
    `manual_class`, `storage_class` (= picking zone, I17) and `zone` (main / overflow).
    """

    scenario: ScenarioDef
    world: World
    params: ParamSet
    catalog: Catalog
    family: Family
    basis: DesignBasis
    design_day: DesignDay
    sku: pl.DataFrame
    eligibility: EligibilityResult
    tracer: Tracer

    def v(self, param_id: str) -> float:
        """Catalog value in this world (after basis and scenario overrides)."""
        return self.params.value(param_id, self.world)

    def tid(self, key: str) -> str:
        """Trace id of a scenario quantity: `<scenario id>.<key>`."""
        return f"{self.scenario.id}.{key}"

    def record(
        self, key: str, label: str, value: float, unit: str, formula: str, inputs: dict[str, str]
    ) -> float:
        """Trace `<scenario id>.<key>` in this world; returns `value`."""
        sid, w = self.scenario.id, self.world
        return self.tracer.record(
            self.tid(key), label, value, unit, formula, inputs, scope=sid, world=w
        )


def world_inputs(
    basis: DesignBasis,
    design_day: DesignDay,
    scenario: ScenarioDef,
    catalog: Catalog,
    sku: pl.DataFrame,
    world: World,
    tracer: Tracer,
) -> WorldInputs:
    """The inputs of `scenario` in `world` (lo = pessimistic, typ, hi = optimistic; ADR-002).

    `sku` is the `sku_frame` output. Parameters: `ParamSet(catalog, basis.overrides,
    scenario.overrides)`. Design stock (F6a, F4 step 7): `s_i = avg_stock_i × stock_units* /
    Σ avg_stock` (proportional to average stock). Eligibility (F5, I10, I44): the scenario's
    `EligibilityCfg` on the family; the manual family takes every SKU (share 1, I17). I48: an
    automated scenario with no eligible line degenerates to manual (no SKU in its main class).
    The `S*.eligibility.*` fields are traced.
    """
    absent = [c for c in REQUIRED if c not in sku.columns]
    if absent:
        raise WhsizingError(f"engine: SKU frame lacks column(s) {absent}; build it with sku_frame")
    dup = sku.filter(pl.col("sku").is_duplicated())["sku"].unique().sort()
    if dup.len():
        raise DataQualityError(f"engine: the SKU frame repeats sku(s) {dup.head(5).to_list()}")
    params = ParamSet(catalog, basis.overrides, scenario.overrides)
    family = catalog.families[scenario.family]
    sku = _with_design_stock(sku.sort("sku"), design_day.stock_units)
    if scenario.family == "manual_p2p":
        mask = pl.Series("eligible", [True] * sku.height, pl.Boolean)
        assumed = pl.Series("assumed", [False] * sku.height, pl.Boolean)
    else:
        mask = eligible_mask(sku, family, scenario.eligibility)
        assumed = assumed_mask(sku, family, scenario.eligibility)
    elig = eligibility_shares(
        mask,
        sku["lines"],
        sku["stock_cube_m3"],
        family=scenario.family,
        low_share=params.value("engine.elig_low_line_share"),
        assumed=assumed,
    )
    effective = mask & (elig.share_lines > 0)  # I48: zero eligible lines → all manual
    sku = classify_skus(sku, scenario.family, effective, catalog, params)
    sku = sku.with_columns(assumed=assumed)
    inp = WorldInputs(
        scenario, world, params, catalog, family, basis, design_day, sku, elig, tracer
    )
    _trace_eligibility(inp)
    return inp


def to_range(values: Mapping[World, float], unit: str) -> Range:
    """ADR-002: lo = min over the three worlds, typ = the typical world, hi = max."""
    v = [values[w] for w in WORLDS]
    return Range(lo=min(v), typ=values["typ"], hi=max(v), unit=unit)


def _with_design_stock(sku: pl.DataFrame, stock_units: float) -> pl.DataFrame:
    """`design_stock` = avg_stock_i × stock_units* / Σ avg_stock (0 when no stock), and its cube
    with `unit_cube_m3` (null → 0, I10)."""
    avg = pl.col("avg_stock").cast(pl.Float64).fill_null(0.0)
    total = float(sku["avg_stock"].fill_null(0).sum())
    k = stock_units / total if total > 0 else 0.0
    return sku.with_columns(design_stock=avg * k).with_columns(
        design_stock_cube_m3=pl.col("design_stock") * pl.col("unit_cube_m3").fill_null(0.0)
    )


def _trace_eligibility(inp: WorldInputs) -> None:
    e = inp.eligibility
    data = {"mask": "data:sku.eligible", "lines": "data:sku.lines"}
    rows = [
        ("share_lines", "Eligible share of lines", e.share_lines, "Σ_elig lines / Σ lines"),
        (
            "share_stock_cube",
            "Eligible share of stock cube",
            e.share_stock_cube,
            "Σ_elig avg_stock × v / Σ avg_stock × v",
        ),
        ("share_skus", "Eligible share of SKUs", e.share_skus, "n_eligible / n_skus"),
        ("n_skus_eligible", "Eligible SKUs", e.n_skus_eligible, "count(eligible)"),
        ("n_skus_total", "SKUs", e.n_skus_total, "count(sku)"),
        (
            "assumed_share_lines",
            "Lines eligible by assumption",
            e.assumed_share_lines,
            "Σ_assumed lines / Σ lines",
        ),
    ]
    for key, label, value, formula in rows:
        inp.record(f"eligibility.{key}", label, float(value), "-", formula, data)
