"""F7 opex of years 1..T for one scenario in one world (trace ids `<sid>.opex.y<t>.<item>`).

Items: labor, maintenance, energy, software, consumables, rent, renewal, `total` (the sum).
Rules: I32 (energy), I33 (labor, literal: temp hours are also inside the annual hours), I34
(maintenance), I35 (software, maintenance and rent flat; consumables = annual orders ×
packaging; renewal = family renewal_share × equipment item in year equipment_life_years only),
I41 (growth exponent t, wage and energy inflation exponent t − 1), I48 (degenerate = manual).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import polars as pl

from whsizing.catalog import Catalog
from whsizing.errors import ConfigError, DataQualityError
from whsizing.finance.capex import Capex, M
from whsizing.finance.context import Ctx
from whsizing.schemas import DesignBasis

ITEMS = ("labor", "maintenance", "energy", "software", "consumables", "rent", "renewal")
FIN = "data:basis.finance."
OPS = "data:basis.operations."


def role_costs(catalog: Catalog, basis: DesignBasis) -> dict[str, float]:
    """Loaded hourly cost per role: the catalog `default_roles_cost_eur_h` (Appendix D), replaced
    by the client's `basis.finance.labor_cost_eur_h` role by role. A client key that is not a role
    of the catalog (a typo) and negative costs are refused."""
    valid = {*catalog.finance.default_roles_cost_eur_h, *catalog.labor.roles.values()}
    unknown = sorted(set(basis.finance.labor_cost_eur_h) - valid)
    if unknown:
        raise ConfigError(
            f"finance.labor_cost_eur_h: unknown role(s) {', '.join(map(repr, unknown))}; "
            f"the valid roles are {sorted(valid)}"
        )
    costs = {**catalog.finance.default_roles_cost_eur_h, **basis.finance.labor_cost_eur_h}
    negative = sorted(r for r, x in costs.items() if x < 0 or not math.isfinite(x))
    if negative:
        raise ConfigError(f"finance.labor_cost_eur_h: negative or non-finite cost for {negative}")
    return costs


def role_cost(c: Ctx, role: str) -> float:
    """Loaded hourly cost of a role (`Ctx.role_costs`)."""
    if role not in c.role_costs:
        raise ConfigError(
            f"finance.labor_cost_eur_h has no cost for role {role!r} and the catalog has no "
            f"default (has {sorted(c.role_costs)})"
        )
    return c.role_costs[role]


def cost_ref(c: Ctx, role: str) -> str:
    """Trace leaf of a role's cost: the client's value, else the catalog default."""
    if role in c.basis.finance.labor_cost_eur_h:
        return f"{FIN}labor_cost_eur_h.{role}"
    return f"data:catalog.finance.default_roles_cost_eur_h.{role}"


def annual_total(c: Ctx, daily: pl.DataFrame, column: str, key: str, t: int) -> float:
    """I4, I41: Σ_{operating days} column × operating_days_per_year / n_op × (1 + g)^t; traced as
    `<sid>.<key>`."""
    missing = {"is_operating", column} - set(daily.columns)
    if missing:
        raise DataQualityError(f"finance: the daily series lacks column(s) {sorted(missing)}")
    ops = daily.filter(pl.col("is_operating").fill_null(False))
    if ops.is_empty():
        raise DataQualityError("finance: the daily series has no operating day")
    k = c.basis.operations.operating_days_per_year / ops.height
    value = float(ops[column].sum()) * k * (1 + c.basis.projection.growth_rate) ** t
    return c.rec(
        key,
        f"Annual {column}, year {t}",
        value,
        column,
        f"Σ_operating days {column} × operating_days_per_year / n_op × (1 + g)^t",
        {
            column: f"data:daily.{column}",
            "is_operating": "data:daily.is_operating",
            "operating_days_per_year": f"{OPS}operating_days_per_year",
            "growth_rate": "data:basis.projection.growth_rate",
        },
    )


def energy_kwh(c: Ctx) -> float:
    """I32: robots × kWh/robot + ports (stations) × kWh/station + forklifts × kWh/forklift + fixed;
    traced as `<sid>.opex.energy_kwh_year`."""
    fam, forklifts = c.fam, c.q("equipment.forklifts")
    kwh = forklifts * c.v(f"{M}kwh_per_forklift_year") + c.v("finance.fixed_energy_kwh_year")
    terms = ["forklifts × kwh_per_forklift_year", "fixed_energy_kwh_year"]
    inputs = {
        "forklifts": c.tid("equipment.forklifts"),
        "kwh_per_forklift_year": f"param:{M}kwh_per_forklift_year",
        "fixed_energy_kwh_year": "param:finance.fixed_energy_kwh_year",
    }
    if c.auto:
        stations = "equipment.ports" if fam == "cube_asrs" else "equipment.gtp_stations"
        kwh += c.q("equipment.robots") * c.v(f"{fam}.kwh_per_robot_year")
        kwh += c.q(stations) * c.v("finance.kwh_per_station_year")
        terms = ["robots × kwh_per_robot_year", "stations × kwh_per_station_year", *terms]
        inputs |= {
            "robots": c.tid("equipment.robots"),
            "kwh_per_robot_year": f"param:{fam}.kwh_per_robot_year",
            "stations": c.tid(stations),
            "kwh_per_station_year": "param:finance.kwh_per_station_year",
        }
    return c.rec("opex.energy_kwh_year", "Energy use", kwh, "kWh", " + ".join(terms), inputs)


def opex_years(
    c: Ctx, cap: Capex, activities: Sequence[tuple[str, str]], daily: pl.DataFrame, years: int
) -> list[dict[str, float]]:
    """Opex items of years 1..`years`. `activities` = (activity, role) of the F6 labor result;
    the year-t hours are the F6 nodes `labor.<activity>.annual_hours.y<t>` and
    `labor.temp_hours.y<t>`."""
    fam, items = c.fam, cap.items
    maintenance = _maintenance(c, cap)
    kwh = energy_kwh(c)
    software = c.v(f"{fam}.software_eur_year")
    rent = _rent(c)
    out: list[dict[str, float]] = []
    for t in range(1, years + 1):
        row = {
            "labor": _labor(c, activities, t),
            "maintenance": _flat(
                c, t, "maintenance", "Maintenance", maintenance, c.tid("opex.maintenance")
            ),
            "energy": _energy(c, kwh, t),
            "software": c.rec(
                f"opex.y{t}.software",
                f"Software, year {t}",
                software,
                "eur",
                "software_eur_year",
                {"software_eur_year": f"param:{fam}.software_eur_year"},
            ),
            "consumables": _consumables(c, daily, t),
            "rent": _flat(c, t, "rent", "Rent", rent, c.tid("opex.rent_year")),
            "renewal": _renewal(c, items["equipment"], t),
        }
        total = c.rec(
            f"opex.y{t}.total",
            f"Opex, year {t}",
            sum(row.values()),
            "eur",
            "Σ items",
            {k: c.tid(f"opex.y{t}.{k}") for k in ITEMS},
        )
        out.append({**row, "total": total})
    return out


def _flat(c: Ctx, t: int, item: str, label: str, value: float, source: str) -> float:
    """A constant yearly cost (I35: no inflation), traced per year from its yearly node."""
    return c.rec(
        f"opex.y{t}.{item}",
        f"{label}, year {t}",
        value,
        "eur",
        f"{item}_eur_year (flat)",
        {f"{item}_eur_year": source},
    )


def _labor(c: Ctx, activities: Sequence[tuple[str, str]], t: int) -> float:
    """I33: [Σ_a hours_a,t × cost(role_a) × (1 + shift_premium) + temp_hours_t × cost_operator ×
    (1 + temp_premium)] × (1 + wage_inflation)^(t−1)."""
    fin = c.basis.finance
    hours = {a: c.q(f"labor.{a}.annual_hours.y{t}") for a, _ in activities}
    direct = sum(hours[a] * role_cost(c, role) for a, role in activities)
    temp = c.q(f"labor.temp_hours.y{t}") * role_cost(c, "operator")
    value = (direct * (1 + fin.shift_premium) + temp * (1 + fin.temp_premium)) * (
        (1 + fin.wage_inflation) ** (t - 1)
    )
    inputs = {f"hours_{a}": c.tid(f"labor.{a}.annual_hours.y{t}") for a, _ in activities}
    inputs |= {f"cost_{role}": cost_ref(c, role) for role in sorted({r for _, r in activities})}
    inputs |= {
        "temp_hours": c.tid(f"labor.temp_hours.y{t}"),
        "cost_operator": cost_ref(c, "operator"),
        "shift_premium": f"{FIN}shift_premium",
        "temp_premium": f"{FIN}temp_premium",
        "wage_inflation": f"{FIN}wage_inflation",
    }
    return c.rec(
        f"opex.y{t}.labor",
        f"Labor cost, year {t}",
        value,
        "eur",
        "[Σ_a hours_a × cost(role_a) × (1 + shift_premium) + temp_hours × cost_operator × "
        "(1 + temp_premium)] × (1 + wage_inflation)^(t−1)",
        inputs,
    )


def _maintenance(c: Ctx, cap: Capex) -> float:
    """I34: family share × equipment item; an automated family adds the manual share × the manual
    zone's carts and forklifts."""
    fam = c.fam
    share = c.v(f"{fam}.maintenance_share_of_equipment_capex")
    value = share * cap.items["equipment"]
    formula = "maintenance_share × equipment"
    inputs = {
        "maintenance_share": f"param:{fam}.maintenance_share_of_equipment_capex",
        "equipment": c.tid("capex.equipment"),
    }
    if c.auto:
        value += c.v(f"{M}maintenance_share_of_equipment_capex") * cap.manual_equipment
        formula += " + manual_maintenance_share × overflow_equipment"
        inputs |= {
            "manual_maintenance_share": f"param:{M}maintenance_share_of_equipment_capex",
            "overflow_equipment": c.tid("capex.overflow.equipment"),
        }
    return c.rec("opex.maintenance", "Maintenance per year", value, "eur", formula, inputs)


