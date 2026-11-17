"""F7 baseline of the NPV / IRR / payback: another scenario's computed costs (I42) or the client's
current operation. Returns capex and opex totals per world and traces them in the compared
scenario's Tracer (`<sid>.finance.baseline.capex`, `<sid>.finance.baseline.opex.y<t>`)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from whsizing.catalog import Catalog
from whsizing.errors import ConfigError
from whsizing.finance.context import Ctx
from whsizing.finance.opex import FIN, OPS, role_cost
from whsizing.schemas import DesignBasis, World

CLIENT_NOTE = (
    "baseline = the client's current operation: capex 0 (sunk); opex = labor from "
    "basis.baseline (actual hours, or actual FTE × annual_paid_hours_per_fte × utilisation, the "
    "F6 core_fte convention; grown at g, wage inflation applied) + the scenario's own "
    "consumables and rent (they cancel in the deltas); maintenance, energy and software of the "
    "existing equipment are not modelled (0)"
)

# Coarse labels of the spec's example basis (Appendix E `actual_fte`) → catalog role key: the
# primary role of the activities the label covers (picking, packing, shipping_parcel: operator;
# receiving, put_away: forklift). A client who needs finer costs names the catalog activities.
COARSE_ROLE = {
    "picking": "operator",
    "packing": "operator",
    "receiving": "forklift",
    "shipping": "operator",
    "indirect": "lead",
}


class Base(NamedTuple):
    """Baseline costs in one world: year-0 capex and opex totals of years 1..T (EUR)."""

    capex: float
    opex: list[float]


def client_hours(basis: DesignBasis, catalog: Catalog) -> dict[str, float] | None:
    """Base-year hours per label of the client's current operation: `actual_hours_month`
    (annualised ×12 / months) else `actual_fte` × annual_paid_hours_per_fte × utilisation (the
    productive hours of Appendix B's core_fte); None when `basis.baseline` holds neither. Labels
    are catalog activities or the coarse ones of `COARSE_ROLE`."""
    b, ops = basis.baseline, basis.operations
    productive = ops.annual_paid_hours_per_fte * ops.utilisation
    hours = {a: _non_negative(f"actual_fte[{a!r}]", fte) * productive
             for a, fte in (b.actual_fte or {}).items()}  # fmt: skip
    for a, monthly in (b.actual_hours_month or {}).items():
        if not monthly:
            raise ConfigError(f"baseline.actual_hours_month[{a!r}] is empty")
        hours[a] = _non_negative(f"actual_hours_month[{a!r}]", *monthly) * 12 / len(monthly)
    known = {*catalog.labor.activities, *COARSE_ROLE}
    unknown = sorted(set(hours) - known)
    if unknown:
        raise ConfigError(f"baseline: unknown activities {unknown} (known: {sorted(known)})")
    return hours or None


def _non_negative(name: str, *values: float) -> float:
    """Σ values; a negative or non-finite value is refused (baseline inputs are client data)."""
    if any(v < 0 or not math.isfinite(v) for v in values):
        raise ConfigError(f"baseline.{name}: negative or non-finite value in {list(values)}")
    return sum(values)


def label_role(label: str, catalog: Catalog) -> str:
    """Finance cost key (`labor_cost_eur_h`) of a baseline label."""
    if label in catalog.labor.activities:
        return catalog.labor.roles[catalog.labor.activities[label].role]
    return catalog.labor.roles[COARSE_ROLE[label]]


def trace_scenario_base(
    baseline_id: str, ctxs: Mapping[World, Ctx], base: Mapping[World, Base]
) -> None:
    """Trace the computed costs of the baseline scenario (`base`) as `data:<baseline id>.…`
    leaves in every world of the compared scenario."""
    for w, c in ctxs.items():
        c.rec(
            "finance.baseline.capex",
            f"Capex of baseline {baseline_id}",
            base[w].capex,
            "eur",
            "capex.total of the baseline scenario",
            {"baseline_capex": f"data:{baseline_id}.capex.total"},
        )
        for t, x in enumerate(base[w].opex, start=1):
            c.rec(
                f"finance.baseline.opex.y{t}",
                f"Opex of baseline {baseline_id}, year {t}",
                x,
                "eur",
                f"opex.y{t}.total of the baseline scenario",
                {"baseline_opex": f"data:{baseline_id}.opex.y{t}.total"},
            )


def client_base(
    hours: Mapping[str, float],
    catalog: Catalog,
    ctxs: Mapping[World, Ctx],
    scenario_opex: Mapping[World, Sequence[Mapping[str, float]]],
) -> dict[World, Base]:
    """Client baseline (CLIENT_NOTE): capex 0; opex_t = Σ_a hours_a × (1 + g)^t × cost(role_a) ×
    (1 + shift_premium) × (1 + wage_inflation)^(t−1) + the scenario's consumables_t and rent_t."""
    out: dict[World, Base] = {}
    for w, c in ctxs.items():
        fin, g = c.basis.finance, c.basis.projection.growth_rate
        base_year = sum(h * role_cost(c, label_role(a, catalog)) for a, h in hours.items())
        c.rec(
            "finance.baseline.capex",
            "Capex of the client's current operation",
            0.0,
            "eur",
            "0: sunk",
            {},
        )
        opex: list[float] = []
        for t, row in enumerate(scenario_opex[w], start=1):
            labor = base_year * (1 + fin.shift_premium) * (1 + g) ** t
            labor *= (1 + fin.wage_inflation) ** (t - 1)
            value = labor + row["consumables"] + row["rent"]
            opex.append(
                c.rec(
                    f"finance.baseline.opex.y{t}",
                    f"Opex of the client's operation, year {t}",
                    value,
                    "eur",
                    "Σ_a actual_hours_a × (1 + g)^t × cost(role_a) × (1 + shift_premium) × "
                    "(1 + wage_inflation)^(t−1) + consumables + rent",
                    {
                        "actual_fte": "data:basis.baseline.actual_fte",
                        "actual_hours_month": "data:basis.baseline.actual_hours_month",
                        "annual_paid_hours_per_fte": f"{OPS}annual_paid_hours_per_fte",
                        "utilisation": f"{OPS}utilisation",
                        "labor_cost_eur_h": f"{FIN}labor_cost_eur_h",
                        "shift_premium": f"{FIN}shift_premium",
                        "wage_inflation": f"{FIN}wage_inflation",
                        "growth_rate": "data:basis.projection.growth_rate",
                        "consumables": c.tid(f"opex.y{t}.consumables"),
                        "rent": c.tid(f"opex.y{t}.rent"),
                    },
                )
            )
        out[w] = Base(0.0, opex)
    return out
