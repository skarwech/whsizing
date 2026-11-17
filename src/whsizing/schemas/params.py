"""Shared base model, literals, Param and Range (§2.5, §2.5.1)."""

from __future__ import annotations

import datetime as dt
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from whsizing.units import is_unit

Confidence = Literal["H", "M", "L"]
FamilyId = Literal["manual_p2p", "amr_gtp", "cube_asrs"]
World = Literal["lo", "typ", "hi"]
DatasetKind = Literal["order_lines", "sku_master", "inventory", "receipts"]


class StrictModel(BaseModel):
    """Base of every contract: unknown keys are rejected (§3.1 `extra="forbid"`)."""

    model_config = ConfigDict(extra="forbid")


class Param(BaseModel, frozen=True, extra="forbid"):
    """A catalog or basis parameter with provenance. `unit` is '-' or a unit of the project's pint
    registry (`whsizing.units`, I87): any other value is a validation error naming id and unit."""

    id: str  # e.g. "cube_asrs.port_rate_lines_h"
    unit: str
    min: float
    typ: float
    max: float
    source: str  # citation, "expert:<name>:<yyyy-mm>", or "TODO"
    confidence: Confidence
    pessimistic_end: Literal["min", "max"]  # which bound is the pessimistic world (see 2.5.1)
    validated_by: str | None = None
    date: dt.date
    note: str | None = None

    @field_validator("date", mode="before")
    @classmethod
    def _year_month(cls, v: object) -> object:
        # ponytail: catalog writes `date: 2026-11` (Appendix C) = 1st of the month
        if isinstance(v, str) and len(v) == 7 and v[4] == "-":
            return f"{v}-01"
        return v

    @model_validator(mode="after")
    def _checked(self) -> Self:
        if not is_unit(self.unit):
            raise ValueError(
                f"{self.id}: unit {self.unit!r} is not a pint unit (see whsizing.units)"
            )
        if not (self.min <= self.typ <= self.max):
            raise ValueError(f"{self.id}: min ≤ typ ≤ max violated")
        return self


class Range(BaseModel, frozen=True, extra="forbid"):
    """A computed quantity: lo ≤ typ ≤ hi, value-ordered."""

    lo: float
    typ: float
    hi: float
    unit: str

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not (self.lo <= self.typ <= self.hi):
            raise ValueError(
                f"Range [{self.unit}]: lo ≤ typ ≤ hi violated ({self.lo}, {self.typ}, {self.hi})"
            )
        return self