def _rent(c: Ctx) -> float:
    """Rent per year by `building.rent_mode`: footprint = area.total × rent, full_building =
    building area × rent, none = 0."""
    b = c.basis.building
    base = {
        "footprint": ("area_total", c.tid("area.total")),
        "full_building": ("building_area_m2", "data:basis.building.area_m2"),
    }
    if b.rent_mode == "none":
        return c.rec("opex.rent_year", "Rent per year", 0.0, "eur", "0: rent_mode = none", {})
    area = c.q("area.total") if b.rent_mode == "footprint" else b.area_m2
    name, ref = base[b.rent_mode]
    return c.rec(
        "opex.rent_year",
        "Rent per year",
        area * b.rent_eur_m2_year,
        "eur",
        f"{name} × rent_eur_m2_year ({b.rent_mode})",
        {name: ref, "rent_eur_m2_year": "data:basis.building.rent_eur_m2_year"},
    )


def _energy(c: Ctx, kwh: float, t: int) -> float:
    fin = c.basis.finance
    return c.rec(
        f"opex.y{t}.energy",
        f"Energy cost, year {t}",
        kwh * fin.energy_price_eur_kwh * (1 + fin.energy_inflation) ** (t - 1),
        "eur",
        "kWh × price × (1 + energy_inflation)^(t−1)",
        {
            "kwh": c.tid("opex.energy_kwh_year"),
            "price": f"{FIN}energy_price_eur_kwh",
            "energy_inflation": f"{FIN}energy_inflation",
        },
    )


