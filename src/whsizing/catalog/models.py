"""Catalog file models (F5, Appendix C/D). Every model forbids unknown keys.

Ranged values are `CatalogParam` blocks (the YAML form of `whsizing.schemas.Param`: `id` and
`pessimistic_end` may be omitted). The loader turns them into `Param`s with flattened ids
(catalog/README.md) in `Catalog.params`; numeric scalars land in `Catalog.constants`.
Family sections hold the union of the three families' keys (all optional, so a key of no family
is rejected); `FAMILY_KEYS` then pins the exact key set of each family's sections, so a missing
family parameter or another family's key is rejected too.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, StringConstraints, field_validator, model_validator

from whsizing.schemas import Confidence, FamilyId, Param, StrictModel

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
)
TemperatureClass = Literal["ambient", "chilled", "frozen"]
# labor standard taken from the scenario's family, e.g. family.decant_cases_per_h
FamilyRef = Annotated[str, StringConstraints(pattern=r"^family\.\w+$")]
HHMM = Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Dims = tuple[float, float, float]


class CatalogModel(StrictModel):
    """Base of every catalog model: rejects unknown keys and non-finite numbers (.nan, .inf)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CatalogParam(CatalogModel):
    """A ranged value as written in a catalog file (§2.5 Param, F5 loader rules)."""

    id: str | None = None  # must equal the flattened id when given
    unit: str
    min: float
    typ: float
    max: float
    source: str
    confidence: Confidence
    pessimistic_end: Literal["min", "max"] | None = None  # inferred from unit/name when absent
    validated_by: str | None = None
    date: str | dt.date  # `2026-11` is read as 2026-11-01 by Param
    note: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not (self.min <= self.typ <= self.max):
            raise ValueError(f"min ≤ typ ≤ max violated ({self.min}, {self.typ}, {self.max})")
        return self


P = CatalogParam
OptP = CatalogParam | None


class I18n(CatalogModel):
    fr: str
    en: str


class Constraints(CatalogModel):
    max_item_mm: Dims  # compared orientation-agnostic (sorted)
    max_weight_kg: float
    excludes_hazmat: bool
    temperature_classes: list[TemperatureClass]
    min_scale_lines_day: float


class PalletRack(CatalogModel):
    positions_per_m2_per_level: P
    pallet_load_height_mm: float
    beam_pitch_mm: float
    top_clearance_m: float
    max_levels: int
    fill_factor: P


class Shelving(CatalogModel):
    bins_per_m2_per_level: P
    bin_net_cube_m3: float
    bin_pitch_mm: float
    shelf_max_height_m: float
    ergonomic_max_levels: int
    fill_factor: P


class PickFacePolicy(CatalogModel):
    classes_with_pick_face: list[Literal["A", "B", "C"]]
    faces_per_sku: int


class Storage(CatalogModel):
    # manual_p2p
    pallet_rack: PalletRack | None = None
    shelving: Shelving | None = None
    pick_face_policy: PickFacePolicy | None = None
    # amr_gtp
    bins_per_pod: OptP = None
    pod_bin_net_cube_m3: float | None = None
    pod_footprint_m2: OptP = None
    # cube_asrs
    bin_dims_mm: Dims | None = None
    bin_net_cube_m3: float | None = None
    bins_per_m2_per_level: OptP = None
    level_height_mm: float | None = None
    grid_overhead_m: float | None = None
    max_levels: int | None = None
    # amr_gtp, cube_asrs
    fill_factor: OptP = None
    empty_bin_reserve: float | None = None


class Throughput(CatalogModel):
    # manual_p2p
    pick_rate_shelving_lines_h: OptP = None
    pick_rate_pallet_lines_h: OptP = None
    eta_pick: OptP = None
    forklift_moves_h: OptP = None
    replen_units_per_move: OptP = None
    # amr_gtp
    station_rate_lines_h: OptP = None
    lines_per_pod_visit: OptP = None
    robot_pod_moves_h: OptP = None
    charging_reserve: float | None = None
    max_robots_per_m2: CatalogParam | float | None = None  # amr scalar (C.2), cube [P] block
    # cube_asrs
    port_rate_lines_h: OptP = None
    lines_per_bin_presentation: OptP = None
    dig_factor: OptP = None
    robot_bins_per_h: OptP = None
    # amr_gtp, cube_asrs
    oee: OptP = None
    robot_availability: OptP = None
    decant_cases_per_h: OptP = None


class Area(CatalogModel):
    m2_per_pack_station: OptP = None
    m2_per_station: OptP = None
    m2_per_robot_parking: OptP = None
    m2_per_port: OptP = None
    service_aisle_share: float | None = None


