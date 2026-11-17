"""ScenarioResult and the per-step results of the sizing engine (§2.5, F5-F6)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from whsizing.schemas.params import FamilyId, Range, StrictModel
from whsizing.schemas.scenario import ScenarioDef

StorageClass = Literal["pallet_rack", "shelving", "cube_bin", "pod_bin"]


class Flag(StrictModel):
    code: str  # F_NO_FIT, F_DOCK_SHORTFALL, F_SLA_RISK, F_LOW_CONFIDENCE, ...
    severity: Literal["info", "warning", "blocking"]
    message: str
    value: float | None = None


class EligibilityResult(StrictModel):
    """F5 eligibility step 4. Overflow share = 1 − share, routed to the overflow family."""

    family: FamilyId
    share_lines: float
    share_stock_cube: float
    share_skus: float
    n_skus_eligible: int
    n_skus_total: int
    assumed_share_lines: float = 0.0  # lines eligible only by assumption (F_ELIG_ASSUMED)
    flags: list[Flag] = []  # F_ELIG_LOW, F_ELIG_ASSUMED (added by F5)


class StorageClassResult(StrictModel):
    """F6a: one storage class in the main (eligible) zone or the manual overflow zone."""

    storage_class: StorageClass
    zone: Literal["main", "overflow"]
    n_skus: int
    positions: Range  # pallet positions or bins (incl. pick faces and empty-bin reserve)
    levels: int | None  # None for pod_bin
    area_m2: Range  # includes aisles
    pods: Range | None = None  # pod_bin only
    grid_area_m2: Range | None = None  # cube_bin only: A_grid before service aisles


class StorageResult(StrictModel):
    classes: list[StorageClassResult]
    total_area_m2: Range
    height_utilisation: float  # used height / clear height (typ)
    flags: list[Flag] = []  # F_HEIGHT_LIMIT, F_ELIG_LOW


class ActivityLabor(StrictModel):
    """F6c: one activity on the design day plus its annual series."""

    activity: str  # receiving, put_away, decant, replenishment, picking, packing_S, ...
    role: str  # key of finance.labor_cost_eur_h
    driver: str  # pallets_in, lines, orders_S, ...
    workload: float  # design-day driver quantity
    hours: Range  # design-day hours incl. PF&D
    heads: Range  # hours / (paid_hours_per_person_day × utilisation)
    roster: Range  # Σ_shift heads_shift × (1 + absenteeism)
    annual_hours: list[Range]  # years 1..T


class ShiftRow(StrictModel):
    """F6c shift table (typical world)."""

    shift: int  # 1..shifts_per_day
    start_hour: float
    end_hour: float
    activity: str
    hours: float
    heads: float


class LaborResult(StrictModel):
    activities: list[ActivityLabor]
    total_hours: Range  # design day
    total_heads: Range  # design day
    roster: Range
    annual_hours: list[Range]  # years 1..T, all activities
    core_fte: list[Range]  # years 1..T
    temp_hours: list[Range]  # years 1..T
    shifts: list[ShiftRow]


class AreaResult(StrictModel):
    """F6d: area budget, fit, docks and the informational ICPE regime."""

    zones: dict[str, Range]  # receiving_staging, shipping_staging, packing, ports, storage, ...
    total_m2: Range
    building_m2: float
    fit: bool  # total.typ ≤ building area
    utilisation: Range  # total / building area
    deficit_m2: Range  # max(0, total − area)
    docks_in_required: float
    docks_out_required: float
    icpe_volume_m3: float  # building area × clear height
    icpe_regime: str | None  # label from icpe_1510.yaml, informational only
    amenities_external: bool = False
    flags: list[Flag] = []  # F_NO_FIT, F_DOCK_SHORTFALL, F_AMENITIES_EXTERNAL


class QueueResource(StrictModel):
    """F6e: Erlang-C check on one pool of servers (packing, GTP stations, ports)."""

    resource: str
    servers: int  # c
    arrival_rate_h: float  # λ_s
    service_rate_h: float  # μ per server
    offered_load: float  # a = λ_s / μ
    stable: bool  # a < c
    p_wait: float | None  # None when unstable
    w_q_h: float | None
    t_h: float  # threshold used for P(W > t)
    p_wait_gt_t: float | None
    c_min: int | None = None  # ceil(a) + 1 when unstable


class QueueResult(StrictModel):
    resources: list[QueueResource]
    flags: list[Flag] = []  # F_SLA_RISK, F_UNSTABLE


class ScenarioResult(StrictModel):
    scenario: ScenarioDef
    eligibility: EligibilityResult
    storage: StorageResult
    equipment: dict[str, Range]  # "gtp_stations", "robots", "ports", "pickers_peak", ...
    bottleneck: str
    labor: LaborResult
    area: AreaResult
    queue: QueueResult
    flags: list[Flag]
    trace_path: str
    status: Literal["computed", "not_computed"] = "computed"
    status_reason: str | None = None  # required when not_computed (F8 edge case)

    @model_validator(mode="after")
    def _reason(self) -> Self:
        if self.status == "not_computed" and not self.status_reason:
            raise ValueError("status_reason is required when status is not_computed")
        return self