def _consumables(c: Ctx, daily: pl.DataFrame, t: int) -> float:
    orders = annual_total(c, daily, "orders", f"finance.annual_orders.y{t}", t)
    return c.rec(
        f"opex.y{t}.consumables",
        f"Consumables, year {t}",
        orders * c.v("finance.packaging_eur_per_order"),
        "eur",
        "annual_orders × packaging_eur_per_order",
        {
            "annual_orders": c.tid(f"finance.annual_orders.y{t}"),
            "packaging_eur_per_order": "param:finance.packaging_eur_per_order",
        },
    )


def _life(c: Ctx) -> float:
    """`equipment_life_years` for the renewal year of I35 (t == life). A life <= 0, or a fractional
    one inside the horizon, would never match a year t and silently drop a renewal: refused. A
    fractional life beyond the horizon never renews within it, as for any life > T."""
    key, horizon = f"{c.fam}.equipment_life_years", c.basis.finance.horizon_years
    life = c.v(key)
    if life <= 0 or (life != int(life) and life <= horizon):
        raise ConfigError(
            f"{key} = {life}: the renewal year must be a whole number of years >= 1 when it falls "
            f"within the {horizon}-year horizon (I35)"
        )
    return life


def _renewal(c: Ctx, equipment: float, t: int) -> float:
    """I35: renewal_share × equipment item when t == equipment_life_years (nothing otherwise)."""
    fam = c.fam
    due = float(t) == _life(c)
    return c.rec(
        f"opex.y{t}.renewal",
        f"Renewal, year {t}",
        c.v(f"{fam}.renewal_share") * equipment if due else 0.0,
        "eur",
        "renewal_share × equipment if t == equipment_life_years else 0",
        {
            "renewal_share": f"param:{fam}.renewal_share",
            "equipment_life_years": f"param:{fam}.equipment_life_years",
            "equipment": c.tid("capex.equipment"),
        },
    )