class Capex(CatalogModel):
    # manual_p2p
    per_pallet_position_eur: OptP = None
    per_shelf_bin_eur: OptP = None
    per_forklift_eur: OptP = None
    per_cart_eur: OptP = None
    wms_adaptation_fixed_eur: OptP = None
    building_works_per_m2_eur: OptP = None
    # amr_gtp
    per_station_eur: OptP = None
    per_pod_eur: OptP = None
    fleet_software_fixed_eur: OptP = None
    charging_per_robot_eur: OptP = None
    # cube_asrs
    per_bin_eur: OptP = None
    grid_structure_per_m2_eur: OptP = None
    per_port_eur: OptP = None
    controls_fixed_eur: OptP = None
    # amr_gtp, cube_asrs
    per_robot_eur: OptP = None
    floor_prep_per_m2_eur: OptP = None
    # all
    integration_share: float
    commissioning_share: float
    contingency_share: float


class Opex(CatalogModel):
    maintenance_share_of_equipment_capex: P
    kwh_per_forklift_year: OptP = None
    kwh_per_robot_year: OptP = None
    software_eur_year: P


class Life(CatalogModel):
    equipment_life_years: int
    renewal_share: float


_SHARES = frozenset({"integration_share", "commissioning_share", "contingency_share"})
_OPEX = frozenset({"maintenance_share_of_equipment_capex", "software_eur_year"})
# Exact keys of each family's sections (Appendix C.1, C.2, F5 schema + CHANGELOG additions).
# `constraints` and `life` are the same for every family and fully required by their models.
FAMILY_KEYS: dict[FamilyId, dict[str, frozenset[str]]] = {
    "manual_p2p": {
        "storage": frozenset({"pallet_rack", "shelving", "pick_face_policy"}),
        "throughput": frozenset(
            {"pick_rate_shelving_lines_h", "pick_rate_pallet_lines_h", "eta_pick"}
            | {"forklift_moves_h", "replen_units_per_move"}
        ),
        "area": frozenset({"m2_per_pack_station"}),
        "capex": _SHARES
        | {"per_pallet_position_eur", "per_shelf_bin_eur", "per_forklift_eur", "per_cart_eur"}
        | {"wms_adaptation_fixed_eur", "building_works_per_m2_eur"},
        "opex": _OPEX | {"kwh_per_forklift_year"},
    },
    "amr_gtp": {
        "storage": frozenset(
            {"bins_per_pod", "pod_bin_net_cube_m3", "pod_footprint_m2", "fill_factor"}
            | {"empty_bin_reserve"}
        ),
        "throughput": frozenset(
            {"station_rate_lines_h", "oee", "lines_per_pod_visit", "robot_pod_moves_h"}
            | {"robot_availability", "charging_reserve", "decant_cases_per_h", "max_robots_per_m2"}
        ),
        "area": frozenset({"m2_per_station", "m2_per_robot_parking"}),
        "capex": _SHARES
        | {"per_robot_eur", "per_station_eur", "per_pod_eur", "fleet_software_fixed_eur"}
        | {"floor_prep_per_m2_eur", "charging_per_robot_eur"},
        "opex": _OPEX | {"kwh_per_robot_year"},
    },
    "cube_asrs": {
        "storage": frozenset(
            {"bin_dims_mm", "bin_net_cube_m3", "bins_per_m2_per_level", "level_height_mm"}
            | {"grid_overhead_m", "max_levels", "fill_factor", "empty_bin_reserve"}
        ),
        "throughput": frozenset(
            {"port_rate_lines_h", "oee", "lines_per_bin_presentation", "dig_factor"}
            | {"robot_bins_per_h", "robot_availability", "decant_cases_per_h", "max_robots_per_m2"}
        ),
        "area": frozenset({"m2_per_port", "service_aisle_share", "m2_per_robot_parking"}),
        "capex": _SHARES
        | {"per_bin_eur", "grid_structure_per_m2_eur", "per_robot_eur", "per_port_eur"}
        | {"controls_fixed_eur", "floor_prep_per_m2_eur"},
        "opex": _OPEX | {"kwh_per_robot_year"},
    },
}


