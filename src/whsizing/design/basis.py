"""F4 design basis: loader, commented FR/EN template and basis-level helpers (§2.5, App. E)."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

import polars as pl
import yaml
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from whsizing.config import load_yaml_model
from whsizing.design.validate import (  # noqa: F401  re-exported: callers import from here
    FINITE_SECTIONS,
    GROWTH_FIELDS,
    RULES,
    STOCK_FIELDS,
    check_basis,
    leaf_fields,
    require_finite,
)
from whsizing.errors import ConfigError, WhsizingError
from whsizing.logging import get_logger
from whsizing.profile.aggregate import METRICS
from whsizing.profile.seasonality import DAYS_PER_MONTH, calendar_months
from whsizing.schemas import DesignBasis, Projection, Service

FULL_HISTORY_MONTHS = 12  # F4 step 1: warn when the window covers less than 12 months (I55)
TWO_PEAKS_MONTHS = 24  # F4 step 1: "use 24 months when available so two peaks are covered"
TWO_PEAKS_MIN = 23.9  # I55: history months (calendar days / 30.4375) from which 24 is used
DAILY_COLUMNS = ("date", "weekday", "is_operating", *METRICS)  # F3 daily columns F4 reads
# Fields written commented out by the template: left unset, F4 derives them (I55)
UNSET_IN_TEMPLATE = frozenset({"projection.trailing_months"})

# Leaf field path → (unit, English label, French label). Units feed the assumptions list.
FIELDS: dict[str, tuple[str, str, str]] = {
    "client": ("-", "client name", "nom du client"),
    "site": ("-", "site name", "nom du site"),
    "currency": ("-", "currency", "devise"),
    "timezone": ("-", "timezone of the data", "fuseau horaire des données"),
    "operations.operating_days_per_year": (
        "d/yr",
        "operating days per year",
        "jours ouvrés par an",
    ),
    "operations.shifts_per_day": ("-", "shifts per day", "équipes par jour"),
    "operations.hours_per_shift": ("h", "hours per shift", "heures par équipe"),
    "operations.paid_hours_per_person_day": (
        "h",
        "paid hours per person-day",
        "heures payées par personne-jour",
    ),
    "operations.annual_paid_hours_per_fte": (
        "h/yr",
        "annual paid hours per FTE (French 35 h)",
        "heures payées annuelles par ETP (35 h)",
    ),
    "operations.utilisation": (
        "-",
        "share of paid time on direct work",
        "part du temps payé en travail direct",
    ),
    "operations.absenteeism": ("-", "absenteeism", "absentéisme"),
    "operations.pfd_allowance": (
        "-",
        "personal, fatigue and delay allowance",
        "majoration repos, fatigue, aléas",
    ),
    "service.cutoff_time": ("hh:mm", "order cutoff time", "heure limite de commande"),
    "service.carrier_departure_time": (
        "hh:mm",
        "carrier departure time",
        "heure de départ transporteur",
    ),
    "service.same_day_share": (
        "-",
        "share of lines shipped the same day",
        "part des lignes expédiées le jour même",
    ),
    "service.sla_window_hours": (
        "h",
        "SLA window (null = departure − cutoff)",
        "fenêtre SLA (null = départ − heure limite)",
    ),
    "projection.horizon_years": ("yr", "sizing horizon", "horizon de dimensionnement"),
    "projection.growth_rate": ("1/yr", "annual volume growth", "croissance annuelle des volumes"),
    "projection.design_percentile": (
        "%",
        "design-day percentile",
        "percentile du jour de conception",
    ),
    "projection.peak_stock_factor": (
        "-",
        "peak stock / average stock",
        "stock de pointe / stock moyen",
    ),
    "projection.trailing_months": (
        "months",
        "design-day window (unset: 24 if the history covers 24 months, else 12; warns under 12 "
        "calendar months)",
        "fenêtre du jour de conception (absente : 24 si l'historique couvre 24 mois, sinon 12 ; "
        "alerte sous 12 mois calendaires)",
    ),
    "flows.returns_rate": (
        "-",
        "returned lines / shipped lines",
        "lignes retournées / lignes expédiées",
    ),
    "flows.inbound_mode": (
        "-",
        "inbound from receipts or derived",
        "réception : réceptions ou dérivée",
    ),
    "flows.inbound_peak_factor": (
        "-",
        "inbound peak factor (null = outbound peak-to-average in derived mode, 1.0 in receipts "
        "mode)",
        "facteur de pointe réception (null = pointe/moyenne sortie en mode dérivé, 1,0 en mode "
        "réceptions)",
    ),
    "flows.pallets_per_truck": ("pallets", "pallets per truck", "palettes par camion"),
    "flows.truck_dwell_hours": ("h", "truck dwell time at the dock", "temps de quai par camion"),
    "flows.dock_utilisation": ("-", "dock utilisation", "taux d'occupation des quais"),
    "flows.pallet_order_weight_kg": (
        "kg",
        "orders at or above ship as pallets",
        "commandes expédiées en palette au-delà de",
    ),
    "flows.pallet_order_cube_m3": (
        "m3",
        "orders at or above ship as pallets",
        "commandes expédiées en palette au-delà de",
    ),
    "flows.parcel_max_weight_kg": ("kg", "maximum parcel weight", "poids maximal d'un colis"),
    "building.area_m2": ("m2", "building area", "surface du bâtiment"),
    "building.clear_height_m": ("m", "clear height", "hauteur libre"),
    "building.dock_doors_in": ("doors", "inbound dock doors", "quais de réception"),
    "building.dock_doors_out": ("doors", "outbound dock doors", "quais d'expédition"),
    "building.floor_load_t_m2": ("t/m2", "floor load", "charge au sol"),
    "building.sprinklered": ("-", "sprinklered", "sprinklé"),
    "building.rent_eur_m2_year": ("eur/m2/yr", "rent", "loyer"),
    "building.rent_mode": (
        "-",
        "rent basis: footprint, full_building or none",
        "base du loyer : footprint, full_building ou none",
    ),
    "finance.discount_rate": ("1/yr", "discount rate", "taux d'actualisation"),
    "finance.horizon_years": ("yr", "financial horizon", "horizon financier"),
    "finance.wage_inflation": ("1/yr", "wage inflation", "inflation salariale"),
    "finance.energy_inflation": ("1/yr", "energy inflation", "inflation de l'énergie"),
    "finance.energy_price_eur_kwh": ("eur/kWh", "energy price", "prix de l'énergie"),
    "finance.labor_cost_eur_h": (
        "eur/h",
        "loaded hourly cost per role",
        "coût horaire chargé par rôle",
    ),
    "finance.temp_premium": (
        "-",
        "premium on temporary labour hours",
        "surcoût des heures intérimaires",
    ),
    "finance.shift_premium": ("-", "shift premium", "prime d'équipe"),
    "baseline.description": ("-", "current operation", "fonctionnement actuel"),
    "baseline.actual_fte": ("FTE", "actual FTE per activity", "ETP actuels par activité"),
    "baseline.actual_hours_month": (
        "h/month",
        "actual hours per month per activity",
        "heures mensuelles réelles par activité",
    ),
    "baseline.equipment": ("units", "current equipment counts", "équipements actuels"),
    "overrides": (
        "-",
        "catalog parameter id → client value",
        "id de paramètre catalogue → valeur client",
    ),
}
VERIFY = frozenset({"operations.annual_paid_hours_per_fte"})  # [VERIFY] in §2.5
# Required client values: example shown in the template (Appendix E)
EXAMPLES: dict[str, Any] = {
    "client": "Client X",
    "site": "Lyon",
    "service.cutoff_time": "15:00",
    "service.carrier_departure_time": "18:30",
    "building.area_m2": 12000,
    "building.clear_height_m": 10.5,
    "building.dock_doors_in": 4,
    "building.dock_doors_out": 6,
    "finance.labor_cost_eur_h": {"operator": 25.5, "forklift_driver": 27.8, "team_leader": 33.0},
}
HEADER = {
    "en": [
        "whsizing design basis (Appendix E). Edit the values, keep the keys (unknown keys are",
        "rejected). [P] = placeholder default, to confirm with the client; [CLIENT] = required",
        'client value (example shown). Times are quoted strings: "15:00".',
    ],
    "fr": [
        "Base de conception whsizing (annexe E). Modifier les valeurs, garder les clés (une clé",
        "inconnue est refusée). [P] = valeur par défaut provisoire, à confirmer avec le client ;",
        '[CLIENT] = valeur client obligatoire (exemple). Heures entre guillemets : "15:00".',
    ],
}


def load_basis(path: Path | str) -> DesignBasis:
    """basis.yaml → DesignBasis; invalid YAML, unknown key or bad value → ConfigError (T4.6)."""
    basis = load_yaml_model(path, DesignBasis)
    # ponytail: second read of the file, pydantic has already turned a YAML `true` into 1.0
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return check_basis(basis, raw.get("overrides") or {})


def sla_window_hours(service: Service) -> float:
    """I16: the given window (> 0), else carrier_departure − cutoff modulo 24 h (crossing
    midnight allowed: 22:00 → 02:00 = 4 h; equal times = 24 h)."""
    if service.sla_window_hours is not None:
        if service.sla_window_hours <= 0:
            raise ConfigError("service.sla_window_hours must be > 0 (or null to derive it)")
        return service.sla_window_hours
    day = date(2000, 1, 1)
    gap = datetime.combine(day, service.carrier_departure_time) - datetime.combine(
        day, service.cutoff_time
    )
    hours = (gap.total_seconds() / 3600) % 24
    return hours or 24.0


def growth_factor(rate: float, years: int) -> float:
    """F4 step 5: (1 + g)^T; a result beyond the float range → ConfigError."""
    try:
        return (1 + rate) ** years
    except OverflowError:
        raise ConfigError(
            f"growth factor (1 + {rate})^{years} overflows: check projection.growth_rate, "
            "projection.horizon_years and overrides.stock_growth_rate"
        ) from None


def history_span(daily: pl.DataFrame) -> tuple[date, date]:
    """(first, last) date of the F3 daily series; a missing F3 column → WhsizingError naming it
    (rather than a raw polars error)."""
    missing = [c for c in DAILY_COLUMNS if c not in daily.columns]
    if missing:
        raise WhsizingError(f"daily frame: missing column(s) {missing} (F3 build_tables output)")
    if daily.is_empty():
        raise WhsizingError("daily frame: no day, no design day can be chosen")
    return daily["date"].min(), daily["date"].max()  # pyright: ignore[reportReturnType]


def window_months(projection: Projection, daily: pl.DataFrame) -> int:
    """I55: trailing_months set in the basis file → as given; left at its default → 24 when the
    history covers ≥ 23.9 months (calendar days / 30.4375), else 12 (I5 for a shorter one)."""
    if "trailing_months" in projection.model_fields_set:
        return projection.trailing_months
    start, end = history_span(daily)
    covered = ((end - start).days + 1) / DAYS_PER_MONTH
    return TWO_PEAKS_MONTHS if covered >= TWO_PEAKS_MIN else projection.trailing_months


def candidate_days(daily: pl.DataFrame, trailing_months: int) -> pl.DataFrame:
    """F4 step 1: operating days with date > period_end − trailing_months; with a shorter
    history every operating day (I5)."""
    if trailing_months < 1:
        raise ConfigError("projection.trailing_months must be ≥ 1")
    _, end = history_span(daily)
    cutoff = end - relativedelta(months=trailing_months)
    cand = daily.filter(pl.col("is_operating") & (pl.col("date") > cutoff)).sort("date")
    if cand.is_empty():
        raise WhsizingError(
            f"no operating day in the last {trailing_months} months up to {end}: "
            "no design day can be chosen"
        )
    return cand


def warn_short_window(daily: pl.DataFrame, trailing_months: int) -> None:
    """I55: warn when the window used covers less than 12 months of history, in the I52
    calendar-months convention (whole calendar months + leftover days / 30.4375): a 365-day
    history and a 12-month window on a longer history are both 12.0 and do not warn."""
    start, end = history_span(daily)
    if min(trailing_months, calendar_months(start, end)) < FULL_HISTORY_MONTHS:
        get_logger().warning(
            "design_day_short_window",
            trailing_months=trailing_months,
            history_start=str(start),
            history_end=str(end),
        )


def yaml_value(value: Any) -> str:
    """A flow-style YAML scalar or mapping (JSON is valid YAML); times quoted as "HH:MM"."""
    if isinstance(value, time):
        return json.dumps(value.strftime("%H:%M"))
    return json.dumps(value, ensure_ascii=False)


def basis_template(out: Path, lang: Literal["fr", "en"]) -> None:
    """Write a commented basis.yaml: every default marked [P], required values [CLIENT]."""
    if lang not in HEADER:
        raise ConfigError(f"basis template language must be 'fr' or 'en', not {lang!r}")
    lines = [f"# {h}" for h in HEADER[lang]]
    section = ""
    for path, field in _template_fields():
        head, _, name = path.rpartition(".")
        if head != section:
            lines += ["", f"{head}:"] if head else [""]
            section = head
        unit, en, fr = FIELDS[path]
        required = field.default is PydanticUndefined
        value = EXAMPLES[path] if required else field.get_default(call_default_factory=True)
        tag = "[CLIENT]" if required else "[P]" + (" [VERIFY]" if path in VERIFY else "")
        indent = ("  " if head else "") + ("# " if path in UNSET_IN_TEMPLATE else "")
        unit_txt = "" if unit == "-" else f" ({unit})"
        lines.append(
            f"{indent}{name}: {yaml_value(value)}  # {tag} {fr if lang == 'fr' else en}{unit_txt}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _template_fields() -> list[tuple[str, Any]]:
    """(path, FieldInfo) of every leaf field of the DesignBasis schema (no instance needed)."""
    out: list[tuple[str, Any]] = []
    for name, field in DesignBasis.model_fields.items():
        sub = field.annotation
        if isinstance(sub, type) and issubclass(sub, BaseModel):
            out += [(f"{name}.{n}", f) for n, f in sub.model_fields.items()]
        else:
            out.append((name, field))
    return out
