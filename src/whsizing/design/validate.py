"""F4 design basis validation (I60): value ranges and finite design values (ConfigError), and
the leaf-field walk of a DesignBasis. Re-exported by `whsizing.design.basis`."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from whsizing.errors import ConfigError
from whsizing.schemas import DesignBasis

_GT0 = (lambda v: v > 0, "> 0")
_GE1 = (lambda v: v >= 1, "≥ 1")
_RATE = (lambda v: 0 < v <= 1, "in (0, 1]")
_ALLOWANCE = (lambda v: 0 <= v < 1, "in [0, 1)")
_SHARE = (lambda v: 0 <= v <= 1, "in [0, 1]")
# I60 (+ F4 fix round 1): field → (valid when, rule). Written as "valid when" so NaN fails too.
RULES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "operations.operating_days_per_year": _GE1,
    "operations.shifts_per_day": _GE1,
    "operations.hours_per_shift": _GT0,
    "operations.paid_hours_per_person_day": _GT0,
    "operations.annual_paid_hours_per_fte": _GT0,
    "operations.utilisation": _RATE,
    "operations.absenteeism": _ALLOWANCE,
    "operations.pfd_allowance": _ALLOWANCE,
    "service.same_day_share": _SHARE,
    "projection.horizon_years": (lambda v: v >= 0, "≥ 0"),
    "projection.growth_rate": (lambda v: v > -1, "> -1"),
    "projection.design_percentile": (lambda v: v >= 0, "≥ 0 (above 100 is clipped)"),
    "projection.peak_stock_factor": _GT0,
    "projection.trailing_months": _GE1,
    "flows.returns_rate": _SHARE,
    "flows.inbound_peak_factor": (lambda v: v is None or v > 0, "> 0 or null"),
    "flows.pallets_per_truck": _GT0,
    "flows.truck_dwell_hours": _GT0,
    "flows.dock_utilisation": _RATE,
    "building.area_m2": _GT0,
    "building.clear_height_m": _GT0,
}
FINITE_SECTIONS = ("operations.", "service.", "projection.", "flows.", "building.", "finance.")
# Basis fields a design value overflows from (I60, F4c): named by require_finite
GROWTH_FIELDS = "projection.growth_rate, projection.horizon_years"
STOCK_FIELDS = "projection.peak_stock_factor, overrides.stock_growth_rate, projection.horizon_years"


def leaf_fields(model: BaseModel, prefix: str = "") -> list[tuple[str, BaseModel, str]]:
    """(dotted path, owning model, field name) of every non-model field, in declaration order."""
    out: list[tuple[str, BaseModel, str]] = []
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, BaseModel):
            out += leaf_fields(value, f"{prefix}{name}.")
        else:
            out.append((f"{prefix}{name}", model, name))
    return out


def shift_hours_error(shifts: int, hours: float) -> str | None:
    """The shifts of a day follow one another, so they cannot add up to more than 24 h (the
    engine refuses it too, but only at sizing, after the design day was written)."""
    return f"operations: {shifts} shifts × {hours} h exceed 24 h" if shifts * hours > 24 else None


def check_basis(basis: DesignBasis, overrides: dict[str, Any] | None = None) -> DesignBasis:
    """I60: no NaN / ±inf float (mapping values included) in the sized sections, and the RULES
    ranges; a failure → ConfigError naming each field. `overrides`: the values as read from the
    YAML, before pydantic coerced them (default `basis.overrides`), to tell a bool."""
    wrong: list[str] = []
    for path, owner, name in leaf_fields(basis):
        value = getattr(owner, name)
        values = value.values() if isinstance(value, dict) else [value]
        if path.startswith(FINITE_SECTIONS) and any(
            isinstance(v, float) and not math.isfinite(v) for v in values
        ):
            wrong.append(f"{path} = {value!r} (must be finite)")
        elif path in RULES and not RULES[path][0](value):
            wrong.append(f"{path} = {value!r} (must be {RULES[path][1]})")
    ops = basis.operations
    if (problem := shift_hours_error(ops.shifts_per_day, ops.hours_per_shift)) is not None:
        wrong.append(problem)
    wrong += _override_errors(basis.overrides, overrides or basis.overrides)
    if wrong:
        raise ConfigError(f"basis: invalid value(s): {'; '.join(wrong)}")
    return basis


def _override_errors(overrides: dict[str, float], raw: dict[str, Any]) -> list[str]:
    """Each override must be a finite number. A YAML bool (`raw`: the value as read) is not one,
    although pydantic made it 1.0; numeric text (PyYAML reads 1e-2 as text) is coerced by
    pydantic like in any typed basis field (F4c). stock_growth_rate replaces g in F4 step 7
    (1 + g)^T, so it must also be > -1."""
    wrong: list[str] = []
    for pid, v in overrides.items():
        r = raw.get(pid, v)
        if isinstance(r, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            wrong.append(f"overrides.{pid} = {r!r} (must be a finite number)")
        elif pid == "stock_growth_rate" and v <= -1:
            wrong.append(f"overrides.{pid} = {v!r} (must be finite and > -1)")
    return wrong


def require_finite(values: dict[str, float | None], fields: str) -> None:
    """I60: a finite but huge basis value (growth rate 1e308) can still overflow a design value
    to ±inf or NaN: every design value must be finite, else ConfigError naming it and `fields`,
    the basis fields it comes from."""
    bad = [f"{k} = {v!r}" for k, v in values.items() if v is not None and not math.isfinite(v)]
    if bad:
        raise ConfigError(f"design value(s) not finite: {'; '.join(bad)}; check {fields}")