class Family(CatalogModel):
    """One automation family file (catalog/families/<id>.yaml); sections per `FAMILY_KEYS`."""

    id: FamilyId
    title: I18n
    version: str
    description: I18n | None = None
    constraints: Constraints
    storage: Storage
    throughput: Throughput
    area: Area
    capex: Capex
    opex: Opex
    life: Life

    @field_validator("version", mode="before")
    @classmethod
    def _semver(cls, v: object) -> object:
        if not SEMVER.match(str(v)):
            raise ValueError(f"version {v!r} is not semver (MAJOR.MINOR.PATCH, e.g. 0.1.0)")
        return str(v)

    @model_validator(mode="after")
    def _family_keys(self) -> Self:
        problems: list[str] = []
        for section, expected in FAMILY_KEYS[self.id].items():
            sec = getattr(self, section)
            given = {k for k in type(sec).model_fields if getattr(sec, k) is not None}
            problems += [
                f"{section}.{k}: missing (required for {self.id})" for k in sorted(expected - given)
            ]
            problems += [
                f"{section}.{k}: not a {self.id} parameter" for k in sorted(given - expected)
            ]
        # the one key whose shape differs by family: a scalar in C.2, a Param block in cube (0.2.0)
        robots = self.throughput.max_robots_per_m2
        shape = {"amr_gtp": float, "cube_asrs": CatalogParam}.get(self.id)
        if shape and robots is not None and not isinstance(robots, shape):
            want = "a number" if shape is float else "a Param block"
            problems.append(f"throughput.max_robots_per_m2: must be {want} for {self.id}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class Activity(CatalogModel):
    """A labor activity: driver + standard + role, or a share of direct hours (indirect)."""

    driver: str | None = None
    standard: CatalogParam | FamilyRef | None = None
    share_of_direct_hours: float | None = None
    role: str

    @model_validator(mode="after")
    def _shape(self) -> Self:
        direct = self.driver is not None and self.standard is not None
        if direct == (self.share_of_direct_hours is not None):
            raise ValueError("give either driver + standard, or share_of_direct_hours")
        return self


class LaborProfiles(CatalogModel):
    outbound_lag_hours: float
    inbound_window: tuple[HHMM, HHMM]  # quoted "06:00": unquoted YAML 1.1 reads 06:00 as 360


class LaborStandards(CatalogModel):
    roles: dict[str, str]  # activity role key → finance.labor_cost_eur_h key
    activities: dict[str, Activity]
    profiles: LaborProfiles

    @model_validator(mode="after")
    def _roles_known(self) -> Self:
        bad = sorted(a for a, act in self.activities.items() if act.role not in self.roles)
        if bad:
            raise ValueError(f"activities {bad} use a role missing from roles {sorted(self.roles)}")
        return self


class FinanceDefaults(CatalogModel):
    packaging_eur_per_order: P
    fixed_energy_kwh_year: float
    default_roles_cost_eur_h: dict[str, float]
    wms_adaptation_default_eur: float
    kwh_per_station_year: P


class StorageClasses(CatalogModel):
    pallet_threshold_m3: float
    shelf_bin_net_cube_m3: float
    max_bins_per_sku_shelf: int
    shelf_item_max_mm: Dims
    mixed_bins_allowed: bool
    skus_per_mixed_bin: int
    mixed_bin_threshold_share: float
    default_units_per_pallet: float


class AreaFactors(CatalogModel):
    m2_per_pallet_staged: float
    staging_days: float
    parcels_per_pallet_equiv: float
    m2_per_return_line_day: float
    returns_fixed_m2: float
    maintenance_fixed_m2: float
    m2_per_head_amenities: float
    amenities_fixed_m2: float
    circulation_share: float
    receiving_window_hours: float
    peak_hour_share_inbound: float


class IcpeRegime(CatalogModel):
    label: str
    min_m3: float
    max_m3: float | None  # None = no upper bound


class IcpeTable(CatalogModel):
    """ICPE rubrique 1510 regimes [VERIFY], informational only."""

    regimes: list[IcpeRegime]
    note_fr: str

    def regime(self, volume_m3: float) -> str | None:
        """Label of the regime with min_m3 ≤ volume < max_m3; None below the first regime."""
        for r in self.regimes:
            if r.min_m3 <= volume_m3 and (r.max_m3 is None or volume_m3 < r.max_m3):
                return r.label
        return None


class EngineDefaults(CatalogModel):
    """[P] constants of F4/F6 with no home in Appendix C/D (see engine_defaults.yaml)."""

    eta_flow: float
    receipt_lines_per_pallet_full: float
    receipt_lines_per_pallet_mixed: float
    core_day_percentile: float
    sla_wait_threshold_share: float
    sla_risk_max_probability: float
    elig_low_line_share: float
    # I85 (b). A default: the catalog copy of a run made before this key existed still loads.
    max_equipment_count: float = 100_000
    pack_station_oee: P


class Catalog(CatalogModel):
    """The loaded catalog. Engine code reads values through `ParamSet`, by id."""

    version: str  # catalog_version(): family semvers + content hash
    families: dict[FamilyId, Family]
    labor: LaborStandards
    finance: FinanceDefaults
    storage: StorageClasses
    area: AreaFactors
    icpe: IcpeTable
    engine: EngineDefaults
    params: dict[str, Param]  # flattened id → Param (pessimistic_end resolved)
    constants: dict[str, float]  # flattened id → structural scalar
    warnings: list[str] = []

    @property
    def todo_count(self) -> int:
        """Number of parameters whose source is still "TODO" (printed in the report)."""
        return sum(p.source == "TODO" for p in self.params.values())
