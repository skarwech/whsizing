"""Independent golden oracle (G1, T1.5): the tiny_golden case computed from description.md alone.

Never imports `whsizing`. Typical world only (every Param at `typ`). Each function names the
formula it implements (Appendix B / F-section). Where the spec is silent or ambiguous the rule
chosen is numbered in docs/INTERPRETATIONS.md and cited here as `I<n>`.

Catalog typ values and formulas only. The F3-F5 stages (demand.py) and F6-F7 stages
(build_golden.py) record every number into an `Out` collector; workbook.py writes it to
golden_values.json and golden_case.xlsx.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
import numpy_financial as npf
from dateutil.relativedelta import relativedelta

# --- Catalog typ values, typed in from the spec -------------------------------------------------
# F5 cube_asrs example (description.md 790-837)
CUBE: dict[str, Any] = {
    "max_item_mm": (600, 400, 300),
    "max_weight_kg": 25.0,
    "excludes_hazmat": True,
    "temperature_classes": ("ambient", "chilled"),
    "min_scale_lines_day": 1500,
    "bin_net_cube_m3": 0.055,
    "bins_per_m2_per_level": 3.0,
    "level_height_mm": 330,
    "grid_overhead_m": 1.2,
    "max_levels": 20,
    "fill_factor": 0.88,
    "empty_bin_reserve": 0.05,
    "port_rate_lines_h": 350.0,
    "oee": 0.85,
    "lines_per_bin_presentation": 1.3,
    "dig_factor": 1.6,
    "robot_bins_per_h": 22.0,
    "robot_availability": 0.95,
    "decant_cases_per_h": 90.0,
    "max_robots_per_m2": 0.05,  # catalog 0.2.0 analog, no spec value (I46)
    "m2_per_port": 20.0,
    "m2_per_robot_parking": 2.0,  # F6d line 995; catalog 0.2.0 Param (I26)
    "service_aisle_share": 0.08,
    "per_bin_eur": 40.0,
    "grid_structure_per_m2_eur": 650.0,
    "per_robot_eur": 35000.0,
    "per_port_eur": 60000.0,
    "controls_fixed_eur": 150000.0,
    "floor_prep_per_m2_eur": 20.0,  # catalog 0.2.0 analog of amr_gtp (C.2 l.1670), I30
    "integration_share": 0.10,
    "commissioning_share": 0.05,
    "contingency_share": 0.10,
    "maintenance_share_of_equipment_capex": 0.05,
    "kwh_per_robot_year": 1200.0,
    "software_eur_year": 40000.0,
    "equipment_life_years": 12,
    "renewal_share": 0.6,
}
# Appendix C.1 manual_p2p.yaml (1584-1633)
MANUAL: dict[str, Any] = {
    "pallet_rack_positions_per_m2_per_level": 0.38,
    "pallet_load_height_mm": 1400,
    "beam_pitch_mm": 150,
    "top_clearance_m": 0.6,
    "pallet_max_levels": 6,
    "pallet_rack_fill_factor": 0.85,
    "shelving_bins_per_m2_per_level": 8.0,
    "bin_pitch_mm": 400,
    "shelf_max_height_m": 2.1,
    "ergonomic_max_levels": 5,
    "shelving_fill_factor": 0.80,
    "pick_face_classes": ("A", "B"),
    "faces_per_sku": 1,
    "pick_rate_shelving_lines_h": 70.0,
    "pick_rate_pallet_lines_h": 35.0,
    "eta_pick": 0.85,
    "forklift_moves_h": 16.0,
    "replen_units_per_move": 80.0,
    "m2_per_pack_station": 12.0,
    "per_pallet_position_eur": 90.0,
    "per_shelf_bin_eur": 12.0,
    "per_forklift_eur": 35000.0,
    "per_cart_eur": 1500.0,
    "wms_adaptation_fixed_eur": 50000.0,
    "building_works_per_m2_eur": 60.0,
    "integration_share": 0.05,
    "commissioning_share": 0.02,
    "contingency_share": 0.10,
    "maintenance_share_of_equipment_capex": 0.04,
    "kwh_per_forklift_year": 4500.0,
    "software_eur_year": 15000.0,
    "equipment_life_years": 10,
    "renewal_share": 0.5,
}
# Appendix D storage_classes.yaml (1689-1696)
STORAGE: dict[str, Any] = {
    "pallet_threshold_m3": 0.6,
    "shelf_bin_net_cube_m3": 0.040,
    "max_bins_per_sku_shelf": 6,
    "shelf_item_max_mm": (500, 400, 350),
    "mixed_bins_allowed": True,
    "skus_per_mixed_bin": 4,
    "mixed_bin_threshold_share": 0.2,
    "default_units_per_pallet": 400,
}
# Appendix D area_factors.yaml (1699-1709)
AREA: dict[str, float] = {
    "m2_per_pallet_staged": 1.5,
    "staging_days": 1.0,
    "parcels_per_pallet_equiv": 40.0,
    "m2_per_return_line_day": 0.05,
    "returns_fixed_m2": 30.0,
    "maintenance_fixed_m2": 40.0,
    "m2_per_head_amenities": 4.0,
    "amenities_fixed_m2": 150.0,
    "circulation_share": 0.25,
    "peak_hour_share_inbound": 0.2,
}
# Appendix D labor_standards.yaml (1712-1725): activity → (role, typ standard per hour)
LABOR: dict[str, tuple[str, float]] = {
    "receiving": ("forklift", 14.0),
    "receipt_check": ("operator", 45.0),
    "put_away": ("forklift", 13.0),
    "replenishment": ("forklift", 14.0),
    "packing_S": ("operator", 55.0),
    "packing_ML": ("operator", 25.0),
    "shipping_parcel": ("operator", 110.0),
    "shipping_pallet": ("forklift", 14.0),
    "returns": ("operator", 22.0),
}
INDIRECT_SHARE = 0.12  # labor_standards.yaml indirect.share_of_direct_hours
ROLES = {"operator": "operator", "forklift": "forklift_driver", "lead": "team_leader"}
# Appendix D finance_defaults.yaml (1731-1732)
PACKAGING_EUR_PER_ORDER = 0.9
FIXED_ENERGY_KWH_YEAR = 20000.0
# Constants the spec values outside a catalog file (F4 766, F6b 930) or not at all (I24, I32)
ETA_FLOW = 0.85
RECEIPT_LINES_PER_PALLET = {"full": 1.0, "mixed": 4.0}
PACK_STATION_OEE = 0.85  # I24: no spec value; same as catalog/engine_defaults.yaml
KWH_PER_STATION_YEAR = 1500.0  # I32: no spec value; same as catalog finance.kwh_per_station_year
ICPE_REGIMES = [
    ("Déclaration (D/DC)", 5000.0, 50000.0),
    ("Enregistrement (E)", 50000.0, 900000.0),
    ("Autorisation (A)", 900000.0, math.inf),
]
METRICS = ("lines", "orders", "units", "cube_m3", "weight_kg", "parcels", "pallets_out")
# F3 step 7 default intraday profile (I51): no spec value; same as ProfileCfg.default_intraday
# ([P] flat 08:00-17:00), used when more than 20 % of lines have no time component.
DEFAULT_INTRADAY = [0.0] * 8 + [1.0 / 9] * 9 + [0.0] * 7
NO_TIME_SHARE_MAX = 0.20
DEAD_STOCK_DAYS = 180  # F3 step 5 [P]
# F_LOW_CONFIDENCE (I47): catalog Param blocks (catalog/ YAML, all confidence L) the formulas read,
# as `<prefix>.<name>` = the catalog `id`.
LOW_CONFIDENCE: dict[str, tuple[str, ...]] = {
    "manual_p2p": (
        *("pallet_rack_positions_per_m2_per_level", "pallet_rack_fill_factor"),
        *("shelving_bins_per_m2_per_level", "shelving_fill_factor"),
        *("pick_rate_shelving_lines_h", "pick_rate_pallet_lines_h", "eta_pick"),
        *("forklift_moves_h", "replen_units_per_move", "m2_per_pack_station"),
        *("per_pallet_position_eur", "per_shelf_bin_eur", "per_forklift_eur", "per_cart_eur"),
        *("wms_adaptation_fixed_eur", "building_works_per_m2_eur"),
        *("maintenance_share_of_equipment_capex", "kwh_per_forklift_year", "software_eur_year"),
    ),
    "cube_asrs": (
        *("bins_per_m2_per_level", "fill_factor", "port_rate_lines_h", "oee"),
        *("lines_per_bin_presentation", "dig_factor", "robot_bins_per_h", "robot_availability"),
        *("decant_cases_per_h", "max_robots_per_m2", "m2_per_port", "m2_per_robot_parking"),
        *("per_bin_eur", "grid_structure_per_m2_eur", "per_robot_eur", "per_port_eur"),
        *("controls_fixed_eur", "floor_prep_per_m2_eur"),
        *("maintenance_share_of_equipment_capex", "kwh_per_robot_year", "software_eur_year"),
    ),
    "labor": tuple(LABOR),
    "finance": ("packaging_eur_per_order",),
    "engine": ("pack_station_oee",),
}
# manual_p2p Params the cube scenario does not read for its overflow zone (I29, I30, I35)
MANUAL_NOT_IN_OVERFLOW = ("wms_adaptation_fixed_eur", "software_eur_year")
# Read only by families with stations / ports (F7 energy "stations × kWh_per_station_year", I32)
STATION_PARAMS = ("finance.kwh_per_station_year",)


@dataclass
class Out:
    """Ordered (sheet, key, value, unit, formula) rows. Deliberately stateful, like the Tracer."""

    rows: list[tuple[str, str, Any, str, str]] = field(default_factory=list)
    sheet: str = ""

    def put(self, key: str, value: Any, unit: str, formula: str) -> Any:
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{key}: non-finite value {value}")
        self.rows.append((self.sheet, key, value, unit, formula))
        return value

    def values(self) -> dict[str, Any]:
        keys = [r[1] for r in self.rows]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            raise ValueError(f"duplicate golden keys: {sorted(dupes)}")
        return {r[1]: r[2] for r in self.rows}


# --- Formulas (one per Appendix B line) ---------------------------------------------------------
def series_stats(x: np.ndarray) -> dict[str, float]:
    """F3 step 2: mean, P50/P90/P95/P98 (np.percentile, linear), max, CV = std(ddof=0)/mean (I3)."""
    mean = float(np.mean(x))
    stats = {"mean": mean}
    stats |= {f"p{q}": float(np.percentile(x, q)) for q in (50, 90, 95, 98)}
    stats["max"] = float(np.max(x))
    stats["cv"] = float(np.std(x) / mean) if mean else 0.0
    return stats


def operating_threshold(daily_lines: np.ndarray, share: float = 0.10) -> float:
    """App. B operating day: lines_d ≥ max(1, share × median(lines_d > 0))."""
    positive = daily_lines[daily_lines > 0]
    return max(1.0, share * float(np.median(positive))) if positive.size else 1.0


def growth_factor(g: float, years: float) -> float:
    """App. B growth: (1 + g)^T."""
    return (1.0 + g) ** years


def abc_classes(lines_desc: list[int], a: float = 0.80, b: float = 0.95) -> list[str]:
    """F3 step 4 (I6): SKUs sorted by lines desc; class by cumulative share *before* the SKU."""
    total = sum(lines_desc)
    out, cum = [], 0.0
    for n in lines_desc:
        out.append("A" if cum < a else "B" if cum < b else "C")
        cum += n / total
    return out


def is_pallet_order(weight_kg: float, cube_m3: float, w_max: float, c_max: float) -> bool:
    """F3 step 8: pallet if weight > pallet_order_weight_kg or cube > pallet_order_cube_m3."""
    return weight_kg > w_max or cube_m3 > c_max


def parcels_per_order(weight_kg: float, parcel_max_kg: float) -> int:
    """F3 step 8: parcels = ceil(weight / parcel_max_weight_kg), minimum 1."""
    return max(1, math.ceil(weight_kg / parcel_max_kg))


def fits(dims_mm: tuple[float, float, float], limits_mm: tuple[float, float, float]) -> bool:
    """F5 eligibility steps 1-2: sorted dims ≤ sorted limits, orientation-agnostic."""
    return all(
        d <= lim
        for d, lim in zip(
            sorted(dims_mm, reverse=True), sorted(limits_mm, reverse=True), strict=True
        )
    )


def manual_class(dims_ok: bool, stock_cube: float) -> str:
    """F6a storage class for the manual family or overflow."""
    if not dims_ok or stock_cube >= STORAGE["pallet_threshold_m3"]:
        return "pallet_rack"
    if stock_cube <= STORAGE["shelf_bin_net_cube_m3"] * STORAGE["max_bins_per_sku_shelf"]:
        return "shelving"
    return "pallet_rack"


def pallets_i(s_units: float, units_per_pallet: float) -> int:
    """App. B: pallets_i = ceil(s_i / units_per_pallet_i)."""
    return math.ceil(s_units / units_per_pallet)


def pallet_positions(sum_pallets: float, fill: float, pick_faces: int) -> float:
    """F6a: Σ pallets_i / fill_pallet, + 1 pick face per A/B SKU in pallet_rack (I11)."""
    return sum_pallets / fill + pick_faces


def shelf_bins_i(stock_cube: float, bin_net_cube: float, fill: float) -> int:
    """F6a shelving: bins_i = max(1, ceil(stock_cube_i / (shelf_bin_net_cube × fill_shelf)))."""
    return max(1, math.ceil(stock_cube / (bin_net_cube * fill)))


def cube_bins_i(stock_cube: float) -> float:
    """F6a cube_bin: max(1, ceil(sc / (bin_net × fill))); 1/4 bin if sc < 0.2 × bin_net (I43)."""
    bins = max(1, math.ceil(stock_cube / (CUBE["bin_net_cube_m3"] * CUBE["fill_factor"])))
    small = stock_cube < STORAGE["mixed_bin_threshold_share"] * CUBE["bin_net_cube_m3"]
    if small and STORAGE["mixed_bins_allowed"]:
        return 1.0 / STORAGE["skus_per_mixed_bin"]
    return float(bins)


def fit_levels(usable_height_m: float, pitch_m: float) -> int:
    """floor(usable height / pitch) with a 1e-9 tolerance (I63 (11)): (7.8 − 1.2) / 0.33 is
    19.999999999999996 in floats, 20 levels on paper."""
    return math.floor(usable_height_m / pitch_m + 1e-9)


def levels(usable_height_m: float, pitch_m: float, cap: int) -> int:
    """App. B levels: min(cap, fit_levels(usable height, level pitch)), at least 1 (F6 edge
    case)."""
    return max(1, min(cap, fit_levels(usable_height_m, pitch_m)))


def class_area(positions: float, n_levels: int, per_m2_per_level: float) -> float:
    """App. B area_class: positions / (levels × positions_per_m2_per_level)."""
    return positions / (n_levels * per_m2_per_level)


def ceil_div(load: float, capacity: float) -> int:
    """App. B stations/ports/pickers: ceil(λ / (rate × efficiency)); 0 when there is no load."""
    return math.ceil(load / capacity) if load > 0 else 0


def labor_hours(workload: float, productivity: float, pfd: float) -> float:
    """App. B hours_a: workload / productivity × (1 + PF&D)."""
    return workload / productivity * (1.0 + pfd)


def heads(hours: float, paid_hours: float, utilisation: float) -> float:
    """App. B heads_a: hours / (paid_hours_per_person_day × utilisation)."""
    return hours / (paid_hours * utilisation)


def shift_heads(hours: float, hours_per_shift: float, utilisation: float) -> float:
    """F6c: hours in shift / (hours_per_shift × utilisation), floor 1 per staffed activity (I19)."""
    return max(1.0, hours / (hours_per_shift * utilisation)) if hours > 0 else 0.0


def erlang_c(c: int, a: float) -> float:
    """F6e / App. B Erlang-C via the Erlang-B recursion; requires a < c."""
    if a >= c:
        raise ValueError(f"unstable queue: offered load {a} ≥ servers {c}")
    b = 1.0
    for k in range(1, c + 1):
        b = a * b / (k + a * b)
    rho = a / c
    return b / (1 - rho + rho * b)


def erlang_wq(c: int, lam: float, mu: float) -> float:
    """App. B W_q = P_wait / (cμ − λ), hours."""
    return erlang_c(c, lam / mu) / (c * mu - lam)


def docks(trucks_peak_h: float, dwell_h: float, dock_utilisation: float) -> int:
    """App. B docks: ceil(trucks_peak_h × dwell_h / dock_utilisation)."""
    return ceil_div(trucks_peak_h * dwell_h, dock_utilisation)


def npv(rate: float, flows: list[float]) -> float:
    """App. B NPV: Σ_t Δcf_t / (1 + r)^t, t = 0..T (flows[0] undiscounted)."""
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(flows))


def irr(flows: list[float]) -> float | None:
    """F7: numpy_financial.irr; None unless exactly one sign change (I37)."""
    signs = [cf > 0 for cf in flows if cf != 0]
    if sum(a != b for a, b in itertools.pairwise(signs)) != 1:
        return None
    value = float(npf.irr(flows))
    return value if math.isfinite(value) else None


def payback(flows: list[float]) -> float | None:
    """App. B payback: first t with cumulative Δcf ≥ 0, linear within the year; None if never."""
    cum = 0.0
    for t, cf in enumerate(flows):
        if cum + cf >= 0:
            return 0.0 if t == 0 else (t - 1) + (-cum) / cf
        cum += cf
    return None


def annuity_factor(rate: float, years: int) -> float:
    """App. B cost_per_line: r / (1 − (1 + r)^−T)."""
    return rate / (1.0 - (1.0 + rate) ** -years)


def icpe_regime(volume_m3: float) -> str | None:
    """F6d icpe_1510.yaml lookup on building area × clear height (info only)."""
    return next((lab for lab, lo, hi in ICPE_REGIMES if lo <= volume_m3 < hi), None)


def hours_between(start: str, end: str) -> float:
    """F4 edge case: departure − cutoff in hours, modulo 24 h (crossing midnight allowed)."""
    (h1, m1), (h2, m2) = (map(int, start.split(":")[:2]), map(int, end.split(":")[:2]))
    return ((h2 * 60 + m2) - (h1 * 60 + m1)) % 1440 / 60.0


def sla_window_hours(service: dict[str, Any]) -> float:
    """I16: explicit service.sla_window_hours (> 0), else carrier_departure_time − cutoff_time
    modulo 24 h; equal times → 24 h (the departure is the next day's)."""
    explicit = service.get("sla_window_hours")
    if explicit is not None:
        if explicit <= 0:
            raise ValueError(f"service.sla_window_hours must be > 0, got {explicit}")
        return float(explicit)
    return hours_between(service["cutoff_time"], service["carrier_departure_time"]) or 24.0


def erlang_queue(c: int, lam: float, mu: float, t_h: float) -> dict[str, Any]:
    """F6e on one server pool (QueueResource fields): a = λ_s/μ; Erlang-C P_wait,
    W_q = P_wait / (cμ − λ_s), P(W > t) = P_wait × exp(−(cμ − λ_s) t); unstable when a ≥ c."""
    a = lam / mu
    q: dict[str, Any] = {"servers": c, "arrival_rate_h": lam, "service_rate_h": mu}
    q |= {"offered_load": a, "stable": a < c, "t_h": t_h}
    if a >= c:
        return q | {"p_wait": None, "w_q_h": None, "p_wait_gt_t": None, "c_min": math.ceil(a) + 1}
    p_wait, slack = erlang_c(c, a), c * mu - lam
    tail = p_wait * math.exp(-slack * t_h)
    return q | {"p_wait": p_wait, "w_q_h": p_wait / slack, "p_wait_gt_t": tail, "c_min": None}


def low_confidence_params(family: str) -> list[str]:
    """I47: ids of the confidence-L Params a scenario of `family` reads (F_LOW_CONFIDENCE count)."""
    manual = [f"manual_p2p.{k}" for k in LOW_CONFIDENCE["manual_p2p"]]
    stations: tuple[str, ...] = ()
    if family == "cube_asrs":
        manual = [p for p in manual if p.split(".")[1] not in MANUAL_NOT_IN_OVERFLOW]
        manual = [f"cube_asrs.{k}" for k in LOW_CONFIDENCE["cube_asrs"]] + manual
        stations = STATION_PARAMS
    shared = ("labor", "finance", "engine")
    return manual + [f"{f}.{k}" for f in shared for k in LOW_CONFIDENCE[f]] + list(stations)


def trend_cagr(month_index: np.ndarray, mean_daily_lines: np.ndarray) -> float | None:
    """F3 step 6 (I52): exp(12 × OLS slope of log(mean daily lines per month) on the month
    index) − 1; None with fewer than 2 months."""
    if len(month_index) < 2:
        return None
    slope = float(np.polyfit(month_index, np.log(mean_daily_lines), 1)[0])
    return math.exp(12 * slope) - 1


def calendar_months(start: date, end: date) -> float:
    """F3 step 6 (I52): whole calendar months from start to end (both included) + leftover
    days / 30.4375; three calendar years are 36.0 months, leap day or not."""
    rd = relativedelta(end + timedelta(days=1), start)
    return rd.years * 12 + rd.months + rd.days / 30.4375


def trend_confidence(months: float) -> str:
    """F3 step 6 [P] (I52): L if < 24 months, M if 24-36, H if > 36."""
    return "L" if months < 24 else "M" if months <= 36 else "H"
